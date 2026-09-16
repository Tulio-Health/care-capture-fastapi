# Public clinical document samples

Original downloaded documents from public educational/sample-report pages. These are clinical content examples, not Cerner production records. Publisher provenance is recorded; no independent claim of formal de-identification is made.

All five PDFs have native selectable text. They are not image-only scans. Live evaluation uses the separate image-only derivatives linked below. Original documents remain unchanged.

| File | Content | Pages | Publisher / source |
|---|---|---|---|
| [doctor_pediatric_progress_examples.pdf](doctor_pediatric_progress_examples.pdf) | Pediatric progress/SOAP notes | 2 | [University of Tennessee Health Science Center](https://www.uthsc.edu/pediatrics/clerkship/documents/progress-notes.pdf) |
| [lab_24hour_urine_sample.pdf](lab_24hour_urine_sample.pdf) | 24-hour urine report | 5 | [Labcorp Litholink](https://litholink.labcorp.com/sites/default/files/2025-08/Litholink%2024-hour%20Enhanced%20Report%20Sample%20-%20910235.pdf) |
| [lab_stone_urinalysis_sample.pdf](lab_stone_urinalysis_sample.pdf) | Stone urinalysis report | 4 | [Labcorp Dianon](https://dianon.labcorp.com/sites/default/files/2021-07/AH3500627%20CLN.pdf) |
| [lab_blood_test_sample_reports.pdf](lab_blood_test_sample_reports.pdf) | Blood-test sample reports | 29 | [Life Extension / Labcorp sample report](https://www.lifeextension.com/-/media/lef/files/pdf/sample_reports.pdf) |
| [doctor_medical_necessity_soap_example.pdf](doctor_medical_necessity_soap_example.pdf) | Treating-physician medical-necessity SOAP example | 2 | [National Functional Evaluations](https://nationalfe.com/images/SOAP%20sample%20NOT%20FOR%20ACTUAL%20USE.pdf) |

The pediatric PDF contains filled educational progress-note examples. The medical-necessity PDF is generic example wording; it is not a completed patient encounter. Lab PDFs are publisher-designated samples.

OCR-specific evaluation uses separately labeled image-only derivatives while retaining these original PDFs as reference. The blood-report collection is 29 pages; check pipeline page limits before using the whole file.

Downloaded for local QA review. Public availability is not an unrestricted redistribution license; preserve source attribution and publisher terms. File hashes and native-text/page counts are in manifest.json.

## Image-only OCR versions

[Six OCR PDFs and provenance](ocr/README.md) are available in `ocr/`. These converted copies have zero native text; originals above are unchanged. The blood-report collection is split into two files, preserving all 29 pages. The latest live OCR and summarization outcomes are saved locally in [the separate report](../../results/clinical_ocr_summary_live/report.html). Rejected or unprocessed documents do not have accepted summaries.

Run OCR followed by actual application summarization from the repository root:

```sh
python qa/summary_regression/run_clinical_ocr.py --summarize
```

Uses `qa/.env.regression.local` and its configured budgets. Only fully accepted OCR is summarized. The separate report is overwritten on each run; no database access or full-catalog regression is performed. OCR candidates and verification findings are retained for review.
