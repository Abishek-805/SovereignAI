# Sequential task supervision

The application uses the resident local model sequentially as worker and reviewer. It does not start another heavyweight model or train model weights.

Semantic planning runs a proposal, evidence review and repair cycle, with at most four reviewed candidates. The review checks the complete current request, follow-up references, selected workspace and requested deliverables. Task classification and application planning receive the actual conversation separately from demonstrations. Essential missing information, repeated identical failures, cancellation or the attempt limit stop the cycle without claiming completion.

Routing decisions interpret the request and select a workflow; they are not certified as completed implementations. Supervision reviews the downstream executable plans and generated results instead. Application-plan reviews receive a short workflow contract and actual task metadata rather than the entire demonstration transcript. Rejected candidates remain reference data during repair, alongside the original task and concrete feedback. Repair sampling uses a small amount of variation, followed by another review.

Coding projects additionally retry actual failed Docker validation up to three times. Each retry receives the preceding candidate and bounded execution error while retaining the original instruction and workspace. Successful changes remain staged for review; the supervisor never accepts or publishes them. Missing Docker is reported as unavailable validation and does not trigger blind retries. A passing syntax check is not proof that a camera, GUI or external dependency works on the host.

Percentage comparisons use an explicit grouping contract: each requested cohort receives its own numerator and denominator over the complete source records. The source binder verifies identity fields and the executor computes values. This supports arbitrary source-bound group labels rather than rules keyed to particular prompt phrases.

Population names are resolved separately from source fields. A source-field pass receives only real candidate columns, observed matching record counts and short matching examples. Its column choice is constrained to those candidates, then validated by the compiler. Incidental matches in an email field cannot silently substitute for the intended identifier field.

These checks improve reliability but do not guarantee correct understanding of every task. Model reviewers can share the worker's mistakes. Actual source validation, runtime checks and transparent blockers remain necessary.

Validation on 2026-10-01: the full backend suite passed (704 tests, 7 skipped). A live ADR/ALR comparison returned all fourteen assessment measurements with separate cohort denominators, matching an independent workbook calculation. The same live model produced an implementation operation for a functional folder request; this verifies planning, not execution of the generated camera or classification software.

## Universal observation and budgets

Public conversation, document, image, automatic-agent, calculation and coding entry points now share one logical supervision envelope. Nested workflows retain the outer request and selected scope. The envelope persists in `data/supervision` before execution, at model/tool checkpoints and at termination. It records actual model calls, tool calls and model changes without keeping another model resident. Repeated leases for the same model retain affinity and do not count as switches. These records support inspection; they do not automatically resume or replay mutations after a crash.

The default envelope permits 64 inference calls, 12 registered tool calls, four model selections/changes and 900 seconds. Configure `SOVEREIGN_SUPERVISOR_MODEL_CALLS`, `SOVEREIGN_SUPERVISOR_TOOL_CALLS`, `SOVEREIGN_SUPERVISOR_MODEL_SWITCHES` and `SOVEREIGN_SUPERVISOR_SECONDS` before starting the service. Cancellation and admission checkpoints run before each new inference/tool operation. Existing request and sandbox timeouts still apply; a supervisor deadline is not a separate thread that forcibly interrupts a write in progress.

`completion` is separate from the HTTP/job transport status. It distinguishes checked execution, awaiting review, missing information/evidence, failed checks, cancellation and unverified responses. Citation and numeric checks cannot prove semantic correctness. Syntax checks cannot prove runtime behavior. Staged changes are never reported as applied changes. Job polling still terminates when a response is ready, with a stage such as Ready for review or Needs information.

Document lookup can refine its search up to twice after insufficient evidence or citation failure. The original question, history and permitted document scope remain controlling. No new passages means no further answer generation; repeated evidence stops recovery. Complete-source table calculations and collection overviews retain their existing specialized execution paths. Mutation operations are not replayed by this recovery loop.

## Tiny-controller experiment

The supplied architecture discussion is a proposal, not evidence of model capability. A frozen, engineer-authored 42-case pilot tests routing, literal targets, follow-ups, next-step decisions, failed validation and false completion. It is not an independently held-out release benchmark. The evaluator only proposes actions; it executes none.

On 2026-10-01, an isolated CPU-only SmolLM2-360M-Instruct Q4_K_M run scored 0/42 exact decisions, 25/42 valid outputs and six unsafe valid proposals. The current server was actually Gemma 4 E2B, not Qwen despite its `sovereign-text` alias; it scored 1/42 exact decisions, 40/42 valid outputs and five unsafe valid proposals. Both used the same single-call zero-shot controller contract. These scores do not measure the existing multi-pass application supervisor or establish that every fine-tuned tiny controller fails. Neither candidate passed promotion. The experimental model remains outside production routing; its server was stopped before the current-model comparison. Full replies, model/runtime metadata, source revisions and integrity hashes are in the accompanying benchmark JSON files.

SmolLM2-360M's official configuration has 8,192 positions. Its model card attributes function calling specifically to the 1.7B variant; that is not a capability certification for 360M. Qwen2.5-0.5B-Instruct is another Apache-2.0 candidate with 32,768 positions, but was not downloaded or measured here. No fine-tuning or model-weight changes were performed.

Sources checked: [SmolLM2 model card](https://huggingface.co/HuggingFaceTB/SmolLM2-360M-Instruct), [SmolLM2 configuration](https://huggingface.co/HuggingFaceTB/SmolLM2-360M-Instruct/blob/main/config.json), [Qwen0.5B model card](https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct), [Qwen0.5B configuration](https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct/raw/main/config.json).

The design uses environmental feedback as in [ReAct](https://arxiv.org/abs/2210.03629). It also respects the limitation examined in [Large Language Models Cannot Self-Correct Reasoning Yet](https://arxiv.org/abs/2310.01798): intrinsic self-correction without external feedback is unreliable in the studied reasoning settings. Applying those findings to this laptop is an engineering inference, not a measured guarantee of general task completion.

Integration validation: 732 backend tests passed, seven skipped. After the final report/execution envelope additions, the affected API, report, maintenance, service and supervisor tests passed again (83 tests). A live `/ask` calculation returned 60 for `12 * 5`, retained the original document scope, recorded `calculation_evaluated: true`, and made zero model calls. Production uses the existing model selection; the experimental controller has no application authority.
