"""Integrated operational acceptance checks, using controlled executor outcomes."""
import json
from types import SimpleNamespace
import pytest

from backend.contracts import WorkbenchError
from backend.jobs import Job
from backend.task_supervisor import CURRENT_SUPERVISOR,consume,operational_event,supervised_task
from router.request_normalization import normalize_request,worker_role
from tests.test_service import service


@pytest.mark.parametrize('user_text,expected',[
    ('creat python file','create python file'),
    ('shwo maintanance interval','show maintenance interval'),
    ('Do not creat files','Do not create files'),
    ('Delete nothing; shwo report','Delete nothing; show report'),
    ('Read "creat" and `shwo`','Read "creat" and `shwo`'),
    ('Open C:/creat/shwo.py and compare 24ALR001','Open C:/creat/shwo.py and compare 24ALR001'),
    ('Use creat@example.edu and maintanance_24','Use creat@example.edu and maintanance_24'),
])
def test_normalization_preserves_quotes_paths_ids_and_negation(user_text,expected):
    result=normalize_request(user_text)
    assert result.original==user_text and result.normalized==expected


def test_simple_greeting_uses_one_inference_and_observed_completion(service,monkeypatch):
    leases=[];inferences=[]
    def lease(capability,required_context=None,worker_role=None):
        leases.append((capability,worker_role));return 'text'
    def simple(request,history):
        consume('model_calls');inferences.append(request);return 'Hello!'
    monkeypatch.setattr(service,'_lease',lease)
    monkeypatch.setattr(service.model,'simple_answer',simple,raising=False)
    monkeypatch.setattr(service.model,'plan_task',lambda *args:pytest.fail('Greeting must not enter semantic planner'))
    result=service.ask('Hi',document_ids=[])
    assert leases==[('text','lightweight')] and inferences==['Hi']
    assert result['completion']['state']=='completed'
    assert result['completion']['checks']['simple_response_delivered'] is True
    assert result['supervisor']['counts']['model_calls']==1
    assert result['supervisor']['counts']['model_switches']==0


def test_two_distinct_docker_errors_repair_with_same_coder_task(service,monkeypatch):
    goal='Create program.py for reading measurements'
    leases=[];calls=[];task_ids=[];replans=[]
    monkeypatch.setattr(service,'_verified_coding_sandbox',lambda:SimpleNamespace(_ready=lambda:None))
    def lease(capability,required_context=None,worker_role=None):
        identity='reasoner' if worker_role=='reasoning' else 'coder'
        consume('model_switches',identity)
        operational_event('MODEL_READY',selected_model=identity,worker_role=worker_role or 'code')
        leases.append((capability,worker_role));return capability
    def run(workspace,target,instruction,*args,**kwargs):
        current=CURRENT_SUPERVISOR.get();task_ids.append(current.id)
        calls.append((workspace,target,instruction,kwargs['history']))
        if len(calls)<3:
            return {'state':'failed','checks':{'container_executed':True},
                    'stderr':'Actual Docker failure '+str(len(calls)),
                    'changes':[{'path':'program.py','after':'uncommitted candidate'}]}
        return {'state':'completed','publication_state':'staged','checks':{'container_executed':True,'tests_passed':True}}
    def replan(instruction,error,candidate):
        current=CURRENT_SUPERVISOR.get()
        replans.append((instruction,error,current.goal,current.context,current.id))
        return 'Read the supplied input path and validate its format.'
    monkeypatch.setattr(service,'_lease',lease)
    monkeypatch.setattr(service.coding,'run_project',run)
    monkeypatch.setattr(service.model,'replan_code',replan,raising=False)
    result=service.run_coding_project_task('selected','program.py',goal,routed=True)
    assert leases==[('code','code')]
    assert len(set(task_ids))==1 and task_ids[0]==result['supervisor']['supervisor_id']
    assert all(call[:3]==('selected','program.py',goal) for call in calls)
    assert replans==[]
    assert 'Actual sandbox validation failed' in calls[2][3][-1]
    assert result['completion']['state']=='awaiting_review' and not result['completion']['achieved']
    assert result['supervisor']['task_state']['replan_count']==0
    assert result['supervisor']['task_state']['current_stage']=='READY_FOR_REVIEW'
    assert result['supervisor']['counts']['model_switches']==1


def test_followup_retains_authoritative_workspace_and_conversation_context(service,monkeypatch):
    history=['user: Create program.py for this project','assistant: program.py has a missing input error']
    captured=[]
    monkeypatch.setattr(service,'_lease',lambda *args,**kwargs:'code')
    monkeypatch.setattr(service,'_verified_coding_sandbox',lambda:SimpleNamespace(_ready=lambda:None))
    def run(workspace,target,instruction,*args,**kwargs):
        captured.append((workspace,instruction,kwargs['history']))
        return {'state':'completed','publication_state':'staged','checks':{'container_executed':True}}
    monkeypatch.setattr(service.coding,'run_project',run)
    result=service.run_coding_project_task('selected','program.py','Fix that',routed=True,history=history)
    assert captured==[('selected','Fix that',history)]
    state=result['supervisor']['task_state']
    assert state['original_request']=='Fix that' and state['workspace']=='selected'
    assert state['conversation_context']==history


def test_cancelled_coding_preserves_original_error_and_never_publishes(service,monkeypatch,tmp_path):
    canonical=tmp_path/'canonical.py';canonical.write_text('original',encoding='utf-8')
    job=Job('agent');published=[]
    monkeypatch.setattr(service,'_lease',lambda *args,**kwargs:'code')
    monkeypatch.setattr(service,'_verified_coding_sandbox',lambda:SimpleNamespace(_ready=lambda:None))
    monkeypatch.setattr(service.coding,'accept',lambda *args:published.append(args))
    def run(*args,**kwargs):
        job.cancel.set()
        raise WorkbenchError('cancelled','Original Docker cancellation detail')
    monkeypatch.setattr(service.coding,'run_project',run)
    with pytest.raises(WorkbenchError) as error:
        service.run_coding_project_task('selected','program.py','Create program.py',routed=True,job=job)
    assert error.value.code=='cancelled'
    assert str(error.value)=='Original Docker cancellation detail'
    assert not published and canonical.read_text(encoding='utf-8')=='original'
    saved=json.loads(next((service.settings.data_dir/'supervision').glob('*.json')).read_text(encoding='utf-8'))
    assert saved['task_state']['current_stage']=='CANCELLED'
    assert not saved['completion']['achieved']


@pytest.mark.parametrize('user_text',[
    'What can you do?','What is a compiler','What is a compiler.',
    'Explain what a compiler is','Tell me a short joke',
])
def test_closed_readonly_faq_shapes_use_lightweight_worker(user_text):
    assert worker_role(user_text)=='lightweight'
    assert worker_role(user_text,documents=True)=='reasoning'
    assert worker_role(user_text,history=['user: Earlier context'])=='reasoning'


def test_synthetic_selected_document_metadata_does_not_disable_faq_fast_path(service,monkeypatch):
    leases=[];calls=[]
    monkeypatch.setattr(service,'_lease',lambda capability,required_context=None,worker_role=None:leases.append(worker_role) or 'text')
    monkeypatch.setattr(service.model,'simple_answer',lambda text,history:calls.append(text) or 'A compiler translates programs.',raising=False)
    monkeypatch.setattr(service.model,'plan_task',lambda *args:pytest.fail('Synthetic scope metadata is not a conversation follow-up'))
    result=service.ask('What is a compiler',document_ids=[])
    assert leases==['lightweight'] and calls==['What is a compiler']
    assert not result['completion']['achieved']  # Actual FAQ correctness was not proven.


def test_real_contextual_history_keeps_faq_on_reasoning_worker(service,monkeypatch):
    roles=[]
    monkeypatch.setattr(service,'_lease',lambda capability,required_context=None,worker_role=None:roles.append(worker_role) or 'text')
    monkeypatch.setattr(service.model,'simple_answer',lambda *args:pytest.fail('Real contextual history must not be discarded'),raising=False)
    monkeypatch.setattr(service.model,'plan_task',lambda *args:{'action':'answer','response':'Contextual response','target':''})
    service.ask('What is a compiler',document_ids=[],history=['user: Explain the previous program'])
    assert roles==['reasoning']


def _followup_service(directory):
    class Service:
        settings=SimpleNamespace(data_dir=directory)
        @supervised_task
        def act(self,goal,workspace_id,document_ids,history=None):
            return {'status':'answered','answer':'Observed response'}
    return Service()


@pytest.mark.parametrize('prefix',['user:','USER:'])
def test_persistent_followup_links_one_prior_task_in_same_scope(tmp_path,prefix):
    service=_followup_service(tmp_path)
    prior=service.act('Create program.py','selected',['doc'])
    result=service.act('Fix that','selected',['doc'],[prefix+' Create program.py'])
    context=result['supervisor']['task_state']['follow_up_context']
    assert context['previous_task_id']==prior['supervisor']['supervisor_id']
    assert context['previous_operational_state']['original_request']=='Create program.py'
    assert result['supervisor']['task_state']['original_request']=='Fix that'
    assert result['supervisor']['task_state']['workspace']=='selected'


@pytest.mark.parametrize('scope',[('other',['doc']),('selected',['other'])])
def test_followup_cannot_inherit_other_workspace_or_document_scope(tmp_path,scope):
    service=_followup_service(tmp_path)
    service.act('Create program.py','selected',['doc'])
    result=service.act('Fix that',*scope,['user: Create program.py'])
    context=result['supervisor']['task_state']['follow_up_context']
    assert 'previous_task_id' not in context
    assert result['supervisor']['task_state']['workspace']==scope[0]
    assert result['supervisor']['task_state']['knowledge_scope']==scope[1]


def test_multiple_prior_matching_tasks_do_not_guess_persistent_target(tmp_path):
    service=_followup_service(tmp_path)
    service.act('Create program.py','selected',['doc'])
    service.act('Create program.py','selected',['doc'])
    result=service.act('Fix that','selected',['doc'],['user: Create program.py'])
    assert 'previous_task_id' not in result['supervisor']['task_state']['follow_up_context']


def test_missing_followup_context_stops_before_worker(tmp_path):
    service=_followup_service(tmp_path)
    with pytest.raises(WorkbenchError) as error:service.act('Fix that','selected',[])
    assert error.value.code=='needs_input'
    saved=json.loads(next((tmp_path/'supervision').glob('*.json')).read_text(encoding='utf-8'))
    assert saved['completion']['state']=='needs_input'
    assert saved['task_state']['current_stage']=='WAITING_FOR_USER'


def test_followup_ignores_corrupt_persisted_record_shapes(tmp_path):
    directory=tmp_path/'supervision';directory.mkdir()
    for index,payload in enumerate([
        [],{'goal':'Create program.py','context':None},
        {'goal':'Create program.py','context':[]},
        {'goal':'Create program.py','supervisor_id':'bad','context':{'workspace_id':'selected','document_ids':['doc']},'task_state':[]},
        {'goal':'Create program.py','supervisor_id':'../../unrelated','context':{'workspace_id':'selected','document_ids':['doc']},'task_state':{}},
    ]):
        (directory/(str(index)+'.json')).write_text(json.dumps(payload),encoding='utf-8')
    service=_followup_service(tmp_path)
    result=service.act('Fix that','selected',['doc'],['user: Create program.py'])
    assert 'previous_task_id' not in result['supervisor']['task_state']['follow_up_context']


def test_followup_link_does_not_recursively_embed_previous_links(tmp_path):
    service=_followup_service(tmp_path)
    first=service.act('Create program.py','selected',['doc'])
    second=service.act('Fix that','selected',['doc'],['user: Create program.py'])
    third=service.act('Continue','selected',['doc'],['user: Fix that'])
    context=third['supervisor']['task_state']['follow_up_context']
    assert context['previous_task_id']==second['supervisor']['supervisor_id']
    assert 'follow_up_context' not in context['previous_operational_state']
    assert first['supervisor']['supervisor_id']!=third['supervisor']['supervisor_id']
