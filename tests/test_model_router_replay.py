"""Deterministic resource-pressure replay, without loading a model or a GPU."""
from dataclasses import replace
from unittest.mock import patch

import pytest

from backend.contracts import WorkbenchError
from router.model_registry import ModelRegistry,ModelSpec,default_specs
from router.model_selection import ModelSelector,SelectionPolicy
from router.resource_admission import ResourceSnapshot,admit_resources
from tests.test_model_selection import registry,snapshot,spec


@pytest.mark.parametrize('resources,code',[
    ({'available_memory_mib':100},'ram_below_emergency_reserve'),
    ({'gpu_free_mib':100},'gpu_below_emergency_reserve'),
    ({'available_memory_mib':1100},'insufficient_ram'),
    ({'gpu_free_mib':1100},'insufficient_gpu'),
])
def test_pressure_replay_has_stable_failure_layer_and_no_runtime_side_effect(tmp_path,resources,code):
    candidate=spec(observed_memory_mib=1000,observed_gpu_mib=1000)
    with patch('router.model_registry.ROOT',tmp_path):
        models=registry(tmp_path,[candidate])
        selector=ModelSelector(models)
        with patch.object(models,'acquire_lease',side_effect=AssertionError('Selection cannot load models')):
            decisions=[selector.select('code',resource_snapshot=snapshot(**resources)) for _ in range(3)]
    for decision in decisions:
        assert decision.selected_model is None
        assert decision.failure_category=='RESOURCE_FAILURE'
        assert code in decision.candidate_rejection_codes['a']
        assert decision.resource_admission['observed']==snapshot(**resources).to_dict()
        assert decision.fallback is None
    assert [decision.candidate_rejection_codes for decision in decisions]==[decisions[0].candidate_rejection_codes]*3


def test_incompatible_candidate_pressure_is_candidate_failure_not_resource_failure(tmp_path):
    with patch('router.model_registry.ROOT',tmp_path):
        selector=ModelSelector(registry(tmp_path,[replace(spec(),capabilities=('text',))]))
        decision=selector.select('vision',modality='image',resource_snapshot=snapshot(gpu_free_mib=0))
    assert decision.failure_category=='CANDIDATE_FAILURE'
    assert 'unsupported_modality' in decision.candidate_rejection_codes['a']


@pytest.mark.parametrize('value',[True,-1,float('nan'),float('inf')])
def test_invalid_resource_numbers_remain_unknown_not_fake_capacity(value):
    observed=ResourceSnapshot(available_memory_mib=value,gpu_free_mib=value,gpu_total_mib=4096)
    decision=admit_resources(spec(),observed)
    assert observed.available_memory_mib is None and observed.gpu_free_mib is None
    assert observed.errors
    assert decision['status']=='conditional'
    assert decision['requirements']['system_memory_mib'] is None


def test_invalid_gpu_free_observation_cannot_exceed_total():
    observed=snapshot(gpu_free_mib=7000,gpu_total_mib=6000)
    assert observed.gpu_free_mib is None
    assert observed.errors==('GPU free memory exceeds observed total',)


def test_resident_model_low_gpu_headroom_is_conditional_not_a_reload_rejection(tmp_path):
    candidate=spec(observed_memory_mib=1000,observed_gpu_mib=1000)
    with patch('router.model_registry.ROOT',tmp_path):
        selector=ModelSelector(registry(tmp_path,[candidate]))
        decision=selector.select('code',current_residency=candidate.alias,
                                 resource_snapshot=snapshot(gpu_free_mib=154))
    assert decision.selected_model==candidate.identifier
    assert decision.resource_admission['status']=='conditional'
    assert 'resident_gpu_headroom_low' in decision.resource_admission['condition_codes']
    assert 'gpu_below_emergency_reserve' not in decision.resource_admission['reason_codes']
    # System memory reserve still applies even to a resident runtime.
    blocked=admit_resources(candidate,snapshot(available_memory_mib=100,gpu_free_mib=154),resident=True)
    assert blocked['status']=='rejected'
    assert 'ram_below_emergency_reserve' in blocked['reason_codes']


def test_measured_context_requires_matching_kv_profile():
    candidate=spec(observed_memory_mib=1000,observed_gpu_mib=1000,
                   resource_context=4096,kv_configuration='q8_0/q8_0',resource_kv_configuration='f16/f16')
    decision=admit_resources(candidate,snapshot(),required_context=3000)
    assert decision['status']=='conditional'
    assert 'kv_profile_unmeasured' in decision['condition_codes']
    assert decision['requirements']['required_context']==3000
    admitted=admit_resources(replace(candidate,resource_kv_configuration='q8_0/q8_0'),snapshot())
    assert admitted['status']=='admitted'
    resident=admit_resources(replace(candidate,resource_kv_configuration='q8_0/q8_0'),snapshot(),resident=True)
    assert resident['status']=='conditional'
    assert 'resident_incremental_kv_unmeasured' in resident['condition_codes']


def test_lexicographic_cost_tie_prefers_residency_before_identifier(tmp_path):
    alternative=spec('a',measured_metrics=(('code.quality',0.9),('code.latency_seconds',2),('code.switch_seconds',1)))
    resident=spec('z',measured_metrics=(('code.quality',0.9),('code.latency_seconds',3),('code.switch_seconds',9)))
    with patch('router.model_registry.ROOT',tmp_path):
        models=registry(tmp_path,[alternative,resident])
        selector=ModelSelector(models,policy=SelectionPolicy(quality_threshold=0.8,quality_threshold_source='fixed fixture benchmark'))
        decision=selector.select('code',current_residency='z',resource_snapshot=snapshot())
    assert decision.selected_model=='z'
    assert decision.switch_required is False
    assert decision.selection_evidence['quality_threshold_source']=='fixed fixture benchmark'
    assert decision.selection_evidence['cost_unit']=='seconds'


def test_unreviewed_license_rejected_before_registration_loading_or_selection(tmp_path):
    candidate=replace(spec(),license_reviewed=False)
    with patch('router.model_registry.ROOT',tmp_path):
        models=registry(tmp_path,[candidate])
        with pytest.raises(WorkbenchError,match='license'):models.launch_args('0')
        with pytest.raises(WorkbenchError,match='license'):ModelRegistry(specs={}).register(candidate)
        decision=ModelSelector(models).select('code',resource_snapshot=snapshot())
    assert decision.selected_model is None and decision.failure_category=='CANDIDATE_FAILURE'
    assert decision.candidate_rejection_codes['a']==['license_not_reviewed']


def test_registry_records_license_and_actual_runtime_configuration():
    models=ModelRegistry()
    records=models.records()
    for entry in records:
        assert entry['license_id']=='Apache-2.0' and entry['license_reviewed'] is True
        assert entry['license_source'].startswith(('https://huggingface.co/Qwen/', 'https://ai.google.dev/gemma/'))
        from datetime import date
        assert date.fromisoformat(entry['license_reviewed_at'])<=date.today()
        assert entry['quantization']=='Q4_K_M'
        assert entry['resource_kv_configuration'] is None
    assert default_specs()['vision'].kv_configuration=='f16/f16'


def test_runtime_asset_absence_has_machine_readable_rejection(tmp_path):
    with patch('router.model_registry.ROOT',tmp_path),patch('router.model_registry.RUNTIME',tmp_path/'missing.exe'):
        models=registry(tmp_path,[spec()])
        decision=ModelSelector(models).select('code',resource_snapshot=snapshot())
    assert decision.selected_model is None
    assert decision.candidate_rejection_codes['a']==['runtime_unavailable']


def test_production_does_not_accept_arbitrary_latency_weights():
    with pytest.raises(ValueError,match='unweighted'):SelectionPolicy(latency_weight=0.5)


def test_explicit_unknown_snapshot_does_not_sample_host_or_invent_headroom(tmp_path):
    with patch('router.model_registry.ROOT',tmp_path):
        selector=ModelSelector(registry(tmp_path,[spec()]))
        with patch.object(selector.sampler,'sample',side_effect=AssertionError('Use supplied unknown observations')):
            decision=selector.select('code',resource_snapshot={})
    assert decision.selected_model=='a'
    assert decision.resource_admission['status']=='conditional'
    assert decision.resource_admission['observed']['gpu_free_mib'] is None
    assert decision.resource_admission['observed']['available_memory_mib'] is None
