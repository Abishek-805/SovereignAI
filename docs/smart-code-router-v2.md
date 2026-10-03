# Smart Router V2: implementation and measurement record

Status: implementation regression and final follow-up review passed; live V2
comparison has not yet run. This document does not claim better task quality.

## Architecture and limits

The existing software classifier selects the task type and bounded workflow.
The existing broker then selects an eligible worker. Capabilities, modality,
context size, licensing, availability and resource admission remain hard gates.
The current one-heavy-model lease remains the only runtime owner. No model was
downloaded and no new production supervisor was introduced.

Ordinary edits, implementation and repairs use the installed coding worker.
Complex architecture requests use a bounded reasoning plan persisted into task
state before releasing that worker and acquiring the coding worker. Mechanical
multi-file renames remain coding work. Active or explicitly referenced files
take precedence within existing bounded context limits. Continuations recover
only a unique observed task with the same workspace and target.

The broker retains an eligible warm worker when measured total latency plus
switch latency does not justify a change. Unknown costs prefer the eligible
resident within the required role. Warm residency cannot override role or
resource constraints. With one installed worker in each role, cross-role
handoffs remain unavoidable. Unknown cost is not evidence of a speedup.

`router/model_history.py` stores bounded context-specific outcome aggregates,
not prompts or code. Counts include actual container execution and independent
supplied goal checks; generated or modified tests cannot establish history
success. Terminal text, valid JSON, and model completion are insufficient.
Wilson intervals, sample counts and coverage are exposed. A conservative
minimum of 20 samples per compared worker and non-overlapping intervals is a
policy requirement, not an empirically calibrated optimum. History cannot
prove adequacy of supplied tests or universal semantic correctness.

Generated-candidate repair preserves the original request, previous candidate,
actual bounded validation error and observed task state. The existing loop
allows three total generation attempts (at most two repairs), stops repeated
observed failures, and checks cancellation and workspace revisions. Traceback
locations and diagnostic hashes do not turn an unchanged error into a new
failure. Unavailable Docker does not count as a model failure or trigger host
execution. Staging, validated completion, review and Accept remain distinct.

## Frozen comparison method

The V2 development set contains 100 tasks across seven categories and 35
computational contracts. Tasks sharing contracts are not independent samples.
The new 24-case heldout set covers debugging, implementation and refactoring.
Its content is withheld from tuning. Fixture authorship limitations and image
asset limitations are recorded in the fixture README and provenance.

The serial harness compares A pinned general, B pinned reasoning, C pinned
coding, D the prior fixed routing/broker policy, and E V2. D loads the broker
from commit `9b9a899` inside common current workflows; it is not a historical
application binary or the former universal E strategy. All arms share current
tools, budgets, sandbox and independent validation. Histories are frozen empty
for this comparison to avoid ordered oracle-driven learning. Consequently the
comparison cannot establish adaptive-history gains.

Switch observations record actual model identities, stage, reason, measured
load time and task outcome. Effects remain UNKNOWN without equivalent paired
counterfactual evidence. Sampled process RSS and device VRAM are observations,
not guarantees for every instant. Executable checks do not replace semantic
review of explanations, architecture or visual fidelity.

## Verification so far

- Backend: 1,021 passed, 7 skipped after final follow-up repair.
- Frontend: 728 tests passed in 61 files; Svelte diagnostics zero errors/warnings.
- Frontend production build passed.
- Fresh actual Docker verification: 18 of 18 isolation checks passed.
- Live V2 task quality, generated-candidate automatic repair demonstrations,
  switching benefit and both heldout results: NOT VERIFIED yet.

The final A–W outcome report will be completed from preserved live evidence.
No improvement in model weights, perfect task understanding or superior
heldout quality is claimed by these implementation changes alone.
