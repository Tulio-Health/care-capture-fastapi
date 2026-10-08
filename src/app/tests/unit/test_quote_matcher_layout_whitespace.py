"""Layout-artifact tolerance of the quote matcher + inline-aware HTML text extraction.

HTML inline spans used to be emitted on their own lines, so the source read
"tacrolimus , mycophenolate" while the model quotes "tacrolimus, mycophenolate".
Fix = parser keeps inline runs on one line AND the matcher drops whitespace before , . ; : ) %
(and after "(") on both sides. Wrong dose/date/name/negation/truncation must still fail closed.
"""

import pytest

from src.app.chains.procedure_extraction.chain import _normalize_quote, _quote_supported
from src.app.services.document_extraction import DocumentTextExtractor

HTML = (
    "<html><body><h2>Medications</h2><ul>"
    "<li><strong>Tacrolimus</strong> 2 mg <em>BID</em> , <strong>mycophenolate</strong> 750 mg BID</li>"
    "<li>Warfarin ( <b>INR</b> goal 2-3 ) held on <span>08/13/2024</span> ; resume later</li>"
    "</ul><p>No chest pain.<br>No <i>syncope</i>.</p><div>Plan</div><table><tr><td>HDL</td><td>45 mg/dL</td></tr></table>"
    "</body></html>"
)


def _extract(html: str = HTML) -> str:
    return DocumentTextExtractor().extract_text(html.encode(), "text/html", "n.html")


def test_html_inline_elements_do_not_break_lines_or_leave_space_before_punct():
    text = _extract()
    lines = text.split("\n")
    assert (
        "Tacrolimus 2 mg BID , mycophenolate 750 mg BID" in lines
    )  # no per-span line breaks
    assert "Warfarin ( INR goal 2-3 ) held on 08/13/2024 ; resume later" in lines
    assert "No chest pain." in lines and "No syncope." in lines  # <br> keeps its break


def test_html_block_breaks_preserved():
    lines = _extract().split("\n")
    for expected in ("Medications", "Plan", "HDL", "45 mg/dL"):
        assert expected in lines
    assert lines.index("Medications") < lines.index("Plan")


def test_html_inline_adjacent_text_is_not_split():
    assert (
        _extract("<p>wound<span>, selective</span> debridement</p>")
        == "wound, selective debridement"
    )


def test_html_extraction_stable_and_hidden_still_skipped():
    assert _extract() == _extract()
    assert "secret" not in _extract(
        "<p>a</p><span style='display:none'>secret</span><p>b</p>"
    )


SOURCE = _normalize_quote(_extract())
RAW_SOURCE = _extract()


@pytest.mark.parametrize(
    "quote",
    [
        "Tacrolimus 2 mg BID, mycophenolate 750 mg BID",
        "Warfarin (INR goal 2-3) held on 08/13/2024; resume later",
        "tacrolimus 2 mg bid , mycophenolate 750 mg bid",
    ],
)
def test_punctuation_spacing_quotes_now_supported(quote):
    assert _quote_supported(quote, RAW_SOURCE) is True
    # also against the OLD-layout source (one fragment per line)
    old_layout = "Tacrolimus\n2 mg\nBID\n,\nmycophenolate\n750 mg BID\nWarfarin\n(\nINR\ngoal 2-3\n)\nheld on\n08/13/2024\n;\nresume later"
    assert _quote_supported(quote, old_layout) is True


@pytest.mark.parametrize(
    "name,quote",
    [
        ("wrong dose 10x", "Tacrolimus 20 mg BID, mycophenolate 750 mg BID"),
        ("wrong dose 750->7500", "Tacrolimus 2 mg BID, mycophenolate 7500 mg BID"),
        ("wrong date", "Warfarin (INR goal 2-3) held on 08/18/2024; resume later"),
        (
            "negation flip",
            "Warfarin (INR goal 2-3) not held on 08/13/2024; resume later",
        ),
        ("wrong drug", "Amiodarone 2 mg BID, mycophenolate 750 mg"),
        ("truncated number", "Tacrolimus 2 mg BID, mycophenolate 75 mg BID"),
        (
            "INR goal changed",
            "Warfarin (INR goal 3-4) held on 08/13/2024; resume later",
        ),
        (
            "fabricated",
            "Coronary artery bypass grafting was performed without complication.",
        ),
    ],
)
def test_wrong_claims_still_fail_closed(name, quote):
    assert _quote_supported(quote, RAW_SOURCE) is False, name


def test_normalize_quote_only_touches_spaces_next_to_punctuation():
    assert _normalize_quote("a , b ; c ( d ) 5 %") == "a, b; c (d) 5%"
    assert _normalize_quote("10 mg") != _normalize_quote("100 mg")
    assert _normalize_quote("no x") != _normalize_quote("x")
