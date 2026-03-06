from langchain.prompts import ChatPromptTemplate
from langsmith import traceable
from langchain_core.output_parsers import PydanticOutputParser

from src.app.common.llm_factory import get_default_chat_model
from src.app.core.langsmith_trace import LangSmithTrace
from src.app.models.fhir_analysis import FhirAnalysisResponse

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


class FhirAnalysisChain:
    """AI chain for analyzing FHIR resources and generating clinical insights"""
    
    def __init__(self):
        # Initialize components except model
        self._model = None
        self.parser = PydanticOutputParser(pydantic_object=FhirAnalysisResponse)
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a clinical AI assistant specialized in analyzing FHIR healthcare data. 
            Your task is to analyze patient FHIR resources and provide comprehensive clinical insights.

            Analysis Guidelines:
            - Focus on clinically significant patterns and findings
            - Identify potential health risks and concerns
            - Highlight medication interactions or polypharmacy risks
            - Note trends in lab results and vital signs
            - Provide actionable recommendations for care
            - Be precise with medical terminology
            - Base insights only on data provided
            - Synthesize information across multiple resource types
            - Consider chronic vs acute conditions
            - Note any gaps in care or missing follow-ups

            GUARDRAILS - Don't Do:
            - Add any new facts, values, or events not explicitly present in the EHR data
            - Infer missing clinical logic, intent, causality, or conclusions
            - Interpret or explain the clinical meaning or significance of any data (e.g., labs, diagnoses, procedures)
            - Reconcile, normalize, prioritize, or resolve conflicting records or values
            - Override, modify, reword, or correct clinician-entered information
            - Predict outcomes, risks, disease progression, or treatment effectiveness
            - Recommend actions, treatments, follow-ups, lifestyle changes, or care decisions
            - Act as clinical decision support in any form
            - Assume relationships between resources unless explicitly linked in the EHR (e.g., Condition ↔ Medication)
            - Assume completion, adherence, success, or patient compliance for orders or plans
            - Merge or blend data across encounters unless explicitly requested
            - Reclassify, reinterpret, or change clinical statuses, priorities, or severities
            - Transform structured data into advisory, judgmental, or evaluative language
            - Implicitly summarize beyond the stated scope of the selected FHIR resources

            GUARDRAILS - Do:
            - Summarize information strictly from the provided EHR records without adding new facts
            - De-duplicate structured entries when multiple identical records exist (e.g., same Observation, MedicationRequest)
            - Normalize terminology into patient-friendly language while preserving clinical intent (e.g., "HTN" → "high blood pressure"). Terminology normalization applies only to standard abbreviations and codes and must not alter clinical meaning, certainty, or intent
            - Collapse timelines clearly by grouping events chronologically without implying causality
            - Attribute source, encounter, and date for each summarized item
            - Preserve the exact clinical meaning of the original EHR data
            - Present data descriptively, not interpretively
            - Surface explicitly stated relationships only (e.g., references already linked in FHIR)
            - Reflect multiple values or conflicts as-is without reconciliation
            - Maintain original statuses, codes, and recorded values
            - Use neutral, informational language suitable for patient viewing
            - Limit summaries to the explicitly selected FHIR resources and encounters

            Output Format Requirements:{output_format}"""),
            ("user", """Analyze the following patient FHIR data:

**Appointment Context:**
- Date: {appointment_date}
- Purpose: {appointment_purpose}
- Provider: {provider_name}

**FHIR Resources Summary:**
{fhir_summary}

**Resource Counts:**
{resource_counts}

Provide a comprehensive clinical analysis including:
1. Overall clinical summary
2. Key insights and findings
3. Condition analysis and patterns
4. Medication analysis
5. Observations and trends
6. Risk factors
7. Clinical recommendations""")
        ])
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

    @traceable(name="fhir_analysis")
    def analyze(
        self, 
        appointment_context: dict,
        fhir_summary: str,
        resource_counts: dict[str, int]
    ) -> FhirAnalysisResponse:
        """
        Analyze FHIR resources and generate clinical insights
        
        Args:
            appointment_context: Dict with appointment details (date, purpose, provider)
            fhir_summary: Summarized FHIR data by resource type
            resource_counts: Count of each resource type
            
        Returns:
            FhirAnalysisResponse with clinical insights
        """
        # Format resource counts for display
        counts_text = "\n".join([f"- {resource_type}: {count}" for resource_type, count in resource_counts.items()])
        
        result = self.chain.invoke({
            "appointment_date": appointment_context.get("appointment_date", "N/A"),
            "appointment_purpose": appointment_context.get("purpose", "N/A"),
            "provider_name": appointment_context.get("provider_name", "N/A"),
            "fhir_summary": fhir_summary,
            "resource_counts": counts_text,
            "output_format": self.parser.get_format_instructions()
        }, config={"callbacks": get_callbacks()})
        
        return result
