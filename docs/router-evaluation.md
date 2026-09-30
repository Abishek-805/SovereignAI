# Router evaluation and release status

**CPU-first promotion: FAIL.** The fresh `evaluate-capability-classifiers.py --version v3` run recorded in [release-classifier.log](../benchmarks/release-classifier.log) still fails heldout accuracy and accepted coverage for every candidate. Production continues to use the conservative abstaining classifier and bounded model-planner fallback. Refreshed artifacts and hashes do not change a failed release result.

## Frozen evaluation

The evaluator trains candidates on 362 development examples and selects thresholds on 46 calibration examples. The v3 heldout contains 93 task cases and 24 safety probes. Three exact normalized overlaps with development are transparently excluded, leaving 90 scored tasks and 24 safety probes. Prior v2 evaluation examples were recycled only as development data for v3. Authoring was separated between engineering agents, not independent human adjudication or representative production sampling.

Before heldout scoring, the policy requires at least 90% top-label accuracy, 100% accepted accuracy, at least 25% accepted task coverage, and zero unsafe mutation, general-question tool, ambiguous-mutation or false-retrieval acceptances. Accepted safety decisions must also be correct. The read-only acceptance whitelist excludes complex application actions and permits `edit_code` only in Chat mode; classifier predictions never grant mutation authority.

Thresholds and training were not relaxed after reading the holdout. A replay of this same heldout is reproducibility evidence, not an additional independent test split. Any future improvement needs a separately frozen development/evaluation cycle with unseen evaluation cases.

Source: [development and gates](../benchmarks/router-development-v3.json), [evaluator](../benchmarks/evaluate-capability-classifiers.py), [v3 methodology](capability-classifier-evaluation-v3.md).

## Fresh classifier results

| Candidate | Top-label accuracy | Accepted tasks | Accepted accuracy | Median prediction |
|---|---:|---:|---:|---:|
| Word TF-IDF ridge | 69/90 (76.67%) | 20/90 (22.22%) | 100% | 0.170 ms |
| Character TF-IDF ridge | 65/90 (72.22%) | 7/90 (7.78%) | 100% | 1.284 ms |
| Hybrid TF-IDF ridge | 68/90 (75.56%) | 18/90 (20.00%) | 100% | 1.527 ms |
| BGE prototypes | 68/90 (75.56%) | 12/90 (13.33%) | 100% | 42.877 ms |
| Release requirement | At least 81/90 | At least 23/90 | 100% | No latency gate |

All four fail `heldout_accuracy` and `accepted_coverage`. Accepted safety counts are respectively 2, 0, 1 and 4 of 24; this small accepted sample cannot establish broad safety generalization. The word candidate's low latency does not justify promotion with failed quality gates.

The fresh run's setup times are approximately 117 ms, 596 ms, 758 ms and 10,282 ms. Prediction timing uses five repetitions per request, then the median of request medians. It excludes generation, retrieval, tool execution and application transport. RSS deltas are setup snapshots, not model peak memory, GPU VRAM, or request-level resource ceilings.

Fresh data: [release log](../benchmarks/release-classifier.log), [aggregate JSON](../benchmarks/router-classifier-v3-results.json), [replay rows](../benchmarks/router-classifier-v3-results.csv). Word, character and hybrid replay manifests remain `release_ready:false`. The release wrapper rejects failed manifests and mismatched development/module hashes. No failed artifact is enabled by refreshing source hashes.

## Selector and end-to-end evidence boundaries

The selector's source implements compatibility/admission filtering and conditional measured-cost ranking. Default model metrics are incomplete, so the code does not establish a new optimizer, a validated quality floor, a speedup, or global optimality. Model-selector unit tests establish branch behavior; they do not supply real generator quality or switching measurements.

The [comparison harness](router-integration-comparison-harness.md) separates always-text, legacy fixed mapping and candidate selection while retaining admission guards. Legacy-adapter calls must be identified separately from selector trace stages. Available reports of live workflows should state their exact completed cases, validation and failures; this document does not infer new live outcomes from classifier-only evaluation.

There is no independently measured alternative-model oracle for each task. Missing oracle latency is unavailable, not zero. One pass, CPU microbenchmarks or synthetic policy fixtures do not prove end-to-end speedup, tail latency, correctness superiority, or CPU-first routing benefits.

Peak RAM/VRAM and resource envelopes for the configured generator context/KV settings remain **unverified**. Available-memory snapshots and conditional admission are useful operational observations, but cannot replace peak measurements. Unknown timings and resource values must remain null or explicitly unverified.

## Final live workflow comparison

The corrected full run `aa259e9559b04144aa39f0cc065ad169` completed 93 executions (31 cases per arm): current mapping 31/31, proposed 31/31, always-text 30/31. The sole baseline failure was the unsupported image case, rejected by production hard admission. Median complete workflow times were 6.333, 6.933 and 6.528 seconds respectively. This single counterbalanced pass is not evidence of a speedup, a tail-latency guarantee, or a quality oracle; open-ended semantic support still needs independent review.

Earlier full run `6ec8c2e3f9bd4436ab0f6ca5ba72929a` recorded 27/31 per arm: nine Windows journal path-length failures and three image resource-admission failures. The path regression was reproduced and fixed, retaining safe publication. Targeted replay `b7f4efa71106431aa163129f451cfade` passed eight of nine code cases; its remaining failure was a validator assuming direct CommonJS export instead of also permitting the valid named export requested by the case. The final harness executes arithmetic checks for either function binding. Historical runs remain separate and their timings are not combined with the corrected full run. See the local `release-routing-verified.log` and [release assessment](final-release-report.md).

Source: [selector](../router/model_selection.py), [default model specs](../router/model_registry.py), [resource admission](../router/resource_admission.py), [telemetry](../router/telemetry.py). Current integration outcomes are reported separately by the release run; no service, model or benchmark execution is implied by this documentation work.
