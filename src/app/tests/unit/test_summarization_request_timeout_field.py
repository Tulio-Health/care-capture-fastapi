"""AttachmentSummarizationRequest/ProcedureSummarizationRequest previously had no
`timeout_seconds` field, so a caller-supplied value was silently dropped by Pydantic
(no `extra="forbid"` on either model) and `bounded_summary`'s
`getattr(request, "timeout_seconds", 120)` always fell back to 120s regardless of
what nodeapi sent. This adds the field, matching ComprehensiveSummarizationRequest's
existing pattern exactly, so a caller-supplied deadline is now actually honoured.
"""
from uuid import uuid4

from src.app.models.attachment_summarization import AttachmentSummarizationRequest
from src.app.models.procedure_summarization import ProcedureSummarizationRequest


class TestAttachmentSummarizationRequestTimeoutField:
    def test_defaults_to_120_when_omitted(self):
        request = AttachmentSummarizationRequest(appointment_id=uuid4(), user_id=uuid4())
        assert request.timeout_seconds == 120

    def test_accepts_a_caller_supplied_value(self):
        request = AttachmentSummarizationRequest(appointment_id=uuid4(), user_id=uuid4(), timeout_seconds=100)
        assert request.timeout_seconds == 100

    def test_bounded_summary_reads_the_caller_supplied_value_via_getattr(self):
        # Mirrors summary_runtime.bounded_summary's own lookup exactly -- this is the
        # actual mechanism that was silently ineffective before this field existed.
        request = AttachmentSummarizationRequest(appointment_id=uuid4(), user_id=uuid4(), timeout_seconds=100)
        assert min(getattr(request, "timeout_seconds", 120), 300) == 100

    def test_rejects_a_value_outside_the_10_to_300_bound(self):
        import pytest
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            AttachmentSummarizationRequest(appointment_id=uuid4(), user_id=uuid4(), timeout_seconds=5)
        with pytest.raises(ValidationError):
            AttachmentSummarizationRequest(appointment_id=uuid4(), user_id=uuid4(), timeout_seconds=301)


class TestProcedureSummarizationRequestTimeoutField:
    def test_defaults_to_120_when_omitted(self):
        request = ProcedureSummarizationRequest(appointment_id=uuid4(), user_id=uuid4())
        assert request.timeout_seconds == 120

    def test_accepts_a_caller_supplied_value(self):
        request = ProcedureSummarizationRequest(appointment_id=uuid4(), user_id=uuid4(), timeout_seconds=100)
        assert request.timeout_seconds == 100

    def test_bounded_summary_reads_the_caller_supplied_value_via_getattr(self):
        request = ProcedureSummarizationRequest(appointment_id=uuid4(), user_id=uuid4(), timeout_seconds=100)
        assert min(getattr(request, "timeout_seconds", 120), 300) == 100
