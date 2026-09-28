# CPU router and system integration

The routing release remains gated. Four CPU classifiers were benchmarked with frozen development/calibration policies and independent heldout cases. None met every accuracy and coverage gate, so the application retains its bounded planner fallback. This is not a completed promotion or a claim that the planner is an optimal router.

## Implemented changes

- Hierarchical capability taxonomy, four reproducible CPU candidates, independent evaluation, calibration-selected acceptance thresholds (not calibrated probabilities), and release manifests that reject failed gates or changed classifier artifacts.
- Model-centric candidate filtering with reviewed license metadata, machine-readable rejection codes, finite resource observations, context/KV profile conditions, and deterministic replay tests.
- Selection compares measured latency plus switching seconds when comparable quality measurements exist. Missing measurements retain explicit resident/registry priority; they are not assigned invented scores.
- Explicit empty document selection cannot widen to the full library, including named-file questions. Retrieval uses the current question rather than silently prepending earlier requests.
- Formal bounded arithmetic goes directly to the existing safe calculator from Chat, document Chat, and Agent. It never loads a model. General conversational replies still require actual generation.
- An approved CPU classifier can bypass the planner for narrowly supported read-only decisions. Agent file mutations always retain the independent planner and application tool guards. No failed classifier is enabled by this integration.
- Additive request-owned telemetry distinguishes Knowledge permission, required evidence, evidence actually used, actual retrieval counts, tool execution, candidate admission, validation, measured timings, and failure layer. Unknown measurements remain null.
- Collapsed route details remain optional; private nested logs are excluded. Production rendering passed desktop/390px dark/light checks.

## Validation evidence

Final backend validation passed 478 tests, with 7 skipped. Frontend validation passed 823 tests across 76 files; Svelte reported zero errors and warnings, and the production build passed. Four browser acceptance checks passed across desktop and 390px layouts in dark and light themes, without horizontal overflow or browser errors.

After restarting the API with the final source, the live arithmetic check executed 24 HTTP requests across four expressions and streamed/non-streamed responses. Its median response time was 5.79 ms, excluding the subsequent routing lookup; there was no selected model or measured model inference in any sample. This does not describe general generation latency. An initial collection script accidentally reused responses for streamed cases; its invalid draft is preserved and explicitly excluded from latency claims. The corrected explicit-loop harness verifies every streamed response separately.

The initial 31-task matched comparison is retained under `benchmarks/routing-strategy-artifacts/3cd5e1ebe05a4a229733c2114d6e82ba/`. Always-text passed 23/31, fixed capability mapping 22/31, and candidate selection 23/31, with identical hard safety filters. CPU classification was disabled in all arms. Genuine model executions exposed incorrect evidence routing, numeric punctuation validation, project inspection, and image routing failures.

After corrections, the nine-case three-policy rerun under `835c8b54f0984f6aad29c03c75f12d55/` passed 9/9 for mapping and selection, and 8/9 for always-text; the latter correctly refused an image unsupported by its text candidate. A subsequent full selection-only run under `3e5b50ae9ca743d1b23432bd14739a38/` passed 29/31, exposing one missed retrieval request and one unjustified report refusal. Balanced planner examples and a bounded evidence-preserving report review corrected those failures.

The final full selection-only run under `benchmarks/routing-strategy-artifacts/d898e45ea1694e54b7816014c6a983a7/` passed **31/31**. It includes genuine conversation, document retrieval, calculations, Word reports, project reads and edits, new executable code with Docker functional checks, and image understanding. Isolated fixtures, source hashes, file readback, and validation outcomes are recorded. Later request-scope and permission tightening passed the final backend suite. These runs remain separate: different source revisions and policy subsets cannot establish a comparative speedup. They do not prove universal semantic correctness or promote the failed CPU classifier.

## Remaining release limits

The classifier quality and coverage gates have not passed. Only one installed model is eligible for ordinary text/code generation, so there is no measured choice between competing text/coding models and no empirical oracle. Model-attributable peak memory/context costs and broader reviewed answer quality are not established by whole-device GPU readings. Resource admission therefore exposes those conditions rather than claiming measured certainty. A single matched run does not establish p95 latency or a speedup.

Existing context/KV experiments in `benchmarks/context-kv-study-results.json` concern their recorded source/runtime configurations and narrow tasks. They do not establish that changing the current production profile improves broad task quality. No new model or runtime profile was installed for this phase.

The application capability router chooses admissible models and workflows; the llama.cpp runtime router manages runtime instances. These remain separate layers. The runtime's supported management behavior is documented in the [official server documentation](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md). Baseline model license metadata links directly to the official [Qwen3-4B-Instruct model card](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507) and [Qwen3.5-2B model card](https://huggingface.co/Qwen/Qwen3.5-2B).
