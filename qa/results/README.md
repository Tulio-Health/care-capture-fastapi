# Regression results

This folder holds local regression outputs. Generated results are ignored by Git.

Each explicitly started run overwrites the canonical report and records current-run observations:

- `report.json`: structured case statuses and failed assertions.
- `report.html`: readable case status tables, source links, and expected-versus-actual checks.
- `outputs/<case>-<mode>-<iteration>.json`: saved application observations from mock or live mode, with secrets redacted.

Regression results are never persisted to a database. Persistence behavior is tested using fresh in-memory fake repositories only. No production or test database connection, write, schema operation or migration is allowed in this pack.

Reports are local QA artifacts; review before sharing. Mock outputs do not establish live AI accuracy. Regression source code, case catalogs and synthetic source documents remain version-controlled under `qa/summary_regression/` and `qa/testdata/`. No expected-results file or case catalog is a test execution report.
