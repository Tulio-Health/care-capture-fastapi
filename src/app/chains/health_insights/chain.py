from langchain.prompts import ChatPromptTemplate
from langchain.chat_models import init_chat_model
from langsmith import traceable
from langchain_core.output_parsers import PydanticOutputParser

from src.app.common.constants.llm import LLM_MODEL, LLM_PROVIDER
from src.app.core.langsmith_trace import LangSmithTrace
from src.app.core.settings import get_settings
from src.app.models.health_insights_extraction import HealthInsightsResponse
from src.app.chains.health_insights.constants import (
    HEALTH_INSIGHTS_EXTRACTION_SYSTEM_PROMPT,
    HEALTH_INSIGHTS_EXTRACTION_USER_PROMPT
)

settings = get_settings()
model = init_chat_model(
    model=LLM_MODEL.GPT_4O_MINI,
    model_provider=LLM_PROVIDER.OPENAI,
    openai_api_key=settings.OPENAI_API_KEY,
    temperature=0.2,
)

tracer = LangSmithTrace().trace(tags=[__name__])



class GenerateHealthInsightsChain:
    def __init__(self):
        self.parser = PydanticOutputParser(pydantic_object=HealthInsightsResponse)
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", HEALTH_INSIGHTS_EXTRACTION_SYSTEM_PROMPT),
            ("user", HEALTH_INSIGHTS_EXTRACTION_USER_PROMPT)
        ])
        self.chain = self.prompt | model | self.parser

    @traceable(name="generate_health_insights")
    def generate_health_insights(self, summary_text: str) -> HealthInsightsResponse:
        result = self.chain.invoke({"summary_text": summary_text, "output_format": self.parser.get_format_instructions()}, config={"callbacks": [tracer]})
        return result