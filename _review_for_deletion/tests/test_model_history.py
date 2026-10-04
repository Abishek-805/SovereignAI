import json
import pytest

from router.model_history import ModelHistory, HistoryContext


CTX = HistoryContext('DEBUG', 'simple', 'python', 'selected_file')


def test_only_explicit_container_validation_counts(tmp_path):
    history = ModelHistory(tmp_path)
    history.record(CTX, 'coder', status='completed')
    history.record(CTX, 'coder', status='cancelled', container_verified=True, exit_code=0, goal_checks_passed=True)
    assert history.lookup(CTX, 'coder')['success_rate'] is None
    history.record(CTX, 'coder', status='completed', container_verified=True, exit_code=0, goal_checks_passed=True)
    history.record(CTX, 'coder', status='failed', container_verified=True, exit_code=1, goal_checks_passed=False)
    result = ModelHistory(tmp_path).lookup(CTX, 'coder')
    assert result['successes'] == result['failures'] == 1
    assert result['success_rate'] == .5
    assert result['unknown'] == 2
    assert result['coverage'] == .5
    assert result['wilson95'][0] < .5 < result['wilson95'][1]


def test_scoped_unknown_and_measurements(tmp_path):
    history = ModelHistory(tmp_path)
    history.record(CTX, 'coder', status='blocked', latency_seconds=2, switches=0, load_seconds=float('nan'))
    result = history.lookup(CTX, 'coder')
    assert result['latency_seconds'] == 2
    assert result['switches'] == 0
    assert result['load_seconds'] is None
    assert history.lookup(HistoryContext('EDIT', 'simple', 'python', 'selected_file'), 'coder')['coverage'] is None
    assert 'prompt' not in json.loads(history.path.read_text())


def test_evidence_requires_sample_and_nonoverlap(tmp_path):
    history = ModelHistory(tmp_path, minimum_samples=10)
    for _ in range(9):
        history.record(CTX, 'good', status='completed', container_verified=True, exit_code=0, goal_checks_passed=True)
        history.record(CTX, 'bad', status='failed', container_verified=True, exit_code=1, goal_checks_passed=False)
    assert not history.sufficient_evidence(CTX, 'good', 'bad')
    for model, code, passed in [('good', 0, True), ('bad', 1, False)]:
        history.record(CTX, model, status='completed', container_verified=True, exit_code=code, goal_checks_passed=passed)
    assert history.sufficient_evidence(CTX, 'good', 'bad')
    assert not history.sufficient_evidence(CTX, 'bad', 'good')


def test_bounded_store_and_bad_metadata(tmp_path):
    history = ModelHistory(tmp_path, max_entries=2)
    for model in ['a', 'b', 'c']:
        history.record(CTX, model, status='unverified')
    assert len(json.loads(history.path.read_text())['entries']) == 2
    with pytest.raises(ValueError):
        history.record(CTX, 'private\ncode', status='completed')


def test_invalid_evidence_and_metrics_do_not_fabricate_results(tmp_path):
    history = ModelHistory(tmp_path)
    history.record(CTX, 'coder', status='failed', container_verified=False,
                   exit_code=1, goal_checks_passed=False, latency_seconds=-1,
                   switches=1.5, load_seconds=True)
    history.record(CTX, 'coder', status='completed', container_verified=True,
                   exit_code=True, goal_checks_passed=True)
    result = history.lookup(CTX, 'coder')
    assert result['validated_samples'] == 0
    assert result['unknown'] == 2
    assert result['wilson95'] is None
    assert all(result[name] is None for name in ['latency_seconds', 'switches', 'load_seconds'])


@pytest.mark.parametrize('payload', [[], {'version': 1, 'entries': {'bad': {}}},
    {'version': 1, 'entries': {CTX.key('coder'): []}},
    {'version': 1, 'entries': {CTX.key('coder'): {'successes': -1, 'failures': 0, 'unknown': 0, 'measurements': {}, 'updated_at': 1}}},
    {'version': 1, 'entries': {CTX.key('coder'): {'successes': True, 'failures': 0, 'unknown': 0, 'measurements': {}, 'updated_at': 1}}},
    {'version': 1, 'entries': {CTX.key('coder'): {'successes': 0, 'failures': 0, 'unknown': 0, 'measurements': {'latency_seconds': {'sum': float('nan'), 'count': 1}}, 'updated_at': 1}}},
    {'version': 1, 'entries': {CTX.key('coder'): {'successes': 0, 'failures': 0, 'unknown': 0, 'measurements': {'prompt': {'sum': 1, 'count': 1}}, 'updated_at': 1}}},
])
def test_malformed_persisted_schema_is_value_error(tmp_path, payload):
    history = ModelHistory(tmp_path)
    history.path.write_text(json.dumps(payload))
    for action in [lambda: history.lookup(CTX, 'coder'), lambda: history.record(CTX, 'coder', status='completed')]:
        with pytest.raises(ValueError):
            action()


def test_oversized_persisted_store_rejected(tmp_path):
    history = ModelHistory(tmp_path, max_entries=1)
    entry = {'successes': 0, 'failures': 0, 'unknown': 1, 'measurements': {}, 'updated_at': 1}
    history.path.write_text(json.dumps({'version': 1, 'entries': {CTX.key('a'): entry, CTX.key('b'): entry}}))
    with pytest.raises(ValueError):
        history.lookup(CTX, 'a')
