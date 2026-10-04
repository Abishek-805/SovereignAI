import importlib.util
from pathlib import Path


def analyzer():
    path = Path(__file__).resolve().parents[1] / 'benchmarks/analyze-smart-code-router.py'
    spec = importlib.util.spec_from_file_location('smart_analysis', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_failed_tasks_count_even_without_artifact_and_unsupported_stays_unknown():
    dataset = {'cases': [{'id': 't', 'category': 'fix', 'oracle': {'kind': 'trusted_tests'}}]}
    rows = [{'arm': 'E', 'case_id': 't', 'stage': 'failed', 'correctness': None, 'measurements': {'model_calls': 3}},
            {'arm': 'E', 'case_id': 't', 'stage': 'READY_FOR_REVIEW', 'correctness': True},
            {'arm': 'E', 'case_id': 't', 'gate': 'NOT_VERIFIED', 'stage': 'failed'}]
    report = analyzer().analyze({'rows': rows}, dataset)['arms']['E']
    assert report['task_endpoints']['failed'] == 1
    assert report['task_endpoints']['passed'] == 1
    assert report['task_endpoints']['unknown'] == 1
    assert report['task_endpoints']['failure_rate_all_cases'] == 1 / 3
    assert report['task_endpoints']['failure_rate_evaluated'] == .5
    assert report['task_failure_rate_executable'] == .5
    assert report['conditional_artifact_tests']['evaluated'] == 1
    assert report['measurements']['model_calls'] == {'observed': 1, 'unknown': 2, 'total': 3, 'mean': 3}
    assert report['measurements']['latency_seconds']['total'] is None


def test_semantic_review_requires_matching_fixture_and_candidate_hashes():
    dataset = {'cases': [{'id': 'r', 'category': 'design', 'oracle': {'kind': 'rubric'}}]}
    row = {'arm': 'E', 'case_id': 'r', 'stage': 'READY_FOR_REVIEW', 'fixture_sha256': 'f',
           'validation': {'candidate_hashes': {'solution.py': 'c'}}}
    review = {'arm': 'E', 'case_id': 'r', 'fixture_sha256': 'f', 'candidate_hashes': {'solution.py': 'c'}, 'goal_satisfied': True}
    module = analyzer()
    assert module.analyze({'rows': [row]}, dataset)['arms']['E']['task_endpoints']['unknown'] == 1
    assert module.analyze({'rows': [row]}, dataset, [review])['arms']['E']['task_endpoints']['passed'] == 1
    review['candidate_hashes']['solution.py'] = 'wrong'
    assert module.analyze({'rows': [row]}, dataset, [review])['arms']['E']['task_endpoints']['unknown'] == 1


def test_resources_and_repairs_keep_unknown_denominators():
    dataset = {'cases': [{'id': 't', 'category': 'fix', 'oracle': {'kind': 'trusted_tests'}}]}
    rows = [{'arm': 'E', 'case_id': 't', 'repair_observed': True, 'repair_succeeded': True,
             'measurements': {'rss_peak_mb': 10}, 'resource_scope': 'whole device'}, {'arm': 'E', 'case_id': 't'}]
    report = analyzer().analyze({'rows': rows}, dataset)['arms']['E']
    assert report['resource_peaks']['rss_peak_mb'] == {'peak': 10, 'observed': 1, 'unknown': 1}
    assert report['resource_scopes'] == ['whole device']
    assert report['repairs']['observation_unknown'] == 1
    assert report['repairs']['independently_passed'] == 1


def test_explanation_review_document_binds_answer_and_preserves_partial():
    import hashlib
    module = analyzer()
    dataset = {'cases': [{'id': 'r', 'category': 'explain', 'oracle': {'kind': 'rubric'}}]}
    row = {'arm': 'A', 'case_id': 'r', 'stage': 'answered', 'fixture_sha256': 'fixture', 'operational_result': {'answer': 'Explanation'}}
    review = {'arm': 'A', 'case_id': 'r', 'fixture_sha256': 'fixture',
              'answer_sha256': hashlib.sha256(b'Explanation').hexdigest(), 'verdict': 'PARTIAL'}
    for verdict, endpoint in [('PASS', 'passed'), ('PARTIAL', 'partial'), ('FAIL', 'failed'), ('UNKNOWN', 'unknown')]:
        review['verdict'] = verdict
        report = module.analyze({'rows': [row]}, dataset, {'schema_version': 1, 'reviews': [review]})['arms']['A']
        assert report['task_endpoints'][endpoint] == 1
        assert report['semantic_verdicts'][verdict] == 1
        assert report['semantic_reviews_verified'] == 1
    review['verdict'] = 'PASS'
    row['operational_result']['answer'] = 'Changed answer'
    assert module.analyze({'rows': [row]}, dataset, {'reviews': [review]})['arms']['A']['task_endpoints']['unknown'] == 1


def test_generation_failure_is_task_failure_without_inventing_artifact_result():
    module = analyzer()
    dataset = {'cases': [{'id': 't', 'category': 'fix', 'oracle': {'kind': 'trusted_tests'}}]}
    rows = [{'arm': 'A', 'case_id': 't', 'gate': 'FAIL', 'stage': None,
             'correctness': None, 'operational_result': {'error': {'code': 'generation_format'}}},
            {'arm': 'A', 'case_id': 't', 'gate': 'STOP', 'stage': 'failed',
             'operational_result': {'error': {'code': 'docker_unavailable'}}}]
    result = module.analyze({'rows': rows}, dataset)['arms']['A']
    assert result['task_endpoints']['failed'] == 1
    assert result['task_endpoints']['unknown'] == 1
    assert result['conditional_artifact_tests']['failed'] == 0
    assert result['conditional_artifact_tests']['unknown'] == 2
    assert result['blocked_cases'] == 1
    assert result['unknown_reasons'] == {'environment_or_execution_stopped': 1}


def test_clustered_uncertainty_groups_contract_reuse_and_excludes_unknown():
    module = analyzer()
    oracle = {'kind': 'trusted_tests', 'trusted_files': {'test.py': 'assert True'}, 'command': ['python', 'test.py']}
    dataset = {'cases': [{'id': 'a', 'category': 'fix', 'oracle': oracle},
                         {'id': 'b', 'category': 'feature', 'oracle': oracle},
                         {'id': 'c', 'category': 'fix', 'oracle': {**oracle, 'trusted_files': {'test.py': 'assert 1'}}},
                         {'id': 'r', 'category': 'explain', 'oracle': {'kind': 'rubric'}}]}
    rows = [{'arm': 'E', 'case_id': 'a', 'stage': 'READY_FOR_REVIEW', 'correctness': True},
            {'arm': 'E', 'case_id': 'b', 'stage': 'failed'},
            {'arm': 'E', 'case_id': 'c', 'stage': 'READY_FOR_REVIEW', 'correctness': True},
            {'arm': 'E', 'case_id': 'c', 'gate': 'NOT_VERIFIED'},
            {'arm': 'E', 'case_id': 'r', 'stage': 'failed'}]
    result = module.analyze({'rows': rows}, dataset)['arms']['E']['trusted_task_pass_clustered_uncertainty']
    assert result['clusters'] == 2
    assert result['evaluated_cases'] == 3
    assert result['pass_fraction'] == 2 / 3
    assert result['interval'] == [.5, 1.0]
    assert result == module.analyze({'rows': rows}, dataset)['arms']['E']['trusted_task_pass_clustered_uncertainty']
    single = module.analyze({'rows': rows[:2]}, dataset)['arms']['E']['trusted_task_pass_clustered_uncertainty']
    assert single['clusters'] == 1
    assert single['interval'] is None
    empty = module.clustered_pass_interval([])
    assert empty['pass_fraction'] is None
    assert empty['evaluated_cases'] == 0
    assert empty['interval'] is None


def test_trusted_task_answer_failure_requires_bound_review_of_unmet_goal():
    import hashlib
    module = analyzer()
    dataset = {'cases': [{'id': 'fix', 'category': 'debug', 'oracle': {'kind': 'trusted_tests'}}]}
    row = {'arm': 'B', 'case_id': 'fix', 'stage': 'answered', 'fixture_sha256': 'fixture',
           'correctness': None, 'operational_result': {'answer': 'Please provide source.'}}
    review = {'arm': 'B', 'case_id': 'fix', 'fixture_sha256': 'fixture',
              'answer_sha256': hashlib.sha256(b'Please provide source.').hexdigest(),
              'verdict': 'FAIL', 'goal_satisfied': False}
    def analyze(record=None):
        return module.analyze({'rows': [row]}, dataset, [record] if record else [])['arms']['B']
    assert analyze()['task_endpoints']['unknown'] == 1
    result = analyze(review)
    assert result['task_endpoints']['failed'] == 1
    assert {key: result['conditional_artifact_tests'][key] for key in ('passed', 'failed', 'unknown', 'evaluated')} == {
        'passed': 0, 'failed': 0, 'unknown': 1, 'evaluated': 0}
    assert result['semantic_verdicts']['FAIL'] == 1
    for altered in ({'fixture_sha256': 'changed'}, {'answer_sha256': 'changed'},
                    {'goal_satisfied': None}, {'goal_satisfied': True}, {'verdict': 'PASS'}):
        assert analyze({**review, **altered})['task_endpoints']['unknown'] == 1
    row['validation'] = {'candidate_hashes': {'solution.py': 'unreviewed'}}
    assert analyze(review)['task_endpoints']['unknown'] == 1


def test_worker_alias_correction_separates_advisory_reported_and_actual_assignment():
    module = analyzer()
    rows = [{'arm': 'A', 'expected': {'suitable_workers': ['coder']},
             'prediction': {'worker_role': 'code', 'active_worker': 'light-model'},
             'telemetry': {'events': [{'event': 'CODING_REQUEST_CLASSIFIED', 'details': {'worker_role': 'code'}}]}},
            {'arm': 'A', 'expected': {'suitable_workers': ['code']},
             'prediction': {'worker_role': 'coder', 'active_worker': 'code-model'}},
            {'arm': 'A', 'expected': {'suitable_workers': ['coder']},
             'prediction': {'worker_role': 'code', 'active_worker': 'unknown-model'}},
            {'arm': 'A', 'prediction': {}}]
    results = {'rows': rows, 'provenance': {'profiles': [
        {'model_id': 'light-model', 'worker_roles': ['lightweight']},
        {'model_id': 'code-model', 'worker_roles': ['code']}]}}
    metric = module.worker_suitability_correction(results)['arms']['A']
    assert metric['advisory_policy_role'] == {'suitable': 1, 'unsuitable': 0, 'unknown': 3, 'evaluated': 1, 'accuracy': 1}
    assert metric['reported_worker_role'] == {'suitable': 3, 'unsuitable': 0, 'unknown': 1, 'evaluated': 3, 'accuracy': 1}
    assert metric['actual_active_model_roles'] == {'suitable': 1, 'unsuitable': 1, 'unknown': 2, 'evaluated': 2, 'accuracy': .5}
    assert rows[0]['expected']['suitable_workers'] == ['coder']
