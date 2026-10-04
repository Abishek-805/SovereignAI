# Reported task and conversation regressions — 2026-10-04

Changes use the existing task runner, query compiler, and model. Historical benchmark evidence and fixtures were not changed for these fixes.

## Before and after

| Reported behavior | Verified result |
| --- | --- |
| All-assessment numeric report omitted WAT 1 | Seven counts match an independent read of the original workbook |
| Week 1 follow-up treated the assessment as a population | Actual local model returns WAT 1: 23/64, retaining ALR and >=25 from user history |
| Bare WAT 1 inherited the wrong scope or rejected its cohort | Actual local model returns only WAT 1: 23/64 |
| Chat refused admission while a workspace task ran | Document/chat job waits behind the owner; owner finishes unchanged, then Chat answers |
| Todo run stopped on repeated continuation | Natural-language run request completes a Docker HTTP preview with status 200 |
| Model bar omitted task activity | Status endpoint exposes active job stages; frontend polls every two seconds |
| Network failure discarded reconnectable task state | Polling retries transient network failures; unresolved connection loss retains working turn and job ID for reopening Agent |

Source counts for 64 ALR records, using numeric scores >=25: WAT 1=23, WAT 2=1, WAT 3=1, WAT 4=6, WAT 5=34, WAT 6=28, CAT 1=31.

The query catalog now includes complete-source matches for earlier **user** requests separately from current-message matches. A generic measurement-follow-up example guides the existing measure contract. The compiler binds explicitly named score fields, recognizes inherited population context, and retains numeric criterion evidence on count results. No ALR-specific threshold or answer is encoded.

Project-map entrypoints that identify an existing Python/Node file use the existing typed file runner. A Flask server therefore uses bounded Docker HTTP readiness rather than a raw terminal command that waits indefinitely.

## Validation and limits

- Latest focused backend suite: 115 passed, one skipped; one upstream Starlette deprecation warning.
- Frontend check: zero errors and warnings. Production build completed; existing bundle warnings remain.
- Actual local-model workbook follow-ups and natural Todo run were executed, not mocked.
- Queue admission, cancellation isolation, inherited-rule count evidence and historical-source coverage have regression tests.
- Raw live results are preserved under ignored `outputs/reported-regressions/`, including failed intermediate attempts, the original workbook snapshot and independent oracle.
- Latest successful follow-up: `measurement-followup-week1.json`; bare measurement: `history-coverage-wat1.json`; natural run: `natural-todo-agent.json`; queue: `queue-admission.json` and `queue-completion.json`.
- Reconnection/UI behavior has compile checks and source-level verification, but no new end-to-end browser disconnect/navigation test was performed. A queued Chat response waits for the current task; concurrent heavy models are not started.
- These targeted results do not establish universal model correctness or benchmark superiority.
