"""PydanticAI batch-shaped chain for extracting structured, patient-facing procedure
summaries from procedure documents (cardiac catheterization, TEE, operative/surgery
reports, etc.).

Batch-shaped like `document_type_inference` (list in, list out, one call) rather than
`attachment_summarization`'s map-reduce+synthesis shape: each procedure document
describes its OWN distinct event and must NOT be merged/deduplicated across documents
the way attachment_summarization merges general visit notes.
"""

import asyncio
import logging
from typing import List

from pydantic_ai import Agent

from src.app.common.llm_factory import get_pydantic_ai_model
from src.app.models.attachment_summarization import DocumentAttachment
from src.app.models.procedure_summarization import (
    NOT_DOCUMENTED_FOLLOW_UP,
    ProcedureSummary,
)

logger = logging.getLogger(__name__)

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
- what_was_performed: plain-language, patient-facing explanation of WHAT was actually done — the key
  steps and findings, translated from clinical jargon into language a patient can understand.
- outcome: plain-language, patient-facing explanation of the RESULT (success/complications, key
  findings, impression/conclusions).
- follow_up: plain-language, patient-facing follow-up instructions or next steps, taken ONLY from an
  explicit recommendation/follow-up/disposition/discharge-instructions section of the SAME document.

CRITICAL RULES (non-negotiable):
1. NEVER fabricate, infer, or guess clinical facts, names, dates, or outcomes that are not explicitly
   stated in the source text.
2. follow_up is the most safety-critical field: if — and only if — the source document has NO
   explicit follow-up/recommendation/disposition/next-steps section, you MUST set follow_up to
   EXACTLY this literal string, verbatim, with no changes: {NOT_DOCUMENTED_FOLLOW_UP!r}
   Do NOT infer follow-up from what "would normally" happen after such a procedure. Do NOT leave it
   blank or write something like "none mentioned" — use the exact sentinel string above.
3. Use second person ("you"/"your") in reason, what_was_performed, outcome, and follow_up (when real
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

    content = doc.extracted_text[:20_000]
    if len(doc.extracted_text) > 20_000:
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
            self._model = get_pydantic_ai_model()
        return self._model

    @property
    def agent(self) -> Agent:
        if self._agent is None:
            self._agent = Agent(
                self.model,
                output_type=ProcedureSummary,
                system_prompt=_SYSTEM_PROMPT,
            )
        return self._agent

    async def _extract_one(self, doc: DocumentAttachment) -> ProcedureSummary:
        prompt = _format_document_prompt(doc)
        result = await self.agent.run(prompt)
        return result.output

    async def extract(self, documents: List[DocumentAttachment]) -> List[ProcedureSummary]:
        """Extract a structured procedure summary for each document, concurrently. A failed
        individual document is logged and dropped rather than failing the whole batch."""
        if not documents:
            return []

        results = await asyncio.gather(
            *(self._extract_one(doc) for doc in documents), return_exceptions=True
        )

        summaries: List[ProcedureSummary] = []
        for doc, result in zip(documents, results):
            if isinstance(result, Exception):
                logger.error(
                    f"Procedure extraction failed for document '{doc.title}': {result}", exc_info=result
                )
                continue
            summaries.append(result)
        return summaries
