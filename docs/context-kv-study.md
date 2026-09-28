# Context and KV cache study — measured local profiles

The six-profile study favors 4096 tokens with q8_0/q8_0 for its **fixed, short synthetic workload**. It does not establish the best production context, document quality, or tail latency. The application default was restored after the study; reducing the production context requires a separate workload and quality gate.

Sources: `benchmarks/context-kv-study.py`, `benchmarks/context-kv-study-results.json`, and `benchmarks/context-kv-study-results.csv`. These are actual local runtime measurements, not model-card estimates. Each profile has one first request after a fresh runtime launch and **two warm requests**. All requests processed 1488 prompt tokens and generated 56 completion tokens. Prompt caching was disabled; recorded cached-token counts were zero. The maximum requested output was 128 tokens.

| Context | KV K/V | Launch to ready (s) | Overall lease (s) | First-request TTFT (s) | Median of two warm TTFTs (s) | Warm generation tokens/s | Maximum sampled process RSS (MiB) |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 4096 | q8_0/q8_0 | 3.539 | 7.638 | 1.239 | 0.976 | 31.64 | 2832.5 |
| 4096 | f16/f16 | 8.030 | 12.179 | 1.529 | 1.466 | 24.54 | 2900.7 |
| 6144 | q8_0/q8_0 | 8.746 | 12.902 | 1.414 | 1.196 | 28.45 | 2872.9 |
| 6144 | f16/f16 | 9.739 | 13.903 | 2.048 | 1.811 | 19.89 | 3029.6 |
| 8192 | q8_0/q8_0 | 7.450 | 11.693 | 1.785 | 1.554 | 23.56 | 2933.5 |
| 8192 | f16/f16 | 5.392 | 9.453 | 2.255 | 2.206 | 17.47 | 3160.5 |

Launch-to-ready measures runtime startup and readiness. Overall lease also includes ownership, acquisition, and launch checks. First-request TTFT begins **after runtime readiness**; it excludes model loading. Adding or equating these columns would obscure distinct measurements. Process RSS was sampled at approximately 50 ms, so a brief higher peak may be missed. Tokens/s is the runtime generation metric; it does not include loading, planning, retrieval, validation, export, or API transport.

The device GPU-used-memory snapshots after requests ranged from 3758–3776, 3738–3771, 3703–3710, 3747–3771, 3705–3735, and 3669–3698 MiB respectively in table order. Available host RAM ranged from 1976–1978, 1810–1822, 1715–1738, 1636–1639, 1387–1628, and 1491–1507 MiB. These are **whole-system snapshots**, not attributable model allocations or isolated VRAM peaks. External memory pressure varied across the fixed-order profiles. The RSS differences cannot be presented as a controlled causal memory saving.

All 18 responses passed the narrow output-format check: the answer began with `RESULT=42`. This is not document-grounding, semantic accuracy, code correctness, OCR, vision, or long-context quality evaluation. No Docker-loaded scenario was measured by this script. The sampled contexts were capacity settings, not prompts occupying 4096/6144/8192 tokens; the workload did not stress the context boundary.

There is **no p95 estimate**: two warm observations per profile are insufficient. These descriptive medians cannot support a general latency SLA or robust cold-loading ranking. The lower q8 warm TTFTs and higher generation rates are an observed result for this workload, with no claim that KV quantization preserves all task quality.

Before changing defaults: run repeated randomized or counterbalanced profiles on matched short and near-limit prompts; measure document and code correctness, citations and exports; include actual Docker concurrency and host pressure; distinguish cold startup from first-token and full workflow latency; verify context admission with reserved output tokens. Collect enough independent repetitions for tail estimates. Register resource measurements against their exact context/KV configuration, and abstain from transferring them to an unmeasured context. The current default of 24576 tokens is not evaluated by this six-profile study.

`benchmarks/routing-strategy-comparison.py` prepares a separate 31-task comparison. It does not reuse these measurements or the primary integration run as independent strategy samples. With the currently registered eligible alternatives, legacy mapping and proposed selection choose the same physical model when admitted. No speedup or retrospective oracle value is implied by that equivalence.
