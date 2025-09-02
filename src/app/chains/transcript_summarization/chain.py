from langchain.prompts import ChatPromptTemplate
from langsmith import traceable
from langchain_core.output_parsers import PydanticOutputParser

from src.app.common.llm_factory import get_default_chat_model
from src.app.core.langsmith_trace import LangSmithTrace
from src.app.models.transcript_summarization import TranscriptSummarizationResponse

_tracer = None

def get_tracer():
    global _tracer
    if _tracer is None:
        _tracer = LangSmithTrace().trace(tags=[__name__])
    return _tracer



class TranscriptSummarizationChain:
    def __init__(self):
        # Initialize components except model
        self._model = None
        self.parser = PydanticOutputParser(pydantic_object=TranscriptSummarizationResponse)
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a medical information extraction assistant. Your task is to analyze medical conversations and extract key information in a structured format.
            Rules:
            - Extract only explicitly stated health or medical information
            - Be precise with medical terminology
            - Maintain original medical terms as mentioned
            - When uncertain, omit rather than guess
            - Keep summaries concise and focused
            - Include specific details for medications and diagnoses
            - Categorize instructions and recommendations clearly
            - Override the latest summary if the latest information is more current

            Output Format Requirements:{output_format}"""),
            ("user", 
             'Conversation: {text}')
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

    @traceable(name="summarize")
    def summarize(self, text) -> TranscriptSummarizationResponse:
        result = self.chain.invoke({"text": text, "output_format": self.parser.get_format_instructions()}, config={"callbacks": [get_tracer()]})
        return result