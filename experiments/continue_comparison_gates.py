"""Resumable experiment scheduling, never production task orchestration."""
import json
from pathlib import Path
import subprocess
import sys
import time
import psutil
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'benchmarks/model-comparison'

def counts():
    return {m:sum(1 for p in (OUT/'fixed-40'/m).glob('*.json')
                  if 'result' in json.loads(p.read_text()))
            for m in ('coder','granite','mini-coder','qwen3.5')}

def checkpoint(stage,**details):
    path=OUT/'gate-progress.json'
    record={'stage':stage,'coverage':counts(),'production_modified':False,**details}
    temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(record,indent=2));temporary.replace(path)

def run(command,name):
    with (OUT/(name+'-stdout.log')).open('a') as out,(OUT/(name+'-stderr.log')).open('a') as err:
        child=subprocess.Popen(command,cwd=ROOT,stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
        checkpoint(name,child_pid=child.pid)
        return child.wait()

def main():
    active=json.loads((OUT/'active-run.json').read_text())
    pid=active.get('pid')
    checkpoint('WAITING_FOR_EXISTING_MODEL_COMPARISON',existing_pid=pid)
    while pid and psutil.pid_exists(pid):
        try:
            if 'model_compatibility.py' not in ' '.join(psutil.Process(pid).cmdline()):break
        except psutil.Error:break
        checkpoint('WAITING_FOR_EXISTING_MODEL_COMPARISON',existing_pid=pid)
        time.sleep(5)
    # Resume only missing pairs. Existing completed outcomes are never discarded.
    for attempt in range(3):
        if all(n==40 for n in counts().values()):break
        checkpoint('RECOVERING_MISSING_PAIRS',recovery_attempt=attempt+1)
        run([active['python_executable'],'experiments/model_compatibility.py','--tasks'],'model-resume')
    if not all(n==40 for n in counts().values()):
        checkpoint('ENVIRONMENT_BLOCKED_INCOMPLETE_MODEL_COVERAGE');return
    old_python=str(ROOT/'.app-venv/Scripts/python.exe')
    for attempt in range(3):
        finished=sum(1 for p in (OUT/'old-workflow').glob('*.json') if 'status' in json.loads(p.read_text()))
        if finished==40:break
        run([old_python,'experiments/old_workflow_control.py'],'old-workflow-control')
    finished=sum(1 for p in (OUT/'old-workflow').glob('*.json') if 'status' in json.loads(p.read_text()))
    if finished != 40:
        checkpoint('OLD_CONTROL_ENVIRONMENT_BLOCKED',old_workflow_coverage=finished);return
    # Supplemental validation retains every original trajectory and outcome.
    # It is a candidate replay, not an estimate of repair with stronger feedback.
    replay_code=run([old_python,'experiments/supplemental_oracle_replay.py'],'oracle-v2-replay')
    if replay_code:
        checkpoint('SUPPLEMENTAL_REPLAY_ENVIRONMENT_BLOCKED',exit_code=replay_code);return
    audit_code=run([old_python,'experiments/trajectory_audit_pack.py'],'trajectory-audit-pack')
    analysis_code=run([old_python,'experiments/comparison_analysis.py'],'paired-analysis')
    checkpoint('EXECUTIONS_AND_REPLAY_COMPLETE_SEMANTIC_AUDIT_PENDING',
               old_workflow_coverage=finished,audit_pack_exit_code=audit_code,
               paired_analysis_exit_code=analysis_code,
               independent_semantic_signoff=False)

if __name__=='__main__':main()
