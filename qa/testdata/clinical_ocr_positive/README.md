# Small clinical OCR controls

Two synthetic, clearly printed single-page clinical documents and one public pen-written prescription demonstration. All OCR PDFs contain images only, with no native text. These are positive-path candidates, not guaranteed passes; retain every outcome.

The synthetic note tests negation and ordered versus performed status. The lab report tests values, units and reference ranges. The handwriting sample tests ambiguous quantities: x1/x2 must not become invented dose instructions. It is not a full hospital visit record.

Public handwriting source: https://github.com/ShubhamRaorane/Handwritten-Prescription-Medicine-Recognition (PrescriptionDetection/static/uploadedFiles/demo.jpeg). Original image unchanged. Public availability is not a claim of unrestricted redistribution rights. Provenance and SHA-256 hashes are in ocr/manifest.json.

Reference text and expectations are QA-only: they are not supplied to the OCR or summary models. No production prompts, validators or thresholds are changed for these examples. Review source, extracted text and summary together; model acceptance is not clinical approval.

Run from the repository root:

```sh
python qa/summary_regression/run_clinical_ocr.py --summarize --data-dir qa/testdata/clinical_ocr_positive/ocr --results-dir qa/results/clinical_ocr_positive_live
```

Uses the existing qa/.env.regression.local key and limits, no database access. Results overwrite only this separate result folder. The earlier six-document rejection report is retained.
