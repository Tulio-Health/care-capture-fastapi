from langchain.prompts import ChatPromptTemplate
from langsmith import traceable
from langchain_core.output_parsers import PydanticOutputParser, StrOutputParser
import json
import re
from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import date, timedelta
from difflib import SequenceMatcher

from src.app.common.llm_factory import get_default_chat_model
from src.app.core.langsmith_trace import LangSmithTrace
from src.app.models.intent_identify import IntentResponse, IntentAiResponse
from src.app.models.past_visit_query import PastVisitQuery, VisitTimeframe
from src.app.chains.ai_chat_intents.not_found_intent.chain import NoDataFoundIntentChain
from src.app.cache.redis import redis_client
from src.app.common.constants.cache_keys import chatbot_conversation_context_key
from .constants import QUERY_PROMPT, RESPONSE_PROMPT

_tracer = None


def get_tracer():
    global _tracer
    if _tracer is None:
        _tracer = LangSmithTrace().trace(tags=[__name__])
    return _tracer


def get_callbacks():
    tracer = get_tracer()
    return [tracer] if tracer is not None else []


NO_PAST_VISIT_INFORMATION_AVAILABLE = (
    "I am sorry, but I don't have any past Provider visit information "
    "available for you, please try with a different query."
)

MAX_SUMMARIES_FOR_LLM = 15


class PastVisitIntentChain:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.no_data_found_chain = NoDataFoundIntentChain()
        self._model = None

        self.query_parser = PydanticOutputParser(pydantic_object=PastVisitQuery)

        self.query_prompt = ChatPromptTemplate.from_messages([
            ("system", QUERY_PROMPT),
            ("user",
             "Generate the query parameters for the following user question: {text}\n"
             "Conversation Context: {conversation_context}")
        ])

        self.response_prompt = ChatPromptTemplate.from_messages([
            ("system", RESPONSE_PROMPT),
            ("user",
             "User Original Question: {text}\n"
             "Conversation History: {conversation_history}\n"
             "Matched Summaries: {matched_summaries}\n"
             "Today's Date: {today_date}")
        ])

        self._query_chain = None
        self._response_content_chain = None

    # ------------------------------------------------------------------ #
    #  Follow-up detection and context resolution                         #
    # ------------------------------------------------------------------ #

    _FOLLOWUP_PATTERNS = re.compile(
        r"\b("
        r"what was|what were|tell me more|more about|"
        r"how about|and the|what about|"
        r"any other|anything else|"
        r"that visit|that appointment|that doctor|that provider|"
        r"the same visit|the same doctor|the same provider|"
        r"during that|from that|in that"
        r")\b",
        re.IGNORECASE,
    )

    def _is_followup(self, text: str, conversation_context: Dict[str, Any]) -> bool:
        """Detect whether the user query is a follow-up to a previous turn."""
        if not conversation_context or not conversation_context.get("lastProvider"):
            return False
        return bool(self._FOLLOWUP_PATTERNS.search(text))

    @staticmethod
    def _condense_summaries(summaries: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        """Create a lightweight provider/date list for query extraction LLM."""
        return [
            {
                "providerName": s.get("providerName", ""),
                "providerSpecialty": s.get("providerSpecialty", ""),
                "appointmentDate": s.get("appointmentDate", ""),
                "appointmentPurpose": s.get("appointmentPurpose", ""),
            }
            for s in summaries
        ]

    # ------------------------------------------------------------------ #
    #  Filtering — operates on enriched summaries (not raw appointments)  #
    # ------------------------------------------------------------------ #

    def filter_summaries(
        self, query: PastVisitQuery, summaries: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Filter enriched summaries based on query parameters."""
        filtered = list(summaries)

        # --- Provider name (fuzzy, case-insensitive, bidirectional) ---
        if query.provider_name:
            q_name = query.provider_name.lower().strip()
            # Strip common titles from query for better matching
            for title in ["dr.", "dr ", "doctor "]:
                if q_name.startswith(title):
                    q_name = q_name[len(title):].strip()
            q_tokens = set(q_name.split())

            def matches_provider(s: Dict[str, Any]) -> bool:
                prov = s.get("providerName")
                if not prov:
                    return False
                prov_lower = prov.lower().strip()
                # Bidirectional substring: query in stored OR stored in query
                if q_name in prov_lower or prov_lower in q_name:
                    return True
                # Token overlap: all query tokens found in stored name or vice versa
                prov_tokens = set(prov_lower.split())
                if q_tokens and prov_tokens:
                    if q_tokens.issubset(prov_tokens) or prov_tokens.issubset(q_tokens):
                        return True
                # Fuzzy match: handles misspellings (e.g., "Roberta" vs "Roberto")
                # Check per-token fuzzy match — each query token must fuzzy-match
                # at least one stored token (ratio >= 0.8)
                if q_tokens and prov_tokens:
                    all_match = all(
                        any(
                            SequenceMatcher(None, qt, pt).ratio() >= 0.8
                            for pt in prov_tokens
                        )
                        for qt in q_tokens
                    )
                    if all_match:
                        return True
                return False

            name_matched = [s for s in filtered if matches_provider(s)]

            if name_matched:
                filtered = name_matched
            else:
                # Provider name matched nothing — try as specialty fallback
                # (LLM sometimes puts "cardiologist" in provider_name instead of specialty)
                q_stem = q_name[:6] if len(q_name) >= 6 else q_name
                spec_fallback = [
                    s for s in filtered
                    if s.get("providerSpecialty")
                    and (
                        q_name in s["providerSpecialty"].lower()
                        or s["providerSpecialty"].lower() in q_name
                        or (q_stem and q_stem in s["providerSpecialty"].lower())
                    )
                ]
                if spec_fallback:
                    filtered = spec_fallback
                else:
                    filtered = name_matched  # empty — will hit no-data path

        # --- NPI ---
        if query.npi:
            filtered = [
                s for s in filtered
                if s.get("npi") == query.npi
            ]

        # --- Specialty (fuzzy, bidirectional + stem matching) ---
        if query.specialty:
            q_spec = query.specialty.lower().strip()

            def matches_specialty(s: Dict[str, Any]) -> bool:
                spec = s.get("providerSpecialty")
                if not spec:
                    return False
                spec_lower = spec.lower()
                # Bidirectional substring
                if q_spec in spec_lower or spec_lower in q_spec:
                    return True
                # Token overlap for multi-word specialties
                q_tokens = set(q_spec.split())
                spec_tokens = set(spec_lower.replace("(", "").replace(")", "").split())
                if q_tokens & spec_tokens:
                    return True
                # Stem matching: "cardiologist" → "cardio" matches "cardiology"
                q_stem = q_spec[:6] if len(q_spec) >= 6 else q_spec
                if q_stem and q_stem in spec_lower:
                    return True
                return False

            filtered = [s for s in filtered if matches_specialty(s)]

        # --- Purpose ---
        if query.purpose:
            q_purpose = query.purpose.lower()
            filtered = [
                s for s in filtered
                if s.get("appointmentPurpose") and q_purpose in s["appointmentPurpose"].lower()
            ]

        # --- Keywords (match any keyword across all text content) ---
        if query.keywords:
            def matches_keywords(s: Dict[str, Any]) -> bool:
                searchable = " ".join([
                    s.get("summaryText") or "",
                    json.dumps(s.get("medications") or []),
                    json.dumps(s.get("keyPoints") or []),
                    json.dumps(s.get("diagnoses") or []),
                    json.dumps(s.get("instructions") or []),
                    json.dumps(s.get("recommendations") or []),
                    s.get("appointmentPurpose") or "",
                ]).lower()
                return any(kw.lower() in searchable for kw in query.keywords)
            filtered = [s for s in filtered if matches_keywords(s)]

        # --- Date filters ---
        today = date.today()
        today_iso = today.isoformat()

        if query.timeframe == VisitTimeframe.SPECIFIC_DATE and query.start_date:
            filtered = [
                s for s in filtered
                if s.get("appointmentDate") == query.start_date.isoformat()
            ]
        elif query.timeframe == VisitTimeframe.DATE_RANGE and query.start_date:
            end_date = query.end_date.isoformat() if query.end_date else today_iso
            filtered = [
                s for s in filtered
                if s.get("appointmentDate")
                and query.start_date.isoformat() <= s["appointmentDate"] <= end_date
            ]
        elif query.timeframe == VisitTimeframe.LAST_MONTH:
            cutoff = (today - timedelta(days=30)).isoformat()
            filtered = [s for s in filtered if (s.get("appointmentDate") or "") >= cutoff]
        elif query.timeframe == VisitTimeframe.LAST_3_MONTHS:
            cutoff = (today - timedelta(days=90)).isoformat()
            filtered = [s for s in filtered if (s.get("appointmentDate") or "") >= cutoff]
        elif query.timeframe == VisitTimeframe.LAST_6_MONTHS:
            cutoff = (today - timedelta(days=180)).isoformat()
            filtered = [s for s in filtered if (s.get("appointmentDate") or "") >= cutoff]
        elif query.timeframe == VisitTimeframe.LAST_YEAR:
            cutoff = (today - timedelta(days=365)).isoformat()
            filtered = [s for s in filtered if (s.get("appointmentDate") or "") >= cutoff]
        else:
            # Default: only past appointments
            filtered = [
                s for s in filtered
                if (s.get("appointmentDate") or "") <= today_iso
            ]

        # Sort
        if query.sort_by == "date":
            filtered.sort(
                key=lambda x: x.get("appointmentDate") or "",
                reverse=(query.sort_order == "desc"),
            )
        elif query.sort_by == "provider":
            filtered.sort(
                key=lambda x: x.get("providerName") or "",
                reverse=(query.sort_order == "desc"),
            )

        # Apply user-specified limit
        if query.limit and len(filtered) > query.limit:
            filtered = filtered[: query.limit]

        # Hard cap: keep most recent N summaries if still too many
        if len(filtered) > MAX_SUMMARIES_FOR_LLM:
            filtered.sort(key=lambda x: x.get("appointmentDate") or "", reverse=True)
            filtered = filtered[:MAX_SUMMARIES_FOR_LLM]

        return filtered

    # ------------------------------------------------------------------ #
    #  Conversation context                                               #
    # ------------------------------------------------------------------ #

    def _write_conversation_context(
        self,
        conversation_id: str,
        matched_summaries: List[Dict[str, Any]],
    ) -> None:
        """Persist lightweight context for follow-up resolution."""
        ctx: Dict[str, Any] = {"lastIntent": "past_visits", "turnCount": 1}
        if matched_summaries:
            first = matched_summaries[0]
            ctx["lastProvider"] = first.get("providerName")
            ctx["lastAppointmentDate"] = first.get("appointmentDate")
            ctx["lastMatchedSummaryIds"] = [s["id"] for s in matched_summaries[:MAX_SUMMARIES_FOR_LLM]]

        # Merge with existing context to increment turnCount
        try:
            existing_raw = redis_client.get(
                chatbot_conversation_context_key(conversation_id)
            )
            if existing_raw:
                existing = json.loads(existing_raw)
                ctx["turnCount"] = existing.get("turnCount", 0) + 1
        except Exception:
            pass

        redis_client.set(
            chatbot_conversation_context_key(conversation_id),
            json.dumps(ctx),
            expiry=60 * 60 * 24,  # 24h
        )

    # ------------------------------------------------------------------ #
    #  Main handler                                                       #
    # ------------------------------------------------------------------ #

    def _resolve_followup_summaries(
        self,
        conversation_context: Dict[str, Any],
        enriched_summaries: List[Dict[str, Any]],
    ) -> Optional[List[Dict[str, Any]]]:
        """Retrieve previously matched summaries for follow-up questions.
        Returns None if no context or IDs don't match."""
        last_ids = conversation_context.get("lastMatchedSummaryIds", [])
        if not last_ids:
            return None
        last_id_set = set(last_ids)
        matched = [s for s in enriched_summaries if s.get("id") in last_id_set]
        return matched if matched else None

    @traceable(name="handle_intent")
    async def handle_intent(self, **kwargs) -> IntentResponse[None]:
        text = kwargs["text"]
        context = kwargs["context"]
        conversation_id = kwargs.get("conversation_id", "")

        user_profile = context.get("user_profile", {})
        chat_history = context.get("conversation_messages", [])
        enriched_summaries = context.get("enriched_summaries", [])
        conversation_context = context.get("conversation_context", {})

        if not enriched_summaries:
            return await self.no_data_found_chain.handle_intent(
                text=text, context=context,
                intent="past_visits", search_details="past appointments"
            )

        try:
            is_followup = self._is_followup(text, conversation_context)

            # --- Follow-up fast path ---
            # Reuse previously matched summaries — the conversation history
            # already gives the response LLM full context for the follow-up.
            if is_followup:
                matched = self._resolve_followup_summaries(
                    conversation_context, enriched_summaries
                )
                if matched:
                    print(f"Follow-up: reusing {len(matched)} summaries from previous turn")

                    ai_content = await self.response_content_chain.ainvoke(
                        {
                            "text": text,
                            "conversation_history": json.dumps(chat_history, default=str),
                            "matched_summaries": json.dumps(matched, default=str),
                            "today_date": date.today().isoformat(),
                        },
                        config={"callbacks": get_callbacks()},
                    )

                    # Keep the same context for further follow-ups
                    self._write_conversation_context(conversation_id, matched)

                    return IntentResponse[None](
                        intent="past_visits",
                        responses=[IntentAiResponse(type="text", content=ai_content, data=None)],
                    )

            # --- Stage 1: Extract query params (new questions only) ---
            condensed = self._condense_summaries(enriched_summaries)
            print(f"Extracting query parameters for query: {text}")
            query_params = self.query_chain.invoke(
                {
                    "text": text,
                    "user_profile": json.dumps(user_profile, default=str),
                    "enriched_summaries": json.dumps(condensed, default=str),
                    "conversation_history": json.dumps(chat_history, default=str),
                    "conversation_context": json.dumps(conversation_context, default=str),
                    "query_format": self.query_parser.get_format_instructions(),
                },
                config={"callbacks": get_callbacks()},
            )
            print(f"Extracted query parameters: {query_params}")

            # --- Stage 1b: Filter enriched summaries ---
            matched = self.filter_summaries(query_params, enriched_summaries)
            print(f"Found {len(matched)} matched summaries")

            if not matched:
                search_details = self._create_search_details(query_params)
                return await self.no_data_found_chain.handle_intent(
                    text=text, context=context,
                    intent="past_visits", search_details=search_details
                )

            # --- Stage 2: Generate response ---
            ai_content = await self.response_content_chain.ainvoke(
                {
                    "text": text,
                    "conversation_history": json.dumps(chat_history, default=str),
                    "matched_summaries": json.dumps(matched, default=str),
                    "today_date": date.today().isoformat(),
                },
                config={"callbacks": get_callbacks()},
            )

            # Write conversation context for follow-ups
            self._write_conversation_context(conversation_id, matched)

            return IntentResponse[None](
                intent="past_visits",
                responses=[IntentAiResponse(type="text", content=ai_content, data=None)],
            )

        except Exception as e:
            print(f"Error processing past visit query: {str(e)}")
            import traceback
            traceback.print_exc()
            return IntentResponse[None](
                intent="past_visits",
                responses=[IntentAiResponse(
                    type="text",
                    content=f"I apologize, but I encountered an issue processing your request about past visits. {NO_PAST_VISIT_INFORMATION_AVAILABLE}",
                    data=None,
                )],
            )

    def _create_search_details(self, query_params: PastVisitQuery) -> str:
        details = []
        if query_params.provider_name:
            details.append(f"past visits with {query_params.provider_name}")
        if query_params.specialty:
            details.append(f"visits with a {query_params.specialty} specialist")
        if query_params.keywords:
            details.append(f"visits related to {', '.join(query_params.keywords)}")
        if query_params.purpose:
            details.append(f"past visits for {query_params.purpose}")
        if query_params.start_date:
            if query_params.timeframe == "specific_date":
                details.append(f"past visits on {query_params.start_date}")
            elif query_params.end_date:
                details.append(f"past visits between {query_params.start_date} and {query_params.end_date}")
            else:
                details.append(f"past visits from {query_params.start_date}")
        return " ".join(details) if details else "past visits matching your criteria"

    @property
    def model(self):
        if self._model is None:
            self._model = get_default_chat_model()
        return self._model

    @property
    def query_chain(self):
        if self._query_chain is None:
            self._query_chain = self.query_prompt | self.model | self.query_parser
        return self._query_chain

    @property
    def response_content_chain(self):
        if self._response_content_chain is None:
            self._response_content_chain = self.response_prompt | self.model | StrOutputParser()
        return self._response_content_chain
