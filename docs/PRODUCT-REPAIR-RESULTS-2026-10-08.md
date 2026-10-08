# SovereignAI product repair results — 8 October 2026

Status: INCOMPLETE. The user prioritized product repair and stopped the model benchmark. Its 22 completed cells, original outcomes and interrupted raw trajectory remain preserved. No model winner is selected from this incomplete comparison.

## Repairs applied to source

| Failure | Repair | Evidence |
|---|---|---|
| Numeric text produces different comparisons from numeric cells | Use one finite numeric interpretation for comparison, filters and outcome score discovery; preserve original cells | Six numeric representation/invalid-value checks plus outcome binding regression |
| Infinity and booleans satisfy numeric score filters | Reject nonfinite values and booleans as measurements | Before/after numeric counterexamples |
| Lowest-value question receives only maxima | Display computed minima and maxima; remove unsupported aggregate field-lead ranking | Independent two-record cost comparison |
| Business filter appears before identity filter | Use unambiguous literal source ID matches among filtered columns | Missing requested sibling identity remains explicitly reported |
| Threshold followed by sentence punctuation is treated as absent | Recognize a terminal full stop without accepting fragments inside identifiers or decimal sequences | Explicit threshold with numeric text score records |
| Workspace/entrypoint replacement closes active preview | Hold preview ownership until its response is consumed | Deterministic concurrent preview replacement counterexample |
| Nested cache digests exceed Windows path limit | Use one full digest of revision plus entrypoint; migrate legacy database without deleting it | Live Windows Docker preview and state migration/isolation checks |
| Failed subprocess assertion loses the command and output | Capture bounded CompletedProcess args, exit status, stdout/stderr and nearby assertion source | Actual Docker failure probe in repair-observation.json |
| Numeric equality compares formatted strings rather than values | Compare explicit numeric operands as finite numbers while preserving literal string identities | Integer/numeric-text equality and leading-zero identity regressions |
| Repair evidence is repeated in source-generation context | Include validation evidence once and explicitly identify the supplied source as a failed candidate | Raw Coder prompt usage decreased from 11,553 to 8,831 tokens across two calls; repair still failed |

These changes do not add a model, planner, reviewer, controller or router. Generated code continues to execute only in Docker, and publication still requires explicit acceptance.

## Live preview acceptance

A disposable Flask/SQLite fixture ran through the repaired Python preview implementation in the pinned Docker image. CRUD, HTTP 204, persisted state after worker replacement and independent entrypoint databases passed. First request took 8.797 seconds; warm requests took 0.188–0.281 seconds; worker replacements took 2.219–2.968 seconds. These are one local run, not population latency estimates. The test directly loaded repaired source; it does not establish that the existing API process has reloaded it.

## Real model-created applications

The inventory application was authored by the local model. Its candidate passed the independent Docker oracle, including cross-file imports, stock preservation, exception semantics and CLI error exits. Its full product workflow remained FAILED because no executable acceptance fixture was supplied to the application beforehand. This is an acceptance-contract limitation, not a validated end-to-end success. The original result is preserved without relabeling.

The notes application was also model-authored and had supplied independent tests. It failed because malformed stored JSON was converted to an empty successful result. Its raw generated candidates, failed tests and independent oracle are preserved. Supplying the exact subprocess command, output and assertion did not recover the behavior. Raw Coder responses confirmed unchanged defective files were emitted by the model, rather than lost by the client. Removing duplicate repair evidence reduced measured prompt tokens by 23.6%, but did not recover correctness. A temporary coding-skill instruction also failed its model check and was reverted. No result here counts toward the stopped benchmark.

Isolated bounded-patch probes with the existing Coder and installed Granite models also failed the same immutable Docker acceptance test. Neither patch was applied to production. A Qwen reasoning-mode probe at 1,536 tokens failed structured-output normalization before raw response persistence; its exact finish reason is unavailable and that missing-evidence limitation is recorded. A separate raw-capture probe using the existing 6,144-token source budget timed out at the 300-second HTTP read boundary without a completion response. Runtime logs confirm request release and all slots idle; no candidate reached Docker. Its timeout evidence is preserved. The diagnostic harness now records requests before calling the runtime and persists exceptions, preventing this evidence gap on later runs. These development probes do not establish a model ranking or justify additional repair attempts in production.

## Regression verification

The latest full source run explicitly selecting `_review_for_deletion/tests`, `tests` and the numeric diagnostic passed 1,323 tests, skipped 7 and had one existing Starlette/httpx deprecation warning. Seven additional benchmark-stop/status tests passed separately. The frontend Svelte/TypeScript check completed with zero errors and zero warnings; this is static verification, not live browser acceptance. Earlier runs used different selections; their original logs remain preserved. The earlier process-readiness mock was missing a running-process poll result; correcting that test fixture resolved its failure. Docker probes separately verified the preview and actual failed-process observation.

## Deployment and remaining gates

The running API was idle when restart was attempted. Automatic approval review rejected the process restart command with `blocked by policy`; it supplied no more specific reason. The command did not execute. Consequently, repaired source is saved and tested, but loading it into that API process remains unverified. No alternate command was used to bypass the rejection.

Remaining work includes ordinary creation requests without pre-supplied acceptance tests, independently verified recovery of model-generated logic errors, runtime/native tool-format reliability, live UI lifecycle/reconnection, and complete product acceptance after the repaired backend is loaded. Passing regressions alone does not establish universal prompt understanding or a fully working product.

## Evidence locations

- `evidence/product-reliability-v1/`: numeric before/after evidence, regression logs, live model trajectories, preview results and repair observations.
- `tests/test_product_reliability.py`: source-bound counterexamples and cache/concurrency checks.
- `evidence/code-agent-fidelity-v1/reports/user-stop-20261007-211104/`: preserved benchmark stop checkpoint.
