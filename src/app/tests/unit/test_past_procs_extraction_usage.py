"""Past-procedure key point collapse (Fix B), extraction usage log (C), history-procedure prompt rule (E)."""

from src.app.chains.attachment_summarization.chain import (
    _collapse_past_procedures,
    _split_procedures,
)
from src.app.models.attachment_summarization import DocumentSummary, ProcedureMention


def test_collapse_zero_single_many_and_cap():
    assert _collapse_past_procedures([]) == []
    assert _collapse_past_procedures(["Appendectomy 1999"]) == [
        "Past procedures (status not stated): Appendectomy 1999"
    ]
    out = _collapse_past_procedures([f"Proc {i} (2000)" for i in range(20)] + ["Proc 0 (2000)"])
    assert len(out) == 1
    assert out[0].startswith("Past procedures (status not stated): Proc 0 (2000); Proc 1")
    assert "Proc 14 (2000)" in out[0] and "Proc 15" not in out[0]
    assert out[0].endswith("; and 5 more")


def test_collapse_leaves_ordered_and_performed_untouched():
    s = DocumentSummary(
        source_document_id="d", evidence_quotes=["q"], source_document_title="t",
        source_document_type="n", narrative_summary="n",
        procedures=[
            ProcedureMention(description="Colonoscopy", status="ordered", source_quote="order colonoscopy", source_section="Plan"),
            ProcedureMention(description="Biopsy", status="performed", source_quote="biopsy done", source_section="Procedure"),
            ProcedureMention(description="Appendectomy", status="not_stated", source_quote="Appendectomy 1999", source_section="Surgical History"),
        ],
    )
    rec = _split_procedures([s])[0]
    assert rec["procedures_ordered"] == ["order colonoscopy"]
    assert rec["procedures_performed"] == ["Biopsy"]
    assert _collapse_past_procedures(rec["procedures_not_stated"]) == [
        "Past procedures (status not stated): Appendectomy 1999"
    ]


# ---- extraction usage logging / prompt rule / token limit ----
import logging
from types import SimpleNamespace

from src.app.chains.attachment_summarization import chain as chain_mod


def _res(out_tokens, finish):
    return SimpleNamespace(
        usage=lambda: SimpleNamespace(input_tokens=100, output_tokens=out_tokens),
        all_messages=lambda: [SimpleNamespace(finish_reason=finish)],
    )


def test_extraction_usage_logged(caplog):
    with caplog.at_level(logging.INFO, logger=chain_mod.logger.name):
        chain_mod._log_extraction_usage(_res(1234, "stop"), 1, 2)
    rec = [r for r in caplog.records if "extraction_usage" in r.getMessage()]
    assert rec and rec[0].levelno == logging.INFO
    assert "output_tokens=1234" in rec[0].getMessage() and "finish_reason=stop" in rec[0].getMessage()


def test_extraction_truncation_warns(caplog):
    with caplog.at_level(logging.INFO, logger=chain_mod.logger.name):
        chain_mod._log_extraction_usage(_res(8192, "length"), 1, 1)
    rec = [r for r in caplog.records if "extraction_usage" in r.getMessage()]
    assert rec[0].levelno == logging.WARNING and "EXTRACTION_OUTPUT_TRUNCATED" in rec[0].getMessage()


def test_extraction_usage_never_raises():
    chain_mod._log_extraction_usage(object(), 1, 1)


def test_extraction_prompt_history_rule_and_limit():
    p = chain_mod._EXTRACTION_SYSTEM_PROMPT
    assert "HISTORICAL history context, NOT procedures to extract" in p
    assert "Extract only procedures that are ordered/recommended or performed" in p
    assert chain_mod._EXTRACTION_MAX_TOKENS == 4096  # 8192 tried and dropped (slower)
