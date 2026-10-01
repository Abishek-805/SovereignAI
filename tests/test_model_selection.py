from dataclasses import replace
from unittest.mock import patch
import pytest
from router.model_registry import ModelRegistry,ModelSpec
from router.model_selection import ModelSelector,SelectionPolicy
from router.resource_admission import ResourceSnapshot,ResourceSampler


def registry(tmp_path, specs):
    root=tmp_path/'models';root.mkdir()
    for spec in specs:
        path=root/spec.model_file;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'fixture')
    return ModelRegistry(specs={str(index):spec for index,spec in enumerate(specs)})


def snapshot(**changes):
    return replace(ResourceSnapshot(1.0,10000,5000,6000,'0','test'),**changes)


def select(tmp_path,specs,**kwargs):
    with patch('router.model_registry.ROOT',tmp_path):
        return ModelSelector(registry(tmp_path,specs)).select('code',resource_snapshot=snapshot(),**kwargs)


def spec(alias='a',**kwargs):
    return ModelSpec('text',alias,alias+'.gguf',context=4096,capabilities=('text','code'),
        license_id='fixture-license',license_reviewed=True,license_reference='fixture-reviewed-license',**kwargs)


@pytest.mark.parametrize('change,reason',[
    ({'enabled':False},'disabled'),({'runtime_adapter':'other'},'unsupported_runtime'),
    ({'capabilities':('text',)},'unsupported_capability'),({'modalities':('image',)},'unsupported_modality'),
    ({'observed_memory_mib':10000},'Insufficient available system memory'),
    ({'observed_gpu_mib':5000},'Insufficient free GPU memory')])
def test_actual_candidate_rejections(tmp_path,change,reason):
    decision=select(tmp_path,[replace(spec(),**change)])
    assert decision.selected_model is None and decision.registry_key is None
    assert any(reason in item for item in decision.candidate_rejection_reasons['a'])
    assert decision.fallback is None


def test_context_rejection_and_unknown_context(tmp_path):
    decision=select(tmp_path,[spec()],required_context=5000)
    assert 'insufficient_context' in decision.candidate_rejection_reasons['a']
    with patch('router.model_registry.ROOT',tmp_path):
        decision=ModelSelector(ModelRegistry(specs={'any':spec()})).select('code',resource_snapshot=snapshot())
    assert decision.required_context is None and decision.available_context==4096
    assert decision.resource_admission['status']=='conditional'
    assert decision.switch_required is None
    assert decision.candidate_models[0]['measured_cost'] is None


def test_missing_projector_and_no_text_fallback_for_image(tmp_path):
    text=spec()
    vision=ModelSpec('vision','v','v.gguf',projector_file='missing.gguf',capabilities=('vision',),modalities=('text','image'),
        license_id='fixture-license',license_reviewed=True,license_reference='fixture-reviewed-license')
    with patch('router.model_registry.ROOT',tmp_path):
        selected=ModelSelector(registry(tmp_path,[text,vision])).select('vision',modality='image',resource_snapshot=snapshot())
    assert selected.selected_model is None
    assert 'missing_model_assets' in selected.candidate_rejection_reasons['v']
    assert 'unsupported_modality' in selected.candidate_rejection_reasons['a']


def test_measured_quality_precedes_latency_and_switch(tmp_path):
    slow=spec('slow',measured_metrics=(('code.quality',0.95),('code.latency_seconds',10),('code.switch_seconds',4)))
    fast=spec('fast',measured_metrics=(('code.quality',0.92),('code.latency_seconds',2),('code.switch_seconds',1)))
    decision=select(tmp_path,[slow,fast],current_residency='slow')
    assert decision.selected_model=='slow' and decision.switch_required is False
    assert decision.routing_time>=0


def test_equal_quality_compares_latency_and_switch(tmp_path):
    slow=spec('slow',measured_metrics=(('code.quality',0.95),('code.latency_seconds',10),('code.switch_seconds',4)))
    fast=spec('fast',measured_metrics=(('code.quality',0.95),('code.latency_seconds',2),('code.switch_seconds',1)))
    decision=select(tmp_path,[slow,fast],current_residency='slow')
    assert decision.selected_model=='fast' and decision.switch_required is True


def test_quality_precedes_residency_even_without_latency_measurement(tmp_path):
    better=spec('better',measured_metrics=(('code.quality',0.95),))
    resident=spec('resident',measured_metrics=(('code.quality',0.80),))
    decision=select(tmp_path,[resident,better],current_residency='resident')
    assert decision.selected_model=='better' and decision.switch_required is True
    assert decision.selection_evidence['quality_comparable'] is True


def test_unknown_metrics_do_not_win_using_fake_zero(tmp_path):
    unknown=spec('unknown')
    measured=spec('measured',measured_metrics=(('code.quality',0.95),('code.latency_seconds',1),('code.switch_seconds',1)))
    decision=select(tmp_path,[unknown,measured],current_residency='measured')
    assert decision.selected_model=='measured'
    assert decision.candidate_models[0]['measured_cost'] is None
    assert 'optimizer not established' in decision.route_reason


def test_quality_floor_rejects_unknown_and_low_scores(tmp_path):
    candidates=[spec('unknown'),spec('low',measured_metrics=(('code.quality',0.3),))]
    with patch('router.model_registry.ROOT',tmp_path):
        decision=ModelSelector(registry(tmp_path,candidates),policy=SelectionPolicy(quality_threshold=0.8)).select('code',resource_snapshot=snapshot())
    assert decision.selected_model is None
    assert decision.candidate_rejection_reasons['unknown']==['quality_threshold_unmeasured']
    assert decision.candidate_rejection_reasons['low']==['quality_below_threshold']


def test_observed_resources_admitted_only_at_covered_context(tmp_path):
    candidate=spec(observed_memory_mib=1000,observed_gpu_mib=1000,resource_context=4096,
        kv_configuration='q8_0/q8_0',resource_kv_configuration='q8_0/q8_0')
    decision=select(tmp_path,[candidate],required_context=3000,current_residency='different')
    assert decision.resource_admission['status']=='admitted'
    assert decision.resource_admission['observed']['gpu_free_mib']==5000
    # A resident model's incremental context requirement is not inferred from its peak.
    with patch('router.model_registry.ROOT',tmp_path):
        decision=ModelSelector(ModelRegistry(specs={'a':candidate})).select('code',resource_snapshot=snapshot(),current_residency='a')
    assert decision.resource_admission['status']=='conditional'


def test_registry_allows_multiple_models_per_capability(tmp_path):
    with patch('router.model_registry.ROOT',tmp_path):
        models=registry(tmp_path,[spec()]);models.register(spec('b'))
        assert set(models.models)=={'a','b'}
        assert all('code' in record['capabilities'] for record in models.records())


def test_sampler_unknown_gpu_and_cached_real_os_values(monkeypatch):
    monkeypatch.setattr('router.resource_admission.shutil.which',lambda _:None)
    sampler=ResourceSampler()
    observed=sampler.sample()
    assert observed.available_memory_mib>0 and observed.gpu_free_mib is None
    assert sampler.sample() is observed


def test_negative_or_fake_context_rejected(tmp_path):
    with pytest.raises(ValueError):select(tmp_path,[spec()],required_context=False)

def test_low_observed_headroom_rejects_even_unknown_resident_requirement(tmp_path):
    with patch('router.model_registry.ROOT',tmp_path):
        models=registry(tmp_path,[spec()])
        decision=ModelSelector(models).select('code',current_residency='a',resource_snapshot=snapshot(available_memory_mib=100,gpu_free_mib=100))
    assert decision.selected_model is None
    assert any('emergency reserve' in reason for reason in decision.candidate_rejection_reasons['a'])
