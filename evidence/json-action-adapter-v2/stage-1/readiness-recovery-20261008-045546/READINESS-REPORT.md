# Stage 1 Readiness Recovery

## Starting State
BLOCKED / ENVIRONMENT. Prior readiness.json and Stage 0 are preserved unchanged.

## Docker State
OBSERVED FACT: Docker Desktop was not running. Its existing per-user executable was started normally with a hidden window (PID 10160). No manual kill, configuration change, alternate engine or system-service restart occurred. docker info now succeeds and reports Linux. Startup poll and raw info are preserved.

## WSL State
OBSERVED FACT: docker-desktop was Stopped, WSL version 2. Its post-start listing is preserved in wsl-after.txt. WslService was observed running before startup. No WSL distribution/configuration was changed.

## Docker Context
OBSERVED FACT: desktop-linux was active before and after recovery. No context switch occurred.

## Pinned Image
OBSERVED FACT: exact image sha256:6f6ac11cda347a185454338dee35d77003e066579a3261b52b7c6ff1048c8573 exists and was inspected. No image pull, rebuild or replacement occurred. Full inspection is in image-info.json.

## Docker 18-Check Result
OBSERVED FACT: 18/18 PASS using the unchanged scripts.verify_docker_sandbox.verify function, in 17.22 seconds. All result booleans and verifier output are retained. The function was called without the CLI's production attestation write; data/sandbox-validation.json was not rewritten. These are trusted safety probes, not generated application or JSON actions.

## Worker Launch
OBSERVED FACT: existing ModelRegistry.acquire_lease('text') launched PID 30072. Actual executable arguments exactly match registry arguments and the saved replay worker. Archived pre-launch PID/log metadata remains in this recovery directory. No unrelated process was terminated and no second heavy worker was launched. One slot is idle (is_processing=false).

## Runtime Fingerprint
OBSERVED FACT: live /props reports b11132-633733d0a, matching the saved runtime. Current build is verified, not substituted from history. No model completion was requested.

## Model Verification
OBSERVED FACT: Qwen/Qwen3.5-4B, Qwen3.5-4B-Q4_K_M.gguf, Q4_K - Medium, selected via the existing registry. Current artifact SHA-256: 00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4. Live model path matches preserved props. Historical replay records did not expose an artifact SHA-256, so historical byte-for-byte digest equality is not independently established; the current digest is retained for future stages. No artifact was modified or downloaded in this recovery.

## Endpoint Verification
OBSERVED FACT: /props, /slots and /v1/models all return HTTP 200. Their raw JSON and headers are saved separately. Live props advertise tools/tool_calls, typed content and object arguments support. preserve_reasoning and reasoning_effort support are false. reasoning_format=none and reasoning_in_content=false. These are metadata observations, not a demonstration that tool calls or JSON actions work.

## Frozen-Configuration Verification
OBSERVED FACT: same context 16384, q8_0/q8_0 cache, one slot, runtime/build, model path, quantization, template, capabilities and complete launch arguments. The command still supplies --n-predict 8192; live props expose n_predict=-1, also recorded separately against saved props. The replay request remains capped at 4096; no request was sent or budget altered. No inference that launcher ceiling enforcement has been experimentally proven is made. Production source and all 3,362 frozen hashes remain unchanged. Stage 0 hashes were rechecked without rerunning Stage 0.

## OBSERVED FACTS
Docker startup restored the approved Linux engine; exact pinned image is present; 18 safety probes passed; registry-owned worker and live endpoints match the expected baseline. No evaluator conflict was found.

## INFERENCES
Docker Desktop being stopped explains the missing engine pipe in this recovery. Restoring it is sufficient for the observed readiness checks. This does not establish model reasoning, JSON action fidelity, task correctness or product readiness.

## UNKNOWNS
Stage 1 compatibility, schema/finish fidelity, string bounds and T10 action semantics are still untested. Historical model digest equality and effective generation-ceiling enforcement are not independently measured. No model response fingerprint beyond live build_info was elicited.

## FINAL READINESS DECISION
READY_FOR_STAGE_1

Environment recovery is complete. STOP. Stage 1 model tests, JSON adapter execution, T10 replay and generated-code execution did not occur. Explicit approval is still required before Stage 1. This recovery does not authorize production migration.
