# Code Fidelity & Repair — Phase C, 2026-10-03

Production remains frozen. All 60 scheduled executions finished: 20 new contracts × three arms. No old benchmark or held-out data was modified. This small diagnostic does not establish overall architectural superiority.

## Design and evidence

A skips Qwen planning and uses the existing Coder workflow. B forces the existing Qwen3.5 plan → Coder path. C uses the unchanged Smart Router. The common Coder operation planner, tools, project inputs, private Docker oracle and existing bounded repair policy are identical. Direct does not mean a newly invented one-call generator. Arm order rotates; model residency carries over. Twenty distinct behaviors share a two-file service skeleton, so this is not a broad application-engineering benchmark. No extra retries were added.

The private oracle was authored independently of the evaluated models and never supplied to them. Twenty positive reference implementations passed Docker checks; twenty initial stubs failed. The corrected offline component observer also passed all twenty positive controls. These finite tests do not prove every possible behavior.

Full raw executions are in `benchmarks/code-fidelity-repair/raw/`. `results.json` preserves raw statuses; `evidence-index.json` maps all 17 requested fields. Empty candidate/Docker fields mean the operation stopped before that stage, never a pass. `analysis.json` supplies clustered paired analysis.

## Results

| Arm | Passed | Operational failures | Median task seconds | Model calls | Switches | Verified repair recoveries |
|---|---:|---:|---:|---:|---:|---:|
| A | 3/20 | 17 | 34.60 | 109 | 1 | 0 |
| B | 4/20 | 16 | 62.84 | 132 | 40 | 0 |
| C | 4/20 | 16 | 62.48 | 124 | 39 | 0 |

Raw NOT_VERIFIED with a known operation error is counted as an operational failure, not an independently tested candidate failure. One C execution (histogram) failed model startup, with zero model calls; this is TOOL / runtime availability, not demonstrated routing or generation failure.

B gained paths, pagination and statistics relative to A, but lost escaping and polynomial. Transitions passed all arms. B and C have identical task-level pass/fail outcomes. The paired planning advantage is +5 percentage points, exploratory task-bootstrap 95% interval −15 to +25 points, discordant exact p=1. This does not demonstrate a reliable planning benefit. Median paired added latency is 28.00 seconds for B and 29.08 seconds for C.

| Contract | A | B | C |
|---|---|---|---|
| ledger | FAIL | NOT_VERIFIED | NOT_VERIFIED |
| ranges | FAIL | NOT_VERIFIED | NOT_VERIFIED |
| paths | NOT_VERIFIED | PASS | PASS |
| csvrows | NOT_VERIFIED | NOT_VERIFIED | NOT_VERIFIED |
| money | NOT_VERIFIED | NOT_VERIFIED | NOT_VERIFIED |
| topology | FAIL | NOT_VERIFIED | NOT_VERIFIED |
| inventory | FAIL | FAIL | FAIL |
| escaping | PASS | NOT_VERIFIED | NOT_VERIFIED |
| pagination | NOT_VERIFIED | PASS | PASS |
| versions | FAIL | NOT_VERIFIED | NOT_VERIFIED |
| rle | NOT_VERIFIED | FAIL | FAIL |
| dedup | NOT_VERIFIED | NOT_VERIFIED | NOT_VERIFIED |
| dates | NOT_VERIFIED | NOT_VERIFIED | NOT_VERIFIED |
| polynomial | PASS | NOT_VERIFIED | NOT_VERIFIED |
| histogram | FAIL | FAIL | NOT_VERIFIED |
| queues | FAIL | FAIL | FAIL |
| statistics | NOT_VERIFIED | PASS | PASS |
| transitions | PASS | PASS | PASS |
| network | FAIL | FAIL | FAIL |
| formatting | NOT_VERIFIED | NOT_VERIFIED | NOT_VERIFIED |

## Answer-bound failure review

Every captured source handoff retains the original request. Literal requirement loss in transport is not established. Qwen planning receives the request and file names/sizes, but not actual source interfaces. Coder receives source later. This weakens planning grounding; shorthand such as run() is not by itself proof of a lost signature. A richer handoff contract is a concrete candidate for a later isolated change, not a fix implemented here.

Ledger A uses isinstance(entry, int), which accepts bool contrary to the request, and service.run duplicates computation instead of delegating. Both failed checks persist after repair. Inventory candidates fail atomic/copy behavior. Versions A raises IndexError on a tested valid comparison and misses a required ValueError check. RLE B/C accept an invalid count. Several generated strings contain invalid escaping and never become executable Python. Repeated workspace paths are malformed plans; the existing tool correctly rejects them. These are PLAN or MODEL_GENERATION failures, not evidence that the tool or router is broken.

Histogram B initially omits compatibility_tag; repair restores that binding but remains behaviorally failing. No assembled candidate shows actual unrelated-file removal. Protected-file proposals do occur and are rejected: targeting a protected path, proposing changed bytes, and successfully saving/deleting a file are different events. No candidate was accepted into production. Lambda-bound compatibility_tag is a preserved callable, not an omitted symbol.

Offline per-statement replay found no previously passing ordinary oracle check turning into a failed check across saved completed repairs. This is limited evidence, not proof that repair preserves all behavior: some attempts never assemble, some replay executions have no check output, and finite tests are incomplete. The optional sample-mutation check in observer v1 failed because AST locations were absent; its index −1 records are excluded from regression conclusions. The corrected observer passes reference controls; candidate mutation claims must use the original trusted tests/source inspection.

## Per-execution classification and resource evidence

The following classifications are evidence tags, not mutually exclusive causal counts. ROUTER is not assigned without a demonstrated decision error. CONTEXT/HANDOFF risks are discussed above, not invented from a failed result. Runtime availability is classified TOOL with an environment subtype because Phase C has no ENVIRONMENT category.

| Case/arm | Classification | Exact boundary or trusted error | RAM MiB peak | VRAM MiB peak |
|---|---|---|---:|---:|
| ledger/A | MODEL_GENERATION, REPAIR | Independent trusted validation failed (exit=1; diagnostic_sha256=7f6305af373111e399991260e8442d99d4e7af8eb238e1b1d59a550a16bff141): AssertionError | 2571.4 | 3686.0 |
| ledger/B | MODEL_GENERATION, REPAIR | Generated ledger.py lacks substantive Python content after three attempts: Python syntax error on line 6: unexpected character after line continuation character. No project changes were saved | 3477.1 | 3239.0 |
| ledger/C | MODEL_GENERATION, REPAIR | Generated ledger.py lacks substantive Python content after three attempts: Python syntax error on line 6: unexpected character after line continuation character. No project changes were saved | 3482.8 | 3207.0 |
| ranges/B | PLAN | The plan repeats a workspace path | 3484.4 | 3304.0 |
| ranges/C | PLAN | The plan repeats a workspace path | 3485.3 | 3260.0 |
| ranges/A | MODEL_GENERATION, REPAIR | Independent trusted validation failed (exit=1; diagnostic_sha256=e4d0c594d7c39c5aec22506d83660d9dab528a3187a1fab62b798cedba0732c1): TypeError | 2517.9 | 3208.0 |
| paths/C | PASS | Independent contract checks passed | 3486.0 | 3211.0 |
| paths/A | PLAN | The plan repeats a workspace path | 2495.0 | 3210.0 |
| paths/B | PASS | Independent contract checks passed | 3486.9 | 3208.0 |
| csvrows/A | PLAN | The plan repeats a workspace path | 2486.9 | 3242.0 |
| csvrows/B | PLAN | The plan repeats a workspace path | 3490.2 | 3241.0 |
| csvrows/C | PLAN | The plan repeats a workspace path | 3486.9 | 3206.0 |
| money/B | PLAN | The plan repeats a workspace path | 3487.7 | 3206.0 |
| money/C | PLAN | The plan repeats a workspace path | 3485.8 | 3244.0 |
| money/A | PLAN | The plan repeats a workspace path | 2486.5 | 3242.0 |
| topology/C | PLAN | Tool coding_project_candidate failed: Validation candidate contains a fixture-protected path | 3490.6 | 3312.0 |
| topology/A | MODEL_GENERATION, REPAIR | Independent trusted validation failed (exit=1; diagnostic_sha256=a1ed97dad2d5f09cf5362cd3e95bc49f99b8d0f00ed1ea48517edb1e8276363e): AssertionError | 2536.1 | 3384.0 |
| topology/B | PLAN | Tool coding_project_candidate failed: Validation candidate contains a fixture-protected path | 3485.4 | 3237.0 |
| inventory/A | PLAN, REPAIR | Tool coding_project_candidate failed: Validation candidate contains a fixture-protected path | 2611.9 | 3205.0 |
| inventory/B | MODEL_GENERATION, REPAIR | Independent trusted validation failed (exit=1; diagnostic_sha256=a19b88f389bf74418100d730969a3bacf69665455ad169a5de2a4c9094c7fae7): AssertionError | 3480.6 | 3408.0 |
| inventory/C | MODEL_GENERATION, REPAIR | Independent trusted validation failed (exit=1; diagnostic_sha256=a19b88f389bf74418100d730969a3bacf69665455ad169a5de2a4c9094c7fae7): AssertionError | 3482.3 | 3389.0 |
| escaping/B | PLAN | The plan repeats a workspace path | 3487.0 | 3417.0 |
| escaping/C | PLAN | The plan repeats a workspace path | 3488.1 | 3535.0 |
| escaping/A | PASS | Independent contract checks passed | 2494.5 | 3482.0 |
| pagination/C | PASS | Independent contract checks passed | 3490.7 | 3452.0 |
| pagination/A | PLAN | Task interpretation was incomplete | 2540.7 | 3454.0 |
| pagination/B | PASS | Independent contract checks passed | 3489.5 | 3416.0 |
| versions/A | MODEL_GENERATION, REPAIR | Independent trusted validation failed (exit=1; diagnostic_sha256=6a3ff64c65dbaa5e80d912ed7e928fbf5ee767af4678f72e4d8b2b074c6552fa): IndexError: list index out of range | 2541.4 | 3442.0 |
| versions/B | MODEL_GENERATION | Generated unrelated.py lacks substantive Python content after three attempts: Python syntax error on line 3: unterminated string literal (detected at line 3). No project changes were saved | 3490.3 | 3450.0 |
| versions/C | MODEL_GENERATION | Generated unrelated.py lacks substantive Python content after three attempts: Python syntax error on line 3: unterminated string literal (detected at line 3). No project changes were saved | 3489.8 | 3413.0 |
| rle/B | MODEL_GENERATION, REPAIR | Independent trusted validation failed (exit=1; diagnostic_sha256=73439843a117f022c16b83b378783e510ee8a24721fc9f39b5a5119555fede83): AssertionError | 3491.1 | 3447.0 |
| rle/C | MODEL_GENERATION, REPAIR | Independent trusted validation failed (exit=1; diagnostic_sha256=73439843a117f022c16b83b378783e510ee8a24721fc9f39b5a5119555fede83): AssertionError | 3489.1 | 3412.0 |
| rle/A | PLAN | The plan repeats a workspace path | 2534.5 | 3413.0 |
| dedup/C | PLAN, REPAIR | Tool coding_project_candidate failed: Validation candidate contains a fixture-protected path | 3492.4 | 3419.0 |
| dedup/A | PLAN | Candidate changed a fixture-protected path: unrelated.py | 2586.4 | 3411.0 |
| dedup/B | PLAN, REPAIR | Tool coding_project_candidate failed: Validation candidate contains a fixture-protected path | 3496.6 | 3508.0 |
| dates/A | PLAN | The plan repeats a workspace path | 2578.6 | 3444.0 |
| dates/B | PLAN | Task interpretation was incomplete | 3498.3 | 3405.0 |
| dates/C | PLAN | Task interpretation was incomplete | 3496.2 | 3766.0 |
| polynomial/B | PLAN | Tool coding_project_candidate failed: Validation candidate contains a fixture-protected path | 3495.4 | 3646.0 |
| polynomial/C | PLAN | Tool coding_project_candidate failed: Validation candidate contains a fixture-protected path | 3498.7 | 3614.0 |
| polynomial/A | PASS | Independent contract checks passed | 2530.8 | 3385.0 |
| histogram/C | TOOL | Runtime availability: Server failed to start in 30 seconds | 2638.5 | 3385.0 |
| histogram/A | MODEL_GENERATION, REPAIR | Independent trusted validation failed (exit=1; diagnostic_sha256=f261f5d9173df344f2c887d74c9a155a32feaa4f60084fbf21ff4559de3514fa): AssertionError | 2511.4 | 2859.0 |
| histogram/B | MODEL_GENERATION, REPAIR | Independent trusted validation failed (exit=1; diagnostic_sha256=52531789f68bc87cffd1f94a14d52f0eae1ec715f68f8e38332a524f9dab366f): AssertionError | 3501.9 | 2821.0 |
| queues/A | MODEL_GENERATION, REPAIR | Independent trusted validation failed (exit=1; diagnostic_sha256=1f4e57aa5d31dc247b779574abd42117d13808e13ae790b3bca2368467ffd021): AssertionError | 2570.0 | 2831.0 |
| queues/B | MODEL_GENERATION, REPAIR | Independent trusted validation failed (exit=1; diagnostic_sha256=826031db594d37ea0c723fc4e4499fa1dc8593917ce08223ad02ca943ae519ad): TypeError | 3500.9 | 2838.0 |
| queues/C | MODEL_GENERATION, REPAIR | Independent trusted validation failed (exit=1; diagnostic_sha256=826031db594d37ea0c723fc4e4499fa1dc8593917ce08223ad02ca943ae519ad): TypeError | 3504.0 | 2835.0 |
| statistics/B | PASS | Independent contract checks passed | 3502.8 | 2839.0 |
| statistics/C | PASS | Independent contract checks passed | 3495.8 | 2854.0 |
| statistics/A | PLAN | Tool coding_project_candidate failed: Validation candidate contains a fixture-protected path | 2504.4 | 2855.0 |
| transitions/C | PASS | Independent contract checks passed | 3490.9 | 2995.0 |
| transitions/A | PASS | Independent contract checks passed | 2522.3 | 2949.0 |
| transitions/B | PASS | Independent contract checks passed | 3495.1 | 2924.0 |
| network/A | MODEL_GENERATION, REPAIR | Independent trusted validation failed (exit=1; diagnostic_sha256=be95ed1d5501cc654a1c21e3a022be3f34083dcf6dae913a77998b00b7a55da4): AssertionError | 2546.7 | 2924.0 |
| network/B | MODEL_GENERATION, REPAIR | Independent trusted validation failed (exit=1; diagnostic_sha256=b5c0aeb9e418d1103ae15159090b7f7b0bd5bad8574ce8244ae2c3278b0428e5): TypeError | 3487.8 | 2931.0 |
| network/C | MODEL_GENERATION, REPAIR | Independent trusted validation failed (exit=1; diagnostic_sha256=b5c0aeb9e418d1103ae15159090b7f7b0bd5bad8574ce8244ae2c3278b0428e5): TypeError | 3495.5 | 2922.0 |
| formatting/B | MODEL_GENERATION | Generated formatting.py lacks substantive Python content after three attempts: Python syntax error on line 5: unterminated string literal (detected at line 5). No project changes were saved | 3490.9 | 3406.0 |
| formatting/C | MODEL_GENERATION | Generated formatting.py lacks substantive Python content after three attempts: Python syntax error on line 5: unterminated string literal (detected at line 5). No project changes were saved | 3494.1 | 3249.0 |
| formatting/A | MODEL_GENERATION | Generated formatting.py lacks substantive Python content after three attempts: Python syntax error on line 4: unterminated string literal (detected at line 4). No project changes were saved | 2502.6 | 2993.0 |

Memory values are sampled runtime process/device peaks, not total machine RAM requirements; sequential sampling can miss brief peaks. Each task observed at most one llama-server process. No overlap of two model servers was observed.

## Switch analysis

B has 40 switches (Qwen then Coder per task). C has 39: the histogram startup failure stopped after one switch. A has one switch after that failed startup changed residency. Switching is necessary to execute the forced two-model path; that does not establish policy necessity. On three tasks planning is associated with a pass that A lacks; on two it is associated with losing A’s pass; on transitions it adds cost without changing the passing outcome; on fourteen tasks neither path passes. Association is not proof of causality, especially with a single execution per arm. There is no evidence justifying mandatory switching for every multi-file request.

## Smallest evidence-supported recommendations

1. Retain Coder direct as the low-cost baseline and a candidate default for validated classes; 3/20 means it is not sufficient generally.
2. Do not make Qwen→Coder mandatory. The three observed planning wins warrant replication on new contracts before defining a narrow production class.
3. Test a handoff contract containing exact public interfaces, protected paths, exception/output obligations and the untouched original request. Ground planning in actual source interfaces.
4. Test repair feedback with public requirement identifiers and preservation checks while keeping private test values hidden. Existing AssertionError-only feedback is too vague to locate many semantic defects; more retries are not supported.
5. Defer router retraining/redesign. Model output, malformed plans and repair fidelity need isolated experiments first. A new router cannot by itself correct an already selected Coder’s bool acceptance or invalid Python.

No production changes are implemented. These are proposed bounded experiments, not another agent/reviewer/controller.

## Latest pasted research proposal

The upstream mini-coder model card reports agent-trajectory training and SWE-bench results, making it a relevant challenger, not a demonstrated local replacement: https://huggingface.co/ricdomolm/mini-coder-1.7b . Granite is another published candidate: https://huggingface.co/ibm-granite/granite-4.2-3b . mini-SWE-agent and RoRF are separate scaffold/router experiments: https://github.com/SWE-agent/mini-swe-agent and https://github.com/Not-Diamond/RoRF . Their upstream claims do not validate SovereignAI.

A model experiment should hold the scaffold fixed; a scaffold experiment should hold the model fixed. Replacing model and loop together would confound attribution. Do not train a router on this diagnostic then report these same tasks as held-out performance. Production freeze and the explicit no-new-model instruction remain in force; no candidates were installed or registered.

## Observer incidents and preservation

A preflight ledger/A capture was lost to an observer decode error and is NOT_VERIFIED outside the final 60; it is not a recovery or pass. After 18 recorded rows, protected-path auditing rejected an already saved inventory/A raw artifact; it was recovered without a model rerun. Both observer versions and corrections are retained. The def-only symbol audit was corrected to include lambda assignments. Optional mutation observer v1 is retained and excluded as described above. These corrections changed observation only.

Frozen production/historical hash changes: []. Raw benchmark evidence and historical hashes are preserved. No overall superiority claim is warranted.
