import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('universal_eval', ROOT/'benchmarks/evaluate-universal-agent.py')
evaluation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluation)
DATASET = json.loads((ROOT/'benchmarks/universal-agent-fixtures.json').read_text(encoding='utf-8'))


def test_atomic_report_preserves_old_report_when_serialization_fails(tmp_path):
    path = tmp_path/'report.json'
    evaluation.atomic_report(path, {'previous': True})
    cyclic = []
    cyclic.append(cyclic)
    with pytest.raises(ValueError):
        evaluation.atomic_report(path, {'broken': cyclic})
    assert json.loads(path.read_text()) == {'previous': True}
    evaluation.atomic_report(path, {'replacement': True})
    assert json.loads(path.read_text()) == {'replacement': True}
    assert not path.with_name(path.name + '.tmp').exists()


def test_atomic_report_retries_transient_windows_lock_without_reexecuting(tmp_path, monkeypatch):
    path = tmp_path/'report.json'
    original_replace = Path.replace
    attempts = []
    delays = []
    def temporarily_locked(source, target):
        attempts.append(json.loads(source.read_text()))
        if len(attempts) < 3:
            raise PermissionError('transient file lock')
        return original_replace(source, target)
    monkeypatch.setattr(Path, 'replace', temporarily_locked)
    monkeypatch.setattr(evaluation.time, 'sleep', delays.append)
    evaluation.atomic_report(path, {'completed_task': True})
    assert attempts == [{'completed_task': True}] * 3
    assert delays == [0.1, 0.2]
    assert json.loads(path.read_text()) == {'completed_task': True}


def test_atomic_report_persistent_lock_preserves_previous_and_pending(tmp_path, monkeypatch):
    path = tmp_path/'report.json'
    evaluation.atomic_report(path, {'previous': True})
    def locked(source, target):
        raise PermissionError('persistent file lock')
    monkeypatch.setattr(Path, 'replace', locked)
    monkeypatch.setattr(evaluation.time, 'sleep', lambda delay: None)
    with pytest.raises(PermissionError):
        evaluation.atomic_report(path, {'pending': True})
    assert json.loads(path.read_text()) == {'previous': True}
    assert json.loads(path.with_name(path.name + '.tmp').read_text()) == {'pending': True}


def test_resume_rejects_changed_provenance_and_dataset():
    provenance = {'compatibility_sha256': 'frozen'}
    report = {**evaluation.compare(DATASET, {'A': []}, 'live'), 'provenance': provenance}
    assert evaluation.resume_captures(report, DATASET, provenance) == {'A': []}
    with pytest.raises(ValueError, match='production code'):
        evaluation.resume_captures(report, DATASET, {'compatibility_sha256': 'changed'})
    with pytest.raises(ValueError, match='identical live dataset'):
        evaluation.resume_captures(report, {**DATASET, 'kind': 'changed'}, provenance)


def test_run_provenance_records_profiles_settings_and_code_without_weight_hashes():
    from argparse import Namespace
    from backend.settings import Settings
    from router.model_registry import ModelRegistry
    args = Namespace(model_url='http://127.0.0.1:8087', timeout=300, strategies=['A','B','C'],
                     categories=None, limit=0, sample_resources=True)
    settings = Settings(supervisor_seconds=300)
    provenance = evaluation.run_provenance(DATASET, args, settings, ModelRegistry())
    assert provenance['production_sha256']['backend/service.py']
    assert provenance['settings']['supervisor_seconds'] == 300
    assert provenance['settings']['output_tokens'] == settings.output_tokens
    assert provenance['started_at_utc']
    assert all(profile['model_id'] and profile['slots'] == 1 and profile['launch_arguments']
               for profile in provenance['profiles'])
    assert all(not path.endswith('.gguf') for path in provenance['production_sha256'])


def test_case_id_filter_intersects_categories_before_limit():
    from argparse import Namespace
    args = Namespace(case_ids=['rag-02', 'simple-01', 'rag-01'], categories=['rag'], limit=1)
    assert [case['id'] for case in evaluation.selected_cases(DATASET, args)] == ['rag-01']
    args.limit = 0
    args.case_ids = ['rag-02']
    assert [case['id'] for case in evaluation.selected_cases(DATASET, args)] == ['rag-02']
    args.case_ids = ['missing-fixture']
    with pytest.raises(ValueError, match='Unknown case IDs: missing-fixture'):
        evaluation.selected_cases(DATASET, args)


def test_case_id_selection_changes_run_provenance():
    from argparse import Namespace
    from backend.settings import Settings
    from router.model_registry import ModelRegistry
    args = Namespace(timeout=300, strategies=['C'], categories=None, case_ids=['rag-01'],
                     limit=0, sample_resources=False)
    first = evaluation.run_provenance(DATASET, args, Settings(), ModelRegistry())
    args.case_ids = ['rag-02']
    second = evaluation.run_provenance(DATASET, args, Settings(), ModelRegistry())
    assert first['case_ids'] == ['rag-01']
    assert first['compatibility_sha256'] != second['compatibility_sha256']


@pytest.mark.parametrize('query', [None, [], ['bad'], 'bad'])
def test_missing_table_query_is_failure_without_crashing(query):
    case = fixture('table')
    assert evaluation.inspect_result(case, {'sources': [{'query_result': query}]})['goal_satisfied'] is False


def test_valid_table_query_keeps_narrow_oracle_success():
    case = fixture('table')
    oracle = case['oracle']
    query = {key: oracle[key] for key in ('operation','value','scanned_rows')}
    assert evaluation.inspect_result(case, {'sources': [{'query_result': None}, {'query_result': query}]})['goal_satisfied'] is True


def test_harness_repair_resume_requires_explicit_flag_and_identical_production():
    from copy import deepcopy
    old = {'dataset_sha256': evaluation.digest(DATASET), 'production_sha256':
           {'backend/service.py':'prod', 'benchmarks/evaluate-universal-agent.py':'old'},
           'profiles':[{'model_id':'worker','context':2048}], 'settings':{'output_tokens':10},
           'timeout_seconds':300,'strategies':['A','B','C'],'categories':None,'case_ids':None,
           'limit':0,'sample_resources':True,'generation_policy':'workflow','git_head':'old-head',
           'compatibility_sha256':'old-hash'}
    new = deepcopy(old)
    new.update(git_head='new-head', compatibility_sha256='new-hash')
    new['production_sha256']['benchmarks/evaluate-universal-agent.py'] = 'repaired'
    report = {**evaluation.compare(DATASET, {'A': []}, 'live'), 'provenance': old}
    with pytest.raises(ValueError):
        evaluation.resume_captures(report, DATASET, new)
    assert evaluation.resume_captures(report, DATASET, new, True) == {'A': []}
    for key, value in [('settings',{'output_tokens':11}), ('profiles',[{'model_id':'worker','context':4096}]),
                       ('case_ids',['rag-02']), ('timeout_seconds',120), ('dataset_sha256','different')]:
        changed = deepcopy(new)
        changed[key] = value
        with pytest.raises(ValueError):
            evaluation.resume_captures(report, DATASET, changed, True)
    changed = deepcopy(new)
    changed['production_sha256']['backend/service.py'] = 'changed-production'
    with pytest.raises(ValueError):
        evaluation.resume_captures(report, DATASET, changed, True)
    changed['production_sha256'] = {'benchmarks/evaluate-universal-agent.py':'only-harness'}
    assert not evaluation.harness_repair_compatible(old, changed)


def fixture(category):
    return next(case for case in DATASET['cases'] if case['category'] == category)


def test_fixture_coverage_and_independent_source_arithmetic():
    import csv
    import io
    assert len(DATASET['cases']) == 128
    counts = {}
    for case in DATASET['cases']:
        counts[case['category']] = counts.get(case['category'], 0) + 1
    assert len(counts) == 16 and set(counts.values()) == {8}
    assert len({case['id'] for case in DATASET['cases']}) == 128
    source = next(source for source in DATASET['sources'] if source['name'] == 'students.csv')
    values = [int(row['CAT1']) for row in csv.DictReader(io.StringIO(source['content']))]
    assert len(values) == 8 and sum(values) == 216 and sum(value >= 25 for value in values) == 5


def test_unknown_metrics_remain_null_in_empty_replay():
    report = evaluation.compare(DATASET, {'A': [], 'B': [], 'C': []}, 'replay')
    assert not report['comparison_complete']
    for strategy in report['results'].values():
        assert strategy['overall']['task_success']['value'] is None
        assert strategy['overall']['repair_success']['value'] is None
        assert strategy['overall']['peak_vram_mib']['value'] is None


def test_model_assertion_cannot_certify_success_or_repair():
    case = fixture('repair_tasks')
    result = evaluation.score(case, {'validation': {'kind': 'model_assertion', 'goal_satisfied': True, 'repair_succeeded': True}})
    assert result['task_success'] is None and result['repair_success'] is None


def test_wrong_calculated_result_is_not_saved_as_success():
    case = fixture('calculator')
    assert evaluation.inspect_result(case, {'result': {'result': 60}})['goal_satisfied'] is True
    assert evaluation.inspect_result(case, {'result': {'result': 59}})['goal_satisfied'] is False
    assert evaluation.inspect_result(case, {'result': {'result': True}})['goal_satisfied'] is False


def test_staged_tested_artifact_is_not_published_task_success():
    case = fixture('repair_tasks')
    result = evaluation.inspect_result(case, {'result': {'publication_state': 'staged',
        'checks': {'container_executed': True, 'tests_passed': True}}})
    assert result['artifact_verified'] and result['repair_succeeded']
    assert not result['goal_satisfied']


def test_false_completion_and_unauthorized_actions_scored_separately():
    case = fixture('coding')
    result = evaluation.score(case, {'completion': {'achieved': True},
        'proposals': [{'action': 'delete'}, {'action': 'publish'}]})
    assert result['false_completion'] is True
    assert result['unsafe_action_proposals'] == 2
    assert result['task_success'] is None


def test_source_fact_requires_actual_source_not_only_correct_prose():
    case = fixture('rag')
    assert evaluation.inspect_result(case, {'answer': '120 hours', 'sources': []})['goal_satisfied'] is False
    assert evaluation.inspect_result(case, {'answer': '120 hours', 'sources': [{'text': '120 hours'}]})['goal_satisfied'] is True


def test_capture_fixture_hash_prevents_changed_ids_and_requests():
    case = fixture('table')
    row = {'case_id': case['id'], 'fixture_sha256': evaluation.digest({**case, 'request': 'different'})}
    with pytest.raises(ValueError, match='Fixture changed'):
        evaluation.compare(DATASET, {'A': [row]}, 'replay')


def test_duplicate_records_cannot_inflate_coverage():
    case = fixture('simple')
    row = {'case_id': case['id'], 'fixture_sha256': evaluation.digest(case)}
    with pytest.raises(ValueError, match='Duplicate'):
        evaluation.compare(DATASET, {'A': [row, row]}, 'replay')


def test_strategy_specific_worker_policy_versus_common_task_intent():
    case = fixture('simple')
    record = {'prediction': {'worker': 'reasoning'}}
    assert evaluation.score(case, {**record, 'strategy': 'A'})['worker_correct'] is True
    assert evaluation.score(case, {**record, 'strategy': 'C'})['worker_correct'] is False
    code = fixture('coding')
    assert evaluation.score(code, {'strategy': 'B', 'prediction': {'worker': 'reasoning'}})['worker_correct'] is True
    assert evaluation.score(code, {'strategy': 'C', 'prediction': {'worker': 'reasoning'}})['worker_correct'] is False


def test_invalid_telemetry_is_unknown_not_zero():
    result = evaluation.score(fixture('simple'), {'measurements': {'model_calls': True, 'peak_ram_mib': float('nan'), 'latency_seconds': -1}})
    assert result['model_calls'] is None and result['peak_ram_mib'] is None and result['latency_seconds'] is None


def test_resource_probe_disabled_does_not_invent_residency_or_memory():
    assert evaluation.ResourceProbe(False).close() == {'peak_ram_mib': None, 'peak_vram_mib': None, 'max_llama_server_processes': None}


def test_workbench_adapter_executes_actual_calculator_without_model(tmp_path, monkeypatch):
    from backend.settings import Settings
    from backend.service import Workbench
    monkeypatch.delenv('SOVEREIGN_KNOWLEDGE_DIR', raising=False)
    class NoInference:
        def __getattr__(self, name):
            if name == 'cancel_scope':
                raise AttributeError(name)
            raise AssertionError('Calculator attempted a model call: ' + name)
    class EmptyRegistry:
        specs = {}
    workbench = Workbench(settings=Settings(data_dir=tmp_path/'data', project_dir=tmp_path/'projects'),
                          model=NoInference(), registry=EmptyRegistry())
    row = evaluation.capture_workbench(fixture('calculator'), workbench, 5)
    assert row['gate'] == 'EXECUTED'
    assert row['validation']['goal_satisfied'] is True
    assert row['measurements']['model_calls'] == 0
    assert row['prediction']['worker'] == 'none'
    assert row['completion']['achieved'] is True


def test_cancellation_adapter_records_actual_checkpoint_not_success(tmp_path, monkeypatch):
    from backend.settings import Settings
    from backend.service import Workbench
    monkeypatch.delenv('SOVEREIGN_KNOWLEDGE_DIR', raising=False)
    class EmptyRegistry:
        specs = {}
    workbench = Workbench(settings=Settings(data_dir=tmp_path/'data', project_dir=tmp_path/'projects'),
                          model=object(), registry=EmptyRegistry())
    case = {**fixture('calculator'), 'cancelled': True, 'oracle': {'kind': 'cancelled'}}
    row = evaluation.capture_workbench(case, workbench, 5)
    assert row['gate'] == 'CANCELLED'
    assert row['validation']['goal_satisfied'] is True
    assert not row['completion']['achieved']
