"""
This module defines the core data models and enums used by the intent identification system.

The models include:
- AgentState: A TypedDict representing the state of the conversation
- RouterOptions: An Enum defining the possible intent categories
"""

from typing import Annotated, Sequence, TypedDict
import operator
from enum import Enum

from langchain_core.messages import BaseMessage

# Define our state
class AgentState(TypedDict):
    """
    Represents the state of a conversation agent.
    
    Attributes:
        messages: A sequence of BaseMessage objects representing the conversation history
        next: A string indicating the next action or state
    """
    messages: Annotated[Sequence[BaseMessage], operator.add]
    next: str

# Define router options as an enum
class RouterOptions(str, Enum):
    """
    Enum defining the possible intent categories for message routing.
    
    Options:
        PAST_VISITS: For past visits inquiries
        HEALTH_INSIGHTS: For health insights inquiries
        UPCOMING_VISITS: For upcoming visits inquiries
        MANAGE_VISITS: For managing visits (create, cancel, reschedule, etc.)
        NOT_A_VALID_OPTION: For invalid queries options
        END: For conversation termination
    """
    PAST_VISITS = "past_visits"
    HEALTH_INSIGHTS = "health_insights"
    UPCOMING_VISITS = "upcoming_visits"
    MANAGE_VISITS = "manage_visits" # create, cancel, reschedule, etc.
    NOT_A_VALID_OPTION = "not_a_valid_option"
    END_CONVERSATION = "end_conversation"
    MEDICAL_INQUIRY = "medical_inquiry"

      