# PDF OCR extraction returns 0 characters — root cause

**Interim mitigation applied 2026-09-28:** `ENABLE_DOCUMENT_OCR` default flipped to `False` in
`src/app/core/settings.py` (branch `fix/disable-broken-document-ocr`). This is a cost/latency
mitigation only, not the fix described in section 5 below -- OCR remains fully implemented and
is re-enabled by flipping the default back once the verification-gate bug is actually fixed and
re-measured against real documents.

**Status:** diagnosed, not fixed (code change required, deliberately not implemented).
**Code under test:** `origin/develop` @ `43435e7`, worktree `/tmp/gate-ab/wt`.
**Data:** real dev S3 documents (`s3://carecapture-dev-storage/emr/documents/...`), cached locally in
`/tmp/gate-ab/raw`. Real `gpt-4o-mini` vision calls. Zero DB writes, zero prod writes.

---

## 1. Verdict in one line

The OCR **transcription** works fine. The **verification gate that follows it**
(`document_ocr.transcribe_verified_image`) rejects nearly every correct transcription over
whitespace/line-break artifacts and self-contradictory verdicts, and on rejection it discards the
*entire document* — so a working OCR result is thrown away and recorded as `extraction_error`.

Category, against the brief's options: **(c)/(e) — a design defect in the verification gate, not a
config, credential, dependency, regression, or transient/rate-limit problem.**

---

## 2. Reproduction numbers

| measurement | result |
|---|---|
| Real dev OCR-routed documents tested (distinct, cumulative incl. prior Gate-A 9) | **24** |
| Of those, produced **0 extracted characters** on their measured run | **24 / 24 (100%)** |
| Reason code distribution | 23 × `OCR_VERIFICATION_FAILED`, 1 × `OCR_UNREADABLE` |
| Fresh documents I ran this session (not in the original sample) | **15 / 15 → 0 chars** |
| Original failing docs re-reproduced by me, instrumented | **5 / 5 → 0 chars** |
| Repo's **own** "clear/legible" OCR positive-control fixtures (`qa/testdata/.../ocr/*.pdf`) | **3 / 4 failed** |
| Total real end-to-end OCR runs executed (real vision API) | **35** |

The one fixture that passes (`clear_visit_note_ocr.pdf`) produces **315 characters**. Every
document above ~1,000 characters of transcription failed.

**The gate is stochastic, not deterministic.** `1789985083419_XR-208838633.pdf` failed
(`OCR_VERIFICATION_FAILED`, branch `:185`) in one run and passed (`matches=true`, 0 issues) in a
later identical run. So the real rate is "very close to 100%, biased hard toward reject", not a
hard deterministic 0.

### Failing branch distribution (exact `document_ocr.py` line that raised)

| line | condition | observed |
|---|---|---|
| `:178` | verifier verdict failed self-consistency **twice** | majority |
| `:185` | verifier returned a *consistent* `matches=false` | common |
| `:175` | verifier JSON failed `OCRVerification` schema validation | 2 cases |
| `:162/:165/:168/:171` | no choices / refusal / truncation / non-stop finish | **never observed** |

No call ever errored, timed out, was refused, was rate-limited, or was truncated. `finish_reason`
was `stop` on **every single** transcription and verification call.

---

## 3. Root cause, with evidence

### 3.1 Transcription succeeds every time

Instrumented capture of the first (transcription) vision call, all 5 instrumented cases:

```
CALL transcribe model=gpt-4o-mini finish=stop refusal=False out_tok=484 chars=2542
     t_chars=2474 complete=True unreadable=[]
     head='AUTHORIZATION TO RELEASE/OBTAIN MEDICAL INFORMATION I HEREBY AUTHORIZE DSM SLEEP...'
```

`complete=True`, `unreadable_regions=[]`, 1,000–2,500 chars of clean, correct clinical text
(patient demographics, MRN/FIN, service dates, medication lists, discharge instructions). The
documents are **not** poor scans — they are legible Cerner-generated clinical PDFs without a text
layer. OCR is doing its job.

### 3.2 The verifier rejects that correct text over non-differences

The second model call (`OCR_VERIFICATION_POLICY`, same `gpt-4o-mini`) returns `matches: false`
with issues whose `source_quote` and `candidate_quote` are **character-identical**:

```json
{"kind":"text_mismatch","candidate_line":3,
 "candidate_quote":"Kansas City, MO 64117-","source_quote":"Kansas City, MO 64117-",
 "reason":"Extra hyphen at the end of the address in the candidate transcription."}
```

```json
{"kind":"text_mismatch","candidate_line":17,
 "candidate_quote":"Document Subject: Kranes Patient Education - Acetaminophen; Hydrocodone...",
 "source_quote":  "Document Subject: Kranes Patient Education - Acetaminophen; Hydrocodone...",
 "reason":"The candidate transcription has a typo in 'Kranes' instead of 'Kranes'."}
```

And, most damning, on the retry attempt for `1789985093224_XR-206838765.pdf` the verifier returned
**eight issues, every one of them with `"reason": "No discrepancy."`, while still setting
`matches: false`**:

```
attempt1 consistent=False matches=False n=8
  text_mismatch src='MRN: 00000006930'                         reason=No discrepancy.
  text_mismatch src='FIN: 000000016000'                        reason=No discrepancy.
  text_mismatch src='DOB/Age/Sex: 1/2/1990 36 years Female'     reason=No discrepancy.
  text_mismatch src='Service Date/Time: 9/17/2024 16:12 CDT'    reason=No discrepancy.
  ... (4 more, all "No discrepancy.")
```

The remaining rejections are **linearization artifacts**: the transcription flattens a 2-D page to
one string, so a heading and the following sentence join without a space
(`...MEDICAL INFORMATIONI HEREBY AUTHORIZE...`). The verifier reads that as a content mismatch
against the image. It is a rendering artifact of the transcription format, not lost or wrong
clinical content.

### 3.3 Why this becomes 0 characters instead of degraded output

Three compounding design choices in `src/app/services/document_ocr.py`:

1. **`verification_is_consistent` detects the bogus whitespace-only mismatch but only uses it to
   invalidate the verdict, never to forgive it** (line ~96):
   ```python
   if issue.kind == "text_mismatch" and " ".join(issue.source_quote.split()) == " ".join(issue.candidate_quote.split()):
       return False
   ```
   An identical-quotes issue → verdict "inconsistent" → one retry → if still inconsistent →
   `OCR_VERIFICATION_FAILED` (`:178`). The code already *knows* the complaint is vacuous and still
   fails the document over it.
2. **The gate is all-or-nothing.** One issue on one page discards that page's entire transcription,
   and `extract_scanned_document`'s `except DocumentProcessingError: raise` discards **the whole
   document** — every other successfully-verified page included. There is no partial-acceptance path.
3. **The verifier model is the same weak `gpt-4o-mini`** (`DOCUMENT_OCR_MODEL`, settings.py:45) used
   for transcription, asked to do the strictly harder job of adversarial image-vs-text diffing,
   under a policy that explicitly instructs it to check "punctuation" and never tells it to ignore
   whitespace or layout.

### 3.4 Ruled out, with evidence

| hypothesis | ruled out by |
|---|---|
| (a) missing/misconfigured OCR dependency or credential | Rendering works (`render_pages` returns real pages); vision calls succeed with `finish_reason=stop` and real token usage on all 35 runs. Same dev key used throughout; no 401, no fallback needed. |
| (a) `ENABLE_DOCUMENT_OCR` disabled | Default `True` (`settings.py:41`); no env var, YAML, Dockerfile, or SSM override of `ENABLE_DOCUMENT_OCR` / `DOCUMENT_OCR_MODEL` exists anywhere in the repo. `OCR_DISABLED` was never raised. |
| (b) recent regression | `git log origin/develop -- document_ocr.py ocr_regions.py document_image_routing.py` returns **exactly one commit**: `493effe` (2026-09-17, SummaryEnhancement pre-merge fixes, #44). The code has never had a different version. It has **never worked** on dense documents. |
| (c) genuinely bad scans / unsupported format | The transcriber returns `complete=True`, `unreadable_regions=[]` and correct text on every one. The repo's own designated-legible fixtures fail too. |
| (d) rate limit / timeout / transient | Zero exceptions, zero timeouts, zero refusals, zero truncations across 35 runs spanning ~20 minutes. Failures are semantic verdicts, not transport faults. |

---

## 4. Severity and scope (measured, not estimated)

Computed over the full dev measurement corpus (`/tmp/gate-ab/measured_all.json`: 2,240 attachments
across 560 encounters).

| metric | value |
|---|---|
| Attachments routed to OCR | **305** (304 PDF + 1 XML) = 13.6% of all attachments, **19.0% of PDFs** |
| Share of **total attachment bytes** sitting in OCR-routed documents | **83.3%** (87.9 MB / 105.6 MB) |
| Encounters with ≥1 OCR-routed document | **31 / 560 (5.5%)** |
| Encounters where OCR-routed docs are the **only** content — every other attachment failed or is absent | **15 / 560 (2.7%)** → **total clinical blackout** |
| Encounters partially covered (other text survives) | 16 / 560 (2.9%), median 13,821 surviving chars |
| Of those partial ones, surviving text < 2,000 chars (near-blackout) | 3 |

So the honest severity: **~2.7% of encounters get a summary built on literally no document content**,
and a further ~0.5% are near-empty. The remaining ~2.9% lose the scanned document but retain a
substantive CDA/XML/HTML source for the same visit, so the clinical loss there is partial, not total.
The 83.3%-of-bytes figure is real but must not be read as 83% of clinical information lost — the
large scanned PDFs are byte-heavy (median 112 KB, max 5.5 MB) and text-light relative to CDAs.

**Wasted cost:** each failing document burns up to 3 vision calls per page and returns nothing.
The 305 OCR-routed dev documents total **1,344 pages → up to ~4,032 wasted `gpt-4o-mini` vision
calls per full corpus pass**, plus 12–32 s of added latency per document inside the summary job wall.

### Prod exposure

**This is not a live prod incident — it is a release blocker.**

- `origin/main` (prod) is at `dc99f74` and **does not contain `document_ocr.py` at all**;
  `493effe` is not an ancestor of main. The entire OCR feature is unreleased.
- Prod's `document_extraction.py` handles PDFs with a plain `fitz` `page.get_text()`, so scanned
  PDFs today silently yield empty text with no OCR attempt. **Prod already loses this content
  silently** — the develop OCR feature exists precisely to close that hole.
- Net: shipping develop→main as-is would close **0%** of the gap it was built to close, while adding
  thousands of billed vision calls and 12–32 s/document of latency for nothing.
- No environment difference would save prod: there is no `ENABLE_DOCUMENT_OCR` or
  `DOCUMENT_OCR_MODEL` SSM parameter in either environment, so both run the same hardcoded defaults
  (`True`, `gpt-4o-mini`).

---

## 5. Proposed fix — scoped, **not implemented**

Per the brief, this touches document-extraction logic with a history of production incidents, so it
stops at diagnosis. One thing is already settled empirically, which the follow-up task must not
re-litigate:

> **The obvious one-line fix does not work.** I A/B-tested the narrow version — add a
> whitespace-tolerance instruction to `OCR_VERIFICATION_POLICY` **and** drop `text_mismatch` issues
> whose `source_quote` and `candidate_quote` are whitespace-normalize-equal, recomputing `matches`.
> Result: **7 of 8 documents still failed** (`/tmp/ocr-inv/fixtest_out.json`). It recovered one
> previously-failing repo fixture and nothing else, because the retry attempt simply produces a
> *different* set of complaints, including line-join artifacts that survive whitespace normalization.

The fix needs all of the following, in this order of value:

1. **Partial acceptance instead of all-or-nothing (highest value, lowest risk).**
   In `extract_scanned_document`, a page that fails verification should contribute nothing while
   pages that pass still contribute, and the document should succeed if *any* page verified.
   Today a single page's verdict voids a 14-page document. This alone converts most total
   blackouts into partial coverage and never publishes unverified text.
2. **Normalize before comparing, at the point of comparison.** Verification should run against a
   whitespace-normalized candidate, and any issue that disappears under normalization should be
   dropped rather than used to invalidate the verdict. Also drop issues the verifier self-labels as
   non-issues (`reason` ≈ "No discrepancy") — it emits these while setting `matches:false`.
3. **Use a stronger verifier, or drop the second-model gate.** `gpt-4o-mini` is empirically not
   capable of this adversarial image-vs-text diff: it fabricates mismatches between identical
   strings and contradicts its own `matches` flag. Either point verification at `gpt-4o`/`gpt-4.1-mini`
   (measure the new pass rate before shipping), or rely on the transcriber's own `complete` /
   `unreadable_regions` signals, which were accurate in all 35 observed runs.
4. **Make the failure observable.** `OCR_VERIFICATION_FAILED` currently collapses seven distinct
   conditions (`:162/:165/:168/:171/:175/:178/:185`) into one opaque code, which is why a 100%
   failure rate went unnoticed. Distinct codes per branch would have surfaced this immediately.

**Trivial, safe, optional interim mitigation (also not applied):** setting `ENABLE_DOCUMENT_OCR=False`
loses no content whatsoever today (OCR yields 0 chars) and stops ~4,000 wasted vision calls per
corpus pass. It is strictly a cost/latency mitigation and should not be mistaken for a fix. It is
only worth doing if develop ships to main before the real fix lands.

**Acceptance criterion for the follow-up task:** re-run the 24 real dev OCR-routed documents in
`/tmp/gate-ab/raw` (list in `/tmp/gate-ab/ocr_results.json` + `/tmp/gate-ab/ocr_rate.json`) plus the
4 repo fixtures, and require a materially non-zero extraction rate with no unverified text published.
The instrumentation used here is reusable at `/tmp/ocr-inv/repro.py` (branch-level raise-site capture,
per-call verifier payload logging).

---

## 6. Artifacts

| path | contents |
|---|---|
| `/tmp/ocr-inv/repro.py` | instrumented reproduction (raise-site + full verifier payload capture) |
| `/tmp/ocr-inv/repro_out.json` | 5 instrumented failures, complete call logs |
| `/tmp/ocr-inv/rate.py`, `rate_out_corpus.json`, `rate_out_fixture.json` | 15 fresh dev docs + 4 repo fixtures |
| `/tmp/ocr-inv/fixtest.py`, `fixtest_out.json` | A/B proving the narrow whitespace fix is insufficient |
| `/tmp/ocr-inv/residual.py` | per-issue cosmetic/content classification of verifier rejections |
| `/tmp/gate-ab/raw/` | 2,240 cached real dev attachments (108 MB), incl. all failing PDFs |
