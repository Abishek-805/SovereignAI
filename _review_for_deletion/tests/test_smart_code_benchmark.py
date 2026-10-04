import importlib.util
from pathlib import Path
from types import SimpleNamespace
import pytest

PATH = Path(__file__).resolve().parents[1] / 'benchmarks/evaluate-smart-code-router.py'

def harness():
    spec = importlib.util.spec_from_file_location('smart_benchmark', PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def test_pin_every_lease_through_role():
    module = harness()
    calls = []
    wb = SimpleNamespace(_lease=lambda capability, **kw: calls.append((capability, kw)))
    module.configure_arm(wb, 'A')
    wb._lease('code', worker_role='code')
    wb._lease('text', worker_role='reasoning')
    assert calls == [('text', {'required_context': None, 'worker_role': 'lightweight'})] * 2

def test_candidate_does_not_publish_or_admit_unallowed_paths():
    module = harness()
    case = {'context': {'initial_files': {'solution.py': 'original'}}, 'allowed_change_paths': ['solution.py']}
    assert module.candidate_files(case, {'changes': [{'path': 'solution.py', 'before': 'original', 'after': 'fixed'}]}) == {'solution.py': 'fixed'}
    with pytest.raises(ValueError):
        module.candidate_files(case, {'changes': [{'path': 'test_contract.py', 'after': 'fake'}]})

def test_trusted_validation_only_external_readonly_input():
    module = harness()
    calls = []
    sandbox = SimpleNamespace(execute=lambda code, **kw: calls.append((code, kw)) or SimpleNamespace(executed=True, exit_code=0, stdout='', stderr=''))
    case = {'oracle': {'trusted_files': {'test_contract.py': 'assert True'}, 'command': ['python', 'test_contract.py'], 'expected_exit_code': 0}}
    result = module.validate_candidate(case, {'solution.py': 'pass'}, sandbox, 30)
    assert result['artifact_verified'] is True
    assert calls[0][1]['input_files']['trusted/test_contract.py'] == b'assert True'
    assert 'runpy.run_path' in calls[0][0]

def test_resume_rejects_changed_provenance():
    module = harness()
    with pytest.raises(ValueError):
        module.resume_rows({'provenance': {'compatibility_sha256': 'old'}}, {'compatibility_sha256': 'new'})

def test_all_fixed_workers_and_prior_policy():
    module = harness()
    for arm, role in [('A', 'lightweight'), ('B', 'reasoning'), ('C', 'code')]:
        calls = []
        wb = SimpleNamespace(_lease=lambda capability, **kw: calls.append((capability, kw)))
        module.configure_arm(wb, arm)
        wb._lease('text', worker_role='lightweight')
        assert calls[0][1]['worker_role'] == role
    for arm, strategy in [('D', 'fixed'), ('E', 'universal')]:
        original = lambda *args, **kw: None
        wb = SimpleNamespace(_lease=original)
        module.configure_arm(wb, arm)
        assert wb._lease is original
        assert wb.routing_strategy == strategy

def test_external_sandbox_timeout_stops():
    module = harness()
    sandbox = SimpleNamespace(execute=lambda *args, **kw: SimpleNamespace(executed=True, exit_code=-1, stdout='', stderr='Execution timed out'))
    case = {'oracle': {'trusted_files': {'test_contract.py': 'assert True'}, 'command': ['python', 'test_contract.py'], 'expected_exit_code': 0}}
    with pytest.raises(Exception) as error:
        module.validate_candidate(case, {'solution.py': 'pass'}, sandbox, 30)
    assert error.value.code == 'timeout'

def test_frozen_main_validates_without_live():
    module = harness()
    dataset = module.load_dataset(PATH.parent / 'smart-code-router/main.json')
    assert len(dataset['cases']) == 100
    assert module.should_stop({'error': {'code': 'sandbox_unavailable'}})
    assert module.should_stop({'error': {'code': 'cancelled'}})

def test_trusted_proxy_feeds_real_failure_without_assertion_source():
    module = harness()
    from router.sandbox import SandboxResult
    results = iter([SandboxResult(0, 'syntax ok', '', True), SandboxResult(1, '', 'assert SECRET_ORACLE\nAssertionError', True)])
    calls = []
    sandbox = SimpleNamespace(execute=lambda code, **kw: calls.append(kw) or next(results), _ready=lambda: None)
    case = {'context': {'initial_files': {'solution.py': 'pass'}}, 'allowed_change_paths': ['solution.py'],
            'oracle': {'trusted_files': {'test_contract.py': 'assert SECRET_ORACLE'}, 'command': ['python', 'test_contract.py'], 'expected_exit_code': 0}}
    proxy = module.TrustedSandboxProxy(sandbox, case, 30)
    result = proxy.execute('syntax check', input_files={'solution.py': b'pass'})
    assert result.executed and result.exit_code == 1
    assert 'SECRET_ORACLE' not in result.stderr
    assert proxy.trajectory[0]['artifact_verified'] is False
    assert 'trusted/test_contract.py' not in calls[0]['input_files']


def test_repair_diagnostic_retains_undefined_name_without_private_traceback():
    module = harness()
    stderr = ('Traceback (most recent call last):\n'
              '  File "/trusted/SECRET_ORACLE.py", line 9, in <module>\n'
              '    assert execute(SECRET_EXPECTED) == SECRET_RESULT\n'
              "NameError: name 'solution' is not defined\n")
    assert module.safe_repair_diagnostic(stderr, {'service.py': b'return solution.rotate(items)'}) == "NameError: name 'solution' is not defined"
    assert module.safe_repair_diagnostic("NameError: name 'SECRET_ORACLE' is not defined", {'service.py': b'pass'}) == 'NameError'


def test_proxy_v3_runtime_feedback_preserves_offline_evidence_and_fingerprint():
    module = harness()
    from router.sandbox import SandboxResult
    import hashlib
    stderr = ('Traceback (most recent call last):\n'
              '  File "/trusted/private.py", line 2\n'
              '    assert SECRET_EXPECTED == execute()\n'
              "NameError: name 'solution' is not defined\n")
    results = iter([SandboxResult(0, '', '', True), SandboxResult(1, '', stderr, True)])
    sandbox = SimpleNamespace(execute=lambda *args, **kw: next(results))
    case = {'context': {'initial_files': {'service.py': 'return solution.rotate(items)'}},
            'allowed_change_paths': ['service.py'],
            'oracle': {'trusted_files': {'test_contract.py': 'assert SECRET_EXPECTED'},
                       'command': ['python', 'test_contract.py'], 'expected_exit_code': 0}}
    proxy = module.TrustedSandboxProxy(sandbox, case, 30)
    result = proxy.execute('check', input_files={'service.py': b'return solution.rotate(items)'})
    assert "NameError: name 'solution' is not defined" in result.stderr
    assert hashlib.sha256(stderr.encode()).hexdigest() in result.stderr
    assert 'SECRET_EXPECTED' not in result.stderr and '/trusted/' not in result.stderr
    assert proxy.trajectory[0]['stderr'] == stderr


@pytest.mark.parametrize('stderr,expected', [
    ('AssertionError: expected SECRET_VALUE at /trusted/test.py', 'AssertionError'),
    ('ValueError: SECRET_ORACLE expected 42', 'ValueError'),
    ('RuntimeError: /trusted/private.py SECRET_VALUE', 'RuntimeError'),
    ('CustomError: secret', 'unclassified validation failure'),
    ('TypeError: unsupported operand type(s) for +: \'int\' and \'str\'',
     'TypeError: unsupported operand type(s) for +: \'int\' and \'str\''),
    ('NameError: name \'SECRET_ORACLE\' is not defined\nprivate trailing text',
     'unclassified validation failure'),
])
def test_repair_diagnostic_never_echoes_arbitrary_oracle_messages(stderr, expected):
    assert harness().safe_repair_diagnostic(stderr) == expected

def test_live_lock_excludes_second_owner(tmp_path):
    module = harness()
    with module.LiveSuiteLock(tmp_path / 'suite.lock'):
        with pytest.raises(RuntimeError):
            with module.LiveSuiteLock(tmp_path / 'suite.lock'):
                pass

def test_proxy_checks_fixture_owned_paths_before_tests():
    module = harness()
    from router.sandbox import SandboxResult
    sandbox = SimpleNamespace(execute=lambda *args, **kw: SandboxResult(0, '', '', True))
    case = {'context': {'initial_files': {'solution.py': 'pass'}}, 'allowed_change_paths': ['solution.py'], 'oracle': {}}
    with pytest.raises(ValueError):
        module.TrustedSandboxProxy(sandbox, case, 30).execute('check', input_files={'test_contract.py': b'fake'})

def test_proxy_records_actual_failure_then_pass():
    module = harness()
    from router.sandbox import SandboxResult
    results = iter([SandboxResult(0, '', '', True), SandboxResult(1, '', 'AssertionError', True),
                    SandboxResult(0, '', '', True), SandboxResult(0, 'trusted passed', '', True)])
    sandbox = SimpleNamespace(execute=lambda *args, **kw: next(results))
    case = {'context': {'initial_files': {'solution.py': 'pass'}}, 'allowed_change_paths': ['solution.py'],
            'oracle': {'trusted_files': {'test_contract.py': 'assert True'}, 'command': ['python', 'test_contract.py'], 'expected_exit_code': 0}}
    proxy = module.TrustedSandboxProxy(sandbox, case, 30)
    assert proxy.execute('check', input_files={'solution.py': b'pass'}).exit_code == 1
    assert proxy.execute('check', input_files={'solution.py': b'fixed'}).exit_code == 0
    assert [entry['artifact_verified'] for entry in proxy.trajectory] == [False, True]
    assert proxy.trajectory[0]['stderr'] == 'AssertionError'
    assert proxy.trajectory[1]['stdout'] == 'trusted passed'
    assert proxy.trajectory[0]['candidate_hashes'] != proxy.trajectory[1]['candidate_hashes']

def test_initial_backend_supervisor_check_blocks_running(tmp_path):
    module = harness()
    import json
    (tmp_path / 'supervision').mkdir()
    (tmp_path / 'supervision/job.json').write_text(json.dumps({'outcome': 'running', 'supervisor_id': 'active'}))
    with pytest.raises(RuntimeError, match='active'):
        module.check_backend_idle(SimpleNamespace(data_dir=tmp_path), 'http://unused', [])


def test_summary_separates_routing_from_task_correctness_and_unknowns():
    module = harness()
    expected = {'task_type': 'bugfix', 'complexity': 'medium', 'suitable_workers': ['code', 'reasoning']}
    rows = [
        {'arm': 'E', 'expected': expected, 'prediction': {'task_type': 'bugfix', 'complexity': 'medium', 'worker_role': 'reasoning'}, 'correctness': False, 'measurements': {'latency_seconds': 2}},
        {'arm': 'E', 'expected': expected, 'prediction': {'task_type': 'feature', 'complexity': 'medium', 'worker_role': 'lightweight'}, 'correctness': True, 'measurements': {'latency_seconds': 4}},
        {'arm': 'E', 'expected': expected, 'prediction': {'task_type': 'bugfix'}, 'correctness': None},
        {'arm': 'E', 'prediction': {'task_type': 'bugfix', 'complexity': 'medium', 'worker_role': 'code'}, 'correctness': None},
    ]
    summary = module.summarize(rows)['E']
    assert summary['routing']['classification_exact'] == {'cases': 4, 'evaluated': 2, 'unknown': 2, 'correct': 1, 'incorrect': 1, 'accuracy': .5}
    assert summary['routing']['task_type_exact']['evaluated'] == 3
    assert summary['routing']['task_type_exact']['accuracy'] == 2 / 3
    assert summary['routing']['complexity_exact']['evaluated'] == 2
    assert summary['routing']['worker_suitability']['accuracy'] == .5
    assert summary['routing']['worker_suitability']['unknown'] == 2
    assert summary['trusted_artifacts_evaluated'] == 2
    assert summary['trusted_artifact_accuracy'] == .5
    assert summary['correctness_unknown'] == 2
    assert summary['latency_observed_cases'] == 2
    assert summary['latency_unknown_cases'] == 2
    assert summary['latency_p50_seconds'] == 3
    assert summary['latency_p95_seconds'] == pytest.approx(3.9)


def test_summary_does_not_invent_observations_for_empty_or_unverified_arms():
    module = harness()
    summary = module.summarize([{'arm': 'A', 'gate': 'NOT_VERIFIED'}])
    for arm, count in [('A', 1), ('B', 0)]:
        assert summary[arm]['trusted_artifact_accuracy'] is None
        assert summary[arm]['latency_p50_seconds'] is None
        assert summary[arm]['latency_p95_seconds'] is None
        assert summary[arm]['latency_observed_cases'] == 0
        assert summary[arm]['latency_unknown_cases'] == count
        for metric in summary[arm]['routing'].values():
            assert metric['accuracy'] is None
            assert metric['evaluated'] == 0
            assert metric['unknown'] == count


def test_worker_suitability_accepts_any_expected_role_without_task_success():
    module = harness()
    rows = [{'prediction': {'worker_role': role}, 'expected': {'suitable_workers': ['code', 'reasoning']}, 'correctness': False}
            for role in ['code', 'reasoning', 'lightweight']]
    rows.append({'prediction': {'worker_role': 'code'}, 'expected': {'suitable_workers': []}})
    result = module.routing_metrics(rows)['worker_suitability']
    assert result == {'cases': 4, 'evaluated': 3, 'unknown': 1, 'correct': 2, 'incorrect': 1, 'accuracy': 2 / 3}


def test_dataset_image_is_confined_and_hash_verified(tmp_path):
    import hashlib
    module = harness()
    image = tmp_path / 'diagram.png'
    image.write_bytes(b'frozen image')
    case = {'context': {'image_path': 'diagram.png', 'image_sha256': hashlib.sha256(image.read_bytes()).hexdigest()}}
    assert module.verified_image_path(case, tmp_path / 'supplemental.json') == str(image.resolve())
    image.write_bytes(b'changed')
    with pytest.raises(ValueError, match='hash mismatch'):
        module.verified_image_path(case, tmp_path / 'supplemental.json')
    for path in ['../escape.png', str(image.resolve())]:
        case['context']['image_path'] = path
        with pytest.raises(ValueError, match='relative|escapes'):
            module.verified_image_path(case, tmp_path / 'supplemental.json')
    assert module.verified_image_path({'context': {}}, tmp_path / 'supplemental.json') is None


def test_capture_passes_verified_optional_image_before_model_call(tmp_path, monkeypatch):
    import hashlib
    module = harness()
    image = tmp_path / 'diagram.png'
    image.write_bytes(b'image')
    case = {'id': 'vision', 'category': 'vision', 'request': 'inspect diagram',
            'context': {'initial_files': {}, 'image_path': 'diagram.png', 'image_sha256': hashlib.sha256(b'image').hexdigest()},
            'oracle': {'kind': 'rubric'}}
    calls = []
    wb = SimpleNamespace(coding=SimpleNamespace(create=lambda name: {'workspace_id': 'w'}),
                         _verified_coding_sandbox=lambda: None,
                         run_coding_project_task=lambda *a, **kw: calls.append(kw) or {'supervisor': {'task_state': {}}},
                         settings=SimpleNamespace(data_dir=tmp_path))
    monkeypatch.setattr(module.shared, 'BenchmarkJob', lambda timeout: SimpleNamespace(progress=lambda *a: None, close=lambda: None, cancel=SimpleNamespace(is_set=lambda: False)))
    monkeypatch.setattr(module.shared, 'ResourceProbe', lambda enabled: SimpleNamespace(close=lambda: {}))
    args = SimpleNamespace(dataset=tmp_path / 'supplemental.json', timeout=30, sample_resources=False)
    module.capture(case, wb, args)
    assert calls[0]['image_path'] == str(image.resolve())
    image.write_bytes(b'tampered')
    with pytest.raises(ValueError, match='hash mismatch'):
        module.capture(case, wb, args)
    assert len(calls) == 1
    case['context'].pop('image_path')
    module.capture(case, wb, args)
    assert 'image_path' not in calls[-1]
