"""Playground Attachment Summarization Service — stateless, no DB storage."""

from typing import List
from uuid import uuid4

from src.app.chains.attachment_summarization.chain import (
    AttachmentSummarizationChain,
    _EXTRACTION_SYSTEM_PROMPT,
    _SYNTHESIS_SYSTEM_PROMPT,
)
from src.app.common.logging import get_logger
from src.app.models.attachment_summarization import DocumentAttachment
from src.app.models.playground_attachment_summarization import (
    PlaygroundAttachmentRequest,
    PlaygroundAttachmentResponse,
)

logger = get_logger(__name__)


class PlaygroundAttachmentSummarizationService:
    """
    Stateless service for the attachment summarization playground.

    Delegates to the production AttachmentSummarizationChain with an optional
    synthesis system prompt override. Accepts pre-built DocumentAttachment objects
    so the route can provide per-file structure for uploads.
    """

    async def summarize(
        self,
        request: PlaygroundAttachmentRequest,
        documents: List[DocumentAttachment],
    ) -> PlaygroundAttachmentResponse:
        """
        Run attachment summarization via the production chain.

        Args:
            request: Playground request with optional synthesis prompt override
                     and appointment context fields.
            documents: Pre-built list of DocumentAttachment objects (one per file
                       for uploads, one from pasted text for paste mode).

        Returns:
            PlaygroundAttachmentResponse with structured data and effective prompts.

        Raises:
            ValueError: If no valid documents are provided.
            Exception: If the chain fails.
        """
        logger.info("Playground attachment summarization started")

        extraction_prompt = request.extraction_system_prompt or _EXTRACTION_SYSTEM_PROMPT
        synthesis_prompt = request.synthesis_system_prompt or _SYNTHESIS_SYSTEM_PROMPT
        chain = AttachmentSummarizationChain(
            extraction_system_prompt=extraction_prompt,
            synthesis_system_prompt=synthesis_prompt,
        )

        appointment_context = {
            "appointment_date": request.appointment_date,
            "purpose": request.appointment_purpose,
            "provider_name": request.provider_name,
        }

        result = await chain.analyze(appointment_context, documents)

        response = PlaygroundAttachmentResponse(
            request_id=uuid4(),
            data=result,
            prompts_used={
                "extraction_system_prompt": extraction_prompt,
                "synthesis_system_prompt": synthesis_prompt,
            },
        )

        logger.info(
            "Playground attachment summarization completed - request_id: %s",
            response.request_id,
        )
        return response
