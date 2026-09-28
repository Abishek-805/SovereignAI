# CPU intent screening, 2026-09-28

Decision: do not enable these prototype routers in production. The current structured generative planner remains the intent authority. An explanatory question was incorrectly accepted as an edit by the strongest prototype.

The frozen [dataset](../benchmarks/intent-screening-v1.json) contains 44 development prototypes, 42 held-out requests and 10 additional safety probes across seven intents. Labels are engineer-authored, not independently reviewed. Dataset SHA256 is `4a97495c1e48109e2933b4eabb77826b6e9df90eceb31880f494610491930fa7`. The [evaluation script](../benchmarks/evaluate-intent-router.py) and [raw result](../benchmarks/intent-screening-results.json) record versions, predictions, timings, memory samples and policy. No request executed tools or changed files.

| Method | Held-out top-label accuracy | Accepted coverage | Accepted correct | Setup | Sampled RSS increase | Median classification |
|---|---:|---:|---:|---:|---:|---:|
| Word TF-IDF prototypes | 61.9% | 1/42 | 1/1 | 6.95 ms | 0.41 MB | 0.052 ms |
| Character TF-IDF prototypes | 69.0% | 1/42 | 1/1 | 20.45 ms | 1.36 MB | 0.376 ms |
| Installed BGE CPU embeddings | 85.7% | 18/42 | 18/18 | 595.09 ms | 162.84 MB | 6.901 ms |

Acceptance used a frozen minimum similarity of 0.72 and margin of 0.08; these are pilot thresholds, not calibrated probabilities. Remaining requests defer to the planner. BGE accepted **“How would I create a directory in Python?”** as `edit_code` (similarity approximately 0.723, margin 0.09). This is a general explanation, so the probe demonstrates an unsafe intent decision even though the 18 accepted held-out cases were correct. Writes were never authorized by this experiment.

The machine has 16,873,545,728 bytes RAM, Windows 11 build 26200, Python 3.12.14, NumPy 2.5.2 and ONNX Runtime 1.23.2. BGE used CPUExecutionProvider and two ONNX threads. Timings are one pass over heterogeneous requests, not repeated workflow latency, p95 or release quality evidence. RSS differences are samples, not peaks or attributable steady-state memory.

This evaluates nearest-prototype retrieval, not a trained linear classifier. No extra dependency or model was installed. A production candidate needs independently reviewed examples, calibrated uncertainty, explicit read/write safeguards and comparisons against the current planner on real document, code, vision and conversational workflows. The evaluation set must not become training data without replacing the held-out set.

Method references: [BGE model card](https://huggingface.co/BAAI/bge-small-en-v1.5), [scikit-learn text feature extraction](https://scikit-learn.org/stable/modules/feature_extraction.html#text-feature-extraction). These explain methods, not performance on this laptop.
