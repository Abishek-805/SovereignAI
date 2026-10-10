"""Record Stage1A readiness stop without model calls or recovery mutation."""
import hashlib
import json
import subprocess
from pathlib import Path
from experiments.json_action_v2.coverage import BASE, ROOT, TASKS

def main():
    def save(name,value): (BASE/name).write_text(json.dumps(value,indent=2),encoding='utf-8')
    docker=subprocess.run(['docker','--host','npipe:////./pipe/dockerDesktopLinuxEngine','info','--format','{{.OSType}}'],capture_output=True,text=True)
    save('environment-blocker.json',{'status':'BLOCKED','category':'ENVIRONMENT/SANDBOX','stage':'pre-execution Docker verifier','command':docker.args,'exit_code':docker.returncode,'stdout':docker.stdout,'stderr':docker.stderr,'error':'sandbox_unavailable: Docker Linux engine or pinned image is unavailable','completion_calls':0,'coverage_action_dispatches':0,'fixture_workspaces_created':0,'recovery_attempted':False})
    prior=json.loads((BASE/'evidence-inventory.json').read_text())
    previous_changes=[p for p,d in prior['previous_stage1_sha256'].items() if hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=d]
    manifest=json.loads((ROOT/'evidence/json-action-adapter-v2/manifest.json').read_text())
    changes=[p for p,d in manifest['frozen_sha256'].items() if hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=d]
    save('integrity.json',{'previous_stage1_checked':len(prior['previous_stage1_sha256']),'previous_stage1_changed':previous_changes,'historical_production_checked':len(manifest['frozen_sha256']),'historical_production_changed':changes,'preregistration_unchanged':hashlib.sha256((BASE/'PREREGISTRATION.md').read_bytes()).hexdigest()==prior['preregistration_sha256'],'amendment_unchanged':hashlib.sha256((BASE/'AMENDMENT-TO-BOUND-POLICY.md').read_bytes()).hexdigest()==prior['amendment_sha256']})
    observations=[{'parameter':name+'.'+key,'task_id':identity,'action':None,'nonempty':None,'executed':False,'independent_validation':False,'qualifies':False,'reason':'NOT_RUN: Docker unavailable before model generation'} for identity,name,key,_ in TASKS]
    save('observations.json',observations); save('nonqualifying-observations.json',observations)
    save('bound-derivations.json',[{'parameter':r['parameter'],'observation_count':0,'maxLength':None,'status':'BOUND_EVIDENCE_UNAVAILABLE','margin':256} for r in observations])
    save('converter-audit.json',{'status':'NOT_RUN','reason':'Coverage readiness failed; no bounded schema generated'})
    save('json-size-analysis.json',{'status':'NOT_RUN','reason':'Required bounds remain undefined; no budget conclusion'})
    report=f'''# Stage 1A — Action-Space Coverage

Execution status: BLOCKED / ENVIRONMENT. Final bound status: BOUND_EVIDENCE_UNAVAILABLE.

## Objective
Obtain independently validated, genuine action values for four missing native registry string parameters. No T10 replay, benchmark changes or production changes.

## Amendment
Preregistration and amendment created and hashed before execution. Hashes in evidence-inventory.json. Margin remains 256. Bounds require raw model-generated native registry action, permission-path execution and independent Docker oracle PASS. Harness-created fixtures and read prerequisites cannot count as model evidence.

## Evidence Sources
Previous Stage1 is actually under stage-1/execution-20261008-045947 (the attachment omitted stage-1 in one path). Previous successful-baseline scan remains the source confirming four missing parameters. Existing rp07 fixture from experiments/comparison_extra_tasks.py contains an app directory, documented python -m app.runner command and expected stdout17. Its immutable content, source digest and the proposed disposable-file addition were registered before execution. No coverage workspace or disposable deletion target was materialized because Docker preflight failed first.

## list_dir.path
NOT RUN. Existing copied-fixture target app planned; no genuine emitted action or independent validation.

## search_code.query
NOT RUN. Existing fixture VALUE assignment planned as useful verifiable search target. No action value substituted.

## delete_file.path
NOT RUN. Only planned target disposable.txt, experiment-owned fixture addition. No file created/deleted, no real project data touched. Fixture registration is not successful action evidence.

## run_command.command
NOT RUN. Existing fixture documents python -m app.runner, expected output17. No generated command executed.

## Qualification Results
| Parameter | Action | Nonempty | Executed | Independent Validation | Qualifies |
|---|---|---|---|---|---|
| list_dir.path | Not generated | Unknown | No | No | No |
| search_code.query | Not generated | Unknown | No | No | No |
| delete_file.path | Not generated | Unknown | No | No | No |
| run_command.command | Not generated | Unknown | No | No | No |

## Non-Qualifying Evidence
Registered fixture inputs and runtime metadata are not model-success evidence. Neither planned action strings nor Registry.check-only results qualify. Four unexecuted cells preserved in observations/nonqualifying-observations.json.

## Bound Derivations
All four remain BOUND_EVIDENCE_UNAVAILABLE. No maximum guessed. Original six baseline-derived bounds remain unchanged. No bounded schema was generated.

## Action-Space Completeness
No action removed. Registered coverage design uses all ten unchanged frozen native schemas. Coverage evidence incomplete, so full bounded action-space readiness is unestablished.

## Finish Action
Prior evidence preserves existing empty-arguments finish mapping. No generated finish or termination test in this run.

## Converter Fidelity
NOT RUN. No claim of converter compatibility or incompatibility. Coverage preflight failed before the required bounded-schema prerequisite.

## Worst-Case JSON Size
NOT RUN. Undefined bounds prevent complete calculation. No claim of fitting or exceeding4096tokens. Context/KV/output budget unchanged.

## T10 Authorization Status
T10 B/C remains unauthorized and unrun. Stage2 unrun. No JSON T10 action executed.

## Security
Docker verifier failed at its initial existing _ready check: Linux engine named pipe missing. Repeated read-only docker info captured the same error (exit {docker.returncode}). No Docker containers or model completions were started. No recovery mutation attempted after the registered stopping condition. Current /props was read, slots were idle and evaluator not verified running before failure. Previous Stage1 files checked: {len(prior['previous_stage1_sha256'])}, changed: {len(previous_changes)}. Historical/production files checked: {len(manifest['frozen_sha256'])}, changed: {len(changes)}. No publication, security weakening, benchmark mutation or production modification.

## OBSERVED FACTS
The expected model endpoint answered metadata requests. Docker Linux engine was unavailable; verifier could not run18checks. Previous18/18PASS does not establish current readiness. Zero new qualifying observations, zero completion calls, zero coverage action dispatches.

## INFERENCES
The present blocker is environment readiness, not evidence of model/adapter failure. Native file tools inspect draft metadata; the registered design would independently verify results in Docker, without pretending native metadata dispatch itself is a Docker shell operation.

## UNKNOWNS
Whether any coverage action would be emitted/executed correctly, recovered bounds, complete converter fidelity, integer semantics and4096token worst-case fit. No new model behavior measured.

## HYPOTHESIS STATUS
Not tested. Readiness failed before model execution; no action success or failure inferred.

## RECOMMENDATION
Preserve this stopped run. Restore Docker readiness in a separately authorized recovery, verify the pinned image/safety and then resume only unexecuted coverage cells under the unchanged preregistration. Do not fabricate bounds or move to T10. The existing preregistration explicitly says stop if Docker unavailable; this stop follows that rule, not a model conclusion.

BOUND_EVIDENCE_UNAVAILABLE
'''
    (BASE/'STAGE-REPORT.md').write_text(report,encoding='utf-8')
    (BASE/'action-space-audit.md').write_text('Coverage incomplete: four parameters without qualifying values; no bounded schema, converter or size gate executed. See STAGE-REPORT.md.\n')
    save('progress.json',{'status':'BOUND_EVIDENCE_UNAVAILABLE','execution_status':'BLOCKED','cause':'ENVIRONMENT','stopped':True,'completion_calls':0,'actions_executed':0,'t10_run':False})
    print('BOUND_EVIDENCE_UNAVAILABLE; frozen changes',changes,previous_changes)

if __name__=='__main__': main()
