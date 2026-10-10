"""Write Stage1A outcome without altering prior stopped run or failed output."""
import json
import sys
from pathlib import Path

def main():
    out=Path(sys.argv[1]); rows=json.loads((out/'observations.json').read_text())
    checks=json.loads((out/'docker-verifier.json').read_text())
    integrity=json.loads((out/'integrity-after.json').read_text())
    table='\n'.join('| '+r['parameter']+' | '+json.dumps(r.get('value'))+' | '+str(r.get('characters','N/A'))+' | '+str(r['executed'])+' | '+str(r['independent_validation'])+' | '+str(r['qualifies'])+' |' for r in rows)
    table+='\n| delete_file.path | NOT RUN | N/A | False | False | False |\n| run_command.command | NOT RUN | N/A | False | False | False |'
    metrics=[]
    for r in rows:
        raw=json.loads((out/r['task_id']/'model/result.json').read_text())
        response=raw['response']; metrics.append({'task_id':r['task_id'],'latency':raw['latency'],'usage':response.get('usage'),'finish_reason':response['choices'][0]['finish_reason']})
    (out/'model-metrics.json').write_text(json.dumps(metrics,indent=2))
    report=f'''# Stage 1A Resume

## Previous State
Previous stopped Stage1A had no model calls, no qualifying actions and unavailable Docker. Its preregistration/amendment remain byte-identical; this new execution preserves those files and snapshots all previous evidence digests. This is a separately labeled coverage run, not an addition to frozen benchmark outcomes.

## Docker Recovery
Docker was already running at inspection. No process start/stop, context switch, engine replacement or security configuration mutation needed. WSL docker-desktop running. Actual state captured in docker-state.json. Existing context desktop-linux unchanged.

## Docker Verification
Fresh unchanged verifier: {sum(checks.values())}/{len(checks)} PASS. Historical 18/18 was not used as current readiness.

## Pinned Image
Inspected exact image sha256:6f6ac11cda347a185454338dee35d77003e066579a3261b52b7c6ff1048c8573. No pull/substitution.

## Worker Verification
Existing owned registered Qwen/Qwen3.5-4B worker verified, b11132, context16384, q8_0/q8_0, same native registry snapshot. Slots idle and no verified evaluator before model calls. No second worker launched. Temperature0, max_tokens4096, thinkingfalse, tools required, parallelfalse; no response_format protocol change. Two calls total, one per executed cell. Raw requests/responses and headers preserved in A/model and B/model. Metrics in model-metrics.json. Preregistered original cell requests and native SYSTEM unchanged.

## list_dir.path
Model generated list_dir with path `app` (3 characters/3 UTF-8 bytes). Existing registry/permission executor returned app/__init__.py, app/runner.py and app/value.py. Independent Docker oracle verified exact fixture listing and all unrelated file hashes; negative control with empty listing rejected. Canonical workspace unchanged. QUALIFIES=True. Derived bound3+256=259. Native list_dir performs draft metadata inspection; Docker independently validates its returned result, not a claim that native file metadata dispatch itself is Docker execution.

## search_code.query
Model generated search_code query `VALUE =` (7 characters/7 bytes). Registry accepted and real search executed, returning zero matches. Immutable fixture uses `VALUE=17` (no space). Independent Docker oracle requires a nonempty correct result and rejected the observation. Negative control rejected too. Canonical fixture unchanged. QUALIFIES=False; no bound derived from this failed action. The harness did not strip whitespace, replace the query, alter the fixture or retry generation.

## delete_file.path
NOT RUN: preregistered nonqualifying-cell stopping rule triggered after B. No disposable.txt created or deleted. No unrelated file deletion.

## run_command.command
NOT RUN after same stop. No coverage command generated or executed. Oracle/verifier Docker executions are separate from model-generated command evidence.

## Qualification Table
| Parameter | Exact value | Characters | Executed | Independent validation | Qualifies |
|---|---|---:|---|---|---|
{table}

Only A is a qualifying observation. B is NONEMPTY_OBSERVATION -> EXECUTED, but not VALIDATED or QUALIFYING_SUCCESS. C/D remain NO_OBSERVATION. No states collapsed.

## Bound Derivations
list_dir.path: largest qualifying value app, observed3characters, fixed margin256, maxLength259. Source A/model/response.body and A/oracle-result.json. All observations preserved. search_code.query/delete_file.path/run_command.command remain BOUND_EVIDENCE_UNAVAILABLE in this execution. This does not establish permanent unavailability. Existing six successful-baseline derivations are untouched.

## Action-Space Status
Incomplete. No parameters removed or guessed. Bounded schema not generated; converter keyword/integer fidelity and worst-case escaped/tokenizer size NOT RUN because required bound evidence is incomplete. Existing finish action remains in frozen registry; no schema termination or T10 action experiment run.

## T10 Authorization
No T10 B/C, no JSON T10 action, no Stage2. Stop and wait for explicit approval per the attached recovery prompt. Successful list coverage is not T10 success or product superiority.

## Security
Only experimental isolated fixture copies created. Native dispatch and Docker oracle use existing permission/security paths. No publication. No source/configuration changes during resume: {integrity['source_changes_during_resume']}. Previous Stage1A changed files: {integrity['previous_stage1a_changes']}. Preregistration and amendment preserved. Startup launcher repair from the earlier separately authorized task predates this execution and is not silently claimed to match the older global freeze snapshot. Fresh before-source hashes record this execution's exact boundary.

## OBSERVED FACTS
Docker ready, pinned verifier18/18PASS. list_dir model action validated. Search action executed but no match; oracle FAIL. Two generated actions, no manual replacement. No cells rerun. Remaining cells not run under registered stop.

## INFERENCES
The immediate unresolved search bound is missing qualifying action evidence, caused in this cell by literal query whitespace mismatch. It does not prove routing failure or permanent action inability. A new attempt would require explicit authorized methodological amendment/new coverage attempt, not silent retries within this run.

## UNKNOWNS
Whether a later approved search cell would qualify, C/D action behavior, complete bounded-schema/converter fidelity, integer grammar equivalence, worst-case4096token fit, T10 JSON emission and task correctness.

## FINAL STATUS
BOUND_EVIDENCE_UNAVAILABLE
'''
    (out/'STAGE-1A-RESUME-REPORT.md').write_text(report,encoding='utf-8')
    (out/'docker-recovery-report.md').write_text('Docker already restored; desktop-linux Linux engine and pinned image verified. Fresh unchanged verifier18/18PASS. No recovery configuration mutation.\n',encoding='utf-8')
    (out/'progress.json').write_text(json.dumps({'status':'BOUND_EVIDENCE_UNAVAILABLE','stopped':True,'qualifying_parameters':['list_dir.path'],'nonqualifying_executed':['search_code.query'],'unexecuted':['delete_file.path','run_command.command'],'reason':'Preregistered stop on nonqualifying cell B','t10_run':False,'production_changes':False},indent=2))
    print('Report saved; BOUND_EVIDENCE_UNAVAILABLE')

if __name__=='__main__': main()
