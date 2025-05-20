from langchain.prompts import ChatPromptTemplate
from langchain.chat_models import init_chat_model
from langchain_core.output_parsers import PydanticOutputParser
from src.app.common.constants.cache_keys import CACHE_KEY
from src.app.common.constants.llm import LLM_MODEL , LLM_PROVIDER
from src.app.models.intent_identify import IntentResponse
from src.app.cache.redis import redis_client

from src.app.core import get_settings

settings = get_settings()
model = init_chat_model(
    model=LLM_MODEL.GPT_4O_MINI,
    model_provider=LLM_PROVIDER.OPENAI,
    openai_api_key=settings.OPENAI_API_KEY,
    temperature=0.2,
)


HealthInsightsExtractionResponse = IntentResponse[None]
class HealthInsightsIntentChain:
    def __init__(self):
        self.parser = PydanticOutputParser(pydantic_object=HealthInsightsExtractionResponse)
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", "Provide a short and crisp answer of user query of relevant health insights from the medical context to answer the user's query. Output format: {output_format}"),
            ("user", "Extract health insights from the context '{context}' to answer the query '{text}' in the format specified above.")
        ])
        self.chain = self.prompt | model | self.parser
        self.cache = redis_client.client

    async def handle_intent(self, **kwargs) -> HealthInsightsExtractionResponse:
        text = kwargs['text']
        conversation_id = kwargs['conversation_id']
        context = self.fetch_visit_summary(conversation_id)
        return self.invoke(text, context)
    
    def fetch_visit_summary(self, conversation_id: str) -> str:
        cache_key = CACHE_KEY.CONVERSATION_PROVIDER_VISIT_SUMMARY.format(conversation_id)
        return self.cache.get(cache_key)
    
    def invoke(self, text: str, context: str) -> HealthInsightsExtractionResponse:
        return self.chain.invoke({"text": text ,"context":context , "output_format": self.parser.get_format_instructions()})