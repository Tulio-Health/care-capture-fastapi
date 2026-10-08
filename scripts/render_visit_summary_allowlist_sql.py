#!/usr/bin/env python3
"""Render the read-only allowlist census SQL from the VISIT_SUMMARY_ALLOWLIST constant.

``scripts/sql/visit_summary_allowlist_census.template.sql`` holds the hand-written census queries
with placeholders; this renderer substitutes

* ``@@ALLOWLIST_BLOCK@@`` -> ``render_allowlist_sql()`` (the generated allow_rules / loinc_codes CTEs),
* ``@@VERSION@@`` / ``@@SHA256@@`` -> ``ALLOWLIST_VERSION`` / ``canonical_sha()``

and the result must equal the checked-in ``scripts/sql/visit_summary_allowlist_census.sql``
byte-for-byte (unit test ``test_visit_summary_allowlist_sql_in_sync``). The SQL contains a literal
NBSP (U+00A0) in the whitespace class, so the file is UTF-8 and is read/written in binary mode
(no newline translation). Do NOT build the census from SQLAlchemy ``literal_binds``: it doubles
backslashes.

Usage:
    python scripts/render_visit_summary_allowlist_sql.py            # print to stdout
    python scripts/render_visit_summary_allowlist_sql.py --write    # rewrite the checked-in .sql
    python scripts/render_visit_summary_allowlist_sql.py --check    # exit 1 if out of sync
"""
import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.app.services import visit_summary_allowlist as allowlist  # noqa: E402

SQL_DIR = REPO_ROOT / "scripts" / "sql"
TEMPLATE_PATH = SQL_DIR / "visit_summary_allowlist_census.template.sql"
OUTPUT_PATH = SQL_DIR / "visit_summary_allowlist_census.sql"


def render(template_text: str) -> str:
    out = template_text.replace("@@ALLOWLIST_BLOCK@@", allowlist.render_allowlist_sql())
    out = out.replace("@@VERSION@@", allowlist.ALLOWLIST_VERSION)
    return out.replace("@@SHA256@@", allowlist.canonical_sha())


def render_file() -> bytes:
    return render(TEMPLATE_PATH.read_bytes().decode("utf-8")).encode("utf-8")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--write", action="store_true", help="rewrite the checked-in census SQL"
    )
    group.add_argument(
        "--check", action="store_true", help="exit 1 if the checked-in SQL is stale"
    )
    args = parser.parse_args(argv)

    rendered = render_file()
    if args.write:
        OUTPUT_PATH.write_bytes(rendered)
        print(f"wrote {OUTPUT_PATH.relative_to(REPO_ROOT)} ({len(rendered)} bytes)")
        return 0
    if args.check:
        if OUTPUT_PATH.read_bytes() != rendered:
            print("census SQL is out of sync; run with --write", file=sys.stderr)
            return 1
        return 0
    sys.stdout.buffer.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
