from types import SimpleNamespace
import pytest
from tests.test_service import service
from backend.contracts import WorkbenchError


def test_unavailable_validation_stops_before_code_generation(service,monkeypatch):
    generated=[]
    def unavailable():
        raise WorkbenchError('sandbox_unavailable','Validation unavailable')
    monkeypatch.setattr(service,'_verified_coding_sandbox',unavailable)
    monkeypatch.setattr(service.coding,'run_project',lambda *args,**kwargs:generated.append(True))
    with pytest.raises(WorkbenchError) as error:
        service.run_coding_project_task('selected','program.py','Create program.py',routed=True)
    assert error.value.code=='sandbox_unavailable'
    assert generated==[]


def test_ordinary_repairs_keep_coder_affinity(service,monkeypatch):
    leases=[]
    monkeypatch.setattr(service,'_lease',lambda capability,**kwargs:leases.append((capability,kwargs.get('worker_role'))) or 'code')
    monkeypatch.setattr(service,'_verified_coding_sandbox',lambda:SimpleNamespace(_ready=lambda:None))
    monkeypatch.setattr(service.model,'replan_code',lambda *args:'repair proposal',raising=False)
    results=iter([{'state':'failed','checks':{'container_executed':True},'stderr':'first runtime failure'},
                  {'state':'failed','checks':{'container_executed':True},'stderr':'different runtime failure'},
                  {'state':'completed','publication_state':'staged','checks':{'container_executed':True}}])
    monkeypatch.setattr(service.coding,'run_project',lambda *args,**kwargs:next(results))
    result=service.run_coding_project_task('selected','program.py','Fix program.py',routed=True)
    assert result['supervisor_attempts']==3
    assert all(capability=='code' for capability,role in leases)


@pytest.mark.parametrize('repeat_error,expected_attempts',[(False,3),(True,2)])
def test_supervisor_retries_actual_validation_without_publishing(service,monkeypatch,repeat_error,expected_attempts):
    calls=[]
    monkeypatch.setattr(service,'_verified_coding_sandbox',lambda:SimpleNamespace(_ready=lambda:None))
    def run(workspace,target,instruction,*args,**kwargs):
        calls.append((workspace,instruction,kwargs['history']))
        if len(calls)==3:
            return {'state':'completed','publication_state':'staged','checks':{'container_executed':True}}
        return {'state':'failed','checks':{'container_executed':True},
                'stderr':'missing input' if repeat_error else 'error '+str(len(calls)),
                'changes':[{'path':'program.py','after':'candidate'}]}
    monkeypatch.setattr(service.coding,'run_project',run)
    result=service.run_coding_project_task('selected','program.py','Create program.py',routed=True)
    assert result['supervisor_attempts']==expected_attempts
    assert len(calls)==expected_attempts
    assert all(call[:2]==('selected','Create program.py') for call in calls)
    assert 'Actual sandbox validation failed' in calls[1][2][-1]
    assert result['state']==('failed' if repeat_error else 'completed')
    if not repeat_error:assert result['publication_state']=='staged'
