"""PydanticAI batch-shaped chain for extracting structured, patient-facing procedure
summaries from procedure documents (cardiac catheterization, TEE, operative/surgery
reports, etc.).

Batch-shaped like `document_type_inference` (list in, list out, one call) rather than
`attachment_summarization`'s map-reduce+synthesis shape: this chain still produces ONE
ProcedureSummary per source document, one LLM call each. It deliberately does NOT merge or
deduplicate across documents itself — that is `procedure_extraction.consolidation`'s job,
run as a separate step over this chain's output (see `ExtractedProcedure`/`extract()` below).
"""

from src.app.services.summary_runtime import model_call
import asyncio
import difflib
import logging
import re
from dataclasses import dataclass
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
    ProcedureDocumentExtraction,
)

from src.app.services.document_ingestion import require_parsed, mark_parsed
from src.app.services.document_extraction import DocumentProcessingError
from src.app.services.clinical_grounding import GROUNDING_POLICY, verify_grounding

logger = logging.getLogger(__name__)

# Bound each model input; larger parsed documents are fully covered by overlapping
# chunks. A failed chunk fails the document and cannot authorize deletion.
_MAX_DOC_CHARS = 48_000
_CHUNK_OVERLAP = 2_000
_MAX_CHUNKS = 32

@dataclass
class ExtractedProcedure:
    """Pairs one extracted ProcedureSummary with its source document's stable identifier.

    `document_id` is structural metadata (the source DocumentAttachment's `resource_id`,
    falling back to `file_path` if a resource_id was never set) attached AFTER `result.output`
    is obtained from the LLM — the model never sees or produces this field, avoiding a
    hallucination surface on an id the LLM has no reliable way to know.
    """

    document_id: str
    summary: ProcedureSummary


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

OUTPUT: a ProcedureDocumentExtraction envelope with zero or more distinct performed events.
An order or referral is not a performed event. For each performed event, provide a
unique event_source_quote copied verbatim from the document.
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
5. Include every distinct, explicitly performed event; return an empty procedures list when none is supported.
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

    content = doc.extracted_text

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
                output_type=ProcedureDocumentExtraction,
                system_prompt=_SYSTEM_PROMPT + "\n" + GROUNDING_POLICY + "\nReturn procedures: a list of ZERO OR MORE distinct performed events. Return an empty list for orders, referrals, recommendations, historical mentions without a described performed event, or no procedure. Do not force one result per document. Supply evidence_quotes for every returned event.",
                model_settings=ModelSettings(
                    temperature=0.0, timeout=30.0, max_tokens=4096
                ),
                retries=2,
                deps_type=str,
            )

            @self._agent.output_validator
            async def _validate_follow_up_grounding(ctx: RunContext[str], output: ProcedureDocumentExtraction):
                from src.app.services.clinical_grounding import validate_quotes
                if output.procedures:
                    validate_quotes(output.evidence_quotes, ctx.deps)
                ranges = []
                for procedure in output.procedures:
                    validate_quotes([procedure.event_source_quote], ctx.deps)
                    if ctx.deps.count(procedure.event_source_quote) != 1:
                        raise ModelRetry("Use a unique verbatim passage identifying this event, including its local context.")
                    start = ctx.deps.index(procedure.event_source_quote)
                    ranges.append((start, start + len(procedure.event_source_quote)))
                    if procedure.follow_up != NOT_DOCUMENTED_FOLLOW_UP:
                        validate_quotes([procedure.follow_up_source_quote], ctx.deps)
                    elif procedure.follow_up_source_quote:
                        raise ModelRetry("Do not attach a quote to an absent follow-up.")
                ranges.sort()
                if any(left[1] > right[0] for left, right in zip(ranges, ranges[1:])):
                    raise ModelRetry("Each distinct event needs its own non-overlapping evidence passage; do not duplicate an event.")
                return output

        return self._agent

    async def _extract_one(self, doc: DocumentAttachment) -> ProcedureDocumentExtraction:
        require_parsed(doc)
        if len(doc.extracted_text) > _MAX_DOC_CHARS:
            offsets = range(0, len(doc.extracted_text), _MAX_DOC_CHARS - _CHUNK_OVERLAP)
            if len(offsets) > _MAX_CHUNKS:
                raise DocumentProcessingError("PROCEDURE_CONTEXT_LIMIT_EXCEEDED")
            events = {}
            for offset in offsets:
                chunk = mark_parsed(doc.model_copy(update={
                    "extracted_text": doc.extracted_text[offset:offset + _MAX_DOC_CHARS]}))
                result = await self._extract_one(chunk)
                for event in result.procedures:
                    quote = event.event_source_quote
                    if doc.extracted_text.count(quote) != 1:
                        raise DocumentProcessingError("INVALID_SOURCE_EVIDENCE")
                    if quote in events and events[quote].model_dump() != event.model_dump():
                        raise DocumentProcessingError("CLINICAL_EVIDENCE_FAILED")
                    events[quote] = event
            ordered = sorted(events.values(), key=lambda event: doc.extracted_text.index(event.event_source_quote))
            return ProcedureDocumentExtraction(procedures=ordered,
                                               evidence_quotes=[event.event_source_quote for event in ordered])
        prompt = _format_document_prompt(doc)
        # deps must match exactly what the model was shown in `prompt` (both capped at
        # _MAX_DOC_CHARS) — the output_validator reads ctx.deps to check quote-grounding and
        # the anti-omission challenge, so a deps/prompt mismatch lets the validator demand
        # content the model was never shown, causing an unwinnable ModelRetry loop.
        result = await model_call(self.agent.run,
            prompt, deps=doc.extracted_text[:_MAX_DOC_CHARS]
        )
        await verify_grounding(self.model, doc.extracted_text, result.output, scope="performed_events")
        return result.output

    async def extract(
        self, documents: List[DocumentAttachment]
    ) -> Tuple[List[ExtractedProcedure], List[dict]]:
        """Extract a structured procedure summary for each document, concurrently.

        Returns (extracted, failures): a failed individual document is logged, dropped from
        `extracted`, and recorded in `failures` using the SAME {"file_path", "error"} shape
        already used by ProcedureSummarizationService for S3/extraction failures, so callers
        can merge both into one `extraction_errors` list instead of silently losing documents
        that downloaded fine but failed LLM validation. Each successful result is paired with
        its source document's stable id via `ExtractedProcedure` (see its docstring) so callers
        can consolidate/persist per-document rather than per-appointment.
        """
        if not documents:
            return [], []

        results = await asyncio.gather(
            *(self._extract_one(doc) for doc in documents), return_exceptions=True
        )

        extracted: List[ExtractedProcedure] = []
        failures: List[dict] = []
        for doc, result in zip(documents, results):
            if isinstance(result, Exception):
                logger.warning("Procedure extraction failed; error_type=%s", type(result).__name__)
                failures.append({"source_id": doc.resource_id or "unknown", "error": getattr(result, "code", "PROCEDURE_EXTRACTION_FAILED")})
                continue
            document_id = doc.resource_id or doc.file_path
            import hashlib
            import json
            ordered_events = sorted(result.procedures, key=lambda event: doc.extracted_text.find(event.event_source_quote))
            for ordinal, event in enumerate(ordered_events):
                identity = json.dumps([doc.content_sha256 or hashlib.sha256(doc.extracted_text.encode()).hexdigest(), ordinal], ensure_ascii=False)
                event_id = hashlib.sha256(identity.encode()).hexdigest()
                extracted.append(ExtractedProcedure(document_id=f"{document_id}:event:{event_id}", summary=event))
        return extracted, failures
