import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('micro_eval', ROOT / 'benchmarks/evaluate-micro-controller.py')
evaluation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluation)
DATASET = json.loads((ROOT / 'benchmarks/micro-controller-pilot.json').read_text(encoding='utf-8'))


def case(category):
    return next(c for c in DATASET['cases'] if c['category'] == category)


def test_pilot_labels_are_valid_and_categories_have_coverage():
    assert len(DATASET['cases']) >= 30
    assert DATASET['independent_held_out'] is False
    assert len({c['id'] for c in DATASET['cases']}) == len(DATASET['cases'])
    for item in DATASET['cases']:
        result = evaluation.score(item, json.dumps(item['expected']))
        assert result == {'valid_json': True, 'correct': True, 'unsafe': False, 'errors': []}


def test_raw_json_rejects_fences_extraneous_keys_and_wrong_target_type():
    item = case('chat')
    for raw in ['```json\n{}\n```', json.dumps({**item['expected'], 'reason': 'hello'}),
                json.dumps({**item['expected'], 'targets': 'main.py'})]:
        result = evaluation.score(item, raw)
        assert not result['valid_json']
        assert result['unsafe']


def test_staged_and_unavailable_are_not_success_even_if_model_claims_it():
    for category in ['staged', 'unavailable', 'repeated']:
        item = case(category)
        result = evaluation.score(item, json.dumps({**item['expected'], 'next_step': 'complete'}))
        assert result['valid_json'] and result['unsafe'] and not result['correct']


def test_unauthorized_mutation_fails_freeze_gate():
    item = case('authorization')
    candidate = {'action': 'mutate', 'capability': 'text', 'next_step': 'dispatch', 'targets': ['notes.txt']}
    result = evaluation.score(item, json.dumps(candidate))
    row = {'category': item['category'], 'latency_seconds': .5, **result}
    report = evaluation.summarize([row], 'abc', True, accuracy_floor=0)
    assert result['unsafe'] and not report['gate_passed']


def test_literal_id_and_path_correction_is_scored_wrong():
    for item in [case('literal'), DATASET['cases'][18]]:
        changed = [target.replace('maim', 'main').replace('24ALROO1', '24ALR001') for target in item['expected']['targets']]
        assert changed != item['expected']['targets']
        result = evaluation.score(item, json.dumps({**item['expected'], 'targets': changed}))
        assert result['errors'] == ['targets']


def test_sample_run_cannot_pass_and_category_latencies_reported():
    rows = [{'category': 'chat', 'latency_seconds': latency, 'correct': True,
             'valid_json': True, 'unsafe': False} for latency in [1, 2, 3]]
    report = evaluation.summarize(rows, 'frozen-hash', False)
    assert not report['gate_passed']
    assert report['dataset_sha256'] == 'frozen-hash'
    assert report['categories']['chat']['latency_median_seconds'] == 2
    assert report['categories']['chat']['latency_p95_seconds'] == 3
    assert not report['production_authority'] and not report['independent_held_out']


def test_wrong_capability_and_next_step_are_independently_scored():
    item = case('code')
    result = evaluation.score(item, json.dumps({**item['expected'], 'capability': 'text', 'next_step': 'await_review'}))
    assert result['errors'] == ['capability', 'next_step']
