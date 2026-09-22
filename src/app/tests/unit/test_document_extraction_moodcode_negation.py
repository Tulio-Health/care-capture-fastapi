"""moodCode/negationInd/entryRelationship-typeCode semantic-prefix fix in
DocumentTextExtractor._xml_text.

Fix from care-capture-nodeapi's
.claude/debug-reports/2026-09-22-async-summarization-fix/
xml-compression-information-loss-audit.md §9.1: _XML_NOISE_ATTRS at develop
HEAD dropped moodCode and negationInd entirely, so a real Day Surgery
Encounter Summary's 12 actually-given (moodCode="EVN") and 11 merely-ordered
(moodCode="INT") medication entries - including opioids - rendered as
structurally identical text. This is the CDA-native form of the
"ordered vs performed" hallucination this codebase already guards against
elsewhere (chain.py's ordered-vs-performed gate) - but upstream, in
extraction, before that gate ever sees the text. negationInd="true" (a
finding that did NOT occur) was silently dropped the same way.

These tests build small synthetic CDA snippets that mirror the real
structure (tag names, nesting) without any real patient data.
"""

import xml.etree.ElementTree as ET

from src.app.services.document_extraction import DocumentTextExtractor


def _document(entry_xml: str) -> bytes:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<ClinicalDocument xmlns="urn:hl7-org:v3">'
        "<component><structuredBody><component><section>"
        "<entry>" + entry_xml + "</entry>"
        "</section></component></structuredBody></component>"
        "</ClinicalDocument>"
    ).encode()


def _extract(entry_xml: str) -> str:
    return DocumentTextExtractor._xml_text(_document(entry_xml))


# --- moodCode -----------------------------------------------------------

def test_moodcode_int_renders_ordered_planned_prefix():
    out = _extract(
        '<substanceAdministration classCode="SBADM" moodCode="INT">'
        '<code code="123" displayName="Oxycodone 5mg"/>'
        "</substanceAdministration>"
    )
    assert "[ORDERED/PLANNED]" in out
    assert "substanceAdministration" in out


def test_moodcode_evn_renders_no_prefix_and_is_byte_identical_to_today():
    evn = _extract(
        '<substanceAdministration classCode="SBADM" moodCode="EVN">'
        '<code code="123" displayName="Oxycodone 5mg"/>'
        "</substanceAdministration>"
    )
    absent = _extract(
        '<substanceAdministration classCode="SBADM">'
        '<code code="123" displayName="Oxycodone 5mg"/>'
        "</substanceAdministration>"
    )
    assert "[ORDERED/PLANNED]" not in evn
    assert "[APPOINTMENT]" not in evn
    assert "[GOAL]" not in evn
    # Byte-identical to the moodCode-absent case, and to what today's shipped
    # code emits (classCode/moodCode were already noise-suppressed pre-fix).
    assert evn == absent
    assert "substanceAdministration/code: code=123; displayName=Oxycodone 5mg" in evn


def test_moodcode_given_vs_ordered_medications_now_differ():
    """The exact real-world shape from the audit: two otherwise-identical
    medication entries, one actually given, one only ordered, must no
    longer render as structurally identical text."""
    given = _extract(
        '<substanceAdministration classCode="SBADM" moodCode="EVN">'
        '<code code="7052" displayName="Fentanyl"/>'
        "</substanceAdministration>"
    )
    ordered = _extract(
        '<substanceAdministration classCode="SBADM" moodCode="INT">'
        '<code code="7052" displayName="Fentanyl"/>'
        "</substanceAdministration>"
    )
    assert given != ordered
    assert "[ORDERED/PLANNED]" in ordered and "[ORDERED/PLANNED]" not in given


def test_moodcode_apt_renders_appointment_prefix():
    out = _extract('<encounter classCode="ENC" moodCode="APT"><code code="99213"/></encounter>')
    assert "[APPOINTMENT]" in out


def test_moodcode_gol_renders_goal_prefix():
    out = _extract('<observation classCode="OBS" moodCode="GOL"><code code="1"/></observation>')
    assert "[GOAL]" in out


def test_moodcode_marker_survives_even_with_no_other_surviving_attributes():
    """A node whose only non-noise attribute is moodCode must still emit a
    line carrying the marker - it must not be silently dropped just because
    the attribute-line would otherwise be empty."""
    out = _extract('<act classCode="ACT" moodCode="INT"><code nullFlavor="NA"/></act>')
    lines = [l for l in out.splitlines() if "[ORDERED/PLANNED]" in l]
    assert len(lines) == 1
    assert lines[0] == "[ORDERED/PLANNED] ClinicalDocument/component/structuredBody/component/section/entry/act"


# --- negationInd ----------------------------------------------------------

def test_negationind_true_renders_negated_prefix():
    out = _extract(
        '<observation classCode="OBS" moodCode="EVN" negationInd="true">'
        '<value displayName="Penicillin allergy"/>'
        "</observation>"
    )
    assert "NEGATED:" in out
    assert "displayName=Penicillin allergy" in out


def test_negationind_false_renders_no_prefix_and_unchanged():
    false_out = _extract(
        '<observation classCode="OBS" moodCode="EVN" negationInd="false">'
        '<value displayName="Penicillin allergy"/>'
        "</observation>"
    )
    absent_out = _extract(
        '<observation classCode="OBS" moodCode="EVN">'
        '<value displayName="Penicillin allergy"/>'
        "</observation>"
    )
    assert "NEGATED:" not in false_out
    assert false_out == absent_out


# --- entryRelationship/@typeCode ------------------------------------------

def test_entry_relationship_mfst_renders_manifestation_prefix():
    out = _extract(
        '<observation classCode="OBS" moodCode="EVN">'
        '<value displayName="Penicillin allergy"/>'
        '<entryRelationship typeCode="MFST">'
        '<observation classCode="OBS" moodCode="EVN"><value displayName="Hives"/></observation>'
        "</entryRelationship>"
        "</observation>"
    )
    assert "MANIFESTATION:" in out
    assert "displayName=Hives" in out


def test_entry_relationship_rson_renders_reason_prefix():
    out = _extract('<entryRelationship typeCode="RSON"><observation classCode="OBS"/></entryRelationship>')
    assert "REASON:" in out


def test_entry_relationship_caus_renders_cause_prefix():
    out = _extract('<entryRelationship typeCode="CAUS"><observation classCode="OBS"/></entryRelationship>')
    assert "CAUSE:" in out


def test_entry_relationship_other_typecodes_stay_suppressed_no_raw_dump():
    for type_code in ("COMP", "REFR", "SUBJ"):
        out = _extract(f'<entryRelationship typeCode="{type_code}"><observation classCode="OBS"/></entryRelationship>')
        assert "MANIFESTATION:" not in out
        assert "REASON:" not in out
        assert "CAUSE:" not in out
        assert f"typeCode={type_code}" not in out
        assert "entryRelationship:" not in out  # no bare attribute line for entryRelationship itself


def test_typecode_on_non_entry_relationship_node_never_gets_a_prefix():
    """typeCode is only meaningful on <entryRelationship> per the fix scope -
    a hypothetical typeCode on some other element must stay fully suppressed,
    exactly like today."""
    out = _extract('<participant typeCode="MFST"><code code="1"/></participant>')
    assert "MANIFESTATION:" not in out
    assert "typeCode=" not in out


def test_inversionind_never_raw_dumped_and_never_gets_a_prefix():
    out = _extract('<entryRelationship typeCode="MFST" inversionInd="true"><observation classCode="OBS"/></entryRelationship>')
    assert "inversionInd" not in out
    assert "MANIFESTATION:" in out  # typeCode signal still renders


# --- combined case ---------------------------------------------------------

def test_combined_moodcode_and_negationind_render_both_prefixes_not_garbled():
    out = _extract(
        '<observation classCode="OBS" moodCode="INT" negationInd="true">'
        '<value displayName="Follow-up screening"/>'
        "</observation>"
    )
    # The observation node's own attribute set is empty after noise-filtering
    # (classCode/moodCode/negationInd all filtered) - its markers land on the
    # `elif prefix` bare-path line, not on the child <value> line.
    line = next(l for l in out.splitlines() if l.rstrip().endswith("/observation"))
    assert "[ORDERED/PLANNED]" in line
    assert "NEGATED:" in line
    assert line.count("[ORDERED/PLANNED]") == 1
    assert line.count("NEGATED:") == 1
    # Marker order is deterministic: mood before negation.
    assert line.index("[ORDERED/PLANNED]") < line.index("NEGATED:")
    assert "displayName=Follow-up screening" in out  # child value still renders separately


# --- raw attribute never leaks -----------------------------------------------

def test_semantic_attributes_never_appear_as_raw_key_value_pairs():
    out = _extract(
        '<observation classCode="OBS" moodCode="INT" negationInd="true">'
        '<entryRelationship typeCode="MFST" inversionInd="true">'
        '<observation classCode="OBS" moodCode="EVN"/>'
        "</entryRelationship>"
        "</observation>"
    )
    for raw in ("moodCode=", "negationInd=", "typeCode=", "inversionInd=", "classCode="):
        assert raw not in out


def test_old_replica_walk_shows_these_four_attrs_were_previously_dropped_entirely():
    """Sanity check against the pre-fix behavior this test file guards
    against regressing to: the OLD noise-suppressed walk (mirroring
    _XML_NOISE_ATTRS as it stood before this fix) drops moodCode/negationInd
    with no signal at all, unlike the fixed walk which now surfaces them."""
    old_noise_attrs = {"styleCode", "ID", "width", "span", "root", "extension",
                        "codeSystem", "codeSystemName", "classCode", "moodCode",
                        "typeCode", "inversionInd", "contextControlCode",
                        "independentInd", "determinerCode", "negationInd", "type"}

    def old_xml_text(content: bytes) -> str:
        root = ET.fromstring(content)
        parts = []

        def walk(node, ancestors=()):
            local = node.tag.rsplit("}", 1)[-1]
            path = (*ancestors, local)
            attrs = {k.rsplit("}", 1)[-1]: v for k, v in node.attrib.items() if k.rsplit("}", 1)[-1] not in old_noise_attrs}
            if attrs:
                parts.append("/".join(path) + ": " + "; ".join(f"{k}={v}" for k, v in attrs.items()))
            for child in node:
                walk(child, path)

        walk(root)
        return "\n".join(parts)

    entry = (
        '<substanceAdministration classCode="SBADM" moodCode="EVN">'
        '<code code="7052" displayName="Fentanyl"/></substanceAdministration>'
    )
    given = old_xml_text(_document(entry))
    ordered = old_xml_text(_document(entry.replace('moodCode="EVN"', 'moodCode="INT"')))
    assert given == ordered  # the bug this fix corrects
