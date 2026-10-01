# Sequential task supervision

The application uses the resident local model sequentially as worker and reviewer. It does not start another heavyweight model or train model weights.

Semantic planning runs a proposal, evidence review and repair cycle, with at most four reviewed candidates. The review checks the complete current request, follow-up references, selected workspace and requested deliverables. Task classification and application planning receive the actual conversation separately from demonstrations. Essential missing information, repeated identical failures, cancellation or the attempt limit stop the cycle without claiming completion.

Routing decisions interpret the request and select a workflow; they are not certified as completed implementations. Supervision reviews the downstream executable plans and generated results instead. Application-plan reviews receive a short workflow contract and actual task metadata rather than the entire demonstration transcript. Rejected candidates remain reference data during repair, alongside the original task and concrete feedback. Repair sampling uses a small amount of variation, followed by another review.

Coding projects additionally retry actual failed Docker validation up to three times. Each retry receives the preceding candidate and bounded execution error while retaining the original instruction and workspace. Successful changes remain staged for review; the supervisor never accepts or publishes them. Missing Docker is reported as unavailable validation and does not trigger blind retries. A passing syntax check is not proof that a camera, GUI or external dependency works on the host.

Percentage comparisons use an explicit grouping contract: each requested cohort receives its own numerator and denominator over the complete source records. The source binder verifies identity fields and the executor computes values. This supports arbitrary source-bound group labels rather than rules keyed to particular prompt phrases.

Population names are resolved separately from source fields. A source-field pass receives only real candidate columns, observed matching record counts and short matching examples. Its column choice is constrained to those candidates, then validated by the compiler. Incidental matches in an email field cannot silently substitute for the intended identifier field.

These checks improve reliability but do not guarantee correct understanding of every task. Model reviewers can share the worker's mistakes. Actual source validation, runtime checks and transparent blockers remain necessary.

Validation on 2026-10-01: the full backend suite passed (704 tests, 7 skipped). A live ADR/ALR comparison returned all fourteen assessment measurements with separate cohort denominators, matching an independent workbook calculation. The same live model produced an implementation operation for a functional folder request; this verifies planning, not execution of the generated camera or classification software.
