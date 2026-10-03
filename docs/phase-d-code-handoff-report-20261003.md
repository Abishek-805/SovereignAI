# Phase D — code handoff and repair fidelity

Primary comparison: **COMPLETED**, 60/60 executions. Secondary repair feedback: **COMPLETED**, 20/20 executions. Separate integration: **COMPLETED**.

## Architecture change summary

Production router, model registry, Model Broker, Docker sandbox, publication controls, historical benchmarks, held-out sets and Phase C evidence remained frozen. Phase D used disposable Workbench instances and an observational harness. A uses Coder direct; B adds the existing Qwen plan and handoff; C changes the Qwen planning input and Coder handoff to a bounded public source contract. All three arms have the same models, tools, sandbox, private validation, existing repair budget and preservation gate. The gate checks required files, symbols and signatures, protected bytes and target scope before behavioral tests; it does not claim behavior succeeds.

Source grounding and structured handoff changed together in C, so their separate effects cannot be attributed. The secondary R arm repeats C with bounded public-source repair diagnostics; it is analyzed separately. No new model, agent, reviewer, routing rule or generic retry was introduced.

## Design and task list

Twenty independently authored two-file contracts use a common feature/adapter skeleton. Each requires exact signatures, adapter delegation and an unchanged protected file. The private Docker checks were absent from all model inputs. Positive references passed 20/20; initial stubs failed 20/20. Schema and preservation controls passed for all 20 tasks, including 80 deliberate negative mutations. A separate three-module parcel-manifest task tests annotated interfaces and integration.

| Task | A | B | C | R |
|---|---|---|---|---|
| credits | PASS | FAIL | PASS | PASS |
| windows | NOT_VERIFIED | FAIL | NOT_VERIFIED | NOT_VERIFIED |
| baskets | NOT_VERIFIED | NOT_VERIFIED | PASS | PASS |
| revision | NOT_VERIFIED | NOT_VERIFIED | NOT_VERIFIED | NOT_VERIFIED |
| runs | FAIL | FAIL | PASS | PASS |
| letters | FAIL | FAIL | NOT_VERIFIED | FAIL |
| streams | NOT_VERIFIED | FAIL | FAIL | FAIL |
| config | PASS | PASS | FAIL | FAIL |
| labels | FAIL | NOT_VERIFIED | FAIL | FAIL |
| chunks | NOT_VERIFIED | PASS | NOT_VERIFIED | NOT_VERIFIED |
| ranking | FAIL | NOT_VERIFIED | NOT_VERIFIED | NOT_VERIFIED |
| pathsafe | NOT_VERIFIED | FAIL | FAIL | FAIL |
| timestamps | NOT_VERIFIED | FAIL | NOT_VERIFIED | NOT_VERIFIED |
| pairs | PASS | FAIL | FAIL | NOT_VERIFIED |
| rotation | PASS | PASS | PASS | PASS |
| catalog | NOT_VERIFIED | NOT_VERIFIED | NOT_VERIFIED | NOT_VERIFIED |
| distance | PASS | PASS | FAIL | FAIL |
| brackets | FAIL | NOT_VERIFIED | NOT_VERIFIED | NOT_VERIFIED |
| updates | NOT_VERIFIED | PASS | FAIL | FAIL |
| indentation | NOT_VERIFIED | NOT_VERIFIED | NOT_VERIFIED | NOT_VERIFIED |

PASS means final independent Docker checks passed. FAIL means a completed candidate failed. NOT_VERIFIED means no independently verified final candidate; the exact reason is in raw evidence. PARTIAL is reserved for a validated subset that does not satisfy the complete request; no task is promoted to PASS from partial checks. BLOCKED is an unavailable environment. UNKNOWN marks an unmeasured semantic property.

Supplemental answer-bound review: the original `credits` oracle omitted the explicit finite-value obligation. `credits` A and C accepted infinity/NaN in later independent Docker probes. Their primary PASS labels remain immutable evidence, but their semantic status is **PARTIAL**. All twelve other primary PASS candidates passed their targeted supplemental probes. A finite set of probes still cannot prove full correctness.

After these targeted probes, semantic PASS counts are A 4/20, B 5/20, C 3/20 and R 3/20. R’s `credits` result also downgrades to PARTIAL. Primary and semantic counts answer different questions; neither is silently substituted for the other.

## Paired results and resources

| Arm | Validated PASS | Median seconds | Calls | Switches | Behavior repairs | Peak process RAM MiB | Peak sampled VRAM MiB |
|---|---:|---:|---:|---:|---:|---:|---:|
| A | 5/20 | 33.2 | 124 | 0 | 1 | 2681 | 3105 |
| B | 5/20 | 62.1 | 158 | 40 | 2 | 3511 | 3143 |
| C | 4/20 | 59.3 | 124 | 40 | 0 | 3529 | 3071 |
| R | 4/20 | 54.9 | 126 | 40 | 0 | 3507 | 2955 |

| Pair | Tasks | Left-only passes | Right-only passes | Pass delta right-left | Task bootstrap 95% | Median paired seconds right-left |
|---|---:|---:|---:|---:|---|---:|
| AB | 20 | 2 | 2 | +0.00 | [-0.2, 0.2] | +30.1 |
| BC | 20 | 4 | 3 | -0.05 | [-0.3, 0.2] | -3.6 |
| AC | 20 | 3 | 2 | -0.05 | [-0.25, 0.15] | +25.5 |
| CR | 20 | 0 | 0 | +0.00 | [0, 0] | -2.7 |

These intervals resample tasks, not executions. One execution per task/arm and model residency carryover limit causal claims; R runs later than C, adding temporal confounding. Reported RAM is sampled process usage and VRAM is sampled device usage, not guaranteed hardware requirements.

## Handoff, plans and failures

The C contract preserves original_user_request separately and includes exact parsed function signatures/imports, bounded source excerpts, allowed/protected paths, expected inputs/outputs, exception obligations, diagnostics and acceptance requirements. Schema validation ran before generation. Raw model requests, plans, exact Coder messages, candidates, diffs, Docker trajectories and repair contexts are in the evidence archive. Supplied context is measurable; semantic comprehension of each plan remains subject to answer-bound review.

C received all parsed public interfaces in 20/20 tasks. All 12 C tasks reaching source generation retained both the original request and contract in Coder’s exact input messages. The Qwen planning payload had a placeholder workspace label; Coder’s handoff was updated to the actual isolated workspace identifier. This limits the claim of complete planner grounding. Source excerpts and interface fields did not prevent incorrect plans or invalid source output.

Answer-bound contradictions: the B plan for `config` said to return a missing value without raising, while the request required KeyError. The C plan for `updates` said to apply truthy values, while the request required retaining non-None falsy values. These are demonstrated PLAN faults; other plans are not exhaustively certified.

| Failure category | Observed task/arm count | Evidence boundary |
|---|---:|---|
| PLAN | 18 | See `analysis.json` review entry and raw trace. |
| HANDOFF | 0 | See `analysis.json` review entry and raw trace. |
| CONTEXT | 0 | See `analysis.json` review entry and raw trace. |
| MODEL_GENERATION | 44 | See `analysis.json` review entry and raw trace. |
| REPAIR | 40 | See `analysis.json` review entry and raw trace. |
| TOOL | 0 | See `analysis.json` review entry and raw trace. |
| SANDBOX | 0 | See `analysis.json` review entry and raw trace. |
| VALIDATION | 0 | See `analysis.json` review entry and raw trace. |
| RUNTIME | 0 | See `analysis.json` review entry and raw trace. |

Failure tags may overlap. A malformed plan rejected by the tool is a PLAN failure unless the tool itself demonstrably malfunctioned. An environment or model-start failure is RUNTIME. The router is not blamed without a concrete bad classification decision; no router changes were made.

## Repair and preservation

The primary comparison retained the existing bounded repair budget. In the secondary R arm, the first attempt receives the same grounded handoff as C; later attempts also receive public-source diagnostics and the actual bounded Docker message. The diagnostic does not inspect private oracle source or disclose test inputs or expected private constants. Identical first candidates across C/R, where observed, are the strongest paired evidence for feedback effects. Differences in first candidates mean later success cannot be attributed solely to feedback.

R and C had identical task-level PASS outcomes, 4/20 each. The added public diagnostic reached nine repair sequences; five began with byte-identical captured candidates, and none produced an independently verified behavioral recovery. Each arm recorded one preservation-only recovery. The feedback does not show a measurable benefit on this sample.

The replayed component checks and exact candidate traces show whether required symbols or previously passing checks disappear after repair. A syntactic preservation pass is not proof of requested behavior. Protected-path changes were rejected before independent behavioral validation. No generated candidate was published to the user project.

One concrete repair-induced regression occurred in `timestamps` B: attempt 1 retained `legacy_label()` and passed its component check; attempt 2 removed it while trying to repair time parsing. The preservation gate rejected attempts 2 and 3. This is REPAIR plus MODEL_GENERATION, while the gate behaved as intended. The component replay covers every saved assembled candidate; malformed generations without assembled candidates remain NOT VERIFIED at that stage.

## Separate live integration

Parcel manifest arm C: raw NOT_VERIFIED, independent verification None, 4 model calls, 2 switches, 44.8s. Exact plan, candidate, Docker output and repair history are in `benchmarks/phase-d-live-integration/results.json`.

The separate parcel-manifest trace revealed an ambiguity: its request did not explicitly define whether `units` means line-item count or summed quantities, while the private oracle assumes summed quantities. Qwen planned `len(items)`. Coder’s workspace plan then repeated a path and the existing boundary rejected it before source generation; no Docker candidate or repair occurred. This integration is **NOT VERIFIED** and its oracle ambiguity limits interpretation. The primary synthetic `rotation` C trace is a complete worked two-file example: grounded plan and handoff, candidate missing `legacy_label`, preservation Docker rejection, bounded repair, final independent Docker PASS. Its repair proves symbol preservation, not a behavioral fix. No real three-module integration completed end to end.


## Security, publication and regression

Frozen baseline hash changes: **0**. All evaluated rows have publication state NOT_ACCEPTED. Only the generated public contract was sent to the models; private reference implementations and oracle source stayed in the harness/Docker validation path. The observer stores private traces locally in the evidence archive for audit and never injects them into a model context.

Limitations: 20 multi-file contracts share an adapter skeleton; not broad application tasks; One execution per arm, rotating order with warm residency carryover; Secondary R is run later; temporal/resource drift can confound latency; Preservation gate common to all arms changes evaluation controls, not production scaffold; Source-grounding and structured handoff change together in C; they cannot be individually attributed; Private oracles are finite; do not prove every requested corner case; Structured repair feedback flags public-source risks, not hidden assertion values.

## Evidence-based decisions

1. Retain Coder direct as the low-cost baseline in the diagnostic. B matched its primary pass count but cost 34 more calls, 40 switches and about 30 seconds more median paired latency. The paired interval includes both benefit and harm, so the evidence does not justify broad Qwen planning.
2. Do not promote the grounded C handoff: it delivered source interfaces, yet had one fewer primary pass than B and two fewer semantic passes. Source grounding and contract structure changed together, so their separate effects remain unknown.
3. Do not promote public repair feedback R: C and R had the same task-level outcomes and R had zero verified behavioral recoveries.
4. Investigate the evidenced workspace-plan repetition and repair-induced symbol deletion within a separately reviewed change. The current preservation gate correctly rejected lost symbols; keep it in the diagnostic.
5. Keep the router frozen. No task demonstrates a bad classifier decision, and no ROUTER blame is supported. Any future handoff or repair change needs a replicated source-grounded comparison before production implementation.

No final recommendation was implemented automatically. Full task-level evidence, result state, control results and hash manifests are preserved in the Phase D evidence archive.
