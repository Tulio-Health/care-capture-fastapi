from langchain.prompts import ChatPromptTemplate
from langchain.chat_models import init_chat_model
from langsmith import traceable
from langchain_core.output_parsers import StrOutputParser, PydanticOutputParser

from src.app.core.settings import get_settings
from src.app.models.intent_identify import IntentResponse
from src.app.models.provider_visit_summarization import ProviderVisitSummarizationResponse

settings = get_settings()
model = init_chat_model(
    model="gpt-4o-mini",
    model_provider="openai",
    openai_api_key=settings.OPENAI_API_KEY,
    temperature=0.2,
)


class PastVisitChain:
    def __init__(self):
        #self.llm = model.invoke(temperature=0.2, input="summarize")
        self.parser = PydanticOutputParser(pydantic_object=ProviderVisitSummarizationResponse)
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

    @traceable(name="summarize")
    def summarize(self, text) -> IntentResponse[None]:
        result = self.chain.invoke({"text": text, "output_format": self.parser.get_format_instructions()})
        return result