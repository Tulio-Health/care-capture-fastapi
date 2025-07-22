from langchain.prompts import ChatPromptTemplate
from langchain.chat_models import init_chat_model
from langchain_core.output_parsers import StrOutputParser
from langchain.memory import RedisChatMessageHistory
from pydantic import BaseModel

from src.app.common.constants.llm import LLM_MODEL, LLM_PROVIDER
from src.app.core.settings import get_settings

settings = get_settings()
model = init_chat_model(
    model=LLM_MODEL.GPT_4O_MINI,
    model_provider=LLM_PROVIDER.OPENAI,
    openai_api_key=settings.OPENAI_API_KEY,
    temperature=0.2,
)

class MedicalChatChain:
    def __init__(self):
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a medical assistant helping with patient care.
                Context:
                Patient Profile: {user_profile}
                Visit Summary: {visit_summary}
                Chat History: {chat_history}
                
                Guidelines:
                - Reference only provided medical information
                - Be clear and professional
                - Defer to doctor for medical advice
                - Explain medical terms clearly"""),
            ("human", "{input}"),
        ])

        # Simple LCEL chain
        self.chain = (
            self.prompt 
            | model 
            | StrOutputParser()
        )

    def chat(self, input_text: str, context: dict) -> str:
        return self.chain.invoke({
            "input": input_text,
            "user_profile": context["user_profile"],
            "visit_summary": context["visit_summary"],
            "chat_history": context["chat_history"]
        })