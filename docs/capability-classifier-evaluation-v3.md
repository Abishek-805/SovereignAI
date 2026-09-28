# CPU capability classifier evaluation v3

The v3 CPU classifiers were evaluated on an independently authored holdout. **No candidate passed the frozen release gates, and no candidate was promoted.** The production-facing conservative classifier still abstains. Scores are advisory, uncalibrated model scores rather than probabilities, and classifier output never authorizes mutation.

## Taxonomy and implementation

`router/capability_classifier.py` defines a registry of five first-stage families: GENERAL, EVIDENCE, ACTION, VISION and CALCULATION. A second learned stage distinguishes members of the selected family:

| Family | Task labels | Fine intent descriptions |
|---|---|---|
| GENERAL | answer, clarify | general knowledge, conversation, clarification |
| EVIDENCE | search_documents, create_report | retrieval, document analysis, report generation |
| ACTION | edit_code, inspect_code, application_tools | code generation/edit/debug, code read, application Agent operations |
| VISION | vision | image analysis |
| CALCULATION | calculate | deterministic calculation |

The learned classifier does not separately predict every fine intent listed above. These descriptions map existing workflow labels to the capability registry. Evidence permission, model selection and tool execution remain separate decisions. Availability markers describe connected metadata; the evaluator never reads user documents, invokes tools or runs a generative model.

Three candidates use learned L2-regularized multiclass ridge coefficients over word, character, or combined TF-IDF features. The fourth uses the installed BGE CPU encoder and maximum labeled-prototype similarity. Each hierarchical candidate learns a family decision and a task decision. Both family and task scores must pass frozen score and margin thresholds.

## Dataset independence and freeze

Development contains **362 training examples and 46 calibration examples**. Previous v2 holdout and safety examples are explicitly recycled as development-only data in v3; they are not presented as unseen v3 evidence. New training augmentation is engineer-authored, including template variants.

The classifier agent authored development and froze every candidate's hyperparameters and thresholds before reading `benchmarks/router-heldout-v3.json`. The root agent authored the fresh holdout without reading v3 development. This is separate-agent authoring, **not independent human review**, external adjudication, or a representative production sample. Both authors belong to the same engineering session.

The fresh file actually contains **93 task cases and 24 safety cases**. An earlier progress description called it 94 tasks; the file is the authority. Three exact normalized development overlaps were detected before scoring and excluded transparently without changing the original dataset:

- `heldout-v3-3`: “What should I call you?”
- `heldout-v3-87`: “Update this.”
- `heldout-v3-92`: “Make it better.”

Metrics therefore cover **90 heldout tasks and 24 safety probes**. Reports record excluded IDs and texts, dataset hashes, module hashes and original policy-freeze timestamps. No training examples, hyperparameters or thresholds were revised after inspecting this holdout.

## Frozen release gates

The v3 development artifact declared these gates before evaluation:

- Overall heldout top-label accuracy: at least **90%**.
- Accepted heldout accuracy: **100%**.
- Accepted heldout coverage: at least **25% of all scored heldout tasks**.
- Accepted safety accuracy, when any safety decisions are accepted: **100%**.
- Zero unsafe mutation acceptances, general-question tool acceptances, ambiguous mutation acceptances and false retrieval acceptances, in both task and safety splits.
- No classifier mutation authority. Agent code writes and complex application operations are deferred even when the candidate label is confident.

The predeclared read-only whitelist is answer, calculate, clarify, vision, search_documents, inspect_code and edit_code **only in Chat mode**. Chat code is text output; it grants no project write permission. Candidate decisions outside this whitelist are excluded from accepted production-route coverage. Independent human review is not declared complete or required by the v3 synthetic-evaluation gate; any release still requires root's integration validation.

Calibration selected the highest coverage with zero accepted calibration mistakes, breaking ties toward stricter thresholds:

| Candidate | Minimum score | Minimum margin | Accepted calibration cases |
|---|---:|---:|---:|
| Word | 0.40 | 0.50 | 20/46 |
| Character | 0.60 | 0.50 | 10/46 |
| Hybrid | 0.40 | 0.50 | 16/46 |
| BGE | 0.85 | 0.04 | 13/46 |

The family stage uses the same frozen score and margin cutoffs as the task stage. These cutoffs are not calibrated confidence percentages.

## Measured comparison

Every method ran in a fresh process with one BLAS thread. BGE used the existing CPU ONNX encoder with two threads. Five prediction repetitions per request yielded a per-request median; the table reports the median of those request medians. No p95 or end-to-end generation latency is inferred.

| Candidate | Heldout top-label accuracy | Macro-F1 | Accepted task cases | Accepted accuracy | Median prediction | Setup | Sampled RSS increase |
|---|---:|---:|---:|---:|---:|---:|---:|
| Word TF-IDF | 76.67% | 0.7995 | 20/90 (22.22%) | 100% | 0.122 ms | 68.65 ms | 1.63 MiB |
| Character TF-IDF | 72.22% | 0.7240 | 7/90 (7.78%) | 100% | 0.932 ms | 455.30 ms | 5.52 MiB |
| Hybrid TF-IDF | 75.56% | 0.7604 | 18/90 (20.00%) | 100% | 1.077 ms | 595.05 ms | 5.71 MiB |
| BGE prototypes | 75.56% | 0.7387 | 12/90 (13.33%) | 100% | 20.297 ms | 5243.59 ms | 166.11 MiB |

RSS values are process snapshots around setup, not peaks or an exclusively attributable steady-state model footprint. They do not measure GPU VRAM. BGE setup includes loading the embedding runtime and encoding training prototypes.

All candidates failed **heldout accuracy** and **accepted coverage** gates. All accepted task and safety decisions were correct on this sample. Word accepted two safety probes, character zero, hybrid one, and BGE four; these small accepted counts do not establish broad safety generalization.

Word was fastest and had the highest aggregate accuracy on this dataset. That does not establish optimal routing or justify promotion. Full confusion matrices, per-class recall, individual predictions, repeated timing samples and failure lists are in the JSON results; CSV provides replay rows.

## Failure analysis and nonpromotion

The principal errors involved code generation versus ordinary conversation/code reading, compound execution versus code editing, and ambiguous mutation targets. Word achieved 100% heldout recall for answer, retrieval, grounded report and vision, but only 38.89% for edit_code. Its overall result therefore does not support universal capability routing. Low-confidence wrong labels were deferred; abstention preserved safety at the expense of coverage.

No threshold was relaxed to make these results look successful. `ReleasedCpuClassifier` rejects `release_ready:false` manifests, a changed development-data hash, and a changed classifier-module hash. All emitted v3 manifests are disabled. A post-evaluation module-hash validation guard intentionally makes an old manifest invalid when classifier behavior changes; evaluation hashes are preserved rather than rewritten to claim a fresh benchmark.

The wrapper is available for future validated artifacts through `predict(text, context).to_dict()`. It exposes a predicted workflow, accepted/deferred decision, classifier timings and hierarchy metadata while always setting `mutation_authorized:false`. Basic learned CPU routing remains an unresolved release requirement until a new, separately frozen development/evaluation cycle passes the gates and integration tests.

## Artifacts and reproduction

- Development: `benchmarks/router-development-v3.json`.
- Independent holdout: `benchmarks/router-heldout-v3.json`.
- Frozen policies: `benchmarks/router-classifier-freeze-{word,character,hybrid,bge}-v3.json`.
- Aggregate results: `benchmarks/router-classifier-v3-results.json` and `.csv`.
- Per-method results: `benchmarks/router-classifier-{method}-v3-results.json`.
- Disabled replay manifests: `benchmarks/router-classifier-{word,character,hybrid}-v3-artifact.json`.
- Evaluator: `benchmarks/evaluate-capability-classifiers.py --version v3`.

Replaying the evaluator measures CPU classification only. It does not prove evidence-answer correctness, coding success, model quality, resource admission or runtime lifecycle behavior. Prior v2 reports are retained unchanged. Regression tests cover hierarchy gates, absent mutation authority, failed-manifest rejection and module-hash invalidation.
