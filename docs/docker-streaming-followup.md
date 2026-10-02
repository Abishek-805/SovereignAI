# Docker setup, live previews, and complete table coverage

2 October 2026 follow-up. This changes application orchestration and evidence supplied to the installed models; it does not retrain their weights or establish correctness on every task.

## Docker

The sandbox verification record was expired. Starting Docker alone did not renew that record, so code execution remained disabled. A subsequent live check also found Desktop's engine stopped despite remaining background processes and cached image metadata. Start Docker now launches Desktop and explicitly starts the engine with the installed CLI, runs the fixed local sandbox verifier as a background job, shows its progress, and refreshes readiness. Engine-startup failures can retry; failed isolation checks or verification timeouts stop setup. No Docker reset or volume deletion is involved. The fixed engine-start command follows [Docker Desktop CLI documentation](https://docs.docker.com/reference/cli/docker/desktop/start/).

The real verification endpoint passed all 18 checks, including isolation, resource limits, timeout, cancellation, and cleanup. The verified sandbox subsequently executed `print(12 * 5)` with exit code 0 and stdout `60`. Setup verification has a 180-second subprocess bound; stopping its job waits for the current verification step to finish rather than forcibly killing containers.

## Live response previews

Knowledge Chat, Agent, and the Code assistant consume actual generated public text from the local runtime stream. Drafts remain unverified, cannot publish files, and are replaced by the checked final result. Internal plans and review JSON are hidden. Stop, errors, and terminal job states clear the preview. The UI polls in short batches rather than simulating a typewriter animation. Planning and retrieval still show progress before public response generation starts.

A live Knowledge answer exposed growing previews of 9, 223, 395, and 499 characters before completion. Its terminal snapshot cleared the draft. Deterministically calculated table results do not pretend to stream model tokens.

## Table applicability

The planner previously saw two sample records when deciding whether a table could represent a requested group. Those samples could omit valid groups elsewhere in the workbook. It now receives bounded literal-match counts and examples from the full table. Truncation is disclosed, and coverage remains source data rather than inferred user intent. No ADR/ALR-specific branch or fixed pass threshold was added.

A live request explicitly defined pass as at least 25, treated absent/non-numeric marks as failed, and used all cohort records as the denominator. All 14 ADR/ALR assessment results matched an independent `openpyxl` calculation from the original workbook: 187 ADR records and 64 ALR records. The result is evidence for this request, not a guarantee for arbitrary prompts.

Compact live evidence is in [docker-streaming-live-summary.json](../benchmarks/docker-streaming-live-summary.json). The earlier 384-execution benchmark remains unchanged; recovering Docker now does not retroactively convert those old blocked executions into successes.

The launcher also retains the correct lightweight alias when Gemma and the Qwen3.5 upgrade coexist. Live startup verified the registered Gemma profile with exactly one llama server.

## Regression checks

Backend regression: 867 passed, 7 skipped; manifest checks were held until the production build finished because that build replaces the output directory. Final API, Desktop, jobs, and manifest checks: 78 passed. Frontend: 727 unit tests across 61 files, typecheck with zero errors or warnings, and a successful final production build. The generated bundle includes the current Docker error classification and code-draft rendering.

The production app rendered without console or page errors in a disposable browser profile with normal service workers. A separate browser test used mocked job snapshots to verify progressive answer/code drafts, embedded code-fence containment, and replacement by the final answer. It started no model jobs. See [UI smoke evidence](../benchmarks/streaming-ui-smoke.json); real runtime streaming is separately recorded in the live summary above.
