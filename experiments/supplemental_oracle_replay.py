"""Versioned candidate-only Docker replay; never overwrites frozen outcomes.

This does not estimate repair success under the stronger oracle. A new worker
evaluation would be a different, explicitly labeled experiment.
"""
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from experiments.kernel_docker import DockerCommands
from experiments.old_workflow_control import private_oracles
from experiments.oracle_supplements import supplemental_test

def main():
    base=ROOT/'benchmarks/model-comparison'
    tasks={t['task_id']:t for t in json.loads((base/'frozen-40-task-manifest.json').read_text())}
    oracles=private_oracles()
    out=base/'oracle-v2-replay';out.mkdir(parents=True,exist_ok=True)
    docker=DockerCommands(ROOT,out/'docker-tasks')
    for model in ('coder','granite','mini-coder','qwen3.5','old-workflow'):
        source=base/'old-workflow' if model=='old-workflow' else base/'fixed-40'/model
        dest=out/model;dest.mkdir(exist_ok=True)
        for task_id, task in tasks.items():
            path=source/(task_id+'.json');destination=dest/(task_id+'.json')
            if destination.exists():continue
            if not path.exists():raise RuntimeError('Missing original execution '+str(path))
            raw=json.loads(path.read_text())
            files=raw['candidate'] if model=='old-workflow' else raw['result']['files']
            source_text=oracles[task_id]+'\n'+supplemental_test(task_id)
            result=docker('python -m unittest discover -p test_contract.py',
                         {**files,'test_contract.py':source_text},60)
            omissions=sorted(set(task['starting_files'])-set(files)) if task_id.startswith(('cp','rp')) else []
            if omissions and result['exit_code']==0:
                result.update(exit_code=1,stderr='Missing required original project files: '+', '.join(omissions))
            original_status=raw['status'] if model=='old-workflow' else raw['result']['state']
            report_check=None
            if task_id.startswith('rp'):
                from experiments.comparison_extra_tasks import cases
                case=next(c for c in cases() if c['id']==task_id)
                if model=='old-workflow':
                    final_text=(raw.get('result') or {}).get('answer','')
                    observations=raw['sandbox_executions']
                    observed=any(e.get('executed') and e.get('exit_code')==0 and e.get('stdout')==case['expected_stdout'] and case['expected_command'] in e.get('code','') for e in observations)
                else:
                    events=raw['result']['events']
                    final_text=next((e['action'].get('reason','') for e in reversed(events) if e.get('action',{}).get('action')=='finish'),'')
                    observed=any(e.get('action',{}).get('command')==case['expected_command'] and e.get('observation',{}).get('exit_code')==0 and e['observation'].get('stdout')==case['expected_stdout'] for e in events)
                report_check=case['expected_stdout'].strip() in final_text
                if not observed or files!=task['starting_files'] or not report_check:
                    result.update(exit_code=1,stderr='Run/report contract not fully established: command/output, unchanged files, and final report output required')
            row={'model':model,'task_id':task_id,'oracle_version':'v2-supplemental-candidate-replay',
                 'original_status':original_status,'original_raw_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                 'oracle_sha256':hashlib.sha256(source_text.encode()).hexdigest(),'validation':result,
                 'status':'PASS' if result['docker_executed'] and result['exit_code']==0 else 'FAIL',
                 'missing_required_files':omissions,'final_report_output_check':report_check,
                 'does_not_measure_worker_repair_with_v2_feedback':True}
            destination.write_text(json.dumps(row,indent=2))
            print('oracle-v2',model,task_id,row['status'],flush=True)

if __name__=='__main__':main()
