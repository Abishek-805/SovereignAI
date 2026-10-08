# Product repair tracker

Goal: reliable request understanding, appropriate worker selection, grounded computation/answers, model-authored changes, real execution/repair, usable previews and honest completion status.

The user explicitly prioritized product repairs. The model comparison was stopped at 22 completed cells; raw results and the interrupted attempt are preserved in evidence/code-agent-fidelity-v1. Product fixes are now authorized. Historical project modifications predate this pass and have not been reset.

| Area | Current evidence | State / acceptance requirement |
|---|---|---|
| Structured numeric answers | Numeric-string comparison and nonfinite/boolean filter counterexamples reproduced | Isolated repair: six new checks and 21 compatibility checks pass; applied to production source; service restart pending |
| Comparison direction | Source comparison path reports maxima even when request includes `lowest` | Reproduced and fixed: report both extrema and avoid an unsupported overall ranking |
| Model action emission | Exact T10 stream/nonstream replay emits prose to limit with no raw tools | Runtime/template constraint mechanism remains to be controlled; not a client stream-loss fix |
| Coder native action fidelity | Current frozen arm has early failures; comparison incomplete | Do not infer macro-path quality or a universal model ranking from native-path failures |
| Request/history fidelity | Earlier calculator/search and attendance-entrypoint failures reported; multiple subsequent scoped patches exist | Fresh end-to-end independent requests and real follow-ups needed; no task-specific canned app |
| Routing | Capability selection exists, but full quality/latency benefit is unproven | Evaluate selected worker against actual operation format and validated task outcome |
| Retrieval scope and synthesis | Deterministic query executor and verified presentation exist | Check complete entity/field coverage, missing data, citations and actual comparison conclusions |
| Preview | Warm Docker session adapter now exists | Docker CRUD, HTTP 204, state persistence and entrypoint isolation passed; concurrency and Windows cache-path failures fixed; live API reload unverified |
| Jobs/UI state | In-process jobs, polling/reconnection and queued chat exist | Trace backend truth to API to UI under cancellation, navigation, disconnection and restart |
| Dependency/runtime readiness | Pinned Docker image reverified 18/18; stale model PID was safely archived | Test startup/readiness failures without terminating unrelated processes or mislabeling BLOCKED as model failure |
| Publication | Explicit Accept, revision checks, journal and Docker gate exist | Preserve security; rerun applicable conflict/nonpublication gates after changes |

## Product acceptance criteria

For an action request, success requires the requested artifact or behavior, actual tool execution, independent validation, and accurate user-visible state. File mutations require staging and explicit acceptance. A working API response, model claim, correct JSON or screenshot alone is insufficient.

For a data question, success requires source-bound values, complete requested coverage or explicit missing items, appropriate deterministic computation and a direct supported answer. Retrieved snippets alone are insufficient. Source instructions never override the user's request.

For routing, record the actual model/process and task-level selection. Maintain one heavy model at a time and do not hide switches or unknown resource measurements.

Current overall status: INCOMPLETE. The first isolated repair has been verified; no claim that all reported issues are solved.

Latest repair evidence: [8 October report](PRODUCT-REPAIR-RESULTS-2026-10-08.md). Current source is repaired in the listed areas; overall product acceptance remains INCOMPLETE.
