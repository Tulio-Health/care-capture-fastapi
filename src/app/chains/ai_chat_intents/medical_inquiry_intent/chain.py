import logging
from langchain.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
import json

from src.app.common.llm_factory import get_default_chat_model
from src.app.core.langsmith_trace import LangSmithTrace
from src.app.models.intent_identify import MedicalIntentResponse, MedicalIntentAiResponse
from src.app.chains.ai_chat_intents.intend_identifier.models import RouterOptions
from src.app.chains.ai_chat_intents.medical_inquiry_intent.constants import (
    MEDICAL_INQUIRY_SYSTEM_PROMPT,
    MEDICAL_INQUIRY_USER_PROMPT
)

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

logger = logging.getLogger(__name__)


class MedicalInquiryIntentChain:
    def __init__(self):
        # Initialize components except model
        self._model = None
        # Use StrOutputParser for natural text responses like past visit chain
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", MEDICAL_INQUIRY_SYSTEM_PROMPT),
            ("user", MEDICAL_INQUIRY_USER_PROMPT)
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
            self._chain = self.prompt | self.model | StrOutputParser()
        return self._chain

    async def handle_intent(self, **kwargs) -> MedicalIntentResponse[None]:
        try:
            text = kwargs['text']
            context = kwargs.get('context', {})
            
            # Extract user profile and conversation history from context
            user_profile = context.get('user_profile', {})
            # Use 'conversation_messages' key for consistency with ai_chat.py
            chat_history = context.get('conversation_messages', [])
            # Get health insights directly from context instead of fetching from cache
            health_insights = context.get('health_insights', [])
            
            # Format context data for prompt
            try:
                user_profile_str = self._format_user_profile(user_profile)
                health_insights_str = self._format_health_insights(health_insights)
            except Exception as e:
                logger.error(f"Error formatting user profile or health insights: {str(e)}. Still processing the request with no context.")
                user_profile_str = "No user profile available"
                health_insights_str = "No health insights available"
            
            # Generate natural text response
            ai_content_string = await self.chain.ainvoke({
                "text": text, 
                "user_profile": user_profile_str,
                "health_insights": health_insights_str,
                "conversation_history": json.dumps(chat_history, default=str)
            }, config={"callbacks": get_callbacks()})
            
            # Parse the response to extract content and citations
            content, citations = self._parse_medical_response(ai_content_string)
            
            # Apply citation guardrail
            if not self._validate_citations(citations):
                logger.warning(f"Medical response missing proper citations. Returning standard message. Citations: {citations}")
                return self._get_standard_medical_response()
            
            # Add disclaimer
            content += "\n*This information is for educational purposes and not a substitute for professional medical advice. Consult a healthcare provider for guidance."
            
            # Return the response in the expected format with citations
            return MedicalIntentResponse[None](
                intent=RouterOptions.MEDICAL_INQUIRY,
                responses=[MedicalIntentAiResponse(
                    type="text", 
                    content=content, 
                    citation=citations,
                    data=None
                )]
            )
            
        except Exception as e:
            logger.error(f"Error processing medical inquiry: {str(e)}")
            return self._get_standard_medical_response()

    def _format_user_profile(self, profile: dict) -> str:
        """Format user profile for prompt context"""
        if not profile:
            return "No user profile available"
        
        formatted = []
        if profile.get('name'):
            formatted.append(f"Name: {profile['name']}")
        if profile.get('dob'):
            formatted.append(f"Date of Birth: {profile['dob']}")
        if profile.get('language'):
            formatted.append(f"Preferred Language: {profile['language']}")
        
        return "; ".join(formatted) if formatted else "Limited profile information available"

    def _format_health_insights(self, insights: list) -> str:
        """Format health insights for prompt context"""
        if not insights:
            return "No health insights available"
        
        formatted_insights = []
        for insight in insights:
            insight_data = insight.get('insight_data', {})
            if isinstance(insight_data, dict):
                # Extract comprehensive information from insight data
                conditions = insight_data.get('conditions', [])
                medications = insight_data.get('medications', [])
                prior_testing = insight_data.get('priorTesting', [])
                surgeries = insight_data.get('surgeriesAndProcedures', [])
                
                insight_summary = []
                
                # Format conditions with details
                if conditions:
                    condition_details = []
                    for c in conditions[:5]:  # Limit to 5 most recent
                        if c.get('name'):
                            detail = c['name']
                            if c.get('details'):
                                detail += f" ({c['details']})"
                            condition_details.append(detail)
                    if condition_details:
                        insight_summary.append(f"Conditions: {', '.join(condition_details)}")
                
                # Format medications with dosage
                if medications:
                    med_details = []
                    for m in medications[:5]:  # Limit to 5 most recent
                        if m.get('name'):
                            detail = m['name']
                            if m.get('dosage'):
                                detail += f" {m['dosage']}"
                            if m.get('frequency'):
                                detail += f" {m['frequency']}"
                            med_details.append(detail)
                    if med_details:
                        insight_summary.append(f"Medications: {', '.join(med_details)}")
                
                # Format prior testing
                if prior_testing:
                    test_names = [t.get('name', '') for t in prior_testing[:3] if t.get('name')]
                    if test_names:
                        insight_summary.append(f"Recent Testing: {', '.join(test_names)}")
                
                # Format surgeries/procedures
                if surgeries:
                    surgery_names = [s.get('name', '') for s in surgeries[:3] if s.get('name')]
                    if surgery_names:
                        insight_summary.append(f"Procedures: {', '.join(surgery_names)}")
                
                if insight_summary:
                    formatted_insights.append("; ".join(insight_summary))
        
        return "; ".join(formatted_insights) if formatted_insights else "No specific health insights available"

    def _parse_medical_response(self, response: str) -> tuple[str, str]:
        """
        Parse the LLM response to extract content and citations.
        
        Args:
            response: The raw response from the LLM
            
        Returns:
            tuple: (content, citations) where content is the medical response and citations is the citation string
        """
        try:
            # Split the response by lines to look for RESPONSE and CITATIONS sections
            lines = response.strip().split('\n')
            content_lines = []
            citations = None
            
            in_response_section = False
            in_citations_section = False
            
            for line in lines:
                line = line.strip()
                
                if line.startswith('RESPONSE:'):
                    in_response_section = True
                    in_citations_section = False
                    # Remove the "RESPONSE:" prefix and add the content
                    content_part = line[9:].strip()
                    if content_part:
                        content_lines.append(content_part)
                    continue
                    
                elif line.startswith('CITATIONS:'):
                    in_response_section = False
                    in_citations_section = True
                    # Extract citations
                    citations = line[10:].strip()
                    continue
                    
                elif in_response_section and line:
                    content_lines.append(line)
                    
                elif in_citations_section and line:
                    # Append additional citation lines
                    if citations:
                        citations += "; " + line
                    else:
                        citations = line
            
            # If no structured format found, treat the entire response as content
            if not content_lines:
                content_lines = [response]
            
            content = '\n'.join(content_lines).strip()
            
            # Return empty citations if none found - let the guardrail handle it
            if not citations:
                citations = ""
            
            return content, citations
            
        except Exception as e:
            logger.error(f"Error parsing medical response: {str(e)}")
            # Return empty citations on error - let the guardrail handle it
            return response, ""

    def _validate_citations(self, citations: str) -> bool:
        """
        Validate that citations meet the required standards.
        
        Args:
            citations: The citation string to validate
            
        Returns:
            bool: True if citations are valid, False otherwise
        """
        if not citations or citations.strip() == "":
            return False
        
        # Check if it's just the default fallback citation
        if citations == "Source: General medical knowledge from peer-reviewed sources":
            return False
        
        # Check if citations contain actual source information
        # Look for common medical source indicators
        medical_source_indicators = [
            "american heart association", "aha", "mayo clinic", "who", "cdc", 
            "nih", "fda", "medical journal", "peer-reviewed", "clinical study",
            "research", "medical association", "health organization", "medical center",
            "university", "hospital", "medical school", "health.gov", "medlineplus",
            "pubmed", "ncbi", "medical literature", "clinical guidelines"
        ]
        
        citations_lower = citations.lower()
        
        # Check if citations contain at least one medical source indicator
        has_medical_source = any(indicator in citations_lower for indicator in medical_source_indicators)
        
        # Check if citations contain a URL or reference format
        has_url_or_reference = any(char in citations for char in ["http", "www", ".org", ".gov", ".edu", ".com"])
        
        # Citations are valid if they have either a medical source indicator or a URL/reference
        return has_medical_source or has_url_or_reference

    def _get_standard_medical_response(self) -> MedicalIntentResponse[None]:
        """
        Return a standard medical response when citations are missing or invalid.
        
        Returns:
            MedicalIntentResponse: Standard response with proper citations
        """
        standard_content = (
            "I understand you're asking about medical information. For accurate and up-to-date medical advice, "
            "I recommend consulting with your healthcare provider or a qualified medical professional. "
            "They can provide personalized guidance based on your specific health situation and medical history."
        )
        
        standard_citation = (
            "Source: General medical consultation guidelines - American Medical Association; "
            "Source: Patient education standards - Centers for Disease Control and Prevention"
        )
        
        return MedicalIntentResponse[None](
            intent=RouterOptions.MEDICAL_INQUIRY,
            responses=[MedicalIntentAiResponse(
                type="text",
                content=standard_content,
                citation=standard_citation,
                data=None
            )]
        )