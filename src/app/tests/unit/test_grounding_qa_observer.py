"""Fix 3 (round9-revision3.md Sec 3.5.1): tests for the QA-observer hooks used by
scripts/grounding_rerun.py, and -- the mandatory coverage regardless of H1/H2 outcome -- the
prod-impossible safety gate that guards enabling them.

Three things must always hold:
  1. With no observer registered (every normal process, including prod), the hooks are
     inert -- raising/returning verdicts exactly as before, no behavior change, no crash.
  2. When registered, the hooks fire with the right (source, candidate/quote, verdict) data.
  3. scripts/grounding_rerun.require_qa_observer_enabled() refuses to enable the hook unless
     BOTH QA_OBSERVER=1 is set AND the loaded Settings object's APP_ENV != "production" --
     and (3) is the hard gate: a stray QA_OBSERVER=1 in a prod environment must still refuse.
"""

from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, patch

import pytest

from src.app.services import clinical_grounding
from src.app.services.clinical_grounding import GroundingVerdict, validate_quotes, validate_single_subject, verify_grounding
from src.app.services.document_extraction import DocumentProcessingError
from src.app.chains.procedure_extraction import chain as procedure_chain


@pytest.fixture(autouse=True)
def _reset_observers():
    """Every test starts and ends with both observers unregistered -- a test that forgets to
    detach its own observer must not leak into the next test (or into a real request if these
    modules stay imported in-process)."""
    clinical_grounding.register_qa_observer(None)
    procedure_chain.register_qa_observer(None)
    yield
    clinical_grounding.register_qa_observer(None)
    procedure_chain.register_qa_observer(None)


# --------------------------------------------------------------------- inert-by-default


def test_quote_supported_unaffected_with_no_observer_registered():
    """Default state (every normal process, including prod): no observer, no behavior change."""
    assert procedure_chain._quote_supported("aspirin 81 mg daily", "aspirin 81 mg daily") is True
    assert procedure_chain._quote_supported("fully fabricated claim", "unrelated text") is False


def test_validate_single_subject_unaffected_with_no_observer_registered():
    validate_single_subject("Patient: Jane Doe\nNote text.")  # must not raise
    with pytest.raises(DocumentProcessingError):
        validate_single_subject("Patient: Jane Doe\n...\nPatient: John Smith\n...")


@pytest.mark.asyncio
async def test_verify_grounding_unaffected_with_no_observer_registered():
    run = AsyncMock(return_value=NS(output=GroundingVerdict(supported=False, issues=["x"])))
    with patch("src.app.core.settings.get_settings", return_value=NS(DOCUMENT_VERIFICATION_MODEL="mock")), \
         patch("src.app.common.llm_factory.get_pydantic_ai_model", return_value=object()), \
         patch("pydantic_ai.Agent", return_value=NS(run=run)):
        with pytest.raises(DocumentProcessingError):
            await verify_grounding(None, "source text", {"a": "b"})


# ----------------------------------------------------------------------- hooks fire correctly


def test_quote_supported_observer_fires_with_quote_source_verdict_threshold():
    captured = []
    procedure_chain.register_qa_observer(lambda *a: captured.append(a))
    procedure_chain._quote_supported("aspirin 81 mg daily", "aspirin 81 mg daily")
    assert len(captured) == 1
    quote, source, supported, threshold = captured[0]
    assert quote == "aspirin 81 mg daily"
    assert source == "aspirin 81 mg daily"
    assert supported is True
    assert threshold == 0.85


def test_validate_single_subject_observer_fires_only_on_reject():
    captured = []
    clinical_grounding.register_qa_observer(lambda **kw: captured.append(kw))
    validate_single_subject("Patient: Jane Doe\nSingle patient note.")
    assert captured == []  # single-subject: no raise, no observer call
    with pytest.raises(DocumentProcessingError):
        validate_single_subject("Patient: Jane Doe\n...\nPatient: John Smith\n...")
    assert len(captured) == 1
    assert captured[0]["event"] == "multi_patient_subject"
    assert captured[0]["supported"] is False


@pytest.mark.asyncio
async def test_verify_grounding_observer_fires_with_source_payload_issues():
    captured = []
    clinical_grounding.register_qa_observer(lambda **kw: captured.append(kw))
    run = AsyncMock(return_value=NS(output=GroundingVerdict(supported=False, issues=["not grounded"])))
    with patch("src.app.core.settings.get_settings", return_value=NS(DOCUMENT_VERIFICATION_MODEL="mock")), \
         patch("src.app.common.llm_factory.get_pydantic_ai_model", return_value=object()), \
         patch("pydantic_ai.Agent", return_value=NS(run=run)):
        with pytest.raises(DocumentProcessingError):
            await verify_grounding(None, "the source text", {"diagnoses": ["x"]})
    assert len(captured) == 1
    assert captured[0]["event"] == "grounding_validation_failed"
    assert captured[0]["source"] == "the source text"
    assert captured[0]["issues"] == ["not grounded"]
    assert captured[0]["supported"] is False


def test_observer_exception_is_swallowed_and_never_blocks_the_real_raise():
    """A broken observer callback must never break production behavior -- it is a side
    channel, not a dependency."""
    procedure_chain.register_qa_observer(lambda *a: (_ for _ in ()).throw(RuntimeError("boom")))
    assert procedure_chain._quote_supported("x", "x") is True  # does not raise RuntimeError

    clinical_grounding.register_qa_observer(lambda **kw: (_ for _ in ()).throw(RuntimeError("boom")))
    with pytest.raises(DocumentProcessingError):  # DocumentProcessingError, not RuntimeError
        validate_single_subject("Patient: A\n...\nPatient: B\n...")


def test_validate_quotes_invalid_source_evidence_is_observed_via_quote_supported():
    """validate_quotes itself has no separate hook -- it rides entirely on
    _quote_supported's hook (clinical_grounding.py's docstring / grounding_rerun.py's design:
    hooking the shared primitive covers every call site, including this one, for free)."""
    captured = []
    procedure_chain.register_qa_observer(lambda *a: captured.append(a))
    with pytest.raises(DocumentProcessingError) as excinfo:
        validate_quotes(["entirely fabricated quote text"], "completely unrelated source")
    assert excinfo.value.reason_code == "INVALID_SOURCE_EVIDENCE"
    assert len(captured) == 1
    assert captured[0][2] is False  # supported=False


# ------------------------------------------------------------ prod-impossible safety gate


def _load_require_qa_observer_enabled():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "grounding_rerun", "scripts/grounding_rerun.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.require_qa_observer_enabled


def test_qa_observer_refuses_without_env_var(monkeypatch):
    require_qa_observer_enabled = _load_require_qa_observer_enabled()
    monkeypatch.delenv("QA_OBSERVER", raising=False)
    with pytest.raises(SystemExit):
        require_qa_observer_enabled()


def test_qa_observer_refuses_in_production_even_with_env_var_set(monkeypatch):
    """THE critical case: QA_OBSERVER=1 set (e.g. by mistake in a prod environment) must
    still refuse, because the gate asserts on the Settings object's APP_ENV, not the env var."""
    require_qa_observer_enabled = _load_require_qa_observer_enabled()
    monkeypatch.setenv("QA_OBSERVER", "1")
    with patch("src.app.core.settings.get_settings", return_value=NS(APP_ENV="production")):
        with pytest.raises(SystemExit):
            require_qa_observer_enabled()


def test_qa_observer_passes_in_development_with_env_var_set(monkeypatch):
    require_qa_observer_enabled = _load_require_qa_observer_enabled()
    monkeypatch.setenv("QA_OBSERVER", "1")
    with patch("src.app.core.settings.get_settings", return_value=NS(APP_ENV="development")):
        require_qa_observer_enabled()  # must not raise
