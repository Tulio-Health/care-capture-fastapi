
from langchain.prompts import ChatPromptTemplate
from langchain.chat_models import init_chat_model
from langchain_core.output_parsers import StrOutputParser

from ..core import get_settings

settings = get_settings()
model = init_chat_model(
    model="gpt-4o-mini",
    model_provider="openai",
    openai_api_key=settings.OPENAI_API_KEY,
    temperature=0.2,
)

class HeathInsightsExtractionChain:
    def __init__(self):
        self.prompt = ChatPromptTemplate.from_messages([
            ("system","""Extract structured health information from medical summaries into JSON. Follow this exact format:
                {{
                "conditions": [{{"name": string, "details": string|null, "date": "YYYY-MM-DD"}}],
                "surgeriesAndProcedures": [{{"name": string, "details": string|null, "date": "YYYY-MM-DD"}}],
                "medications": [{{"name": string, "dosage": string|null, "frequency": string|null, "date": "YYYY-MM-DD"}}],
                "priorTesting": [{{"name": string, "result": string|null, "date": "YYYY-MM-DD"}}]
                }}
                Rules:
                -Output raw JSON only - no markdown, no ```json tags
                -Use YYYY-MM-DD dates from createdAt
                -Use null for missing optional fields
                -Include all arrays even if empty
                -Prefer recent info
                -No duplicates unless new details
                -Output valid JSON only"""),
            ("user", "Extract clinical information as JSON:\n{text}")
            ]
        )
        self.chain = self.prompt | model | StrOutputParser()

    def extract(self, text) -> str:
        return self.chain.invoke({"text": text})