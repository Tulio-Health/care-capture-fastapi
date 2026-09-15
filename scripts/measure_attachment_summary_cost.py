#!/usr/bin/env python3
"""Operator entry point for PR-3a's windowing/follow_up change -- the wall-time/batch-size
measurement Check 3(g) makes in CI when OPENAI_API_KEY is present. Read-only apart from the
summary row `analyze_attachments` writes on dev.

Runs one real AttachmentSummarizationService.analyze_attachments call for an appointment and
prints wall time, batch count, and prompt chars per batch (computed from the same
_create_batches/_format_batch_prompt the real run uses, so the windowing behavior is measured
exactly, not approximated).

Usage:
    uv run python scripts/measure_attachment_summary_cost.py <appointment_id> <user_id>
"""

import argparse
import asyncio
import os
import time
from uuid import UUID

from src.app.chains.attachment_summarization.chain import (
    _create_batches,
    _format_batch_prompt,
)
from src.app.db.config.database import get_session_factory
from src.app.models.attachment_summarization import AttachmentSummarizationRequest
from src.app.services.summarization.attachment_summarization import (
    AttachmentSummarizationService,
)


def _require_llm_credentials() -> None:
    """Same @requires_llm gate the test suite uses, as a hard exit for a standalone script."""
    if os.environ.get("OPENAI_API_KEY"):
        return
    try:
        from src.app.core.settings import get_settings

        if get_settings().OPENAI_API_KEY:
            return
    except Exception:
        pass
    raise SystemExit("No OPENAI_API_KEY configured in this environment.")


async def main(appointment_id: UUID, user_id: UUID) -> None:
    _require_llm_credentials()
    async with get_session_factory()() as db:
        service = AttachmentSummarizationService(db)
        request = AttachmentSummarizationRequest(
            appointment_id=appointment_id, user_id=user_id
        )

        appointment, provider_name = await service._fetch_appointment_details(request)
        doc_refs = await service._fetch_document_references(request, appointment)
        documents = await service._process_attachments(doc_refs)
        batches = _create_batches(documents)
        for i, batch in enumerate(batches, 1):
            chars = len(_format_batch_prompt(batch, i, len(batches)))
            print(
                f"batch {i}/{len(batches)}: {len(batch)} doc(s), {chars} prompt chars"
            )

        started = time.monotonic()
        summary = await service.analyze_attachments(request)
        elapsed = time.monotonic() - started
        print(
            f"wall_time_s={elapsed:.2f} batches={len(batches)} summary_id={summary.id}"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("appointment_id", type=UUID)
    parser.add_argument("user_id", type=UUID)
    args = parser.parse_args()
    asyncio.run(main(args.appointment_id, args.user_id))
