# Adding Test Cases

## Adding a New Extraction Document

### Step 1: Create the fixture document
```bash
# Create the text file with clinical content
touch evals/fixtures/documents/NEW_DOC_NAME.txt
```

Write realistic clinical text. Include:
- Standard section headers (e.g., CHIEF COMPLAINT, ASSESSMENT AND PLAN, MEDICATIONS)
- At least one "interesting" clinical scenario for each dimension you want to test
- Some abbreviations to test patient_language
- Ideally one non-drug intervention that should NOT appear in medications
- Consider including a plausible-but-absent item (to use as a trap)

### Step 2: Create the ground truth file
```bash
touch evals/fixtures/ground_truth/NEW_DOC_NAME.json
```

Minimum viable ground truth (fill in relevant fields, leave empty arrays for inapplicable ones):
```json
{
  "document_type": "Progress Note",
  "expected_diagnoses": [
    ["Primary diagnosis", "abbreviation", "synonym"]
  ],
  "expected_medications": [
    ["Drug Name Xmg dose", "Drug Name Xmg"]
  ],
  "expected_lab_results": [],
  "acceptable_diagnoses": [
    ["Primary diagnosis", "abbreviation", "synonym", "additional variant"]
  ],
  "acceptable_medications": [
    ["Drug Name Xmg dose", "Drug Name Xmg", "Drug Name"]
  ],
  "forbidden_medications": [
    "Oxygen therapy", "oxygen", "nasal cannula"
  ],
  "trap_items": [
    "Item not in document but clinically plausible"
  ],
  "expected_abbreviation_expansions": {
    "HTN": "High blood pressure"
  },
  "notes": "KEY TEST: What makes this document interesting for the eval suite"
}
```

**GT writing tips**:
- Run the chain on your document first (manually), then use the output to calibrate expected items
- `expected_*` = items you're confident the chain should extract
- `acceptable_*` = all the ways the chain might validly phrase each item
- Start conservative with trap items — a false positive trap is worse than no trap

### Step 3: Register the document in `run_eval.py`
```python
# In evals/run_eval.py, find DOC_NAMES list:
DOC_NAMES = [
    "lab_report_cbc",
    "lab_report_metabolic",
    ...
    "NEW_DOC_NAME",    # Add here
]
```

Also register in `conftest.py` if using pytest:
```python
# In evals/conftest.py, find the extraction_results fixture:
DOC_NAMES = [
    "lab_report_cbc",
    ...
    "NEW_DOC_NAME",    # Add here
]
```

### Step 4: Run and validate
```bash
# Run eval on active version
uv run python evals/run_eval.py v002

# Or run only your new document via pytest
uv run pytest evals/test_extraction.py -k "NEW_DOC_NAME" -v
```

Review results and iterate on ground truth until scores reflect your intent. It's normal to adjust `acceptable_*` lists after seeing first-run output.

---

## Adding a New Synthesis Case

### Step 1: Create the case JSON
```bash
touch evals/fixtures/synthesis_cases/NEW_CASE_NAME.json
```

```json
{
  "name": "NEW_CASE_NAME",
  "description": "What multi-document scenario this case tests",
  "appointment_context": {
    "appointment_date": "2025-MM-DD",
    "purpose": "Reason for appointment / encounter type",
    "provider_name": "Dr. First Last"
  },
  "documents": [...],
  "expected_output": {...}
}
```

### Step 2: Define the documents
Choose 2–4 documents that:
- Share at least one medication or diagnosis (to test deduplication)
- Cover the same patient encounter realistically
- Have complementary information (not just the same document twice)

**Option A — Use existing fixtures**:
```json
"documents": [
  {
    "fixture_file": "progress_note_diabetes",
    "title": "Diabetes Follow-up Note",
    "date": "2025-10-15T10:00:00Z"
  },
  {
    "fixture_file": "lab_report_metabolic",
    "title": "Metabolic Panel Results",
    "date": "2025-11-20T08:00:00Z"
  }
]
```

**Option B — Inline document text** (for cases where no suitable fixture exists):
```json
{
  "extracted_text": "CONSULTATION NOTE\nPatient: ...",
  "title": "Cardiology Consult",
  "date": "2025-10-30T14:00:00Z"
}
```

### Step 3: Define the expected output
```json
"expected_output": {
  "expected_diagnoses_unique": [
    ["Type 2 Diabetes", "DM2"],
    ["High blood pressure", "HTN"]
  ],
  "expected_medications_unique": [
    ["Metformin", "Metformin 1000mg"],
    ["Lisinopril 10mg", "Lisinopril"]
  ],
  "medications_must_not_duplicate": ["Metformin"],
  "forbidden_medications": [
    "Oxygen therapy", "oxygen", "nasal cannula"
  ],
  "notes": "Metformin appears in both docs — must be deduplicated"
}
```

`medications_must_not_duplicate` documents which items are specifically being tested for deduplication (documentation only — the actual dedup scorer checks all pairs).

### Step 4: Register in `run_eval.py` and `conftest.py`
```python
# In evals/run_eval.py:
SYNTHESIS_CASE_NAMES = [
    "diabetes_followup",
    "cardiac_admission",
    "NEW_CASE_NAME",    # Add here
]

# In evals/conftest.py (synthesis_cases fixture):
SYNTHESIS_CASE_NAMES = [
    "diabetes_followup",
    "cardiac_admission",
    "NEW_CASE_NAME",    # Add here
]
```

### Step 5: Validate
```bash
uv run pytest evals/test_synthesis.py -k "NEW_CASE_NAME" -v
```

---

## Writing Good Trap Items

**Goal**: The LLM should not extract the trap item. A good trap is plausible but definitively absent.

**Process**:
1. Identify items commonly associated with the document's topic that are NOT in this specific document
2. Verify absence with grep: `grep -i "TRAP_ITEM" evals/fixtures/documents/DOC_NAME.txt`
3. Check for substring overlap with expected items (a trap overlapping an expected item causes false failures)

**Examples of good traps by document type**:

| Document Type | Good Trap Items |
|---------------|----------------|
| CBC lab report | Iron, Ferritin, Vitamin B12, Prothrombin time (not part of CBC) |
| Metabolic panel | CBC items (WBC, RBC), coagulation tests |
| Diabetes progress note | Insulin (if not prescribed), Glipizide (alternative not chosen), Losartan (not on their med list) |
| Discharge summary | Warfarin (if on different anticoagulant), ACE inhibitor (if on ARB instead) |
| Radiology report | Specific findings that imaging ruled OUT |

**Verification command**:
```bash
# Confirm all trap items are absent from document
for TRAP in "Ferritin" "Iron" "Vitamin B12"; do
  echo -n "$TRAP: "
  grep -ic "$TRAP" evals/fixtures/documents/lab_report_cbc.txt && echo "FOUND - DO NOT USE AS TRAP" || echo "absent (OK)"
done
```

---

## Ground Truth Iteration Patterns

After running evals, you'll need to refine ground truth. Here's when to do what:

| Scenario | Action |
|----------|--------|
| Chain extracted a valid form not in `acceptable_*` | Add to `acceptable_*` — GT was too narrow |
| Chain missed an expected item that IS in the document | Check if the prompt needs improving; also verify the item is in `expected_*` with correct synonyms |
| Chain included a trap item legitimately (item IS in document) | Remove from trap items; consider redesigning the trap |
| Chain correctly excludes a forbidden item | Verify forbidden item is listed in `forbidden_medications` |
| Accuracy score fails but items are genuinely valid | Expand `acceptable_*` list; don't change the prompt unless it's an extraction quality issue |
| Accuracy score fails because items are genuinely hallucinated | Prompt improvement needed; don't expand acceptable list to paper over real hallucinations |

**Key principle**: Ground truth should reflect what a correct extraction looks like, not what the current prompt produces. When in doubt, favor stricter ground truth and fix the prompt.
