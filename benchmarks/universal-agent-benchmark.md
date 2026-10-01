# Frozen Universal Task Agent comparison

The 128 engineer-authored tasks cover 16 categories with eight distinct requests
each. They are realistic fixtures, not independent held-out user measurements.
The fixture source documents and coding projects are synthetic and isolated.

Strategies use the same existing Workbench flows and runtime settings:

- A: `fixed` routing, reasoning text worker and coding specialist.
- B: `always_reasoning`, reasoning worker for nonvisual model work.
- C: `universal`, software task agent and role broker.

The strategy affects worker selection; no second model is preloaded. Tool-only
calculations remain tool-only. Worker-selection accuracy uses the declared policy
of each strategy. Task intent and mathematical expectations remain common.

```powershell
# Run only when the application's inference runtime is idle/stopped and the
# coordinating parent has authorized the model lifecycle.
.app-venv/Scripts/python.exe benchmarks/evaluate-universal-agent.py --mode live --allow-model-lifecycle --sample-resources --strategies A B C --timeout 120 --output benchmarks/universal-live-comparison.json

# Quick actual arithmetic acceptance; incomplete-suite coverage is explicit.
.app-venv/Scripts/python.exe benchmarks/evaluate-universal-agent.py --mode live --allow-model-lifecycle --strategies C --categories calculator --timeout 120 --output benchmarks/universal-live-calculator.json

# Replay existing capture lists; replay does not execute models or tools.
.app-venv/Scripts/python.exe benchmarks/evaluate-universal-agent.py --mode replay --captures A=path/to/A-captures.json --captures B=path/to/B-captures.json --captures C=path/to/C-captures.json --output benchmarks/universal-replay.json
```

Unset `SOVEREIGN_KNOWLEDGE_DIR` before live runs. An environment override that could
write to user Knowledge is rejected. Each strategy uses a temporary data/project
root; each coding case gets a fresh workspace. Sources are imported from the
fixture. The runner never Accepts or publishes generated changes. The existing
broker may load/switch installed models only with the explicit CLI opt-in.

The timer sets the real cancellation event at the deadline; interruption depends
on existing cooperative model/tool checkpoints. Environment errors, cancellation
and execution errors are reported separately. Partial reports are saved after
every case, retaining failures rather than retrying the entire benchmark blindly.

Success is checked only where a narrow independent fixture oracle exists:
arithmetic values, source-backed facts, structured table results, cancellation,
and unchanged fixture-owned unit tests. Generated model assertions cannot certify
success. Validated staged code is recorded as an artifact check and does not count
as published task completion. General and visual semantic judgments remain unknown
until independently reviewed. Missing security/proposal telemetry also remains
unknown; zero observed unsafe proposals is never inferred from absent data.

Optional resources are sampled approximately once per second. RAM is the sum of
benchmark Python and all llama-server resident-set sizes, not exclusive private
allocation. VRAM is total device memory reported by `nvidia-smi`, not exclusive
model attribution. Process counts are conservative observations of all llama
servers. Very short tasks may be missed between samples. Unavailable observations
stay null. Counters preserve the existing supervisor's definitions.

This harness reports separate metrics and coverage. It does not manufacture a
single quality score, claim C is superior, certify a release, or replace live
publication/browser/resource-pressure acceptance tests.
