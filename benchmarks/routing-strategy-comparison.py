"""Matched real strategy comparison. Default is manifest-only: no inference.

Run only in an exclusive model window:
  .app-venv/Scripts/python.exe benchmarks/routing-strategy-comparison.py --execute

This compares model-selection policies, not different planners. Legacy mapping
still uses current workflow validation and the current model client. API transport
is excluded. Each strategy has its own isolated fixture and every recorded sample
is an independent execution; no primary-run timing is reused. No oracle is
invented when there is no competing eligible installed alternative.
"""
from __future__ import annotations
import argparse
import ast
import csv
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
import sys
import time
import uuid
import zipfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
STRATEGIES = ('always_text', 'current_mapping', 'proposed')


def describe(cases, selected, source_hash):
    """Dry validation: reads source literals only, never imports runtime services."""
    if len(cases)<30 or any(not isinstance(case.get('question'),str) or not case['question'].strip() for case in cases):
        raise ValueError('A complete representative manifest requires at least thirty nonempty tasks')
    allowed={'answer','calculate','search_documents','create_report','inspect_code','edit_code','analyze_image'}
    if any(case.get('action') not in allowed for case in cases):raise ValueError('Unknown expected action')
    return {'matched_tasks':len(cases),'selected_tasks':len(selected),
        'selected_case_ids':[f'e{i+1:02}' for i,_ in selected], 'strategies':STRATEGIES,
        'tasks':[{'case_id':f'e{i+1:02}',**case} for i,case in enumerate(cases)],
        'primary_manifest_sha256':source_hash,'inference_performed':False,
        'category_counts':dict(Counter(case['category'] for case in cases)),
        'expected_action_counts':dict(Counter(case['action'] for case in cases)),
        'classifier':{'production_enabled':False,'policy':'evaluated_cpu_abstains_then_bounded_model_planner',
            'promotion_status':'blocked','reason':'Independent CPU classifier safety/quality release gates have not passed'},
        'comparison_scope':'Candidate mapping/admission policies using the same disabled CPU classifier and model fallback; not an enabled CPU-routing A/B experiment',
        'strategy_definitions':{
            'always_text':'Fixed text model with production hard admission; refuse unsupported image modality',
            'current_mapping':'Fixed legacy text/code→text, image→vision mapping with identical production hard admission; no candidate optimizer',
            'proposed':'Current hard candidate/resource admission and measured selection; learned CPU routing remains disabled'},
        'mapping_equivalence':'Only one admissible text/code model and one vision model; current/proposed may select the same physical model',
        'always_text_image':'Unsupported modality; recorded refusal, not invented image timing or quality',
        'oracle':{'status':'unavailable','latency_seconds':None,
            'reason':'No competing eligible installed model actually executed for the same capability'},
        'remaining_gates':['Execute full matched manifest in an exclusive window',
            'Human review open answers, reports, and image','Repeat/counterbalance before tail-latency or speedup claims',
            'Independent classifier promotion requires separate frozen held-out safety/quality evidence',
            'Execute competing eligible models before oracle or optimizer claims']}


def manifest():
    """Read literals without importing the primary harness (which executes)."""
    source = ROOT / 'benchmarks/routing-system-integration.py'
    tree = ast.parse(source.read_text(encoding='utf-8'))
    cases, fixture = [], None
    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            call = node.value
            if isinstance(call.func, ast.Name) and call.func.id == 'add':
                values = [ast.literal_eval(arg) for arg in call.args]
                if len(values) == 3:
                    values.append(None)
                cases.append(dict(zip(('question', 'action', 'category', 'needle'), values)))
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'fixture' for t in node.targets):
            fixture = ast.literal_eval(node.value)
    cases.append({'question': 'Describe the two colored shapes and their left/right positions.',
                  'action': 'analyze_image', 'category': 'vision', 'needle': None})
    if len(cases) != 31 or not isinstance(fixture, str):
        raise ValueError('Primary matched manifest changed; review fixtures before execution')
    return cases, fixture, hashlib.sha256(source.read_bytes()).hexdigest()


def fixed_router(registry, strategy):
    from router.router import CapabilityRouter
    from router.model_selection import ModelSelector

    class FixedRegistry:
        def __init__(self,key):
            self.specs={key:registry.specs[key]} if key in registry.specs else {}
        def installed(self,spec):return registry.installed(spec)
        def runtime_available(self,spec):return registry.runtime_available(spec)

    class FixedRouter(CapabilityRouter):
        def select_model(self, capability, *, modality='text', required_context=None,
                         resource_snapshot=None,current_residency=None, **_):
            key='vision' if strategy=='current_mapping' and capability=='vision' else 'text'
            # Fixed selection never bypasses production license/runtime/resource
            # safety or silently falls through to another mapped candidate.
            choice=ModelSelector(FixedRegistry(key),sampler=self.selector.sampler,
                                 policy=self.selector.policy).select(capability,modality=modality,
                required_context=required_context,resource_snapshot=resource_snapshot,
                current_residency=current_residency)
            choice.selection_policy='fixed_mapping_with_production_hard_admission'
            choice.selection_evidence.update({'benchmark_strategy':strategy,'fixed_registry_key':key,
                                             'optimizer_comparison':False})
            choice.route_reason='Fixed benchmark mapping with production hard admission. '+choice.route_reason
            return choice
    return FixedRouter(registry)


def check_idle():
    """Abort instead of competing with an application task or another benchmark."""
    import httpx
    # The installed runtime may wake a sleeping model for /slots. This preflight
    # is outside workflow timings; wait for it rather than treating wake as idle.
    with httpx.Client(timeout=30, trust_env=False) as client:
        response = client.get('http://127.0.0.1:8087/slots')
        response.raise_for_status()
        slots = response.json()
        if any(slot.get('is_processing') for slot in slots):
            raise RuntimeError('Runtime is processing another request; exclusive benchmark window required')


def run_job(work, deadline):
    from backend.jobs import Jobs
    jobs = Jobs()
    snapshot = jobs.start('agent', work)
    job = jobs.get(snapshot['job_id'])
    until = time.monotonic() + deadline
    while job.state == 'running':
        if time.monotonic() > until:
            job.cancel.set()
            # Stop the suite, never start the next inference while this is unwinding.
            raise TimeoutError('Comparison deadline: cancellation requested; suite aborted')
        time.sleep(.1)
    return job.snapshot()


def file_snapshot(service, workspace_id):
    return {name:hashlib.sha256(data).hexdigest() for name,data in service.coding.raw_files(workspace_id).items()}


def validate(service, workspace_id, case, result, before):
    actual = result.get('plan', {}).get('action')
    answer = result.get('answer', '')
    nested = result.get('result', {})
    expected = case['action']
    checks = {'route_matches': actual == expected}
    if expected != 'edit_code':checks['answer_nonempty']=isinstance(answer,str) and bool(answer.strip())
    if case['needle']:
        checks['answer_contains_expected_fact'] = case['needle'].lower() in answer.lower()
    if expected in ('search_documents', 'create_report'):
        checks['source_links_present'] = bool(nested.get('sources'))
        known={item['document_id']:item['active_hash'] for item in service.documents()}
        sources=nested.get('sources') or []
        checks['source_identity_valid']=bool(sources) and all(source.get('document_id') in known and source.get('version_hash')==known[source['document_id']] for source in sources)
        labels={source.get('label') for source in sources}
        references={label for bracket in re.findall(r'\[([^\]]+)\]',answer) for label in re.findall(r'\bS\d+\b',bracket)}
        checks['answer_cites_returned_labels']=bool(references) and references.issubset(labels)
        checks['semantic_support_human_review']=None
    if expected == 'create_report':
        task_id = nested.get('task_id') or result.get('task_id')
        paths = list((service.settings.data_dir.parent / 'outputs' / str(task_id)).glob('*.docx'))
        checks['artifact_valid'] = bool(paths) and all(zipfile.is_zipfile(path) for path in paths)
        if checks['artifact_valid']:
            bodies=[]
            for path in paths:
                with zipfile.ZipFile(path) as archive:
                    bodies.append(' '.join(ET.fromstring(archive.read('word/document.xml')).itertext()))
            checks['artifact_content_readback']=all(' '.join(answer.split()) in ' '.join(body.split()) for body in bodies)
    after = file_snapshot(service, workspace_id)
    if expected != 'edit_code':
        checks['unrelated_files_unchanged'] = before == after
    elif 'notes.md' in case['question']:
        checks['code_valid'] = service.coding.read(workspace_id, 'notes.md')['content'] == '# Working notes\nVerified item.\n'
        checks['unrelated_files_unchanged'] = {k: v for k, v in before.items() if k != 'notes.md'} == {k: v for k, v in after.items() if k != 'notes.md'}
    elif 'divide.js' in case['question']:
        checks['code_valid'] = service.coding.read(workspace_id, 'divide.js')['content'] == 'module.exports = function divide(a, b) { return a / b; };\n'
        checks['unrelated_files_unchanged'] = {k: v for k, v in before.items() if k != 'divide.js'} == {k: v for k, v in after.items() if k != 'divide.js'}
    else:
        from backend.jobs import Job
        terminal_job = Job('terminal')
        command = "node -e \"const multiply=require('./multiply.js'); for(const [a,b] of [[6,7],[0,8],[-3,4],[1.5,2],[9,1]])if(multiply(a,b)!==a*b)process.exit(1); console.log('RESULT=42')\""
        terminal = service.execute_terminal(workspace_id, command, terminal_job)
        checks['code_valid'] = terminal.get('exit_code') == 0 and 'RESULT=42' in terminal_job.output
        checks['unrelated_files_unchanged'] = before == {k: v for k, v in after.items() if k != 'multiply.js'}
    if expected == 'analyze_image':
        checks['scene_words_present'] = all(word in answer.lower() for word in ('red', 'blue', 'left', 'right'))
        checks['human_review'] = None
    return actual, checks


def persist(folder, rows, metadata):
    (folder / 'results.json').write_text(json.dumps({'metadata': metadata, 'rows': rows}, indent=2, default=str), encoding='utf-8')
    fields = ['execution_id', 'task_id', 'strategy', 'expected_action', 'actual_action', 'success',
              'workflow_seconds', 'validation_seconds', 'failure_category']
    with (folder / 'results.csv').open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fields, extrasaction='ignore')
        writer.writeheader(); writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--deadline', type=int, default=240)
    parser.add_argument('--tasks', type=int, default=31, help='Prefix only, 1–31; reductions are explicitly reported')
    parser.add_argument('--case-ids',help='Explicit targeted correction IDs, for example e12,e28,e29,e30')
    parser.add_argument('--manifest-out',type=Path,help='Write dry validated manifest JSON; no runtime imports')
    parser.add_argument('--strategies',default=','.join(STRATEGIES),help='Explicit policy subset; omitted arms are reported, never substituted')
    args = parser.parse_args()
    strategies=tuple(args.strategies.split(','))
    if not strategies or len(set(strategies))!=len(strategies) or any(value not in STRATEGIES for value in strategies):parser.error('Unknown or duplicate strategy')
    if not 1 <= args.tasks <= 31 or args.deadline < 1:
        parser.error('tasks must be 1–31 and deadline positive')
    cases, fixture, source_hash = manifest()
    selected=list(enumerate(cases[:args.tasks]))
    if args.case_ids:
        requested=args.case_ids.split(',')
        if len(set(requested))!=len(requested) or any(item not in {f'e{i+1:02}' for i in range(len(cases))} for item in requested):parser.error('Unknown or duplicate correction case IDs')
        selected=[(i,case) for i,case in enumerate(cases) if f'e{i+1:02}' in requested]
    description = describe(cases,selected,source_hash)
    description['strategies']=strategies
    description['omitted_strategies']=[value for value in STRATEGIES if value not in strategies]
    if args.manifest_out:
        args.manifest_out.write_text(json.dumps(description,indent=2),encoding='utf-8')
    if not args.execute:
        print(json.dumps(description, indent=2)); return
    check_idle()
    from backend.service import Workbench
    from backend.settings import Settings
    from router.model_registry import ModelRegistry
    from rag.embedding import Embedder
    from router.sandbox import CodeSandbox
    from PIL import Image, ImageDraw

    class IsolatedSettings(Settings):
        @property
        def sources_dir(self): return self.data_dir / 'sources'

    folder = ROOT / 'benchmarks' / 'routing-strategy-artifacts' / uuid.uuid4().hex
    folder.mkdir(parents=True)
    registry = ModelRegistry(8087)
    verified_path=Settings().data_dir/'sandbox-validation.json'
    verified=json.loads(verified_path.read_text(encoding='utf-8'))
    required={'normal_execution','network_blocked','root_read_only','input_read_only','non_root'}
    if not all(verified.get('checks',{}).get(key) is True for key in required):raise ValueError('Actual pinned sandbox verification has not passed')
    CodeSandbox('docker',image_id=verified.get('image_id'))._ready()
    image_path = folder / 'scene.png'
    image = Image.new('RGB', (640, 360), 'white'); draw = ImageDraw.Draw(image)
    draw.rectangle((50, 90, 210, 250), fill='red'); draw.ellipse((390, 90, 550, 250), fill='blue'); image.save(image_path)
    services = {}
    shared_embedder=Embedder(Settings().model_dir)
    for strategy in strategies:
        own = folder / strategy; own.mkdir()
        settings = IsolatedSettings(data_dir=own / 'data', project_dir=own / 'projects')
        service = Workbench(settings=settings, registry=registry,embedder=shared_embedder)
        from router.capability_classifier import ConservativeCapabilityClassifier
        # This experiment must not silently promote a learned classifier when
        # candidate safety gates failed. Every comparator uses the same gate.
        service.classifier=ConservativeCapabilityClassifier()
        (settings.data_dir/'sandbox-validation.json').write_text(json.dumps(verified),encoding='utf-8')
        if strategy != 'proposed': service.router = fixed_router(registry, strategy)
        workspace = service.coding.create('Independent ' + strategy)['workspace_id']
        for name, content in {'notes.md': '# Working notes\nOld item.\n', 'divide.js': 'module.exports = function divide(a, b) { return a * b; };\n'}.items():
            service.coding.write(workspace, name, content)
        service.coding.import_bytes(workspace,'assets/imported.png',b'\x89PNG\r\n\x1a\n\0'+b'p'*1_100_000)
        service.coding.import_bytes(workspace,'assets/diagram.svg',b'<svg xmlns="http://www.w3.org/2000/svg"/>')
        document = own / 'fixture.txt'; document.write_text(fixture, encoding='utf-8')
        did = service.import_file(document)['document_id']
        services[strategy] = (service, workspace, did)
    metadata = {**description, 'inference_performed': True, 'run_id': folder.name,
                'timing_boundary': 'Direct Workbench workflow, excluding setup, API transport, and separately timed validation',
                'counterbalance': 'Rotate strategy order for each task; preserve independent strategy fixture histories',
                'registry': registry.records(), 'p95': None, 'oracle_samples': [], 'human_review_complete': False}
    metadata['harness_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    metadata['source_sha256']={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in (
        'backend/model.py','backend/service.py','backend/cancellation.py','router/capability_classifier.py',
        'workflows/document_report.py','router/model_registry.py','router/model_selection.py','router/resource_admission.py',
        'router/tool_registry.py','backend/application_tools.py','rag/answer.py','rag/calculator.py','rag/retrieve.py','router/telemetry.py')}
    metadata['sandbox_verification']={'image_id':verified['image_id'],'source_sha256':hashlib.sha256(verified_path.read_bytes()).hexdigest()}
    rows = []
    persist(folder, rows, metadata)
    try:
        for index, case in selected:
            offset=index % len(strategies)
            order = strategies[offset:] + strategies[:offset]
            for strategy in order:
                check_idle()
                service, workspace, did = services[strategy]
                before = file_snapshot(service, workspace)
                start = time.perf_counter()
                work = (lambda job: service.run_image_agent(case['question'], image_path, job=job)) if case['action'] == 'analyze_image' else (lambda job: service.run_auto_agent(case['question'], [did], workspace, [], job=job))
                job = run_job(work, args.deadline)
                workflow_seconds = time.perf_counter() - start
                result = job.get('result') or {}
                validation_start = time.perf_counter()
                try:
                    actual, checks = validate(service, workspace, case, result, before)
                except Exception as exc:
                    actual = result.get('plan', {}).get('action')
                    checks = {'validator_completed': False, 'validation_error': str(exc)}
                validation_seconds = time.perf_counter() - validation_start
                success = job['state'] == 'completed' and all(value is not False for value in checks.values())
                error = job.get('error') or ''
                failure = None if success else 'resource_failure' if 'cannot satisfy' in error or 'No model satisfies' in error else 'evidence_failure' if 'grounded report' in error else 'router_failure' if actual != case['action'] else 'validation_failure' if checks.get('validator_completed') is False or checks.get('code_valid') is False or checks.get('artifact_valid') is False or checks.get('unrelated_files_unchanged') is False else 'evidence_failure' if checks.get('source_links_present') is False else 'model_failure'
                row = {'execution_id': uuid.uuid4().hex, 'task_id': f'e{index+1:02}', 'strategy': strategy,
                       'task': case['question'], 'expected_action': case['action'], 'actual_action': actual,
                       'success': success, 'workflow_seconds': workflow_seconds, 'validation_seconds': validation_seconds,
                       'failure_category': failure, 'checks': checks, 'job': job}
                trace=job.get('routing') or result.get('routing_decision') or {}
                row['routing_observations']={key:trace.get(key) for key in (
                    'request_id','classification','evidence_required','evidence_used','knowledge_scope','retrieval',
                    'selected_model','switch_required','resource_admission','selection_evidence','failure_layer','timings')}
                leases=[stage for stage in trace.get('stages',[]) if stage.get('stage')=='runtime_lease']
                row['runtime_lease_requests']=len(leases) if trace else None
                row['actual_model_switches']=sum(stage.get('switch_required') is True for stage in leases) if trace else None
                rows.append(row); persist(folder, rows, metadata)
                print(json.dumps({key: row[key] for key in ('task_id', 'strategy', 'success', 'workflow_seconds', 'failure_category')}), flush=True)
    finally:
        # Retain only suite-owned fixtures/results for inspection. No user files are altered or deleted.
        metadata['completed_samples'] = len(rows)
        metadata['complete'] = len(rows) == len(selected) * len(strategies)
        persist(folder, rows, metadata)
        print('Results and isolated fixtures: ' + str(folder), flush=True)


if __name__ == '__main__':
    main()
