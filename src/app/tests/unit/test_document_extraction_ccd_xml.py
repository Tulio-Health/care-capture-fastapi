"""CDA/CCD <text> narrative rendering in DocumentTextExtractor._xml_text.

Fix A from care-capture-nodeapi's
.claude/debug-reports/2026-09-16-summaryenhancement-fix-plan/pr12-research/
topic-A-ccd-xml-and-validate-quotes.md (PR-12a): a real production CCD
extracted 503,489 chars of which only 6.9% was clinical content - the rest
was XPath-scaffold lines (`ClinicalDocument/.../tr: styleCode=xRowNormal`)
that shattered table row adjacency, making even a correct model-produced
quote like "Blood Pressure: 124/73" unverifiable (2-char longest contiguous
match against the source text).

These tests cover the two structurally different CDA narrative shapes and
the regression this fix must not reintroduce: <table><tr><td> rows must join
onto one quotable line, but <list><item> blocks (used for medication
narratives - frequently one <br/>-separated <item>, as in the real
production document these fixtures mirror) must NOT be row-joined, or every
medication collapses onto one unreadable, unquotable line.
"""

import re
import xml.etree.ElementTree as ET

from src.app.services.document_extraction import DocumentTextExtractor


def _section(body: str) -> str:
    return f"<component><section>{body}</section></component>"


def _document(*sections: str) -> bytes:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<ClinicalDocument xmlns="urn:hl7-org:v3">'
        "<component><structuredBody>"
        + "".join(sections)
        + "</structuredBody></component>"
        "</ClinicalDocument>"
    ).encode()


# Mirrors the real Ricardo Febry production CCD vitals table shape (nested
# <content> split systolic/diastolic, styleCode/ID plumbing on <tr>/<td>).
VITALS_SECTION = _section(
    '<code code="8716-3" codeSystem="2.16.840.1.113883.6.1" codeSystemName="LOINC" displayName="Vital signs"/>'
    "<title>Last Filed Vital Signs</title>"
    "<text><table>"
    '<colgroup><col width="25%" span="4"/></colgroup>'
    "<thead><tr><th>Vital Sign</th><th>Reading</th><th>Time Taken</th></tr></thead>"
    "<tbody>"
    '<tr styleCode="xRowNormal">'
    '<td styleCode="xcellHeader">Blood Pressure</td>'
    '<td><content ID="sysBP_1">124</content>/<content ID="diaBP_1">73</content></td>'
    "<td>04/11/2024 10:31 AM CDT</td></tr>"
    '<tr ID="pulse_1" styleCode="xRowAlt">'
    '<td styleCode="xcellHeader">Pulse</td><td>73</td>'
    "<td>04/11/2024 10:31 AM CDT</td></tr>"
    '<tr styleCode="xRowNormal">'
    '<td styleCode="xcellHeader">Weight</td>'
    "<td>122.8 kg (270 lb 11.2 oz)</td>"
    "<td>04/11/2024 10:31 AM CDT</td></tr>"
    "</tbody></table></text>"
)

# Mirrors the real production shape exactly: <list><item> wrapping a single
# <br/>-separated <content> narrative block, not one <item> per medication.
MEDICATION_SECTION = _section(
    "<title>Plan of Care</title>"
    "<text>"
    '<list styleCode="xTOC"><item><caption>Robert Greer, MD - 04/11/2024</caption>'
    '<content ID="Note1"><content>'
    "Home Medications: <br/>"
    "Current Outpatient Medications <br/>"
    "Medication Instructions <br/>"
    " aspirin 81 mg Cap 81 each, Oral, Daily <br/>"
    " atorvastatin (LIPITOR) 20 mg, Oral, Daily <br/>"
    " metFORMIN (GLUCOPHAGE) 750 mg, Oral, Daily <br/>"
    " OZEMPIC 0.5 mg, Subcutaneous, Every 7 Days <br/>"
    " tamsulosin (FLOMAX) 0.4 mg, Oral, Nightly <br/>"
    " valsartan (DIOVAN) 160 mg, Oral, 2 times daily <br/>"
    "</content></content></item></list>"
    "</text>"
)

VITALS_TABLE_XML = _document(VITALS_SECTION)
MEDICATION_LIST_XML = _document(MEDICATION_SECTION)
MIXED_XML = _document(VITALS_SECTION, MEDICATION_SECTION)

MEDICATIONS = [
    "aspirin 81 mg Cap 81 each, Oral, Daily",
    "atorvastatin (LIPITOR) 20 mg, Oral, Daily",
    "metFORMIN (GLUCOPHAGE) 750 mg, Oral, Daily",
    "OZEMPIC 0.5 mg, Subcutaneous, Every 7 Days",
    "tamsulosin (FLOMAX) 0.4 mg, Oral, Nightly",
    "valsartan (DIOVAN) 160 mg, Oral, 2 times daily",
]


def _old_xml_text_render(content: bytes) -> str:
    """Byte-for-byte replica of the OLD (pre-PR-12a) _xml_text walk - one
    line per text node plus one XPath-scaffold line per attributed element,
    no row adjacency. Kept only to measure the before/after noise-ratio
    delta in a test; the production algorithm is now
    DocumentTextExtractor._cda_narrative / _cda_inline."""
    root = ET.fromstring(content)
    parts = []

    def walk(node, ancestors=()):
        local = node.tag.rsplit("}", 1)[-1]
        path = (*ancestors, local)
        if node.attrib:
            attrs = "; ".join(f"{k.rsplit('}', 1)[-1]}={v}" for k, v in node.attrib.items())
            parts.append("/".join(path) + ": " + attrs)
        if node.text and node.text.strip():
            parts.append(node.text.strip())
        for child in node:
            walk(child, path)
            if child.tail and child.tail.strip():
                parts.append(child.tail.strip())

    walk(root)
    return "\n".join(parts)


def test_extraction_version_bumped():
    # parser_version is persisted and require_parsed gates on it (see
    # document_ingestion.py) - changing extraction output without bumping
    # VERSION would silently mix old and new text for the same document.
    assert DocumentTextExtractor.VERSION == "strict-4"


def test_table_rows_join_onto_one_quotable_line():
    new = DocumentTextExtractor._xml_text(VITALS_TABLE_XML)
    assert "Blood Pressure: 124/73" in new
    assert "Pulse: 73" in new
    assert "Weight: 122.8 kg (270 lb 11.2 oz)" in new
    # No bare XPath-scaffold lines survive for the table row/cell elements.
    assert "styleCode=xRowNormal" not in new
    assert "styleCode=xcellHeader" not in new
    assert "/tr:" not in new and "/td:" not in new


def test_table_scaffold_noise_ratio_drops_dramatically_vs_old_behavior():
    old = _old_xml_text_render(VITALS_TABLE_XML)
    new = DocumentTextExtractor._xml_text(VITALS_TABLE_XML)

    def scaffold_ratio(text):
        lines = text.splitlines()
        scaffold = [l for l in lines if re.match(r"^[\w/]+(?:/[\w]+)*: \w+=", l)]
        return len(scaffold) / len(lines) if lines else 0

    old_ratio, new_ratio = scaffold_ratio(old), scaffold_ratio(new)
    assert old_ratio > 0.3  # old behavior is dominated by scaffold lines
    # One legitimate scaffold-shaped line survives: the section <code> element's
    # displayName/code attributes (clinical signal, deliberately not noise - see
    # the report's real AFTER excerpt, which keeps this exact line too). Every
    # <tr>/<td>/<table> scaffold line the old walk emitted is gone.
    assert new_ratio < 0.2
    assert new_ratio < old_ratio / 2  # dramatic drop, not a marginal one
    assert len(new) < len(old) * 0.6  # substantial size reduction too


def test_medication_list_items_stay_on_separate_lines_not_collapsed():
    """Regression guard: <list><item> is a <br/>-separated narrative BLOCK,
    not a <tr> row. Routing it through the row-join branch would concatenate
    all 6 medications with " | " onto a single line and destroy the
    quotability that works correctly today."""
    new = DocumentTextExtractor._xml_text(MEDICATION_LIST_XML)
    for med in MEDICATIONS:
        assert med in new

    lines = [l.strip() for l in new.splitlines() if l.strip()]
    med_lines = [l for l in lines if any(l.startswith(m.split()[0]) for m in MEDICATIONS)]
    assert len(med_lines) == 6  # each medication on its OWN line
    # The failure mode this guards against: row-joining would produce one
    # line containing every medication separated by " | ".
    assert not any(sum(m in line for m in MEDICATIONS) > 1 for line in lines)


def test_mixed_table_and_list_document_renders_both_correctly():
    """A single CDA document with a vitals <table> section AND a medication
    <list> section - both narrative shapes must render correctly in the
    same walk() pass, matching the real production document's structure."""
    mixed = DocumentTextExtractor._xml_text(MIXED_XML)
    assert "Blood Pressure: 124/73" in mixed
    assert "Pulse: 73" in mixed
    for med in MEDICATIONS:
        assert med in mixed
    lines = [l.strip() for l in mixed.splitlines() if l.strip()]
    med_lines = [l for l in lines if any(l.startswith(m.split()[0]) for m in MEDICATIONS)]
    assert len(med_lines) == 6


def test_noise_tags_and_attrs_suppressed_but_clinical_attrs_survive():
    xml = _document(
        _section(
            '<templateId root="2.16.840.1.113883.10.20.22.4.4"/>'
            '<code code="8716-3" codeSystem="2.16.840.1.113883.6.1" displayName="Vital signs"/>'
        )
    )
    out = DocumentTextExtractor._xml_text(xml)
    assert "templateId" not in out  # pure CDA plumbing tag suppressed
    assert "codeSystem=" not in out  # noise attribute suppressed
    assert "displayName=Vital signs" in out  # clinical attribute survives
