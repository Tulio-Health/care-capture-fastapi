# Scoring System Reference

## Dimension Weights and Thresholds

| Dimension | Weight | Threshold | Rationale |
|-----------|--------|-----------|-----------|
| `completeness` | 0.20 | 0.85 | Highest weight — missing critical info is a patient safety risk |
| `accuracy` | 0.20 | 0.85 | Equally critical — wrong info is worse than missing info |
| `hallucination` | 0.15 | 0.90 | Strict — invented medical facts are dangerous; higher threshold |
| `medication_filtering` | 0.15 | 0.95 | Very strict — non-drugs in medication list cause confusion and errors |
| `patient_language` | 0.10 | 0.80 | Moderate — abbreviations impede patient comprehension |
| `deduplication` | 0.10 | 0.85 | Synthesis quality — repeated items reduce trust |
| `clinical_summary` | 0.10 | 0.75 | Lowest threshold — LLM judging is approximate; some variance expected |

**Overall score** = weighted average of per-case dimension scores, averaged across all cases.
**Report passes** when `overall_average >= 0.85`.

---

## Fuzzy Matching System

All scorers use a two-step matching strategy:

```python
# Step 1: Substring check (case-insensitive)
if query.lower() in candidate.lower() or candidate.lower() in query.lower():
    return True  # Match found

# Step 2: Fuzzy similarity via SequenceMatcher
from difflib import SequenceMatcher
ratio = SequenceMatcher(None, a.lower(), b.lower()).ratio()
return ratio >= threshold  # Default threshold: 0.55
```

**Why substring first**: Handles abbreviations embedded in full names (e.g., "HTN" in "High blood pressure / HTN"). Fuzzy matching alone would fail this case.

**Threshold 0.55**: Permissive enough to handle:
- Dosage variations: "Metformin 1000mg" ↔ "Metformin 1000mg twice daily"
- Synonym overlap: "heart attack" ↔ "myocardial infarction" (fails fuzzy but passes completeness via synonym groups)
- Minor phrasing differences: "Type 2 Diabetes" ↔ "Type 2 Diabetes Mellitus"

**When fuzzy fails**: Very different phrasings (NSTEMI ↔ heart attack) require explicit synonym groups in ground truth — fuzzy alone cannot bridge them.

---

## Per-Scorer Details

### 1. Completeness (`scoring/completeness.py`)
**What**: Recall — fraction of expected items present in extraction output.

**Synonym group support**: `expected_*` fields can be lists of lists:
```json
"expected_diagnoses": [
  ["Type 2 Diabetes", "Type 2 Diabetes Mellitus", "DM2", "diabetes"],
  ["High blood pressure", "Hypertension", "HTN"]
]
```
Any synonym matching any extracted item = that expected item "found". Uses `flatten_synonyms()` internally.

**Scoring**:
```
score = matched_count / total_expected_items
```
Passes if score >= 0.85.

**What counts as matched**: substring OR fuzzy >= 0.55 between ANY expected synonym and ANY extracted item.

**Result examples**: Shows which expected items were NOT found (the misses).

---

### 2. Accuracy (`scoring/accuracy.py`)
**What**: Precision — fraction of extracted items supported by the acceptable set.

**Uses `acceptable_*` fields** (broader than `expected_*`):
```json
"acceptable_diagnoses": [
  ["Type 2 Diabetes", "DM2", ...],
  ["Shortness of breath", "dyspnea", ...]  // More variants than expected
]
```
If no `acceptable_*` present, falls back to `expected_*`.

**Scoring**:
```
score = supported_count / total_extracted_items
```
- No extracted items → score 1.0 (nothing to be inaccurate about)
- Items extracted but nothing in acceptable list → score 0.0

**What counts as supported**: substring OR fuzzy >= 0.55 between extracted item and ANY acceptable variant.

**Result examples**: Shows unsupported (hallucinated or wrong) items.

---

### 3. Hallucination (`scoring/hallucination.py`)
**What**: Trap item detection — things explicitly NOT in the source document.

**Trap items** are designed to be plausible but absent:
```json
"trap_items": ["Iron: 45 mcg/dL", "Ferritin: 12 ng/mL", "Vitamin B12", "Prothrombin time"]
```

**Scoring** (inverse):
```
score = 1.0 - (hallucinated_count / trap_count)
```
Threshold 0.90 means at most 1 trap in 10 can be hallucinated.

**Match logic**: If ANY extracted item matches a trap item (substring OR fuzzy), the trap is counted as hallucinated.

**Important**: Negation phrases like "No X found" in the source doc can still score a false positive if the LLM extracts "X" from that sentence. See [troubleshooting.md](troubleshooting.md).

---

### 4. Medication Filter (`scoring/medication_filter.py`)
**What**: Ensures non-drug interventions do NOT appear in the extracted medications list.

**Common forbidden items**:
- Oxygen therapy, supplemental O2, nasal cannula, O2 at X L/min
- IV fluids: Normal Saline, Lactated Ringer's, D5W
- Blood transfusions (packed red blood cells)
- Physical therapy, physiotherapy, cardiac rehabilitation
- Cold/heat packs
- Wound care, monitoring

**Scoring** (inverse):
```
score = 1.0 - (violation_count / forbidden_count)
```
Threshold 0.95 is very strict — nearly zero tolerance for non-drug items in medication lists.

---

### 5. Patient Language (`scoring/patient_language.py`)
**What**: Verifies medical abbreviations are expanded to patient-friendly terms.

**Per abbreviation, two checks**:
1. Abbreviation should NOT appear unexpanded in diagnoses/medications
2. Expanded form SHOULD appear in the output

```json
"expected_abbreviation_expansions": {
  "HTN": "High blood pressure",
  "DM2": "Type 2 Diabetes",
  "NSTEMI": "heart attack"
}
```

**Second-person check** (synthesis only):
- Clinical summary should use "you"/"your" language
- Extraction: `check_second_person=False` (clinical-facing, 3rd person OK)
- Synthesis: `check_second_person=True` (patient-facing)

**Scoring**:
```
score = checks_passed / total_checks
```
Each abbreviation = 2 checks (abbreviation absent + expansion present).

---

### 6. Deduplication (`scoring/deduplication.py`)
**What**: Near-duplicate detection in synthesis output lists.

**Logic**: Pairwise fuzzy comparison of all items in the list.
```
for each pair (a, b): if fuzzy_score(a, b) >= 0.80 → near-duplicate
score = 1.0 - (duplicate_pairs / total_pairs)
```
Threshold 0.85. Only 1 pair in ~7 allowed to be near-duplicates.

**Why 0.80 similarity**: Catches "Metformin 1000mg" + "Metformin HCl 500mg" as duplicates (same drug, different brand/dose), while allowing "Metformin" + "Atorvastatin" (similarity ~0.45) through.

**Applied to**: `diagnoses` and `medications` lists in synthesis output, separately.

---

### 7. Clinical Summary (`scoring/clinical_summary.py`)
**What**: LLM-as-judge for synthesis clinical_summary quality.

**4 sub-dimensions** (each 0–1, averaged):
1. **coverage** — Addresses: Why did the patient visit? What was found? What was done? What's the diagnosis? What are next steps?
2. **patient_friendliness** — Uses "you"/"your" throughout, plain language, no unexpanded abbreviations
3. **accuracy** — Consistent with appointment context (date, provider name, purpose)
4. **conciseness** — 2–6 sentences, no repetition, each sentence adds value

**Judge model**: Same model as chain (`gpt-4o` or equivalent via PydanticAI).
**Output type**: `JudgeScores` Pydantic model with 4 float fields.

**Fallback**: If judge fails (API error, parse error), returns `ScoreResult(score=0.5, passed=False)`. A 0.5 with no error messages indicates a judge failure, not a bad summary.

---

## Overall Score Calculation

**Per case**:
```python
applicable_dims = [d for d in DIMENSION_WEIGHTS if d in case.scores]
case_score = sum(
    case.scores[d].score * DIMENSION_WEIGHTS[d]
    for d in applicable_dims
) / sum(DIMENSION_WEIGHTS[d] for d in applicable_dims)
```
Weights renormalize if some dimensions are skipped (e.g., extraction cases don't have `deduplication`).

**Per report**:
```python
overall_average = mean(case.overall_score for case in cases)
dimension_averages = {dim: mean(case.scores[dim].score for case in cases if dim in case.scores)}
```
