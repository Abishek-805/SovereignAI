# Project audit follow-up — 2026-09-30

This is an evidence-based continuation, not a claim that every project flaw is resolved. Screenshots establish symptoms; source tracing and tests establish the findings below. Existing user projects were not used as test fixtures.

## Findings addressed

| Finding | Cause and correction | Evidence |
|---|---|---|
| Excel import can spend excessive work on empty cells | `rag/ingest.py` previously expanded worksheet dimensions with openpyxl. The XLSX reader now streams actual OOXML cells with archive, stored-cell, sheet and extracted-text limits. | `tests/test_ingest.py` imports A1 and XFD1048576 in one workbook without expanding the intervening grid. |
| Import appears stuck with no stage or Stop | The library awaited one synchronous request. Optional background imports now use bounded job history; the UI polls extraction/indexing progress and can request cancellation. | `tests/test_api.py` checks progress, successful retrieval, upload cleanup and cancellation before index publication. |
| Common text/source files cannot be selected | Frontend and backend format lists were narrow. Both now accept the documented text formats; decoding supports UTF-8 and BOM-marked UTF-16 and rejects NUL-bearing binary input. | Parameterized ingestion tests cover source/config/tabular formats, Unicode and disguised binary input. |
| Chunk line-number calculation repeats scans | Every chunk counted all preceding newlines. Precomputed newline positions now support binary-search offsets. | Existing Unicode, overlapping chunk and line-citation tests. |
| Broad project cleanup removes only a planner subset | The planner could emit its eight-operation subset for an all-files request. A typed scoped-delete operation enumerates the complete selected project and stages it for review; an exception must identify the preserved folder. | Application-tool and publication-boundary tests cover more than eight files, preserving a subtree, full cleanup and mistaken project deletion. Actual local Qwen planning returned the scoped operation for the three reported requests. |
| Successful Knowledge creation has no destination action | Agent results now retain created document IDs and open the corresponding Knowledge document. | Frontend type checking; interactive acceptance remains to be recorded. |

## Boundaries reviewed

`backend/app.py` implements local host/origin checks, request-size limits, upload validation and fixed local model proxying. `backend/service.py` routes tasks, acquires model/import locks and requires verified Docker validation for code acceptance. `router/sandbox.py` uses a pinned image, no network, non-root user, dropped capabilities, read-only root/input, bounded tmpfs, CPU/memory/PID/time/output limits and cleanup. `workflows/coding_workspace.py` stages changes separately, validates paths and revisions, and performs reviewed publication. `rag/ingest.py`, `rag/embedding.py` and `rag/store.py` form extraction, bounded embedding batches and transactional index publication. `backend/jobs.py` retains bounded job histories and cooperative cancellation. Code, Agent and Knowledge have distinct mutation paths; one path's checks do not certify the others.

The prior live Docker probes and their limitations are recorded in `sandbox-audit-results.md`. They were not rerun merely because ingestion changed; no new live isolation PASS is implied. Backend tests, frontend type checking and production compilation are separate evidence from browser acceptance and real-model task quality.

## Unresolved release gates

- Multi-file canonical publication has exception rollback but no durable crash-recovery transaction. Process death or power loss can leave a partially published project.
- Revision checks and the mutation lock coordinate this process; they do not prevent another process or a filesystem-link swap racing publication. Rollback is also not a general external-writer conflict resolver.
- Parser and embedding cancellation is cooperative. An active parser/native inference call is not forcibly terminated; an import worker is not an isolated parser sandbox.
- Secret exclusions identify common sensitive paths, not secrets embedded in arbitrary selected source files.
- Earlier browser acceptance has four failures and a client-browser launch failure. Type checks and builds do not clear those findings.
- Small-model task comprehension and output correctness are not guaranteed by tool availability or syntax validation. General planner scope remains bounded; supporting every possible application task is not demonstrated.

These remain open engineering work, not PASS findings. No claim of complete security, all-format support, or complete project-wide correctness is made.

## Verification for this follow-up

- Full Python suite: 566 passed, seven skipped, one Starlette deprecation warning. A subsequently added shared-string validation test passed with the complete 22-test ingestion suite.
- Frontend check: zero errors and warnings.
- Focused frontend regression tests: 21 passed across Agent request and Knowledge context/history tests.
- Production build completed successfully, including the final message-copy adjustment.
- `git diff --check` passed. Real-model cleanup planning was checked with simulated project metadata, without deleting user files.
- Targeted browser acceptance passed using installed Chrome and a disposable backend: TSV import, visible Stop/progress controls, successful library publication, and stopping a larger text import without publishing it. `benchmarks/audit-import-server.py` creates temporary data/projects; `frontend/llama-ui/tests/e2e/sovereign-import-audit.cjs` exercises the controls. This does not clear the four earlier browser-suite failures or establish model quality.
