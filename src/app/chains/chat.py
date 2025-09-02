from langchain.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain.memory import RedisChatMessageHistory
from pydantic import BaseModel

from src.app.common.llm_factory import get_default_chat_model

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

        # Get model lazily to ensure SSM parameters are loaded
        self.model = None
        
    def _get_chain(self):
        """Get or create the chain with lazy model initialization"""
        if self.model is None:
            self.model = get_default_chat_model()
        
        return (
            self.prompt 
            | self.model 
            | StrOutputParser()
        )

    def chat(self, input_text: str, context: dict) -> str:
        chain = self._get_chain()
        return chain.invoke({
            "input": input_text,
            "user_profile": context["user_profile"],
            "visit_summary": context["visit_summary"],
            "chat_history": context["chat_history"]
        })