# Backend routing audit — 2026-09-28

This audit inspected the current request paths, rather than treating the model label or a passing UI build as proof of routing. It uses the supplied routing/model workstream briefs, `workbench-upgrade-plan.md`, and `intent-router-screening.md`. No model was installed, no inference was run, and no live process was restarted by this audit.

## Immediate request correctness

1. **The reported 422 is validation, before model inference.** `/agent/jobs` accepts at most eight history strings and a 2,000-character goal. A growing Code conversation must send bounded history and display the actual validation detail. The root workstream owns the shared frontend request helper; backend routing changes alone cannot repair an invalid payload.
2. **Connecting documents must not force retrieval.** `ask()` and `run_auto_agent()` already ask the structured local planner for an action before evidence/project reads. An `answer` action returns the actual model response, not a greeting table. The planner still requires real behavioral evaluation: current mocked tests prove dispatch contracts, not that every real model interpretation is correct.
3. **Vanilla Chat follows a different path.** `model_proxy()` previously obtains `service.embedder` and applies the heuristic `relevant_passages()` to each textual user message without a structured decision. This may load the embedding runtime for ordinary conversation and search the whole library without a connected scope. Use an explicit context/intent contract in the proxy; do not replace it with a greeting word list. Parent owns this endpoint.
4. **Agent document follow-ups lost history.** The dispatched `ask(...force_documents=True)` and report call omitted recent conversation. A question such as “what rating did he receive?” then lost its referent. Corrected in this bounded change.
5. **Document dispatch retrieved twice.** Agent prefetched two passages before invoking the grounded answer/report workflow, which retrieved again and did not use that prefetch. Corrected by removing the speculative retrieval and vector validation; the selected workflow validates scope and retrieves evidence.
6. **Cancellation after planning was incomplete.** A stopped request could still complete a conversational result after the non-streaming planner returned. Corrected by checking cancellation immediately after planning and before completing answer/inspection results. This does not claim immediate interruption of the underlying non-streaming inference.
7. **Seven-entry history could split a pair.** Planner metadata now retains eight entries, matching the endpoint's four user/assistant-pair contract. The client remains responsible for complete, successful turns.

## Evidence coverage: audit finding and implemented fix

`ask()` uses one top-six retrieval query. A request to summarize sixteen connected documents cannot be assumed to cover all sixteen. The existing generic report fallback is a cited excerpt inventory taking one first chunk per document; its own text truthfully labels this limitation. It is not a semantic synthesis of all files.

The subsequent implementation now provides a planner-selected overview mode; see [document-overview-coverage.md](document-overview-coverage.md). The audit recommendation was a planner-selected overview mode with a bounded per-document evidence budget, followed by a model synthesis and source coverage metadata. For oversized collections, summarize each document with citations and then combine the grounded summaries. Never invent an unavailable pre-existing summary, and never claim full-file coverage when only selected passages were read. Preserve filename focusing for specific questions and history-based referent resolution for follow-ups.

## Routing architecture is not yet complete

`CapabilityRouter.route_request()` maps text/code/calculation to the text key and vision to the vision key. `ModelRegistry` is still keyed by one capability per model. This is a compatible baseline, not the model-centric candidate filtering, admission, measured selection, and per-step telemetry specified by the project.

Missing gates:

- Model records keyed by stable model ID, with multiple supported capabilities and actual asset/runtime availability.
- A structured route decision exposing request ID, required capability/modality, candidate rejection reasons, chosen model/tool, reason, actual context budget, residency, and switch outcome.
- Hard context/asset/runtime admission. GPU/RAM admission must use attributable measurements or conservatively recorded unknown values; total GPU usage is not model usage.
- Alias-aware inference: `LocalModel` methods currently request `sovereign-text` directly. A future selected coding/text candidate must propagate its alias and runtime-reported context consistently.
- A lifecycle result measuring readiness/load/switch and preserving process ownership. Current `acquire_lease()` is serialized launch selection, not a duration-bound resource lease; the service's model lock prevents overlapping inference.
- Independently reviewed held-out capability labels and actual end-to-end comparisons. The prototype BGE router's unsafe explanatory-question→edit result prevents enabling it as a write authority. Do not claim 85.7% pilot accuracy proves production routing correctness.
- Candidate quality and latency/RAM/VRAM profiles measured on this laptop. No new coding model is justified as superior yet.

Keep these gates explicit rather than adding fake confidence, estimated optimal weights, or a separate model per page. A pretrained dense model plus an external task router should not be described as architectural mixture-of-experts inference.

## Executable bounded next steps

1. Finish contract fixes and no-read conversation dispatch across Chat/Agent/Code; run real connected-document unrelated question, named fact, pronoun follow-up, all-file overview, and explicit edit probes.
2. Implement the shared route decision/model-centric registry with the installed baseline assets. Test missing assets, disabled entries, insufficient context, unknown memory, ownership conflicts, load failures, and canceled decisions without launching models in unit tests.
3. Run serialized real workflow checks with cold/warm timing, source IDs, model alias, actual actions and artifacts recorded. Establish a baseline before resource/context tuning.
4. Compare context/KV/residency policies on the fixed workload. Adopt only supported, measured variants. Do not run concurrent UI builds during inference benchmarks.
5. Evaluate a bounded coding specialist only after baseline quality/resource measurements and model-card/license/runtime review. Preserve the baseline for comparison.
6. Let the UI display the verified decision. Styling follows backend correctness, per the user's latest priority.

## Changes and validation owned by this audit

Only the `run_auto_agent()` region of `backend/service.py`, this document, and `tests/test_agent_context_flow.py` were changed. Root owns other routing/model/request changes.

Command: `.app-venv/Scripts/python.exe -m pytest tests/test_agent_context_flow.py -q`

Result: **5 passed in 0.70 seconds**. These tests verify single-dispatch document handling, preserved follow-up history, paired recent planner context, cancellation after planning, and unrelated conversational answers without evidence/project reads. They use a controlled planner; they do not establish real-model semantic quality or latency. Initial system-Python collection failed because that interpreter lacks `lxml`; the installed application virtual environment is the correct test runtime.

## Ordinary Chat proxy follow-up

The proxy no longer instantiates the embedding runtime or searches the private library implicitly. Explicit Knowledge context continues through `/documents/jobs`; ordinary Chat forwards caller conversation and image parts unchanged. This removes the divergent heuristic RAG path rather than adding greeting special cases.

The proxy now preserves a validated `X-Conversation-Id`, and permits GET/DELETE on the actual pinned runtime contract `/v1/stream?conv_id=<identity>` (GET optionally uses `from=<byte offset>`). Exactly one bounded identity is required. Malformed identities/offsets are rejected before model leasing or upstream requests. Stop forwards only that explicit identity to the fixed localhost runtime and does not issue a global slot cancellation or load a model. Replay GET is forwarded as SSE, not buffered until completion.

Verified contract sources: [b11132 server route registration](https://github.com/ggml-org/llama.cpp/blob/b11132/tools/server/server.cpp) and [b11132 stream implementation](https://github.com/ggml-org/llama.cpp/blob/b11132/tools/server/server-stream.cpp). Local `llama-server-impl.dll` also contains `/v1/stream`, `conv_id`, and the completions control endpoint; string presence alone is not proof of behavior.

Cancellation limitation: pinned `server-stream.cpp` explicitly notes that eviction stops stream producers/readers while underlying inference can continue to its natural stop condition. Ordinary Chat must remain truthful about pending compute. Backend Agent/Knowledge jobs still use non-streaming `LocalModel` completions: their cancel event is observed at workflow boundaries, not during that blocking HTTP completion. A feasible future change is request-owned generation identity plus streamed model results and cancellation checks, using the existing pinned per-conversation stop endpoint. Do not globally cancel slots, kill the shared model, or claim an unsupported request-specific hard abort. An actual timing probe is needed before claiming reduced compute time.

Focused proxy tests include unrelated questions, identity questions, exact message/image forwarding, header ownership, per-conversation DELETE forwarding, malformed requests, replay offsets, SSE closure, and no model lease during Stop.

## Image Agent jobs and intent-first dispatch

Image Agent submissions now use `/agent/vision/jobs`, the same observable job state/poll/Stop mechanics as text Agent tasks. Uploads remain available to the job until its callback finishes; the callback's `finally` removes them on success, cancellation, or failure. A rejected busy submission cleans up only its own file. The existing `/agent/vision` and `/vision/ask` synchronous contracts remain compatible.

An attached image supplies bounded metadata to the local planner. An unrelated question receives a real text-model response without opening image pixels or loading the vision model. Only `analyze_image` dispatches visual inference, after releasing the planning lock. A visual action with no attachment requests input instead of causing a dispatch-map failure. No greeting keyword list was introduced.

Vision jobs check Stop before reading/loading/inference and after inference. The current standalone vision HTTP call remains blocking: this change must not be described as hard aborting an in-progress vision generation. The frontend queues Stop while the upload/job ID is pending and then stops that exact job. Submitted attachments leave the composer while their names remain in the user's conversation turn, including stopped/failed requests.

Regression command: `.app-venv/Scripts/python.exe -m pytest tests/test_image_agent_jobs.py tests/test_agent_context_flow.py tests/test_chat_proxy_context.py tests/test_api.py -q`

Result: **91 passed in 7.26 seconds**, with one existing Starlette deprecation warning. Full backend regression subsequently passed **241 tests, with six skipped**. Vision/API follow-up after the complete-request visual instruction passed 16 tests.

Installed-model browser verification passed an attached-image greeting without visual inference, the user's actual Code screenshot through the vision model, and image-job Stop without a published answer. The initial screenshot response returned only the application title; an instruction correction then produced the visible Summa workspace/editor/explorer details. This is a bounded smoke check, not a general vision-quality or compute-performance claim. See [knowledge-context-redesign.md](knowledge-context-redesign.md) for production acceptance.
