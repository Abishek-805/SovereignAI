import json
import pytest
from workflows.agent_kernel import ToolRegistry,WorkspaceManager,PermissionPolicy,AgentLoop
from workflows.coding_workspace import CodingWorkspace

def test_schema_and_path_policy():
    registry=ToolRegistry()
    assert {'list_dir','read_file','search_code','write_file','apply_patch','delete_file','run_command','run_tests','inspect_process','finish'}<=set(registry.fields)
    with pytest.raises(ValueError):registry.check('write_file',{'path':'x'})
    policy=PermissionPolicy('edit source',{'source.py':b'original','test_acceptance.py':b'test'})
    with pytest.raises(ValueError):policy.path('../outside')
    with pytest.raises(ValueError):policy.edit('source.py',set(),{'source.py':b'x'})
    with pytest.raises(ValueError):policy.edit('test_acceptance.py',{'test_acceptance.py'},{'test_acceptance.py':b'x'})
    with pytest.raises(ValueError):policy.edit('source.py',{'source.py'},{'source.py':b'x'},True)
    assert policy.path('./source.py')=='source.py'

def test_overlay_checkpoint_does_not_mutate_existing_project(tmp_path):
    coding=CodingWorkspace(tmp_path);wid=coding.create('Existing')['workspace_id']
    coding.write(wid,'main.py','print(1)\n');coding.write(wid,'keep.java','class Keep {}\n')
    workspace=WorkspaceManager(coding,wid,'Modify main.py; keep keep.java unchanged.')
    workspace.read.add('main.py');workspace.write('main.py','print(2)\n')
    assert coding.read(wid,'main.py')['content']=='print(1)\n'
    assert len(workspace.changes())==1 and '+print(2)' in workspace.diff()
    coding.write(wid,'main.py','print(3)\n')
    with pytest.raises(Exception,match='Workspace changed'):workspace.assert_revision()

def test_model_done_cannot_bypass_independent_validation(tmp_path):
    coding=CodingWorkspace(tmp_path);wid=coding.create('No oracle')['workspace_id']
    class Sandbox:
        image_id='pinned'
        def _ready(self):pass
    class Model:
        def agent_tool_turn(self,messages,tools,alias):
            return {'role':'assistant','content':'','tool_calls':[{'id':'call1','type':'function','function':{'name':'finish','arguments':'{}'}}]}
    result=AgentLoop().run(coding,wid,'Create a program.',Model(),Sandbox(),'fixed')
    assert result['agent_state']=='BLOCKED' and result['state']=='failed'
    assert not result['checks']['container_executed']
    assert result.get('publication_state') is None

def test_retention_never_removes_user_workspace_or_evidence(tmp_path):
    from workflows.agent_retention import EphemeralRetention
    user=tmp_path/'workspaces';user.mkdir();(user/'user.py').write_text('valuable')
    cache=EphemeralRetention(tmp_path,max_bytes=2)
    (cache.root/'cache-old.json').write_text('unknown ownership')
    (cache.root/'accepted.docx').write_text('must remain')
    verdict=cache.prune()
    assert verdict['removed_owned_cache_files']==[]
    owned=cache.write('b'*32,{'log':'disposable'})
    assert not __import__('pathlib').Path(owned).exists()
    assert (cache.root/'cache-old.json').exists()
    assert (user/'user.py').read_text()=='valuable'
    assert (cache.root/'accepted.docx').read_text()=='must remain'

def test_native_stream_tool_arguments_are_not_dropped():
    import httpx,threading
    from backend.model import LocalModel
    chunks=[{'choices':[{'index':0,'delta':{'tool_calls':[{'index':0,'id':'call_1','function':{'name':'read_file','arguments':'{"path":'}}]},'finish_reason':None}]},
            {'choices':[{'index':0,'delta':{'tool_calls':[{'index':0,'function':{'arguments':'"main.py"}'}}]},'finish_reason':'tool_calls'}]}]
    def transport(request):
        payload=json.loads(request.content)
        assert payload['tools'] and payload['parallel_tool_calls'] is False
        assert payload['chat_template_kwargs']=={'enable_thinking':False}
        stream=''.join('data: '+json.dumps(chunk)+'\n\n' for chunk in chunks)+'data: [DONE]\n\n'
        return httpx.Response(200,headers={'Content-Type':'text/event-stream'},content=stream)
    model=LocalModel(transport=httpx.MockTransport(transport))
    with model.cancel_scope(threading.Event()):result=model.agent_tool_turn([{'role':'user','content':'Read main.py'}],ToolRegistry().schemas(),'fixed')
    call=result['tool_calls'][0]
    assert call['id']=='call_1' and call['function']['name']=='read_file'
    assert json.loads(call['function']['arguments'])=={'path':'main.py'}

def test_ephemeral_log_preserves_unicode(tmp_path):
    from workflows.agent_retention import EphemeralRetention
    cache=EphemeralRetention(tmp_path)
    path=cache.write('a'*32,{'output':'✓ validated — மாணவர்'})
    assert json.loads(__import__('pathlib').Path(path).read_text(encoding='utf-8'))['records']['output']=='✓ validated — மாணவர்'

def test_checkpoint_recovers_rejected_null_arguments_and_no_final_newline(tmp_path):
    from workflows.agent_kernel import CheckpointStore,ObservationStore,AgentSession
    coding=CodingWorkspace(tmp_path);wid=coding.create('Draft')['workspace_id'];coding.write(wid,'main.py','old')
    workspace=WorkspaceManager(coding,wid,'Modify main.py');workspace.read.add('main.py');workspace.write('main.py','new')
    assert '\\ No newline at end of file' in workspace.diff()
    assert '-old\n' in workspace.diff() and '+new\n' in workspace.diff()
    observations=ObservationStore();observations.add('write_file',None,{'error':'invalid arguments'})
    session=AgentSession('Modify main.py',wid,'fixed');checkpoint=CheckpointStore(coding,wid,session.task_id)
    checkpoint.save(session,workspace,observations)
    saved=json.loads(checkpoint.path.read_text())
    assert saved['observations'][0]['arguments']=={'invalid_arguments':None}
    assert 'after' not in saved['changes'][0] and saved['diff']==workspace.diff()

def test_unrelated_or_zero_test_suite_cannot_prove_new_implementation(tmp_path):
    from workflows.agent_kernel import ValidationEngine,AgentSession
    from router.sandbox import SandboxResult
    coding=CodingWorkspace(tmp_path);wid=coding.create('Oracle')['workspace_id']
    coding.write(wid,'test_old.py','import unittest\nclass Old(unittest.TestCase):\n def test_old(self):self.assertTrue(True)\n')
    workspace=WorkspaceManager(coding,wid,'Create a.py');workspace.write('a.py','print(42)\n')
    class Sandbox:
        def execute(self,*a,**k):return SandboxResult(0,'INDEPENDENT_ORACLE_TEST_COUNT=0\n','',True)
    session=AgentSession('Create a.py',wid,'fixed')
    result=ValidationEngine(workspace,Sandbox(),session).validate()
    assert result['state']=='BLOCKED' and not result['passed']
    coding.write(wid,'test_old.py','import a\n')
    workspace=WorkspaceManager(coding,wid,'Create a.py');workspace.write('a.py','print(42)\n')
    result=ValidationEngine(workspace,Sandbox(),session).validate()
    assert result['test_count']==0 and not result['passed']

def test_native_outer_budget_matches_owner_and_legacy_stays_frozen(monkeypatch):
    from backend.application_tools import ApplicationTools
    from types import SimpleNamespace
    monkeypatch.setenv('SOVEREIGN_AGENT_KERNEL','1')
    service=SimpleNamespace(model=SimpleNamespace(agent_tool_turn=lambda:None),routing_strategy='capability',supervisor_limits=SimpleNamespace(seconds=900))
    assert ApplicationTools(service).registry.contracts['file_edit'].timeout_seconds==900
    service.routing_strategy='universal'
    assert ApplicationTools(service).registry.contracts['file_edit'].timeout_seconds==300

def test_actual_command_failure_is_retained_and_repair_counted(tmp_path,monkeypatch):
    from workflows.agent_kernel import ValidationEngine
    coding=CodingWorkspace(tmp_path);wid=coding.create('Repair observation')['workspace_id']
    coding.write(wid,'main.py','print(1)\n')
    outcomes=iter([1,0])
    monkeypatch.setattr(ValidationEngine,'command',lambda self,command:{'container_executed':True,'exit_code':next(outcomes),'stderr':'specific runtime error'})
    monkeypatch.setattr(ValidationEngine,'validate',lambda self:{'passed':True,'independent':True,'container_executed':True,'exit_code':0})
    actions=iter([('run_command',{'command':'python main.py'}),('read_file',{'path':'main.py'}),('apply_patch',{'path':'main.py','old_text':'print(1)','new_text':'print(42)'}),('run_command',{'command':'python main.py'}),('finish',{})])
    class Sandbox:
        image_id='pinned'
        def _ready(self):pass
    class Model:
        def agent_tool_turn(self,messages,tools,alias):
            name,args=next(actions)
            return {'role':'assistant','tool_calls':[{'id':name+str(len(messages)),'type':'function','function':{'name':name,'arguments':json.dumps(args)}}]}
    result=AgentLoop().run(coding,wid,'Edit main.py to print 42',Model(),Sandbox(),'fixed')
    assert result['state']=='completed'
    assert result['metrics']['validation_failures']==1 and result['metrics']['repairs']==1
    checkpoint=json.loads((coding._directory(wid)/'tasks'/(result['task_id']+'-agent.json')).read_text())
    assert checkpoint['session']['repairs']==1
