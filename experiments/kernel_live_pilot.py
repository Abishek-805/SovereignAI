"""One fixed-Coder pilot; never changes production or switches models."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from experiments.task_kernel import TaskRoot
from experiments.minimal_execution import MinimalKernel, TaskBudget
from experiments.kernel_docker import DockerCommands
from experiments.kernel_model import LocalWorker


def main():
    destination = ROOT/'benchmarks/overnight-convergence/kernel-live-pilot.json'
    record = {'name':'Isolated fixed-Coder live pilot','not_comparison_evidence':True}
    try:
        worker = LocalWorker(ROOT/'models/qwen2.5-coder-3b-instruct-q4_k_m.gguf')
        docker = DockerCommands(ROOT,ROOT/'benchmarks/overnight-convergence/docker-tasks')
        test = 'from app import answer\nassert answer()==42, "expected 42"\nprint("PASS")\n'
        def validate(files,seconds):
            return docker('python check.py',{**files,'check.py':test},seconds)
        task = TaskRoot.create(request='Fix app.py so answer() returns the integer 42. Preserve answer().',
            workspace_id='isolated-live-pilot',workspace_revision='snapshot-1',task_type='code',
            requirements=('answer() returns integer 42',),context_manifest=('app.py',),model='sovereign-code')
        result = MinimalKernel(task,{'app.py':'def answer():\n    return 24\n'},worker,docker,validate,
                               TaskBudget(max_model_calls=6,timeout_seconds=120)).run()
        record.update(result=result,calls=worker.calls)
    except Exception as error:
        record.update(state='BLOCKED',error=type(error).__name__+': '+str(error))
    destination.write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps({'state':record.get('state') or record['result']['state'],
                      'error':record.get('error')}))


if __name__=='__main__':main()
