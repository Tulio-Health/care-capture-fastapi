from langchain.prompts import ChatPromptTemplate
from langchain.chat_models import init_chat_model
from langsmith import traceable
from langchain_core.output_parsers import PydanticOutputParser
import json
from typing import Dict, Any, List, Optional

from src.app.common.constants.llm import LLM_MODEL, LLM_PROVIDER
from src.app.models.intent_identify import IntentResponse, IntentAiResponse
from src.app.models.past_visit_query import PastVisitQuery
from src.app.core import get_settings

settings = get_settings()
model = init_chat_model(
    model=LLM_MODEL.GPT_4O_MINI,
    model_provider=LLM_PROVIDER.OPENAI,
    openai_api_key=settings.OPENAI_API_KEY,
    temperature=0.2,
)

NO_PAST_VISIT_INFORMATION_AVAILABLE = "I am sorry, but I don't have any past Provider visit information available for you, please try with a different query."

class PastVisitIntentChain:
    def __init__(self):
        self.parser = PydanticOutputParser(pydantic_object=IntentResponse[None])
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a medical expert in extracting patient past visit information. 
             You have been given user's past conversions summaries with their provider.
             The user query is the user's question or request for information.
             The past conversions summaries are the summaries of the patient's past conversions with the provider.
             The past conversions summaries are in the format of a list of dictionaries, each dictionary containing the following keys: {context}
             In case conversions summaries are not available, you must respond as 
             ""I am sorry, but I don't have any past Provider visit information available for you, please try with a different query.""
             Make sure you follow the output format requirements: {output_format}"""),
            ("user", 
             'Conversation: Answer the query from the context {text} , Context: {context}')
        ])
        self.chain = self.prompt | model | self.parser

    @traceable(name="handle_intent")
    def handle_intent(self, **kwargs) -> IntentResponse[None]:
        text = kwargs['text']
        context = kwargs['context']
        visit_summary = context['visit_summary']
        print(f"Visit summary: {visit_summary}")
        result = self.chain.invoke({"text": text, "context":visit_summary, "output_format": self.parser.get_format_instructions()})
        return result
