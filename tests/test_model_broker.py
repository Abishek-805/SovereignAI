from dataclasses import replace
from unittest.mock import patch

import pytest

from router.model_broker import ModelBroker
from router.model_registry import ModelRegistry,default_specs
from tests.test_model_selection import registry,snapshot,spec


def test_role_gate_beats_warm_incompatible_worker(tmp_path):
    simple=spec('simple',worker_roles=('lightweight',))
    reasoning=spec('reasoning',worker_roles=('reasoning',))
    with patch('router.model_registry.ROOT',tmp_path):
        models=registry(tmp_path,[simple,reasoning])
        decision=ModelBroker(models).select('reasoning',resource_snapshot=snapshot(),current_residency='simple')
    assert decision.selected_model=='reasoning' and decision.switch_required
    assert decision.candidate_rejection_codes['simple']==['unsuitable_worker_role']
    assert decision.candidate_models[1]['quality'] is None
    assert decision.to_dict()['worker_role']=='reasoning'


def test_unknown_metrics_keep_task_affinity_without_fake_cost(tmp_path):
    workers=[spec(name,worker_roles=('code',)) for name in ('a','z')]
    with patch('router.model_registry.ROOT',tmp_path):
        decision=ModelBroker(registry(tmp_path,workers)).select('code',resource_snapshot=snapshot(),
            current_residency='z',task_affinity='z')
    assert decision.selected_model=='z' and decision.is_warm and not decision.switch_required
    assert all(candidate['measured_cost'] is None for candidate in decision.candidate_models)


def test_broker_lexicographic_latency_not_latency_switch_sum(tmp_path):
    workers=[spec('a',worker_roles=('code',),measured_metrics=(('code.quality',.9),('code.latency_seconds',1),('code.switch_seconds',9))),
             spec('z',worker_roles=('code',),measured_metrics=(('code.quality',.9),('code.latency_seconds',2),('code.switch_seconds',0)))]
    with patch('router.model_registry.ROOT',tmp_path):
        decision=ModelBroker(registry(tmp_path,workers)).select('code',resource_snapshot=snapshot(),current_residency='z')
    assert decision.selected_model=='a'
    assert 'latency_seconds ascending' in decision.selection_evidence['comparison']


def test_broker_pressure_rejects_without_role_fallback(tmp_path):
    with patch('router.model_registry.ROOT',tmp_path):
        decision=ModelBroker(registry(tmp_path,[spec(worker_roles=('code',))])).select('code',
            resource_snapshot=snapshot(available_memory_mib=100),current_residency='other')
    assert decision.selected_model is None and decision.failure_category=='RESOURCE_FAILURE'
    assert 'ram_below_emergency_reserve' in decision.candidate_rejection_codes['a']


def test_checkpoint_failure_precedes_unload_under_lease_lock():
    models=ModelRegistry(specs={'code':spec(worker_roles=('code',))})
    events=[]
    def checkpoint(state):
        events.append(state)
        assert models._lock.locked()
        raise RuntimeError('disk full')
    with patch.object(models,'launch_args',return_value=['runtime']),patch.object(models,'_get_current_alias',return_value='old'),\
         patch.object(models,'_owns_server',return_value=True),patch.object(models,'kill_server') as kill:
        with pytest.raises(RuntimeError,match='disk full'):
            models.acquire_lease('code',persist_before_swap=checkpoint)
    assert events[0]['selected_model']=='a'
    kill.assert_not_called()


def test_warm_lease_does_not_checkpoint_or_unload():
    models=ModelRegistry(specs={'code':spec(worker_roles=('code',))})
    with patch.object(models,'launch_args',return_value=['runtime']),patch.object(models,'_get_current_alias',return_value='a'),\
         patch.object(models,'_owns_server',return_value=True),patch.object(models,'_runtime_profile_matches',return_value=True),\
         patch.object(models,'kill_server') as kill:
        result=models.acquire_lease('code',persist_before_swap=lambda _:pytest.fail('warm lease must not swap'))
    assert result['switch_required'] is False
    kill.assert_not_called()


def test_alias_alone_does_not_prove_residency():
    models=ModelRegistry(specs={'code':spec(worker_roles=('code',))})
    with patch.object(models,'_get_current_alias',return_value='a'),patch.object(models,'_owns_server',return_value=True),\
         patch.object(models,'launch_args',return_value=['runtime']),patch.object(models,'_runtime_profile_matches',return_value=False):
        assert models.verified_residency() is None


def test_installed_default_worker_roles_do_not_rename_assets():
    entries=default_specs()
    assert entries['text'].worker_roles==('reasoning',)
    assert entries['vision'].worker_roles==('vision',)
    if 'text-light' in entries:
        assert entries['text-light'].worker_roles==('lightweight',)
        assert entries['text-light'].model_file=='gemma-4-E2B-it-Q4_K_M.gguf'
    if 'code' in entries:assert entries['code'].worker_roles==('code',)
    assert all(item.identifier!=item.alias for item in entries.values())
    assert len(entries)<=4
    assert entries['vision'].identifier=='Qwen/Qwen3.5-2B'


def test_shared_alias_mismatched_model_is_not_warm(tmp_path):
    candidate=spec('sovereign-text',model_id='actual/qwen',worker_roles=('reasoning',))
    with patch('router.model_registry.ROOT',tmp_path):
        models=registry(tmp_path,[candidate])
        with patch.object(models,'verified_residency',return_value=None) as verify:
            decision=ModelBroker(models).select('reasoning',resource_snapshot=snapshot(),current_residency='sovereign-text')
    verify.assert_called_once()
    assert decision.selected_model=='actual/qwen' and not decision.is_warm
    assert decision.switch_required


def test_quality_floor_cannot_be_bypassed_by_affinity(tmp_path):
    from router.model_selection import SelectionPolicy
    candidate=spec('warm',worker_roles=('code',),measured_metrics=(('code.quality',.2),))
    with patch('router.model_registry.ROOT',tmp_path):
        decision=ModelBroker(registry(tmp_path,[candidate]),policy=SelectionPolicy(quality_threshold=.8)).select(
            'code',resource_snapshot=snapshot(),current_residency='warm',task_affinity='warm')
    assert decision.selected_model is None
    assert 'quality_below_threshold' in decision.candidate_rejection_codes['warm']


def test_changed_identity_invalidates_decision_before_lease(tmp_path):
    from backend.contracts import WorkbenchError
    with patch('router.model_registry.ROOT',tmp_path):
        models=registry(tmp_path,[spec('a',worker_roles=('code',))])
        broker=ModelBroker(models)
        decision=broker.select('code',resource_snapshot=snapshot(),current_residency='a')
        models.specs['0']=replace(models.specs['0'],model_id='different')
        with patch.object(models,'acquire_lease') as lease:
            with pytest.raises(WorkbenchError,match='identity'):broker.acquire(decision)
    lease.assert_not_called()


def test_actual_gemma_file_under_qwen_text_alias_is_not_qwen_residency(tmp_path):
    candidate=spec('sovereign-text',model_id='Qwen/Qwen3.5-4B',worker_roles=('reasoning',))
    pid=tmp_path/'server.pid';pid.write_text('123',encoding='utf-8')
    with patch('router.model_registry.ROOT',tmp_path),patch('router.model_registry.PID_FILE',pid):
        models=registry(tmp_path,[candidate])
        actual=models.launch_args('0')
        actual[actual.index('-m')+1]=str(tmp_path/'models'/'gemma-4-E2B-it-Q4_K_M.gguf')
        with patch.object(models,'_get_current_alias',return_value='sovereign-text'),\
             patch.object(models,'_owns_server',return_value=True),patch('router.model_registry.psutil.Process') as process:
            process.return_value.cmdline.return_value=actual
            assert models.verified_residency() is None


def test_admission_release_checkpoints_under_lock_before_unloading():
    models=ModelRegistry(specs={})
    events=[]
    def checkpoint(observation):
        assert models._lock.locked()
        events.append(('checkpoint',observation['current_residency']))
    with patch.object(models,'_get_current_alias',return_value='owned'),patch.object(models,'_owns_server',return_value=True),\
         patch.object(models,'kill_server',side_effect=lambda:events.append(('unload','owned'))):
        result=models.release_for_admission(checkpoint)
    assert events==[('checkpoint','owned'),('unload','owned')]
    assert result['released'] and models.runtime_state=='Unloaded'


def test_admission_release_checkpoint_failure_preserves_runtime():
    models=ModelRegistry(specs={})
    with patch.object(models,'_get_current_alias',return_value='owned'),patch.object(models,'_owns_server',return_value=True),\
         patch.object(models,'kill_server') as kill:
        with pytest.raises(RuntimeError,match='checkpoint'):
            models.release_for_admission(lambda _:(_ for _ in ()).throw(RuntimeError('checkpoint')))
    kill.assert_not_called()


def test_admission_release_refuses_unowned_runtime():
    from backend.contracts import WorkbenchError
    models=ModelRegistry(specs={})
    with patch.object(models,'_get_current_alias',return_value='foreign'),patch.object(models,'_owns_server',return_value=False),\
         patch.object(models,'kill_server') as kill:
        with pytest.raises(WorkbenchError,match='unowned'):models.release_for_admission()
    kill.assert_not_called()


def test_post_release_refresh_observes_fresh_memory_despite_ttl():
    from types import SimpleNamespace
    from router.resource_admission import ResourceSampler
    sampler=ResourceSampler(ttl=60)
    with patch('router.resource_admission.shutil.which',return_value=None),\
         patch('router.resource_admission.psutil.virtual_memory',side_effect=[SimpleNamespace(available=1024**3),SimpleNamespace(available=2*1024**3)]):
        first=sampler.sample()
        assert sampler.sample() is first
        refreshed=sampler.refresh()
    assert first.available_memory_mib==1024 and refreshed.available_memory_mib==2048
