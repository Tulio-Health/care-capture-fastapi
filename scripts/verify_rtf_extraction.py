#!/usr/bin/env python3
"""Operator entry point for PR-1's RTF merge gate.

Read-only S3 GET; no DB, no deploy. Same check as
test_document_extraction_rtf.py::test_extract_from_rtf_against_real_prod_artifact,
for when a pytest run is inconvenient.

Usage:
    uv run python scripts/verify_rtf_extraction.py <s3-key> [--bucket <bucket>]
"""

import argparse

import boto3

from src.app.services.document_extraction import DocumentTextExtractor

LANDMARKS = ["Assessment/Plan", "Follow up", "Return in"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("s3_key", help="S3 object key of the RTF fixture")
    parser.add_argument("--bucket", default="carecapture-prod-storage")
    args = parser.parse_args()

    content = (
        boto3.client("s3")
        .get_object(Bucket=args.bucket, Key=args.s3_key)["Body"]
        .read()
    )
    text = DocumentTextExtractor()._extract_from_rtf(content, args.s3_key)

    print(f"Raw bytes: {len(content)}, extracted chars: {len(text)}")
    print(f"Markup-stripped ratio: {1 - len(text) / len(content):.2%}")
    for landmark in LANDMARKS:
        print(f"  {'FOUND' if landmark in text else 'MISSING'}: {landmark!r}")

    if not all(landmark in text for landmark in LANDMARKS):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
