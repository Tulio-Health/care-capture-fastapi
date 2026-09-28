# Engineering review record

2026-09-16. Reviewer: Codex, source inspection and synthetic regression evidence; this is not independent clinical approval.

- **12 error-policy cases:** inspected `processing_errors.STAGES`, `describe_error`, `summary_runtime.model_call`, `retry_delay`, and repository transaction retry handling. `transient_retryable` describes eligibility, not a claim that every layer automatically retries. Model retries, output correction and database serialization/deadlock retries have separate bounded policies. The twelve assertions verify the registry's code/stage/eligibility fields; retry behavior has separate runtime cases. Removed the generic review reminder, not the assertions.
- **Three content-gate cases:** attachment/procedure inputs are parsed before clinical chains. The transcript test invokes the real transcript chain with malformed markup and observes zero model calls. It does not invent an attachment upload capability for transcript APIs. Removed the generic scope reminder; model-call and raw-forwarding assertions remain.
- **Archive expansion:** ZIP is excluded by the user's release scope. Reviewed rejection before archive payload expansion with archive-read/extract spies. Disabled-container rejection is the requirement; enabled-ZIP expansion tests now explicitly assert unsupported format rather than claiming ZIP conversion support.
- **Redirect security:** FastAPI's document download boundary parses S3 URIs and uses the AWS SDK; arbitrary HTTP redirect URLs are rejected before SDK invocation. This evidence covers this FastAPI path only, not connector-owned HTTP fetch behavior.
- **24 optional-format reviews:** user approved FHIR JSON/XML and multipart, and explicitly excluded NDJSON, gzip document containers and ZIP. Updated cases to reflect that decision. HTTP Content-Encoding remains a distinct download transport layer.
- **Legacy Word:** retained a truncated-OLE negative fixture and added an actual generated .doc positive fixture. Clinical fidelity review remains pending for the positive fixture.
- **Visual fidelity case:** wired the actual application adapter for both modes. Automated checks assess evidence accounting and raw-content exclusion. Accuracy thresholds/reviewer approval are explicitly manual; neither mocks nor the AI verifier set them to approved. Live execution with valid regression credentials is still necessary.

No expected clinical facts were changed to match model wording. No production condition references QA IDs, fixture filenames, sample patients, diagnoses or medications.
