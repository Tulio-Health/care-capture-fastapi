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
            ("system", """You are a medical information extraction assistant. Your task is to analyze medical conversations and extract key information in a structured format.
            Rules:
            - Extract only explicitly stated health or medical information
            - Be precise with medical terminology
            - Maintain original medical terms as mentioned
            - When uncertain, omit rather than guess
            - Keep summaries concise and focused
            - Include specific details for medications, diagnoses, and dates from the conversation summary
            - Use previous health insights to combine data from the new conversation summary
            - Override the summary if the latest information is more current
            - Categorize instructions and recommendations clearly
            - While setting date , use the YYYY-MM-DD format

            Output Format Requirements:{output_format}"""),
            ("user", 
             'Conversation: {summary_text} , Previous Health Insights: {prev_health_insights}')
        ])
        self.chain = self.prompt | model | self.parser

    @traceable(name="generate_health_insights")
    def generate_health_insights(self, summary_text: str , prev_health_insights: dict) -> HealthInsightsResponse:
        result = self.chain.invoke({"summary_text": summary_text, "prev_health_insights":prev_health_insights, "output_format": self.parser.get_format_instructions(), "prev_health_insights": prev_health_insights}, config={"callbacks": [tracer]})
        return result