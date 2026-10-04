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
from experiments.benchmark_resources import ResourceSamples
from experiments.comparison_extra_tasks import cases as extra_cases
from experiments.comparison_report import main as update_report

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
    metadata = {}
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
        metadata[task_id] = {'category':'repair_verify' if specs[task_id]['cluster']=='repair_regression' else 'code_modification'}
    for task_id, task in complex_tasks.TASKS.items():
        tasks.append((task_id, task['request'], task['requirements'], task['starting_files'], task['private_test']))
        metadata[task_id] = {'category':'complex'}
    for case in extra_cases():
        tasks.append((case['id'], case['request'], case['requirements'], case['starting_files'], case['private_test']))
        metadata[case['id']] = case
    assert len(tasks)==40
    manifest = [{'task_id':i,'request':r,'requirements':req,'starting_files':f,
                 'private_test_sha256':hashlib.sha256(t.encode()).hexdigest(),
                 'category':metadata[i]['category']} for i,r,req,f,t in tasks]
    frozen = ROOT/'benchmarks/model-comparison/frozen-40-task-manifest.json'
    encoded = json.dumps(manifest,sort_keys=True,indent=2)
    if frozen.exists() and frozen.read_text()!=encoded:
        raise RuntimeError('Frozen task manifest changed')
    if not frozen.exists(): frozen.write_text(encoded)
    out = ROOT/'benchmarks/model-comparison/fixed-40'/name
    out.mkdir(parents=True, exist_ok=True)
    docker = DockerCommands(ROOT, out/'docker-tasks')
    controls=json.loads((ROOT/'benchmarks/model-comparison/oracle-controls/summary.json').read_text())
    if controls.get('controls')!=25 or controls.get('all_passed') is not True:
        raise RuntimeError('New oracle controls are incomplete')
    invariant_paths=['experiments/minimal_execution.py','experiments/task_kernel.py',
        'experiments/kernel_docker.py','experiments/kernel_model.py','experiments/model_task_tranche.py',
        'experiments/comparison_extra_tasks.py','experiments/comparison_report.py',
        'experiments/benchmark_resources.py','benchmarks/overnight-convergence/code-fidelity-authoring.py',
        'benchmarks/overnight-convergence/complex-project-authoring.py',
        'benchmarks/overnight-convergence/code-fidelity-tasks.json','runtime/llama-b11132/llama-server.exe']
    contract={'files':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in invariant_paths},
        'sandbox_image_id':docker.image_id,'context_tokens':4096,'temperature':0,
        'max_model_calls':12,'max_repair_attempts':3,'max_sandbox_runs':12,
        'timeout_seconds':300,'max_output_tokens':12000,'max_tool_calls':40}
    contract_path=ROOT/'benchmarks/model-comparison/frozen-experiment-contract.json'
    if contract_path.exists() and json.loads(contract_path.read_text())!=contract:
        raise RuntimeError('Frozen experiment contract changed')
    if not contract_path.exists():contract_path.write_text(json.dumps(contract,indent=2))
    rows = []
    for task_id, request, requirements, files, private_test in tasks:
        if (ROOT/'benchmarks/model-comparison/pause-requested').exists():
            raise SystemExit('Evidence-collection maintenance requested at task boundary')
        destination = out/(task_id+'.json')
        prior = ROOT/'benchmarks/model-comparison/task-tranche-1'/name/(task_id+'.json')
        if not destination.exists() and prior.exists():
            historical = json.loads(prior.read_text())
            historical['resource_measurements_unavailable'] = 'Recorded before passive sampler; retained valid result without rerun'
            historical['category'] = metadata[task_id]['category']
            destination.write_text(json.dumps(historical,indent=2))
        if destination.exists():
            rows.append(json.loads(destination.read_text()))
            update_report()
            continue
        worker = LocalWorker(ROOT/model_path)
        task = TaskRoot.create(request=request, workspace_id=task_id,
            workspace_revision=hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest(),
            task_type='code', requirements=tuple(requirements), context_manifest=tuple(files), model=name)
        def validate(candidate, seconds):
            checked = docker('python -m unittest discover -p test_contract.py',
                            {**candidate, 'test_contract.py': private_test}, seconds)
            if metadata[task_id]['category']=='run_project' and checked['exit_code']==0:
                case = metadata[task_id]
                evidence = [e for e in kernel.events if e.get('action',{}).get('action')=='exec'
                    and e['action'].get('command')==case['expected_command']
                    and e.get('observation',{}).get('exit_code')==0
                    and e['observation'].get('stdout')==case['expected_stdout']]
                reads = [e for e in kernel.events if e.get('action',{}).get('action')=='read_file'
                         and e['action'].get('path')=='README.md']
                if not evidence or not reads or candidate!=files:
                    checked.update(exit_code=1,stderr='Run contract failed: require README inspection, exact documented command/output, and unchanged files.')
            return checked
        started = time.time()
        kernel = MinimalKernel(task, files, worker, docker, validate,
            TaskBudget(max_model_calls=12, max_repair_attempts=3, timeout_seconds=300),
            record_path=out/(task_id+'-trajectory.json'))
        with ResourceSamples(worker.identity['pid']) as resources:
            result = kernel.run()
        diff = ''.join(''.join(difflib.unified_diff(files.get(p,'').splitlines(True),
                   result['files'].get(p,'').splitlines(True), fromfile=p, tofile=p))
                   for p in sorted(set(files)|set(result['files'])))
        row = {'task_id': task_id, 'request': request, 'requirements': requirements,
               'model': name, 'routing': 'fixed model, no router', 'switches': 0,
               'starting_files': files, 'private_test_sha256': hashlib.sha256(private_test.encode()).hexdigest(),
               'result': result, 'calls': worker.calls, 'candidate_diff': diff,
               'removed_files': sorted(set(files)-set(result['files'])), 'started_unix': started,
               'category':metadata[task_id]['category'], 'resources':resources.result(),
               'not_complete_40_task_comparison': True}
        temporary = destination.with_suffix('.tmp')
        temporary.write_text(json.dumps(row, indent=2))
        temporary.replace(destination)
        rows.append(row)
        update_report()
        print(name, task_id, result['state'], flush=True)
        (out/'progress.json').write_text(json.dumps({'completed':len(rows), 'required_tranche':len(tasks),
               'full_comparison_complete':False}, indent=2))
    return rows
