import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]

def harness():
    spec=importlib.util.spec_from_file_location('v2_benchmark',ROOT/'benchmarks/evaluate-smart-code-router-v2.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module

def test_v2_capture_records_cost_without_inventing_switch_effect():
    module=harness()
    stages=[{'stage':'model_selection','current_residency':'warm','selected_model':'next',
        'worker_role':'code','route_reason':'required context','selection_evidence':{}},
        {'stage':'runtime_lease','selected_model':'next','switch_required':True,'model_load_time':3}]
    module.original_capture=lambda *args:{'correctness':True,'operational_result':{'routing':{'decision':{'stages':stages}}}}
    row=module.capture({},SimpleNamespace(),None)
    event=row['switch_observations'][0]
    assert event['previous_model']=='warm' and event['load_seconds']==3
    assert event['validated_outcome'] is True and event['effect']=='UNKNOWN'

def test_v2_failure_taxonomy_separates_model_environment_and_validation():
    module=harness()
    assert module.failure_layer({'operational_result':{'error':{'code':'model_unavailable'}}})=='ENVIRONMENT_FAILURE'
    assert module.failure_layer({'operational_result':{'error':{'code':'generation_format'}}})=='MODEL_FAILURE'
    assert module.failure_layer({'correctness':False})=='VALIDATION_FAILURE'

def test_v2_frozen_old_outputs_cannot_be_overwritten():
    module=harness()
    import pytest
    with patch('sys.argv',['evaluate','--output','smart-code-router-results.json']):
        with pytest.raises(ValueError,match='Frozen V1'):module.main()
