from langchain.prompts import ChatPromptTemplate
from langchain.chat_models import init_chat_model
from langsmith import traceable
from langchain_core.output_parsers import PydanticOutputParser

from src.app.common.constants.llm import LLM_MODELS, LLM_PROVIDERS
from src.app.models.intent_identify import IntentResponse
from src.app.core import get_settings

settings = get_settings()
model = init_chat_model(
    model=LLM_MODELS.GPT_4O_MINI,
    model_provider=LLM_PROVIDERS.OPENAI,
    openai_api_key=settings.OPENAI_API_KEY,
    temperature=0.2,
)


class PastVisitIntentChain:
    def __init__(self):
        #self.llm = model.invoke(temperature=0.2, input="summarize")
        self.parser = PydanticOutputParser(pydantic_object=IntentResponse[None])
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a medical information extraction assistant.

            Output Format Requirements:{output_format}"""),
            ("user", 
             'Conversation: Answer the query from the context {text} , Context: {context}')
        ])
        self.chain = self.prompt | model | self.parser

    @traceable(name="summarize")
    def summarize(self, **kwargs) -> IntentResponse[None]:
        text = kwargs['text']
        context = kwargs['context']
        visit_summary = context['visit_summary']
        print(f"Visit summary: {visit_summary}")
        result = self.chain.invoke({"text": text, "context":visit_summary, "output_format": self.parser.get_format_instructions()})
        return result
