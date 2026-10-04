"""First 15 authored tasks; not the complete requested 40-task comparison."""
import difflib
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from experiments.task_kernel import TaskRoot
from experiments.minimal_execution import MinimalKernel, TaskBudget
from experiments.kernel_docker import DockerCommands
from experiments.kernel_model import LocalWorker

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def run(name, model_path):
    here = ROOT/'benchmarks/overnight-convergence'
    small = load('fidelity_authoring', here/'code-fidelity-authoring.py')
    complex_tasks = load('complex_authoring', here/'complex-project-authoring.py')
    specs = {t['id']: t for t in json.loads((here/'code-fidelity-tasks.json').read_text())['tasks']}
    tasks = []
    for task_id, case in small.CASES.items():
        if 'source_path' in case:
            source = (ROOT/case['source_path']).read_bytes()
            if hashlib.sha256(source).hexdigest() != case['source_sha256']:
                raise RuntimeError('Source snapshot changed: '+task_id)
            starting = source.decode().replace(case['mutate_from'], case['mutate_to'], 1)
        else:
            starting = case['starting']
        tasks.append((task_id, specs[task_id]['request'], specs[task_id]['requirements'],
                      {'solution.py': starting}, case['tests']))
    for task_id, task in complex_tasks.TASKS.items():
        tasks.append((task_id, task['request'], task['requirements'], task['starting_files'], task['private_test']))
    out = ROOT/'benchmarks/model-comparison/task-tranche-1'/name
    out.mkdir(parents=True, exist_ok=True)
    docker = DockerCommands(ROOT, out/'docker-tasks')
    rows = []
    for task_id, request, requirements, files, private_test in tasks:
        destination = out/(task_id+'.json')
        if destination.exists():
            rows.append(json.loads(destination.read_text()))
            continue
        worker = LocalWorker(ROOT/model_path)
        task = TaskRoot.create(request=request, workspace_id=task_id,
            workspace_revision=hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest(),
            task_type='code', requirements=tuple(requirements), context_manifest=tuple(files), model=name)
        def validate(candidate, seconds):
            return docker('python -m unittest discover -p test_contract.py',
                          {**candidate, 'test_contract.py': private_test}, seconds)
        started = time.time()
        result = MinimalKernel(task, files, worker, docker, validate,
            TaskBudget(max_model_calls=12, max_repair_attempts=3, timeout_seconds=300),
            record_path=out/(task_id+'-trajectory.json')).run()
        diff = ''.join(''.join(difflib.unified_diff(files.get(p,'').splitlines(True),
                   result['files'].get(p,'').splitlines(True), fromfile=p, tofile=p))
                   for p in sorted(set(files)|set(result['files'])))
        row = {'task_id': task_id, 'request': request, 'requirements': requirements,
               'model': name, 'routing': 'fixed model, no router', 'switches': 0,
               'starting_files': files, 'private_test_sha256': hashlib.sha256(private_test.encode()).hexdigest(),
               'result': result, 'calls': worker.calls, 'candidate_diff': diff,
               'removed_files': sorted(set(files)-set(result['files'])), 'started_unix': started,
               'not_complete_40_task_comparison': True}
        temporary = destination.with_suffix('.tmp')
        temporary.write_text(json.dumps(row, indent=2))
        temporary.replace(destination)
        rows.append(row)
        print(name, task_id, result['state'], flush=True)
        (out/'progress.json').write_text(json.dumps({'completed':len(rows), 'required_tranche':len(tasks),
               'full_comparison_complete':False}, indent=2))
    return rows
