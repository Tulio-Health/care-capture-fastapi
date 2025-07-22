from langsmith import Client as LangSmithClient
from langchain.callbacks.tracers import LangChainTracer

from src.app.core.settings import get_settings

settings = get_settings()


class LangSmithTrace:
    def __init__(self):
        self.client = LangSmithClient(
            api_key=settings.LANGSMITH_API_KEY,
            api_url=settings.LANGSMITH_ENDPOINT,
        )
        
    def trace(self, tags: list[str] = None):
        return LangChainTracer(
            project_name=settings.LANGSMITH_PROJECT,
            client=self.client,
            tags=tags,
        )