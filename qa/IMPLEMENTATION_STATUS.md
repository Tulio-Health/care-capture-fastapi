# FastAPI implementation status

Updated 2026-09-16. Implementation and synthetic verification completed for the code paths described below; independent clinical approval and successful live AI verification remain outstanding. The current [regression report](results/report.html) is the authority for execution counts and any failures. No deployment or database-backed regression has been performed.

## Implemented behavior

- Documents pass bounded MIME/signature/encoding detection and parsing before clinical AI. Parsing errors never fall back to raw-document summarization.
- Internal release policy enables FHIR JSON/XML and multipart without additional application environment variables. FHIR bundles and typed nested attachments are decoded and parsed with depth/count/byte limits. Unacquired external attachment URLs produce a contained outcome and are not fetched arbitrarily.
- NDJSON, ZIP and gzip document containers are excluded by the user's format decision and return a clear unsupported-format message. HTTP Content-Encoding remains a separate bounded download transport layer.
- Text-based legacy Word .doc uses the read-only antiword parser and olefile structure checks. Docker packages the native dependency; the Python dependency is locked. Encrypted, macro-bearing, picture-bearing and embedded-object variants are rejected, not silently summarized without their content. Modern Word, PDF, RTF, text, HTML, XML, JSON and supported image paths retain their existing bounded adapters.
- S3 retains the original stored URI lookup through user/encounter-scoped inventory and IAM. Removed the global prefix requirement introduced by the earlier fix-pack commit. No new per-user folder configuration, bucket layout or connector behavior was introduced. Malformed/control-character URIs are rejected before AWS access; explicit scopes remain available to restricted callers/tests.
- Dedicated OCR validates the transcription before clinical extraction. Supplementary overlapping regions cross-check full-page text; that text is emitted once. Ambiguous regional evidence fails closed rather than being spliced or deduplicated by guessing.
- Clinical outputs preserve source evidence, uncertainty and procedure/medication statuses. Independent model verification and deterministic guards reject unsupported claims; these mechanisms do not prove medical accuracy. FHIR prompt instructions were aligned with source-only reporting.
- Chunk failures, aggregate budgets, over-limit transcripts, parser memory exhaustion and model failures yield bounded outcomes. Parser cancellation terminates its process group, including native converter children; parent-owned temporary folders remove source files even after forced worker termination.
- Attachment failure can fall back to separately parsed structured FHIR evidence. Partial warning/metadata are added before persistence; a failed fallback retains the original contained attachment result. Previously validated summaries remain protected.
- Fixed-label processing counters/log events distinguish failure stages and coverage outcomes without logging document content or patient identifiers. Provider HTTP 401/403 has a distinct nonretrying authentication code.
- Outcomes use the existing summary JSON and persistence contract. No new tables, columns, migrations, Node or mobile changes were introduced by this completion work.

## Verification and review

- 76 offline safety tests passed, including nested FHIR attachment parsing, legacy Word, source-only gates, failure containment and persistence decisions against memory boundaries.
- Nine reporting tests passed. The report retains separate safety containment and summary-availability outcomes; safe rejection is not presented as an unsafe-output failure.
- Focused integrations exercised all eight formerly blocked scenarios. The visual-fidelity scenario now runs through the application adapter; clinical approval remains manual and is not manufactured by automated assertions.
- Real Linux RLIMIT_AS allocation failure was contained through the production parser worker in a network-disabled container. This verifies the mechanism, not production replica sizing.
- A Linux container with antiword and olefile successfully ran the actual asynchronous legacy Word parser against the stored synthetic .doc fixture. Full application deployment/IAM qualification remains separate.
- Changed-source syntax/undefined-name checks passed. No production database was connected to by regression tests; do not run the repository's DB-owning test conftest for this QA pack.
- Live AI requests returned HTTP 401 with the current regression credentials. Correct the existing `qa/.env.regression.local` key before claiming live model/OCR accuracy. The key was never displayed or replaced by this work.

## Remaining human/external evidence

The clinical review packet covers CDA table relationships, Word tables, rotated scans, broader visual fidelity, supplementary crops and legacy Word. Reviewers must compare source documents against actual live output; mock outputs do not qualify accuracy. [Engineering review evidence](ENGINEERING_REVIEW.md) explains why generic code/configuration review reminders were closed without changing clinical expectations.

Production IAM, transaction isolation/locking, final source-mutation races, replica capacity and actual mobile rendering still require deployment/integration qualification. The current tests do not claim that the application can never fail. The requirement is bounded failure, no publication of known-invalid content, and clear disclosure of unavailable information.

## Artifacts

- [Current regression report](results/report.html): one overwritten report with exact assertions, observations and source links.
- [Clinical review packet](CLINICAL_REVIEW.md): regenerate after a completed run with `python qa/summary_regression/prepare_clinical_review.py`.
- [Synthetic documents](testdata/): retained binary and textual fixtures with catalog hashes.
- [Run instructions](README.md): mock/live usage, dependencies and memory-only persistence boundary.

## OCR/DOCX routing correction

Native PDFs with supported small marginal logos no longer trigger vision. Mixed PDFs retain native page text and OCR only pages requiring image extraction. DOCX small header/footer/first-paragraph logos preserve text and tables; unsupported embedded images return an unsupported-format outcome rather than invoking PIL on a Word file. Parser version is strict-3. These geometry rules are heuristics with documented support limits, not proof that every small image is nonclinical.

Nine new regression cases cover routing, trusted-service/mapped-patient access and memory-backed summary preservation. Direct caregiver/provider delegation remains unresolved. Deployed PostgreSQL verification is deferred; memory tests do not prove transaction safety. See [scope and deferred checks](ROUTING_AND_PERSISTENCE_REVIEW.md). The latest full rerun is mock-only; it does not resolve prior live AI credential failures or establish OCR accuracy.

Latest completed mock pack: **494 executions — 485 PASS, 0 FAIL, 0 BLOCKED, 9 REVIEW_REQUIRED**. The nine reviews comprise six clinical checks, one access-integration check, and two deployed-persistence checks. All new automated routing/access/preservation assertions passed; review status is intentionally retained where external evidence is missing. All 114 synthetic fixture hashes and saved observation run IDs were verified.
