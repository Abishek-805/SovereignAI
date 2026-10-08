# Pinned source comparison and predeclared experiment

Production stays unchanged. This is a new evaluation, not a continuation of the frozen model bake-off.

| Reference | Inspected execution source | Observed mechanism | SovereignAI equivalent | Classification |
|---|---|---|---|---|
| Nanobot, 42f06ab1 | nanobot/agent/runner.py, loop.py, tools/registry.py | Native assistant calls, registered tools, paired observations, before/after action checkpoints, bounded iterations | AgentLoop, ToolExecutor, CheckpointStore | A ADOPT existing equivalent; B ADAPT checkpoint-before-dispatch |
| Hermes, 17d4518c | agent/conversation_loop.py, tool_executor.py, iteration_budget.py | Exact argument parsing without coercion, native tool-result pairing, bounded malformed/truncated-call handling, sequential/concurrent dispatch | Native schemas, observations, shared supervisor | A ADOPT existing exact parsing; B ADAPT bounded format-error observation recovery |
| mini-SWE-agent, 04d809ce | src/minisweagent/agents/default.py and environments/docker.py | query/execute/observe, explicit exit roles, step/wall-time budgets, trajectory save in finally, bounded format errors | Existing native loop and supervisor | A ADOPT exact trajectory saving; C INSPIRE ONLY alternate text-action transport |
| All | Context and provider source listed in upstream manifests | Model-based summaries, provider fallback, memory, delegation and multi-channel integrations | Original request plus deterministic bounded context | D REJECT for this comparison |

Full URLs, source bytes and SHA-256 values are in reports/upstream/*/manifest.json and execution-sources-v2.json. Sources are inert .txt archives, not installed or imported. Claims describe the inspected revisions, not every release.

## A/B mechanism decisions

- **Exact trajectories (A)**: reuse LocalModel and capture the actual request after skill injection, response (including truncated output), tool arguments/results, source hashes, token counts and timing. Current public logs omit exact full handoff context. Cost: an experiment-only transport observer. Risk: evidence size/private source; stays local in this evidence directory. Expected benefit: attribution, not increased PASS. Test: request/response hash round-trip and complete failed-call capture.
- **Nanobot before-dispatch checkpoint (B)**: persist a pending action before execution, then the existing completed observation. Current native checkpoints occur after action execution. Cost: a small ToolExecutor wrapper. Risk: no semantic difference during normal execution; do not invent a fidelity benefit. Test: interrupted/pending action provenance and paired outcomes. The core loop itself is already equivalent.
- **Hermes bounded format-error recovery (B)**: return the exact provider format error to the same worker, within the existing turn/time budget, with a two-consecutive-error ceiling. Current native baseline stops immediately on a truncated native response. Cost: one ModelAdapter wrapper. Risk: extra latency and repeated unproductive generation; no extra steps, output tokens, retries beyond the existing overall budget, model switches or auxiliary calls. Test: valid tool selection after an error, total cost, and no partial-tool execution.
- **Independent repair rollback (B, SovereignAI requirement)**: B/C preserve candidate diffs at every action; on independently measured loss of previously passing properties, restore the previous revision's overlay. Native A stays unchanged and its lack of rollback is recorded. Cost: bounded changed-file overlay copies, not disk project snapshots. Risk: blocking a repair with an inadequate oracle. Test: oracle controls, property-level regression trace and unchanged canonical files.
- **Strict argument identity (A)**: already present; no new implementation. No guessed/coerced tool or repaired arbitrary JSON. Test malformed arguments never execute.
- **Sequential tools (A)**: retain the existing single-tool execution order. Upstream concurrent dispatch is D REJECT here: it confounds ordering and is unnecessary for these tasks.

No new router, supervisor, registry implementation, task database, model, cloud provider, messaging integration, memory layer or delegation is introduced. Existing classes are reused inside the isolated harness.

## Controlled arms

- `native_v1`: frozen native snapshot, unchanged runtime semantics, observer-only instrumentation.
- `nanobot_minimal`: same native core, before-dispatch evidence plus property-regression rollback. This is an adaptation, not a Nanobot installation or a claim to reproduce its full agent.
- `hermes_minimal`: same native core and rollback, with bounded provider-format-error recovery. This is a narrow adapted policy, not the full Hermes architecture.

Initial system, injected skills, task request, workspace ID, fixtures, tool schemas, model, runtime profile, context fitting, Docker image/policy, validators and limits are identical. Subsequent observations can differ only because the runner executes/stops/rolls back differently. There is no model-specific prompt tuning. All positive/negative oracle controls are completed before freezing the task suite and before model outcomes are inspected.

Common limits: native default 600 seconds, 32 turns, 64 tools, 12 Docker executions, 4096 output tokens, temperature zero, 16,384 context, unchanged llama.cpp b11132 and fit/KV profile. The existing owning supervisor supplies cancellation and accounting. B/C stop after three independently unsuccessful repair validations; regressions roll back. Baseline A retains its current stopping behavior. All arms use the same supplied tests and execution costs.

15 task categories are predeclared. T1–T11 are coding outcomes; T12–T15 are lifecycle/publication controls and are reported separately, not used to inflate coding success. One deterministic trial per arm/task gives descriptive paired evidence, not proof of global superiority. A migration requires reproduced category gains and all safety gates; small/no gains mean no migration. No model switching is permitted in the fixed-worker comparison.

After the runner stage, run the separately labeled model experiment on the fixed native scaffold (all parameters fixed except model), then analyze router decisions offline on these new records. Do not train or replace a router. Diagnose the attendance trajectory once from prior raw evidence and stage boundaries; do not repeatedly retry the UI request.
