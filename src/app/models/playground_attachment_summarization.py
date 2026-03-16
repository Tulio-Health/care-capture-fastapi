"""Pydantic models for the attachment summarization playground."""

from typing import Dict, Optional
from uuid import UUID

from pydantic import BaseModel

from src.app.models.attachment_summarization import AttachmentSummarizationResponse


class PlaygroundAttachmentRequest(BaseModel):
    extraction_system_prompt: Optional[str] = None  # optional override for extraction system prompt
    synthesis_system_prompt: Optional[str] = None  # optional override for synthesis system prompt
    appointment_date: str = "N/A"
    appointment_purpose: str = "N/A"
    provider_name: str = "N/A"


class PlaygroundAttachmentResponse(BaseModel):
    request_id: UUID
    data: AttachmentSummarizationResponse
    prompts_used: Dict[str, str]  # echoes back the effective extraction + synthesis prompts
