
from langchain.prompts import ChatPromptTemplate
from langchain.chat_models import init_chat_model
from langchain_core.output_parsers import PydanticOutputParser
from src.app.models.intent_identify import IntentResponse

from src.app.core import get_settings

settings = get_settings()
model = init_chat_model(
    model="gpt-4o-mini",
    model_provider="openai",
    openai_api_key=settings.OPENAI_API_KEY,
    temperature=0.2,
)


HealthInsightsExtractionResponse = IntentResponse[None]
class HealthInsightsIntentChain:
    def __init__(self):
        self.parser = PydanticOutputParser(pydantic_object=HealthInsightsExtractionResponse)
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", "Provide a short and crisp summary of relevant health insights from the medical context to answer the user's query. Output format: {output_format}"),
            ("user", "Extract health insights from the context '{context}' to answer the query '{text}' in the format specified above.")
        ])
        self.chain = self.prompt | model | self.parser

    def extract(self, **kwargs) -> HealthInsightsExtractionResponse:
        text = kwargs['text']
        context = kwargs['context']
        visit_summary = context['visit_summary']
        return self.chain.invoke({"text": text ,"context":visit_summary , "output_format": self.parser.get_format_instructions()})