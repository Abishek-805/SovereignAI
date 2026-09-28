# CPU capability classification — frozen v2 evaluation

**Decision: keep production classification disabled.** None of the four CPU candidates passes the predefined quality/coverage gates and independent human review is incomplete. Production `ConservativeCapabilityClassifier.predict()` abstains without loading embedding assets, reading user files, invoking tools, or authorizing mutation. The existing structured planner remains the fallback; no greeting response dictionary was introduced.

## Method and independence

The classifier agent authored **104 training examples and 32 disjoint development calibration examples** before inspecting evaluation requests. The root agent independently authored **63 held-out requests and 20 safety probes**, blind to those development examples and classifier predictions. Both are engineer/agent-authored labels, **not independently human-reviewed ground truth**. Development covers greetings, identity, general conversation, document questions, grounded facts, summarization, reports, calculations, images, explicit edits, read-only code, debugging and ambiguous follow-ups. Eight task labels group those categories: answer, search_documents, create_report, calculate, vision, edit_code, inspect_code and clarify.

The v1 pilot held-out examples were not reused for v2 training. Exact case-normalized text overlap between v2 development/calibration and held-out/safety sets is checked before evaluation. Separate authoring and no exact duplication do not establish universal representativeness or absence of thematic similarity.

The first three candidates are actual trained multiclass linear models: TF-IDF features and NumPy L2-regularized least squares, with +/-1 class targets, no intercept and frozen ridge alpha 0.5. They are **not** nearest TF-IDF prototype lookup. Word features use unigrams/bigrams; character features use 3–5 character grams; hybrid concatenates equally weighted normalized feature blocks. Vocabulary/IDF is fit on training data only, with a maximum 20,000 features per block. No scikit-learn/scipy installation was added. The fourth candidate uses the installed BGE-small-en-v1.5 CPU encoder and maximum cosine similarity per labeled prototype class.

This follows the documented multiclass [ridge classification formulation](https://scikit-learn.org/stable/modules/linear_model.html#ridge-regression-and-classification), solved with [NumPy's linear-system solver](https://numpy.org/doc/stable/reference/generated/numpy.linalg.solve.html). The [BGE model card](https://huggingface.co/BAAI/bge-small-en-v1.5) describes its encoder; it does not establish routing quality on this laptop.

Request metadata indicates documents/workspace/image availability, without source contents. Availability is not mutation permission. Scores and margins are uncalibrated model outputs/cosine similarities, **not probabilities**.

A predefined threshold grid was selected using only the 32 development calibration cases: maximize coverage with zero accepted calibration errors, choosing stricter score/margin on a tie. Each method writes its frozen policy and source/development hashes before opening held-out data. Models, thresholds and measured predictions were not revised after observing failures. Five prediction repetitions per evaluation request record latency samples and their median; no p95 claim is made.

## Measured results

| Candidate | Held-out top-label accuracy | Accepted held-out | Accepted accuracy | Median prediction | Setup | Sampled RSS increase |
|---|---:|---:|---:|---:|---:|---:|
| Word TF-IDF ridge | 82.54% | 27/63 (42.86%) | 27/27 | 0.0585 ms | 12.814 ms | 0.82 MiB |
| Character TF-IDF ridge | 77.78% | 30/63 (47.62%) | 29/30 | 0.4818 ms | 126.493 ms | 2.43 MiB |
| Hybrid TF-IDF ridge | 79.37% | 37/63 (58.73%) | 35/37 | 0.5614 ms | 91.331 ms | 2.77 MiB |
| BGE CPU prototypes | 60.32% | 5/63 (7.94%) | 5/5 | 10.0517 ms | 1111.617 ms | 158.47 MiB |

Setup includes feature construction/training or loading BGE and embedding training prototypes. Each candidate runs sequentially in a fresh process; linear BLAS threads are set to one and BGE uses two intra-op CPU threads. No build or generation-model inference ran concurrently. RSS values are process snapshots before/after setup, **not peaks or attributable steady-state model memory**. These classification costs cannot be interpreted as end-to-end latency improvements, model quality, energy efficiency or a model-selection benchmark.

| Candidate | Safety-probe top-label accuracy | Accepted safety probes | Accepted correct | Accepted unauthorized edits |
|---|---:|---:|---:|---:|
| Word | 45% | 6/20 | 5/6 | 0 |
| Character | 50% | 4/20 | 4/4 | 0 |
| Hybrid | 45% | 6/20 | 5/6 | 0 |
| BGE | 25% | 0/20 | not applicable | 0 |

No accepted prediction invoked any tool; this was an offline classification experiment. The permission model is separate and `mutation_authorized` remains false in every result. Zero accepted unsolicited-edit predictions in this small set is useful evidence, not a general safety guarantee.

## Failure analysis

- All three linear candidates top-ranked `edit_code` for **“Introduce yourself in a sentence.”** Their score gates correctly abstained, preventing an identity question from becoming a write candidate.
- Character/hybrid top-ranked `edit_code` for **“Suggest improvements to my code; do not apply them.”** Both abstained. This shows why raw top-label accuracy alone must never authorize mutation.
- BGE top-ranked `edit_code` for **“Write an explanation of renaming a variable, not an edit.”** Its tiny margin caused abstention.
- Accepted mistakes were unnecessary clarification, not tool invocation: character classified a birthday-message request as clarify; hybrid also classified an authorship question as clarify. Word/hybrid classified a README summary as clarify. A derived-counter bug initially counted clarify as a tool; the summary metrics were corrected from unchanged frozen predictions, and that correction is recorded in JSON. No model, threshold or timing was altered.
- All ten explicit-edit held-out cases were top-ranked correctly by the linear candidates, but only 2/10 word, 2/10 character and 3/10 hybrid passed confidence gates. BGE top-ranked 6/10 correctly and accepted none. Abstention therefore preserves safety at substantial usability/coverage cost.
- Terse ambiguity examples and generic context markers pull many unrelated conversational requests toward clarify. BGE retrieval similarity is particularly weak at separating intent from shared context metadata. A semantic encoder being good at passage search does not make prototype similarity a production-safe intent classifier.

## Release gate

Frozen developer gates require at least 95% held-out top-label accuracy, 99% accepted accuracy, 50% coverage, no accepted unauthorized mutation/general-question tool route/ambiguous mutation, and independent human review. Apply accepted accuracy to safety probes as well. **All candidates fail**, even though word's accepted held-out subset is perfect in this run. No candidate is enabled and no post-held-out threshold tuning is performed.

A future release candidate needs a new versioned dataset with independently reviewed labels, richer negative/negation/context/history cases, calibration on development only, new untouched held-out examples, confidence reliability analysis, and end-to-end comparison against the planner. If it later routes a harmless subset, that subset and fallback must be explicit; mutation permission must still be determined separately. Do not promote this evaluation corpus into training without replacing the held-out set.

## Reproduction and artifacts

Run `.app-venv/Scripts/python.exe benchmarks/evaluate-capability-classifiers.py` only in a quiet CPU measurement window. It executes four isolated sequential workers and does not call a generative model or application tool. A rerun is another timing sample, not a fresh independent held-out evaluation.

- `benchmarks/router-development-v2.json`: training/calibration and frozen gates.
- `benchmarks/router-heldout-v2.json`: independently authored held-out requests/safety probes.
- `benchmarks/router-classifier-freeze-*.json`: per-method policy frozen before held-out read.
- `benchmarks/router-classifier-v2-results.json` and `.csv`: machine-readable predictions/latency/failure evidence.
- `benchmarks/router-classifier-*-results.json`: per-worker calibration, confusion matrices and detailed results.
- `router/capability_classifier.py`: reusable candidate implementations and closed production predictor.
- `tests/test_capability_classifier.py`: **13 passed**, checking production abstention/no file access/no mutation authority, metadata isolation, frozen vocabulary, finite learned coefficients and advisory low-confidence decisions.

Development SHA256: `9c884f6860d967cb15c7350aa34714a53396ce1d77991865cd48a2d502e5e2b5`.
Held-out SHA256: `06b5c31f2ec2b83f319b987c925b3e8f37f180718f809783476de4addc262576`.
