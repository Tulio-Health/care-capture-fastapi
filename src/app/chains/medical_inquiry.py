from langchain.prompts import ChatPromptTemplate
from langchain.chat_models import init_chat_model

from langchain_core.output_parsers import StrOutputParser
from ..core import get_settings

settings = get_settings()
model = init_chat_model(
    model="gpt-4o-mini",
    model_provider="openai",
    openai_api_key=settings.OPENAI_API_KEY,
    temperature=0.2,
)


class MedicalInquiryChain:
    def __init__(self):
        #self.llm = model.invoke(temperature=0.2, input="summarize")
        self.prompt = ChatPromptTemplate.from_messages([
            ("system","""Answer thie medical inquiry
                
                Rules:
                -No duplicates unless new details
                -Output valid string only"""),
            ("user", "Answer this question in the format specified above: {text}")
            ])
        self.chain = self.prompt | model | StrOutputParser()

    def answer(self, text) -> str:
        return self.chain.invoke({"text": text})
