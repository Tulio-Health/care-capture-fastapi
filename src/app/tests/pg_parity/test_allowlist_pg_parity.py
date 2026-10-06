"""T0b -- the shipped allowlist SQL predicates must equal ``match()`` in a REAL PostgreSQL.

The selection WHERE term (``fhir_resources._build_allowlist_predicates``) evaluates the include /
deny alternations with PostgreSQL's ``~`` (ARE) and the LOINC fallback with ``IN``/``ILIKE``; the
Python constant uses ``re``. Only portable syntax is allowed in the patterns (T0c) and this test
proves the two engines agree on every T0 row, every probe, whitespace/case/NBSP variants and the
code/system cases.

Marker ``pg_parity``; needs ``PARITY_PG_DSN`` (e.g. ``postgresql://user@host:5432/db``) and is
skipped when unset. It is literal-only: one ``SELECT ... FROM (VALUES ...)`` inside a READ ONLY
transaction; no table is read or written, so it is safe against any database (CI uses a
throwaway ``postgres:15`` service).

Runs through both the sync psycopg2 driver and asyncpg (the application's runtime driver, which
binds parameters server-side), because the two bind regex parameters differently.
"""
import os
import re

import pytest
from sqlalchemy import Integer, and_, column, create_engine, not_, or_, select, text, values
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import create_async_engine

from src.app.db.objects.repositories.fhir_resources import _build_allowlist_predicates
from src.app.services import visit_summary_allowlist as al
from src.app.tests.unit.visit_summary_allowlist_labels import LABEL_TABLE
from src.app.tests.unit.visit_summary_allowlist_probes import P

pytestmark = pytest.mark.pg_parity

DSN = os.environ.get("PARITY_PG_DSN")
if not DSN:
    pytest.skip("PARITY_PG_DSN is not set", allow_module_level=True)

LOINC = "http://loinc.org"
VARIANTS = [
    "Progress\u00a0Note", "  PROGRESS   NOTE ", "progress\tnote", "Progress\r\nNote", "H\u00a0&\u00a0P",
    "Patient\u00a0Instructions", "Nursing\u00a0Note", "Ed\u00a0Note", "Height Weight Allergy Rule \u2013 Text",
    "Progress Note \u2014 Text", "Progress Note-Text",
]
CODE_CASES = [  # (label, typeCode, typeSystem)
    (None, "11506-3", LOINC), (None, "11506-3", "http://LOINC.org"), (None, "11506-3", " http://loinc.org "),
    (None, "34133-9", al.LOINC_OID), (None, "34133-9", " " + al.LOINC_OID + " "), (None, "34133-9", al.LOINC_OID + ".1"),
    (None, "11506-3", "urn:oid:1.2.840.114350.1.13.0.1.7.2.688879"), (None, "11502-2", LOINC), (None, "18748-4", LOINC),
    (None, "34139-6", LOINC), (None, "99999-9", LOINC), (None, "11506-3", None), (None, None, LOINC), ("", "11488-4", LOINC),
    ("Patient Instructions", "11506-3", LOINC), ("Diagnostic Imaging Study", "34111-5", LOINC),
    ("Progress Note", "11506-3", LOINC), ("Other", "28570-0", LOINC), ("Nursing Note", "11504-8", LOINC),
] + [(None, code, LOINC) for code in al.LOINC_ALLOW_CODES]


def _cases():
    seen, cases = set(), []

    def add(label, code=None, system=None):
        key = (label, code, system)
        if key not in seen:
            seen.add(key)
            cases.append(key)

    for _env, label, *_rest in LABEL_TABLE:
        add(label)
    for label, _expected in P:
        add(label)
    for label in VARIANTS:
        add(label)
    for case in CODE_CASES:
        add(*case)
    return cases


CASES = _cases()


def _data(label, code, system):
    return {"type": label, "typeCode": code, "typeSystem": system}  # JSON null when None


def _python_expected(label, code, system):
    lbl = al.normalize_label(label)
    inc = bool(lbl and re.search(al.include_regex(), lbl))
    den = bool(lbl and re.search(al.deny_regex(), lbl))
    loinc = al.loinc_code_matches(code, system)
    eligible = (inc or loinc) and not den
    # the per-rule matcher must agree with the alternation form the SQL uses
    assert al.match(label, code, system)[0] is eligible
    return inc, loinc, den, eligible


def _query():
    rows = [(i, _data(*case)) for i, case in enumerate(CASES)]
    v = values(column("rid", Integer), column("data", JSONB), name="v").data(rows)
    inc, loinc, den = _build_allowlist_predicates(v.c.data)
    eligible = and_(or_(inc, loinc), not_(den))
    return select(v.c.rid, inc.label("inc"), loinc.label("loinc"), den.label("den"), eligible.label("eligible")).order_by(v.c.rid)


def _check(result_rows):
    assert len(result_rows) == len(CASES)
    mismatches = []
    for rid, inc, loinc, den, eligible in result_rows:
        case = CASES[rid]
        expected = _python_expected(*case)
        if (inc, loinc, den, eligible) != expected:
            mismatches.append((case, (inc, loinc, den, eligible), expected))
    assert not mismatches, f"{len(mismatches)}/{len(CASES)} PG != Python mismatches: {mismatches[:5]}"


def test_case_corpus_covers_every_t0_row_probe_and_code_case():
    assert len(CASES) >= len(LABEL_TABLE) // 2 + 113  # de-duplicated, but nothing is dropped silently
    assert len(CASES) >= 250
    for _env, label, *_rest in LABEL_TABLE:
        assert (label, None, None) in CASES
    for label, _e in P:
        assert (label, None, None) in CASES


def test_sync_psycopg2_parity():
    url = re.sub(r"^postgres(ql)?(\+\w+)?://", "postgresql+psycopg2://", DSN)
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            conn.execute(text("SET TRANSACTION READ ONLY"))
            _check(conn.execute(_query()).all())
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_async_asyncpg_parity():
    url = re.sub(r"^postgres(ql)?(\+\w+)?://", "postgresql+asyncpg://", DSN)
    url = re.sub(r"([?&])sslmode=[^&]*&?", r"\1", url).rstrip("?&")
    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SET TRANSACTION READ ONLY"))
            _check((await conn.execute(_query())).all())
    finally:
        await engine.dispose()


def test_server_regex_semantics_match_python_on_boundaries():
    """Direct literal probes of the ARE constructs the patterns rely on (no `\\b`, `\\y`, escapes)."""
    url = re.sub(r"^postgres(ql)?(\+\w+)?://", "postgresql+psycopg2://", DSN)
    engine = create_engine(url)
    cases = [
        ("avs", al._B + "avs" + al._E, True), ("xavsx", al._B + "avs" + al._E, False),
        ("c-cda", al._B + "(ccd|c-?cda)" + al._E, True), ("progress  note", "progress notes?", False),
        ("a \u2013 text", "[-\u2013\u2014] ?text$", True), ("a\u2014text", "[-\u2013\u2014] ?text$", True),
    ]
    try:
        with engine.connect() as conn:
            conn.execute(text("SET TRANSACTION READ ONLY"))
            for literal, pattern, expected in cases:
                got = conn.execute(text("SELECT CAST(:s AS text) ~ CAST(:p AS text)"), {"s": literal, "p": pattern}).scalar()
                assert got is expected is bool(re.search(pattern, literal)), (literal, pattern)
    finally:
        engine.dispose()
