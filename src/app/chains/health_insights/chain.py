from langchain.prompts import ChatPromptTemplate
from langsmith import traceable
from langchain_core.output_parsers import PydanticOutputParser

from src.app.common.llm_factory import get_default_chat_model
from src.app.core.langsmith_trace import LangSmithTrace
from src.app.models.health_insights_extraction import HealthInsightsResponse
from src.app.chains.health_insights.constants import (
    HEALTH_INSIGHTS_EXTRACTION_SYSTEM_PROMPT,
    HEALTH_INSIGHTS_EXTRACTION_USER_PROMPT
)

_tracer = None

def get_tracer():
    global _tracer
    if _tracer is None:
        _tracer = LangSmithTrace().trace(tags=[__name__])
    return _tracer



class GenerateHealthInsightsChain:
    def __init__(self):
        self._model = None
        self.parser = PydanticOutputParser(pydantic_object=HealthInsightsResponse)
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", HEALTH_INSIGHTS_EXTRACTION_SYSTEM_PROMPT),
            ("user", HEALTH_INSIGHTS_EXTRACTION_USER_PROMPT)
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

    @traceable(name="generate_health_insights")
    def generate_health_insights(self, summary_text: str) -> HealthInsightsResponse:
        result = self.chain.invoke({"summary_text": summary_text, "output_format": self.parser.get_format_instructions()}, config={"callbacks": [get_tracer()]})
        return result