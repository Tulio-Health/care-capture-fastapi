# Troubleshooting

## Hallucination False Positives from Negation

**Symptom**: Hallucination score drops because a trap item appears as "hallucinated" even though the document says "No X" or "X was not administered".

**Root cause**: The hallucination scorer uses substring + fuzzy matching on extracted items. If the LLM extracts "X" from "No X prescribed", the trap item matches. The scorer cannot distinguish extracted-as-present from extracted-from-negation.

**Diagnosis**:
```bash
# Find the negation in the document
grep -i "NO_TRAP_ITEM\|not.*TRAP_ITEM\|denied.*TRAP_ITEM" evals/fixtures/documents/DOC_NAME.txt
```

**Resolution options**:
1. **If the LLM correctly handles negation** (doesn't extract the item): Remove the trap item — the document mentions it and the scorer can't safely test it.
2. **If the LLM incorrectly extracts negated items**: This is a real extraction bug. Strengthen the prompt: `"Do not extract items described as absent, denied, not present, not administered, or contraindicated."`
3. **Redesign the trap**: Replace with a different item that is truly absent with no mention in any form.

---

## Fuzzy Match Failures

**Symptom**: Completeness score drops for items that ARE in the extraction output — the extracted text just uses different phrasing than expected.

**Diagnosis**: Compare the extracted text with the `expected_*` synonyms:
```bash
# Read the failing case result to see which expected items weren't "found"
cat evals/results/v002_*.json | python -c "
import json, sys
report = json.load(sys.stdin)
for case in report['cases']:
    if case['scores'].get('completeness', {}).get('score', 1.0) < 1.0:
        print(case['case_name'], case['scores']['completeness'])
"
```

**Fuzzy threshold is 0.55** — very permissive. If an item isn't matching, it's likely a fundamental phrasing difference (e.g., "NSTEMI" ↔ "heart attack" have ~0.35 similarity).

**Resolution options**:
1. **Expand the synonym group** in the ground truth JSON to include the extracted phrasing
2. **Add the abbreviation to the conversion table** in the prompt if the LLM should be expanding it
3. **Check for extra text** — "Metformin 1000mg twice daily with meals" won't fuzzy-match "Metformin 1000mg" (similarity ~0.72 — should pass, but verify)

---

## Batch Extraction Merging (Why Eval Uses Per-Document Extraction)

**Context**: The production `chain.analyze()` method batches multiple documents into a single LLM call for efficiency (up to 30,000 chars per batch). The eval system intentionally uses per-document extraction instead.

**Why**: When multiple documents are in one batch, the LLM may merge findings across documents. This makes it impossible to attribute extracted items to specific documents, breaking the per-document ground truth comparison.

**How eval avoids this**: In `conftest.py`, the `extraction_results` fixture calls `chain._extract_batch([doc], 1, 1)` — one document at a time, batch size 1.

**If you see cross-document contamination**: Check that `conftest.py` is passing single-element lists to `_extract_batch`. If it's been changed to batch documents together, revert to per-document calls.

---

## Transient Validation Errors

**Symptom**: Eval run fails with a Pydantic validation error or `None` extraction result for some documents, but works on the next run.

**Root cause**: LLM API rate limits or intermittent model errors causing partial responses.

**How `run_eval.py` handles this**: The runner has retry logic for extraction calls. Check if the retry count in `run_eval.py` is set appropriately:
```python
# Look for retry logic in _run_extraction_eval
# Typically wraps _extract_batch with exponential backoff
```

**If error persists across retries**:
1. Check OpenAI API key: `aws ssm get-parameter --name "/tuliohealth/dev/openai/api_key" --with-decryption`
2. Check SSM loaded: `USE_SSM_LOCALLY=true uv run python -c "from src.app.config.ssm_loader import load_ssm_configuration; import asyncio; asyncio.run(load_ssm_configuration())"`
3. Run the failing document in isolation: `uv run pytest evals/test_extraction.py -k "FAILING_DOC" -v -s`

---

## Clinical Summary Judge Returning 0.5

**Symptom**: `clinical_summary` score is exactly 0.5 with `passed: false` but no helpful error message.

**Root cause**: The LLM judge in `scoring/clinical_summary.py` failed to parse its output as `JudgeScores`. The fallback is `ScoreResult(score=0.5, passed=False)`.

**Diagnosis**: Check if the synthesis result has a `clinical_summary` field at all:
```python
# Quick check
import json
with open("evals/results/LATEST.json") as f:
    report = json.load(f)
for case in report["cases"]:
    if "clinical_summary" in case.get("scores", {}):
        print(case["case_name"], case["scores"]["clinical_summary"])
```

**Resolution**:
1. **No `clinical_summary` in output**: Synthesis agent didn't return a `clinical_summary` field — prompt issue, or the field is named differently
2. **`clinical_summary` present but judge fails**: Judge model is hitting rate limits or returning malformed JSON — transient, retry
3. **Judge consistently fails**: Check `scoring/clinical_summary.py` — the judge prompt may need updating if model behavior changed

---

## Score Stagnation After Prompt Changes

**Symptom**: You edited the prompt, created a new version, but scores are identical to the old version.

**Cause 1 — Wrong version file**:
```bash
# Verify the version directory has your changes
cat evals/prompts/v003/extraction_prompt.txt | head -20
```

**Cause 2 — current.json not updated**:
```bash
cat evals/prompts/current.json
# Should show version: "v003", not "v002"
```
`run_eval.py` takes the version as a CLI arg, but conftest.py reads `current.json`. If using pytest, make sure `current.json` is updated.

**Cause 3 — Cached extraction results in pytest session**:
Pytest fixtures are session-scoped — if you run `pytest` twice in the same shell session without restarting, the second run uses cached LLM results from the first. Restart pytest to get fresh results.

**Cause 4 — Editing `src/app/chains/` but running evals against `evals/prompts/`**:
`run_eval.py` loads prompts from `evals/prompts/{version}/`, not from `chain.py`. Your edits to the chain file won't affect eval results until you also update the corresponding version's prompt files.

---

## "Extraction Returned None"

**Symptom**: `run_eval.py` logs "Extraction returned None for doc_name" and that document's case is skipped or fails.

**Most common causes**:
1. **SSM parameters not loaded**: The chain can't get the OpenAI API key
   ```bash
   # Verify SSM is accessible
   aws ssm get-parameter --name "/tuliohealth/dev/openai/api_key" --with-decryption
   ```
2. **Model name misconfigured**: Check the model name in `chain.py` is valid for your account
3. **Document file is empty**: `cat evals/fixtures/documents/DOC_NAME.txt` should have content
4. **Pydantic output parsing failed**: LLM returned text that doesn't parse as `DocumentSummary` — check model logs if available

**Quick diagnostic**:
```bash
# Try extracting a single document manually
uv run python -c "
import asyncio
from src.app.config.environment import initialize_environment_sync
initialize_environment_sync()
from src.app.chains.attachment_summarization.chain import AttachmentSummarizationChain
from src.app.models.attachment import DocumentAttachment
import datetime

chain = AttachmentSummarizationChain()
doc = DocumentAttachment(
    id='test',
    title='Test',
    extracted_text=open('evals/fixtures/documents/lab_report_cbc.txt').read(),
    document_date=datetime.datetime.now()
)
result = asyncio.run(chain._extract_batch([doc], 1, 1))
print(result)
"
```

---

## Deduplication Score Below Threshold for Legitimate Items

**Symptom**: Deduplication scorer flags items as near-duplicates that are actually distinct.

**Example**: "Metoprolol succinate 50mg" + "Metoprolol tartrate 25mg" → different formulations, same drug class. Fuzzy similarity might be ~0.82, above the 0.80 threshold.

**Resolution**:
1. **If these should be treated as distinct**: Check if the synthesis prompt is correctly instructing the LLM to distinguish formulations. If the LLM correctly keeps both, the scorer's 0.80 threshold might be too aggressive for this specific pair.
2. **If these should be merged**: The synthesis prompt should say "when the same drug appears in multiple documents, keep only the most recent/most specific entry."
3. **Ground truth adjustment**: If the similarity threshold causing false positives is a known edge case, document it in the case's `notes` field and consider whether the GT `medications_must_not_duplicate` list needs updating.
