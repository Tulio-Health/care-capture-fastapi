"""PydanticAI batch-shaped chain for inferring FHIR DocumentReference document types.

Copies the "one call in, list out" `output_type=list[...]` Agent construction pattern
already shipped in `attachment_summarization/chain.py` (see
`AttachmentSummarizationChain.extraction_agent`) — NOT that file's `_format_batch_prompt`
human-readable prompt-formatting helper, since this chain's input is compact structured
JSON (minimal CodeableConcept-derived fields), not long-form document prose.
"""

from src.app.services.summary_runtime import model_call
import json
import logging
import time
from typing import List

from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings

from src.app.common.llm_factory import get_pydantic_ai_model
from src.app.models.document_type_inference import (
    DocumentTypeInferenceRequest,
    DocumentTypeInferenceResponse,
)
from src.app.services.bounded_fanout import UNRESOLVED, fan_out

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You classify a FHIR DocumentReference's clinical document type from minimal metadata only. You never see the document content.

INPUT (JSON): a JSON array of one or more objects, each carrying an id plus: type_code, type_system, category_text, category_codes, content_title, content_type, raw_display (the original, sometimes-unhelpful type.coding[0].display, e.g. "unknown").

OUTPUT: a JSON array with exactly one output object per input object, each preserving its corresponding input's id field unchanged so it can be correlated back to its request — regardless of what order you return them in. Each output object has exactly these 5 fields:
- id: the SAME id from the corresponding input object, unchanged.
- normalized_type: a short, human-readable label a healthcare admin would recognize. Prefer one of: Progress Note, Consult Note, Discharge Summary, History and Physical, Operative Note, Procedure Note, Lab Report, Imaging Report, Pathology Report, Referral Note, Summary of Care, Patient Education, Consent Form, Insurance Card, Patient ID Card, Billing Statement, Other. Use content_title and raw_display as primary signal. Use type_code (LOINC) as secondary signal when recognized (e.g. 11506-3=Progress note, 18842-5=Discharge summary, 34133-9=Summary of episode note, 11488-4=Consult note, 28570-0=Procedure note). If type_code is NullFlavor "UNK" and raw_display is uninformative ("unknown"/"other"/empty), rely entirely on content_title/content_type. If truly indeterminate, return "Other".
- include_for_summary: true only if this is a clinically substantive document (visit/progress/consult/discharge notes, lab/imaging/pathology/operative reports, referral or summary-of-care notes). false for administrative/non-clinical documents (insurance or ID cards, consent/registration forms, billing, patient-education handouts, scanned card photos). When unclear, prefer false.
- is_procedure_document: true only when the document describes a SPECIFIC procedure/intervention performed ON the patient — a cardiac catheterization, transesophageal echocardiogram (TEE), endoscopy, biopsy, or an operative/surgery report. false for general visit/progress/consult notes, discharge summaries, labs, imaging reports that are not themselves a procedure record, and all administrative documents. When unclear, prefer false.
- confidence: your confidence in normalized_type, 0.0-1.0.

EXAMPLES (each shown as a single input/output pair; a real request typically contains one or more of these in a single JSON array):
Input: {"id":"doc-1","type_code":"UNK","type_system":"http://terminology.hl7.org/CodeSystem/v3-NullFlavor","category_text":null,"category_codes":["clinical-note"],"content_title":"Insurance Card - Front","content_type":"image/jpeg","raw_display":"unknown"}
Output: {"id":"doc-1","normalized_type":"Insurance Card","include_for_summary":false,"is_procedure_document":false,"confidence":0.95}

Input: {"id":"doc-2","type_code":"11506-3","type_system":"http://loinc.org","category_text":"Clinical Note","category_codes":["clinical-note"],"content_title":"Progress Notes 03/14/2026","content_type":"application/pdf","raw_display":"Progress note"}
Output: {"id":"doc-2","normalized_type":"Progress Note","include_for_summary":true,"is_procedure_document":false,"confidence":0.98}

Input: {"id":"doc-3","type_code":"28570-0","type_system":"http://loinc.org","category_text":"Clinical Note","category_codes":["clinical-note"],"content_title":"Cardiac Catheterization Report","content_type":"application/pdf","raw_display":"Card Cath"}
Output: {"id":"doc-3","normalized_type":"Procedure Note","include_for_summary":true,"is_procedure_document":true,"confidence":0.95}

Never fabricate clinical findings. You are naming a document type, not reading or summarizing its content. Return exactly one output object per input object, preserving each input's id on its corresponding output, in a JSON array."""


class DocumentTypeInferenceChain:
    """Batch-shaped PydanticAI chain: one call in (list of minimal metadata items), one call out
    (list of classifications). A single item is just a batch of 1 — deliberately no separate
    single-item method exists; callers always go through `infer_batch`."""

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
                output_type=list[DocumentTypeInferenceResponse],
                system_prompt=_SYSTEM_PROMPT,
                model_settings=ModelSettings(temperature=0.2, timeout=15.0, max_tokens=1200),
                retries=1,
            )
        return self._agent

    async def infer_batch(
        self, items: List[DocumentTypeInferenceRequest]
    ) -> List[DocumentTypeInferenceResponse]:
        """Classify a batch of minimal DocumentReference metadata items.

        Default: serial 5-item model calls. With DOCTYPE_INFERENCE_PARALLEL_ENABLED the items
        are classified by 1-item calls through a bounded fan-out (see `_infer_parallel`)."""
        from src.app.core import get_settings
        from src.app.services.document_extraction import DocumentProcessingError
        ids = [item.id for item in items]
        if len(ids) != len(set(ids)) or len(items) > 100:
            raise DocumentProcessingError("INVALID_CLASSIFICATION_BATCH")
        settings = get_settings()
        if settings.DOCTYPE_INFERENCE_PARALLEL_ENABLED:
            return await self._infer_parallel(
                items,
                concurrency=settings.DOCTYPE_INFERENCE_CONCURRENCY,
                deadline_s=settings.DOCTYPE_INFERENCE_DEADLINE_S,
            )
        responses = []
        for offset in range(0, len(items), 5):
            batch = items[offset:offset + 5]
            payload_json = json.dumps([item.model_dump(exclude_none=True) for item in batch])
            if len(payload_json) > 20_000:
                raise DocumentProcessingError("CLASSIFICATION_INPUT_LIMIT")
            result = await model_call(self.agent.run, payload_json)
            returned_ids = [item.id for item in result.output]
            if len(returned_ids) != len(set(returned_ids)) or set(returned_ids) != {item.id for item in batch}:
                raise DocumentProcessingError("CLASSIFICATION_ID_MISMATCH")
            responses.extend(result.output)
        return responses

    async def _infer_parallel(
        self,
        items: List[DocumentTypeInferenceRequest],
        *,
        concurrency: int,
        deadline_s: float,
    ) -> List[DocumentTypeInferenceResponse]:
        """1-item calls through `fan_out`; same prompt/payload shape as a 1-item serial batch.

        Per-item failure isolation: an item whose call raised (timeout/429/unavailable/id
        mismatch) or missed the deadline is OMITTED from the result (the route already omits ids
        infer_batch did not return, and the connector keeps that document's pre-AI values).
        Resolved results keep request order. If NO item resolved, the request fails with the
        first item's error code, exactly like today's whole-request failure."""
        from src.app.services.document_extraction import DocumentProcessingError
        if not items:
            return []
        payloads = [json.dumps([item.model_dump(exclude_none=True)]) for item in items]
        if any(len(payload) > 20_000 for payload in payloads):
            raise DocumentProcessingError("CLASSIFICATION_INPUT_LIMIT")
        failure_codes: dict = {}

        async def classify(index: int) -> DocumentTypeInferenceResponse:
            try:
                result = await model_call(self.agent.run, payloads[index])
                output = result.output
                if len(output) != 1 or output[0].id != items[index].id:
                    raise DocumentProcessingError("CLASSIFICATION_ID_MISMATCH")
                return output[0]
            except Exception as exc:
                failure_codes[index] = getattr(exc, "reason_code", None) or type(exc).__name__
                raise

        started = time.monotonic()
        results = await fan_out(
            list(range(len(items))), classify, concurrency=concurrency, deadline_s=deadline_s
        )
        resolved = [r for r in results if r is not UNRESOLVED]
        logger.info(
            "doctype_inference_fanout items=%d resolved=%d unresolved=%d concurrency=%d elapsed_ms=%d",
            len(items),
            len(resolved),
            len(items) - len(resolved),
            concurrency,
            int((time.monotonic() - started) * 1000),
        )
        if not resolved:
            first_failed = next(i for i, r in enumerate(results) if r is UNRESOLVED)
            # Items that missed the deadline never reached `except`; they have no recorded code.
            raise DocumentProcessingError(failure_codes.get(first_failed) or "MODEL_TIMEOUT")
        return resolved
