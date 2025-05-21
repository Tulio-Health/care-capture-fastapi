
from langchain.prompts import ChatPromptTemplate
from langchain.chat_models import init_chat_model
from langchain_core.output_parsers import PydanticOutputParser
from src.app.common.constants.cache_keys import CACHE_KEY
from src.app.common.constants.llm import LLM_MODEL , LLM_PROVIDER
from src.app.db.config.database import get_db
from src.app.db.objects.entities.patient_health_insights import PatientHealthInsights
from src.app.db.objects.repositories.patient_health_insights import PatientHealthInsightsRepository
from src.app.models.intent_identify import IntentResponse
from src.app.cache.redis import redis_client
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.encoders import jsonable_encoder


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


    async def handle_intent(self, **kwargs) -> HealthInsightsExtractionResponse:
        text = kwargs['text']
        user_id = kwargs['user_id']
        context = await self.fetch_health_insights(user_id)
        return self.invoke(text, context)
    
    async def fetch_health_insights(self, user_id: str ) -> str:
        async for session in get_db():
            repo = PatientHealthInsightsRepository(session)
            health_insights = await repo.get_by_user_id(user_id)
            return jsonable_encoder([r.__dict__ for r in health_insights])
    
    def invoke(self, text: str, context: str) -> HealthInsightsExtractionResponse:
        return self.chain.invoke({"text": text ,"context":context , "output_format": self.parser.get_format_instructions()})