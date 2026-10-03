import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'benchmarks' / 'smart-code-router-v2'

def test_frozen_v2_development_coverage_and_assets():
    data = json.loads((ROOT / 'main.json').read_text(encoding='utf-8'))
    assert Counter(c['category'] for c in data['cases']) == {'explain':20,'edit':20,'debug':20,'implement':15,'refactor_multifile':15,'architecture':5,'vision':5}
    assert len({c['id'] for c in data['cases']}) == 100
    assert all(c['oracle'] for c in data['cases'])
    assert any(c.get('history') for c in data['cases'])
    assert any(c.get('properties', {}).get('ambiguous') for c in data['cases'])
    for case in data['cases']:
        if case['modality'] == 'image':
            image = ROOT / case['context']['image_path']
            assert image.read_bytes().startswith(b'\x89PNG\r\n\x1a\n')
            assert hashlib.sha256(image.read_bytes()).hexdigest() == case['context']['image_sha256']

def test_v2_fixture_freeze_hashes_only_without_opening_holdout_cases():
    provenance = json.loads((ROOT / 'provenance.json').read_text(encoding='utf-8'))
    for entry in provenance['datasets']:
        assert hashlib.sha256((ROOT / entry['file']).read_bytes()).hexdigest() == entry['file_sha256']
    assert provenance['datasets'][1]['case_count'] == 24
    assert provenance['holdout_policy']

def test_independent_fixture_oracles_accept_references_and_reject_broken_baselines():
    report = json.loads((ROOT / 'oracle-authoring-validation.json').read_text(encoding='utf-8'))
    assert report['failures'] == []
    assert report['reference_pass'] == 103
    assert report['broken_baseline_fail'] == 103
    assert report['rubric_only'] == 21
