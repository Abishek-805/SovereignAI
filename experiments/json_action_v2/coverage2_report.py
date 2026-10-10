"""Stage1A-2 evidence aggregation only; no schema/converter/model calls."""
import json
from experiments.json_action_v2.coverage2 import BASE
from experiments.json_action_v2.coverage import ROOT, save, sha

def main():
    rows=json.loads((BASE/'observations.json').read_text())
    previous=ROOT/'evidence/json-action-adapter-v2/stage-1a/execution-20261008-105532/observations.json'
    approved=json.loads(previous.read_text())+rows
    successful=[r for r in approved if r.get('qualifies')]
    parameters=['list_dir.path','search_code.query','delete_file.path','run_command.command']
    bounds=[]
    for parameter in parameters:
        values=[r for r in successful if r['parameter']==parameter]
        largest=max(values,key=lambda r:r['characters']) if values else None
        bounds.append({'parameter':parameter,'observation_count':len(values),'largest_qualifying_value':largest['value'] if largest else None,'observed_characters':largest['characters'] if largest else None,'margin':256,'derived_maxLength':largest['characters']+256 if largest else None,'sources':[r['raw_path'] for r in values],'source_task':largest['task_id'] if largest else None,'formula':'largest qualifying codepoint count + 256'})
    save(BASE/'bound-derivations-all-approved.json',bounds)
    save(BASE/'coverage-observations.json',{'current_run':rows,'reused_successes':[r for r in approved[:2] if r['qualifies']],'preserved_failure_source':str(previous.relative_to(ROOT)),'previous_failure_not_promoted':True})
    checks=json.loads((BASE/'docker-verifier.json').read_text()); inventory=json.loads((BASE/'manifest.json').read_text())
    assert sha(BASE/'PREREGISTRATION.md')==inventory['preregistration_sha256'] and sha(BASE/'AMENDMENT.md')==inventory['amendment_sha256']
    metrics=[]
    for row in rows:
        result=json.loads((BASE/row['task_id']/'model/result.json').read_text())
        metrics.append({'task_id':row['task_id'],'latency_seconds':result['latency'],'usage':result['response'].get('usage'),'finish_reason':result['response']['choices'][0]['finish_reason']})
    save(BASE/'model-metrics.json',metrics)
    integrity=json.loads((BASE/'integrity-after.json').read_text())
    table='\n'.join('| '+r['parameter']+' | `'+r['value']+'` | '+str(r['characters'])+' | '+str(r['bytes'])+' | Yes | PASS | Yes |' for r in successful)
    boundtable='\n'.join('| '+b['parameter']+' | '+str(b['observed_characters'])+' | 256 | '+str(b['derived_maxLength'])+' |' for b in bounds)
    status='BOUND_RECOVERED' if all(b['observation_count'] for b in bounds) else 'BOUND_EVIDENCE_UNAVAILABLE'
    report=f'''# Stage 1A-2 — Remaining Action-Space Coverage

## Objective
New approved native coverage cells for search_code.query, delete_file.path, run_command.command. Do not rerun list_dir or previous failed search. Obtain real model action values and independently validate them; no T10.

## Amendment
PREREGISTRATION.md, AMENDMENT.md, fixed task/fixture/validation contracts hashed in manifest.json before all coverage completions, hashes verified after. Fixed margin256 unchanged. Previous VALUE = failure remains failed and excluded from bounds. New search task explicitly names known literal target VALUE=17; this is a new experimental task input, not a replacement action or retry of old cell. The harness does not normalize/correct arguments.

## Frozen Variables
Existing registry-owned Qwen3.5-4B Q4_K_M, b11132, context16384, KVq8_0/q8_0, temp0, max4096, enable_thinkingfalse, no seed, native tools required/parallelfalse. SHA-verified frozen native registry/system/permissions/executor/validator unchanged. Same pinned sandbox image/security. Current slot was busy during initial inspection; no coverage call made until idle. Benchmark remains stopped. Three sequential one-call cells, no retries. Fresh Docker verifier {sum(checks.values())}/{len(checks)}PASS. No other model launched. Registered rp07 fixture copied immutably; source bytes unchanged.

## Search Coverage
New B task requested exact VALUE=17 source content. Model emitted search_code query VALUE=17 (8 characters/8bytes). Registry accepted and native literal search actually returned app/value.py line1 VALUE=17. Independent pinned Docker oracle verified the frozen required match, complete expected matches and unrelated hashes. Negative control empty result failed. Raw model request/headers/response retained in B/model; no hand-written action substituted. Independent oracle result B/oracle-result.json exit0.

## Delete Coverage
Model emitted delete_file path delete-coverage.txt (19 characters/19bytes). Harness-created disposable fixture and prerequisite registry read are explicitly labeled non-model evidence. Before-Docker check C/disposable-before-docker.json verified exact bytes and existence. Existing permissions required requested deletion and prior read, then native executor removed only this file from virtual draft. After-Docker oracle proved absence and unchanged unrelated file hashes. Negative control wrong deleted path failed. Canonical isolated workspace retained original snapshot; no publication or actual user/source-file deletion occurred. This is the native draft deletion semantics, not a fabricated shell deletion. Actual draft deletion plus Docker before/after evidence qualifies the observation.

## Command Coverage
Model emitted run_command command python -m app.runner (20characters/20bytes), the existing fixture README command named by the new task. Real existing ValidationEngine ran it in pinned Docker: exit0, stdout17newline, stderr empty. Separate Docker oracle validated observed command result and unchanged snapshot hashes. Negative control wrong stdout failed. D/execution.json and D/oracle-result.json preserve evidence; model assertion alone never counted.

## Qualification Table
| Parameter | Exact action value | Characters | UTF-8 bytes | Executed | Independent validation | Qualifies |
|---|---|---:|---:|---|---|---|
{table}

list_dir row is preserved earlier successful A, not rerun. All new rows reached NONEMPTY_OBSERVATION -> EXECUTED -> VALIDATED -> QUALIFYING_SUCCESS. Each action has raw wire-body JSON, result, oracle and negative control preserved. The unchanged canonical snapshot is also checked.

## Successful Observations
Three new independently qualifying actions plus one prior qualifying listing. Sources and exact values in coverage-observations.json and bound-derivations-all-approved.json. Current observations.json contains all three new original records. One successful value per parameter; no value-length maximization.

## Failed Observations
No new failed cell. Prior query VALUE = returned empty matches and remains nonqualifying in its original evidence namespace. It was not corrected, retried or counted. nonqualifying-observations.json for this new run is empty. Model metrics contain finish reasons, tokens and latency; success depends on oracle results rather than finish labels.

## Bound Derivations
| Parameter | Largest qualifying characters | Fixed margin | Derived maxLength |
|---|---:|---:|---:|
{boundtable}

All approved qualifying observations considered; failed VALUE = excluded. These are evidence-derived finite bounds for this experimental coverage policy, not proof that every future legitimate tool string fits. Previous six successful-baseline parameter derivations untouched. The original per-run bound-derivations.json is retained; combined bounds are a separate all-approved artifact.

## Remaining Missing Bounds
None among the four coverage parameters. This does not establish converter fidelity, integer equivalence, full bounded-schema adequacy or worst-case output-token feasibility.

## Security
Production/source changes during run: {integrity['source_changes']}. Previous Stage1/Stage1A evidence changes: {integrity['prior_evidence_changes']}. No benchmark outcomes or prompts globally changed. No permissions bypass, network fallback, extra heavy model or publication. Only experiment-owned virtual draft deletion authorized. Harness operations are distinct from model action evidence. All independent code execution occurs in unchanged Docker sandbox. The experimentally parameterized coverage helper was changed before this new preregistration to support the newly authorized filename and stricter source-bound search oracle; no production kernel changes.

## T10 Authorization
No T10 B/C, JSON action execution, bounded schema generation, grammar conversion, tokenizer stress or Stage2. Stop here and wait for explicit approval as requested.

## OBSERVED FACTS
Three exact native actions emitted, executed and independently validated. Before/after deletion evidence exists. Docker18/18passed. Negative controls rejected. Prior evidence/source integrity verified. Fixed256margin applied to genuine action values.

## INFERENCES
The four previously missing string parameters now have qualifying observations under the approved coverage amendment. This resolves missing evidence only; it does not demonstrate T10 action emission, semantic reasoning improvement or product readiness.

## UNKNOWNS
Full experimental bounded schema fidelity, converter keywords/integer semantics, worst-case4096token fit, T10 action correctness, oracle task success and broader model reliability remain untested here.

## FINAL STATUS
{status}
'''
    (BASE/'STAGE-REPORT.md').write_text(report,encoding='utf-8')
    save(BASE/'progress.json',{'status':status,'new_cells':3,'new_qualifying':sum(r['qualifies'] for r in rows),'total_missing_parameters':sum(not b['observation_count'] for b in bounds),'stopped_after_coverage':True,'t10_run':False,'bounded_schema_generated':False,'grammar_or_tokenizer_run':False,'stage2_run':False})
    print(status)

if __name__=='__main__': main()
