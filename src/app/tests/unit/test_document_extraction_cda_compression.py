"""Redundancy-only CDA compression (strict-5) in DocumentTextExtractor._xml_text.

Executable form of the design doc's Invariant R (care-capture-nodeapi
.claude/debug-reports/2026-09-22-async-summarization-fix/
cda-redundancy-compression-design.md §8), strengthened in round 3: grouping
and tail paths may only remove mechanical path redundancy -- the MULTISET
(not just set) of (attribute, value) pair occurrences, the multiset of text
lines and the raw semantic-marker counts must be identical to the ungrouped
strict-4 walk's, for any input. There is no identical-subtree back-referencing
(the design's Rule 3 was measured and dropped in round 3): every occurrence of
every subtree renders in full. Names may influence layout, never retention.
"""

import re
import xml.etree.ElementTree as ET
from collections import Counter

from src.app.services.document_extraction import (
    DocumentTextExtractor,
    _XML_ENTRY_RELATIONSHIP_TYPE_PREFIXES,
    _XML_MOOD_PREFIXES,
    _XML_NOISE_ATTRS,
    _XML_NOISE_TAGS,
    _XML_SEMANTIC_ATTRS,
)

_MARKERS = ("[ORDERED/PLANNED]", "[APPOINTMENT]", "[GOAL]",
            "NEGATED:", "MANIFESTATION:", "REASON:", "CAUSE:")


def _strict4_render(content: bytes) -> str:
    """Byte-for-byte replica of the pre-compression (strict-4) _xml_text walk:
    one full-XPath line per attributed/marked element, no grouping. Kept as the
    reference the compressed output is proven multiset-equal against."""
    root = ET.fromstring(content)
    parts = []

    def walk(node, ancestors=()):
        local = node.tag.rsplit("}", 1)[-1]
        if local in _XML_NOISE_TAGS:
            return
        if local == "text":
            rendered = DocumentTextExtractor._cda_narrative(node)
            if rendered.strip():
                parts.append(rendered.strip())
            return
        path = (*ancestors, local)
        raw_attrs = {k.rsplit("}", 1)[-1]: v for k, v in node.attrib.items()}
        attributes = {k: v for k, v in raw_attrs.items()
                      if k not in _XML_NOISE_ATTRS and k not in _XML_SEMANTIC_ATTRS}
        markers = []
        mood = raw_attrs.get("moodCode")
        if mood in _XML_MOOD_PREFIXES:
            markers.append(_XML_MOOD_PREFIXES[mood])
        if raw_attrs.get("negationInd") == "true":
            markers.append("NEGATED:")
        if local == "entryRelationship":
            rel = raw_attrs.get("typeCode")
            if rel in _XML_ENTRY_RELATIONSHIP_TYPE_PREFIXES:
                markers.append(_XML_ENTRY_RELATIONSHIP_TYPE_PREFIXES[rel])
        prefix = (" ".join(markers) + " ") if markers else ""
        if attributes:
            parts.append(prefix + "/".join(path) + ": " +
                         "; ".join(f"{k}={v}" for k, v in attributes.items()))
        elif prefix:
            parts.append(prefix + "/".join(path))
        if node.text and node.text.strip():
            parts.append(node.text.strip())
        for child in node:
            walk(child, path)
            if child.tail and child.tail.strip():
                parts.append(child.tail.strip())

    walk(root)
    return "\n".join(parts)


_PATH_SHAPE = re.compile(r"^[A-Za-z_][\w\[\]]*(?:/[A-Za-z_][\w\[\]]*)*$")


def _channels(text: str):
    """Split an extraction into the three Invariant R channels: the MULTISET of
    (attribute, value) pair occurrences, the multiset of non-path text lines,
    and raw semantic-marker counts. Applied identically to old and new output."""
    pairs, text_lines = Counter(), Counter()
    for line in text.splitlines():
        if not line.strip():
            continue
        work, structural = line, False
        if work.startswith("@ "):
            work, structural = work[2:], True
        stripped_marker = True
        while stripped_marker:
            stripped_marker = False
            for marker in _MARKERS:
                if work.startswith(marker + " "):
                    work, stripped_marker, structural = work[len(marker) + 1:], True, True
        head, sep, rest = work.partition(": ")
        if sep and _PATH_SHAPE.match(head):
            for token in re.split(r"; (?=[A-Za-z_][\w.:-]*=)", rest):
                eq = token.find("=")
                if eq > 0:
                    pairs[(token[:eq], token[eq + 1:])] += 1
            continue
        if _PATH_SHAPE.match(work) and ("/" in work or structural):
            continue  # bare path line (marker-only or spine)
        text_lines[work if not structural else line] += 1
    counts = {marker: text.count(marker) for marker in _MARKERS}
    return pairs, text_lines, counts


def _nchunks(text: str) -> int:
    # The real _create_batches arithmetic: CHUNK_CHAR_LIMIT=30_000, stride
    # 30_000 - min(1000, 30_000 // 10) = 29_000 (attachment_summarization/chain.py).
    return len(range(0, len(text), 29_000)) if text else 0


def _document(*sections: str) -> bytes:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<ClinicalDocument xmlns="urn:hl7-org:v3">'
        "<component><structuredBody>"
        + "".join(f"<component><section>{s}</section></component>" for s in sections)
        + "</structuredBody></component>"
        "</ClinicalDocument>"
    ).encode()


_AUTHOR_BLOCK = (
    '<author><time value="20240101"/><assignedAuthor>'
    '<code code="207Q00000X" displayName="Family Medicine"/>'
    "<addr><streetAddressLine>123 Main St</streetAddressLine><city>Springfield</city></addr>"
    '<telecom value="tel:+1-555-0100"/>'
    "<assignedPerson><name><given>Sara</given><family>Nguyen</family></name></assignedPerson>"
    "</assignedAuthor></author>"
)

# fat=True pads the criticality observation past any small-block threshold with
# ordinary CDA elements (statusCode/effectiveTime/interpretationCode/methodCode,
# all present in the real corpus) -- the round-2 M4 case where the old Rule 3
# collapsed a legitimately-repeated criticality assessment into a pointer.
_CRIT_EXTRA = ('<statusCode code="completed"/><effectiveTime value="20240101"/>'
               '<interpretationCode code="ABN" displayName="Abnormal"/>'
               '<methodCode code="M1" displayName="Assessment"/>')

def _allergy(name, reaction, reaction_code, crit, crit_code, fat=False):
    return (
        '<entry><act classCode="ACT" moodCode="EVN"><code code="CONC"/>'
        '<entryRelationship typeCode="SUBJ"><observation classCode="OBS" moodCode="EVN">'
        f"<participant><participantRole><playingEntity><name>{name}</name></playingEntity></participantRole></participant>"
        '<entryRelationship typeCode="MFST"><observation classCode="OBS" moodCode="EVN">'
        f'<value code="{reaction_code}" displayName="{reaction}"/>'
        "</observation></entryRelationship>"
        '<entryRelationship typeCode="SUBJ"><observation classCode="OBS" moodCode="EVN">'
        '<code code="82606-5" displayName="Criticality"/>'
        + (_CRIT_EXTRA if fat else "")
        + f'<value code="{crit_code}" displayName="{crit}"/>'
        "</observation></entryRelationship>"
        "</observation></entryRelationship></act></entry>"
    )


_MEDICATION = (
    '<entry><substanceAdministration classCode="SBADM" moodCode="{mood}">'
    '<statusCode code="{status}"/>'
    '<effectiveTime><low value="{low}"/><high value="{high}"/></effectiveTime>'
    '<routeCode code="C38276" displayName="intraVENOUS"><originalText>intraVENOUS</originalText></routeCode>'
    '<doseQuantity unit="{unit}" value="{dose}"/>'
    "<consumable><manufacturedProduct><manufacturedMaterial>"
    '<code code="{rxnorm}" displayName="{drug}"/>'
    "</manufacturedMaterial></manufacturedProduct></consumable>"
    + _AUTHOR_BLOCK +
    "</substanceAdministration></entry>"
)


def _rich_document() -> bytes:
    """Big enough that the root cannot be one group (spine + several groups),
    with repeated provenance blocks, semantic markers, narrative and an
    element-text lab value -- every channel exercised at once."""
    narrative = (
        "<title>Results</title><text><table><tbody>"
        '<tr><td styleCode="xcellHeader">Blood Pressure</td><td>124/73</td></tr>'
        "<tr><td>Pulse</td><td>73</td></tr>"
        "</tbody></table></text>"
    )
    labs = (
        '<entry><observation classCode="OBS" moodCode="EVN">'
        '<code code="94500-6" displayName="SARS-CoV2 (COVID-19) RNA NAA+probe QI (Resp)"/>'
        '<statusCode code="completed"/><effectiveTime value="20210902184400+0000"/>'
        "<value>NOT DETECTED</value>"
        '<interpretationCode code="NEG" displayName="Negative"/>'
        "</observation></entry>"
    )
    negated = (
        '<entry><observation classCode="OBS" moodCode="EVN" negationInd="true">'
        '<value displayName="Pregnancy"/></observation></entry>'
    )
    meds = "".join(
        _MEDICATION.format(
            mood=("EVN" if i % 2 else "INT"), status="active",
            low=f"202401{i:02d}0800", high=f"202401{i:02d}2000",
            unit="mg", dose=str(5 * (i + 1)), rxnorm=str(1000 + i),
            drug=f"Drug-{i}",
        )
        for i in range(6)
    )
    allergies = (
        _allergy("PENICILLIN G", "Hives", "126485001", "low criticality", "CRITL")
        + _allergy("SHELLFISH-DERIVED PRODUCTS", "Itching", "418290006", "high criticality", "CRITH")
        + _allergy("STRAWBERRY EXTRACT", "Anaphylaxis", "39579001", "high criticality", "CRITH")
    )
    return _document(narrative, "<title>Medications</title>" + meds,
                     "<title>Allergies</title>" + allergies, labs + negated)


# --- Invariant R property tests, multiset-strength (design §8, tests 1-2) ----

def test_attribute_pair_multiset_equal_to_ungrouped_walk():
    doc = _rich_document()
    old_pairs, _, _ = _channels(_strict4_render(doc))
    new_pairs, _, _ = _channels(DocumentTextExtractor._xml_text(doc))
    assert old_pairs, "fixture must exercise the attribute channel"
    assert new_pairs == old_pairs  # every occurrence kept, nothing invented


def test_text_line_multiset_and_marker_counts_equal_to_ungrouped_walk():
    doc = _rich_document()
    _, old_text, old_counts = _channels(_strict4_render(doc))
    _, new_text, new_counts = _channels(DocumentTextExtractor._xml_text(doc))
    assert old_text, "fixture must exercise the text channel"
    assert new_text == old_text
    assert old_text["NOT DETECTED"] == 1 and new_text["NOT DETECTED"] == 1
    assert sum(old_counts.values()) > 0, "fixture must exercise semantic markers"
    assert new_counts == old_counts


# --- multiplicity of identical clinical facts, thin AND fat (round-2 M4) -----

def test_repeated_high_criticality_renders_twice_not_once():
    """Two different allergies sharing a byte-identical criticality observation
    must both print it -- at ANY block size. The fat variant (7 emitted parts)
    is the exact round-2 repro where the since-removed back-reference mechanism
    collapsed the second occurrence into a pointer."""
    for fat in (False, True):
        doc = _document(
            "<title>Allergies</title>"
            + _allergy("SHELLFISH", "Itching", "418290006", "high criticality", "CRITH", fat)
            + _allergy("STRAWBERRY", "Anaphylaxis", "39579001", "high criticality", "CRITH", fat)
        )
        out = DocumentTextExtractor._xml_text(doc)
        assert out.count("displayName=high criticality") == 2, f"fat={fat}"
        assert "IDENTICAL TO" not in out


# --- repeated subtrees always render in full (replaces the Rule 3 tests) -----

def test_identical_blocks_render_in_full_at_every_occurrence():
    """Six byte-identical author blocks: every occurrence renders completely --
    no back-references, no anchors, no cross-line dependencies of any kind
    (every extraction chunk is self-contained by construction)."""
    out = DocumentTextExtractor._xml_text(_rich_document())
    assert out.count("123 Main St") == 6
    assert out.count("tel:+1-555-0100") == 6
    assert "IDENTICAL TO" not in out
    assert not re.search(r"\{#\d+\}", out)


# --- narrative is never swallowed by layout (round-2 M2) ---------------------

def test_narrative_repeats_verbatim_in_duplicated_sections():
    """Two byte-identical narrative-bearing sections: the quotable prose must
    appear at BOTH locations, byte-identically (load-bearing for
    verify_grounding's quote matching)."""
    section = (
        "<title>Allergies</title><text><table><tbody>"
        "<tr><td>No known allergies documented for this patient</td>"
        "<td>Reviewed 2024-01-01</td></tr>"
        "</tbody></table></text>"
        + _allergy("SHELLFISH", "Itching", "418290006", "high criticality", "CRITH", fat=True)
    )
    doc = _document(section, section)
    old = _strict4_render(doc)
    new = DocumentTextExtractor._xml_text(doc)
    for prose in ("No known allergies documented for this patient", "Reviewed 2024-01-01"):
        assert old.count(prose) == 2, "fixture must duplicate the narrative"
        assert new.count(prose) == 2


# --- node with attributes AND attribute-bearing children (test 5) ------------

def test_node_with_attributes_and_attributed_children_keeps_both():
    doc = _document(
        '<entry><observation classCode="OBS">'
        '<code code="X-1" displayName="Parent payload">'
        '<translation code="Y-2" displayName="Child payload"/>'
        "</code></observation></entry>"
    )
    out = DocumentTextExtractor._xml_text(doc)
    assert "code: code=X-1; displayName=Parent payload" in out
    assert "code/translation: code=Y-2; displayName=Child payload" in out


# --- chunk-boundary statelessness of tail paths ------------------------------

def test_body_lines_carry_complete_tail_paths_not_deltas():
    """Every attribute body line inside a group must carry the complete
    ancestor chain from the group root -- a chunk that starts mid-group must
    never see a context-free 'value: ...' line (the report-2 orphaned-line
    failure the delta/indent encoding was rejected for)."""
    out = DocumentTextExtractor._xml_text(_rich_document())
    crit_lines = [l for l in out.splitlines() if "displayName=high criticality" in l]
    assert crit_lines and all(
        "observation/value: " in l and l.split(": ")[0].count("/") >= 2 for l in crit_lines
    )


# --- foreign/non-CDA XML must never get bigger than today (round-2 M3) -------

def test_flat_foreign_xml_renders_byte_identical_to_ungrouped_walk():
    """Flat XML (attributed leaves under one root) gains nothing from grouping:
    a leaf earns no '@' header (no descendant path line would share it), so the
    output is byte-identical to today's renderer -- same size, same chunks.
    Round 2 measured +32.8% chars and one EXTRA chunk on this shape before the
    header-earning guard existed."""
    doc = (b'<?xml version="1.0"?><Records>'
           + b"".join(f'<Record id2="{i}" code="C{i}" value="{i * 1.5}" unit="mg"/>'.encode()
                      for i in range(300))
           + b"</Records>")
    old = _strict4_render(doc)
    new = DocumentTextExtractor._xml_text(doc)
    assert new == old
    assert _nchunks(new) == _nchunks(old)


def test_foreign_xml_never_bigger_than_ungrouped_walk():
    """Nested-but-unknown schemas may group (smaller) but must never exceed
    today's size -- the design's §7.4 'worst case approaches today's verbosity'
    claim, now enforced."""
    lab = (b'<?xml version="1.0"?><LabReport xmlns="urn:acme:lab">'
           b'<Header><Lab name="Acme" clia="99D1234567"/></Header>'
           b'<Specimen sid="S1" type="serum"><CollectedAt when="2024-03-01T08:00:00Z"/></Specimen>'
           b"<Analytes>"
           + b"".join(f'<Analyte loinc="{2000 + i}" name="Analyte{i}" value="{i * 1.5}" unit="mg/dL">'
                      f"<Comment>Result note {i}</Comment></Analyte>".encode()
                      for i in range(40))
           + b"</Analytes></LabReport>")
    over_group_limit = ("<section>"
                        + "".join(f'<obs code="C{i}" displayName="D{i}"/>' for i in range(41))
                        + "</section>").encode()
    for doc in (lab, b'<?xml version="1.0"?><doc>' + over_group_limit + b"</doc>"):
        old = _strict4_render(doc)
        new = DocumentTextExtractor._xml_text(doc)
        assert len(new) <= len(old)
    # Many DISTINCT spine sections just over the group limit: their own spine
    # lines carry sibling indices (a deliberate disambiguation feature), so the
    # bound is "approaches today's verbosity", not byte-parity -- but the +8.5%
    # regression round 3 found (indexed ancestors leaking into inline body
    # lines) must never come back.
    many = (b'<?xml version="1.0"?><doc>'
            + b"".join((f'<section sid="{s}">'
                        + "".join(f'<obs code="C{s}-{i}" displayName="D{i}"/>' for i in range(41))
                        + "</section>").encode() for s in range(50))
            + b"</doc>")
    old = _strict4_render(many)
    new = DocumentTextExtractor._xml_text(many)
    assert len(new) <= len(old) * 1.01
    assert _nchunks(new) <= _nchunks(old)
