# Review decisions and remaining work

Updated 2026-09-16. Code review only for S3; no production configuration, storage layout, database or connector changes were made in this review.

## Existing S3 flow

FastAPI verifies appointment ownership, selects DocumentReference resources by user and encounter, and passes the stored attachment filePath to S3DocumentClient. The URI supplies the bucket and exact object key dynamically; a per-user folder is not hardcoded in this selection flow.

An additional authorize_location gate checks DOCUMENT_ALLOWED_S3_PREFIXES. Its default is empty (deny all), while the attachment and procedure services construct S3DocumentClient without request-specific scopes. Thus valid stored document paths can be rejected unless deployment configuration supplies an applicable scope. This is a concrete configuration/compatibility concern, not evidence that live downloads currently fail: deployment configuration and IAM were not accessed. Keep reviewing the existing contract rather than introducing per-user folder maintenance or broadening access indiscriminately.

References: src/app/services/summarization/attachment_summarization.py, src/app/services/document_ingestion.py, src/app/db/objects/repositories/fhir_resources.py, src/app/utils/s3_client.py, src/app/core/settings.py.

## Accepted format scope

Enable FHIR JSON/XML and multipart. Other optional formats discussed (NDJSON, gzip document containers and ZIP) should produce an explicit unsupported-format outcome. Current transport/container flags group capabilities together; separate format policy is required to implement this choice. HTTP Content-Encoding decoding is a transport layer and should not be confused with support for uploaded compressed document containers.

Legacy Word .doc is required. Current rejection does not satisfy this capability; implementation, a conversion/runtime dependency if used, and real valid synthetic .doc fixtures are needed.

## Blocked cases: nature of work

| Case | Required work |
|---|---|
| LONG-03 | Test integration plus a configurable chunk-budget seam; exercise a real failed chunk and coverage outcome. Current chunking uses character limits. |
| A08-REDUCE | Test integration for repeated large documents and observed coverage/budget assertions. Existing budget controls need qualification, not a configuration-only claim. |
| VISION-REVIEW | Live evaluation integration, predeclared accuracy criteria and independent clinical review. |
| LIMIT-MEMORY | Memory-exhaustion fault integration and qualification on the deployment operating system; existing worker limits alone do not prove enforcement. |
| A03-FHIRFALLBACK | Application orchestration plus test integration. Current FHIR fallback is selected when attachments are absent, not after present attachments fail. |
| A08-LONGTRANSCRIPT | Test integration against the transcript service. It already has a context-limit rejection; verify containment and coverage disclosure. |
| VISION-CROP | Application implementation and tests for overlapping crop coverage/deduplication if this capability is required. Current full-page OCR does not establish it. |
| MONITOR-STAGES | Application instrumentation and test integration for distinct parse/model/coverage metrics. |

None of these eight should be presented as resolved by changing an environment variable alone. Test integration may reveal further application defects; preserve actual outcomes rather than tuning code to sample text.

## Clinical review

[Reviewer packet](CLINICAL_REVIEW.md) contains six entries selected from the current live and clinical/OCR/table review cases, links to synthetic source documents, expected checks, extracted text, returned messages, rejected candidates and reviewer decision fields. All remain pending. The blocked live evaluation entry explicitly has insufficient evidence.

## Resolution after implementation

The added global S3 prefix requirement was removed, preserving the original stored-path/IAM flow and owner-scoped inventory. Agreed formats now use internal defaults; .doc parsing is packaged; the eight formerly blocked scenarios have executable integrations. Linux memory enforcement and legacy Word parsing were exercised in isolated containers. Independent clinical review remains pending, and live AI verification is blocked by HTTP 401 from the current regression key. See IMPLEMENTATION_STATUS.md and the current report for the completed behavior and execution evidence.
