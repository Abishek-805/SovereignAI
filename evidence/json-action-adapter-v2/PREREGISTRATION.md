# JSON action adapter v2 — Stage 0 preregistration

Registered on 8 October 2026 (Asia/Calcutta), before the Stage 0 analysis script executes.

## Scope and hypothesis

Stage 0 only. Determine whether the preserved exact T10 call-8 replay text resides in ordinary assistant content, reasoning_content, or an alternate action representation. Inspect historical launcher arguments and current read-only runtime metadata. This stage tests no adapter and makes no task-success claim.

## Independent variable and controls

No intervention or independent-variable manipulation. Compare two already-completed responses: streaming and non-streaming. Reuse their exact requests, raw bodies, headers and runtime records. Do not rerun a cell. Historical responses remain controls, not current-session measurements.

Frozen: production source, model, quantization, prompts, messages, tools, context, budgets, kernel, validator, Docker policy, KV-cache settings and historical evidence. No model lease acquisition or launcher invocation is authorized in this stage.

## Sample, temperature and seeds

Sample size: two preserved response bodies from evidence/t10-exact-replay/20261007-202627. All streaming JSON events are inspected. Temperature, seed, max_tokens and thinking settings are read from the preserved requests, never overridden. No fresh sampled output, no assigned seeds and no temperature sweep.

## Measurements

Parse the raw non-streaming JSON and raw SSE data events. Inventory every nonempty response field recursively; separately count assistant content, reasoning_content, tool_calls and legacy function_call fields. Concatenate content fragments in wire order. Compare resulting text and count characters as Python Unicode code points. Record finish reasons, directly exposed usage and fingerprints. Hidden reasoning-token count remains UNKNOWN unless explicitly supplied in usage.

Read router/model_registry.py, saved runtime command and runtime props. Identify explicit reasoning/thinking flags without treating their absence as proof of effective runtime behavior. Capture current process identities, GET /props, GET /slots, GET /v1/models and Docker ps output, with bounded timeouts. Unavailable endpoints stay UNKNOWN; never start a server to make them available.

## Criteria and stopping rule

Inspection success: raw responses parse completely, field counts reconcile with preserved parsed content, and absence/presence of action representations is explicitly reported. Disproof of the ordinary-content-only hypothesis: populated reasoning_content or alternate structured action content carrying the observed text/action. Malformed or missing evidence prevents a definitive conclusion.

If substantial text is in reasoning_content, recommend a separate approved reasoning/template diagnostic. If ordinary content carries it and no alternate tool representation exists, recommend considering Stage 1 only after approval. In every case, write Stage 0 report and STOP. Do not execute Stage 1 automatically.

## Evidence and integrity

Evidence path: evidence/json-action-adapter-v2/stage-0/. Before execution, record this document's SHA-256 and hashes of inspected historical files and production source in manifest.json. Recheck those hashes after analysis. Never edit preregistration after execution starts; corrections require a separate AMENDMENTS.md. All analysis code stays in experiments/json_action_v2/. No final experiment report or winner is authorized at Stage 0.
