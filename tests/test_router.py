import pytest
from backend.contracts import WorkbenchError
from router.sandbox import CodeSandbox, SandboxResult
from router.tool_registry import ToolRegistry, ToolContract
from router.orchestrator import Orchestrator, TaskState
from router.router import CapabilityRouter
from router.model_registry import ModelRegistry, ModelSpec
import httpx
from unittest.mock import patch

def test_sandbox_disabled_fallback():
    sandbox = CodeSandbox("none")
    res = sandbox.execute("print('hello')")
    assert res.exit_code == -1
    assert res.executed is False
    assert "Execution Disabled" in res.stdout

def test_sandbox_unsupported():
    sandbox = CodeSandbox("unsupported")
    with pytest.raises(WorkbenchError) as exc:
        sandbox.execute("print('hello')")
    assert "Unsupported sandbox backend" in str(exc.value)


def test_docker_runner_requires_pinned_image(tmp_path):
    sandbox=CodeSandbox('docker',task_root=tmp_path,docker_cli='docker')
    with pytest.raises(WorkbenchError,match='pinned'):
        sandbox.execute('print(1)')


def test_docker_runner_security_arguments(tmp_path,monkeypatch):
    from io import BytesIO
    import subprocess
    calls=[]
    image='sha256:'+'a'*64
    class Process:
        def __init__(self,args,**kwargs):
            calls.append(args)
            self.stdout=BytesIO(b'ok\n');self.stderr=BytesIO()
        def wait(self,timeout=None): return 0
    def command(args,**kwargs):
        if args[3]=='info': return type('Completed',(),{'stdout':'linux\n'})()
        return type('Completed',(),{})()
    monkeypatch.setattr('router.sandbox.subprocess.run',command)
    monkeypatch.setattr('router.sandbox.subprocess.Popen',Process)
    sandbox=CodeSandbox('docker',image_id=image,task_root=tmp_path,docker_cli='docker')
    result=sandbox.execute('print(1)',input_files={'input.csv':b'a,b\n1,2\n'})
    assert result.executed and result.stdout=='ok\n'
    args=calls[0]
    for flag in ('--network=none','--read-only','--cap-drop=ALL','--security-opt=no-new-privileges',
                 '--pids-limit=64','--memory=512m','--cpus=1','--ulimit=fsize=33554432:33554432',
                 '--user=65534:65534','--pull=never'):
        assert flag in args
    assert image in args
    assert args[1:3]==['--host','npipe:////./pipe/dockerDesktopLinuxEngine']
    assert not any('DockerDesktop' in arg for arg in args)

def test_tool_registry():
    reg = ToolRegistry()
    reg.register("add", lambda x, y: x + y)
    
    assert reg.execute("add", {"x": 2, "y": 3}) == 5
    
    with pytest.raises(WorkbenchError) as exc:
        reg.execute("missing", {})
    assert exc.value.code == "tool_not_found"
    
    with pytest.raises(WorkbenchError):
        reg.register("add", lambda: None)


def test_tool_contract_rejects_extra_inputs_and_large_results():
    reg=ToolRegistry()
    reg.register('bounded',lambda value: {'value':value},
                 ToolContract(('value',),('value',),max_input_bytes=30,max_output_bytes=30))
    assert reg.execute('bounded',{'value':'ok'})=={'value':'ok'}
    with pytest.raises(WorkbenchError) as exc:
        reg.execute('bounded',{'value':'ok','shell':'cmd'})
    assert exc.value.code=='tool_input'
    with pytest.raises(WorkbenchError) as exc:
        reg.execute('bounded',{'value':'x'*25})
    assert exc.value.code=='resource_limit'

def test_orchestrator_fsm():
    tools = ToolRegistry()
    tools.register("fail_tool", lambda: exec("raise ValueError('Oops')"))
    tools.register("success_tool", lambda: "Success")
    
    # Use a dummy registry for tests
    class DummyRegistry:
        pass
        
    orch = Orchestrator(tools, DummyRegistry())
    task = orch.create_task("task1", "do something")
    
    assert task.state == TaskState.CREATED
    
    # Success step
    orch.run_step("task1", "success_tool", {})
    assert task.state == TaskState.CHECKING
    assert task.step_count == 1
    with pytest.raises(WorkbenchError):
        orch.complete_task('task1', {'verified':False})
    
    # Needs to transition to running/planning for next step
    task.transition(TaskState.PLANNING)
    
    # Fail step triggers repair
    orch.run_step("task1", "fail_tool", {})
    assert task.state == TaskState.REPAIRING
    assert task.repair_count == 1
    
    # Fail again triggers 2nd repair
    orch.run_step("task1", "fail_tool", {})
    assert task.state == TaskState.REPAIRING
    assert task.repair_count == 2
    
    # Fail again triggers failed state (budget exhausted)
    orch.run_step("task1", "fail_tool", {})
    assert task.state == TaskState.FAILED
    with pytest.raises(WorkbenchError):
        task.transition(TaskState.RUNNING)


def test_orchestrator_requires_checks_before_completion():
    tools=ToolRegistry(); tools.register('inspect',lambda: {'valid':True})
    orch=Orchestrator(tools,object())
    task=orch.create_task('review','inspect artifact')
    orch.run_step('review','inspect',{})
    with pytest.raises(WorkbenchError):
        task.transition(TaskState.COMPLETED)
    assert orch.complete_task('review',{'artifact_valid':True}).state==TaskState.COMPLETED
    with pytest.raises(WorkbenchError):
        orch.run_step('review','inspect',{})

def test_capability_router():
    class DummyRegistry:
        pass
    router = CapabilityRouter(DummyRegistry())
    
    assert router.route_request("text") == "text"
    assert router.route_request("vision") == "vision"
    assert router.route_request("code") == "text"
    
    with pytest.raises(WorkbenchError):
        router.route_request("unknown")


def test_bounded_agent_classification():
    router=CapabilityRouter(object())
    assert router.classify_agent_goal('Calculate: 2+2')=='CALCULATION'
    assert router.classify_agent_goal('Fix parser',workspace_id='workspace')=='CODING'
    assert router.classify_agent_goal('What is the limit?',document_ids=['doc'])=='DOCUMENT_QA'
    assert router.classify_agent_goal('Prepare maintenance note',document_ids=['doc'])=='ARTIFACT'
    assert router.classify_agent_goal('What is visible?',image=True)=='VISION'
    with pytest.raises(WorkbenchError,match='Choose documents'):
        router.classify_agent_goal('Control machinery')


def test_orchestrator_nonretryable_failure_and_step_limit():
    tools=ToolRegistry(); tools.register('fail',lambda: (_ for _ in ()).throw(WorkbenchError('tool_failure','Failed')))
    tools.register('ok',lambda: {'status':'completed'})
    orch=Orchestrator(tools,object())
    task=orch.create_task('failure','run')
    with pytest.raises(WorkbenchError,match='Failed'):
        orch.run_step('failure','fail',{},retryable=False)
    assert task.state==TaskState.FAILED and task.repair_count==0
    limited=orch.create_task('limited','run'); limited.max_steps=0
    with pytest.raises(WorkbenchError) as exc:
        orch.run_step('limited','ok',{})
    assert exc.value.code=='step_limit' and limited.state==TaskState.FAILED


def test_orchestrator_emits_authoritative_states_during_tool_execution():
    seen=[]
    tools=ToolRegistry()
    tools.register('inspect',lambda: seen.append('tool:'+seen[-1]) or {'valid':True})
    orch=Orchestrator(tools,object())
    task=orch.create_task('live','inspect',on_change=lambda current: seen.append(current.state.value))
    orch.run_step('live','inspect',{})
    orch.complete_task('live',{'valid':True})
    assert seen==['created','running','tool:running','checking','completed']


def test_capability_router_rejects_unavailable_or_wrong_modality():
    from dataclasses import replace
    registry=ModelRegistry()
    router=CapabilityRouter(registry)
    registry.specs['vision']=replace(registry.specs['vision'],enabled=False)
    with pytest.raises(WorkbenchError,match='disabled'):
        router.route_request('vision')
    registry.specs['vision']=replace(registry.specs['vision'],enabled=True,modalities=('text',))
    with pytest.raises(WorkbenchError,match='image'):
        router.route_request('vision')


def test_registry_reads_actual_served_alias():
    def fake_get(url, **kwargs):
        if url.endswith('/v1/models'):
            return httpx.Response(200, json={'data':[{'id':'sovereign-vision'}]})
        raise AssertionError(url)
    with patch('router.model_registry.httpx.get', side_effect=fake_get):
        assert ModelRegistry()._get_current_alias() == 'sovereign-vision'


def test_registry_does_not_kill_unowned_pid(tmp_path):
    pid_file=tmp_path/'server.pid'; pid_file.write_text('123')
    with patch('router.model_registry.PID_FILE',pid_file), patch('router.model_registry.psutil.Process') as process, patch('router.model_registry.subprocess.run') as run:
        process.return_value.exe.return_value = r'C:\\Windows\\System32\\notepad.exe'
        with pytest.raises(WorkbenchError,match='not owned'):
            ModelRegistry().kill_server()
        run.assert_not_called()


def test_missing_vision_assets_do_not_stop_text_server(tmp_path):
    registry=ModelRegistry()
    with patch.object(registry,'_get_current_alias',return_value='sovereign-text'), \
         patch.object(registry,'kill_server') as stop, \
         patch('router.model_registry.ROOT',tmp_path):
        with pytest.raises(WorkbenchError,match='Vision model files missing'):
            registry.acquire_lease('vision')
        stop.assert_not_called()


def test_switch_rejects_unowned_model_port(tmp_path):
    model=tmp_path/'models'/'Qwen3-4B-Instruct-2507-Q4_K_M.gguf'
    model.parent.mkdir()
    model.write_bytes(b'test')
    registry=ModelRegistry()
    with patch('router.model_registry.ROOT',tmp_path), \
         patch.object(registry,'_get_current_alias',return_value='other-model'), \
         patch.object(registry,'_owns_server',return_value=False), \
         patch.object(registry,'kill_server') as stop:
        with pytest.raises(WorkbenchError,match='does not own'):
            registry.acquire_lease('text')
        stop.assert_not_called()


def test_matching_alias_still_requires_owned_process(tmp_path):
    model=tmp_path/'models'/'Qwen3-4B-Instruct-2507-Q4_K_M.gguf'
    model.parent.mkdir()
    model.write_bytes(b'test')
    registry=ModelRegistry()
    with patch('router.model_registry.ROOT',tmp_path), \
         patch.object(registry,'_get_current_alias',return_value='sovereign-text'), \
         patch.object(registry,'_owns_server',return_value=False):
        with pytest.raises(WorkbenchError,match='not owned'):
            registry.acquire_lease('text')


def test_registry_accepts_reviewed_entry_without_orchestrator_change(tmp_path):
    model=tmp_path/'models'/'small'/'code.gguf'
    model.parent.mkdir(parents=True)
    model.write_bytes(b'test')
    registry=ModelRegistry()
    spec=ModelSpec('code-specialist','sovereign-code','small/code.gguf',
                   revision='reviewed-revision',license_reference='docs/license.md',license_id='fixture-license',license_reviewed=True)
    with patch('router.model_registry.ROOT',tmp_path):
        registry.register(spec)
        args=registry.launch_args('code-specialist')
        assert args[args.index('--alias')+1]=='sovereign-code'
        assert str(model) in args
        with pytest.raises(WorkbenchError):
            registry.register(ModelSpec('escape','unsafe','../outside.gguf'))
