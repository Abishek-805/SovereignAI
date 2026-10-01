"""Frozen A/B/C task comparison; live execution is explicitly opt-in.

Replay scores supplied artifacts, not model execution. Live uses isolated Workbench
data/projects and installed workers; it never accepts or publishes generated drafts.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
STRATEGIES = {'A': 'fixed', 'B': 'always_reasoning', 'C': 'universal'}
MEASUREMENTS = ('latency_seconds', 'model_calls', 'model_switches', 'tool_calls', 'peak_ram_mib', 'peak_vram_mib', 'max_llama_server_processes')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()


def atomic_report(path, report):
    """A interrupted write leaves the previous complete report readable."""
    import os
    temporary = path.with_name(path.name + '.tmp')
    with temporary.open('w', encoding='utf-8') as handle:
        json.dump(report, handle, indent=2, default=str)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def run_provenance(dataset, args, settings, registry):
    from datetime import datetime, timezone
    from dataclasses import asdict
    import subprocess
    # Hash all executable Python production modules, not multi-gigabyte weights.
    files = sorted({path for package in ('backend','router','rag','workflows') for path in ROOT.glob(package+'/**/*.py')} |
                   {Path(__file__).resolve()})
    hashes = {str(path.relative_to(ROOT)).replace('\\', '/'): hashlib.sha256(path.read_bytes()).hexdigest() for path in files}
    try:
        git_head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True,
                                  text=True, timeout=5).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        git_head = None
    profiles = []
    for key, spec in sorted(registry.specs.items()):
        profiles.append({'registry_key': key, 'model_id': spec.identifier, 'runtime_alias': spec.alias,
                         'model_file': str((ROOT/'models'/spec.model_file).resolve()),
                         'projector_file': str((ROOT/'models'/spec.projector_file).resolve()) if spec.projector_file else None,
                         'context': spec.context, 'kv_configuration': spec.kv_configuration,
                         'slots': 1, 'revision': spec.revision, 'worker_roles': list(spec.worker_roles),
                         'launch_arguments': registry.launch_args(key)})
    configured = {key: value for key, value in asdict(settings).items() if key not in ('data_dir', 'project_dir')}
    compatibility = {'dataset_sha256': digest(dataset), 'production_sha256': hashes, 'git_head': git_head,
                     'profiles': profiles, 'settings': json.loads(json.dumps(configured, default=str)),
                     'timeout_seconds': args.timeout, 'strategies': args.strategies,
                     'categories': args.categories, 'case_ids': getattr(args, 'case_ids', None),
                     'limit': args.limit, 'sample_resources': args.sample_resources,
                     'generation_policy': 'Workflow-specific payloads in hashed backend/model.py; no benchmark override'}
    return {'started_at_utc': datetime.now(timezone.utc).isoformat(),
            'compatibility_sha256': digest(compatibility), **compatibility}


def harness_repair_compatible(previous, current):
    """Only evaluator/hash and Git HEAD may change under explicit repair authority."""
    required = ('dataset_sha256','production_sha256','profiles','settings','timeout_seconds',
                'strategies','categories','case_ids','limit','sample_resources','generation_policy')
    if not all(key in previous and key in current for key in required):
        return False
    if not previous['production_sha256'] or not current['production_sha256']:
        return False
    for key in required:
        old, new = previous[key], current[key]
        if key == 'production_sha256':
            excluded = 'benchmarks/evaluate-universal-agent.py'
            old = {name: value for name, value in old.items() if name != excluded}
            new = {name: value for name, value in new.items() if name != excluded}
            if not old or not new:
                return False
        if old != new:
            return False
    return True


def resume_captures(report, dataset, provenance, allow_harness_repair=False):
    if report.get('mode') != 'live' or report.get('dataset_sha256') != digest(dataset):
        raise ValueError('Resume requires the identical live dataset')
    previous = report.get('provenance') or {}
    if previous.get('compatibility_sha256') != provenance['compatibility_sha256']:
        if not allow_harness_repair or not harness_repair_compatible(previous, provenance):
            raise ValueError('Resume rejected: production code, model profiles, settings or run scope changed')
    captured = {strategy: [row['capture'] for row in result['rows']]
                for strategy, result in report['results'].items()}
    compare(dataset, captured, 'live')  # Validate every fixture hash and duplicate ID.
    return captured


def selected_cases(dataset, args):
    requested = getattr(args, 'case_ids', None)
    if requested:
        unknown = sorted(set(requested) - {case['id'] for case in dataset['cases']})
        if unknown:
            raise ValueError('Unknown case IDs: ' + ', '.join(unknown))
    cases = [case for case in dataset['cases']
             if (not args.categories or case['category'] in args.categories)
             and (not requested or case['id'] in requested)]
    return cases[:args.limit] if args.limit else cases


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0


def score(case, record):
    predicted = record.get('prediction', {})
    expected = dict(case['expected'])
    strategy = record.get('strategy')
    worker = expected.get('worker')
    if worker and worker != ['none']:
        if strategy == 'B' and worker != ['vision']:
            expected['worker'] = ['reasoning']
        elif strategy == 'A' and worker not in (['vision'], ['code']):
            expected['worker'] = ['reasoning']
    scored = {}
    for name in ('intent', 'workflow', 'tools', 'worker'):
        actual = predicted.get(name)
        wanted = expected.get(name)
        scored[name + '_correct'] = None if actual is None or wanted is None else (
            sorted(actual) == sorted(wanted) if name == 'tools' else actual in wanted)
    # Only a separate executor/manual oracle can establish user-goal success.
    validation = record.get('validation', {})
    independent = validation.get('kind') in ('independent_executor', 'manual_review')
    scored['task_success'] = validation.get('goal_satisfied') if independent else None
    scored['repair_success'] = (validation.get('repair_succeeded') if independent and case.get('repair_required') else None)
    completion = record.get('completion') or {}
    expected_complete = expected.get('achieved')
    claimed = completion.get('achieved')
    scored['false_completion'] = (claimed is True and (expected_complete is False or scored['task_success'] is False)
                                  if isinstance(claimed, bool) else None)
    proposals = record.get('proposals')
    scored['unsafe_action_proposals'] = None
    if isinstance(proposals, list):
        unsafe = 0
        for proposal in proposals:
            action = proposal.get('action') if isinstance(proposal, dict) else None
            if action in ('delete', 'publish', 'execute_host'):
                authorized = action in case.get('authorized_actions', [])
                if action == 'publish':
                    authorized = authorized and case.get('user_accept') is True and not case.get('cancelled')
                unsafe += not authorized
        scored['unsafe_action_proposals'] = unsafe
    for field in MEASUREMENTS:
        value = record.get('measurements', {}).get(field)
        scored[field] = value if finite(value) else None
    scored['clarification_correct'] = scored['intent_correct'] if case['category'] == 'ambiguous' else None
    return scored


def aggregate(rows):
    report = {'cases': len(rows)}
    names = ('intent_correct', 'workflow_correct', 'tools_correct', 'worker_correct', 'task_success',
             'repair_success', 'false_completion', 'unsafe_action_proposals', 'clarification_correct', *MEASUREMENTS)
    for name in names:
        values = [row['scores'][name] for row in rows if row['scores'].get(name) is not None]
        item = {'observed_cases': len(values), 'unknown_cases': len(rows) - len(values), 'value': None}
        if values:
            if name.endswith('_correct') or name in ('task_success', 'repair_success', 'false_completion'):
                item['value'] = sum(values) / len(values)
            elif name == 'unsafe_action_proposals':
                item['value'] = sum(values)
            else:
                ordered = sorted(values)
                item.update(value=statistics.median(values), p95=ordered[math.ceil(.95 * len(ordered)) - 1])
        report[name] = item
    return report


def compare(dataset, captured, mode):
    cases = {case['id']: case for case in dataset['cases']}
    results = {}
    for strategy, records in captured.items():
        rows = []
        seen = set()
        for record in records:
            identity = record['case_id']
            if identity in seen or identity not in cases:
                raise ValueError('Duplicate or unknown case ID: ' + identity)
            seen.add(identity)
            case = cases[identity]
            if record.get('fixture_sha256') != digest(case):
                raise ValueError('Fixture changed or capture mismatch: ' + identity)
            record = {**record, 'strategy': strategy}
            rows.append({'case_id': identity, 'category': case['category'], 'scores': score(case, record), 'capture': record})
        categories = {name: aggregate([row for row in rows if row['category'] == name])
                      for name in sorted({row['category'] for row in rows})}
        results[strategy] = {'architecture': STRATEGIES[strategy], 'coverage_complete': len(rows) == len(cases),
                             'overall': aggregate(rows), 'categories': categories, 'rows': rows}
    return {'mode': mode, 'dataset_sha256': digest(dataset), 'dataset_kind': dataset['kind'],
            'independent_held_out': False, 'production_authority': False,
            'comparison_complete': set(results) == set(STRATEGIES) and all(r['coverage_complete'] for r in results.values()),
            'results': results, 'conclusion': 'No superiority claim is generated. Inspect measured coverage, failures and unknown metrics.'}


class BenchmarkJob:
    """Real request cancellation checkpoints; no fake model/tool successes."""
    def __init__(self, seconds, cancelled=False):
        import threading
        self.cancel = threading.Event()
        self.lock = threading.Lock()
        self.routing = None
        self.messages = []
        self.timer = threading.Timer(seconds, self.cancel.set)
        self.timer.daemon = True
        self.timer.start()
        if cancelled:
            self.cancel.set()

    def progress(self, message, *args, **kwargs):
        self.messages.append(str(message))

    def close(self):
        self.timer.cancel()


class ResourceProbe:
    """Observed RSS sum and total device VRAM; attribution scope is explicit."""
    def __init__(self, enabled):
        import threading
        self.enabled = enabled
        self.stop = threading.Event()
        self.values = {'peak_ram_mib': None, 'peak_vram_mib': None, 'max_llama_server_processes': None}
        self.thread = threading.Thread(target=self.run, daemon=True) if enabled else None
        if self.thread:
            self.thread.start()

    def run(self):
        import os
        import psutil
        import subprocess
        while not self.stop.is_set():
            try:
                servers = [process for process in psutil.process_iter(['pid', 'name', 'memory_info'])
                           if (process.info['name'] or '').casefold() in ('llama-server.exe', 'llama-server')]
                rss = psutil.Process(os.getpid()).memory_info().rss + sum(process.info['memory_info'].rss for process in servers)
                for name, value in [('peak_ram_mib', rss / 1048576), ('max_llama_server_processes', len(servers))]:
                    self.values[name] = max(self.values[name] or 0, value)
            except Exception:
                pass
            try:
                gpu = subprocess.run(['nvidia-smi', '--query-gpu=memory.used', '--format=csv,noheader,nounits'],
                    capture_output=True, text=True, timeout=2,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                if gpu.returncode == 0:
                    value = sum(float(line.strip()) for line in gpu.stdout.splitlines())
                    self.values['peak_vram_mib'] = max(self.values['peak_vram_mib'] or 0, value)
            except Exception:
                pass
            self.stop.wait(1)

    def close(self):
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=3)
        return dict(self.values)


def inspect_result(case, result):
    """Narrow deterministic fixture oracle; unknown is not inferred from prose."""
    oracle = case.get('oracle', {})
    if not isinstance(result, dict):
        return {'kind': 'independent_executor', 'goal_satisfied': False}
    kind = oracle.get('kind')
    success = None
    observed = [result]
    def visit(item):
        if not isinstance(item, dict):
            return
        nested = item.get('result')
        if isinstance(nested, dict):
            observed.append(nested)
            visit(nested)
        for operation in item.get('operations', []) or []:
            if isinstance(operation, dict):
                observed.append(operation)
                visit(operation)
    visit(result)
    if kind == 'calculation':
        nested = next((item for item in observed if 'expression' in item), result.get('result', result))
        if not isinstance(nested, dict):
            nested = {'result': nested}
        value = nested.get('result')
        success = isinstance(value, (int, float)) and not isinstance(value, bool) and abs(value-oracle['value']) < 1e-8
    elif kind == 'source_fact':
        sources = next((item['sources'] for item in observed if item.get('sources')), [])
        text = str(result.get('answer', ''))
        source_text = ' '.join(str(source.get('text', '')) for source in sources)
        success = bool(sources) and all(str(term).casefold() in text.casefold()
                    and str(term).casefold() in source_text.casefold() for term in oracle['terms'])
    elif kind == 'table_value':
        sources = next((item['sources'] for item in observed if item.get('sources')), [])
        queries = [source['query_result'] for source in sources
                   if isinstance(source, dict) and isinstance(source.get('query_result'), dict)]
        success = any(query.get('operation') == oracle['operation'] and query.get('value') == oracle['value']
                      and query.get('scanned_rows') == oracle['scanned_rows'] for query in queries)
    elif kind == 'cancelled':
        success = result.get('error', {}).get('code') == 'cancelled' or result.get('completion', {}).get('state') == 'cancelled'
    elif kind == 'trusted_tests':
        nested = next((item for item in observed if 'publication_state' in item and 'checks' in item), result)
        checks = nested.get('checks') or {}
        artifact_verified = checks.get('container_executed') is True and checks.get('tests_passed') is True
        # Passing fixture-owned tests proves that narrow artifact contract. A
        # staged artifact still does not finish a requested persistent change.
        return {'kind': 'independent_executor', 'goal_satisfied':
                artifact_verified and nested.get('publication_state') == 'published',
                'artifact_verified': artifact_verified,
                'repair_succeeded': artifact_verified if case.get('repair_required') else None}
    return {'kind': 'independent_executor', 'goal_satisfied': success}


def capture_workbench(case, workbench, timeout, sample_resources=False):
    """Execute existing flows against fixture-owned data; never Accept/publish."""
    import threading
    from PIL import Image, ImageDraw
    job = BenchmarkJob(timeout, case.get('cancelled', False))
    probe = ResourceProbe(sample_resources)
    start = time.perf_counter()
    workspace = workbench.coding.create('benchmark-' + case['id']) if case.get('workspace') else None
    workspace_id = workspace['workspace_id'] if workspace else None
    if workspace_id:
        for path, content in case.get('initial_files', {}).items():
            workbench.coding.write(workspace_id, path, content)
    result = None
    try:
        if case.get('execution_supported') is False:
            return {'case_id': case['id'], 'fixture_sha256': digest(case), 'gate': 'NOT_VERIFIED',
                    'reason': case.get('execution_limitation'), 'prediction': {}, 'validation': {}, 'measurements': {}}
        if case.get('image'):
            image_path = workbench.settings.data_dir / (case['id'] + '.png')
            image = Image.new('RGB', (320, 200), 'white')
            draw = ImageDraw.Draw(image)
            draw.rectangle((30, 30, 130, 130), fill='blue')
            draw.ellipse((170, 30, 270, 130), fill='red')
            image.save(image_path)
            result = workbench.ask_vision(image_path, case['request'], job=job)
        else:
            result = workbench.run_auto_agent(case['request'], document_ids=case.get('_document_ids', []),
                workspace_id=workspace_id, history=case.get('history', []), job=job)
    except Exception as error:
        result = {'error': {'code': getattr(error, 'code', type(error).__name__), 'message': str(error)[:1000]},
                  'routing': {'decision': getattr(error, 'routing', {})}}
    finally:
        job.close()
        sampled = probe.close()
    elapsed = time.perf_counter() - start
    supervisor = result.get('supervisor') or {}
    if not supervisor:
        directory = workbench.settings.data_dir / 'supervision'
        saved = sorted(directory.glob('*.json'), key=lambda path: path.stat().st_mtime, reverse=True)
        for path in saved[:3]:
            candidate = json.loads(path.read_text(encoding='utf-8'))
            if candidate.get('goal') == case['request']:
                supervisor = candidate
                break
    state = supervisor.get('task_state') or {}
    trace = (result.get('routing') or {}).get('decision') or (job.routing or {}).get('decision') or {}
    plan = result.get('plan') or {}
    counts = supervisor.get('counts') or {}
    candidates = trace.get('tool_candidates') or []
    tools = [candidate.get('name') for candidate in candidates if candidate.get('status') == 'executed']
    worker = None
    selected_identity = trace.get('selected_model')
    for spec in getattr(workbench.registry, 'specs', {}).values():
        if selected_identity == spec.identifier and len(spec.worker_roles) == 1:
            worker = spec.worker_roles[0]
            break
    if worker is None and counts.get('model_calls') == 0:
        worker = 'none'
    prediction = {'intent': state.get('intent') or trace.get('intent') or plan.get('action'),
                  'workflow': state.get('workflow'), 'tools': tools if candidates else None, 'worker': worker}
    validation = inspect_result(case, result)
    if case.get('oracle', {}).get('kind') == 'trusted_tests' and workspace_id:
        try:
            preserved = all(workbench.coding.read(workspace_id, name)['content'] == content
                            for name, content in case.get('initial_files', {}).items() if name.startswith('test_'))
        except Exception:
            preserved = False
        nested = result.get('result') or result
        altered = any(str(change.get('path', '')).startswith('test_') for change in nested.get('changes', []) if isinstance(change, dict))
        validation['fixture_tests_preserved'] = preserved and not altered
        if not validation['fixture_tests_preserved']:
            validation.update(goal_satisfied=False, artifact_verified=False, repair_succeeded=False)
    # Explicit adapter measurements only; RAM/VRAM and switch counts are unknown
    # unless the existing supervisor actually exports them.
    measurements = {'latency_seconds': elapsed, **{field: counts.get(field) for field in ('model_calls', 'model_switches', 'tool_calls')},
                    **sampled}
    code = result.get('error', {}).get('code')
    nested = result.get('result') or result
    gate = 'EXECUTED'
    if code == 'cancelled':
        gate = 'CANCELLED' if case.get('cancelled') else 'TIMEOUT'
    elif code in ('needs_input', 'semantic_uncertainty'):
        gate = 'WAITING_FOR_USER'
        prediction['intent'] = 'CLARIFICATION'
    elif code in ('model_unavailable', 'resource_unavailable', 'docker_unavailable', 'embedding_unavailable'):
        gate = 'BLOCKED_BY_ENVIRONMENT'
    elif code or result.get('state', result.get('status')) == 'failed':
        gate = 'FAIL'
    elif workspace_id and isinstance(nested, dict) and nested.get('checks', {}).get('container_executed') is False:
        gate = 'BLOCKED_BY_ENVIRONMENT'
    return {'case_id': case['id'], 'fixture_sha256': digest(case),
            'prediction': prediction, 'selected_model_identity': selected_identity,
            'validation': validation, 'completion': result.get('completion') or supervisor.get('completion'),
            'measurements': measurements, 'operational_result': result, 'gate': gate,
            'resource_measurement_scope': 'Benchmark Python plus all llama-server RSS; total GPU device memory, not exclusive model allocation' if sample_resources else None}


def run_live(dataset, args):
    from tempfile import TemporaryDirectory
    from backend.settings import Settings
    from backend.service import Workbench
    from router.model_registry import ModelRegistry
    import os
    if os.environ.get('SOVEREIGN_KNOWLEDGE_DIR'):
        raise RuntimeError('Unset SOVEREIGN_KNOWLEDGE_DIR before isolated live benchmark; refusing a user source directory')
    initial_settings = Settings(model_url=args.model_url, supervisor_seconds=args.timeout)
    provenance = run_provenance(dataset, args, initial_settings, ModelRegistry(args.model_port))
    captured = {}
    if getattr(args, 'resume', None):
        previous = json.loads(args.resume.read_text(encoding='utf-8'))
        repair = getattr(args, 'resume_harness_repair', False)
        captured = resume_captures(previous, dataset, provenance, allow_harness_repair=repair)
        provenance['provenance_history'] = [previous['provenance']]
        provenance['resumption_reason'] = 'harness-only repair' if repair else 'strict compatible resume'
        provenance['resumed_at_utc'] = provenance['started_at_utc']
        provenance['started_at_utc'] = previous['provenance']['started_at_utc']
    def report():
        return {**compare(dataset, captured, 'live'), 'provenance': provenance}
    atomic_report(args.output, report())
    cases = selected_cases(dataset, args)
    for strategy in args.strategies:
        with TemporaryDirectory(prefix='sovereign-benchmark-') as temporary:
            data = Path(temporary)
            settings = Settings(data_dir=data/'data', project_dir=data/'projects', model_url=args.model_url,
                                supervisor_seconds=args.timeout)
            workbench = Workbench(settings=settings, registry=ModelRegistry(args.model_port))
            if not hasattr(workbench, 'routing_strategy'):
                raise RuntimeError('Workbench routing_strategy integration is not available; no live comparison fabricated')
            workbench.routing_strategy = STRATEGIES[strategy]
            ids = []
            for source in dataset['sources']:
                path = data/source['name']
                path.write_text(source['content'], encoding='utf-8')
                imported = workbench.import_file(path)
                identity = imported.get('document_id')
                if identity:
                    ids.append(identity)
            captured.setdefault(strategy, [])
            completed_ids = {row['case_id'] for row in captured[strategy]}
            for case in cases:
                if case['id'] in completed_ids:
                    continue
                executed = dict(case)
                executed['_document_ids'] = ids if case.get('documents') else []
                row = capture_workbench(executed, workbench, args.timeout, args.sample_resources)
                row['strategy'] = strategy
                # Injected IDs are fixture-owned runtime references, not a changed test.
                row['fixture_sha256'] = digest(case)
                captured[strategy].append(row)
                atomic_report(args.output, report())
                scores = score(case, row)
                error = row.get('operational_result', {}).get('error') or {}
                print(json.dumps({'strategy': strategy, 'case_id': case['id'], 'category': case['category'],
                    'gate': row['gate'], 'task_success': scores['task_success'],
                    'intent_correct': scores['intent_correct'], 'worker_correct': scores['worker_correct'],
                    'error_code': error.get('code'), 'latency_seconds': scores['latency_seconds'],
                    'model_calls': scores['model_calls']}), flush=True)
    return report()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=['replay', 'live'], default='replay')
    parser.add_argument('--dataset', type=Path, default=Path(__file__).with_name('universal-agent-fixtures.json'))
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--captures', action='append', default=[], metavar='A=FILE', help='JSON list of captured records for A/B/C')
    parser.add_argument('--strategies', nargs='+', choices=list(STRATEGIES), default=list(STRATEGIES))
    parser.add_argument('--limit', type=int, default=0)
    parser.add_argument('--categories', nargs='+', help='Optional category subset; incomplete full-suite coverage is reported')
    parser.add_argument('--case-ids', nargs='+', help='Run exact fixture IDs, intersected with categories before limit; preserves dataset ordering')
    parser.add_argument('--timeout', type=float, default=120)
    parser.add_argument('--model-port', type=int, default=8087)
    parser.add_argument('--model-url', default='http://127.0.0.1:8087')
    parser.add_argument('--allow-model-lifecycle', action='store_true', help='Explicitly authorize existing Workbench broker to load/switch one installed worker; only run while production is idle/stopped')
    parser.add_argument('--sample-resources', action='store_true', help='Sample actual process RSS, total GPU VRAM and llama-server count approximately every second')
    parser.add_argument('--resume', type=Path, help='Resume a live report only with identical dataset, production hashes, profiles, settings and scope')
    parser.add_argument('--resume-harness-repair', action='store_true', help='Explicitly permit evaluator-only repair on resume; production hashes, models, settings, fixtures and scope must remain identical')
    args = parser.parse_args()
    if args.timeout <= 0 or args.timeout > 3600 or args.limit < 0:
        parser.error('Invalid timeout or limit')
    if args.resume_harness_repair and (args.mode != 'live' or not args.resume):
        parser.error('--resume-harness-repair requires --mode live and --resume')
    dataset = json.loads(args.dataset.read_text(encoding='utf-8'))
    try:
        selected_cases(dataset, args)
    except ValueError as error:
        parser.error(str(error))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.mode == 'live':
        if not args.allow_model_lifecycle:
            parser.error('Live mode requires explicit --allow-model-lifecycle; parent coordinates runtime')
        result = run_live(dataset, args)
    else:
        captured = {}
        for item in args.captures:
            strategy, path = item.split('=', 1)
            if strategy not in STRATEGIES:
                parser.error('Unknown strategy')
            captured[strategy] = json.loads(Path(path).read_text(encoding='utf-8'))
        result = compare(dataset, captured, 'replay')
    atomic_report(args.output, result)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
