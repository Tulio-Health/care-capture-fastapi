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


class ProvidervisitSummarizationChain:
    def __init__(self):
        #self.llm = model.invoke(temperature=0.2, input="summarize")
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a medical information extraction assistant. Your task is to analyze medical conversations and extract key information in a structured format.
            Rules:
            - Extract only explicitly stated information
            - Be precise with medical terminology
            - Maintain original medical terms as mentioned
            - When uncertain, omit rather than guess
            - Keep summaries concise and focused
            - Include specific details for medications and diagnoses
            - Categorize instructions and recommendations clearly

            Output Format Requirements:
            - All output must be valid JSON
            - summaryText: Single paragraph, max 250 words
            - keyPoints: List of distinct, important points
            - medications: Must include name, specify other fields only if explicitly stated
            - diagnoses: Include both condition and current status
            - instructions: Categorize as "medication", "lifestyle", "follow-up", or "other"
            - recommendations: Include specific actionable items with type classification
            - Empty arrays are preferred over null values
            - Remove any duplicate entries"""),
            ("user", "Extract the following information from this medical conversation and format as JSON:\n" +
             '{{\n' +
             '"summary_text": "brief summary of the conversation",\n' +
             '"key_points": {{\n' +
             '    "points": ["key point 1", "key point 2"]\n' +
             '}},\n' +
             '"medications": [\n' +
             '    {{"name": "medication name"}}\n' +
             '],\n' +
             '"diagnoses": [\n' +
             '    {{"condition": "specific condition", "status": "current status"}}\n' +
             '],\n' +
             '"instructions": [\n' +
             '    {{"instruction": "specific instruction", "category": "category type"}}\n' +
             '],\n' +
             '"recommendations": [\n' +
             '    {{"recommendation": "specific recommendation", "type": "recommendation type"}}\n' +
             ']\n' +
             '}}\n\n' +
             'Conversation: {text}')
        ])
        self.chain = self.prompt | model | StrOutputParser()

    def summarize(self, text) -> str:
        return self.chain.invoke({"text": text})
