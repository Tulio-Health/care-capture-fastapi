"""LangChain AI chain for analyzing medical document attachments."""

from langchain.prompts import ChatPromptTemplate
from langsmith import traceable
from langchain_core.output_parsers import PydanticOutputParser

from src.app.common.llm_factory import get_default_chat_model
from src.app.core.langsmith_trace import LangSmithTrace
from src.app.models.attachment_summarization import AttachmentSummarizationResponse

_tracer = None


def get_tracer():
    global _tracer
    if _tracer is None:
        _tracer = LangSmithTrace().trace(tags=[__name__])
    return _tracer


def get_callbacks():
    """Get callbacks list, handling disabled tracing"""
    tracer = get_tracer()
    return [tracer] if tracer is not None else []


class AttachmentSummarizationChain:
    """AI chain for analyzing medical document attachments and generating clinical insights"""

    def __init__(self):
        # Initialize components except model
        self._model = None
        self.parser = PydanticOutputParser(
            pydantic_object=AttachmentSummarizationResponse
        )
        self.prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    """You are a clinical AI assistant specialized in analyzing medical documents and reports. 
            Your task is to analyze medical documents (lab reports, consultation notes, procedure reports, 
            imaging reports, progress notes, etc.) and extract key clinical information.

            Analysis Guidelines:
            - Extract all mentioned diagnoses, conditions, and clinical findings
            - List all medications with dosages and instructions
            - Identify laboratory test results with values and reference ranges
            - Note imaging findings and interpretations
            - Extract vital signs and physical examination findings
            - Identify procedures performed or recommended
            - Note any recommendations, follow-up instructions, or care plans
            - Highlight critical, abnormal, or concerning findings
            - Identify risk factors and patient history
            - Maintain clinical accuracy and medical terminology
            - Synthesize information across multiple documents chronologically
            - Note any conflicting information between documents

            GUARDRAILS - Don't Do:
            - Add any new facts, values, or events not explicitly present in the documents
            - Infer missing clinical logic, intent, causality, or conclusions
            - Interpret or explain the clinical meaning or significance of findings
            - Reconcile, normalize, prioritize, or resolve conflicting values
            - Override, modify, reword, or correct information from documents
            - Predict outcomes, risks, disease progression, or treatment effectiveness
            - Recommend actions, treatments, follow-ups beyond what's stated in documents
            - Act as clinical decision support in any form
            - Assume relationships between findings unless explicitly stated
            - Assume completion, adherence, or success of treatments
            - Merge or blend data inappropriately across different encounters or time periods
            - Reclassify, reinterpret, or change clinical statuses or severities
            - Transform descriptive data into advisory or evaluative language

            GUARDRAILS - Do:
            - Summarize information strictly from the provided documents without adding facts
            - De-duplicate identical entries when same information appears in multiple documents
            - Normalize terminology into patient-friendly language while preserving clinical intent
              (e.g., "HTN" → "high blood pressure", "DM2" → "Type 2 Diabetes")
            - Organize information chronologically by document date
            - Attribute each finding to its source document with date
            - Present conflicting values as-is without reconciliation
            - Maintain original statuses, codes, and recorded values
            - Use neutral, informational language suitable for patient viewing
            - Preserve exact numerical values and units for all lab results
            - Include reference ranges when provided in documents
            - Note document types (lab report, progress note, etc.) for context

            Output Format Requirements:{output_format}""",
                ),
                (
                    "user",
                    """Analyze the following medical documents for this appointment:

**Appointment Context:**
- Date: {appointment_date}
- Purpose: {appointment_purpose}
- Provider: {provider_name}

**Medical Documents:**
{documents_text}

**Document Count:** {document_count}

Provide a comprehensive clinical analysis including:
1. Overall clinical summary synthesizing all documents
2. Key clinical insights and findings
3. All diagnoses and conditions mentioned
4. All medications mentioned with dosages
5. Laboratory results with values and reference ranges
6. Recommendations and follow-up instructions
7. Risk factors identified
8. Document metadata summary""",
                ),
            ]
        )
        self._chain = None

    @property
    def model(self):
        """Lazy load the model on first access"""
        if self._model is None:
            self._model = get_default_chat_model()
        return self._model

    @property
    def chain(self):
        """Lazy load the chain on first access"""
        if self._chain is None:
            self._chain = self.prompt | self.model | self.parser
        return self._chain

    @traceable(name="analyze_attachments")
    def analyze(
        self, appointment_context: dict, documents_text: str, document_count: int
    ) -> AttachmentSummarizationResponse:
        """
        Analyze medical document attachments and generate clinical insights.

        Args:
            appointment_context: Dict with appointment_date, purpose, provider_name
            documents_text: Formatted text from all documents
            document_count: Number of documents analyzed

        Returns:
            AttachmentSummarizationResponse with structured clinical analysis
        """
        result = self.chain.invoke(
            {
                "appointment_date": appointment_context.get("appointment_date", "N/A"),
                "appointment_purpose": appointment_context.get("purpose", "N/A"),
                "provider_name": appointment_context.get("provider_name", "N/A"),
                "documents_text": documents_text,
                "document_count": document_count,
                "output_format": self.parser.get_format_instructions(),
            },
            config={"callbacks": get_callbacks()},
        )
        return result
