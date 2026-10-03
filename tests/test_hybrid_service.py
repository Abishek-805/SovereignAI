"""Hybrid integration contracts using simulated Docker, not live proof."""
import pytest
from backend.contracts import WorkbenchError
from tests.test_service import service
from tests.test_coding_project import ProjectModel, Sandbox
from router.sandbox import SandboxResult
from router.tool_registry import ToolRegistry


def test_project_failure_repair_reuses_plan_registry_and_preserves_workspace(service, monkeypatch):
    wid=service.coding.create('Hybrid contract')['workspace_id']
    source='def answer():\n    return 0\n'
    service.coding.write(wid,'solution.py',source)
    class Generator(ProjectModel):
        plans=0
        def plan_workspace_edit(self,*args,**kwargs):
            self.plans+=1
            return super().plan_workspace_edit(*args,**kwargs)
    model=Generator([{'action':'edit','path':'solution.py','reason':'requested'}],
                    'def answer():\n    return 1\n','def answer():\n    return 2\n')
    class SequenceSandbox(Sandbox):
        def execute(self,code,input_files):
            self.snapshots.append(input_files.copy())
            return SandboxResult(1 if len(self.snapshots)==1 else 0,'',
                'AssertionError: actual simulated check failed' if len(self.snapshots)==1 else '',True)
    sandbox=SequenceSandbox()
    service.model=model
    monkeypatch.setattr(service,'_verified_coding_sandbox',lambda:sandbox)
    delegated=[]
    original=ToolRegistry.execute
    def execute(registry,name,kwargs):
        delegated.append((id(registry),name,kwargs.copy()))
        return original(registry,name,kwargs)
    monkeypatch.setattr(ToolRegistry,'execute',execute)
    result=service.run_coding_project_task(wid,'solution.py','Fix solution.py',routed=True)
    assert [item[2]['attempt'] for item in delegated]==[1,2]
    assert len({item[0] for item in delegated})==1
    assert {item[1] for item in delegated}=={'coding_project_candidate'}
    assert model.plans==0 and len(sandbox.snapshots)==2
    assert result['validation_exit_code']==0 and result['repair_stop_reason']=='validated'
    assert result['repair_count']==1
    assert service.coding.read(wid,'solution.py')['content']==source
    assert result['operation_plan']['workspace_id']==wid
    assert any(event.get('event')=='PLAN_REUSED' for event in result['events'])
    state=result['supervisor']['task_state']
    assert state['context_scope']['workspace_id']==wid
    assert state['candidate_hash'] and state['current_candidate'][0]['path']=='solution.py'
    assert state['completion_status']=='awaiting_review'


def test_hybrid_stale_workspace_stops_before_second_candidate(service,monkeypatch):
    wid=service.coding.create('Hybrid stale')['workspace_id']
    service.coding.write(wid,'solution.py','x=0\n')
    calls=[]
    monkeypatch.setattr(service,'_verified_coding_sandbox',lambda:Sandbox())
    def candidate(*args,**kwargs):
        calls.append(True)
        service.coding.write(wid,'solution.py','x=99\n')
        return {'state':'failed','checks':{'container_executed':True},'validation_exit_code':1,'stderr':'ValueError: observed','changes':[]}
    monkeypatch.setattr(service.coding,'run_project',candidate)
    with pytest.raises(WorkbenchError) as error:
        service.run_coding_project_task(wid,'solution.py','Fix solution.py',routed=True)
    assert error.value.code=='workspace_conflict' and len(calls)==1
    assert service.coding.read(wid,'solution.py')['content']=='x=99\n'




def test_hybrid_cancellation_after_failed_candidate_prevents_retry(service,monkeypatch):
    from threading import Event
    from types import SimpleNamespace
    wid=service.coding.create('Hybrid cancel')['workspace_id']
    service.coding.write(wid,'solution.py','x=0\n')
    calls=[]
    job=SimpleNamespace(cancel=Event(),progress=lambda *_:None,append=lambda *_:None)
    monkeypatch.setattr(service,'_verified_coding_sandbox',lambda:Sandbox())
    def candidate(*args,**kwargs):
        calls.append(True)
        job.cancel.set()
        return {'state':'failed','checks':{'container_executed':True},'validation_exit_code':1,'stderr':'ValueError: observed','changes':[]}
    monkeypatch.setattr(service.coding,'run_project',candidate)
    with pytest.raises(WorkbenchError) as error:
        service.run_coding_project_task(wid,'solution.py','Fix solution.py',routed=True,job=job)
    assert error.value.code=='cancelled' and len(calls)==1
    assert service.coding.read(wid,'solution.py')['content']=='x=0\n'
