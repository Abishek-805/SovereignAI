from types import SimpleNamespace
import pytest
from tests.test_service import service


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
