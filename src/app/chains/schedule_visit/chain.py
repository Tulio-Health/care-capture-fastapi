from langchain.prompts import ChatPromptTemplate
from datetime import datetime

from langchain_core.output_parsers import PydanticOutputParser
from src.app.common.llm_factory import get_default_chat_model
from src.app.core.langsmith_trace import LangSmithTrace
from src.app.models.schedule_visit import ScheduleVisitResponse

_tracer = None

def get_tracer():
    global _tracer
    if _tracer is None:
        _tracer = LangSmithTrace().trace(tags=[__name__])
    return _tracer


def get_callbacks():
    """Get callbacks list, handling disabled tracing"""
    tracer = get_tracer()
    return [tracer] if tracer is not None else []



class ScheduleVisitChain:
    def __init__(self):
        self._model = None
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
        self._chain = None

    @property
    def model(self):
        """Lazy load the model on first access"""
        if self._model is None:
            self._model = get_default_chat_model()
        return self._model
    
    @property
    def chain(self):
        """Lazy load the chain on first access"""
        if self._chain is None:
            self._chain = self.prompt | self.model | self.parser
        return self._chain

    def schedule_visit(self, **kwargs) -> str:
        text = kwargs['text']
        providers = kwargs['providers']
        return self.chain.invoke({"text": text, "providers": providers, "output_format": self.parser.get_format_instructions() , "current_timestamp": datetime.now()}, config={"callbacks": get_callbacks()})