# Prompt Engineering Guide

## v001 → v002: What Changed and Why

v001 was a direct copy of the production prompts. v002 was created after analyzing the baseline eval results and fixing four key failure patterns:

### Problem 1: Abbreviations Not Expanded (patient_language: 0.73)
**Root cause**: Prompt listed "expand abbreviations" as a general guideline but didn't provide a conversion table. LLMs follow examples, not vague rules.

**Fix**: Added an explicit medical term conversion table in the extraction prompt:
```
MEDICAL TERM CONVERSIONS (always apply):
- HTN → High blood pressure
- DM2 / Type 2 DM → Type 2 Diabetes
- NSTEMI → Heart attack
- CAD → Coronary artery disease
- HLD / Hyperlipidemia → High cholesterol
- CKD → Chronic kidney disease
- SOB → Shortness of breath
```

**Lesson**: Specific conversion tables outperform general instructions. LLMs need examples, not categories.

---

### Problem 2: Missing Diagnoses (completeness: 0.65)
**Root cause**: Prompt said "extract diagnoses from Assessment section" — but diagnoses appear in multiple places (Chief Complaint, HPI, Impression, Plan headers).

**Fix**: Updated extraction instructions to pull diagnoses from ALL sections:
> "Extract diagnoses and conditions from the entire document: Assessment/Plan section, ICD-10 codes and their descriptions, Chief Complaint, Impression (radiology), and any condition mentioned as context for medication decisions."

**Lesson**: Enumerate all source locations explicitly. "Extract from the document" is too vague.

---

### Problem 3: Conditional Medications Incorrectly Extracted (accuracy: 0.76)
**Root cause**: "Consider starting X if Y" or "X was offered but declined" appeared as extracted medications.

**Fix**: Added explicit rule:
> "MEDICATIONS LIST: Include only medications that are actively prescribed or administered. Do NOT include:
> - Medications mentioned as possibilities ('consider', 'if needed', 'PRN basis' without active use)
> - Medications offered but declined by patient
> - Medications mentioned in historical context only ('previously on X')"

**Note**: PRN (as-needed) medications that ARE actively prescribed should still be included.

**Lesson**: The LLM needs explicit exclusion rules, not just inclusion rules. Default behavior is to include anything that looks like a medication name.

---

### Problem 4: Non-Drug Items in Medications (medication_filtering: 0.83)
**Root cause**: Extraction prompt mentioned excluding "IV fluids and oxygen" but didn't cover the full range of non-drug interventions.

**Fix**: Replaced vague mention with explicit ALL-CAPS rule block:
> "NEVER include in medications:
> - Oxygen therapy, supplemental O2, nasal cannula, oxygen at X L/min
> - IV fluids (Normal Saline, Lactated Ringer's, D5W)
> - Blood transfusions, packed red blood cells
> - Physical therapy, physiotherapy, cardiac rehabilitation
> - Cold packs, heat packs, wound care, monitoring"

**Lesson**: ALL CAPS draws LLM attention to critical rules. A bulleted forbidden-list works better than prose instructions.

---

## Dimension-Specific Fix Patterns

### Completeness (recall too low)

**Diagnosis**: Read the failing case result — which expected items are missing? Open the source document and find where the missed item appears.

**Common causes and fixes**:

| Cause | Fix |
|-------|-----|
| Diagnosis buried in ICD-10 code only | Add "extract diagnoses from ICD-10 codes and their descriptions" |
| Lab result format mismatch (expected "WBC: 11.8 K/uL" but extracted "WBC 11.8") | Expand `expected_lab_results` acceptable formats, or normalize extraction format |
| Abbreviation in source, expansion in expected | Add synonym group: `["WBC", "White Blood Cell Count"]` |
| Item in "Plan" section, not "Assessment" | Update prompt to extract from all sections |
| Items extracted but with extra text | Expand `acceptable_*` list to include the verbose form |

**Quick check**: Run `grep -i "MISSED_ITEM" evals/fixtures/documents/DOC_NAME.txt` to confirm the item is actually in the document.

---

### Accuracy (precision too low — hallucinations via wrong source)

**Diagnosis**: Which extracted items are "unsupported" by the acceptable list? Are they in the source document but missing from the acceptable list, OR are they genuinely hallucinated?

**Two different problems, two different fixes**:

| Problem | Fix |
|---------|-----|
| Item IS in document but NOT in `acceptable_*` | Add to `acceptable_diagnoses`/`acceptable_medications` — GT was too narrow |
| Item is NOT in document (true hallucination) | Tighten prompt: add explicit "do not infer or add facts not stated" |
| Item is a conditional/historical med | Add conditional medication exclusion rule to prompt |

---

### Hallucination (trap items being extracted)

**Diagnosis**: Which trap items appeared in extraction? Check if the source document mentions the trap item in ANY context (even negation).

**Common causes and fixes**:

| Cause | Fix |
|-------|-----|
| Trap item appears in negation ("No X prescribed") | Strengthen negation handling: "Do not extract items mentioned as absent, denied, or not present" |
| Trap item is clinically adjacent (related lab test) | Accept this as a genuine hallucination — tighten prompt |
| Trap item fuzzy-matches something legitimate | Review trap design — may need to remove this trap item |
| LLM "completing" a standard clinical picture | Add: "Only extract items explicitly documented, not standard-of-care assumptions" |

---

### Medication Filtering (non-drugs in medications list)

**Diagnosis**: Which forbidden items appeared in the medications list? Read the source document — how is that item phrased?

**Common causes and fixes**:

| Cause | Fix |
|-------|-----|
| "Oxygen 2L/min" → extracted as medication | Add "O2", "oxygen at", "L/min" variants to forbidden list; add to prompt ALL-CAPS block |
| "Normal Saline 0.9%" → extracted | Add IV fluid variations to forbidden list and prompt |
| Non-drug appears under "Treatment" header | Clarify: "medications = drug-based treatments only; exclude physical interventions, fluids, gases" |

---

### Patient Language (abbreviations not expanded)

**Diagnosis**: Which abbreviations appear unexpanded? Are they in the `expected_abbreviation_expansions` dict?

**Fix pattern**:
1. Add abbreviation to the conversion table in the extraction/synthesis prompt
2. Use specific "A → B" format, not prose instructions
3. Make sure the expanded form appears in ground truth `expected_*` lists as a synonym

**Common abbreviations to add**: COPD, CHF, AFib, PVD, DVT, PE, GI, UTI, BPH, OSA

---

### Deduplication (near-duplicates in synthesis)

**Diagnosis**: Which item pairs are flagged as duplicates? Are they truly the same drug/diagnosis, or is the similarity threshold too aggressive?

| Cause | Fix |
|-------|-----|
| Same drug, different docs (e.g., "Metformin 1000mg" + "Metformin HCl 500mg") | Strengthen synthesis dedup instructions: "consolidate identical medications across sources" |
| Similar-sounding but distinct (e.g., "Metformin" + "Metoprolol") | Review threshold — may be a scorer false positive; verify fuzzy score |
| Diagnosis stated differently per document | Add to synthesis prompt: "use consistent, patient-friendly terminology for the same condition across documents" |

---

### Clinical Summary (LLM judge scoring low)

**Diagnosis**: Read the `examples` field in the score result — which sub-dimension scored lowest?

| Sub-dimension low | Fix |
|-------------------|-----|
| `coverage` | Ensure synthesis prompt requires: why visit, what found, what done, diagnosis, next steps |
| `patient_friendliness` | Strengthen "you"/"your" requirement and abbreviation expansion in synthesis prompt |
| `accuracy` | Ensure appointment context (date, provider, purpose) is passed through to synthesis agent |
| `conciseness` | Add sentence count requirement: "Limit clinical_summary to 3-5 sentences" |

---

## Prompt Structure Best Practices

| Pattern | Avoid | Prefer |
|---------|-------|--------|
| Critical rules | "try to exclude oxygen" | "NEVER include: oxygen, IV fluids, ..." |
| Abbreviation expansion | "expand medical abbreviations" | Explicit conversion table |
| Source locations | "extract from the document" | "extract from: Assessment, ICD-10 codes, Chief Complaint, Impression" |
| Conditional exclusions | *(no mention)* | "Do NOT include medications mentioned as 'consider', 'if needed', 'offered but declined'" |
| Language style | "use plain language" | "Use 'you'/'your' throughout the clinical_summary" |
| Extraction scope | "extract relevant lab values" | "extract ALL lab values with their reference ranges" |

**Consistency between extraction and synthesis prompts**: Both prompts must have the same conversion table and the same non-drug exclusion list. Divergence causes inconsistent behavior between single-doc and multi-doc cases.
