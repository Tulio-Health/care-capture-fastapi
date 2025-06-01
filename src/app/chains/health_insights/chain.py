from langchain.prompts import ChatPromptTemplate
from langchain.chat_models import init_chat_model
from langsmith import traceable
from langchain_core.output_parsers import PydanticOutputParser

from src.app.common.constants.llm import LLM_MODEL, LLM_PROVIDER
from src.app.core.langsmith_trace import LangSmithTrace
from src.app.core.settings import get_settings
from src.app.models.health_insights_extraction import HealthInsightsResponse

settings = get_settings()
model = init_chat_model(
    model=LLM_MODEL.GPT_4O_MINI,
    model_provider=LLM_PROVIDER.OPENAI,
    openai_api_key=settings.OPENAI_API_KEY,
    temperature=0.2,
)

tracer = LangSmithTrace().trace(tags=[__name__])



class GenerateHealthInsightsChain:
    def __init__(self):
        self.parser = PydanticOutputParser(pydantic_object=HealthInsightsResponse)
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a medical information extraction assistant.
                Your task is to analyze provided medical conversations, summaries, or transcripts and extract structured medical information following these strict rules:
                Extraction Rules: Extract only explicitly stated health or medical information; do not infer or assume details. Be precise and use the exact medical terminology as mentioned in the source; do not paraphrase or generalize.
                If any information is uncertain or incomplete, omit it rather than guess. 
                Keep summaries concise and focused only on key medical facts. Include specific details such as:
                Medication names, dosages, frequencies
                Diagnoses or health conditions (with dates if mentioned)
                Symptoms
                Lab results or vital signs (if mentioned)
                Event or procedure dates
                Always format dates in the YYYY-MM-DD format.
                Combine this extracted data with any provided previous health insights, overriding old details if the latest conversation provides more current or updated information. Clearly categorize the extracted content under:
                Diagnoses (Health Conditions)
                Symptoms
                Medications
                Instructions / Recommendations
                Lab Results (if applicable)
                Dates
                Important Definitions: Health Symptom: A symptom is a subjective experience or sensation reported by a person that may indicate the presence of a problem.
                Symptoms are not diagnoses themselves. They are signals that something might be wrong.
                Examples: Chest pain, Fatigue, Shortness of breath, Nausea. Health Condition:
                A health condition (also called a medical condition or diagnosis) is a defined disease, disorder, or abnormal state of health typically diagnosed by a clinician.
                It is often identified based on symptoms, signs, test results, and medical history. A condition can be acute (short-term) or chronic (long-term).
                Examples: Coronary artery disease, Diabetes, Asthma, Depression. Example: If someone experiences shortness of breath (symptom), a doctor may diagnose heart failure or asthma (condition) as the cause.
                Summary: Symptoms are what you feel. Conditions are what you have.
                Output Format Requirements:{output_format}"""),
            ("user", 
             'Conversation: {summary_text}')
        ])
        self.chain = self.prompt | model | self.parser

    @traceable(name="generate_health_insights")
    def generate_health_insights(self, summary_text: str) -> HealthInsightsResponse:
        result = self.chain.invoke({"summary_text": summary_text, "output_format": self.parser.get_format_instructions()}, config={"callbacks": [tracer]})
        return result