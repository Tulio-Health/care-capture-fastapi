from typing import Any, Dict, Optional
from langchain.prompts import PromptTemplate
from ..common.logging import get_logger

class BasePromptTemplate:
    """Base class for all prompt templates"""
    
    def __init__(self, template: str, input_variables: list[str]):
        self.logger = get_logger(self.__class__.__name__)
        self.template = template
        self.input_variables = input_variables
        self.prompt = PromptTemplate(
            template=template,
            input_variables=input_variables
        )
    
    def format(self, **kwargs: Any) -> str:
        """Format the prompt template with the given variables"""
        try:
            return self.prompt.format(**kwargs)
        except Exception as e:
            self.logger.error(f"Error formatting prompt: {str(e)}")
            raise
    
    def get_template(self) -> str:
        """Get the raw template string"""
        return self.template
    
    def get_input_variables(self) -> list[str]:
        """Get the list of input variables"""
        return self.input_variables 