"""PydanticAI batch-shaped chain for extracting structured, patient-facing procedure
summaries from procedure documents (cardiac catheterization, TEE, operative/surgery
reports, etc.).

Batch-shaped like `document_type_inference` (list in, list out, one call) rather than
`attachment_summarization`'s map-reduce+synthesis shape: each procedure document
describes its OWN distinct event and must NOT be merged/deduplicated across documents
the way attachment_summarization merges general visit notes.
"""

import asyncio
import difflib
import logging
import re
from typing import List, Tuple

from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.settings import ModelSettings

from src.app.common.constants.llm import LLM_MODEL
from src.app.common.llm_factory import get_pydantic_ai_model
from src.app.models.attachment_summarization import DocumentAttachment
from src.app.models.procedure_summarization import (
    NOT_DOCUMENTED_FOLLOW_UP,
    ProcedureSummary,
)

logger = logging.getLogger(__name__)

_FOLLOWUP_SECTION_PATTERN = re.compile(
    r"\b(recommendation|follow[\s-]?up|disposition|discharge instruction|plan)\b",
    re.IGNORECASE,
)

# Was 20_000 (an unexamined leftover doubled from attachment_summarization's per-doc cap,
# which was sized for a smaller-context model). gpt-4.1-mini has a ~1M token context window;
# 100k chars ~= 25k tokens gives 5x headroom over any realistic procedure report while keeping
# cost and spurious-retry exposure bounded. Deliberately NOT 200k: at that length, common
# section-header keywords (recommendation/follow-up/plan/etc.) appear in almost every document
# somewhere, making the anti-omission validator (see _validate_follow_up_grounding) fire a
# near-guaranteed extra round-trip on most long documents, for ~10x the cost per document with
# no diagnosed benefit.
_MAX_DOC_CHARS = 100_000

# Process-wide cap on concurrent LLM calls from this chain. ProcedureExtractionChain is
# instantiated fresh per HTTP request, so this MUST be a module-level semaphore (not an
# instance attribute) to actually bound cross-request concurrency rather than giving every
# request its own private budget. 8 is a conservative default (this org's actual OpenAI TPM
# tier isn't known from this repo) and is per-process: with N uvicorn workers, the effective
# cross-process cap is 8 x N.
_LLM_SEMAPHORE = asyncio.Semaphore(8)


def _normalize(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def _quote_supported(quote: str, source: str, threshold: float = 0.85) -> bool:
    """Fuzzy-checks that `quote` is (close to) a verbatim substring of `source`, tolerating
    whitespace/case differences and minor transcription noise from the model."""
    q, src = _normalize(quote), _normalize(source)
    if not q:
        return False
    if q in src:
        return True
    matcher = difflib.SequenceMatcher(None, q, src)
    match = matcher.find_longest_match(0, len(q), 0, len(src))
    return match.size / max(len(q), 1) >= threshold


_SYSTEM_PROMPT = f"""You are an AI Clinical Summarizer (Non-Advisory) that turns procedure documents
(cardiac catheterization reports, transesophageal echocardiogram/TEE reports, operative/surgery
notes, endoscopy reports, biopsy reports, etc.) into a clear, accurate, patient-facing explanation
of what happened and what the patient should know next.

INPUT: one or more procedure documents, each with a title, date, and extracted text.

OUTPUT: exactly one ProcedureSummary object for THE document below.
It has these fields:
- source_document_title: the document's title, as given.
- procedure_type: a short, specific description of the procedure performed (e.g. "Cardiac
  catheterization with coronary angioplasty and stent placement", "Transesophageal echocardiogram
  (TEE)", "Aortic valve replacement (AVR) surgery"). Infer from the document content, not from a
  fixed list.
- procedure_date: ISO format (YYYY-MM-DD) if a procedure/result date is stated, else null.
- performed_by: one entry per person who actually PERFORMED/OPERATED the procedure (e.g. the
  surgeon, the cath physician, the physician performing a TEE), as "Name, credentials (role)".
  Do NOT include referring, ordering, or primary-care physicians who did not themselves perform it.
- reason: plain-language, patient-facing ("you"/"your") explanation of WHY the procedure was done —
  based only on the documented indication/reason for study/pre-op diagnosis/history of present illness.
- procedure_details: plain-language, patient-facing explanation of WHAT was actually done — the key
  steps and findings, translated from clinical jargon into language a patient can understand.
- outcome: plain-language, patient-facing explanation of the RESULT (success/complications, key
  findings, impression/conclusions).
- follow_up: plain-language, patient-facing follow-up instructions or next steps, taken ONLY from an
  explicit recommendation/follow-up/disposition/discharge-instructions section of the SAME document.

CRITICAL RULES (non-negotiable):
1. NEVER fabricate, infer, or guess clinical facts, names, dates, or outcomes that are not explicitly
   stated in the source text.
2. follow_up is the most safety-critical field. Follow this two-step process:
   a. FIRST, locate and copy the exact sentence(s) from the source document's follow-up/
      recommendation/disposition/discharge-instructions section into follow_up_source_quote,
      copied character-for-character verbatim from the source.
      Follow-up content is STILL follow-up even when it's phrased as clinician-directed orders
      rather than text addressed directly to the patient — e.g. "Integrilin gtt x 6 hours",
      "TR band wean per protocol", "Monitor vitals q4h", "f/u with cardiology in 2 weeks" all
      COUNT as follow-up content. Do NOT skip a section just because it reads like a clinical
      order instead of a sentence addressed to "you" — that phrasing is fixed in step b below.
      If no such section exists anywhere in the document, follow_up_source_quote MUST be null.
   b. THEN, if you copied a quote in step (a), paraphrase it into follow_up in plain,
      patient-facing, second-person language (e.g. "TR band wean per protocol" becomes
      "You will have the compression band on your wrist gradually loosened according to the
      standard protocol"; "f/u with cardiology in 2 weeks" becomes "You were told to follow up
      with cardiology in 2 weeks").
      If follow_up_source_quote is null (no such section exists), follow_up MUST be set to
      EXACTLY this literal string, verbatim, with no changes: {NOT_DOCUMENTED_FOLLOW_UP!r}
   Do NOT infer follow-up from what "would normally" happen after such a procedure. Do NOT leave it
   blank or write something like "none mentioned" — use the exact sentinel string above.
   follow_up_source_quote is null if and only if follow_up is the exact sentinel string above.
3. Use second person ("you"/"your") in reason, procedure_details, outcome, and follow_up (when real
   content exists). Do not use imperative/command language — attribute instructions to the provider
   (e.g. "You were told to..." not "Take...").
4. Translate medical terminology into plain language while preserving clinical accuracy (e.g.
   "myocardial infarction" -> "heart attack", "aortic stenosis" -> "narrowing of the aortic valve").
5. Return exactly one ProcedureSummary for the document provided.
"""


def _format_document_prompt(doc: DocumentAttachment) -> str:
    """Format a single procedure document into a user prompt for the extraction agent.

    Deliberately ONE document per LLM call (not a multi-document batch like
    document_type_inference's compact-JSON batch): each ProcedureSummary carries several
    free-text fields, and a combined multi-document batch call risks the model truncating/
    dropping output items under its output-token budget. Per-document calls are run
    concurrently via `extract()` so this costs latency, not correctness.
    """
    header = f"Title: {doc.title or 'Unknown'}\n"
    if doc.date:
        header += f"Date: {doc.date.strftime('%Y-%m-%d')}\n"
    header += f"Content-Type: {doc.content_type}\n"
    header += "---\n\n"

    content = doc.extracted_text[:_MAX_DOC_CHARS]
    if len(doc.extracted_text) > _MAX_DOC_CHARS:
        content += f"\n\n[... truncated, total: {len(doc.extracted_text)} chars]"

    return header + content


class ProcedureExtractionChain:
    """PydanticAI chain: one call per procedure document (run concurrently across documents),
    each producing a single ProcedureSummary. See `_format_document_prompt` for why this is
    per-document rather than a single multi-document batch call."""

    def __init__(self):
        self._model = None
        self._agent = None

    @property
    def model(self):
        if self._model is None:
            self._model = get_pydantic_ai_model(LLM_MODEL.GPT_4_1_MINI)
        return self._model

    @property
    def agent(self) -> Agent[str, ProcedureSummary]:
        if self._agent is None:
            self._agent = Agent(
                self.model,
                output_type=ProcedureSummary,
                system_prompt=_SYSTEM_PROMPT,
                model_settings=ModelSettings(
                    temperature=0.0, timeout=30.0, max_tokens=1500
                ),
                retries=2,
                deps_type=str,
            )

            @self._agent.output_validator
            async def _validate_follow_up_grounding(
                ctx: RunContext[str], output: ProcedureSummary
            ) -> ProcedureSummary:
                """Enforces the quote-grounding contract from _SYSTEM_PROMPT rule 2: every real
                follow_up must be traceable to a verbatim quote from the source (anti-fabrication),
                and a sentinel follow_up is challenged once if the source looks like it has a
                follow-up section the model may have missed (anti-omission)."""
                source = ctx.deps

                if output.follow_up == NOT_DOCUMENTED_FOLLOW_UP:
                    match = _FOLLOWUP_SECTION_PATTERN.search(source)
                    if match and not output.follow_up_source_quote:
                        raise ModelRetry(
                            "The source document appears to contain a follow-up/recommendation/"
                            f"disposition section (matched keyword: {match.group(0)!r}). Re-check it "
                            "carefully — if it truly contains no follow-up instructions for the "
                            "patient, keep the sentinel, but if you find relevant content, extract "
                            "it into follow_up_source_quote and follow_up."
                        )
                    output.follow_up_source_quote = None
                    return output

                if not output.follow_up_source_quote or not _quote_supported(
                    output.follow_up_source_quote, source
                ):
                    raise ModelRetry(
                        "follow_up must be supported by follow_up_source_quote copied VERBATIM "
                        "from the document. Your quote was missing or not found in the source. "
                        "Either provide the exact quote, or set follow_up to exactly "
                        f"{NOT_DOCUMENTED_FOLLOW_UP!r} with a null quote."
                    )
                return output

        return self._agent

    async def _extract_one(self, doc: DocumentAttachment) -> ProcedureSummary:
        prompt = _format_document_prompt(doc)
        # deps must match exactly what the model was shown in `prompt` (both capped at
        # _MAX_DOC_CHARS) — the output_validator reads ctx.deps to check quote-grounding and
        # the anti-omission challenge, so a deps/prompt mismatch lets the validator demand
        # content the model was never shown, causing an unwinnable ModelRetry loop.
        async with _LLM_SEMAPHORE:
            result = await self.agent.run(
                prompt, deps=doc.extracted_text[:_MAX_DOC_CHARS]
            )
        return result.output

    async def extract(
        self, documents: List[DocumentAttachment]
    ) -> Tuple[List[ProcedureSummary], List[dict]]:
        """Extract a structured procedure summary for each document, concurrently.

        Returns (summaries, failures): a failed individual document is logged, dropped from
        `summaries`, and recorded in `failures` using the SAME {"file_path", "error"} shape
        already used by ProcedureSummarizationService for S3/extraction failures, so callers
        can merge both into one `extraction_errors` list instead of silently losing documents
        that downloaded fine but failed LLM validation.
        """
        if not documents:
            return [], []

        results = await asyncio.gather(
            *(self._extract_one(doc) for doc in documents), return_exceptions=True
        )

        summaries: List[ProcedureSummary] = []
        failures: List[dict] = []
        for doc, result in zip(documents, results):
            if isinstance(result, Exception):
                if isinstance(result, UnexpectedModelBehavior):
                    logger.error(
                        f"Procedure extraction failed for document '{doc.title}': model exhausted "
                        f"retries against the follow_up quote-grounding validator: {result}",
                        exc_info=result,
                    )
                else:
                    logger.error(
                        f"Procedure extraction failed for document '{doc.title}': {result}",
                        exc_info=result,
                    )
                failures.append({"file_path": doc.file_path, "error": str(result)})
                continue
            summaries.append(result)
        return summaries, failures
