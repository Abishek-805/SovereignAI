"""Read-only comparison isolation contracts; no dataset or live provider calls."""
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import pytest

ROOT=Path(__file__).resolve().parents[1]

def harness():
    spec=importlib.util.spec_from_file_location('hybrid_benchmark_test',ROOT/'benchmarks/evaluate-hybrid-code-agent.py')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_six_arms_and_exact_frozen_source_hashes():
    module=harness()
    assert set(module.base.ARMS)==set('ABCDEF')
    manifest=json.loads((module.DIRECTORY/'baseline-source.json').read_text())
    assert {'baseline-service.py','baseline-coding-workspace.py'} <= set(manifest['sha256'])
    for name,expected in manifest['sha256'].items():
        assert hashlib.sha256((module.DIRECTORY/name).read_bytes()).hexdigest()==expected


def test_only_f_keeps_current_methods(monkeypatch):
    module=harness()
    monkeypatch.setattr(module.v2,'configure_arm',lambda *_:None)
    current=lambda:None
    workbench=SimpleNamespace(run_coding_project_task=current,coding=SimpleNamespace(run_project=current,run=current))
    module.configure_arm(workbench,'F')
    assert workbench.run_coding_project_task is current
    module.configure_arm(workbench,'E')
    assert workbench.run_coding_project_task.__func__.__module__=='hybrid_frozen_service'
    assert workbench.coding.run_project.__func__.__module__=='hybrid_frozen_workflow'
    assert workbench.coding.run.__func__.__module__=='hybrid_frozen_workflow'


def test_baseline_mismatch_rejected_before_import(monkeypatch):
    module=harness()
    monkeypatch.setattr(module.v2,'configure_arm',lambda *_:None)
    monkeypatch.setattr(module.hashlib,'sha256',lambda *_:SimpleNamespace(hexdigest=lambda:'wrong'))
    with pytest.raises(ValueError,match='Frozen baseline source mismatch'):
        module.configure_arm(SimpleNamespace(),'A')


def test_historical_output_cannot_be_overwritten():
    module=harness()
    with patch('sys.argv',['evaluate','--output','smart-code-router-v2-results.json']):
        with pytest.raises(ValueError,match='Historical router evidence'):
            module.main()


def test_provenance_captures_orchestration_policy_without_dataset_reads(monkeypatch):
    module=harness()
    monkeypatch.setattr(module,'original_provenance',lambda *_:{'production_sha256':{}})
    result=module.provenance(None,None,None,None)
    assert 'E frozen V2 coding entrypoints, F hybrid' in result['comparison_policy']
    assert 'history disabled' in result['comparison_policy']
    assert 'benchmarks/evaluate-hybrid-code-agent.py' in result['production_sha256']
