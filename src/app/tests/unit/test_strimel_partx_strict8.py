"""strict-8 (CDA_COMPACT_EXTRACTION_ENABLED) counterparts of the strict-7-format extractor tests.

strict-7 tests (test_document_extraction_ccd_xml / _cda_compression / _moodcode_negation) pin the
flag OFF and keep specifying the prod-default renderer. These specify the compact renderer:
same values and semantic markers, one line per clinical statement, admin plumbing dropped.
"""

import xml.etree.ElementTree as ET

import pytest

from src.app.core.settings import get_settings
from src.app.services.document_extraction import (
    _CDA_ENTRY_ADMIN,
    _CDA_KEEP_PARTICIPANT,
    _XML_NOISE_ATTRS,
    _XML_NOISE_TAGS,
    _XML_SEMANTIC_ATTRS,
    DocumentTextExtractor,
)
from src.app.tests.unit.test_document_extraction_cda_compression import (
    _allergy,
    _document,
    _rich_document,
)


@pytest.fixture(autouse=True)
def _compact_on(monkeypatch):
    monkeypatch.setattr(get_settings(), "CDA_COMPACT_EXTRACTION_ENABLED", True)


def _x(doc: bytes) -> str:
    return DocumentTextExtractor._xml_text(doc)


def _entry(entry_xml: str) -> bytes:
    return _document("<entry>" + entry_xml + "</entry>")


def _clinical_values(doc: bytes):
    """Every attribute/element-text value under structuredBody outside admin subtrees."""
    root = ET.fromstring(doc)
    parent = {c: p for p in root.iter() for c in p}
    local = lambda n: n.tag.rsplit("}", 1)[-1]
    out = []
    for node in root.iter():
        chain, x = [], node
        while x is not None:
            chain.append(x)
            x = parent.get(x)
        names = [local(a) for a in chain]
        if "structuredBody" not in names or any(n in _XML_NOISE_TAGS for n in names):
            continue
        if any(local(a) in _CDA_ENTRY_ADMIN or (local(a) == "participant" and a.attrib.get("typeCode", "CSM") not in _CDA_KEEP_PARTICIPANT)
               for a in chain if "entry" in names):
            continue
        for k, v in node.attrib.items():
            k = k.rsplit("}", 1)[-1]
            if k in _XML_NOISE_ATTRS or k in _XML_SEMANTIC_ATTRS or k == "nullFlavor" or v.startswith("#"):
                continue
            out.append(v)
        if node.text and node.text.strip():
            out.append(" ".join(node.text.split()))
    return out


def test_version_follows_flag(monkeypatch):
    assert DocumentTextExtractor.VERSION == "strict-8"
    monkeypatch.setattr(get_settings(), "CDA_COMPACT_EXTRACTION_ENABLED", False)
    assert DocumentTextExtractor.VERSION == "strict-7"


def test_every_clinical_value_survives_on_rich_document():
    doc = _rich_document()
    flat = " ".join(_x(doc).split())
    missing = [v for v in _clinical_values(doc) if " ".join(v.split()) not in flat]
    assert missing == []


def test_noise_tags_and_attrs_never_rendered():
    out = _x(_entry('<observation classCode="OBS" moodCode="EVN"><templateId root="2.16.840.1.113883"/>'
                    '<id root="1.2.3" extension="X9"/><code code="8480-6" codeSystem="2.16.840.1.113883.6.1" '
                    'displayName="Systolic blood pressure"/><value value="124" unit="mm[Hg]"/></observation>'))
    assert "2.16.840" not in out and "X9" not in out and "codeSystem" not in out
    line = [l for l in out.splitlines() if l.startswith("observation")][0]
    assert "Systolic blood pressure (8480-6)" in line and "124 mm[Hg]" in line  # one line, contiguous


def test_repeated_high_criticality_renders_twice_across_entries():
    for fat in (False, True):
        out = _x(_document(
            "<title>Allergies</title>"
            + _allergy("SHELLFISH", "Itching", "418290006", "high criticality", "CRITH", fat)
            + _allergy("STRAWBERRY", "Anaphylaxis", "39579001", "high criticality", "CRITH", fat)))
        assert out.count("high criticality") == 2, f"fat={fat}"
        assert "SHELLFISH" in out and "STRAWBERRY" in out  # participant without typeCode kept
        assert out.count("MANIFESTATION:") == 2


def test_identical_sections_render_in_full_each_time():
    section = ("<title>Plan</title><text><paragraph>Return in 2 weeks</paragraph></text>"
               '<entry><observation moodCode="EVN"><code displayName="Follow-up"/></observation></entry>')
    out = _x(_document(section, section))
    assert out.count("Return in 2 weeks") == 2 and out.count("Follow-up") == 2


def test_mood_evn_no_prefix_int_prefix_on_the_statement_line():
    evn = _x(_entry('<substanceAdministration moodCode="EVN"><doseQuantity value="5" unit="mg"/></substanceAdministration>'))
    assert "[ORDERED" not in evn and "5 mg" in evn
    intent = _x(_entry('<substanceAdministration moodCode="INT"><doseQuantity value="5" unit="mg"/></substanceAdministration>'))
    line = [l for l in intent.splitlines() if "substanceAdministration" in l][0]
    assert line.startswith("[ORDERED/PLANNED] substanceAdministration") and "5 mg" in line


def test_marker_survives_with_no_other_attributes():
    out = _x(_entry('<act moodCode="INT"/>'))
    assert "[ORDERED/PLANNED] act" in out


def test_negation_and_relationship_prefixes():
    neg = _x(_entry('<observation moodCode="EVN" negationInd="true"><value displayName="Penicillin allergy"/></observation>'))
    assert "NEGATED: observation" in neg and "Penicillin allergy" in neg
    mfst = _x(_entry('<observation moodCode="EVN"><value displayName="Penicillin allergy"/>'
                     '<entryRelationship typeCode="MFST"><observation moodCode="EVN"><value displayName="Hives"/></observation>'
                     "</entryRelationship></observation>"))
    assert any(l.strip().startswith("MANIFESTATION: observation") and "Hives" in l for l in mfst.splitlines())
    for code, word in (("RSON", "REASON:"), ("CAUS", "CAUSE:")):
        assert word in _x(_entry(f'<entryRelationship typeCode="{code}"><observation classCode="OBS"/></entryRelationship>'))
    for code in ("COMP", "REFR", "SUBJ"):
        out = _x(_entry(f'<entryRelationship typeCode="{code}"><observation classCode="OBS"/></entryRelationship>'))
        assert "MANIFESTATION:" not in out and "REASON:" not in out and f"typeCode={code}" not in out
    combined = _x(_entry('<observation moodCode="INT" negationInd="true"><value displayName="Flu shot"/></observation>'))
    assert "[ORDERED/PLANNED] NEGATED: observation" in combined


def test_inversionind_never_rendered():
    out = _x(_entry('<observation moodCode="EVN"><entryRelationship typeCode="SUBJ" inversionInd="true">'
                    '<observation><value displayName="Mild"/></observation></entryRelationship></observation>'))
    assert "inversionInd" not in out and "Mild" in out


def test_entry_admin_plumbing_dropped_but_header_kept():
    doc = (b'<?xml version="1.0"?><ClinicalDocument xmlns="urn:hl7-org:v3"><title>Summary</title>'
           b'<author><assignedAuthor><assignedPerson><name><family>HeaderDoc</family></name></assignedPerson></assignedAuthor></author>'
           b'<component><structuredBody><component><section><entry><procedure moodCode="EVN">'
           b'<code code="45378" displayName="Colonoscopy"/><statusCode code="completed"/>'
           b'<performer><assignedEntity><addr><city>Springfield</city></addr></assignedEntity></performer>'
           b'</procedure></entry></section></component></structuredBody></component></ClinicalDocument>')
    out = _x(doc)
    assert "HeaderDoc" in out  # header rendered by the strict-7 walk
    assert "Springfield" not in out
    assert any(l.startswith("procedure") and "Colonoscopy (45378)" in l and "statusCode: completed" in l for l in out.splitlines())
