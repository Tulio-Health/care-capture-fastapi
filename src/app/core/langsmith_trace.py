from langsmith import Client as LangSmithClient
from langchain.callbacks.tracers import LangChainTracer

from src.app.core.settings import get_settings


class LangSmithTrace:
    def __init__(self):
        self._client = None
        self._settings = None
    
    @property
    def settings(self):
        """Lazy load settings"""
        if self._settings is None:
            self._settings = get_settings()
        return self._settings
    
    @property 
    def client(self):
        """Lazy load LangSmith client"""
        if self._client is None:
            self._client = LangSmithClient(
                api_key=self.settings.LANGSMITH_API_KEY,
                api_url=self.settings.LANGSMITH_ENDPOINT,
            )
        return self._client
    
    def is_enabled(self) -> bool:
        """Check if LangSmith tracing is enabled"""
        return (
            self.settings.LANGSMITH_TRACING.lower() == 'true' and
            bool(self.settings.LANGSMITH_API_KEY) and
            bool(self.settings.LANGSMITH_PROJECT)
        )
        
    def trace(self, tags: list[str] = None):
        """Return LangChain tracer if enabled, otherwise None"""
        if not self.is_enabled():
            return None
            
        return LangChainTracer(
            project_name=self.settings.LANGSMITH_PROJECT,
            client=self.client,
            tags=tags,
        )