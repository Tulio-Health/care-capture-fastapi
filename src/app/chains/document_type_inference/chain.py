"""PydanticAI batch-shaped chain for inferring FHIR DocumentReference document types.

Copies the "one call in, list out" `output_type=list[...]` Agent construction pattern
already shipped in `attachment_summarization/chain.py` (see
`AttachmentSummarizationChain.extraction_agent`) — NOT that file's `_format_batch_prompt`
human-readable prompt-formatting helper, since this chain's input is compact structured
JSON (minimal CodeableConcept-derived fields), not long-form document prose.
"""

import json
import logging
from typing import List

from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings

from src.app.common.llm_factory import get_pydantic_ai_model
from src.app.models.document_type_inference import (
    DocumentTypeInferenceRequest,
    DocumentTypeInferenceResponse,
)

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You classify a FHIR DocumentReference's clinical document type from minimal metadata only. You never see the document content.

INPUT (JSON): a JSON array of one or more objects, each carrying an id plus: type_code, type_system, category_text, category_codes, content_title, content_type, raw_display (the original, sometimes-unhelpful type.coding[0].display, e.g. "unknown").

OUTPUT: a JSON array with exactly one output object per input object, each preserving its corresponding input's id field unchanged so it can be correlated back to its request — regardless of what order you return them in. Each output object has exactly these 4 fields:
- id: the SAME id from the corresponding input object, unchanged.
- normalized_type: a short, human-readable label a healthcare admin would recognize. Prefer one of: Progress Note, Consult Note, Discharge Summary, History and Physical, Operative Note, Procedure Note, Lab Report, Imaging Report, Pathology Report, Referral Note, Summary of Care, Patient Education, Consent Form, Insurance Card, Patient ID Card, Billing Statement, Other. Use content_title and raw_display as primary signal. Use type_code (LOINC) as secondary signal when recognized (e.g. 11506-3=Progress note, 18842-5=Discharge summary, 34133-9=Summary of episode note, 11488-4=Consult note, 28570-0=Procedure note). If type_code is NullFlavor "UNK" and raw_display is uninformative ("unknown"/"other"/empty), rely entirely on content_title/content_type. If truly indeterminate, return "Other".
- include_for_summary: true only if this is a clinically substantive document (visit/progress/consult/discharge notes, lab/imaging/pathology/operative reports, referral or summary-of-care notes). false for administrative/non-clinical documents (insurance or ID cards, consent/registration forms, billing, patient-education handouts, scanned card photos). When unclear, prefer false.
- confidence: your confidence in normalized_type, 0.0-1.0.

EXAMPLES (each shown as a single input/output pair; a real request typically contains one or more of these in a single JSON array):
Input: {"id":"doc-1","type_code":"UNK","type_system":"http://terminology.hl7.org/CodeSystem/v3-NullFlavor","category_text":null,"category_codes":["clinical-note"],"content_title":"Insurance Card - Front","content_type":"image/jpeg","raw_display":"unknown"}
Output: {"id":"doc-1","normalized_type":"Insurance Card","include_for_summary":false,"confidence":0.95}

Input: {"id":"doc-2","type_code":"11506-3","type_system":"http://loinc.org","category_text":"Clinical Note","category_codes":["clinical-note"],"content_title":"Progress Notes 03/14/2026","content_type":"application/pdf","raw_display":"Progress note"}
Output: {"id":"doc-2","normalized_type":"Progress Note","include_for_summary":true,"confidence":0.98}

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
        """Classify a batch of minimal DocumentReference metadata items in a single LLM call."""
        payload_json = json.dumps([item.model_dump(exclude_none=True) for item in items])
        result = await self.agent.run(payload_json)
        return result.output
