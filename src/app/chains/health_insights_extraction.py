
from langchain.prompts import ChatPromptTemplate
from langchain.chat_models import init_chat_model
from langchain_core.output_parsers import PydanticOutputParser

from src.app.models.health_insights_extraction import HealthInsights
from src.app.models.intent_identify import IntentResponse

from ..core import get_settings

settings = get_settings()
model = init_chat_model(
    model="gpt-4o-mini",
    model_provider="openai",
    openai_api_key=settings.OPENAI_API_KEY,
    temperature=0.2,
)


#HealthInsightsExtractionResponse = IntentResponse[HealthInsights]
HealthInsightsExtractionResponse = IntentResponse[None]
class HeathInsightsExtractionChain:
    def __init__(self):
        self.parser = PydanticOutputParser(pydantic_object=HealthInsightsExtractionResponse)
        self.prompt = ChatPromptTemplate.from_messages([
            ("system","""Extract structured health information from medical summaries into JSON. Follow this exact format:{output_format}"""),
            ("user", "Extract clinical information as JSON:\n{text}")
            ]
        )
        self.chain = self.prompt | model | self.parser

    def extract(self, text) -> str:
        return self.chain.invoke({"text": text , "output_format": self.parser.get_format_instructions()})