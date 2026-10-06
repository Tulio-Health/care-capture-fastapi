"""Visit-summary document allowlist (v2).

A DocumentReference is eligible for the VISIT summary iff

    (label matches an include rule  OR  its LOINC typeCode is in LOINC_ALLOW_CODES)
    AND label matches no deny rule
    [AND is not excluded by a DB/floor exclude rule -- applied by the repository]

Precedence: DB exclude > deny > include = LOINC fallback.

The module is a pure-Python constant + matcher. Its PostgreSQL twin lives in
``db/objects/repositories/fhir_resources.py`` (selection WHERE term) and in
``scripts/sql/visit_summary_allowlist_census.sql`` (rendered by
``scripts/render_visit_summary_allowlist_sql.py``). The three must agree, which is enforced by:

* the ``sql_in_sync`` byte-equality test (census SQL == re-render),
* the portability test T0c (only characters/constructs that mean the same in Python ``re`` and
  PostgreSQL ARE are used -- no ``\\b`` (backspace in ARE), no ``\\y`` (not Python), no escapes),
* the real-PostgreSQL parity test T0b (``src/app/tests/pg_parity``).

Match semantics (part of the contract): the label is whitespace-folded (including NBSP),
trimmed and lower-cased, then ``re.search`` (== PostgreSQL ``~``) is applied.
"""
import hashlib
import json
import re
from typing import Iterable, Optional, Tuple

ALLOWLIST_VERSION = "visit-summary-allowlist-v2"

_B = "(^|[^a-z0-9])"  # portable left boundary (NOT \b: backspace in PG ARE; NOT \y: not Python)
_E = "([^a-z0-9]|$)"  # portable right boundary

# Whitespace class used by normalize_label (Python) and its SQL twin. NBSP (U+00A0) is folded too.
WS_CLASS_PY = "[ \t\r\n\f\v\u00a0]+"
# SQL twin: backslash escapes are interpreted by PostgreSQL's ARE engine (standard_conforming_strings
# on, bound as a parameter); the NBSP is a literal character (UTF-8 database).
WS_CLASS_SQL = "[ \\t\\r\\n\\f\\v\u00a0]+"

# (rule_id, kind, pattern, reason). kind in {"include", "deny"}.
VISIT_SUMMARY_ALLOWLIST: Tuple[Tuple[str, str, str, str], ...] = (
    # (A) documents that summarize the encounter as a whole
    ("vs.summary", "include", "(visit|depart|clinical|encounter|discharge|patient|ambulatory|episode) summar(y|ies)",
     "A: AVS/depart/clinical/encounter/discharge/patient summary (W2,W3,W5,W10,W12)"),
    ("vs.summary_of", "include", "summary of (the )?(visit|encounter|care|episode)", "A: summary of visit/care/episode (W8)"),
    ("vs.avs", "include", _B + "avs" + _E, "A: AVS abbreviation (W5)"),
    ("vs.ccd", "include", _B + "(ccd|c-?cda)" + _E, "A: CCD / C-CDA, owner-listed (W8)"),
    ("vs.continuity_of_care", "include", "continuity of care document", "A: CCD spelled out"),
    ("vs.hospital_course", "include", "hospital course", "A: synopsis of a stay (discharge-summary content)"),
    # (B) the note of the clinician who delivered the encounter's service (any modality)
    ("note.progress", "include", "progress notes?", "B: USCDI Progress Note (W1)"),
    ("note.office_clinic", "include", "(office|clinic|outpatient)( visit| clinic| progress)? notes?", "B: office/clinic/outpatient note (W1)"),
    ("note.visit", "include", "visit notes?", "B: visit note"),
    ("note.visit_bare", "include", _B + "(office|clinic|follow[ -]?up|outpatient|telehealth|telemedicine|virtual|video|urgent care) visit" + _E,
     "B: bare '<setting> visit' label = the encounter's note"),
    ("note.clinical", "include", _B + "clinical notes?" + _E, "B: generic clinical note"),
    ("note.enhanced", "include", "^enhanced note$", "B (weak): Cerner Enhanced Note"),
    ("note.telehealth", "include", "(telemedicine|telehealth|virtual|video) (visit|note|encounter|consult)", "B: telehealth encounter note"),
    ("note.urgent_care", "include", "urgent care (visit )?notes?", "B: urgent-care note"),
    ("note.follow_up", "include", "follow[ -]?up notes?", "B: follow-up note"),
    ("note.ed", "include", _B + "(ed|er|emergency|emergency department|emergency room|emergency medicine)([ -](provider|physician))?[ -]notes?" + _E,
     "B: USCDI Emergency Department Note (W1)"),
    ("note.critical_care", "include", "critical care notes?", "B: critical-care physician note"),
    ("note.hp", "include", "history ?(and|&|/) ?physical", "B: USCDI History & Physical (W1)"),
    ("note.hp_abbrev", "include", _B + "h ?(&|and|/) ?p" + _E, "B: H&P abbreviations"),
    ("note.admission", "include", "admission note", "B: Cerner admission note physician (incl. readmission)"),
    ("note.consult", "include", _B + "consult(ation|ations|s)?" + _E, "B: USCDI Consultation Note (W1)"),
    ("note.telephone", "include", "(telephone|phone) (encounter|call|note|visit)", "B: note of a telephone encounter (W6,W7)"),
    ("note.operative", "include", _B + "(op|operative|surgeon|surgical|procedure|procedures|endoscopy|endo) (note|notes|report|reports)" + _E,
     "B: operative/procedure note of a procedure encounter (W1 Operative/Procedure Note)"),
    ("note.therapy", "include", "(physical|occupational|speech) therapy( progress| visit| daily| treatment| evaluation)? notes?",
     "B: therapist is the treating clinician of a therapy visit"),
    ("note.behavioral", "include", "(social work|behavioral health|psychology|psychiatry|psychiatric|counseling)( progress| visit| follow[ -]?up| session)? notes?",
     "B: behavioral-health clinician note"),
    # carve-outs: deny wins over include
    ("deny.nursing", "deny", "(nursing|nsg)( [a-z/]+)? notes?", "E: nursing documentation"),
    ("deny.note_nursing", "deny", "notes? nursing", "E: '<x> note nursing'"),
    ("deny.nursing_suffix", "deny", _B + "(nursing|nsg)$", "E: '<x> nursing' (discharge summary nursing, telephone encounter nursing)"),
    ("deny.nursing_narrative", "deny", "(nursing|nsg) narrative", "E: nursing narrative"),
    ("deny.pathology", "deny", "patholog", "C: pathology"),
    ("deny.diagnostic", "deny", _B + "(imaging|radiology|laboratory|lab|diagnostic|x-?ray|xr|ct|mri|ultrasound|echo|ekg|ecg)" + _E,
     "C: diagnostic test vocabulary"),
    ("deny.admission_criteria", "deny", "admission criteria", "F: utilization-review form"),
    ("deny.anesthesia", "deny", "anesthesi", "C: anesthesia record"),
    ("deny.text_rendering", "deny", "[-\u2013\u2014] ?text$", "F: structured '- Text' renderings"),
    ("deny.instructions", "deny", "instruction", "F: instruction sheets (W9: an AVS section)"),
    ("deny.education", "deny", "education", "F: education material"),
    ("deny.referral", "deny", "referral", "D: referral/hand-off"),
    ("deny.consult_order", "deny", "consult(ation)? (order|request)s?", "D: consult order/request, not the consult note"),
)

# LOINC typeCode fallback (secondary key). Eligible by code only when the label hits no deny / DB
# exclude. The three result codes (imaging 18748-4, lab 11502-2, pathology 11526-1) are deliberately
# NOT allowed (W15); 34139-6 (nurse telephone note) is deliberately NOT allowed (W16).
LOINC_SYSTEM_PATTERN = "loinc"
LOINC_OID = "urn:oid:2.16.840.1.113883.6.1"
LOINC_ALLOW_CODES = ("11506-3", "34117-2", "11488-4", "34111-5", "18842-5", "34133-9", "34748-4", "28570-0", "11504-8")

_INC = [r for r in VISIT_SUMMARY_ALLOWLIST if r[1] == "include"]
_DEN = [r for r in VISIT_SUMMARY_ALLOWLIST if r[1] == "deny"]
_INC_COMPILED = [(r[0], re.compile(r[2])) for r in _INC]
_DEN_COMPILED = [(r[0], re.compile(r[2])) for r in _DEN]


def normalize_label(label: Optional[str]) -> str:
    """Whitespace-fold (incl. NBSP), trim spaces, lower-case. SQL twin: lower(btrim(regexp_replace(
    label, WS_CLASS_SQL, ' ', 'g')))."""
    if label is None:
        return ""
    return re.sub(WS_CLASS_PY, " ", label).strip(" ").lower()


def include_regex() -> str:
    """Alternation of every include pattern (the SQL ``~`` operand)."""
    return "|".join("(" + r[2] + ")" for r in _INC)


def deny_regex() -> str:
    """Alternation of every deny pattern (the SQL ``~`` operand)."""
    return "|".join("(" + r[2] + ")" for r in _DEN)


def loinc_code_matches(type_code: Optional[str], type_system: Optional[str]) -> bool:
    """LOINC fallback test. SQL twin: typeCode IN (...) AND (typeSystem ILIKE '%loinc%' OR
    btrim(typeSystem) = LOINC_OID). Epic ``urn:oid:1.2.840.114350...`` systems are local codes,
    not LOINC, and never match."""
    if not type_code or not type_system:
        return False
    if type_code not in LOINC_ALLOW_CODES:
        return False
    return LOINC_SYSTEM_PATTERN in type_system.lower() or type_system.strip(" ") == LOINC_OID


def match(
    type_label: Optional[str],
    type_code: Optional[str] = None,
    type_system: Optional[str] = None,
) -> Tuple[bool, Optional[str], Optional[str]]:
    """Return ``(eligible, include_rule_id_or_loinc, deny_rule_id)``.

    ``eligible`` is ``(include or LOINC) and not deny``. The second element is the first matching
    include rule id (or ``"loinc:<code>"`` when only the code qualifies); the third is the first
    matching deny rule id (set even when nothing includes the label).
    """
    lbl = normalize_label(type_label)
    inc = next((rid for rid, rx in _INC_COMPILED if lbl and rx.search(lbl)), None)
    den = next((rid for rid, rx in _DEN_COMPILED if lbl and rx.search(lbl)), None)
    by_code = loinc_code_matches(type_code, type_system)
    eligible = (inc is not None or by_code) and den is None
    return eligible, inc or ("loinc:" + type_code if by_code else None), den


def canonical_sha() -> str:
    payload = json.dumps(
        {
            "v": ALLOWLIST_VERSION,
            "rules": VISIT_SUMMARY_ALLOWLIST,
            "loinc": LOINC_ALLOW_CODES,
            "loinc_oid": LOINC_OID,
            "ws": WS_CLASS_SQL,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def sql_quote(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def render_allowlist_sql() -> str:
    """The generated CTE block: allow_rules + loinc_codes (standard_conforming_strings=on)."""
    lines = [
        "-- BEGIN GENERATED ALLOWLIST (do not edit by hand; render_allowlist_sql())",
        f"-- version={ALLOWLIST_VERSION} sha256={canonical_sha()} rules={len(VISIT_SUMMARY_ALLOWLIST)} loinc={len(LOINC_ALLOW_CODES)}",
        "allow_rules(rule_id, kind, pattern) as (values",
    ]
    body = [f"  ({sql_quote(r[0])},{sql_quote(r[1])},{sql_quote(r[2])})" for r in VISIT_SUMMARY_ALLOWLIST]
    lines.append(",\n".join(body) + "),")
    lines.append("loinc_codes(code) as (values " + ",".join(f"({sql_quote(c)})" for c in LOINC_ALLOW_CODES) + "),")
    lines.append("-- END GENERATED ALLOWLIST")
    return "\n".join(lines)


def label_telemetry_key(label: Optional[str], max_len: int = 64) -> str:
    """Normalized, length-capped label used as a telemetry map key ("(null)" for empty)."""
    lbl = normalize_label(label)
    return lbl[:max_len] if lbl else "(null)"


def iter_rule_ids(kind: Optional[str] = None) -> Iterable[str]:
    return (r[0] for r in VISIT_SUMMARY_ALLOWLIST if kind is None or r[1] == kind)
