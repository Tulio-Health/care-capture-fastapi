from langchain.prompts import ChatPromptTemplate
from langchain.chat_models import init_chat_model
from langsmith import traceable
from langchain_core.output_parsers import PydanticOutputParser

from src.app.common.constants.llm import LLM_MODEL, LLM_PROVIDER
from src.app.core.settings import get_settings
from src.app.models.health_insights_extraction import HealthInsightsResponse

settings = get_settings()
model = init_chat_model(
    model=LLM_MODEL.GPT_4O_MINI,
    model_provider=LLM_PROVIDER.OPENAI,
    openai_api_key=settings.OPENAI_API_KEY,
    temperature=0.2,
)


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
            - Include specific details for medications and diagnoses
            - Categorize instructions and recommendations clearly
            - Override the latest summary if the latest information is more current

            Output Format Requirements:{output_format}"""),
            ("user", 
             'Conversation: {text}')
        ])
        self.chain = self.prompt | model | self.parser

    @traceable(name="generate_health_insights")
    def generate_health_insights(self, text) -> HealthInsightsResponse:
        result = self.chain.invoke({"text": text, "output_format": self.parser.get_format_instructions()})
        return result