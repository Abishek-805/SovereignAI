# Smart Router V2 Implementation Plan

> For agentic workers: use executing-plans or subagent-driven-development with independent file ownership and review.

**Goal:** Improve economical worker selection and evidence-driven generated-candidate repair on existing local Code Assist.

**Architecture:** Keep software classification separate from broker selection; retain role/compatibility/resource gates and one-heavy lease. Add bounded outcome aggregates to the existing broker and task completion flow; hysteresis remains conservative when evidence is unknown. Reuse code staging, Docker checks and Accept.

**Tech Stack:** Python, existing llama.cpp registry, Docker, Svelte, pytest, serial benchmark harness.

**Spec:** User attachment `C:/Users/ashek/.codex/attachments/3f508e60-eeeb-45df-86d5-732d23642376/Pasted text.txt`.

## Constraints

No new production models or supervisor, UI redesign, unrelated feature expansion, oracle exposure, host execution fallback, implicit publication or two heavy workers. Preserve frozen V1 evidence and old heldout24. V2 development and heldout are independently authored and hashed before evaluation. Outcome unknown remains unknown. Three repairs maximum; repeated actual failure stops.

## Review focus

- Warm worker cannot bypass capabilities, context, resource or authorization gates.
- Unknown cost and small samples cannot establish superiority.
- Repeated errors with changing sandbox paths still stop; cancellation and unavailable Docker never become repair evidence.
- Relevant active file and previous candidate must survive follow-up/repair without unrelated writes.
- Completion, review and publication remain distinct; model claims cannot enter outcome success counts.

## Tasks

- [x] Trace selection, roles, repair and validation; verify installed identities and current engine.
- [x] Freeze new independent >=100 development and separate V2 heldout cases with actual image inputs and coverage limitations.
- [x] Add red tests for warm retention versus measured switching cost, incompatible resident rejection and unknown evidence; implement broker hysteresis without weighted scores.
- [x] Add persistent bounded context-specific outcome counts, measured latency and confidence/coverage; integrate only real task evidence, not generated text.
- [ ] Reproduce generated-candidate repair gaps with real execution; test bounded feedback, previous candidate/state, repeated failure stop and maximum three repairs.
- [x] Prioritize active/referenced bounded context and preserve follow-ups using existing task state.
- [x] Extend serial harness with V2 policy provenance, switching observations and separate failure taxonomy; preserve old outputs.
- [ ] Run required seven live cases and development five arms; freeze policy then evaluate old heldout once and independent V2 heldout.
- [ ] Run targeted/full backend, frontend tests/build, live model/Docker and resource observations.
- [ ] Produce A-W measured report, limitations and exact evidence; commit only reviewed verified changes.
