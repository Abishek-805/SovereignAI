# Final router and installed-model audit — 2026-09-28

The router runs real local inference. This is an external capability/task router around dense models, not architectural mixture-of-experts inference. Its registered generation baseline is Qwen3-4B-Instruct-2507 Q4_K_M for text/code and Qwen3.5-2B Q4_K_M with its F16 projector for vision. No coding specialist was installed or claimed superior.

## What was actually exercised

Requests were serialized against the installed runtime/API. The test imports one clearly labelled fictional TXT document, requests a real report artifact, and removes only that test document's library record in `finally`. It neither edits existing user documents nor runs a generated Python demonstration. Existing workspace selection was supplied as metadata for conversational cases; those cases returned the `answer` plan and no file/document tool steps.

Initial end-to-end API sample before the final prompt correction:

| Request | Observed wall time | Action/result |
|---|---:|---|
| Hello, how are you doing? | 9.266 s | Actual model answer; sleeping text runtime observed before request |
| What is your name? | 3.120 s | Actual model answer; no project reads |
| Capital of France, document connected | 3.329 s | Paris; no evidence retrieval |
| Northwind workshop closing time | 3.335 s | **Failed semantic routing**: answered that sources lacked information without searching |
| 18.5 multiplied by 24 | 3.331 s | Calculator action, validated result 444.0 |
| Create a Word report from fictional source | 11.175 s | Read evidence, cited 16:45/Mira Cole/4.2 mm/s, published Word artifact |

The factual failure was not hidden by a passing mocked test. The planner receives document names, not their contents, so it must never conclude that connected sources lack a fact without searching. The prompt now states this explicitly and includes local organization/schedule facts in evidence-dependent questions. An updated installed-model planning run selected `search_documents` for the same closing-time question with all sixteen existing document metadata references. It still selected `answer` for Paris and an informal greeting. This is a bounded observed correction, not proof that every natural-language request is understood perfectly.

## Safety and computation fixes

- Removed the regex override that could promote a model-selected document workflow into a code write merely because a request contained repair vocabulary. The structured intent remains the authority; target fallback is restricted to an actual `edit_code` action.
- Workspace edit planning now declares `new_files`, `existing_files`, or `project` scope. A standalone creation must use only create/mkdir operations; a malformed new-files plan that edits/deletes an existing file is rejected before generation. Root's workspace dispatcher enforces the declared scope.
- The updated model planned a standalone JavaScript subtraction task against an existing addition file/readme as exactly one `new_files` create operation in 9.133 seconds. This checks the real planner, not an executed program.
- Ordinary greetings, identity questions and unrelated knowledge questions use model-generated answers. There is no hi/hey/bye response dictionary in this path. Selected context grants availability, not a request to read all contents.
- Documents are retrieved once by the selected evidence workflow; speculative prefetch was already removed. Report generation reuses that grounded pipeline and exports the actual answer.

## Limits and interpretation

Short warm API samples of approximately 3.1–3.3 seconds are usable but not instant. A sleeping model cost 9.3 seconds for one greeting. A longer generic JavaScript troubleshooting answer took 36.966 seconds in a separate direct planner/conversation run with sixteen document metadata entries. No median, p95, energy efficiency, or general quality score is inferred from these small heterogeneous samples. The supplied screenshot's approximately 103-second four-file code task is a real latency concern; restricting unintended edits reduces repeated generation/validation work, but a before/after matched workload is needed to quantify that reduction.

The machine reports an Intel Core i5-13450HX and an NVIDIA RTX 3050 A Laptop GPU with 4094 MiB VRAM. A sampled GPU total usage of 3530 MiB is not attributable model memory and is not a memory-admission guarantee.

The application supports the registered evidence/report/calculator/vision/coding workflows. Arbitrary navigation and every application action are not available as model tools. Lack of a tool must not be represented as successful execution. Job-owned text completions now aggregate SSE results and check Stop between incoming lines, closing only the active response when cancelled. Loading and prefill can still block before the first stream bytes; standalone vision remains blocking at workflow boundaries. This is not a universal hard cancellation or zero-continuing-compute guarantee.

The registry still has one candidate per text/vision capability. It verifies installed assets/runtime/modality/ownership and models report context limits, but it is not a measured model-centric candidate optimizer with calibrated confidence, quality profiles, or per-model VRAM/RAM admission. The prototype CPU intent classifier remains disabled because its held-out safety probe selected an edit for an explanatory request. No faster model or coding specialist should be enabled solely from an unmeasured recommendation.

## Regression validation

`tests/test_model.py` and `tests/test_agent_context_flow.py`: **25 passed**. New tests reject invalid scope and new-file edit/delete plans, and ensure repair vocabulary in a document explanation does not execute a coding workflow. These controlled tests validate dispatch contracts, not semantic model accuracy.

Live script: `benchmarks/final-router-live-audit.py`. Baseline evidence: `benchmarks/final-router-baseline-results.json`. After the backend reloaded the corrected source, the six-case API repeat passed. The script now asserts actual action selection, plan-only unrelated answering, closing-time fact plus source links, and a successful Word download with valid ZIP header. Raw final evidence: `benchmarks/final-router-live-results.json`.

| Final request | Observed wall time | Verified result |
|---|---:|---|
| Greeting with a selected existing workspace | 8.707 s | `answer`, sleeping runtime before request, no project work |
| Assistant identity | 3.545 s | `answer`, actual natural model output |
| Capital of France with connected source and workspace | 2.905 s | `answer`, Paris, only a plan ledger step |
| Northwind workshop closing time | 5.835 s | `search_documents`, 16:45 with [S1] and linked evidence |
| 18.5 multiplied by 24 with context connected | 3.313 s | `calculate`, 444.0 |
| Word report from the fictional source | 10.221 s | `create_report`, cited facts and real downloadable DOCX |

The test source was removed successfully (HTTP 200). Normal indexed report/answer artifacts remain available from this acceptance task. No unrelated original files were moved or modified. The factual correction increased this sample from an incorrect 3.335-second unsupported answer to a correct 5.835-second sourced answer; speed alone is not an acceptable success criterion. The timing differences between runs are samples, not statistically established improvements.


## Request-owned streamed Stop follow-up

The root implementation preserves the existing completion return contract while requesting `stream: true` only inside a job's cancellation context. Partial text is accumulated internally and published only after a finish reason. Usage/timing events after completion are retained. Cancellation closes that response and does not issue a global slot-stop or model-kill request. ContextVar scope restoration leaves subsequent requests unaffected.

`tests/test_model_job_stream.py` adds seven tests covering partial chunk assembly, usage/timings, stream close on Stop, restored request-local scope, incomplete/malformed/error events, JSON fallback and loading errors. Along with the focused model/context/replacement tests: **38 passed**. An idle `/slots` response initially exposed only processing state; during live inference it also exposed `next_token.n_decoded`, allowing the final probe to observe actual token generation.

The live API Stop probe warmed the model using a real short calculation request, then requested a general JavaScript debugging explanation without files. After 5.247 seconds, the slot was processing with **81 decoded tokens**. Stop targeted only that job. The job reached `cancelled` after **0.119 seconds**, with `result: null`; the runtime slot was observed idle after **0.225 seconds**. These are polling-resolution observations from one generation, not a universal stop-latency guarantee. Loading/prefill before incoming bytes and standalone vision retain the limits described above. Raw evidence is `benchmarks/final-router-stop-results.json`, produced by `benchmarks/final-router-stop-audit.py`.

An initial long-answer probe finished before the Stop threshold because the planner refused the requested 1500-word detail. That attempt did not leave a running job and is not counted as a successful Stop check. The planner instruction now explicitly directs detailed questions to the full-budget conversation generator instead of refusing because of its short planning budget; that instruction remains a bounded behavioral safeguard, not a general model-quality guarantee.


## Precise existing-file edits

The real workspace-plan schema now requires a replacements array for every operation (empty where not applicable). For a small literal edit, the model proposes exact `old_text`/`new_text` replacements on the full requested path. Parser checks reject malformed fields, empty old text, oversized replacement strings and replacements attached to non-edit operations. The workspace applies only uniquely matching bounded replacements, preserving unrelated content, rather than asking the model to regenerate an entire file for a one-line wording change. Existing-file scope with an explicitly named path does not authorize a duplicate basename/content in another folder. Legacy controlled test plans without replacements remain compatible; real structured inference always supplies the required array.
