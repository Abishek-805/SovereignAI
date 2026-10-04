"""Docker-only checks that new oracles reject unfinished implementations."""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from experiments.comparison_extra_tasks import cases
from experiments.kernel_docker import DockerCommands

def main():
    out=ROOT/'benchmarks/model-comparison/oracle-controls'
    out.mkdir(parents=True,exist_ok=True)
    docker=DockerCommands(ROOT,out/'docker-tasks')
    records=[]
    for case in cases():
        destination=out/(case['id']+'.json')
        if destination.exists():
            records.append(json.loads(destination.read_text()))
            continue
        files=case['starting_files']
        if case['category']=='run_project':
            result=docker(case['expected_command'],files,60)
            accepted=result['docker_executed'] and result['exit_code']==0 and result['stdout']==case['expected_stdout']
        else:
            result=docker('python -m unittest discover -p test_contract.py',
                         {**files,'test_contract.py':case['private_test']},60)
            accepted=result['docker_executed'] and result['exit_code']!=0 and 'NotImplementedError' in result['stderr']
        row={'task_id':case['id'],'control_passed':accepted,'result':result,
             'control_type':'documented_run' if case['category']=='run_project' else 'unfinished_candidate_rejected',
             'not_model_completion_evidence':True}
        destination.write_text(json.dumps(row,indent=2))
        records.append(row)
        print(case['id'],accepted,flush=True)
        if not accepted:raise RuntimeError('Oracle control failed: '+case['id'])
    (out/'summary.json').write_text(json.dumps({'controls':len(records),'all_passed':all(r['control_passed'] for r in records)},indent=2))

if __name__=='__main__': main()
