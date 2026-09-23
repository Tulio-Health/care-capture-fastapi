"""Redundancy-only CDA compression (strict-5) in DocumentTextExtractor._xml_text.

Executable form of the design doc's Invariant R (care-capture-nodeapi
.claude/debug-reports/2026-09-22-async-summarization-fix/
cda-redundancy-compression-design.md §8): grouping, tail paths and
identical-subtree back-references may only remove mechanical redundancy --
the de-duplicated set of (attribute, value) pairs, the set of text lines and
the raw semantic-marker counts must be identical to the ungrouped strict-4
walk's, for any input. Names may influence layout, never retention.
"""

import re
import xml.etree.ElementTree as ET

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
    one full-XPath line per attributed/marked element, no grouping, no
    back-references. Kept as the reference the compressed output is proven
    set-equal against."""
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
    """Split an extraction into the three Invariant R channels: the set of
    (attribute, value) pairs, the set of non-path text lines, and raw
    semantic-marker counts. Applied identically to old and new output."""
    pairs, text_lines = set(), set()
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
        if re.search(r" -> IDENTICAL TO #\d+$", work):
            continue
        if re.search(r" \{#\d+\}$", work):
            work, structural = re.sub(r" \{#\d+\}$", "", work), True
        head, sep, rest = work.partition(": ")
        if sep and _PATH_SHAPE.match(head):
            for token in re.split(r"; (?=[A-Za-z_][\w.:-]*=)", rest):
                eq = token.find("=")
                if eq > 0:
                    pairs.add((token[:eq], token[eq + 1:]))
            continue
        if _PATH_SHAPE.match(work) and ("/" in work or structural):
            continue  # bare path line (marker-only, spine, or {#n} anchor)
        text_lines.add(work if not structural else line)
    counts = {marker: text.count(marker) for marker in _MARKERS}
    return pairs, text_lines, counts


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

_ALLERGY = (
    '<entry><act classCode="ACT" moodCode="EVN"><code code="CONC"/>'
    '<entryRelationship typeCode="SUBJ"><observation classCode="OBS" moodCode="EVN">'
    "<participant><participantRole><playingEntity><name>{name}</name></playingEntity></participantRole></participant>"
    '<entryRelationship typeCode="MFST"><observation classCode="OBS" moodCode="EVN">'
    '<value code="{reaction_code}" displayName="{reaction}"/>'
    "</observation></entryRelationship>"
    '<entryRelationship typeCode="SUBJ"><observation classCode="OBS" moodCode="EVN">'
    '<code code="82606-5" displayName="Criticality"/>'
    '<value code="{crit_code}" displayName="{crit}"/>'
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
        _ALLERGY.format(name="PENICILLIN G", reaction="Hives", reaction_code="126485001",
                        crit="low criticality", crit_code="CRITL")
        + _ALLERGY.format(name="SHELLFISH-DERIVED PRODUCTS", reaction="Itching", reaction_code="418290006",
                          crit="high criticality", crit_code="CRITH")
        + _ALLERGY.format(name="STRAWBERRY EXTRACT", reaction="Anaphylaxis", reaction_code="39579001",
                          crit="high criticality", crit_code="CRITH")
    )
    return _document(narrative, "<title>Medications</title>" + meds,
                     "<title>Allergies</title>" + allergies, labs + negated)


# --- Invariant R property tests (design doc §8, tests 1-2) ------------------

def test_attribute_pair_set_equal_to_ungrouped_walk():
    doc = _rich_document()
    old_pairs, _, _ = _channels(_strict4_render(doc))
    new_pairs, _, _ = _channels(DocumentTextExtractor._xml_text(doc))
    assert old_pairs, "fixture must exercise the attribute channel"
    assert old_pairs - new_pairs == set()   # nothing lost
    assert new_pairs - old_pairs == set()   # nothing invented


def test_text_line_set_and_marker_counts_equal_to_ungrouped_walk():
    doc = _rich_document()
    _, old_text, old_counts = _channels(_strict4_render(doc))
    _, new_text, new_counts = _channels(DocumentTextExtractor._xml_text(doc))
    assert old_text, "fixture must exercise the text channel"
    assert old_text - new_text == set()
    assert "NOT DETECTED" in old_text and "NOT DETECTED" in new_text
    assert sum(old_counts.values()) > 0, "fixture must exercise semantic markers"
    assert new_counts == old_counts


# --- multiplicity of identical small clinical facts (test 3) -----------------

def test_repeated_high_criticality_renders_twice_not_once():
    """Two different allergies sharing the byte-identical value 'high
    criticality' must both print it: the criticality observation is far below
    _XML_BLOCK_MIN_PARTS, so back-referencing never touches it, and line-level
    dedup does not exist in this design."""
    out = DocumentTextExtractor._xml_text(_rich_document())
    assert out.count("displayName=high criticality") == 2
    assert out.count("displayName=low criticality") == 1


# --- identical-subtree back-reference (test 4) -------------------------------

def test_identical_blocks_render_once_plus_pointers():
    """Byte-identical >=_XML_BLOCK_MIN_PARTS-part author blocks: the first
    occurrence renders in full (anchored {#n}); every later occurrence is one
    explicit pointer line, so multiplicity stays visible."""
    out = DocumentTextExtractor._xml_text(_rich_document())
    assert out.count("123 Main St") == 1          # block content rendered once
    assert out.count("tel:+1-555-0100") == 1
    pointers = [l for l in out.splitlines() if re.search(r"-> IDENTICAL TO #\d+$", l)]
    assert len(pointers) == 5                     # 6 identical author blocks -> 1 full + 5 pointers
    assert len({l.split("#")[-1] for l in pointers}) == 1  # all point at the same block
    anchor_id = pointers[0].split("#")[-1]
    assert re.search(r"author \{#" + anchor_id + r"\}$", out, re.M)  # anchor line exists
    # Every pointer still carries its own full tail path back to its entry.
    assert all(l.split(" -> ")[0].strip().endswith("author") for l in pointers)


def test_two_distinct_blocks_never_collapse():
    """Blocks that differ in a single byte must both render in full."""
    variant = _AUTHOR_BLOCK.replace("Sara", "Mara")
    doc = _document("<entry>" + _AUTHOR_BLOCK + "</entry><entry>" + variant + "</entry>")
    out = DocumentTextExtractor._xml_text(doc)
    assert "IDENTICAL TO" not in out
    assert "Sara" in out and "Mara" in out


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
