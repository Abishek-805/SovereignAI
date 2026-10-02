"""Frozen five-arm Code Assist comparison. Defaults to fixture validation only.

Live candidates remain staged; trusted tests never enter editable/model context.
"""
import argparse
import hashlib
import importlib.util
import json
import os
import re
from pathlib import Path
import shutil
import sys
import time
from urllib.request import urlopen
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location('universal_benchmark', ROOT / 'benchmarks/evaluate-universal-agent.py')
shared = importlib.util.module_from_spec(spec)
spec.loader.exec_module(shared)
ARMS = {'A': 'lightweight', 'B': 'reasoning', 'C': 'code', 'D': None, 'E': None}
REPAIR_FEEDBACK_POLICY = 'V3-bounded-runtime-exception'


def safe_repair_diagnostic(stderr, candidate_files=None):
    """Expose only a final built-in exception and narrowly templated diagnostics.

    Arbitrary exception messages can contain oracle values or paths. They are
    never copied, including AssertionError messages. Full stderr stays offline.
    """
    lines = str(stderr).strip().splitlines()
    final = lines[-1] if lines else ''
    match = re.fullmatch(r'(NameError|UnboundLocalError|TypeError|ValueError|IndexError|KeyError|AttributeError|ZeroDivisionError|RuntimeError|ImportError|ModuleNotFoundError|AssertionError|OverflowError|RecursionError)(?:: (.*))?', final)
    if not match:
        return 'unclassified validation failure'
    category, message = match.groups()
    # Identifiers are bounded and must be ordinary source symbols, not paths.
    identifier = r'[A-Za-z_][A-Za-z_0-9]{0,63}'
    templates = {
        'NameError': rf"name '{identifier}' is not defined",
        'UnboundLocalError': rf"cannot access local variable '{identifier}' where it is not associated with a value",
        'TypeError': r"unsupported operand type\(s\) for [+-/*%]: '(?:int|float|str|list|tuple|dict|set|NoneType|bool)' and '(?:int|float|str|list|tuple|dict|set|NoneType|bool)'",
        'ZeroDivisionError': r'(?:division by zero|integer division or modulo by zero|float division by zero)',
        'IndexError': r'(?:list|tuple|string) index out of range',
    }
    if message and category in templates and re.fullmatch(templates[category], message):
        if category in {'NameError', 'UnboundLocalError'}:
            symbol = re.search(r"'([^']+)'", message).group(1)
            sources = [content.decode('utf-8', errors='replace') if isinstance(content, bytes) else str(content)
                       for content in (candidate_files or {}).values()]
            if not any(re.search(r'\b' + re.escape(symbol) + r'\b', source) for source in sources):
                return category
        return category + ': ' + message
    return category

class LiveSuiteLock:
    """Kernel lock shared by every evaluator output; released on process exit."""
    def __init__(self, path):
        self.path = path
        self.handle = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open('a+b')
        if self.path.stat().st_size == 0:
            self.handle.write(b'0')
            self.handle.flush()
        self.handle.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            self.handle.close()
            raise RuntimeError('Another live benchmark owns the exclusive suite lock') from error
        return self

    def __exit__(self, *exc):
        self.handle.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        self.handle.close()

def routing_metrics(rows):
    """Score routing labels independently of trusted task outcome.

    Missing predictions or expected labels are unknown, never incorrect.
    Joint classification requires both task type and complexity labels.
    """
    def score(predicate):
        outcomes = [predicate(row.get('prediction') or {}, row.get('expected') or {}) for row in rows]
        known = [outcome for outcome in outcomes if outcome is not None]
        correct = sum(outcome is True for outcome in known)
        return {'cases': len(rows), 'evaluated': len(known), 'unknown': len(rows) - len(known),
                'correct': correct, 'incorrect': len(known) - correct,
                'accuracy': correct / len(known) if known else None}

    def exact(prediction, expected, fields):
        if any(prediction.get(field) is None or expected.get(field) is None for field in fields):
            return None
        return all(prediction[field] == expected[field] for field in fields)

    def suitable(prediction, expected):
        workers = expected.get('suitable_workers')
        role = prediction.get('worker_role')
        if role is None or not isinstance(workers, (list, tuple)) or not workers:
            return None
        return role in workers

    return {'task_type_exact': score(lambda p, e: exact(p, e, ('task_type',))),
            'complexity_exact': score(lambda p, e: exact(p, e, ('complexity',))),
            'classification_exact': score(lambda p, e: exact(p, e, ('task_type', 'complexity'))),
            'worker_suitability': score(suitable)}


def summarize(rows):
    summary = {}
    for arm in ARMS:
        selected = [row for row in rows if row.get('arm') == arm]
        latencies = sorted(row['measurements']['latency_seconds'] for row in selected
                           if row.get('measurements', {}).get('latency_seconds') is not None)
        def percentile(fraction):
            if not latencies:
                return None
            position = (len(latencies) - 1) * fraction
            lower = int(position)
            upper = min(lower + 1, len(latencies) - 1)
            return latencies[lower] + (latencies[upper] - latencies[lower]) * (position - lower)
        summary[arm] = {'completed_cases': len(selected),
                        'routing': routing_metrics(selected),
                        'trusted_artifacts_evaluated': sum(row.get('correctness') is not None for row in selected),
                        'trusted_artifact_accuracy': (sum(row.get('correctness') is True for row in selected) /
                                                      sum(row.get('correctness') is not None for row in selected)
                                                      if any(row.get('correctness') is not None for row in selected) else None),
                        'latency_observed_cases': len(latencies),
                        'latency_unknown_cases': len(selected) - len(latencies),
                        'trusted_artifacts_passed': sum(row.get('correctness') is True for row in selected),
                        'trusted_artifacts_failed': sum(row.get('correctness') is False for row in selected),
                        'correctness_unknown': sum(row.get('correctness') is None for row in selected),
                        'semantic_goals_unknown': sum(row.get('goal_satisfied') is None for row in selected),
                        'repairs_observed': sum(row.get('repair_observed') is True for row in selected),
                        'repairs_independently_passed': sum(row.get('repair_succeeded') is True for row in selected),
                        'latency_p50_seconds': percentile(.5), 'latency_p95_seconds': percentile(.95),
                        'categories': {category: {'cases': sum(row.get('category') == category for row in selected),
                                                'trusted_passed': sum(row.get('category') == category and row.get('correctness') is True for row in selected)}
                                       for category in sorted({row['category'] for row in selected if 'category' in row})}}
    return summary

def check_backend_idle(settings, backend_url, job_ids):
    """Read persisted supervisor state and optional known backend job snapshots."""
    active = []
    for path in (settings.data_dir / 'supervision').glob('*.json'):
        snapshot = json.loads(path.read_text(encoding='utf-8'))
        if snapshot.get('outcome') == 'running':
            active.append(snapshot.get('supervisor_id', path.stem))
    observed = []
    for job_id in job_ids or []:
        if not job_id.isalnum():
            raise ValueError('Invalid backend job identity')
        with urlopen(backend_url.rstrip('/') + '/coding/jobs/' + job_id, timeout=5) as response:
            snapshot = json.load(response)
        observed.append({'job_id': job_id, 'state': snapshot.get('state')})
        if snapshot.get('state') == 'running':
            active.append(job_id)
    if active:
        raise RuntimeError('Backend jobs are active or incomplete: ' + ', '.join(active))
    return {'persisted_supervisor_check': 'idle', 'known_backend_jobs': observed,
            'limitation': 'Backend exposes individual job lookup, no list-active endpoint; other callers must remain idle'}

class TrustedSandboxProxy:
    """Feed externally observed test failures into the existing repair workflow."""
    def __init__(self, sandbox, case, timeout, deadline=None):
        object.__setattr__(self, '_sandbox', sandbox)
        object.__setattr__(self, 'case', json.loads(json.dumps(case)))
        object.__setattr__(self, 'timeout', timeout)
        object.__setattr__(self, 'deadline', deadline)
        object.__setattr__(self, 'trajectory', [])

    def __getattr__(self, name):
        return getattr(self._sandbox, name)

    def __setattr__(self, name, value):
        setattr(self._sandbox, name, value)

    def execute(self, code, timeout=30, input_files=None):
        from backend.contracts import WorkbenchError
        from router.sandbox import SandboxResult
        if self.deadline is not None and time.perf_counter() >= self.deadline:
            raise WorkbenchError('timeout', 'Benchmark deadline exceeded before validation')
        result = self._sandbox.execute(code, timeout=timeout, input_files=input_files)
        if should_stop({'stderr': result.stderr}):
            raise WorkbenchError('timeout', 'Product sandbox validation timed out')
        if not result.executed:
            raise WorkbenchError('sandbox_unavailable', 'Product sandbox did not execute')
        if result.exit_code != 0:
            self.trajectory.append({'phase': 'product_validation', 'artifact_verified': False, 'exit_code': result.exit_code})
            return result
        files = input_files or {}
        original = self.case['context']['initial_files']
        allowed = set(self.case['allowed_change_paths'])
        if any(name not in allowed and (name not in original or content != original[name].encode()) for name, content in files.items()):
            raise ValueError('Validation candidate contains a fixture-protected path')
        if any(name not in allowed and name not in files for name in original):
            raise ValueError('Validation candidate removed a fixture-protected source')
        remaining = self.timeout if self.deadline is None else min(self.timeout, self.deadline - time.perf_counter())
        if remaining <= 0:
            raise WorkbenchError('timeout', 'Benchmark deadline exceeded before trusted tests')
        validation = validate_candidate(self.case, files, self._sandbox, remaining)
        self.trajectory.append({'phase': 'trusted_tests', **validation,
                                'candidate_hashes': {name: hashlib.sha256(content).hexdigest() for name, content in files.items()}})
        if not validation['container_executed']:
            raise WorkbenchError('sandbox_unavailable', 'Independent trusted tests did not execute')
        if validation['artifact_verified']:
            return result
        # V3 feedback adds safe runtime diagnostics; V1/V2 evidence is immutable.
        # Traceback frames, oracle source and arbitrary messages stay offline.
        diagnostic = hashlib.sha256(validation['stderr'].encode()).hexdigest()
        return SandboxResult(validation['exit_code'] or 1, '',
                             'Independent trusted validation failed (exit=' + str(validation['exit_code']) +
                             '; diagnostic_sha256=' + diagnostic + '): ' +
                             safe_repair_diagnostic(validation['stderr'], files), True)

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()

def verified_image_path(case, dataset_path):
    """Resolve frozen image evidence inside its dataset directory."""
    context = case.get('context') or {}
    relative = context.get('image_path')
    if relative is None:
        return None
    parent = Path(dataset_path).resolve().parent
    source = Path(relative)
    if source.is_absolute() or source.drive:
        raise ValueError('Dataset image path must be relative')
    image = (parent / source).resolve()
    if not image.is_relative_to(parent):
        raise ValueError('Dataset image path escapes dataset directory')
    expected = context.get('image_sha256')
    if not expected or hashlib.sha256(image.read_bytes()).hexdigest() != expected:
        raise ValueError('Dataset image hash mismatch')
    return str(image)


def load_dataset(path):
    dataset = json.loads(path.read_text(encoding='utf-8'))
    provenance = json.loads((path.parent / 'provenance.json').read_text(encoding='utf-8'))
    entry = next(item for item in provenance['datasets'] if item['file'] == path.name)
    if digest(dataset) != entry['canonical_sha256'] or hashlib.sha256(path.read_bytes()).hexdigest() != entry['file_sha256']:
        raise ValueError('Frozen dataset hash mismatch')
    if len(dataset['cases']) != entry['case_count']:
        raise ValueError('Fixture count mismatch')
    for case in dataset['cases']:
        verified_image_path(case, path)
    return dataset

def configure_arm(workbench, arm):
    workbench.routing_strategy = 'fixed' if arm == 'D' else 'universal'
    if ARMS[arm]:
        original = workbench._lease
        role = ARMS[arm]
        def pinned(capability, required_context=None, worker_role=None):
            # Text modality permits all three installed worker roles in broker.
            return original('vision' if capability == 'vision' else 'text',
                            required_context=required_context, worker_role=role)
        workbench._lease = pinned

def candidate_files(case, result):
    files = dict(case['context']['initial_files'])
    for change in result.get('changes', []):
        path = change['path']
        if path not in case['allowed_change_paths']:
            raise ValueError('Candidate changed a fixture-protected path: ' + path)
        if change.get('before') != files.get(path):
            raise ValueError('Candidate source snapshot mismatch: ' + path)
        if change.get('after') is None:
            files.pop(path, None)
        else:
            files[path] = change['after']
    return files

def validate_candidate(case, files, sandbox, timeout):
    oracle = case['oracle']
    inputs = {'candidate/' + name: content if isinstance(content, bytes) else content.encode() for name, content in files.items()}
    inputs.update({'trusted/' + name: content.encode() for name, content in oracle['trusted_files'].items()})
    command = oracle['command']
    if command[0] != 'python' or len(command) != 2 or command[1] not in oracle['trusted_files']:
        raise ValueError('Unsupported trusted command')
    script = ('import os, sys, runpy, shutil\n'
              'shutil.copytree("/input/candidate", "/output/candidate")\n'
              'os.chdir("/output/candidate")\n'
              'sys.path.insert(0, "/output/candidate")\n'
              'runpy.run_path(' + repr('/input/trusted/' + command[1]) + ', run_name="__main__")\n')
    execution = sandbox.execute(script, timeout=min(120, max(1, int(timeout))), input_files=inputs)
    if not execution.executed:
        from backend.contracts import WorkbenchError
        raise WorkbenchError('sandbox_unavailable', 'Independent trusted validation did not execute')
    if execution.exit_code == -1 and ('timed out' in execution.stderr.casefold() or 'stopped' in execution.stderr.casefold()):
        from backend.contracts import WorkbenchError
        raise WorkbenchError('timeout', 'Independent sandbox validation stopped or timed out')
    return {'artifact_verified': execution.executed is True and execution.exit_code == oracle['expected_exit_code'],
            'container_executed': execution.executed, 'exit_code': execution.exit_code,
            'stdout': execution.stdout, 'stderr': execution.stderr,
            'trusted_hashes': {name: hashlib.sha256(content.encode()).hexdigest() for name, content in oracle['trusted_files'].items()}}

def should_stop(result):
    error = result.get('error', {})
    return (error.get('code') in {'sandbox_unavailable', 'docker_unavailable', 'cancelled', 'timeout', 'supervisor_timeout'}
            or 'execution timed out' in str(result.get('stderr', '')).casefold()
            or (error.get('code') == 'supervisor_budget' and any(word in str(error.get('message', '')).casefold() for word in ('time', 'deadline'))))

def resume_rows(previous, provenance):
    if previous.get('provenance', {}).get('compatibility_sha256') != provenance['compatibility_sha256']:
        raise ValueError('Resume rejected: fixtures, code, profiles, settings or scope changed')
    return previous.get('rows', [])

def capture(case, workbench, args):
    image_path = verified_image_path(case, args.dataset) if case.get('context', {}).get('image_path') is not None else None
    if not case.get('execution_supported', True):
        return {'case_id': case['id'], 'gate': 'NOT_VERIFIED', 'reason': case.get('execution_limitation'), 'correctness': None}
    workspace = workbench.coding.create('smart-' + case['id'])
    wid = workspace['workspace_id']
    for name, content in case['context']['initial_files'].items():
        workbench.coding.write(wid, name, content)
    job = shared.BenchmarkJob(args.timeout)
    # Coding execution streams into append; the shared job exposes progress.
    job.append = job.progress
    probe = shared.ResourceProbe(args.sample_resources)
    started = time.perf_counter()
    original_factory = workbench._verified_coding_sandbox
    proxies = []
    if case['oracle']['kind'] == 'trusted_tests':
        def trusted_factory():
            proxy = TrustedSandboxProxy(original_factory(), case, args.timeout, started + args.timeout)
            proxies.append(proxy)
            return proxy
        workbench._verified_coding_sandbox = trusted_factory
    validation = {'artifact_verified': None, 'semantic_review_required': case['oracle'].get('semantic_review_required', False)}
    try:
        image_options = {'image_path': verified_image_path(case, args.dataset)} if image_path else {}
        result = workbench.run_coding_project_task(wid, case['context'].get('active_file', ''), case['request'],
                                                 job=job, history=case.get('history', case['context'].get('history', [])), **image_options)
        original_preserved = all(workbench.coding.read(wid, name)['content'] == content
                                 for name, content in case['context']['initial_files'].items())
        validation['original_sources_preserved'] = original_preserved
        if case['oracle']['kind'] == 'trusted_tests' and result.get('state') == 'completed':
            candidate = candidate_files(case, result)
            remaining = args.timeout - (time.perf_counter() - started)
            if remaining <= 0:
                from backend.contracts import WorkbenchError
                raise WorkbenchError('timeout', 'Deadline exceeded before final independent validation')
            validation.update(validate_candidate(case, candidate, original_factory(), remaining))
            if not original_preserved:
                validation['artifact_verified'] = False
        if job.cancel.is_set():
            result['error'] = {'code': 'timeout', 'message': 'Benchmark deadline exceeded'}
    except Exception as error:
        result = {'error': {'code': getattr(error, 'code', type(error).__name__), 'message': str(error)}}
    finally:
        workbench._verified_coding_sandbox = original_factory
        job.close()
        resources = probe.close()
    supervisor = result.get('supervisor') or {}
    if not supervisor:
        saved = sorted((workbench.settings.data_dir / 'supervision').glob('*.json'), key=lambda path: path.stat().st_mtime, reverse=True)
        for path in saved[:3]:
            snapshot = json.loads(path.read_text(encoding='utf-8'))
            if snapshot.get('goal') == case['request']:
                supervisor = snapshot
                break
    counts = supervisor.get('counts') or {}
    task_state = supervisor.get('task_state') or {}
    events = supervisor.get('events') or []
    repair = any(event.get('type', event.get('event', event.get('name'))) == 'REPAIR_STARTED' for event in events)
    attempts = result.get('supervisor_attempts')
    if attempts is not None:
        repair = repair or attempts > 1
    trajectory = [entry for proxy in proxies for entry in proxy.trajectory]
    observed_failure = any(entry['artifact_verified'] is False for entry in trajectory)
    observed_recovery = observed_failure and bool(trajectory) and trajectory[-1]['artifact_verified'] is True
    return {'case_id': case['id'], 'fixture_sha256': digest(case), 'category': case['category'],
            'gate': 'STOP' if should_stop(result) else 'FAIL' if result.get('error') else 'EXECUTED',
            'stage': 'READY_FOR_REVIEW' if result.get('state') == 'completed' else result.get('state'),
            'correctness': validation.get('artifact_verified'), 'validation': validation,
            'goal_satisfied': None if validation.get('semantic_review_required') else validation.get('artifact_verified'),
            'prediction': {'task_type': task_state.get('task_type'), 'complexity': task_state.get('complexity'),
                           'worker_role': task_state.get('worker_role'), 'active_worker': task_state.get('active_worker')},
            'expected': {'task_type': case.get('expected_task_type'), 'complexity': case.get('complexity'),
                         'suitable_workers': case.get('expected_suitable_workers')},
            'repair_observed': repair if events or attempts is not None else None,
            'repair_succeeded': bool(observed_recovery and validation.get('artifact_verified')) if repair else None,
            'validation_trajectory': trajectory,
            'measurements': {'latency_seconds': time.perf_counter() - started,
                             **{name: counts.get(name) for name in ('model_calls', 'model_switches', 'tool_calls')}, **resources},
            'operational_result': result, 'telemetry': supervisor,
            'publication': 'NOT_ACCEPTED', 'resource_scope': 'Python plus all llama-server RSS; total device VRAM'}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, default=ROOT / 'benchmarks/smart-code-router/main.json')
    parser.add_argument('--live', action='store_true', help='Explicitly run installed workers and verified Docker')
    parser.add_argument('--strategies', nargs='+', choices=list(ARMS), default=list(ARMS))
    parser.add_argument('--case-ids', nargs='+')
    parser.add_argument('--categories', nargs='+')
    parser.add_argument('--limit', type=int)
    parser.add_argument('--timeout', type=float, default=900)
    parser.add_argument('--model-url', default='http://127.0.0.1:8087')
    parser.add_argument('--model-port', type=int, default=8087)
    parser.add_argument('--sample-resources', action='store_true')
    parser.add_argument('--output', type=Path, default=ROOT / 'benchmarks/smart-code-router-results.json')
    parser.add_argument('--resume', type=Path)
    parser.add_argument('--backend-url', default='http://127.0.0.1:8765')
    parser.add_argument('--backend-job-ids', nargs='*', help='Known UI backend job IDs to check before running; backend has no list-active API')
    args = parser.parse_args()
    dataset = load_dataset(args.dataset)
    cases = [case for case in dataset['cases'] if (not args.case_ids or case['id'] in args.case_ids)
             and (not args.categories or case['category'] in args.categories)]
    if args.limit is not None:
        cases = cases[:args.limit]
    if not args.live:
        print(json.dumps({'mode': 'validate-only', 'frozen_cases': len(dataset['cases']), 'selected_cases': len(cases), 'dataset_sha256': digest(dataset)}))
        return
    if os.environ.get('SOVEREIGN_KNOWLEDGE_DIR'):
        raise RuntimeError('Unset SOVEREIGN_KNOWLEDGE_DIR before isolated execution')
    with LiveSuiteLock(ROOT / 'data/smart-code-router-live.lock'):
        run_live(args, dataset, cases)

def run_live(args, dataset, cases):
    from backend.settings import Settings
    from backend.service import Workbench
    from router.model_registry import ModelRegistry
    settings = Settings(model_url=args.model_url, supervisor_seconds=args.timeout)
    idle_check = check_backend_idle(settings, args.backend_url, args.backend_job_ids)
    provenance = shared.run_provenance(dataset, args, settings, ModelRegistry(args.model_port))
    provenance['repair_feedback_policy'] = REPAIR_FEEDBACK_POLICY
    provenance['production_sha256'][str(Path(__file__).relative_to(ROOT)).replace('\\', '/')] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    provenance['arm_policy'] = ARMS
    provenance['backend_url'] = args.backend_url
    provenance['backend_job_ids'] = args.backend_job_ids
    provenance['compatibility_sha256'] = digest({key: value for key, value in provenance.items() if key not in ('started_at_utc', 'compatibility_sha256')})
    rows = resume_rows(json.loads(args.resume.read_text()), provenance) if args.resume else []
    report = {'mode': 'live', 'provenance': provenance, 'rows': rows, 'backend_idle_check': idle_check,
              'state': 'INITIALIZED', 'checkpoint': None,
              'limitations': ['Rubrics require independent semantic review', 'Contracts reused across categories; clustered uncertainty required', 'READY_FOR_REVIEW is not publication']}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    shared.atomic_report(args.output, report)
    for arm in args.strategies:
        with TemporaryDirectory(prefix='smart-code-benchmark-') as temporary:
            directory = Path(temporary)
            isolated = Settings(data_dir=directory / 'data', project_dir=directory / 'projects', model_url=args.model_url, supervisor_seconds=args.timeout)
            isolated.data_dir.mkdir(parents=True, exist_ok=True)
            verification = settings.data_dir / 'sandbox-validation.json'
            if verification.is_file():
                shutil.copyfile(verification, isolated.data_dir / verification.name)
            workbench = Workbench(settings=isolated, registry=ModelRegistry(args.model_port))
            configure_arm(workbench, arm)
            for case in cases:
                if any(row['arm'] == arm and row['case_id'] == case['id'] for row in rows):
                    continue
                report.update(state='RUNNING', checkpoint={'arm': arm, 'case_id': case['id'], 'fixture_sha256': digest(case), 'started_at': time.time()})
                shared.atomic_report(args.output, report)
                if case.get('context', {}).get('image_path') is not None and arm in {'A', 'B', 'C'}:
                    row = {'case_id': case['id'], 'fixture_sha256': digest(case), 'category': case['category'],
                           'gate': 'NOT_VERIFIED', 'reason': 'Pinned worker does not support vision', 'correctness': None}
                else:
                    row = capture(case, workbench, args)
                row['arm'] = arm
                rows.append(row)
                report['summary'] = summarize(rows)
                report.update(state='STOPPED' if row['gate'] == 'STOP' else 'CHECKPOINTED', checkpoint={'arm': arm, 'case_id': case['id'], 'completed_at': time.time()})
                shared.atomic_report(args.output, report)
                print(json.dumps({key: row.get(key) for key in ('arm', 'case_id', 'gate', 'stage', 'correctness')}), flush=True)
                if row['gate'] == 'STOP':
                    return
    report.update(state='COMPLETED', checkpoint=None)
    report['summary'] = summarize(rows)
    shared.atomic_report(args.output, report)

if __name__ == '__main__':
    main()
