# SovereignAI product verification — 2026-10-04

This pass verifies the existing prototype. It does not resume historical benchmarks, compare models, or change the agent/router architecture. New raw evidence is under `outputs/product-verification-20261004/`; failed attempts remain available alongside subsequent checks.

## Corrections verified

| Observed issue | Correction | Independent evidence |
| --- | --- | --- |
| IDE displayed an unsuccessful application operation as “Answered” | Execution failure, blocked, and successful run states have distinct labels | Real Todo request with prior failed conversation history; new UI displays Completed and Docker verifies HTTP 200 |
| Transient IDE polling failure discarded the running job | Network failures retain the job ID and resume polling | Browser went offline, reloaded, and displayed the same job's actual Docker output |
| “Create a Python CLI project” was rejected by the project authorization parser | Bounded descriptive project phrases are recognized; negative and explanation-only requests remain guarded | Actual browser-created main.py, helpers.py, README.md; Docker assertion verifies integer 42 and exact CLI output |
| README generation exhausted output tokens | File generation instructions explicitly request one concise file, without repeated sections | Original incomplete candidate preserved; later real creation completed in 52.6 seconds |
| A qualified function reference was outside filename-only scope | Resolve a Python module/symbol only against a unique existing source that defines it | Real helpers.answer() repair, ambiguous/missing-symbol rejection tests |
| Model proposed overwriting a file requested to be preserved | Literal file-preservation clauses exclude edits/deletions before generation | Repaired helper and main output verified; main.py and keep.txt remain unchanged |
| An existing-project repair with an explicit CLI run request received syntax checks only | The existing Docker validation also runs the mapped staged Python CLI entrypoint | Runtime-failure-before-publication regression; real error/repair/run and independent output checks |
| Control Center text incorrectly said coding models were not enabled | Describe the current task-level capability policy and Docker/Accept controls | Compiled frontend; backend route evidence identifies actual selected workers |

The file-preservation guard distinguishes preserving file bytes from preserving behavior or a backward-compatible import. Regression checks caught and corrected the latter distinction before release.

## Real workflows

- Normal browser Chat produced a real multi-chunk local-model stream, without Agent, retrieval, or Docker requests. Observed total latency: 17.1 seconds for this single practical check.
- Browser upload, indexing, selecting one Knowledge source, and asking through Chat returned the source's 7 repair bays and supervisor Mira with a citation. Source document IDs were independently checked against the selected source.
- The real assessment workbook returned ALR counts with the user-supplied rule of at least 25. Follow-ups “Check Week 1” and “WAT 1” retained the population/rule and returned 23 of 64 for WAT 1.
- Browser file tree/read/search/copy/rename, Monaco edit/save, and new-file creation passed. Browser project generation produced exactly the three requested files; review/Accept and independent Docker function/output assertions passed.
- Existing Summa Todo execution passed through the IDE even with the earlier failed requests present in conversation history. Docker reported HTTP 200.
- A deliberately broken project produced a real ZeroDivisionError. Its exact error was included in repair context. The model repair was staged, Docker-validated, accepted, and independently checked for integer return value, exact main.py output, and preserved unrelated bytes.
- A two-file function rename updated the definition/import/call; independent Docker checks passed and an unrelated sentinel file remained unchanged.
- Real Markdown, DOCX, and XLSX generation passed independent decoding/content checks. XLSX had exactly the requested Checks sheet and Item/Count rows Alpha/7 and Beta/3.
- Generated artifact SHA-256 values remained identical after backend restart, model unload/reload, and launcher restart.
- Real Python, Node, and Java projects used project maps and ran cross-file helper calls in Docker, each printing 42.
- Queue testing recorded an active Docker owner and two queued requests. Cancelling one queued request preserved the active owner and the other request; both completed.
- A real unavailable offline Node start command was reported as a DEPENDENCY blocker through project Run, without a success claim. Raw terminal execution correctly recorded exit 127 and stderr as a failed command.
- Agent and IDE disconnect/reload checks retained the original backend job IDs and displayed final results without restarting the underlying tasks.

## Regression and startup

Backend regression: **1,218 passed, 7 skipped**; results are recorded in `backend-regression-final.txt`. The suite has one existing Starlette/httpx deprecation warning. Archived tests remain archived. Their repository-relative loader paths were corrected, and tests of retained opt-in legacy workflows explicitly select that legacy strategy; production keeps its capability strategy.

Frontend focused request/workspace tests: **17 passed**. Final Svelte check and production build logs are stored with the product evidence.

Both `.\start-sovereign.ps1 -NoBrowser` and `Start SovereignAI.bat -NoBrowser` were exercised from empty ports. Each started a new owned backend and one registered model runtime, with frontend/API on 8088 and model runtime on 8087. Health, served frontend bytes, process identities, and artifact persistence were checked independently.

## Limits

These are product verification cases, not proof of correctness for arbitrary future requests or a model superiority claim. Offline dependencies must exist in the approved sandbox image/bundle. Unsupported dependencies produce a specific blocker; generated code is never executed on the host to bypass it. Model generation can still fail or hit its existing budget. No retries or extra architecture were added to inflate results.

Historical benchmark files and held-out fixtures were not resumed or rewritten by this pass. Existing unrelated working-tree changes were left untouched.

## Follow-up: application folder target

The later failed automatic task `8c11c1c244a94cfc8169128902116cc1` selected `file_run` with target `todo_app`, a directory. File lookup failed and the continuation repeated the same target. Earlier successful checks selected `todo_app/todo_app.py`, so they did not cover this model-plan variation.

The existing Run executor now resolves directory targets through the scoped project map. It uses the typed Docker adapter for resolved Python module entrypoints, preserving HTTP verification for web applications. Ambiguous entrypoints still require clarification. No Todo-specific rule, retry, router, or controller was added.

The exact previously failed directory target now passed real Docker HTTP 200. A fresh browser natural-language request with failed history also passed. Application-tool tests: 48 passed; preview/runtime tests: 13 passed. Raw original failure and corrected run are saved as `todo-folder-original-failure.json` and `todo-folder-run-fixed.json`.
