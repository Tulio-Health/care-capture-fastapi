"""PydanticAI map-reduce chain for analyzing medical document attachments."""

import asyncio
import json
import logging
from typing import List

from langsmith import traceable
from pydantic_ai import Agent

from src.app.common.llm_factory import get_pydantic_ai_model
from src.app.models.attachment_summarization import (
    AttachmentSummarizationResponse,
    DocumentAttachment,
    DocumentSummary,
)

logger = logging.getLogger(__name__)

BATCH_CHAR_LIMIT = 30_000  # ~7,500-10,000 tokens of content per batch

_EXTRACTION_SYSTEM_PROMPT = """You are a clinical AI assistant that extracts structured data from medical documents.

For each document provided in the batch, return one DocumentSummary object in the output list (same order as documents).

Document Type Inference:
- Infer the document type dynamically from the content (e.g., "Lab Report", "Progress Note", "Radiology Report", "Discharge Summary", "Consultation Note", "Operative Report", "Prescription")
- Do NOT assume a fixed set of document types

Extraction Guidelines:
- Extract all mentioned diagnoses, conditions, and clinical findings
- List all medications with dosages and instructions
- Identify laboratory test results with values and reference ranges
- Extract vital signs and physical examination findings
- Identify procedures performed or recommended
- Note any recommendations, follow-up instructions, or care plans
- Highlight critical, abnormal, or concerning findings
- Identify risk factors
- Write a 2-4 sentence narrative_summary capturing clinical context not covered by structured fields

Patient-Perspective Language:
- Normalize medical abbreviations (e.g., "HTN" → "high blood pressure", "DM2" → "Type 2 Diabetes")
- Preserve exact numerical values and units for lab results
- Include reference ranges when provided

Diagnosis Identification:
- Look for diagnoses in: Diagnosis, Visit Diagnosis, Assessment, Impression, Problems, Problem List,
  Active Problems, Ongoing Problems, Discharge Diagnosis, Reason for Visit, Past Medical History (if active)
-Past Medical History may contain chronic conditions. Extract them only if they are clearly active or referenced as relevant to the current visit.
-Reason for Visit often contains symptoms rather than confirmed diagnoses. Extract items from this section only if they represent a medical condition.
-If ICD-10 codes appear (e.g., M25.512), remove the code and keep the diagnosis description.
-Convert medical terminology into patient-friendly language while preserving the clinical meaning.
-If multiple diagnoses refer to the same anatomical region and underlying condition, combine them into a single primary diagnosis and optionally list symptoms separately


GUARDRAILS - Don't Do:
- Add any new facts, values, or events not explicitly present in the document
- Infer missing clinical logic, intent, causality, or conclusions
- Interpret or explain the clinical meaning or significance of findings
- Predict outcomes, risks, disease progression, or treatment effectiveness
- Recommend actions beyond what's stated in the document

GUARDRAILS - Do:
- Extract only what is explicitly stated in the document
- Preserve original statuses, codes, and recorded values
- Return one DocumentSummary per document in the batch, in order """

_SYNTHESIS_SYSTEM_PROMPT = """You are a clinical AI assistant that synthesizes multiple per-document clinical extractions into a unified patient-facing summary.

Synthesis Guidelines:
- Merge and deduplicate information across all document summaries
- Organize findings chronologically by source_document_date
- Preserve conflicting values as-is without reconciliation
- Present information in second person ("you", "your") for patient-facing output
- Normalize terminology into patient-friendly language while preserving clinical intent

clinical_summary field:
- Begin with a brief sentence referencing the appointment date, purpose, and provider
- Then synthesize to answer: Why did you go to the doctor? What did the doctor find? What did they do? What is your diagnosis? What should you do next?

key_insights field:
- Include key findings, trends, and notable observations
- Fold in procedures and vital_signs from per-document summaries as relevant insights

diagnoses_mentioned: Deduplicated list of all diagnoses/conditions across all documents
medications_mentioned: Deduplicated list of all medications with dosages
lab_results: Deduplicated list of all lab values with units and reference ranges
recommendations: Deduplicated list of all recommendations and follow-up instructions
risk_factors: Deduplicated list of all risk factors identified
document_metadata: Build from source_document_title, source_document_date, source_document_type in each DocumentSummary

GUARDRAILS - Don't Do:
- Add any new facts not present in the document summaries
- Reconcile, normalize, prioritize, or resolve conflicting values
- Act as clinical decision support in any form
- Merge data inappropriately across different encounters or time periods

GUARDRAILS - Do:
- De-duplicate identical entries
- Address the patient directly using "you" and "your" throughout
- Maintain original statuses, codes, and recorded values
- Present conflicting values as-is"""


def _create_batches(
    documents: List[DocumentAttachment],
) -> List[List[DocumentAttachment]]:
    """Group documents into batches that fit within the token budget."""
    batches = []
    current_batch: List[DocumentAttachment] = []
    current_size = 0

    for doc in documents:
        if doc.extraction_error:
            continue
        doc_size = min(len(doc.extracted_text), 10_000)
        if current_batch and current_size + doc_size > BATCH_CHAR_LIMIT:
            batches.append(current_batch)
            current_batch = []
            current_size = 0
        current_batch.append(doc)
        current_size += doc_size

    if current_batch:
        batches.append(current_batch)

    return batches


def _format_batch_prompt(
    batch: List[DocumentAttachment], batch_num: int, total_batches: int
) -> str:
    """Format a batch of documents into a user prompt for the extraction agent."""
    parts = [
        f"Batch {batch_num} of {total_batches}. Extract structured clinical data from each document below.\n"
    ]

    for idx, doc in enumerate(batch, 1):
        header = f"\n--- DOCUMENT {idx} ---\n"
        header += f"Title: {doc.title or 'Unknown'}\n"
        if doc.date:
            header += f"Date: {doc.date.strftime('%Y-%m-%d')}\n"
        header += f"Content-Type: {doc.content_type}\n"
        if doc.file_name:
            header += f"Filename: {doc.file_name}\n"
        header += "---\n\n"

        content = doc.extracted_text[:10_000]
        if len(doc.extracted_text) > 10_000:
            content += f"\n\n[... truncated, total: {len(doc.extracted_text)} chars]"

        parts.append(header + content)

    return "\n".join(parts)


class AttachmentSummarizationChain:
    """Map-reduce chain for analyzing medical document attachments using PydanticAI."""

    def __init__(
        self,
        extraction_system_prompt: str | None = None,
        synthesis_system_prompt: str | None = None,
    ):
        self._model = None
        self._extraction_agent = None
        self._synthesis_agent = None
        self._extraction_system_prompt = (
            extraction_system_prompt or _EXTRACTION_SYSTEM_PROMPT
        )
        self._synthesis_system_prompt = (
            synthesis_system_prompt or _SYNTHESIS_SYSTEM_PROMPT
        )

    @property
    def model(self):
        if self._model is None:
            self._model = get_pydantic_ai_model()
        return self._model

    @property
    def extraction_agent(self) -> Agent:
        if self._extraction_agent is None:
            self._extraction_agent = Agent(
                self.model,
                output_type=list[DocumentSummary],
                system_prompt=self._extraction_system_prompt,
            )
        return self._extraction_agent

    @property
    def synthesis_agent(self) -> Agent:
        if self._synthesis_agent is None:
            self._synthesis_agent = Agent(
                self.model,
                output_type=AttachmentSummarizationResponse,
                system_prompt=self._synthesis_system_prompt,
            )
        return self._synthesis_agent

    @traceable(name="extract_batch")
    async def _extract_batch(
        self, batch: List[DocumentAttachment], batch_num: int, total_batches: int
    ) -> List[DocumentSummary]:
        """Run extraction agent on a single batch of documents."""
        prompt = _format_batch_prompt(batch, batch_num, total_batches)
        result = await self.extraction_agent.run(prompt)
        return result.output

    @traceable(name="synthesize_summaries")
    async def _synthesize(
        self, appointment_context: dict, all_summaries: List[DocumentSummary]
    ) -> AttachmentSummarizationResponse:
        """Run synthesis agent to produce the final response."""
        summaries_json = json.dumps(
            [s.model_dump() for s in all_summaries],
            indent=2,
            default=str,
        )
        prompt = (
            f"Appointment Context:\n"
            f"- Date: {appointment_context.get('appointment_date', 'N/A')}\n"
            f"- Purpose: {appointment_context.get('purpose', 'N/A')}\n"
            f"- Provider: {appointment_context.get('provider_name', 'N/A')}\n\n"
            f"Per-Document Summaries (JSON):\n{summaries_json}\n\n"
            f"Synthesize these {len(all_summaries)} document summaries into a unified AttachmentSummarizationResponse. "
            f"Set documents_analyzed to {len(all_summaries)}."
        )
        result = await self.synthesis_agent.run(prompt)
        response = result.output
        # Ensure accuracy — override with ground truth count
        response.documents_analyzed = len(all_summaries)
        return response

    @traceable(name="analyze_attachments")
    async def analyze(
        self,
        appointment_context: dict,
        documents: List[DocumentAttachment],
    ) -> AttachmentSummarizationResponse:
        """
        Analyze medical document attachments using a map-reduce pipeline.

        Map phase: Extract structured data from each batch of documents in parallel.
        Reduce phase: Synthesize all extractions into the final response.

        Args:
            appointment_context: Dict with appointment_date, purpose, provider_name
            documents: List of DocumentAttachment objects (with extracted text)

        Returns:
            AttachmentSummarizationResponse with structured clinical analysis
        """
        batches = _create_batches(documents)
        if not batches:
            raise ValueError(
                "No valid documents to analyze after filtering extraction errors."
            )

        logger.info(
            f"Map phase: {len(batches)} batch(es) from {len(documents)} document(s)"
        )

        # Map phase: extract from each batch in parallel
        tasks = [
            self._extract_batch(batch, i + 1, len(batches))
            for i, batch in enumerate(batches)
        ]
        batch_results = await asyncio.gather(*tasks, return_exceptions=True)

        # Collect successful extractions
        all_summaries: List[DocumentSummary] = []
        for i, result in enumerate(batch_results):
            if isinstance(result, Exception):
                logger.error(
                    f"Batch {i + 1} extraction failed: {result}", exc_info=result
                )
            else:
                all_summaries.extend(result)

        if not all_summaries:
            raise Exception("All extraction batches failed — cannot synthesize.")

        logger.info(
            f"Reduce phase: synthesizing {len(all_summaries)} document summary(ies)"
        )

        return await self._synthesize(appointment_context, all_summaries)
