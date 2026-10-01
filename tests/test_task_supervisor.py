import json
from types import SimpleNamespace
import pytest
from backend.contracts import WorkbenchError
from backend.task_supervisor import CURRENT_SUPERVISOR,SupervisorLimits,TaskSupervisor,consume,supervised_task


def test_one_envelope_for_nested_workflows_preserves_scope(tmp_path):
    class Service:
        settings=SimpleNamespace(data_dir=tmp_path)
        @supervised_task
        def outer(self,goal,document_ids,workspace_id):
            self.inner('changed internal goal')
            document_ids.append('unrequested')
            return {'status':'answered','answer':'Response'}
        @supervised_task
        def inner(self,question):
            consume('model')
            assert CURRENT_SUPERVISOR.get().goal=='Original request'
    result=Service().outer('Original request',['allowed'],'selected')
    assert result['supervisor']['context']=={'document_ids':['allowed'],'workspace_id':'selected'}
    assert result['supervisor']['counts']['model_calls']==1
    assert len(list((tmp_path/'supervision').glob('*.json')))==1
    assert not result['completion']['achieved']
    assert CURRENT_SUPERVISOR.get() is None


def test_checkpoint_persists_running_observations_before_completion(tmp_path):
    class Service:
        settings=SimpleNamespace(data_dir=tmp_path)
        @supervised_task
        def act(self,goal):
            consume('model_calls')
            saved=json.loads(next((tmp_path/'supervision').glob('*.json')).read_text(encoding='utf-8'))
            assert saved['outcome']=='running'
            assert saved['goal']==goal and saved['counts']['model_calls']==1
            assert saved['events'][0]['operation']=='model_calls'
            return {'status':'answered','answer':'Response'}
    Service().act('Keep my request')


def test_budgets_enforce_before_next_operation_and_model_affinity():
    task=TaskSupervisor('goal',{},SupervisorLimits(model_calls=1,model_switches=1))
    task.consume('switch','text');task.consume('switch','text')
    assert task.counts['model_switches']==1
    with pytest.raises(WorkbenchError,match='budget exhausted'):task.consume('switch','code')
    task.consume('model')
    with pytest.raises(WorkbenchError,match='budget exhausted'):task.consume('model')
    assert task.counts['model_calls']==1


def test_exception_persisted_without_replacing_error(tmp_path):
    class Service:
        settings=SimpleNamespace(data_dir=tmp_path)
        @supervised_task
        def act(self,instruction):raise WorkbenchError('needs_input','Choose the target')
    with pytest.raises(WorkbenchError,match='Choose the target'):Service().act('Update file')
    saved=json.loads(next((tmp_path/'supervision').glob('*.json')).read_text(encoding='utf-8'))
    assert saved['outcome']=='needs_input' and not saved['completion']['achieved']
    assert saved['goal']=='Update file'


def test_invalid_budget_and_cancel_and_deadline():
    with pytest.raises(ValueError):SupervisorLimits(model_calls=True)
    with pytest.raises(ValueError):SupervisorLimits(seconds=float('inf'))
    import threading
    job=SimpleNamespace(cancel=threading.Event());job.cancel.set()
    with pytest.raises(WorkbenchError,match='stopped'):TaskSupervisor('g',{},job=job).checkpoint()
    task=TaskSupervisor('g',{},SupervisorLimits(seconds=.01));task.started-=1
    with pytest.raises(WorkbenchError,match='time budget'):task.checkpoint()


def test_model_admission_counts_inference_and_stops_before_extra_request(monkeypatch):
    from backend.model import LocalModel
    model=LocalModel();calls=[]
    monkeypatch.setattr(model,'_request_raw',lambda method,path,**kwargs:calls.append(path) or {})
    task=TaskSupervisor('g',{},SupervisorLimits(model_calls=1))
    token=CURRENT_SUPERVISOR.set(task)
    try:
        model._request('POST','/tokenize',json={'content':'reference'})
        model._request('POST','/v1/chat/completions',json={})
        with pytest.raises(WorkbenchError,match='budget exhausted'):
            model._request('POST','/v1/chat/completions',json={})
        assert calls==['/tokenize','/v1/chat/completions']
        assert task.counts['model_calls']==1
    finally:
        CURRENT_SUPERVISOR.reset(token);model.close()
