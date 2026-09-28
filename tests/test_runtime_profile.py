from dataclasses import replace
from unittest.mock import Mock,patch
import httpx
import pytest
from router.model_registry import ModelRegistry,ModelSpec
from backend.contracts import WorkbenchError


@pytest.fixture
def registry(tmp_path,monkeypatch):
    model=tmp_path/'models'/'model.gguf';model.parent.mkdir();model.write_bytes(b'fixture')
    pid=tmp_path/'server.pid';pid.write_text('123')
    monkeypatch.setattr('router.model_registry.ROOT',tmp_path)
    monkeypatch.setattr('router.model_registry.PID_FILE',pid)
    return ModelRegistry(specs={'text':ModelSpec('text','owned','model.gguf',context=4096,kv_configuration='q8_0/q8_0',
        license_id='fixture-license',license_reviewed=True,license_reference='fixture-reviewed-license')})


def test_profile_matches_actual_model_context_and_kv(registry):
    args=registry.launch_args('text')
    with patch('router.model_registry.psutil.Process') as process,patch('router.model_registry.httpx.get',return_value=httpx.Response(200,json={'default_generation_settings':{'n_ctx':4096}})):
        process.return_value.cmdline.return_value=args
        assert registry._runtime_profile_matches(args)
        modified=args.copy();modified[modified.index('-c')+1]='6144';process.return_value.cmdline.return_value=modified
        assert not registry._runtime_profile_matches(args)


@pytest.mark.parametrize('flag,value',[('-m','different.gguf'),('-ctk','f16'),('-ctv','f16'),('-np','2'),('--alias','other'),('--fit-target','512'),('--fit','off'),('--sleep-idle-seconds','60')])
def test_profile_rejects_model_kv_or_slots_mismatch(registry,flag,value):
    args=registry.launch_args('text');actual=args.copy();actual[actual.index(flag)+1]=value
    with patch('router.model_registry.psutil.Process') as process:
        process.return_value.cmdline.return_value=actual
        assert not registry._runtime_profile_matches(args)


def test_actual_fitted_context_cannot_be_claimed_as_requested(registry):
    args=registry.launch_args('text')
    with patch('router.model_registry.psutil.Process') as process,patch('router.model_registry.httpx.get',return_value=httpx.Response(200,json={'default_generation_settings':{'n_ctx':2048}})):
        process.return_value.cmdline.return_value=args
        assert not registry._runtime_profile_matches(args)


def test_alias_only_warm_reuse_requires_verified_profile(registry):
    with patch.object(registry,'_get_current_alias',return_value='owned'),patch.object(registry,'_owns_server',return_value=True),patch.object(registry,'_runtime_profile_matches',return_value=True),patch.object(registry,'kill_server') as kill:
        lease=registry.acquire_lease('text')
        assert lease['switch_required'] is False and lease['model_load_time'] is None and lease['available_context']==4096
        kill.assert_not_called()


def test_mismatch_relaunches_only_owned_process(registry):
    with patch.object(registry,'_get_current_alias',return_value='owned'),patch.object(registry,'_owns_server',return_value=True),patch.object(registry,'_runtime_profile_matches',side_effect=[False,True]),patch.object(registry,'kill_server') as kill,patch('router.model_registry.subprocess.Popen') as launch:
        launch.return_value.pid=456
        lease=registry.acquire_lease('text')
        assert lease['switch_required'] is True and lease['model_load_time']>=0
        kill.assert_called_once();launch.assert_called_once()


def test_unowned_matching_alias_never_relaunches(registry):
    with patch.object(registry,'_get_current_alias',return_value='owned'),patch.object(registry,'_owns_server',return_value=False),patch.object(registry,'kill_server') as kill:
        with pytest.raises(WorkbenchError,match='not owned'):registry.acquire_lease('text')
        kill.assert_not_called()


def test_implicit_or_duplicate_kv_configuration_is_not_trusted(registry):
    args=registry.launch_args('text')
    with patch('router.model_registry.psutil.Process') as process:
        process.return_value.cmdline.return_value=args+['-ctk','f16']
        assert not registry._runtime_profile_matches(args)
        process.return_value.cmdline.return_value=[item for index,item in enumerate(args) if index not in {args.index('-ctk'),args.index('-ctk')+1}]
        assert not registry._runtime_profile_matches(args)
