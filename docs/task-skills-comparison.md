# Task skills: implementation and before/after diagnostic

Implemented eight application-owned capability skills: chat, evidence answers, documents, spreadsheets, coding, project runner, artifacts and workspace. The shared task contract and relevant stage instructions are injected into actual model requests. Token admission includes these instructions; route telemetry records instruction hashes. Backend permissions, sandbox, budgets and validation remain authoritative. No model, controller or router was added.

The library is enabled by default. Set `SOVEREIGN_TASK_SKILLS=0` before starting the backend to disable it. See [capability index](../skills/INDEX.md).

## Paired development results

Fixed resident Qwen3.5-4B, same task fixtures, tools, budgets and validation, skills off versus on. Twelve task pairs were executed; one ambiguous coding oracle was excluded from the reliability denominator, with original outcomes preserved.

| Metric | Before | After |
| --- | ---: | ---: |
| Valid checks passed | 6/11 | 11/11 |
| Structured-data checks | 1/6 | 6/6 |
| Operation-plan checks | 3/3 | 3/3 |
| Docker repair check | 1/1 | 1/1 |
| Grounded-answer check | 1/1 | 1/1 |
| Median task latency | 7.48 s | 7.40 s |
| Model calls | 11 | 11 |
| Prompt tokens | 11,984 | 16,489 |

Prompt tokens increased 37.6%; this is not a token-saving result. Cache state was uncontrolled, so the latency difference does not establish a speed improvement. Operation-plan checks establish valid plans, not completed external operations. This small development suite does not prove universal reliability or improvement across every installed model.

The first four-profile implementation regressed from 6/11 to 5/11 and was rejected. The final eight-skill revision was evaluated against the preserved baseline. Instructions were developed using this development suite; these are not held-out results. Two harness defects were corrected with original invalid evidence retained. The excluded exception task did not specify tuple versus dictionary item representation, while its oracle required tuples; neither arm is penalized in the audited comparison.

## Independent live verification and separate answer fix

A real selected workbook exposed an additional failure: the query tool correctly counted CAT 1 as 31 passes, but generated prose changed it to 1. The existing numeric validator accepted that number because it occurred elsewhere. Skills alone did not prevent this failure.

A separate general fix now renders supported deterministic table-query results directly, preserving each value's field and assessment association. It covers select, count, sum, average, minimum, maximum and percentage. Its benefit is not credited to the skill-only comparison above.

Independent parsing of the complete workbook confirmed 64 ALR records and the reported explicit-label pass counts: Week 3 = 1, Week 4 = 18, Week 5 = 34, Week 6 = 28, CAT 1 = 31. The live answer matched all five. Two other sheets lacked an explicit outcome rule; the response identified that limitation instead of inventing a threshold. Live answer latency was 48.7 seconds.

The live request to run the todo application completed with Docker exit 0 and HTTP 200. It took 88.4 seconds; latency remains an unresolved practical limitation. This observation is not a controlled before/after speed comparison.

## Verification and preserved evidence

195 relevant automated tests passed, covering model integration, skill selection, token accounting, application tools, query regressions, answer rendering and API behavior.

Machine-readable results and exact request/response trajectories are preserved under:

- `outputs/task-skill-comparison/`: rejected initial revision and harness audit.
- `outputs/task-skill-comparison-v2/`: final paired raw results, `audited-summary.json`, `summary.csv`, live jobs and independent workbook audit.

Historical stopped benchmarks and held-out evidence were not resumed or modified by this work. The conclusion is limited: stage-specific procedures improved this development diagnostic, and deterministic presentation repaired a separately observed numerical-answer defect. Model capability, missing source facts and long inference latency remain limits.
