# SovereignAI Phase A: existing implementation audit

Read-only production audit against commit `89fb7fe`. No model, Docker, production change, or held-out dataset access was performed for this audit. This document identifies consolidation candidates; it does not establish that another framework improves task accuracy.

## Existing ownership

| Responsibility | Current owner and evidence | Keep / simplify |
|---|---|---|
| Public request entry and workflow dispatch | `backend/service.py:447` ask, `:852` Code, `:1154` automatic Agent, `:1348` legacy Agent | Keep public interfaces; converge internal dispatch incrementally. |
| Cheap coding classification | `router/coding_router.py:34`, invoked by `backend/service.py:191` | Already separate from model selection; keep. |
| Eligible worker selection | `router/model_broker.py:15`, `router/model_selection.py:62` | Keep capability, role, context and resource gates. |
| Runtime ownership and single-model admission | `backend/service.py:221`, `router/model_registry.py`, `router/resource_admission.py:77` | Keep actual runtime identity and admission; replacing this with a generic agent loop is unnecessary. |
| Global task budget and observed operational state | `backend/task_supervisor.py:70`, decorator `:219` | Candidate authoritative outer task envelope. Nested decorated calls reuse it rather than allocating another supervisor. |
| Legacy agent step state | `router/orchestrator.py:35`, `:88`, called by `backend/service.py:1397` | Adapt state/events into the outer envelope before retiring any duplicate state. |
| Workflow persistence | `router/task_ledger.py:38`, coding result persistence `workflows/coding_workspace.py:854` | Preserve task IDs, artifacts and publication records; distinguish task envelope from workflow artifact record. |
| Completion observation | `router/task_completion.py:8`, used by `backend/task_supervisor.py:279` | Keep as an observation of executor evidence; never replace with an LLM done verdict. |
| Tool schema and execution | `router/tool_registry.py:66`, `:87`; application operations `backend/application_tools.py:207` | Keep contracts and explicit authorization before mutation. |
| Source staging and publication | `workflows/coding_workspace.py:500`, `:549`, `:601`, publication transaction `:143` | Keep acceptance, revision, validation and recovery gates. |
| Document context | `rag/context.py:23`, service ask/table-query paths | Keep retrieval as a bounded data source; generic agent memory must not substitute for complete table execution. |

## Real call paths and avoidable work

1. Direct Code mutations can skip generic intent planning (`backend/service.py:925`). Simple explanation selects a bounded explanation method after reading prioritized excerpts (`:939–951`). These existing fast paths should survive a refactor.
2. Complex Code tasks call `plan_code_strategy` (`:915`), persist `PLAN_CREATED`, then select Coder. The workflow can still call `plan_workspace_edit` (`workflows/coding_workspace.py:950`) and generate each file (`:1050`). The first plan is strategy prose, the second is an executable file-operation plan: they are different contracts, not automatically redundant. A structured strategy containing validated file operations could allow reuse, but requires schema and authorization checks before removing the second call.
3. Automatic Agent first obtains `_request_plan` (`backend/service.py:1198`). An application-tools path can then plan application operations, followed by Code workspace planning and generation. Measure actual stages and calls before removing a stage; the selected workspace and complete original request must reach the coding executor.
4. `LocalModel.complete_code` invokes `_planned_completion` (`backend/model.py:726`). Semantic review adds an actual completion request (`:286`), and rejected candidates can trigger another generation (`:305`). Thus one source-generation method invocation is not necessarily one LLM call. The review is the same selected worker's assessment, not independent runtime proof.
5. `CodingWorkspace.run_project` checks deterministic literal-edit/delete plans before model workspace planning (`:947–950`). Preserve those narrowly scoped operations; avoid duplicating them in a second framework.
6. `ApplicationTools.execute` already collapses multiple generated `file_edit` operations into one project workflow (`backend/application_tools.py:230`). This prevents full-project regeneration once per planned file. A replacement loop must preserve this behavior.

## Retry ownership and state duplication

There are two concrete source-repair implementations:

- Project path: service `run_coding_project_task`, three total candidate attempts at `backend/service.py:969`. Every retry calls `run_project` again (`:980`), so it can repeat workspace planning and generation for all planned files. Feedback includes the original request, selected workspace/target, prior candidate, actual error and observed checks (`:1003–1018`). It stops on unavailable validation, missing feedback, repeated error, budget, cancellation or revision conflict.
- Legacy single-file path: `CodingWorkspace.run`, three total attempts at `workflows/coding_workspace.py:1196`. It optionally executes the failing baseline, then regenerates only the selected source and validates each candidate. Supplied tests cannot be the editable target (`:1146`). It has its own repeated-error and attempt stop logic (`:1252–1259`).

These are separate entry paths, not evidence of an automatic nine-attempt nested repair loop. `Orchestrator.run_step` increments a repair counter and transitions state on a retryable failure (`router/orchestrator.py:123`), but does not itself rerun the function. Its current legacy service caller sets `retryable=False` (`backend/service.py:1398`). Calling that state transition a working automatic repair agent would be inaccurate.

There is additional, distinct nesting inside the project path: each generated file can have three source-shape validation attempts (`workflows/coding_workspace.py:1048–1064`), and each `complete_code` can contain semantic-review regeneration. The outer global model-call budget bounds actual requests (`backend/task_supervisor.py:55`), but the user-visible repair count does not describe all these generation calls. Consolidating budgets and trace labels is therefore useful even though the two coding executors are not nested inside each other.

The outer supervisor, orchestrator state and workflow ledger serve overlapping tracking purposes but different persistence contracts. Consolidation should first define one task envelope and append workflow records by ID. Do not delete the transaction or review records to make the number of state classes smaller.

## Context and correctness limits

- Project planning summaries use a shared 12,000-character budget and 900 characters per source (`workflows/coding_workspace.py:931–939`). Source generation uses another bounded context assembly (`:1019`). Explanation excerpts use 10,000 characters, 5,000 per file and eight files (`backend/service.py:936–950`). These are separate context policies; a shared context builder could record complete/omitted/truncated status consistently without increasing the model's actual capacity.
- Outer follow-up linking requires one observed prior goal and matching workspace/document scope (`backend/task_supervisor.py:246–265`). Code continuation additionally matches target and preserves the resolved original request (`backend/service.py:860–878`). A generic persistent memory replacement must not inherit another chat's workspace or convert untrusted text into tool authorization.
- Syntax checks do not prove requested behavior. Project history records independent-goal-check provenance only when unchanged supplied tests match the planned test files (`workflows/coding_workspace.py:1095–1100`). Generated tests can provide operational feedback but must not become independent success evidence.
- `observe_completion` distinguishes failure, review, missing input and observed completion. Staged edits remain awaiting review. Even an observed executor contract is expressly not universal semantic correctness (`router/task_completion.py`).
- Retrieval relevance and source completeness are different properties. `rag/context.py` uses lexical cues for optional passage retrieval; table aggregates require complete selected populations and executor semantics. Replacing retrieval with an unconstrained model conversation would not fix missing rows or wrong numerator rules.

## Conservative migration candidates

| Order | Candidate | Observable benefit / acceptance gate | Risk |
|---|---|---|---|
| 1 | Common read-only task/event view over existing IDs | One trace explains intent, worker, candidate, validation and review state; zero runtime behavior changes | Accidental merging of staged and published states. |
| 2 | One bounded context builder used by explanations and coding | Explicit included/omitted/truncated metadata; same authority and byte budgets; regression tests preserve active-file priority | Different tasks need different source limits; blanket concatenation harms context. |
| 3 | Shared repair policy/feedback serializer with existing executors | Same three-attempt maximum and stop reasons on both coding entry paths; actual failure-to-recovery tests | Changing candidate replay or trusted-test provenance. |
| 4 | Reuse validated operation plans during project repair when still applicable | Fewer measured planning calls without changing original scope or revision guards | Previous plan may itself be wrong; must allow bounded replan based on concrete evidence. |
| 5 | Adapt legacy orchestrator into the outer task envelope | Fewer competing state transitions with old API/results retained | Existing clients and artifact/task histories depend on IDs and state labels. |
| 6 | Selective semantic-review policy, experimentally compared | Lower actual call/latency cost with no increase in semantic failures or unsafe operations | Same-worker review can reject valid intermediates, but removing all reviews can admit wrong intent. No benefit established yet. |

A small external agent framework could supply a readable loop or connector abstractions. Its adoption should be a behind-the-interface experiment after these ownership boundaries are explicit, with identical models, input context, tools, budgets and oracles. A second runtime manager, separate agent memory or automatic publication loop would duplicate current responsibilities and increase migration risk.

## Evidence currently available

The local development-only progress analysis (`benchmarks/smart-code-router-v2-analysis-progress.json`, inspected during this audit) is marked RUNNING. At inspection it contained 59 A-arm observations: 37 PASS, 5 PARTIAL, 17 FAIL, with one independently observed repair recovery among ten repair-observed rows. E had zero observations and there were no decisive E paired comparisons. This partial, unequal coverage cannot establish V2 improvement, final failure rates or switch benefit. File contents can advance while the live suite runs; the final report must use the frozen final output and its hash.

Switch effects in that progress report are UNKNOWN because there is no equivalent randomized same-state switch/no-switch counterfactual. Historical/default call counts or a model's preference do not establish a beneficial switch.

Relevant regression coverage exists in `tests/test_task_supervisor.py`, `test_task_completion.py`, `test_coding_supervisor.py`, `test_v2_code_repair.py`, `test_model_broker.py`, `test_model_history.py`, `test_application_tools.py`, and `test_v2_benchmark.py`. This audit did not run them or claim their current pass status; the primary agent owns the frozen live suite and verification record.

## Recommendation

Keep the existing runtime, broker, sandbox and publication system. First unify observation and bounded repair contracts behind existing APIs, then test whether a smaller loop actually reduces duplicate calls and improves independently validated outcomes. Accuracy gains remain a measurement question. No production rewrite or framework adoption is justified by this source audit alone.
