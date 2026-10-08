# Stage 0 — response fields and thinking diagnostic

**Status: COMPLETE for preserved-wire analysis. Current runtime state unavailable. STOPPED; Stage 1 is not authorized.**

Date: 8 October 2026, Asia/Calcutta. Preregistration SHA-256: `d0b682d3250bb5854a0fc9573f66f366bbec25656c36997a4e8457312c69ed7d`.

## OBSERVED FACT — response location

The preserved exact call-8 wire bodies were parsed directly. Streaming contained 4,099 JSON events and one `[DONE]` marker. The reconstructed text matches both the saved stream parser output and the raw non-streaming response.

| Measurement | Streaming | Non-streaming |
|---|---:|---:|
| Ordinary assistant content characters | 16,486 | 16,486 |
| Populated reasoning_content field | Absent | Absent |
| Populated tool_calls/function_call or other assistant structure | None | None |
| Tool marker `<tool_call>` in content | 0 | 0 |
| Finish reason | length | length |
| Completion tokens exposed in usage | 4,096 | 4,096 |
| Prompt tokens exposed in usage | 4,051 | 4,051 |
| Cached prompt tokens exposed in usage | 0 | 4,047 |
| Hidden reasoning-token count | UNKNOWN | UNKNOWN |

Content SHA-256 is identical in both modes: `0f99449a58bf7436f8612d39c2378b58122e63e4f4775b7fc2c9a74ef1b7a2ef`. All populated leaf fields were inventoried, including response metadata, usage and timings. Neither body contains an alternate populated action representation. The assistant role string is metadata, not additional generated prose.

Both preserved requests use temperature 0, max_tokens 4096, tool_choice `required` and `chat_template_kwargs.enable_thinking=false`. No seed or response_format was supplied. Both responses identify fingerprint `b11132-633733d0a`.

## OBSERVED FACT — launcher, saved props and template

The saved worker command uses Qwen3.5-4B-Q4_K_M, Jinja, context 16384, one slot, server prediction ceiling 8192 and q8_0/q8_0 KV cache. The request limit remains 4096. The saved command and current `ModelRegistry.launch_args` source include no explicit reasoning/thinking/reasoning-budget flags. No launcher was invoked.

Historical props expose `reasoning_format="none"` and `reasoning_in_content=false`. Saved template capabilities report tools/tool_calls support, while preserve_reasoning and reasoning_effort support are false. The saved template's generation branch emits an empty `<think>... </think>` block when enable_thinking is false or not true. These are historical observations; they do not establish every effective server default or the model's internal reasoning state.

The preserved pinned parser-generator source permits optional content before the tool marker (lines 356 and 475) and makes required-tool grammar non-lazy (lines 76–79). This is a plausible mechanism for content consuming the output budget. It is not proof that this exact grammar branch caused the response.

## OBSERVED FACT — current environment

The existing run_status reports `STOPPED_BY_USER`, running_verified=false. Its checkpoint still names an interrupted task; that is not a live evaluator. Process inspection found no relevant Python evaluator or llama-server process. No process was started, stopped or leased.

Read-only GET requests to current /props, /slots and /v1/models on port 8087 were refused. Docker ps could not connect to the Docker Desktop Linux engine pipe. Consequently current chat format, detected model capabilities, template state and Docker readiness are UNKNOWN/unavailable. Historical props have not been substituted for current values. This is an environment blocker for later execution, not a model failure.

## INFERENCE

The exact replay's 16,486 characters occupy ordinary content at the HTTP response boundary. The raw wire does not support the claim that the stream parser dropped a valid tool call: no raw action representation exists in these responses. Reasoning-like language in content does not establish a populated reasoning_content field or hidden reasoning-token count.

No observed server-level thinking flag has been shown to cause this failure. Historical reasoning-format settings are known, but their causal effect is untested. Action emission and the separate failure to account for the existing reservation remain distinct unresolved dimensions. Stage 0 executes no action and establishes no implementation or oracle success.

## UNKNOWN

- Exact causal mechanism: model continuation, optional content prefix, grammar/template enforcement or another runtime interaction.
- Hidden reasoning-token count and effective current server configuration.
- Whether a JSON protocol emits a valid action, whether it is semantically correct, or whether its implementation passes Docker validation.
- Schema, finish-action and embedded-code fidelity; latency and token-rate effects of an adapter.

## RECOMMENDATION / stopping decision

The response-field finding does not trigger the rule requiring a separate diagnostic for substantial reasoning_content. Stage 1 is a reasonable next controlled investigation **after explicit human approval and readiness verification**. Do not start it now, and do not start a server or Docker as part of this read-only stage. Production remains frozen; no adapter is promoted and no superiority claim is made.

The submitted prompt explicitly requires stopping after Stage 0. This report is the reviewable checkpoint; Stage 1 and later stages have not been executed.

## Integrity and evidence

Preregistration and 3,362 frozen source/historical files retained their hashes. No production file, historical trajectory, benchmark task, oracle or request was modified. Model calls: 0. Tool dispatches: 0. Docker executions: 0. The initial timestamp-registration failure and its fixed-offset harness correction are recorded in AMENDMENTS.md; preregistration remained unchanged.

Files in this directory:

- `response-fields.json`: complete populated-field inventory and wire counts.
- `request-settings.json`: exact recorded request settings.
- `launcher-template-audit.json`: saved capabilities/settings/template branch and parser-output reconciliation.
- `current-runtime.json`: current read-only endpoint and Docker observations, separate from saved command.
- `run-status.json`, `processes.json`: evaluator/process observations.
- `integrity.json`: frozen hash recheck and zero-execution confirmation.

The parent directory contains the immutable preregistration, manifest and amendments. Original wire bodies and headers remain at `evidence/t10-exact-replay/20261007-202627/`, with their hashes in the new manifest.
