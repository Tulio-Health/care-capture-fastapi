from langchain.prompts import ChatPromptTemplate
from langchain.chat_models import init_chat_model
from datetime import datetime

from langchain_core.output_parsers import PydanticOutputParser
from src.app.common.constants.llm import LLM_MODEL, LLM_PROVIDER
from src.app.core.langsmith_trace import LangSmithTrace
from src.app.models.schedule_visit import ScheduleVisitResponse
from src.app.core import get_settings

settings = get_settings()
model = init_chat_model(
    model=LLM_MODEL.GPT_4O_MINI,
    model_provider=LLM_PROVIDER.OPENAI,
    openai_api_key=settings.OPENAI_API_KEY,
    temperature=0.2,
)

tracer = LangSmithTrace().trace(tags=[__name__])



class ScheduleVisitChain:
    def __init__(self):
        self.parser = PydanticOutputParser(pydantic_object=ScheduleVisitResponse)
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", "You are a medical appointment assistant. "
             "Your job is to read the patient's request, choose the single most suitable doctor "
             "(by name, specialty, location, availability, or any details provided). "
             "If the patient explicitly mentions a doctor's name, look up that name first and regex match "
             "If the patient explicitly mentions a location, match that location with provider's address "
             "if no exact name match is found, match by abbreviated names (e.g. Dr. Rich for RICHARD, Dr. Mill for Dr. Miller) or other criteria. "
             "If no match is found, return a JSON object with all fields set to null."
             "use the current date to schedule appointments. For example, if the patient requests an appointment next Monday, and today is {current_timestamp}, the appointment should be scheduled for next Monday"
             ),
            ("user", '{text}, {providers} . Output format requirements: {output_format}'),
        ])
        self.chain = self.prompt | model | self.parser

    def schedule_visit(self, **kwargs) -> str:
        text = kwargs['text']
        providers = kwargs['providers']
        return self.chain.invoke({"text": text, "providers": providers, "output_format": self.parser.get_format_instructions() , "current_timestamp": datetime.now()}, config={"callbacks": [tracer]})