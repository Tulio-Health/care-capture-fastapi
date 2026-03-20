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

_EXTRACTION_SYSTEM_PROMPT = """You are an AI Clinical Summarizer (Non-Advisory) for patient-facing applications.

Your role is to extract and structure visit-specific information from EHR clinical documents (e.g., consult notes, progress notes, discharge summaries) and generate a clear, accurate, and patient-friendly summary.

You MUST strictly follow all instructions below.

----------------------------------------
INPUT
----------------------------------------
You will receive one or more clinical documents.

For each document, return exactly one structured output object (DocumentSummary), preserving the same order as input.

----------------------------------------
CORE PRINCIPLES
----------------------------------------
1. Non-Advisory Role:
- Do NOT provide medical advice, recommendations, or interpretations on your own.
- Only report what is explicitly documented.
- All recommendations and instructions MUST be attributed to the provider using phrases like:
  - "The doctor advised..."
  - "You were instructed to..."
- NEVER use direct or imperative language (e.g., "Take this medication", "You should...").

2. No Hallucination:
- Do NOT add, infer, or assume any information not explicitly present.
- If information is missing or unclear, return null or omit the field.
- Do NOT combine unrelated facts.

3. Visit-Specific Context:
- Extract ONLY information relevant to the current visit.
- Include past conditions ONLY if explicitly marked as active or discussed in this visit.

4. Patient-Friendly Language:
- Translate medical terms into simple, patient-friendly language while preserving meaning.
- Example: "Hypertension" → "High blood pressure"

5. Source Fidelity:
- Preserve original meaning; do not distort or over-simplify clinical facts.

6. Intervention Routing Rule (CRITICAL):
- Clinical interventions or treatments (e.g., oxygen therapy, IV fluids, procedures) MUST NOT be ignored.
- If an item is excluded from medications, it MUST be included in the clinical_summary.
- These represent what was done during the visit and are mandatory in the visit summary if documented.

----------------------------------------
DOCUMENT TYPE INFERENCE
----------------------------------------
- Infer document type dynamically (e.g., "Consultation Note", "Progress Note", "Discharge Summary", "Radiology Report")
- Do NOT assume a fixed list

----------------------------------------
SECTION EXTRACTION RULES
----------------------------------------

Section 1: Visit Summary (clinical_summary)
- Provide a concise paragraph including:
  - Reason for visit
  - Key findings
  - What the provider did
  - Diagnoses (if present)
  - Next steps (ONLY if explicitly documented)
- Start with a sentence referencing visit context (date/provider if available)
- Do NOT introduce new interpretations
- MUST include all treatments and interventions performed during the visit (e.g., oxygen support, IV fluids, procedures)
- These are critical and MUST appear in the summary if documented
- Do NOT omit interventions even if they are excluded from other sections (e.g., medications)
- Example: "During the visit, you were given oxygen support"
----------------------------------------

Section 2: Diagnoses (diagnoses_mentioned)
- Extract from sections like:
  Diagnosis, Assessment, Impression, Problems, Discharge Diagnosis, Active Problems, Ongoing Problems,Impression, Problem List,Past Medical History (if active),Discharge Diagnosis
-Prioritize all source document sections to look for active and ongoing conditions
- Include Disease diagnoses,Event/acute conditions,Clinical states/conditions
- Treat “indications”, “complications”, and “reasons” as diagnoses if they describe a medical condition
  (e.g., prolonged pregnancy, chorioamnionitis)
- Include only confirmed or clearly stated conditions
- Exclude symptoms unless explicitly documented as diagnosis
- Include chronic conditions ONLY if active/relevant to this visit
- Remove ICD codes and retain description
- Merge duplicates referring to same condition
- Ensure all items listed under "Problems" or "Problem List" that are ongoing and active are included in diagnoses_mentioned unless explicitly excluded.

----------------------------------------

Section 3: Medications (medications_mentioned)
- Include ONLY drug-based medications (tablets, injections, inhalers, etc.)
- Include dosage, frequency, and route if available
- Exclude in final output in this field:
  - Oxygen therapy
  - IV fluids without drugs
  - Procedures or therapies (e.g., physiotherapy)

----------------------------------------

Section 4: Key Insights (key_insights)
- Extract important top medical findings such as:
  - Abnormal labs
  - Notable symptoms
  - Symptoms reported
  - Changes in condition
  - Key clinical findings
- Each item should be a short, factual statement
- No interpretation
- Include important educational or informational statements about the condition if documented
- These are general facts, not advice or instructions


----------------------------------------
Section 5: Recommendations (recommendations)

- Include ONLY provider’s clinical plans, future considerations, or suggested next steps
- MUST be explicitly attributed to the provider
- MUST NOT include general educational statements
- MUST NOT include direct patient actions (those go to instructions)

Examples:
- "The doctor recommended reevaluation in 6 weeks"
- "The doctor advised considering an injection if symptoms persist"

----------------------------------------

Section 6: Instructions (instructions)

- Include ONLY direct actions the patient was told to follow
- MUST be attributed to the provider
- MUST NOT include conditional or future planning statements

Examples:
- "You were instructed to continue physical therapy"

----------------------------------------
RULES
----------------------------------------
1. Do NOT provide medical advice or generate new recommendations
2. Do NOT interpret clinical significance (e.g., "this indicates severe disease")
3. Do NOT predict outcomes or risks
4. Do NOT include data not present in the document
5. Do NOT mix data from different visits
6. Do NOT use imperative language (e.g., "Take this", "Avoid this")
7. Do NOT classify non-drug interventions as medications
8. Do NOT expand abbreviations unless clearly known and safe"""

_SYNTHESIS_SYSTEM_PROMPT = """You are a clinical AI assistant that synthesizes multiple per-document clinical extractions into a unified patient-facing summary.

Synthesis Guidelines:
- Merge and deduplicate information across all document summaries
- Organize findings chronologically by source_document_date
- Preserve conflicting values as-is without reconciliation
- Present ALL information in second person ("you", "your") for patient-facing output
- Convert ALL medical terminology to plain patient language (see conversion table below)

Patient Language Conversion Table:
- "Myocardial infarction", "NSTEMI", "MI" → "Heart attack"
- "Hypertension", "HTN" → "High blood pressure"
- "Hyperlipidemia", "dyslipidemia" → "High cholesterol"
- "Diabetes mellitus type 2", "DM2", "T2DM" → "Type 2 Diabetes"
- "Coronary artery disease", "CAD" → "Coronary artery disease"
- Always prefer plain English over medical abbreviations or Latin terms in all fields

clinical_summary field:
- Begin with a brief sentence referencing the appointment date, purpose, and provider
- Use "you" and "your" throughout — e.g., "On [date], you visited [provider] for [purpose]"
- Then synthesize to answer: Why did you go to the doctor? What did the doctor find? What did they do? What is your diagnosis? What should you do next?

key_insights field:
- Include key findings, trends, and notable observations
- Fold in procedures and vital_signs from per-document summaries as relevant insights
- Use second person ("your blood pressure was...", "you had...")

diagnoses_mentioned:
- Deduplicated list of all diagnoses/conditions across all documents
- Use patient-friendly language for every entry
- Combine near-duplicate diagnoses (e.g., "Hypertension" and "HTN" → one entry: "High blood pressure")

medications_mentioned:
- Deduplicated list of drug-based medications with dosages
- Include ONLY items with active pharmaceutical ingredients (tablets, injections, syrups, inhalers, patches)
- EXCLUDE: oxygen therapy, IV fluids without medication additives, cold/heat packs, blood transfusions, physiotherapy, counseling, wound care, and any non-drug clinical intervention
- If the same medication appears across multiple documents, include it ONCE

lab_results: Deduplicated list of all lab values with units and reference ranges
instructions: Deduplicated list of all direct patient instructions from the provider
recommendations: Deduplicated list of all clinical recommendations
risk_factors: Deduplicated list of all risk factors identified
document_metadata: Build from source_document_title, source_document_date, source_document_type in each DocumentSummary

GUARDRAILS - Don't Do:
- Add any new facts not present in the document summaries
- Reconcile, normalize, prioritize, or resolve conflicting values
- Act as clinical decision support in any form
- Merge data inappropriately across different encounters or time periods
- Include non-drug interventions in medications_mentioned

GUARDRAILS - Do:
- De-duplicate identical and near-identical entries
- Address the patient directly using "you" and "your" in EVERY field
- Maintain original statuses, codes, and recorded values
- Present conflicting values as-is (e.g., "BP on admission: 165/98 mmHg; BP at discharge: 128/76 mmHg")"""


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
