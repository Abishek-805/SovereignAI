import json
from types import SimpleNamespace
import pytest
from backend.contracts import WorkbenchError
from backend.task_supervisor import CURRENT_SUPERVISOR,SupervisorLimits,TaskSupervisor,consume,supervised_task
from backend.task_supervisor import operational_event


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
            assert any(event.get('operation')=='model_calls' for event in saved['events'])
            assert saved['events'][0]['event']=='REQUEST_NORMALIZED'
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


def test_operational_state_survives_worker_switches_with_same_task(tmp_path):
    class Service:
        settings=SimpleNamespace(data_dir=tmp_path)
        @supervised_task
        def act(self,goal,workspace_id,document_ids):
            operational_event('REQUEST_NORMALIZED',normalized_request='Create Python program',workspace='bad',knowledge_scope=['bad'])
            operational_event('PLAN_CREATED',plan=[{'action':'generate','target':'main.py'}],intent='CODE',requested_deliverables=['main.py'])
            consume('model_switches','reasoner')
            operational_event('MODEL_LOADING',selected_model='reasoner')
            operational_event('MODEL_READY')
            operational_event('GENERATION_STARTED')
            operational_event('GENERATION_COMPLETED',observations={'schema_valid':True,'reasoning':'private'})
            consume('model_switches','coder')
            operational_event('MODEL_LOADING',selected_model='coder')
            saved=json.loads(next((tmp_path/'supervision').glob('*.json')).read_text(encoding='utf-8'))
            state=saved['task_state']
            assert state['original_request']==goal and state['normalized_request']=='Create Python program'
            assert state['workspace']==workspace_id and state['knowledge_scope']==document_ids
            assert state['active_worker']=='coder' and state['plan'][0]['target']=='main.py'
            assert state['observations']==[{'schema_valid':True}]
            assert state['model_switch_count']==2
            return {'state':'completed','publication_state':'staged'}
    result=Service().act('creat py program','selected',['source'])
    assert result['supervisor']['task_state']['current_stage']=='READY_FOR_REVIEW'
    assert result['supervisor']['task_state']['completion_status']=='awaiting_review'


def test_terminal_stage_cannot_restart_and_event_budget_is_hard():
    task=TaskSupervisor('goal',{})
    task.record_event('GENERATION_STARTED')
    with pytest.raises(WorkbenchError,match='Cannot move'):
        task.record_event('REQUEST_NORMALIZED')
    task.finish({'state':'completed','checks':{}})
    with pytest.raises(WorkbenchError,match='already stopped'):
        task.record_event('REPAIR_STARTED')
    task=TaskSupervisor('goal',{});task.event_count=512
    with pytest.raises(WorkbenchError,match='event budget'):
        task.record_event('PLAN_CREATED')


def test_repair_replan_and_observations_are_bounded_without_private_reasoning():
    task=TaskSupervisor('goal',{})
    for index in range(50):
        task.record_event('TOOL_COMPLETED',tool_results={'exit_code':1,'chain_of_thought':'hidden'},observations={'attempt':index})
    task.record_event('REPAIR_STARTED',current_action='repair')
    task.record_event('REPLAN_STARTED')
    snapshot=task.snapshot()['task_state']
    assert snapshot['repair_count']==snapshot['replan_count']==1
    assert len(snapshot['tool_results'])==len(snapshot['observations'])==32
    assert len(task.events)==40
    assert 'chain_of_thought' not in snapshot['tool_results'][0]
