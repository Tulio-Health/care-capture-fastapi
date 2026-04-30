---
name: eval-prompts
description: Run, analyze, iterate, and troubleshoot the clinical document summarization eval harness. Triggers on: eval, prompt tuning, scoring, compare prompts, add test case, ground truth, dimension scores, prompt version, hallucination score, completeness score, medication filtering, patient language, deduplication, clinical summary judge, run evals, eval results, prompt iteration, v001 v002.
allowed-tools: [Bash, Read, Write, Edit, Glob, Grep]
---

# Eval-Prompts Skill

Operate the clinical document summarization eval harness in `evals/`. This system evaluates the `AttachmentSummarizationChain` across 7 scored dimensions on 10 test cases (8 extraction + 2 synthesis).

---

## Current State

| Item | Value |
|------|-------|
| Active version | `v002` |
| Overall score | 0.9939 |
| Cases passing | 10/10 |
| Tracked in | `evals/prompts/current.json` |

---

## Quick-Start Commands

```bash
# Run full eval on active version (reads current.json)
uv run python evals/run_eval.py v002

# Run eval on a specific version
uv run python evals/run_eval.py v003

# Compare two versions (uses most recent result file for each)
uv run python evals/compare.py v001 v002

# Compare specific result files directly
uv run python evals/compare.py evals/results/v001_20260319_193436.json evals/results/v002_20260319_225716.json

# Run pytest suite (slower — LLM calls not shared across test processes)
uv run pytest evals/ -v

# Run single dimension tests only
uv run pytest evals/test_extraction.py -k "hallucination" -v

# Run single document
uv run pytest evals/test_extraction.py -k "lab_report_cbc" -v

# Run synthesis tests only
uv run pytest evals/test_synthesis.py -v

# List all result files
ls -lt evals/results/*.json | head -20
```

---

## Iteration Workflow

```
1. RUN       uv run python evals/run_eval.py v002
2. ANALYZE   Read result JSON → identify lowest dimension scores
3. CREATE    cp -r evals/prompts/v002 evals/prompts/v003
             Edit evals/prompts/v003/extraction_prompt.txt or synthesis_prompt.txt
             Edit evals/prompts/v003/notes.md (document what changed and why)
4. COMPARE   uv run python evals/run_eval.py v003
             uv run python evals/compare.py v002 v003
5. PROMOTE   Edit evals/prompts/current.json → set version to v003
             Update src/app/chains/attachment_summarization/chain.py with new prompt text
```

**Never edit prompts in `src/app/chains/` directly during iteration.** Always iterate in `evals/prompts/vXXX/` first, then promote after passing evals.

---

## Scoring Dimensions Overview

| Dimension | Weight | Threshold | What It Measures |
|-----------|--------|-----------|------------------|
| `completeness` | 0.20 | 0.85 | Recall — were all expected items extracted? |
| `accuracy` | 0.20 | 0.85 | Precision — are extracted items supported by source? |
| `hallucination` | 0.15 | 0.90 | Were trap items (things NOT in doc) avoided? |
| `medication_filtering` | 0.15 | 0.95 | Were non-drug interventions excluded from medications? |
| `patient_language` | 0.10 | 0.80 | Were medical abbreviations expanded to plain language? |
| `deduplication` | 0.10 | 0.85 | Were near-duplicate items merged in synthesis output? |
| `clinical_summary` | 0.10 | 0.75 | LLM judge: coverage, friendliness, accuracy, conciseness |

**Overall score** = weighted average of all applicable dimensions per case, then averaged across cases.
**Passes** if overall >= 0.85 and all per-dimension averages >= their thresholds.

---

## Key File Paths

| Path | Purpose |
|------|---------|
| `evals/run_eval.py` | Standalone eval runner (no pytest) |
| `evals/compare.py` | Side-by-side version comparison |
| `evals/conftest.py` | Pytest session fixtures (caches LLM calls) |
| `evals/test_extraction.py` | 8 docs × 5 dimension tests (parametrized) |
| `evals/test_synthesis.py` | 2 cases × 5 tests (parametrized) |
| `evals/scoring/types.py` | Weights, thresholds, fuzzy matching utilities |
| `evals/scoring/` | 7 scorer modules (one per dimension) |
| `evals/fixtures/documents/` | 8 clinical text fixtures |
| `evals/fixtures/ground_truth/` | 8 GT JSON files (one per document) |
| `evals/fixtures/synthesis_cases/` | 2 multi-document synthesis cases |
| `evals/prompts/current.json` | Active version pointer |
| `evals/prompts/v001/` | Baseline prompts (production copy) |
| `evals/prompts/v002/` | Current prompts (active, all tests pass) |
| `evals/results/` | JSON eval reports (gitignored except .gitkeep) |
| `src/app/chains/attachment_summarization/chain.py` | Production chain (update after promotion) |

---

## Reference Files

- [references/scoring-system.md](references/scoring-system.md) — How each of the 7 scorers works, fuzzy matching details, synonym groups, weights and thresholds with rationale
- [references/ground-truth-format.md](references/ground-truth-format.md) — GT JSON schema, expected vs acceptable fields, synonym group format, trap item design rules
- [references/prompt-engineering-guide.md](references/prompt-engineering-guide.md) — v001→v002 lessons, dimension-specific diagnostic and fix patterns
- [references/adding-test-cases.md](references/adding-test-cases.md) — How to add new extraction documents, synthesis cases, and write good trap items
- [references/troubleshooting.md](references/troubleshooting.md) — Hallucination false positives, fuzzy failures, transient errors, score stagnation

---

## Test Suite Structure

**Extraction tests** (`test_extraction.py`): 8 documents × 5 dimensions = up to 40 test cases
- Each document tested on: completeness, accuracy, hallucination, medication_filtering, patient_language
- Tests skip gracefully when ground truth fields are empty (e.g., no trap items for a doc)
- LLM calls run once per session (session-scoped fixture in conftest.py)

**Synthesis tests** (`test_synthesis.py`): 2 cases × 5 tests = 10 test cases
- Each synthesis case tested on: deduplication (diagnoses), deduplication (medications), medication_filtering, completeness, clinical_summary
- Full pipeline run once per case (extraction + synthesis)

**Total**: 10 cases scored, 50 individual test assertions

---

## Documents in the Eval Suite

| Document | Type | Key Dimensions Tested |
|----------|------|-----------------------|
| `lab_report_cbc` | Lab Report | Hallucination (CBC-only values), accurate lab extraction |
| `lab_report_metabolic` | Lab Report | Completeness across full metabolic panel |
| `progress_note_diabetes` | Progress Note | Medication filtering (O2 via nasal cannula), abbreviation expansion (HTN, DM2) |
| `discharge_summary_cardiac` | Discharge Summary | Medication filtering (IV saline, O2, physiotherapy), abbreviations (NSTEMI, HTN) |
| `radiology_mri_knee` | Radiology Report | Hallucination (imaging findings vs invented items), no medications expected |
| `prescription_multidrug` | Prescription | Completeness across all prescribed drugs |
| `consult_note_cardiology` | Consult Note | Accurate extraction, conditional medication handling |
| `operative_report_appendectomy` | Operative Report | Procedure extraction, medication filtering (surgical materials) |
| `diabetes_followup` *(synthesis)* | Multi-doc (3) | Deduplication of Metformin + Type 2 Diabetes across 3 docs |
| `cardiac_admission` *(synthesis)* | Multi-doc (2) | Deduplication of Aspirin, medication filtering of O2/IV saline/physiotherapy |
