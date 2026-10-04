"""Scripted adapter integration control; not a model or architecture benchmark."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from experiments.task_kernel import TaskRoot
from experiments.minimal_execution import MinimalKernel, TaskBudget
from experiments.kernel_docker import DockerCommands


def main():
    original = 'def answer():\n    return 24\n'
    files = {'app.py':original}
    private_test = 'from app import answer\nassert answer() == 42, "expected 42, got %s" % answer()\nprint("validated 42")\n'
    docker = DockerCommands(ROOT,ROOT/'benchmarks/overnight-convergence/docker-tasks')
    def validate(candidate,seconds):
        return docker('python check.py',{**candidate,'check.py':private_test},seconds)
    task = TaskRoot.create(request='Repair answer() to return 42 and preserve app.py',
                           workspace_id='isolated-smoke',workspace_revision='snapshot-1',
                           task_type='code',requirements=('answer() returns 42',),
                           context_manifest=('app.py',),model='scripted-control')
    actions = iter([
        {'action':'finish','reason':'done'},
        {'action':'apply_patch','patch':json.dumps([{'path':'app.py',
          'before_sha256':hashlib.sha256(original.encode()).hexdigest(),
          'content':'def answer():\n    return 42\n'}])},
        {'action':'finish','reason':'tests_passed'},
    ])
    def model(model_name,context,tokens,seconds):
        assert context['original_request'] == task.request
        assert model_name == task.model
        if context['latest_observation'].get('exit_code') == 1:
            assert 'expected 42' in context['latest_observation']['stderr']
        return next(actions),1
    result = MinimalKernel(task,files,model,docker,validate).run()
    assert result['state']=='READY_FOR_REVIEW',result
    assert result['counts']['repair_attempts']==1
    assert result['counts']['sandbox_runs']==2
    exhausted = MinimalKernel(task,files,lambda *args:({'action':'read_file','path':'app.py'},1),
                              docker,validate,TaskBudget(max_model_calls=2)).run()
    assert exhausted['state']=='BUDGET_EXHAUSTED'
    report = {'name':'Minimal kernel scripted Docker integration control',
              'not_model_evidence':True,'repair_control':result,'budget_control':exhausted}
    destination=ROOT/'benchmarks/overnight-convergence/kernel-smoke-results.json'
    destination.write_text(json.dumps(report,indent=2)+'\n')
    print('Docker repair/validation control passed; budget control passed')


if __name__=='__main__':main()
