# Ground Truth Format Reference

## Extraction Ground Truth JSON Schema

**File location**: `evals/fixtures/ground_truth/{doc_name}.json`

### Required fields

| Field | Type | Purpose |
|-------|------|---------|
| `document_type` | `string` | Human-readable doc type (e.g., "Progress Note", "Lab Report") |
| `expected_diagnoses` | `array` | Diagnoses that MUST be in extraction (for completeness) |
| `expected_medications` | `array` | Medications that MUST be in extraction (for completeness) |
| `expected_lab_results` | `array` | Lab values that MUST be in extraction (for completeness) |

### Optional fields

| Field | Type | Purpose |
|-------|------|---------|
| `acceptable_diagnoses` | `array` | All valid phrasings (for accuracy; broader than expected) |
| `acceptable_medications` | `array` | All valid medication phrasings (for accuracy) |
| `acceptable_lab_results` | `array` | All valid lab result phrasings (for accuracy) |
| `forbidden_medications` | `array` | Non-drug items that must NOT appear in medications list |
| `trap_items` | `array` | Items NOT in document — tests hallucination avoidance |
| `expected_abbreviation_expansions` | `object` | `{"HTN": "High blood pressure", "DM2": "Type 2 Diabetes"}` |
| `expected_procedures` | `array` | Procedures/interventions expected to be extracted |
| `expected_instructions` | `array` | Patient instructions expected in extraction |
| `expected_recommendations` | `array` | Clinical recommendations expected in extraction |
| `notes` | `string` | Human-readable explanation of key test intent |

---

## Synonym Group Format

Items in `expected_*` and `acceptable_*` arrays can be either strings or synonym lists:

```json
"expected_diagnoses": [
  "Appendicitis",                                    // plain string: exact or fuzzy match
  ["Type 2 Diabetes", "Type 2 Diabetes Mellitus", "DM2", "diabetes"],  // synonym group
  ["High blood pressure", "Hypertension", "HTN"]    // any synonym counts as "found"
]
```

**How synonym groups work**:
- If ANY synonym matches ANY extracted item → the expected item is "found"
- Enables flexibility without hardcoding a single acceptable phrasing
- Essential for medical terms that have multiple valid representations (NSTEMI, HTN, DM2)

**When to use synonym groups vs plain strings**:
- Use synonym groups when the LLM might use any of several valid phrasings
- Use plain strings when there's only one correct extraction (specific lab values, precise drug names with dose)

---

## `expected_*` vs `acceptable_*` Field Distinction

These two field types serve different scorers:

| Field | Scorer | Semantic |
|-------|--------|---------|
| `expected_*` | **Completeness** (recall) | Minimum viable extraction — must be present |
| `acceptable_*` | **Accuracy** (precision) | All valid variations — extracted items must match one of these |

**Why the distinction matters**:
- `expected_diagnoses` = 2 items → completeness requires both present
- `acceptable_diagnoses` = 5 items (superset) → accuracy allows any of the 5
- Without `acceptable_*`, accuracy falls back to `expected_*`

**Example**:
```json
{
  "expected_diagnoses": [
    ["Type 2 Diabetes", "DM2"],
    ["High blood pressure", "HTN"]
  ],
  "acceptable_diagnoses": [
    ["Type 2 Diabetes", "DM2", "diabetes mellitus"],
    ["High blood pressure", "HTN", "hypertension"],
    ["Shortness of breath", "dyspnea", "SOB"]    // Extra: acceptable but not required
  ]
}
```

---

## Trap Item Design Rules

Trap items test hallucination avoidance. They must be:

**✓ Plausible** — Clinically related to the document topic
- CBC trap: "Iron: 45 mcg/dL" (iron deficiency often co-checked with CBC, but not part of CBC panel)
- Diabetes trap: "Insulin" (common diabetes medication, but NOT prescribed in this note)

**✓ Absent** — Definitively NOT mentioned anywhere in the source document
- Verify with grep: `grep -i "ferritin" evals/fixtures/documents/lab_report_cbc.txt`
- Must not appear even in negation ("No insulin prescribed") — negations still cause false positives

**✗ Avoid: Negated items** — "No insulin" in document still has "insulin" as a substring
- Problem: LLM might extract "insulin" from "No insulin ordered"
- If present as negation: use as trap only if extraction prompt is expected to handle negation correctly

**✗ Avoid: Substring overlap with expected items**
- If "Aspirin 81mg" is an expected medication, don't use "Aspirin" as a trap item
- Fuzzy matching would catch it as hallucinated even if correctly extracted

**✗ Avoid: Very fuzzy-close items to expected items**
- Don't use "Losartan" as a trap if "Lisinopril" is expected — fuzzy similarity could be misleading

**Verification command**:
```bash
# Confirm trap item is truly absent from document
grep -i "ferritin" evals/fixtures/documents/lab_report_cbc.txt
# Expected: no output (item not present)
```

---

## Forbidden Medications Common Patterns

Items to include in `forbidden_medications` for documents that mention:

| Document mentions | Add to forbidden_medications |
|-------------------|------------------------------|
| Oxygen therapy | `"Oxygen therapy"`, `"supplemental oxygen"`, `"O2 via nasal cannula"`, `"nasal cannula"`, `"oxygen"` |
| IV fluids | `"IV Normal Saline"`, `"normal saline"`, `"Lactated Ringer's"`, `"D5W"`, `"IV fluids"` |
| Heparin infusion (anticoagulation bridge) | `"Heparin infusion"`, `"heparin"` (if only used as bridge and not discharged on it) |
| Physiotherapy | `"physiotherapy"`, `"cardiac rehabilitation"`, `"physical therapy"` |
| Cold/heat packs | `"cold packs"`, `"ice packs"`, `"heat packs"` |
| Wound care | `"wound care"`, `"dressing changes"` |
| Lab tests mentioned | `"CBC"`, `"complete blood count"`, `"BMP"`, `"CMP"` |

---

## Synthesis Case JSON Format

**File location**: `evals/fixtures/synthesis_cases/{case_name}.json`

```json
{
  "name": "case_name",
  "description": "Human-readable description of what this case tests",
  "appointment_context": {
    "appointment_date": "YYYY-MM-DD",
    "purpose": "Reason for appointment",
    "provider_name": "Dr. First Last"
  },
  "documents": [
    {
      "fixture_file": "progress_note_diabetes",   // loads from fixtures/documents/
      "title": "Display title for the document",
      "date": "2025-10-15T10:00:00Z"              // optional ISO8601
    },
    {
      "extracted_text": "Raw text...",             // alternative to fixture_file
      "title": "Inline document",
      "date": "2025-11-20T08:00:00Z"
    }
  ],
  "expected_output": {
    "expected_diagnoses_unique": [...],            // *_unique signals dedup is tested
    "expected_medications_unique": [...],
    "medications_must_not_duplicate": ["Metformin"],
    "forbidden_medications": [...],
    "notes": "Explanation of key test intent"
  }
}
```

**`fixture_file` references**: Use the filename without `.txt` extension. The conftest loads from `evals/fixtures/documents/{name}.txt`.

**`expected_diagnoses_unique` vs `expected_diagnoses`**: Both work; `_unique` suffix is a documentation convention signaling that deduplication is the key test — the scorer treats them the same.
