# Fidelity continuation — locked phase order

The user's 7 October continuation instructions establish two separate tracks. Production architecture remains unchanged. Frozen task prompts, fixtures, kernel, model parameters, tools, Docker policy and validators remain unchanged in the four-model baseline.

## Track A: model/runtime fidelity

1. Replay exact saved T10 call eight on the original Qwen3.5 runtime. Streaming and non-streaming bodies differ only in `stream`; retain raw response bytes, headers, full payload and offline production-parser output. Do not execute replayed actions or substitute these transport outcomes for validated coding outcomes.
2. Resume the existing four-model comparison at missing model/task cells. There are 60 planned model-phase cases, separate from 45 completed runner cases. No T10 fix, special prompt or additional retry is permitted in this baseline.
3. Classify failures using wire evidence, model reasoning, actual tool execution and independent oracle results. A prose response on both transports excludes dropped tool fragments in the workbench client for those responses, but does not isolate every server/template/model cause.
4. Test state-aware corrective observations in a new evidence namespace after baseline completion. Preserve initial candidates and actual errors; distinguish task-specific diagnostic corrections from general-purpose context mechanisms.
5. Test a constrained action adapter for Coder separately. A valid action alone is not success: execution, correct modification and independent Docker oracle must pass.
6. Evaluate one appropriately sourced/licensed 7–9B Q4 artifact with partial CPU offload on the same scaffold. Download/load choices require verified upstream metadata and measured local resource viability. Never keep a second heavy model active.
7. Consider explicitly budgeted best-of-N only after single-attempt reliability is known. Report pass@1 and total compute alongside pass@N. Do not merge retries into baseline success counts.

## Track B: product acceptance

8. Trace backend job truth → API response → frontend state → rendered label before changing UI. Measure preview cold start and interactions before optimization. Measure resources at 8K and 16K separately; separate display/GPU-total values from process-attributable values.
9. Execute a clean browser matrix for Chat, Knowledge, Agent, IDE, preview, cancellation/navigation, review/Accept/Discard, and resource/job status. Targeted successful examples do not establish the complete matrix.
10. Define release scope from evidence. Test-backed edit/fix/extend assistance has scoped successes; open-ended application generation remains experimental. Do not claim universal autonomous software engineering.

## Preserved evidence and current admission issues

- Exact replay namespace: `evidence/t10-exact-replay/`; each attempt has a unique timestamp.
- First replay admission attempt stopped before inference because the saved model PID belonged to an unrelated process. That process was not terminated. A later exclusive admission archived stale PID metadata after verifying no heavy server existed.
- Docker was initially offline and was restored before further baseline execution.
- Existing experiment liveness uses PID/create-time/heartbeat observations; it does not release production locks or kill processes on TTL.
- Current state must be read from raw completed result records plus verified process liveness. A saved EXECUTING label alone is insufficient.

## Upstream leads

The [Qwen required-tool/template report](https://github.com/ggml-org/llama.cpp/issues/27767) describes failures when thinking is disabled. A separate [required-tool/cache report](https://github.com/ggml-org/llama.cpp/issues/29295) describes cache-dependent responses. Both are user-submitted upstream bug reports on particular configurations, not independent confirmation of the local cause. They justify controlled diagnostics rather than changing runtime or prompt settings inside the frozen comparison.

No benchmark winner, validated T10 recovery, or production migration is implied by this plan.
