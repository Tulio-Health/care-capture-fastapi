# Regression results

No regression has been run. This folder is the only destination for future run reports.

Each explicitly started run creates a unique UTC timestamp directory containing:

- `report.json`: structured case statuses and failed assertions.
- `report.md`: readable case status table.
- `<case>-live-<iteration>.json`: actual application observations/generated summaries from live-mode cases, with secrets redacted.

Regression results are never persisted to a database. Persistence behavior is tested using fresh in-memory fake repositories only. No production or test database connection, write, schema operation or migration is allowed in this pack.

Generated run directories are ignored by Git. Reports are local QA artifacts; review before sharing. No expected-results file or case catalog is a test execution report.
