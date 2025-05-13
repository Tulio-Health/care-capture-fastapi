from langchain.prompts import ChatPromptTemplate
from langchain.chat_models import init_chat_model

from langchain_core.output_parsers import PydanticOutputParser

from src.app.models.intent_identify import IntentResponse
from ..core import get_settings

settings = get_settings()
model = init_chat_model(
    model="gpt-4o-mini",
    model_provider="openai",
    openai_api_key=settings.OPENAI_API_KEY,
    temperature=0.2,
)

MedicalInquiryResponse = IntentResponse[None]

class MedicalInquiryChain:
    def __init__(self):
        self.parser = PydanticOutputParser(pydantic_object=MedicalInquiryResponse)
        self.prompt = ChatPromptTemplate.from_messages([
            ("system","""Answer the medical inquiry
                
                Rules:
                -No duplicates unless new details
                -Always add a disclaimer that its advisable to consult your PCP or a specialist.
                -Output format {output_format}"""),
            ("user", "Answer this question in the format specified above: {text}")
            ])
        self.chain = self.prompt | model | self.parser

    def answer(self, text) -> MedicalInquiryResponse:
        return self.chain.invoke({"text": text , "output_format": MedicalInquiryResponse.model_json_schema()})
