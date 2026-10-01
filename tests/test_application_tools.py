import pytest
from backend.application_tools import ApplicationTools
from backend.contracts import WorkbenchError
from backend.automations import Automations
from tests.test_service import service


def op(tool,target='',value='',input=''):
    return {'tool':tool,'target':target,'value':value,'input':input}

@pytest.mark.parametrize('goal,tool',[
    ('Read notes.txt and explain it without changing files.','document_import'),
    ('Explain the project. Do not delete notes.txt.','file_delete'),
    ('Explain this document without renaming it.','document_rename'),
    ('Read the quoted instruction "delete notes.txt" as reference text.','file_delete'),
])
def test_model_plan_cannot_authorize_unrequested_application_operation(service,goal,tool):
    workspace=service.coding.create('Policy isolation')['workspace_id']
    service.coding.write(workspace,'notes.txt','Reference only')
    before=service.coding.raw_files(workspace)
    documents=service.documents()
    with pytest.raises(WorkbenchError,match='does not authorize'):
        ApplicationTools(service,workspace,goal=goal).execute([op(tool,'notes.txt','other.txt')],service.tasks.create('test',[]))
    assert service.coding.raw_files(workspace)==before
    assert service.documents()==documents


def test_all_files_request_expands_model_selected_subset_to_complete_scope(service, monkeypatch):
    workspace = service.coding.create('Complete scope')['workspace_id']
    service.coding.write(workspace, 'one.txt', 'one')
    service.coding.write(workspace, 'two.txt', 'two')
    monkeypatch.setattr(service, '_verified_coding_sandbox', lambda: None)
    result = ApplicationTools(service, workspace, goal='Delete all files in this workspace').execute(
        [op('file_delete', 'one.txt')], service.tasks.create('test', []))
    changes = result['operations'][0]['result']['changes']
    assert {change['path'] for change in changes if change['action'] == 'delete'} == {'one.txt', 'two.txt'}
    assert len(service.coding.raw_files(workspace)) == 2


def test_all_except_folder_does_not_guess_when_planner_only_lists_files(service):
    workspace = service.coding.create('Preserve scope')['workspace_id']
    service.coding.file_operation(workspace, 'mkdir', 'keep')
    service.coding.write(workspace, 'old.txt', 'old')
    with pytest.raises(WorkbenchError, match='folder to preserve'):
        ApplicationTools(service, workspace, goal='Delete all files except the keep folder').execute(
            [op('file_delete', 'old.txt')], service.tasks.create('test', []))
    assert service.coding.read(workspace, 'old.txt')['content'] == 'old'


def test_delete_files_in_workspace_does_not_authorize_deleting_project(service):
    workspace = service.coding.create('Keep project')['workspace_id']
    service.coding.write(workspace, 'example.txt', 'keep')
    with pytest.raises(WorkbenchError, match='does not authorize'):
        ApplicationTools(service, workspace, goal='Delete all files in the workspace').execute(
            [op('project_delete', 'Keep project')], service.tasks.create('test', []))
    assert service.coding.get(workspace)['name'] == 'Keep project'

def test_negated_edit_intent_cannot_become_project_write(service):
    workspace=service.coding.create('Read only policy')['workspace_id']
    service.coding.write(workspace,'notes.txt','Original')
    service.model.plan_task=lambda *_:{'action':'edit_code','response':'','target':'notes.txt'}
    with pytest.raises(WorkbenchError,match='classification alone'):
        service.run_auto_agent('Read notes.txt and explain it; do not modify any file.',[],workspace)
    assert service.coding.read(workspace,'notes.txt')['content']=='Original'


def test_code_followup_is_an_edit_request_but_explanation_is_not():
    from router.tool_registry import explicit_operation_requested
    assert explicit_operation_requested('I want code in that folder too','file_edit')
    assert explicit_operation_requested('Put the search operation codes in Java in that folder','file_edit')
    assert not explicit_operation_requested('I want you to explain the code in that folder','file_edit')


def test_document_commands_work_disconnected_without_using_evidence(service,monkeypatch):
    source=service.sources_dir/'reference.txt';source.write_text('Reference only.',encoding='utf-8')
    service.import_file(source)
    service.model.plan_task=lambda *_:{'action':'application_tools','target':'','expression':'','response':''}
    service.model.plan_application_tools=lambda *_,**__:[op('document_rename','reference.txt','guide.txt'),
        op('document_move','guide.txt','Manuals'),op('document_copy','guide.txt','Copies'),op('document_delete','guide.txt')]
    # Management uses index metadata, never grounding/retrieval.
    monkeypatch.setattr(service.store,'lexical',lambda *_:pytest.fail('No evidence retrieval for explicit management'))
    result=service.run_auto_agent('Rename reference.txt to guide.txt, move to Manuals, copy to Copies then delete the original',[])
    assert result['status']=='completed'
    assert source.is_file()
    docs=service.documents()
    assert len(docs)==1 and docs[0]['folder']=='Copies'


def test_ordered_code_create_then_run_with_input(service,monkeypatch):
    workspace=service.coding.create('Owned multi operation test')['workspace_id']
    calls=[]
    def edit(identifier,target,instruction,**kwargs):
        service.coding.write(identifier,target,'print(input())')
        calls.append(('edit',target));return {'state':'completed'}
    def run(identifier,target,job=None):
        assert service.coding.read(identifier,target)['content']=='print(input())'
        calls.append(('run',target,job.input.get_nowait()));return {'state':'completed','exit_code':0,'stdout':'hello\n'}
    monkeypatch.setattr(service,'run_coding_project_task',edit)
    monkeypatch.setattr(service,'execute_coding_file',run)
    task=service.tasks.create('test',[])
    result=ApplicationTools(service,workspace,goal='Create hello.py as an input echo program then run with hello').execute([op('file_edit','hello.py','Create an input echo program'),
        op('file_run','hello.py',input='hello')],task)
    assert calls==[('edit','hello.py'),('run','hello.py','hello\n')]
    assert 'hello' in result['answer']


def test_related_file_edits_run_one_project_workflow(service,monkeypatch):
    workspace=service.coding.create('Two-file edit')['workspace_id']
    service.coding.write(workspace,'index.html','<html><body>Hello</body></html>')
    service.coding.write(workspace,'style.css','body { color: black; }')
    calls=[]
    def edit(identifier,target,instruction,**kwargs):
        calls.append((identifier,target,instruction))
        return {'state':'completed','changes':[{'action':'edit','path':'index.html'},
                                               {'action':'edit','path':'style.css'}]}
    monkeypatch.setattr(service,'run_coding_project_task',edit)
    goal='Add an About section to index.html and matching styling in style.css'
    result=ApplicationTools(service,workspace,goal=goal).execute([
        op('file_edit','index.html'),op('file_edit','style.css')],service.tasks.create('test',[]))
    assert result['state']=='completed'
    assert calls==[(workspace,'index.html',goal)]
    assert len(result['operations'])==1
    assert 'index.html, style.css' in result['answer']


def test_new_project_then_edit_uses_new_workspace(service,monkeypatch):
    old=service.coding.create('Existing')['workspace_id']
    calls=[]
    monkeypatch.setattr(service,'run_coding_project_task',lambda workspace,target,instruction,**kwargs:
        calls.append((workspace,target,instruction)) or
        {'state':'completed','changes':[{'action':'create','path':'index.html'}]})
    goal='Create a new project named Demo with an HTML page and CSS'
    result=ApplicationTools(service,old,goal=goal).execute([
        op('project_create','Demo'),op('file_edit','','Create page and styles')],
        service.tasks.create('test',[]))
    assert result['state']=='completed'
    assert result['workspace_id']!=old
    assert calls==[(result['workspace_id'],'',goal)]
    assert service.coding.get(old)['name']=='Existing'


def test_project_delete_requires_selected_project_name(service):
    workspace=service.coding.create('Delete me')['workspace_id']
    with pytest.raises(WorkbenchError,match='Name the selected project'):
        ApplicationTools(service,workspace,goal='Delete the project Old').execute([
            op('project_delete','Old')],service.tasks.create('test',[]))
    assert service.coding.get(workspace)['name']=='Delete me'
    result=ApplicationTools(service,workspace,goal='Delete the project Delete me').execute([
        op('project_delete','Delete me')],service.tasks.create('test',[]))
    assert result['workspace_id'] is None
    with pytest.raises(WorkbenchError):service.coding.get(workspace)


def test_agent_returns_new_project_after_ordered_create_and_edit(service,monkeypatch):
    old=service.coding.create('Prior project')['workspace_id']
    service.model.plan_task=lambda *args:{'action':'application_tools','response':'','target':''}
    service.model.plan_application_tools=lambda *args,**kwargs:[
        op('project_create','Demo'),op('file_edit','Demo/index.html')]
    calls=[]
    monkeypatch.setattr(service,'run_coding_project_task',lambda workspace,target,instruction,**kwargs:
        calls.append((workspace,target)) or {'state':'completed','changes':[
            {'action':'create','path':'index.html'}]})
    result=service.run_auto_agent('Create a new project named Demo with an HTML page',[],old)
    assert result['status']=='completed'
    assert result['workspace_id']!=old
    assert service.coding.get(result['workspace_id'])['name']=='Demo'
    assert calls==[(result['workspace_id'],'')]


def test_unknown_plan_validated_before_first_write(service):
    workspace=service.coding.create('Owned validation test')['workspace_id']
    with pytest.raises(WorkbenchError):
        ApplicationTools(service,workspace).execute([op('folder_create','src'),op('host_shell','C:/')],service.tasks.create('test',[]))
    assert not (service.coding.files_directory(workspace)/'src').exists()


def test_import_is_project_relative_and_cannot_read_host(service):
    workspace=service.coding.create('Owned import test')['workspace_id']
    tools=ApplicationTools(service,workspace)
    with pytest.raises(WorkbenchError):tools.registry.execute('document_import',{'target':'../secret.txt'})
    service.coding.write(workspace,'notes.txt','Private project note')
    result=tools.registry.execute('document_import',{'target':'notes.txt'})
    assert result['status']=='indexed'


def test_automations_persist_capture_scope_and_do_not_queue_overdue_runs(service,monkeypatch):
    workspace=service.coding.create('Owned automation test')['workspace_id']
    entry=service.automations.create('Check project','Inspect notes.py',60,workspace,[])
    reloaded=Automations(service)
    assert reloaded.list()[0]['id']==entry['id']
    calls=[]
    monkeypatch.setattr(service,'run_auto_agent',lambda goal,**kwargs:calls.append((goal,kwargs)) or
        {'status':'completed','task_id':'audit','answer':'Done'})
    reloaded.run_due(entry['next_run']+600)
    reloaded.run_due(entry['next_run']+600)
    assert len(calls)==1
    assert calls[0][1]['document_ids']==[] and calls[0][1]['history']==[]
    assert reloaded.list()[0]['last_result']['task_id']=='audit'
    reloaded.change(entry['id'],paused=True)
    assert reloaded.list()[0]['paused']
    reloaded.change(entry['id'],delete=True)
    assert reloaded.list()==[]


def test_automation_requires_interval_and_busy_does_not_run(service,monkeypatch):
    with pytest.raises(WorkbenchError):service.automations.create('Unsafe','Run task',10)
    entry=service.automations.create('Check','Inspect project',60)
    monkeypatch.setattr(service,'run_auto_agent',lambda *_:pytest.fail('Busy tasks must not overlap'))
    service.ask_lock.acquire()
    try:service.automations.run_due(entry['next_run']+1)
    finally:service.ask_lock.release()
    assert service.automations.list()[0]['last_run'] is None


def test_automation_api_create_pause_delete_and_bounds(service):
    from tests.test_api import client_for
    with client_for(service) as client:
        bad=client.post('/automations',json={'name':'Too fast','goal':'Inspect project','interval_seconds':1})
        assert bad.status_code==422
        created=client.post('/automations',json={'name':'Owned API automation','goal':'Inspect project','interval_seconds':600})
        assert created.status_code==200
        identifier=created.json()['id']
        assert client.get('/automations').json()[0]['document_ids']==[]
        assert client.patch('/automations/'+identifier,json={'paused':True}).json()['paused']
        assert client.delete('/automations/'+identifier).json()['deleted']
        assert client.get('/automations').json()==[]


def test_application_plan_grammar_preserves_json_string_quotes(monkeypatch):
    from backend.model import LocalModel
    import json
    model=LocalModel('http://127.0.0.1:8087')
    generated=[]
    def request(method,path,**kwargs):
        if path=='/props':return {'default_generation_settings':{'n_ctx':24576}}
        generated.append(kwargs['json'])
        return {'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'operations':[op('file_run','main.py',input='2\n3')]})}}]}
    monkeypatch.setattr(model,'_request',request)
    monkeypatch.setattr(model,'count_messages',lambda *_:1000)
    result=model.plan_application_tools('Run main.py with 2 and 3',[],[{'name':'main.py'}])
    assert result==[op('file_run','main.py',input='2\n3')]
    assert json.dumps(json.dumps('file_run')) in generated[0]['grammar']
    assert generated[0]['max_tokens']==1024
    assert generated[0]['chat_template_kwargs']=={'enable_thinking':False}


def test_current_run_after_creation_dispatches_execution_without_any_edit(service,monkeypatch):
    workspace=service.coding.create('Owned execution followup')['workspace_id']
    service.coding.write(workspace,'division.py','print(float(input()) / float(input()))')
    history=['User: Create division.py','Assistant: Created division.py']
    service.model.plan_task=lambda *_:{'action':'application_tools','response':'','target':'','expression':''}
    service.model.plan_application_tools=lambda *_,**__:[op('file_run','division.py',input='12\n3')]
    monkeypatch.setattr(service,'run_coding_project_task',lambda *_ ,**__:pytest.fail('Running must not create or edit a file'))
    seen=[]
    monkeypatch.setattr(service,'execute_coding_file',lambda identifier,target,job:seen.append((identifier,target,job.input.get_nowait())) or
        {'state':'completed','exit_code':0,'stdout':'4.0\n'})
    result=service.run_auto_agent('Run division.py and provide 12 then 3 as its input.',[],workspace,history)
    assert result['status']=='completed'
    assert seen==[(workspace,'division.py','12\n3\n')]
    assert '4.0' in result['answer']


def test_execution_classifier_prompt_reasserts_current_request_after_history(monkeypatch):
    from backend.model import LocalModel
    import json
    model=LocalModel('http://127.0.0.1:8087')
    payloads=[]
    def request(method,path,**kwargs):
        if path=='/props':return {'default_generation_settings':{'n_ctx':24576}}
        payloads.append(kwargs['json'])
        return {'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'action':'application_tools','response':''})}}]}
    monkeypatch.setattr(model,'_request',request)
    monkeypatch.setattr(model,'count_messages',lambda *_:1000)
    goal='Run division.py and provide 12 then 3 as its input.'
    result=model.plan_task(goal,[],[{'name':'division.py'}],['User: Create division.py','Assistant: Created division.py'])
    assert result['action']=='application_tools'
    assert json.loads(payloads[0]['messages'][-1]['content'])['request']==goal
    assert payloads[0]['chat_template_kwargs']=={'enable_thinking':False}
    assert 'never edit_code' in payloads[0]['messages'][0]['content']
    assert 'Change division.py to accept user input => edit_code' in payloads[0]['messages'][0]['content']


def test_create_knowledge_literal_text_needs_no_reference_connection(service,monkeypatch):
    service.model.plan_task=lambda *_:{'action':'application_tools','response':'','target':'','expression':''}
    service.model.plan_application_tools=lambda *_,**__:[op('document_create','acceptance.txt','Application tools acceptance.')]
    monkeypatch.setattr(service,'create_document_report',lambda *_,**__:pytest.fail('Literal library creation must not export a grounded report'))
    result=service.run_auto_agent('Create Knowledge acceptance.txt containing exactly: Application tools acceptance.',[])
    assert result['status']=='completed'
    assert (service.sources_dir/'acceptance.txt').read_text(encoding='utf-8')=='Application tools acceptance.'
    assert service.documents()[0]['display_name']=='acceptance.txt'


def test_classifier_examples_separate_compound_execution_and_literal_library_creation(monkeypatch):
    from backend.model import LocalModel
    import json
    model=LocalModel('http://127.0.0.1:8087');generated=[]
    def request(method,path,**kwargs):
        if path=='/props':return {'default_generation_settings':{'n_ctx':24576}}
        generated.append(kwargs['json'])
        return {'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'action':'application_tools','response':''})}}]}
    monkeypatch.setattr(model,'_request',request);monkeypatch.setattr(model,'count_messages',lambda *_:1000)
    goal='Create a new Knowledge document named my_notes.txt containing exactly: My note.'
    model.plan_task(goal,[],[])
    messages=generated[0]['messages']
    assert json.loads(messages[-1]['content'])['request']==goal
    samples=[(messages[index]['content'],json.loads(messages[index+1]['content'])) for index in range(1,len(messages)-1,2)]
    assert samples[0][1]['action']=='application_tools' and 'then run it' in samples[0][0]
    assert samples[1][1]['action']=='application_tools' and 'containing exactly' in samples[1][0]
    assert samples[2][1]['action']=='edit_code'


def test_file_edit_uses_original_request_not_planner_generated_escaped_code(service,monkeypatch):
    workspace=service.coding.create('Owned authored instruction test')['workspace_id']
    goal='Create multiplication.py with multiply(a,b), then run it to print multiply(6,7).'
    escaped_code='def multiply(a,b):\\n    return a * b\\nprint(multiply(6,7))'
    calls=[]
    monkeypatch.setattr(service,'run_coding_project_task',lambda identifier,target,instruction,**kwargs:
        calls.append((identifier,target,instruction)) or {'state':'completed'})
    tools=ApplicationTools(service,workspace,goal=goal)
    tools.execute([op('file_edit','multiplication.py',escaped_code)],service.tasks.create('test',[]))
    assert calls[0][0:2]==(workspace,'multiplication.py')
    assert calls[0][2].startswith(goal)
    assert escaped_code not in calls[0][2]
    assert calls[0][2] == goal


def test_application_file_edit_preserves_near_limit_goal_without_appending(service,monkeypatch):
    workspace=service.coding.create('Bounded operation goal')['workspace_id']
    prefix='Create hello.py as an input echo program then run with hello. '
    goal=prefix+'x'*(1000-len(prefix))
    received=[]
    def edit(identifier,target,instruction,**kwargs):
        assert len(instruction)==1000
        assert instruction==goal
        assert target=='hello.py'
        received.append(instruction)
        return {'state':'completed'}
    monkeypatch.setattr(service,'run_coding_project_task',edit)
    result=ApplicationTools(service,workspace,goal=goal).execute(
        [op('file_edit','hello.py','Model-supplied text must not replace the request')],service.tasks.create('test',[]))
    assert result['state']=='completed' and received==[goal]


def test_document_update_retains_identity_and_original_snapshot(service):
    source=service.sources_dir/'nature.txt';source.write_text('Nature includes life.',encoding='utf-8')
    first=service.import_file(source)
    task=service.tasks.create('test',[])
    result=ApplicationTools(service,goal='Make the doc more detailed about Earth nature').execute(
        [op('document_update','nature.txt','Nature on Earth includes ecosystems, oceans and forests.')],task)
    assert result['state']=='completed'
    docs=service.documents()
    assert len(docs)==1 and docs[0]['document_id']==first['document_id']
    assert docs[0]['active_hash']!=first['active_hash']
    assert (service.sources_dir/(first['active_hash']+'.txt')).read_text()=='Nature includes life.'
    assert source.read_text()=='Nature includes life.'


def test_chat_application_plan_remains_inline_without_mutation(service):
    service.model.plan_task=lambda *_:{'action':'application_tools','target':'','response':''}
    service.model.conversation_answer=lambda *_:'Nature includes forests and oceans.'
    result=service.ask('Create a txt file explaining nature',[])
    assert result['status']=='conversation' and 'Nature' in result['answer']
    assert service.documents()==[]


def test_document_update_accepts_details_followup(service):
    from router.tool_registry import explicit_operation_requested
    assert explicit_operation_requested('so can u add details to it', 'document_update')
    source=service.sources_dir/'nature.txt';source.write_text('Nature includes life.',encoding='utf-8')
    service.import_file(source)
    result=ApplicationTools(service,goal='so can u add details to it').execute(
        [op('document_update','nature.txt','Nature includes land, water, atmosphere and life.')],
        service.tasks.create('test',[]))
    assert result['state']=='completed'


def test_agent_followup_passes_history_to_document_planner(service):
    source=service.sources_dir/'nature_explanation.txt'
    source.write_text('Nature includes life.',encoding='utf-8')
    service.import_file(source)
    history=['User: create nature_explanation.txt in Knowledge',
             'Assistant: Completed: document create nature_explanation.txt.']
    seen=[]
    service.model.plan_task=lambda *args:{'action':'application_tools','response':'','target':''}
    service.model.plan_application_tools=lambda goal,documents,files,recent,**kwargs: (
        seen.append((goal,documents,recent)) or [op('document_update','nature_explanation.txt')])
    service.model.document_text=lambda instruction,current,filename:current+' More detail.'
    result=service.run_auto_agent('add more details to it',history=history)
    assert result['status']=='completed'
    assert seen[0][0]=='add more details to it'
    assert seen[0][2]==history
    assert seen[0][1][0]['name']=='nature_explanation.txt'


def test_typo_create_intent_and_duplicate_generated_knowledge_name(service):
    from router.tool_registry import explicit_operation_requested
    assert explicit_operation_requested('CAN U crate a doc explaining about nature','document_create')
    source=service.sources_dir/'nature_explanation.txt';source.write_text('Old nature text.',encoding='utf-8')
    service.import_file(source)
    service.model.document_text=lambda instruction,current,filename:'Nature on Earth includes ecosystems, forests and oceans.'
    result=ApplicationTools(service,goal='can u create a file in knowledge explaining about nature').execute(
        [op('document_create','nature_explanation.txt','A short placeholder.')],service.tasks.create('test',[]))
    assert result['state']=='completed'
    assert 'nature_explanation_2.txt' in result['answer']
    names={doc['display_name'] for doc in service.documents()}
    assert names=={'nature_explanation.txt','nature_explanation_2.txt'}
    assert source.read_text()=='Old nature text.'


def test_explicit_knowledge_filename_collision_asks_for_new_name(service):
    source=service.sources_dir/'nature.txt';source.write_text('Original.',encoding='utf-8')
    service.import_file(source)
    with pytest.raises(WorkbenchError,match='already exists'):
        ApplicationTools(service,goal='Create nature.txt in Knowledge').execute(
            [op('document_create','nature.txt','New text.')],service.tasks.create('test',[]))
    assert source.read_text(encoding='utf-8')=='Original.'


def test_document_detail_expansion_keeps_current_text_and_uses_short_generation():
    from backend.model import LocalModel
    model=LocalModel()
    calls=[]
    def complete(messages,max_tokens=1536):
        calls.append((messages,max_tokens))
        return {'code':'Additional details about forests and oceans.'}
    model.complete_code=complete
    result=model.document_text('so can u add more details to it','Existing explanation.','nature.txt')
    assert result.startswith('Existing explanation.')
    assert result.strip().endswith('Additional details about forests and oceans.')
    assert calls[0][1] <= 768
