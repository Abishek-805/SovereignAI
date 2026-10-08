"""Persist honest gate-stop report and frozen-evidence integrity audit."""
import hashlib
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]

def main():
    out=Path(sys.argv[1]); base=out.parent
    manifest=json.loads((base.parent/'manifest.json').read_text(encoding='utf-8'))
    changes=[name for name,digest in manifest['frozen_sha256'].items() if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest]
    integrity={'checked_files':len(manifest['frozen_sha256']),'changed_files':changes,'preregistration_sha256':hashlib.sha256((base/'PREREGISTRATION.md').read_bytes()).hexdigest(),'generated_action_executions':0,'new_completion_requests':2}
    (out/'integrity.json').write_text(json.dumps(integrity,indent=2))
    coverage=json.loads((out/'baseline-coverage.json').read_text()); cases=json.loads((out/'registry-parser-cases.json').read_text()); bounds=json.loads((out/'string-bounds.json').read_text())
    table='\n'.join('| '+row['parameter']+' | '+str(row['observations'])+' | '+str(row['largest_baseline_value']['chars'] if row['largest_baseline_value'] else 'UNKNOWN')+' | 256 | '+str(row['derived_maxLength'] if row['derived_maxLength'] else 'UNKNOWN')+' |' for row in bounds)
    report=f'''# Stage 1 — JSON-Constrained Action Adapter

STATUS: INCOMPLETE — STOPPED AT SCHEMA-FIDELITY / STRING-BOUND GATE.

## Objective
Determine whether changing only the generation protocol resolves native T10 action emission. No implementation, model or architecture superiority is established.

## Environment
Experimental namespace only. Production remains frozen; SOVEREIGN_AGENT_KERNEL=0. Evidence directory: `{out.name}`. Initial BLOCKED readiness.json was preserved; fresh readiness is in this execution directory and the earlier recovery directory.

## Runtime Verification
Registry-owned Qwen3.5-4B Q4_K_M worker PID 30072, b11132-633733d0a, context 16384, KV q8_0/q8_0, one slot. Idle before tests; no verified evaluator. Artifact SHA-256 00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4. Current argv matches the preserved replay. Historical replay lacked an artifact digest, so historical bitwise artifact equality is not established. Runtime props report n_predict=-1 despite launcher argument 8192; request output budget is 4096 throughout.

## Docker Verification
Pinned image sha256:6f6ac11cda347a185454338dee35d77003e066579a3261b52b7c6ff1048c8573. Existing verifier rerun: 18/18 PASS. This is sandbox readiness verification, not generated-candidate validation.

## Preregistration Hash
`{integrity['preregistration_sha256']}`. Created before the two completion calls, unchanged afterward. Manifest records scope and fixed margin. No post-result tuning or amendments.

## Structured-Output Compatibility
Minimal ok=true schema: HTTP 200, content `{{"ok": true}}`, finish=stop, 6 completion / 23 prompt tokens, 1.453 seconds. JSON shape and required constant satisfied.

Same request plus the first registered native tool: HTTP 400, `Failed to initialize samplers: failed to parse grammar`. This shows failure for this combined configuration, not total structured-output incompatibility. Intended JSON arms omit native tools/tool_choice. No GBNF fallback was required by the preregistration because schema-only worked. Raw requests, headers and response bodies are preserved in compatibility/{out.name}.

## Schema Generation
Programmatic extraction from SHA-verified frozen native ToolRegistry, all ten actions retained. Native request schemas in all inspected successful cells match extraction exactly. Unbounded tagged-action schema saved as action-schema-unbounded.json. This is an intermediate artifact, not a production adapter or approved bounded schema.

## Schema Fidelity
{len(cases)}/{len(cases)} parser-to-Registry.check cases passed: valid required/all fields, unknown action, missing required fields, incorrect types and prohibited extra fields. No dispatcher invoked. These checks establish only direct parser/registry compatibility. Converter fidelity and complete bounded action-space fidelity remain UNESTABLISHED. JSON Schema integer semantics versus Python integer checks require converter inspection before claiming equivalence.

## Finish-Action Fidelity
Existing `finish` action has empty argument object. It is included, parses and passes Registry.check. Frozen executor lines 337–340 route finish to existing validator; loop lines 395–399 stages READY_FOR_REVIEW only on independent validation PASS. No new termination path was invented. Grammar generation and loop termination through generated schema were not executed; no claim of observed termination.

## Converter Keyword Audit
NOT COMPLETED: run stopped on missing preregistered bound evidence. Registered parameter schemas contain type/properties/required/additionalProperties; generated tagging adds const/oneOf/nested objects. Integers and empty objects occur. Arrays, booleans, null, enum, allOf, anyOf, items, minima/maxima and pattern are absent in these native parameter schemas. Derived maxLength is not yet applied. Converter support is UNKNOWN, not assumed unsupported. No pinned-source claim is made.

## String-Bound Derivation
Scanned all preserved independently successful native/nanobot/hermes cells qualifying through nonempty all-true independent post-accept Docker oracle properties: {coverage['count']} cells. Selection and every source action are saved; emitted strings in successful trajectories were included conservatively even if an individual action failed. Other task cells without that independent success evidence cannot justify bounds.

| Parameter | Observations | Largest characters | Margin | Derived maxLength |
|---|---:|---:|---:|---:|
{table}

Missing observations: list_dir.path, search_code.query, delete_file.path, run_command.command. Optional omission of list_dir.path does not provide evidence for legitimate nonempty values. No limits were guessed, parameters removed, or strings truncated. Exact largest values and all source paths remain in string-bounds.json. Scope is preserved benchmark evidence, not arbitrary future tasks.

## Worst-Case JSON Size
NOT RUN: full bounds are undefined. Neither feasibility nor incompatibility with 4096 output tokens has been established. No tokenizer stress requests followed the gate failure. Reaching this gate would require escaped-size calculations plus actual tokenizer evidence; observed ordinary baseline lengths alone are insufficient.

## Arm A
Preserved historical exact T10 replay reused as reference only: streaming and nonstreaming finish=length, completion=4096, prompt=4051, 16486 prose characters, no raw/parsed tool call. Not rerun.

## Arm B
NOT RUN: prerequisite fidelity/bound gates failed. No request diff or action result exists.

## Arm C
NOT RUN: same prerequisite stop. State would be model-written with preregistered 512-character bound; no state was inserted, generated or corrected.

## T10 Action-Emission Analysis
Historical failure remains confirmed. Current minimal constrained JSON success does not demonstrate T10 action success. No new T10 action outcome is available.

## Action Classification
| Arm | Action Emitted | Parseable | Tool Valid | Args Valid | Action Correct | State Correct | Finish? | Finish Reason | Tokens | Latency |
|---|---|---|---|---|---|---|---|---|---|---|
| A historical | No | N/A | N/A | N/A | N/A | N/A | No | length | 4096 completion | See historical raw evidence |
| B | NOT RUN | NOT RUN | NOT RUN | NOT RUN | NOT RUN | N/A | NOT RUN | N/A | N/A | N/A |
| C | NOT RUN | NOT RUN | NOT RUN | NOT RUN | NOT RUN | NOT RUN | NOT RUN | N/A | N/A | N/A |

Minimal ok=true JSON is not an action and was not classified as one.

## State-Field Analysis
No Arm C state exists. State correctness, reservation arithmetic and semantic action selection remain untested.

## Token / Latency Results
Only minimal compatibility output measured: 6 completion tokens, 23 prompt, 1.453 seconds. Combined-tools request rejected; raw result records latency. No action-level token/latency comparison.

## Failure Taxonomy
Combined tools/response_format: RUNTIME/GRAMMAR rejection, root cause UNDETERMINED. Gate stop: HARNESS/EVIDENCE COVERAGE, incomplete string-bound derivation. Not ROUTER or MODEL_SELECTION. No T10 JSON generation failure was observed because no replay ran.

## Security Confirmation
No generated action dispatched, candidate code executed, permissions bypassed or changes published. Docker verifier uses existing safety checks only. Production/source/historical manifest integrity: {integrity['checked_files']} files checked, {len(changes)} changed. Initial readiness.json and preregistration were not rewritten. Previous Stage 1 report archived in this execution directory before replacing the report. JSON parsing and Registry.check do not authorize execution.

## OBSERVED FACTS
Minimal constrained JSON worked. Combined native tools plus schema failed. Registry mapping includes ten unchanged actions including finish. Four string fields have no usable successful baseline observations. Parser/registry examples passed; runtime grammar fidelity did not complete.

## INFERENCES
JSON-only generation is a viable compatibility candidate for further diagnostics. Full fidelity cannot be claimed under the required baseline-derived bound policy. This is a missing-evidence stop, not proof that JSON actions or Qwen are incapable.

## UNKNOWNS
Converter keyword fidelity, integer grammar semantics, complete size bounds, worst-case token fit, T10 B/C emission/argument/state correctness, implementation/oracle success, universal reliability and production benefit.

## DISPROOF STATUS
T10 protocol hypothesis neither proved nor disproved. Combined native-tools compatibility failed for the tested configuration only. The full registered bounded space has not passed readiness for replay.

## RECOMMENDATION
Keep production unchanged. Any continuation needs an explicit preregistered amendment resolving bounds for the four unobserved fields, while retaining legitimate actions and the frozen output budget. Do not silently substitute arbitrary bounds or shrink the registry. Converter and token-budget checks must precede T10 replay. Stage 2 remains unauthorized.

## Required Questions A–P
A: Yes for the minimal tested schema; general action-schema fidelity unknown.
B: Extracted registry names/parameters match; bounded grammar fidelity unestablished.
C: Yes, finish with empty arguments.
D: Existing termination mapping exists; generated-schema termination not run.
E: Unknown; four bounds undefined.
F–G: Not run.
H: Unknown.
I–L: No new T10 action to assess.
M–N: No model-written state generated.
O: Not established.
P: All unresolved gates and task-level correctness listed above.

## Confirmation That No Action Was Executed
Generated-action execution count: 0. New compatibility completion calls: 2. T10 B/C calls: 0. Stage 2 calls: 0. STOPPED per the user's schema-fidelity/evidence stopping rule.
'''
    (base/'STAGE-REPORT.md').write_text(report,encoding='utf-8')
    (out/'STAGE-REPORT.md').write_text(report,encoding='utf-8')
    (out/'progress.json').write_text(json.dumps({'status':'INCOMPLETE','stopped':True,'reason':'Missing independently successful baseline values for four registered string parameters','stage':1,'t10_replay':False,'stage2':False,'production_changes':changes},indent=2))
    print(json.dumps(integrity,indent=2))

if __name__=='__main__': main()
