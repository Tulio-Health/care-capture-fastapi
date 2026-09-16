# Clinical review packet

Source regression: `20260916T093428.927162Z`. Review status: **PENDING**.

All documents are synthetic. No clinical approval is implied by automated checks or by this packet.

Reviewer name/role: __________  Review date: __________

For each case check transcription, table relationships, numbers/units, negation, medication status, procedure ordered versus performed, missing facts, and patient/source attribution. Record discrepancies using source page/section and output field. Do not infer undocumented clinical meaning.

Mock outputs establish application behavior only; they cannot establish OCR or model accuracy. Rejected candidates below were withheld from the user. Review the extracted text separately from the rejection decision.

This packet snapshots the saved text observations. Document and detailed-output links refer to the current QA files and may change after another regression; regenerate this packet before each review.

[Full regression report](results/report.html)

## PARSE-06 — CDA narrative and referral table

Execution: `application_mock`. Result: `REVIEW_REQUIRED`.

- [Source: clinical_cda.xml](testdata/clinical_cda.xml)

[Full observed output](results/outputs/PARSE-06-mock-1.json)

Required review: Verify heading and table associations, not only substring presence.

### Automated expectations and observations

```json
[
  {
    "path": "extraction.status",
    "op": "eq",
    "value": "success",
    "expected": "success",
    "actual": "success",
    "status": "PASS"
  },
  {
    "path": "extraction.text",
    "op": "contains",
    "value": "Iron deficiency anemia",
    "expected": "Iron deficiency anemia",
    "actual": "Assessment and Plan\nSYNTHETIC QA\nIron deficiency anemia.\nAbdominal ultrasound\nOrdered; not performed",
    "status": "PASS"
  },
  {
    "path": "extraction.text",
    "op": "contains",
    "value": "Ordered; not performed",
    "expected": "Ordered; not performed",
    "actual": "Assessment and Plan\nSYNTHETIC QA\nIron deficiency anemia.\nAbdominal ultrasound\nOrdered; not performed",
    "status": "PASS"
  },
  {
    "path": "boundary.raw_content_forwarded",
    "op": "eq",
    "value": false,
    "expected": false,
    "actual": false,
    "status": "PASS"
  }
]
```

### Actual extracted text

```text
Assessment and Plan
SYNTHETIC QA
Iron deficiency anemia.
Abdominal ultrasound
Ordered; not performed
```

### Actual returned summary / user message

```json
{
  "summary": {
    "clinical_summary": "Assessment and Plan\nSYNTHETIC QA\nIron deficiency anemia.\nAbdominal ultrasound\nOrdered; not performed",
    "key_insights": [],
    "documents_analyzed": 1,
    "diagnoses_mentioned": [],
    "procedures_mentioned": [],
    "medications_mentioned": [],
    "lab_results": [],
    "instructions": [],
    "follow_up": [],
    "recommendations": [],
    "risk_factors": [],
    "document_metadata": [],
    "extraction_errors": []
  },
  "display": {
    "text": "Assessment and Plan\nSYNTHETIC QA\nIron deficiency anemia.\nAbdominal ultrasound\nOrdered; not performed",
    "kind": "complete",
    "notice_is_prefix": false,
    "notice_count": 0,
    "template_used": false
  },
  "outcome_assessment": {
    "summary_generation": {
      "status": "PRODUCED",
      "reason": "A candidate summary was returned; consult clinical checks and required review."
    },
    "safety_containment": {
      "status": "NOT_ASSESSED",
      "reason": "No rejected clinical candidate was observed."
    }
  }
}
```

### Rejected candidates — NOT published

```json
{
  "candidates": [],
  "validation_issues": []
}
```

- [ ] Source-to-text accuracy checked (including tables, numbers and units).
- [ ] Returned content contains only supported facts and correct statuses.
- [ ] Missing content and any safe rejection were assessed.
- [ ] Live evidence is sufficient; mock-only or blocked evidence is not approved as clinical accuracy.

Decision: APPROVE / CHANGES REQUIRED / INSUFFICIENT EVIDENCE

Discrepancies, source references and reviewer rationale: ____________________

## VISION-ROTATED — Rotation preserves ordered status

Execution: `application_mock`. Result: `REVIEW_REQUIRED`.

- [Source: scan_rotated.png](testdata/scan_rotated.png)
- [Source: scan_gold.json](testdata/scan_gold.json)

[Full observed output](results/outputs/VISION-ROTATED-mock-1.json)

Required review: Real-model transcription evaluation required; a canned response only tests routing.

### Automated expectations and observations

```json
[
  {
    "path": "extraction.text",
    "op": "contains",
    "value": "not performed",
    "expected": "not performed",
    "actual": "[OCR page 1]\nSYNTHETIC QA DOCUMENT - NOT A REAL PATIENT\nPatient: QA Example 001\nEncounter: 2026-09-08\nAssessment: Iron deficiency anemia.\nPlan: Abdominal ultrasound ordered; not performed at this visit.\nMedication: Ferrous sulfate 325 mg orally once daily.\nFollow-up: Repeat CBC in 2 weeks.",
    "status": "PASS"
  },
  {
    "path": "clinical.current_performed_procedures",
    "op": "eq",
    "value": [],
    "expected": [],
    "actual": [],
    "status": "PASS"
  }
]
```

### Actual extracted text

```text
[OCR page 1]
SYNTHETIC QA DOCUMENT - NOT A REAL PATIENT
Patient: QA Example 001
Encounter: 2026-09-08
Assessment: Iron deficiency anemia.
Plan: Abdominal ultrasound ordered; not performed at this visit.
Medication: Ferrous sulfate 325 mg orally once daily.
Follow-up: Repeat CBC in 2 weeks.
```

### Actual returned summary / user message

```json
{
  "summary": {
    "clinical_summary": "[OCR page 1]\nSYNTHETIC QA DOCUMENT - NOT A REAL PATIENT\nPatient: QA Example 001\nEncounter: 2026-09-08\nAssessment: Iron deficiency anemia.\nPlan: Abdominal ultrasound ordered; not performed at this visit.\nMedication: Ferrous sulfate 325 mg orally once daily.\nFollow-up: Repeat CBC in 2 weeks.",
    "key_insights": [],
    "documents_analyzed": 1,
    "diagnoses_mentioned": [],
    "procedures_mentioned": [],
    "medications_mentioned": [],
    "lab_results": [],
    "instructions": [],
    "follow_up": [],
    "recommendations": [],
    "risk_factors": [],
    "document_metadata": [],
    "extraction_errors": []
  },
  "display": {
    "text": "[OCR page 1]\nSYNTHETIC QA DOCUMENT - NOT A REAL PATIENT\nPatient: QA Example 001\nEncounter: 2026-09-08\nAssessment: Iron deficiency anemia.\nPlan: Abdominal ultrasound ordered; not performed at this visit.\nMedication: Ferrous sulfate 325 mg orally once daily.\nFollow-up: Repeat CBC in 2 weeks.",
    "kind": "complete",
    "notice_is_prefix": false,
    "notice_count": 0,
    "template_used": false
  },
  "outcome_assessment": {
    "summary_generation": {
      "status": "PRODUCED",
      "reason": "A candidate summary was returned; consult clinical checks and required review."
    },
    "safety_containment": {
      "status": "NOT_ASSESSED",
      "reason": "No rejected clinical candidate was observed."
    }
  }
}
```

### Rejected candidates — NOT published

```json
{
  "candidates": [],
  "validation_issues": []
}
```

- [ ] Source-to-text accuracy checked (including tables, numbers and units).
- [ ] Returned content contains only supported facts and correct statuses.
- [ ] Missing content and any safe rejection were assessed.
- [ ] Live evidence is sufficient; mock-only or blocked evidence is not approved as clinical accuracy.

Decision: APPROVE / CHANGES REQUIRED / INSUFFICIENT EVIDENCE

Discrepancies, source references and reviewer rationale: ____________________

## VISION-REVIEW — Real-model visual fidelity evaluation

Execution: `application_mock`. Result: `REVIEW_REQUIRED`.

- [Source: scanned.pdf](testdata/scanned.pdf)
- [Source: mixed.pdf](testdata/mixed.pdf)
- [Source: mixed_region.pdf](testdata/mixed_region.pdf)
- [Source: scan_rotated.png](testdata/scan_rotated.png)
- [Source: scan_page1.webp](testdata/scan_page1.webp)
- [Source: scan_gold.json](testdata/scan_gold.json)

[Full observed output](results/outputs/VISION-REVIEW-mock-1.json)

Required review: Run this case in live mode and review every source image against the saved transcription. Mock evidence does not qualify OCR accuracy. Require exact numbers, units, negation and procedure status, no unsupported additions, and explicit disclosure of unreadable content. Record reviewer, model, source regions and discrepancies; review_complete and thresholds_met remain unapproved until recorded independent review.

### Automated expectations and observations

```json
[
  {
    "path": "boundary.raw_content_forwarded",
    "op": "eq",
    "value": false,
    "expected": false,
    "actual": false,
    "status": "PASS"
  },
  {
    "path": "coverage.all_pages_accounted",
    "op": "eq",
    "value": true,
    "expected": true,
    "actual": true,
    "status": "PASS"
  }
]
```

### Actual extracted text

```text
[OCR page 1]
SYNTHETIC QA DOCUMENT - NOT A REAL PATIENT
Patient: QA Example 001
Encounter: 2026-09-08
Assessment: Iron deficiency anemia.
Plan: Abdominal ultrasound ordered; not performed at this visit.
Medication: Ferrous sulfate 325 mg orally once daily.
Follow-up: Repeat CBC in 2 weeks.

[OCR page 2]
SYNTHETIC QA DOCUMENT - PAGE 2
Patient: QA Example 001
Ferritin: 8 ng/mL
Hemoglobin: 10.2 g/dL
No evidence of pneumonia.

[Page 1]
SYNTHETIC QA DOCUMENT - NOT A REAL PATIENT
Patient: QA Example 001
Encounter: 2026-09-08
Assessment: Iron deficiency anemia.
Plan: Abdominal ultrasound ordered; not performed at this visit.
Medication: Ferrous sulfate 325 mg orally once daily.
Follow-up: Repeat CBC in 2 weeks.

[OCR page 2]
SYNTHETIC QA DOCUMENT - PAGE 2
Patient: QA Example 001
Ferritin: 8 ng/mL
Hemoglobin: 10.2 g/dL
No evidence of pneumonia.

[OCR page 1]
SYNTHETIC QA DOCUMENT - NOT A REAL PATIENT
Patient: QA Example 001
Encounter: 2026-09-08
Assessment: Iron deficiency anemia.
Plan: Abdominal ultrasound ordered; not performed at this visit.
Medication: Ferrous sulfate 325 mg orally once daily.
Follow-up: Repeat CBC in 2 weeks.

[OCR page 2]
SYNTHETIC QA DOCUMENT - PAGE 2
Patient: QA Example 001
Ferritin: 8 ng/mL
Hemoglobin: 10.2 g/dL
No evidence of pneumonia.

[OCR page 1]
SYNTHETIC QA DOCUMENT - NOT A REAL PATIENT
Patient: QA Example 001
Encounter: 2026-09-08
Assessment: Iron deficiency anemia.
Plan: Abdominal ultrasound ordered; not performed at this visit.
Medication: Ferrous sulfate 325 mg orally once daily.
Follow-up: Repeat CBC in 2 weeks.

[OCR page 1]
SYNTHETIC QA DOCUMENT - NOT A REAL PATIENT
Patient: QA Example 001
Encounter: 2026-09-08
Assessment: Iron deficiency anemia.
Plan: Abdominal ultrasound ordered; not performed at this visit.
Medication: Ferrous sulfate 325 mg orally once daily.
Follow-up: Repeat CBC in 2 weeks.
```

### Actual returned summary / user message

```json
{
  "summary": {
    "clinical_summary": "[OCR page 1]\nSYNTHETIC QA DOCUMENT - NOT A REAL PATIENT\nPatient: QA Example 001\nEncounter: 2026-09-08\nAssessment: Iron deficiency anemia.\nPlan: Abdominal ultrasound ordered; not performed at this visit.\nMedication: Ferrous sulfate 325 mg orally once daily.\nFollow-up: Repeat CBC in 2 weeks.\n\n[OCR page 2]\nSYNTHETIC QA DOCUMENT - PAGE 2\nPatient: QA Example 001\nFerritin: 8 ng/mL\nHemoglobin: 10.2 g/dL\nNo evidence of pneumonia.\n\n[Page 1]\nSYNTHETIC QA DOCUMENT - NOT A REAL PATIENT\nPatient: QA Example 001\nEncounter: 2026-09-08\nAssessment: Iron deficiency anemia.\nPlan: Abdominal ultrasound ordered; not performed at this visit.\nMedication: Ferrous sulfate 325 mg orally once daily.\nFollow-up: Repeat CBC in 2 weeks.\n\n[OCR page 2]\nSYNTHETIC QA DOCUMENT - PAGE 2\nPatient: QA Example 001\nFerritin: 8 ng/mL\nHemoglobin: 10.2 g/dL\nNo evidence of pneumonia.\n\n[OCR page 1]\nSYNTHETIC QA DOCUMENT - NOT A REAL PATIENT\nPatient: QA Example 001\nEncounter: 2026-09-08\nAssessment: Iron deficiency anemia.\nPlan: Abdominal ultrasound ordered; not performed at this visit.\nMedication: Ferrous sulfate 325 mg orally once daily.\nFollow-up: Repeat CBC in 2 weeks.\n\n[OCR page 2]\nSYNTHETIC QA DOCUMENT - PAGE 2\nPatient: QA Example 001\nFerritin: 8 ng/mL\nHemoglobin: 10.2 g/dL\nNo evidence of pneumonia.\n\n[OCR page 1]\nSYNTHETIC QA DOCUMENT - NOT A REAL PATIENT\nPatient: QA Example 001\nEncounter: 2026-09-08\nAssessment: Iron deficiency anemia.\nPlan: Abdominal ultrasound ordered; not performed at this visit.\nMedication: Ferrous sulfate 325 mg orally once daily.\nFollow-up: Repeat CBC in 2 weeks.\n\n[OCR page 1]\nSYNTHETIC QA DOCUMENT - NOT A REAL PATIENT\nPatient: QA Example 001\nEncounter: 2026-09-08\nAssessment: Iron deficiency anemia.\nPlan: Abdominal ultrasound ordered; not performed at this visit.\nMedication: Ferrous sulfate 325 mg orally once daily.\nFollow-up: Repeat CBC in 2 weeks.",
    "key_insights": [],
    "documents_analyzed": 5,
    "diagnoses_mentioned": [],
    "procedures_mentioned": [],
    "medications_mentioned": [],
    "lab_results": [],
    "instructions": [],
    "follow_up": [],
    "recommendations": [],
    "risk_factors": [],
    "document_metadata": [],
    "extraction_errors": []
  },
  "display": {
    "text": "[OCR page 1]\nSYNTHETIC QA DOCUMENT - NOT A REAL PATIENT\nPatient: QA Example 001\nEncounter: 2026-09-08\nAssessment: Iron deficiency anemia.\nPlan: Abdominal ultrasound ordered; not performed at this visit.\nMedication: Ferrous sulfate 325 mg orally once daily.\nFollow-up: Repeat CBC in 2 weeks.\n\n[OCR page 2]\nSYNTHETIC QA DOCUMENT - PAGE 2\nPatient: QA Example 001\nFerritin: 8 ng/mL\nHemoglobin: 10.2 g/dL\nNo evidence of pneumonia.\n\n[Page 1]\nSYNTHETIC QA DOCUMENT - NOT A REAL PATIENT\nPatient: QA Example 001\nEncounter: 2026-09-08\nAssessment: Iron deficiency anemia.\nPlan: Abdominal ultrasound ordered; not performed at this visit.\nMedication: Ferrous sulfate 325 mg orally once daily.\nFollow-up: Repeat CBC in 2 weeks.\n\n[OCR page 2]\nSYNTHETIC QA DOCUMENT - PAGE 2\nPatient: QA Example 001\nFerritin: 8 ng/mL\nHemoglobin: 10.2 g/dL\nNo evidence of pneumonia.\n\n[OCR page 1]\nSYNTHETIC QA DOCUMENT - NOT A REAL PATIENT\nPatient: QA Example 001\nEncounter: 2026-09-08\nAssessment: Iron deficiency anemia.\nPlan: Abdominal ultrasound ordered; not performed at this visit.\nMedication: Ferrous sulfate 325 mg orally once daily.\nFollow-up: Repeat CBC in 2 weeks.\n\n[OCR page 2]\nSYNTHETIC QA DOCUMENT - PAGE 2\nPatient: QA Example 001\nFerritin: 8 ng/mL\nHemoglobin: 10.2 g/dL\nNo evidence of pneumonia.\n\n[OCR page 1]\nSYNTHETIC QA DOCUMENT - NOT A REAL PATIENT\nPatient: QA Example 001\nEncounter: 2026-09-08\nAssessment: Iron deficiency anemia.\nPlan: Abdominal ultrasound ordered; not performed at this visit.\nMedication: Ferrous sulfate 325 mg orally once daily.\nFollow-up: Repeat CBC in 2 weeks.\n\n[OCR page 1]\nSYNTHETIC QA DOCUMENT - NOT A REAL PATIENT\nPatient: QA Example 001\nEncounter: 2026-09-08\nAssessment: Iron deficiency anemia.\nPlan: Abdominal ultrasound ordered; not performed at this visit.\nMedication: Ferrous sulfate 325 mg orally once daily.\nFollow-up: Repeat CBC in 2 weeks.",
    "kind": "complete",
    "notice_is_prefix": false,
    "notice_count": 0,
    "template_used": false
  },
  "outcome_assessment": {
    "summary_generation": {
      "status": "PRODUCED",
      "reason": "A candidate summary was returned; consult clinical checks and required review."
    },
    "safety_containment": {
      "status": "NOT_ASSESSED",
      "reason": "No rejected clinical candidate was observed."
    }
  }
}
```

### Rejected candidates — NOT published

```json
{
  "candidates": [],
  "validation_issues": []
}
```

- [ ] Source-to-text accuracy checked (including tables, numbers and units).
- [ ] Returned content contains only supported facts and correct statuses.
- [ ] Missing content and any safe rejection were assessed.
- [ ] Live evidence is sufficient; mock-only or blocked evidence is not approved as clinical accuracy.

Decision: APPROVE / CHANGES REQUIRED / INSUFFICIENT EVIDENCE

Discrepancies, source references and reviewer rationale: ____________________

## DOCX-TABLE — Native Word table relationships

Execution: `application_mock`. Result: `REVIEW_REQUIRED`.

- [Source: clinical.docx](testdata/clinical.docx)

[Full observed output](results/outputs/DOCX-TABLE-mock-1.json)

Required review: Verify header/value/unit associations; text substring checks alone are insufficient.

### Automated expectations and observations

```json
[
  {
    "path": "extraction.status",
    "op": "eq",
    "value": "success",
    "expected": "success",
    "actual": "success",
    "status": "PASS"
  },
  {
    "path": "extraction.text",
    "op": "contains",
    "value": "Ferritin",
    "expected": "Ferritin",
    "actual": "Synthetic clinical report\nSYNTHETIC QA DOCUMENT - NOT A REAL PATIENT\nPatient: QA Example 001\nEncounter: 2026-09-08\nAssessment: Iron deficiency anemia.\nPlan: Abdominal ultrasound ordered; not performed at this visit.\nMedication: Ferrous sulfate 325 mg orally once daily.\nFollow-up: Repeat CBC in 2 weeks.\nTest | Value | Unit\nFerritin | 8 | ng/mL\nHemoglobin | 10.2 | g/dL",
    "status": "PASS"
  },
  {
    "path": "extraction.text",
    "op": "contains",
    "value": "10.2",
    "expected": "10.2",
    "actual": "Synthetic clinical report\nSYNTHETIC QA DOCUMENT - NOT A REAL PATIENT\nPatient: QA Example 001\nEncounter: 2026-09-08\nAssessment: Iron deficiency anemia.\nPlan: Abdominal ultrasound ordered; not performed at this visit.\nMedication: Ferrous sulfate 325 mg orally once daily.\nFollow-up: Repeat CBC in 2 weeks.\nTest | Value | Unit\nFerritin | 8 | ng/mL\nHemoglobin | 10.2 | g/dL",
    "status": "PASS"
  },
  {
    "path": "extraction.text",
    "op": "contains",
    "value": "g/dL",
    "expected": "g/dL",
    "actual": "Synthetic clinical report\nSYNTHETIC QA DOCUMENT - NOT A REAL PATIENT\nPatient: QA Example 001\nEncounter: 2026-09-08\nAssessment: Iron deficiency anemia.\nPlan: Abdominal ultrasound ordered; not performed at this visit.\nMedication: Ferrous sulfate 325 mg orally once daily.\nFollow-up: Repeat CBC in 2 weeks.\nTest | Value | Unit\nFerritin | 8 | ng/mL\nHemoglobin | 10.2 | g/dL",
    "status": "PASS"
  },
  {
    "path": "boundary.raw_content_forwarded",
    "op": "eq",
    "value": false,
    "expected": false,
    "actual": false,
    "status": "PASS"
  }
]
```

### Actual extracted text

```text
Synthetic clinical report
SYNTHETIC QA DOCUMENT - NOT A REAL PATIENT
Patient: QA Example 001
Encounter: 2026-09-08
Assessment: Iron deficiency anemia.
Plan: Abdominal ultrasound ordered; not performed at this visit.
Medication: Ferrous sulfate 325 mg orally once daily.
Follow-up: Repeat CBC in 2 weeks.
Test | Value | Unit
Ferritin | 8 | ng/mL
Hemoglobin | 10.2 | g/dL
```

### Actual returned summary / user message

```json
{
  "summary": {
    "clinical_summary": "Synthetic clinical report\nSYNTHETIC QA DOCUMENT - NOT A REAL PATIENT\nPatient: QA Example 001\nEncounter: 2026-09-08\nAssessment: Iron deficiency anemia.\nPlan: Abdominal ultrasound ordered; not performed at this visit.\nMedication: Ferrous sulfate 325 mg orally once daily.\nFollow-up: Repeat CBC in 2 weeks.\nTest | Value | Unit\nFerritin | 8 | ng/mL\nHemoglobin | 10.2 | g/dL",
    "key_insights": [],
    "documents_analyzed": 1,
    "diagnoses_mentioned": [],
    "procedures_mentioned": [],
    "medications_mentioned": [],
    "lab_results": [],
    "instructions": [],
    "follow_up": [],
    "recommendations": [],
    "risk_factors": [],
    "document_metadata": [],
    "extraction_errors": []
  },
  "display": {
    "text": "Synthetic clinical report\nSYNTHETIC QA DOCUMENT - NOT A REAL PATIENT\nPatient: QA Example 001\nEncounter: 2026-09-08\nAssessment: Iron deficiency anemia.\nPlan: Abdominal ultrasound ordered; not performed at this visit.\nMedication: Ferrous sulfate 325 mg orally once daily.\nFollow-up: Repeat CBC in 2 weeks.\nTest | Value | Unit\nFerritin | 8 | ng/mL\nHemoglobin | 10.2 | g/dL",
    "kind": "complete",
    "notice_is_prefix": false,
    "notice_count": 0,
    "template_used": false
  },
  "outcome_assessment": {
    "summary_generation": {
      "status": "PRODUCED",
      "reason": "A candidate summary was returned; consult clinical checks and required review."
    },
    "safety_containment": {
      "status": "NOT_ASSESSED",
      "reason": "No rejected clinical candidate was observed."
    }
  }
}
```

### Rejected candidates — NOT published

```json
{
  "candidates": [],
  "validation_issues": []
}
```

- [ ] Source-to-text accuracy checked (including tables, numbers and units).
- [ ] Returned content contains only supported facts and correct statuses.
- [ ] Missing content and any safe rejection were assessed.
- [ ] Live evidence is sufficient; mock-only or blocked evidence is not approved as clinical accuracy.

Decision: APPROVE / CHANGES REQUIRED / INSUFFICIENT EVIDENCE

Discrepancies, source references and reviewer rationale: ____________________

## VISION-CROP — Overlapping crops deduplicate without lost rows

Execution: `application_mock`. Result: `REVIEW_REQUIRED`.

- [Source: scan_page2.jpg](testdata/scan_page2.jpg)
- [Source: scan_gold.json](testdata/scan_gold.json)

[Full observed output](results/outputs/VISION-CROP-mock-1.json)

Required review: Mock crop responses verify routing and duplicate suppression only; real crop accuracy requires clinical review.

### Automated expectations and observations

```json
[
  {
    "path": "coverage.duplicate_regions",
    "op": "eq",
    "value": 0,
    "expected": 0,
    "actual": 0,
    "status": "PASS"
  },
  {
    "path": "coverage.complete",
    "op": "eq",
    "value": true,
    "expected": true,
    "actual": true,
    "status": "PASS"
  },
  {
    "path": "coverage.regions_checked",
    "op": "gte",
    "value": 2,
    "expected": 2,
    "actual": 3,
    "status": "PASS"
  }
]
```

### Actual extracted text

```text
[OCR page 1]
SYNTHETIC QA DOCUMENT - PAGE 2
Patient: QA Example 001
Ferritin: 8 ng/mL
Hemoglobin: 10.2 g/dL
No evidence of pneumonia.
```

### Actual returned summary / user message

```json
{
  "summary": {
    "clinical_summary": "[OCR page 1]\nSYNTHETIC QA DOCUMENT - PAGE 2\nPatient: QA Example 001\nFerritin: 8 ng/mL\nHemoglobin: 10.2 g/dL\nNo evidence of pneumonia.",
    "key_insights": [],
    "documents_analyzed": 1,
    "diagnoses_mentioned": [],
    "procedures_mentioned": [],
    "medications_mentioned": [],
    "lab_results": [
      "Ferritin: 8 ng/mL",
      "Hemoglobin: 10.2 g/dL"
    ],
    "instructions": [],
    "follow_up": [],
    "recommendations": [],
    "risk_factors": [],
    "document_metadata": [],
    "extraction_errors": []
  },
  "display": {
    "text": "[OCR page 1]\nSYNTHETIC QA DOCUMENT - PAGE 2\nPatient: QA Example 001\nFerritin: 8 ng/mL\nHemoglobin: 10.2 g/dL\nNo evidence of pneumonia.",
    "kind": "complete",
    "notice_is_prefix": false,
    "notice_count": 0,
    "template_used": false
  },
  "outcome_assessment": {
    "summary_generation": {
      "status": "PRODUCED",
      "reason": "A candidate summary was returned; consult clinical checks and required review."
    },
    "safety_containment": {
      "status": "NOT_ASSESSED",
      "reason": "No rejected clinical candidate was observed."
    }
  }
}
```

### Rejected candidates — NOT published

```json
{
  "candidates": [],
  "validation_issues": []
}
```

- [ ] Source-to-text accuracy checked (including tables, numbers and units).
- [ ] Returned content contains only supported facts and correct statuses.
- [ ] Missing content and any safe rejection were assessed.
- [ ] Live evidence is sufficient; mock-only or blocked evidence is not approved as clinical accuracy.

Decision: APPROVE / CHANGES REQUIRED / INSUFFICIENT EVIDENCE

Discrepancies, source references and reviewer rationale: ____________________

## DOC-LEGACY-VALID — Valid legacy Word parsed before clinical AI

Execution: `application_mock`. Result: `REVIEW_REQUIRED`.

- [Source: legacy_word.doc](testdata/legacy_word.doc)

[Full observed output](results/outputs/DOC-LEGACY-VALID-mock-1.json)

Required review: Review extracted legacy Word content against the source, including any table associations.

### Automated expectations and observations

```json
[
  {
    "path": "extraction.status",
    "op": "eq",
    "value": "success",
    "expected": "success",
    "actual": "success",
    "status": "PASS"
  },
  {
    "path": "extraction.adapter",
    "op": "eq",
    "value": "doc",
    "expected": "doc",
    "actual": "doc",
    "status": "PASS"
  },
  {
    "path": "boundary.raw_content_forwarded",
    "op": "eq",
    "value": false,
    "expected": false,
    "actual": false,
    "status": "PASS"
  }
]
```

### Actual extracted text

```text
SYNTHETIC QA DOCUMENT - NOT A REAL PATIENT
Patient: QA Example 001
Encounter: 2026-09-08
Assessment: Iron deficiency anemia.
Plan: Abdominal ultrasound ordered; not performed at this visit.
Medication: Ferrous sulfate 325 mg orally once daily.
Follow-up: Repeat CBC in 2 weeks.
```

### Actual returned summary / user message

```json
{
  "summary": {
    "clinical_summary": "SYNTHETIC QA DOCUMENT - NOT A REAL PATIENT\nPatient: QA Example 001\nEncounter: 2026-09-08\nAssessment: Iron deficiency anemia.\nPlan: Abdominal ultrasound ordered; not performed at this visit.\nMedication: Ferrous sulfate 325 mg orally once daily.\nFollow-up: Repeat CBC in 2 weeks.",
    "key_insights": [],
    "documents_analyzed": 1,
    "diagnoses_mentioned": [],
    "procedures_mentioned": [],
    "medications_mentioned": [],
    "lab_results": [],
    "instructions": [],
    "follow_up": [],
    "recommendations": [],
    "risk_factors": [],
    "document_metadata": [],
    "extraction_errors": []
  },
  "display": {
    "text": "SYNTHETIC QA DOCUMENT - NOT A REAL PATIENT\nPatient: QA Example 001\nEncounter: 2026-09-08\nAssessment: Iron deficiency anemia.\nPlan: Abdominal ultrasound ordered; not performed at this visit.\nMedication: Ferrous sulfate 325 mg orally once daily.\nFollow-up: Repeat CBC in 2 weeks.",
    "kind": "complete",
    "notice_is_prefix": false,
    "notice_count": 0,
    "template_used": false
  },
  "outcome_assessment": {
    "summary_generation": {
      "status": "PRODUCED",
      "reason": "A candidate summary was returned; consult clinical checks and required review."
    },
    "safety_containment": {
      "status": "NOT_ASSESSED",
      "reason": "No rejected clinical candidate was observed."
    }
  }
}
```

### Rejected candidates — NOT published

```json
{
  "candidates": [],
  "validation_issues": []
}
```

- [ ] Source-to-text accuracy checked (including tables, numbers and units).
- [ ] Returned content contains only supported facts and correct statuses.
- [ ] Missing content and any safe rejection were assessed.
- [ ] Live evidence is sufficient; mock-only or blocked evidence is not approved as clinical accuracy.

Decision: APPROVE / CHANGES REQUIRED / INSUFFICIENT EVIDENCE

Discrepancies, source references and reviewer rationale: ____________________
