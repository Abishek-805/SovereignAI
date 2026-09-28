# SovereignAI workbench upgrade

Updated: 2026-09-28. This reconciles the four supplied plans with the existing implementation. Proposed work is not a measured result.

## Order and boundaries

1. Stabilize intent handling and existing workflows. General conversation must produce a real model answer without project reads, retrieval, Docker, or edits. Selected context is permission to use relevant context, not an instruction to mutate it.
2. Establish the routing contract and CPU classifier evaluation. Keep capability prediction separate from model choice. Compare word/character TF-IDF linear classification with the existing CPU embedding model and labeled prototypes. Train on development examples; evaluate independent held-out requests, including greetings, identity questions, read-only code questions, ambiguous follow-ups, document summaries, reports, images, calculations, and explicit edits. Low-confidence requests may request clarification; they must not trigger writes.
3. Measure the installed model baselines and constrained alternatives. Change production selection only after repeatable local quality and resource measurements.
4. Connect the verified contract to the interface. Preserve sandbox, evidence, cancellation, and file-conflict protections. Inspect desktop, laptop, narrow, light, dark, keyboard, and reduced-motion states.

The source documents contain separate workstream stop rules. They are applied at each workstream boundary, rather than interpreted as permission to mix a UI refactor with an unmeasured runtime replacement.

## Routing contract

One backend decision should expose request ID, task capability, modality, candidate models, rejection reasons, selected model/tool, route reason, required/available context, memory admission, current residency, switch requirement, classifier overhead, execution timings, validation, and fallback outcome. Unknown measurements remain null. Do not invent quality confidence, optimal weights, or VRAM figures.

Pipeline: bounded request metadata → CPU capability classification → candidate filtering → resource admission → measured scoring → model lease → execution → deterministic checks → telemetry. Tool requests use registered deterministic tools where appropriate. No model-generated arbitrary host commands.

Model records become model-centric, allowing several models per capability and several capabilities per model. Hard rejection covers disabled entries, missing GGUF/projector, unsupported modality/runtime, insufficient context, and insufficient resource budget. Quality is a floor, followed by measured total latency and switching cost; retain an already loaded suitable model when justified by those measurements.

## Model selection and experiments

Installed baselines are Qwen3-4B-Instruct-2507 Q4_K_M and Qwen3.5-2B Q4_K_M with F16 projector. Embedding remains the existing local CPU BGE implementation unless retrieval evaluation demonstrates a bottleneck. A Qwen2.5-Coder-3B candidate is proposed, not installed or approved as superior. Compare official model cards, licenses, runtime compatibility, and complementary local task quality before downloading a bounded candidate pool.

The pinned llama.cpp b11132 binary's help was inspected locally. It supports models-dir/models-preset, models-max, idle sleep, context selection, and KV type controls. Support is not proof of performance. Compare the current owned process lifecycle with a persistent router configured for one loaded GPU-heavy model. Keep ownership checks and truthful load failure states.

Run controlled A/B experiments for 4096/6144/8192 context, Q8/Q4 KV where supported, bounded prompt caching, batch/ubatch, and idle retention. Align Settings, registry, launch scripts, and actual runtime context only after the selected workload passes. Measure cold/warm TTFT, output rate, switch time, backend/model/embedding RSS, system free memory, Docker pressure, and total versus attributable GPU usage. Report medians; publish p95 only with adequate sample counts.

Use 30–50 independent end-to-end tasks with expected evidence, executable code checks, deterministic arithmetic, and human-reviewed image observations. Compare always-text, existing mapping, proposed router, and retrospective oracle only when alternatives have actually been run. Separate model, router, resource, and tool failures. Do not describe the model pool as final until these gates pass.

Research shortlist (model cards checked, not local performance results):

| Role | Candidate | Decision now |
| --- | --- | --- |
| General/document/code baseline | [Qwen3-4B-Instruct-2507](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507) | Keep installed baseline; official card identifies Apache 2.0. |
| Vision baseline | [Qwen3.5-2B](https://huggingface.co/Qwen/Qwen3.5-2B) | Keep installed GGUF/projector; verify observations locally. |
| Coding specialist | [Qwen2.5-Coder-3B-Instruct](https://huggingface.co/Qwen/Qwen2.5-Coder-3B-Instruct) | Test candidate only; official card identifies qwen-research license, not Apache 2.0. Check deployment terms before adoption. |
| General alternative | [Phi-4-mini-instruct](https://huggingface.co/microsoft/Phi-4-mini-instruct) | Research candidate; exact GGUF revision, compatibility, memory, and local quality still needed. |
| Multimodal alternative | [Gemma 3 4B IT](https://huggingface.co/google/gemma-3-4b-it) | Research candidate; gated terms, projector/runtime, and 4 GB fit require review. |

[RouteLLM](https://arxiv.org/abs/2406.18665) supports evaluating learned routing and quality/cost trade-offs. [RouterBench](https://arxiv.org/abs/2403.12031) supports systematic comparison against baselines. Neither provides laptop-specific speed or quality results for this application. Newer research links in the supplied proposal must be independently retrieved before being cited as evidence.

## Interface architecture

Five destinations: Chat, Agent, Code, Knowledge, Control Center. Knowledge manages and previews the document library; Chat and Agent consume explicitly connected document references. Knowledge has no assistant or composer. Chat supports local file attachment; Agent presents observable actions, checks, results, and artifacts; Code retains Explorer/editor/assistant/terminal/changes with resizing; Control Center manages model/runtime/document/download/appearance state.

The global model control displays the actual model and automatic routing state. Detailed route reasons must come from the backend. A stopped or sleeping model must not be described as loaded. General questions use inference; a cheap router does not imply canned answers.

Document browsing stays in Knowledge; asking happens in Chat or Agent within a fixed-height workspace. Only the active reading or conversation region scrolls vertically. The composer remains visible. Agent history and new-chat actions stay in a compact header. User turns remain visible during generation. Cancellation is available throughout active jobs.

The terminal accepts program input on its terminal surface. Its shell is Docker Linux, not host PowerShell. Commands must accurately disclose whether sessions are persistent; a cosmetic PowerShell prompt must not imply host access. Applied code changes are reviewable and can be accepted or undone. Unsaved buffers must not be overwritten by an assistant result.

## Design references and adopted patterns

- [Fluent 2 layout](https://fluent2.microsoft.design/layout): consistent spacing and task hierarchy, without importing a second component framework.
- [VS Code terminal basics](https://code.visualstudio.com/docs/terminal/basics): integrated terminal interaction and keyboard focus, while preserving the workbench's sandbox boundary.
- [Cursor agent overview](https://cursor.com/docs/agent/overview): task actions and reviewable outcomes, without copying branding.
- [LM Studio basics](https://lmstudio.ai/docs/app/basics): distinguish model installation, loading, and execution state.
- Installed taste skill: audit, typography, restraint, responsive and copy verification. Its landing-page defaults are not applied to dense IDE/product screens.

Avoid marketing heroes, fake progress, decorative metrics, duplicate status badges, and separate model-per-page routing logic. Keep existing Svelte, Monaco, icon family, and theme foundation.

## Release evidence

Record implementation status, tests, real browser observations, reproducible measurement commands, and known limitations separately. The earlier regression baseline was 188 passed / 6 skipped. Re-run after final source changes. Do not claim “perfect”, “optimal”, or “verified” from a build alone.

## Current implementation checkpoint

The intent-first behavior is currently implemented with the local generative model's structured plan, not yet a production CPU classifier. A real local `What is your name?` request with a selected project completed with an answer and only a plan step: no project reads or Docker execution. Its cold end-to-end time was 23.3 seconds. This single timing is not a median, classifier benchmark, or optimization claim.

The present registry remains keyed by text/vision; code uses the text baseline. Its configured contexts remain 24576 text / 16384 vision. These are baseline settings pending the controlled context study. No new coding model has been installed. No persistent llama.cpp router migration has been adopted. These are explicit remaining engineering work, not completed architecture.

Implementation map for the next routing phase:
- `router/router.py`: capability analysis and structured decision instead of fixed capability-to-string mapping.
- `router/model_registry.py`: model-centric candidates, availability/admission, profiles, owned lifecycle and switching measurements.
- `backend/service.py`: common decision consumer for document, project, image, and agent steps; do not inspect selected context before intent requires it.
- `backend/model.py` and `backend/settings.py`: alias-aware execution and one runtime-reported context budget.
- `backend/app.py`: route/status/telemetry contracts, retaining existing endpoint compatibility.
- `benchmarks/`: versioned labels, train/evaluate scripts, model workflow evaluation and context/KV/lifecycle experiments.
- `tests/`: candidate rejection, conservative resources, uncertainty/no-write behavior, residency, failed loads and concurrent requests.
- Frontend model control and Control Center: display the verified decision, null measurements, actual availability, and retryable failures.

Do not enable an unevaluated classifier just to remove the generative planner. Do not label a capability-to-page mapping as a completed resource-aware router.

CPU screening is now recorded in [intent-router-screening.md](intent-router-screening.md). The frozen 44-development/42-held-out pilot compared word/character TF-IDF and installed CPU BGE prototypes. BGE reached 85.7% top-label accuracy but incorrectly accepted an explanatory directory question as an edit in a safety probe. No candidate was enabled. Independent labels, trained/calibrated classification, model-centric admission and end-to-end quality/resource studies remain open.
