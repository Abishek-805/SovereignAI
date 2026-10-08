# T10 exact call-eight replay — completed transport diagnostic

**Diagnostic status: COMPLETE. Coding recovery status: NOT ESTABLISHED. Production unchanged.**

Evidence: `evidence/t10-exact-replay/20261007-202627/`.

## Controlled input

Replayed the complete request from `evidence/code-agent-fidelity-v1/native/T10/attempt-02/call-008.json`. No user message, tool schema, tool observation, token limit, thinking flag, temperature or context was changed. Paired requests differ only in `stream`. Both preserve the original `stream_options` field. The existing registry launched the original Qwen3.5 worker with the same arguments as the saved runner lease; runtime build is b11132-633733d0a.

Raw response bodies and headers were preserved. Streaming bytes were fed through the production parser offline. No tool returned by this diagnostic would be executed; the replay does not publish files or replace baseline coding outcomes.

## Results

| Transport | Finish | Completion tokens | Prompt tokens | Public characters | Raw tool fragments/calls | Parsed tool calls |
|---|---|---:|---:|---:|---:|---:|
| Streaming | length | 4,096 | 4,051 | 16,486 | 0 | 0 |
| Non-streaming | length | 4,096 | 4,051 | 16,486 | 0 | 0 |

Public content is identical across the paired responses. The first request had zero cached prompt tokens; the second reported 4,047. This is not a balanced latency experiment. Reasoning-token counts are not exposed by the response usage and remain unknown.

The original failure was preceded by seven successful tool calls. It was not an inability to make any tool call. The long response repeatedly misinterpreted aggregate reservation capacity: four existing seats plus two requested seats exceeds capacity five. It discussed the oracle rather than producing the next action.

## What this establishes

For this exact input and configuration, the workbench stream parser did not drop an otherwise valid tool call: the raw stream itself contains none, and the JSON transport reproduces the same prose. Required-tool selection was present in both outbound payloads. A completed validated coding task has not been demonstrated by the replay.

## Pinned source finding and limitations

The [installed-build auto-parser source](https://github.com/ggml-org/llama.cpp/blob/633733d0a/common/chat-auto-parser-generator.cpp) requests a non-lazy grammar for required tools. Its tool-format builders nevertheless allow an optional content prefix before the tool marker (`p.optional(p.content(content_before_tools))`). Therefore “required” does not necessarily bound the number of text tokens emitted before reaching a tool call. A token-limited response can end while still generating that prefix. This is a source-supported mechanism consistent with the observed response, not a trace proving every internal grammar decision.

The local server reported `peg-native` and template tool support. The captured source is retained under `upstream/`. Current evidence supports investigating action-prefix constraints at the runtime/template/adapter boundary. It does not justify claiming that all Qwen templates ignore tools or that a 4B capability ceiling is proven.

Upstream reports [27767](https://github.com/ggml-org/llama.cpp/issues/27767) and [29295](https://github.com/ggml-org/llama.cpp/issues/29295) describe related required-tool/template/cache failures on their own configurations. They are diagnostic leads, not independent proof of this laptop's cause. Here both cold and warm paired requests failed identically; the reported cache-sensitive behavior was not demonstrated by this pair.

## Environment and subsequent work

The first admission attempt was blocked by reused PID metadata. The unrelated process was not terminated. Stale PID data and its adjudication are preserved. Docker was offline, then restored; the existing pinned image passed all 18 verifier checks. The previous attestation was retained before refresh. Neither Docker image nor sandbox policy changed.

The unchanged four-model baseline was relaunched from missing cells using `experiments.fidelity_v1.evaluate --phase models`. It retains the frozen kernel, prompts, fixtures, budgets, tools, runtime and validators. No T10 corrective observation, new grammar or special retry was injected. Process-aware heartbeat evidence is now available.

Focused checks: **13 passed**, including paired-payload equality, liveness and existing runner checks. Frozen production-source and task hashes passed verification.

Model comparison, state-aware correction, constrained Coder actions, larger-model tradeoff, best-of-N and product/browser gates are separate unfinished phases. No production migration or model winner is implied.
