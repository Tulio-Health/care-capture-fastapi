import logging
from langchain.prompts import ChatPromptTemplate
from langchain.chat_models import init_chat_model
from langchain_core.output_parsers import PydanticOutputParser, StrOutputParser

from src.app.common.constants.llm import LLM_MODEL, LLM_PROVIDER
from src.app.core.langsmith_trace import LangSmithTrace
from src.app.models.intent_identify import IntentResponse, IntentAiResponse
from src.app.core import get_settings
from src.app.chains.ai_chat_intents.intend_identifier.models import RouterOptions

settings = get_settings()

tracer = LangSmithTrace().trace(tags=[__name__])

model =init_chat_model(
    model=LLM_MODEL.GPT_4O_MINI,
    model_provider=LLM_PROVIDER.OPENAI,
    openai_api_key=settings.OPENAI_API_KEY,
    temperature=0.2,
)

logger = logging.getLogger(__name__)


MedicalInquiryResponse = IntentResponse[None]

class MedicalInquiryIntentChain:
    def __init__(self):
        self.parser = PydanticOutputParser(pydantic_object=MedicalInquiryResponse)
        self.prompt = ChatPromptTemplate.from_messages([
            ("system","""
                You are an AI assistant that provides medical information to users. Respond to the user's medical inquiry based on the following rules:
                - Whenever you quantify a value or share symptoms, add the disclaimer "It is advisable to consult your PCP or a specialist." For example: "Your blood sugar range is 80-120 mg/dL. It is advisable to consult your PCP or a specialist."
                - Avoid providing duplicate information unless there are new details to add.
                - Format your response as specified in the {output_format} parameter.
            """),
            ("user", "Answer this question in the format specified above: {text}")
            ])
        self.chain = self.prompt | model | self.parser

    async def handle_intent(self, **kwargs) -> MedicalInquiryResponse:
        try:
            text = kwargs['text']
            response = self.chain.invoke({"text": text, "output_format": self.parser.get_format_instructions()},config={"callbacks": [tracer]})
            return response
        except Exception as e:
            logger.error(f"Error processing medical inquiry: {str(e)}")
            return MedicalInquiryResponse(
                intent=RouterOptions.MEDICAL_INQUIRY, 
                responses=[IntentAiResponse(
                    type="text", 
                    content="I apologize, but I couldn't process your medical inquiry. It is advisable to consult your PCP or a specialist.", 
                    data=None)])