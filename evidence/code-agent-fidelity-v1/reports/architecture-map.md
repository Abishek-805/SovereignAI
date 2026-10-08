# Inspected execution map

Request -> router/coding_router.py classify_coding_request -> backend/service.py _lease -> router/model_broker.py select/acquire -> router/model_registry.py owned single-server lease.

Opt-in implementation: workflows/agent_kernel.py AgentLoop.run -> ModelAdapter.fit/turn -> backend/model.py agent_tool_turn -> native assistant tool call -> ToolExecutor.execute -> existing CodeSandbox -> JSON tool observation -> next call. Current limits: 32 turns, 64 tools, 12 sandbox runs, 4096 output tokens; service allows 840 seconds within the 900-second owning supervisor.

Context compaction: ModelAdapter.fit retains original system/request and a bounded latest validation summary, removing complete old exchanges. Exact transmitted payloads are not currently persisted; experiment instrumentation must capture them.

Repair: actual command/test failures retained, patch-only existing draft repair, aggregate failure/repair metrics. Native baseline lacks per-property regression rollback and can generate oversized replacement spans. Preserve this as a baseline finding; do not quietly fix baseline.

Authority: router/tool_registry.py macro action registration is distinct from native tool schema projection in workflows/agent_kernel.py. Reuse both as they exist. Do not introduce another authoritative registry.

Validation: ValidationEngine uses immutable supplied suites or contract checks; no-oracle framework probes are only runtime/HTTP evidence. Model-authored tests remain supplemental.

Publication: CodingWorkspace._stage_changes stores changed bytes and expected revisions outside canonical files. CodingWorkspace.accept requires completed/staged Docker evidence, rechecks paths, revisions and staged hashes, then journaled publish. discard never publishes. Models never invoke accept.

Supervisor: backend/task_supervisor.py shared ContextVar owner handles aggregate counters, cancellation, deadlines and terminal state. Existing CodingWorkspace storage and checkpoints own task state; experiments add evidence logs only.

Legacy workflow: router/code_agent.py delegates admitted actions through the existing registry, with at most three attempts and repeated-error fingerprints. Existing historical evaluations in experiments/comparison_* are not reused or modified.

Production: native flag defaults to zero. No production file edits, registration changes, migration or default changes are authorized for this experiment.
