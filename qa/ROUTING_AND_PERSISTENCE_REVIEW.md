# OCR routing and persistence verification

The routing change keeps native PDF text when the only raster graphics are small marginal letterhead/footer images. A supported graphic is at most 108 × 54 PDF points and wholly within the top 90 or bottom 72 points. This is a layout heuristic, not proof that an image has no clinical meaning. Large or body images require OCR even when other text exists. Truly blank pages do not trigger OCR. Mixed PDFs retain native pages in order and send only selected pages for vision transcription and verification.

DOCX supports small embedded raster logos (at most 1.5 × 0.75 inches) in headers, footers, or the first paragraph. It retains native paragraph/table text. Other image-bearing layouts fail with a supported-format message, without attempting to open DOCX in PIL. Legacy VML, linked images, charts and unknown image geometry are not logo support. Real connector layouts and small clinical images in marginal positions still need representative document review before release.

The OCR default is unchanged; the routing fix does not independently establish PHI governance, provider retention policy, or a monetary spend ceiling. Existing shared model call/deadline limits remain. The parser cache version changed so prior cached results do not bypass revised extraction.

## Automated evidence

The canonical `results/report.html` includes nine new routing/access/preservation cases. Source documents are linked under `testdata/routing`. Mock mode makes no external AI calls and never accesses a database. Zero-call assertions intercept the OCR entry point: even attempting to invoke vision for ordinary logo PDFs/DOCX fails the test. Mixed-page tests exercise the actual renderer and mock only the transcription operation.

The memory-backed repository tests exercise actual publication decisions: failed refreshes preserve prior clinical content, notices are not duplicated, and an empty failed procedure refresh does not prune rows. They do not simulate PostgreSQL locking or prove durable commits.

## Access verification still outstanding

Mapped-patient requests and existing trusted-service delegation are covered. Direct caregiver/provider requests still lack grant resolution in the newly added scope gate. Do not interpret these tests as proof that every existing mobile/Node access flow is preserved. Authorization production code was not broadened or removed by this routing change. Before release, verify primary patient, granted caregiver, revoked caregiver, provider, cross-patient denial, and Node service paths against the deployed integration. This remains an unresolved release concern.

## Deployed persistence verification — deferred, not passed

Use dedicated synthetic QA patients/appointments in a deployed test instance. Do not test destructive scenarios against real patient records. Capture before/after rows and API/mobile output for:

1. Successful initial summary and repeat request: correct source, owner and stable identity.
2. Parser/OCR/AI failure after prior success: previous clinical text and fields retained; refresh warning appears once.
3. Partial and empty failed procedure batches: no prior row deleted; unrelated sources untouched.
4. Explicit complete zero-procedure result: prune only the intended patient/appointment/source.
5. Concurrent refreshes finishing out of order: stale result cannot replace newer result.
6. Confirmed transaction abort: bounded retry, no duplicate rows. Uncertain commit: reconciliation without blind replay.
7. Cross-patient/appointment/source attempts: denied and prior rows unchanged.
8. Node/mobile consumers: existing JSON fields and failure messages display correctly.

Record deployed revision, synthetic identities, request correlation IDs, initial/final row snapshots and expected/actual outcomes. Live deployed persistence validation has not been run or authorized to write real patient data. No persistence implementation changes were made for this routing correction.
