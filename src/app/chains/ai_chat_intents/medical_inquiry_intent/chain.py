from langchain.prompts import ChatPromptTemplate
from langchain.chat_models import init_chat_model
from langchain_core.output_parsers import PydanticOutputParser, StrOutputParser
import json

from src.app.common.constants.llm import LLM_MODEL, LLM_PROVIDER
from src.app.models.intent_identify import IntentResponse, IntentAiResponse
from src.app.core import get_settings
from src.app.chains.ai_chat_intents.intend_identifier.models import RouterOptions

settings = get_settings()
model = init_chat_model(
    model=LLM_MODEL.GPT_4O_MINI,
    model_provider=LLM_PROVIDER.OPENAI,
    openai_api_key=settings.OPENAI_API_KEY,
    temperature=0.2,
)

MedicalInquiryResponse = IntentResponse[None]

class MedicalInquiryIntentChain:
    def __init__(self):
        self.parser = PydanticOutputParser(pydantic_object=MedicalInquiryResponse)
        self.prompt = ChatPromptTemplate.from_messages([
            ("system","""Answer the medical inquiry
                
                Rules:
                -No duplicates unless new details
                -Always add a disclaimer "It is advisable to consult your PCP or a specialist".
                -Output format {output_format}"""),
            ("user", "Answer this question in the format specified above: {text}")
            ])
        self.chain = self.prompt | model | StrOutputParser()

    async def handle_intent(self, **kwargs) -> MedicalInquiryResponse:
        text = kwargs['text']
        response_str = self.chain.invoke({"text": text, "output_format": self.parser.get_format_instructions()})
        
        try:
            return IntentResponse(
                intent=RouterOptions.MEDICAL_INQUIRY,
                responses=[
                    IntentAiResponse(
                        type="text",
                        content=response_str if "it is advisable to consult" in response_str.lower() else response_str + " It is advisable to consult your PCP or a specialist.",
                        data=None
                    )
                ]
            )
        except Exception as e:
            print(f"Error creating medical inquiry response: {e}")
            return IntentResponse(
                intent=RouterOptions.MEDICAL_INQUIRY,
                responses=[
                    IntentAiResponse(
                        type="text",
                        content="I apologize, but I couldn't process your medical inquiry properly. It is advisable to consult your PCP or a specialist.",
                        data=None
                    )
                ]
            )
