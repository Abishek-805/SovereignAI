# Smart Code Router implementation plan

Goal: implement the supplied focused Code Assist router design using the existing broker, supervisor, registry, sandbox and review gates. The controlling specification is the user's pasted master request dated 2026-10-02.

Architecture: an advisory software classifier produces coding task/context features and worker preferences. Existing admission and explicit tool authorization remain authoritative. Clear coding work stays with Coder; simple explanations use the lightweight worker; complex work uses a bounded reasoning handoff. No new model or parallel GPU runtime.

Stack: Python backend, llama.cpp registry, Docker sandbox, existing Svelte frontend, pytest and resumable JSON benchmark harness.

## Execution checklist

- [x] Audit service call paths, normalization/classification, broker measurements and independent benchmark interfaces.
- [x] Freeze independent coding fixtures before implementation tuning: at least 100 main cases plus separate heldout cases, trusted assertions and expected routes.
- [x] Add failing tests for sandbox-unavailable stop and repair affinity; implement minimal service corrections in backend/service.py.
- [x] Add failing tests for coding task/context classification and protected normalization in router/request_normalization.py and a focused coding router module.
- [x] Implement advisory decisions and integrate service entry points without granting write authority from classification.
- [x] Record original/normalized request, task complexity/context, candidates, selection, observed timing, repair and validation outcomes through router/telemetry.py and existing supervisor events.
- [x] Add task-specific measured evidence support to router/model_broker.py without inventing accuracy or cost values.
- [x] Verify direct Coder, lightweight explanation, bounded reasoning-to-Coder and vision handoff paths; preserve review, cancellation, stale draft and publication tests.
- [x] Build resumable five-arm benchmark using existing resource observation and provenance utilities. Separate staged validation from published state and unsupported modality from failures.
- [x] Run actual Docker failing-code → Coder repair → trusted tests pass demo with no implicit publication.
- [x] Run all five strategies on frozen main fixtures, analyze failures, make only evidenced general fixes, then run untouched heldout fixtures.
- [x] Run backend/frontend verification and record live single-worker/resource observations with their sampling limitations.
- [x] Produce measured PASS/PARTIAL/FAIL/BLOCKED/NOT VERIFIED/UNKNOWN report; freeze and commit reviewed implementation and evidence.

Constraints: do not expand document/office workflows, add task-specific cohort conditions, weaken Docker validation, reset Docker data, or claim model weight training/general perfect accuracy. Stop code generation on unavailable validation. Existing role preferences are policy until comparative evidence exists.

Plan review: all master phases are represented. Benchmark main and heldout provenance must remain distinct; agent-authored fixtures must be frozen before production tuning. Actual model benchmark work is serialized by the root agent.

Completion qualification: live paths and comparisons were executed, not universally successful. Vision implementation and automatic generated-candidate repair remain PARTIAL in the measured report.
