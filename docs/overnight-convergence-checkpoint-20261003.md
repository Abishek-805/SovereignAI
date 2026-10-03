# SovereignAI convergence checkpoint — 2026-10-03

Status: **IN PROGRESS. No production candidate selected.** This record is separate from the frozen historical benchmarks, held-out data and Phase D evidence. Branch: `codex/overnight-convergence`; baseline commit: `4f63cf6`.

## Observed local baseline

- Docker Desktop server responds with version 29.8.0. The running `llama-server.exe` at inspection time used `qwen2.5-coder-3b-instruct-q4_k_m.gguf`; one server process was visible. This is a point-in-time observation, not a continuous resource guarantee.
- Installed production GGUF files: Qwen2.5-Coder 3B, Qwen3.5 4B, Gemma 4 E2B, Qwen3.5 2B Vision, and legacy Qwen3 4B. mini-coder and Granite 4.2 are **not installed**.
- Phase D's independently probed semantic pass counts were A direct Coder 4/20, B existing Qwen→Coder 5/20, C grounded handoff 3/20, and R grounded handoff plus public repair feedback 3/20. The test family uses a correlated two-file skeleton, so these are local diagnostic outcomes, not a universal ranking. Broad Qwen planning and the new repair feedback were not promoted.
- The earlier 100-task hybrid fixture exists. Its raw final comparison is `STOPPED` after 163/600 rows (F100, E63). Do not treat provisional F-only counts as a paired scaffold result or restart/alter that frozen run.
- The existing 100-task authoring controls were rechecked without model inference: 85 reference implementations passed and 85 unfinished baselines failed; 15 cases require semantic review. This validates the old development fixtures only and does not satisfy the requested new 100-task benchmark.

## Upstream source screening

- [mini-SWE-agent's agent source](https://github.com/SWE-agent/mini-swe-agent/blob/main/src/minisweagent/agents/default.py) and [environment source](https://github.com/SWE-agent/mini-swe-agent/blob/main/src/minisweagent/environments/local.py) show a small action/observation loop with a linear message history. Its default shell capability is not SovereignAI's Docker policy; an isolated adapter must retain SovereignAI's admitted tools and sandbox.
- [Nanobot](https://github.com/HKUDS/nanobot) centers a small agent loop with optional tools/context. This is an architectural reference, not a reason to import its memory, channels or broad tool permissions.
- [OpenHands SDK](https://github.com/OpenHands/software-agent-sdk) separates agent conversations, workspaces, tools, events and server access. [OpenHands](https://github.com/OpenHands/OpenHands) consumes that SDK. The separation is useful for comparing coordination and execution, but the full SDK would change too many variables for the first scaffold test.
- [Cline](https://github.com/cline/cline) supplies another execution/coordination reference. Its IDE integration is outside this first controlled comparison.
- [RouteLLM](https://github.com/lm-sys/RouteLLM) implements learned routing on model-pair preference/cost data; its published configurations are not calibrated to SovereignAI's local workers. [RoRF](https://github.com/Not-Diamond/RoRF) uses random forests with embeddings and measured outcomes. An outcome-labelled local dataset is prerequisite to claiming either helps here.
- The [mini-coder-1.7B card](https://huggingface.co/ricdomolm/mini-coder-1.7b) reports training on agent trajectories and upstream SWE-bench results; neither is local compatibility or task-quality evidence. [Granite 4.2](https://github.com/ibm-granite/granite-4.2-language-models) documents integrated reasoning/tool calling, also without local evidence. [FunctionGemma](https://huggingface.co/google/functiongemma-270m-it) is a specialized function-calling candidate, not an off-the-shelf general router.

## Experiment order and gates

1. Freeze a new development task manifest and oracle controls, including real project fixtures and explicit run-project, failure/repair and follow-up cases. Hash all raw inputs and protect hidden validation from model context. Do not inspect or tune against held-out data.
2. Hold the **same installed Coder model** fixed while comparing the current runner, a minimal action/observation runner, the existing Nanobot-inspired runner and an evidence-derived hybrid. Use the same admitted tools, Docker sandbox, validation and repair budget. Stop a variant early only with a recorded rule and evidence.
3. Only after scaffold comparison, test Qwen2.5-Coder 3B and Qwen3.5 4B on the selected fixed scaffold. Test mini-coder and Granite 4.2 only after verifying an exact locally runnable quantization, runtime compatibility, license and hardware fit; keep candidates out of production.
4. Build outcome-labelled router examples from paired validated tasks. Compare fixed, current and lightweight CPU methods on the same model pool, with task-level holdout and routing latency. Do not train on model self-scores or fabricate missing counterfactuals.
5. Keep chat latency separate from agent completion. Run independent live demonstrations and regression/security checks before any production change. A result is PASS only after the requested behavior is validated; tool rejection, missing Docker execution and incomplete repair remain distinct states.

Current gate: **step 1 not complete**. No new model, runner, router or production code was installed or changed in this checkpoint.

An hourly thread heartbeat named `SovereignAI overnight convergence` has been created to resume the work from this checkpoint. It should stay quiet during ordinary progress and notify only on completion, material failure or needed user action. The heartbeat is continuity, not evidence that the experiments have finished.
