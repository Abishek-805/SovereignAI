"""Context selection is read permission; Chat code is text, Agent code is a file."""
import pytest
from backend.contracts import WorkbenchError
from tests.test_service import service
from backend.model import LocalModel


@pytest.mark.parametrize('action', ['search_documents', 'create_report'])
def test_disconnected_agent_never_broadens_to_library(service, monkeypatch, action):
    service.model.plan_task=lambda *_: {'action':action,'response':'','target':'','expression':''}
    monkeypatch.setattr(service,'documents',lambda:pytest.fail('Disconnected library must not be opened'))
    monkeypatch.setattr(service.store,'active_chunks',lambda *_:pytest.fail('Disconnected evidence must not be read'))
    with pytest.raises(WorkbenchError) as error:
        service.run_auto_agent('Question about a document',[])
    assert error.value.code=='needs_input'
    assert not service.ask_lock.locked()


def test_chat_code_is_inline_without_any_project_or_document_reads(service, monkeypatch):
    service.model.plan_task=lambda *_: {'action':'edit_code','response':'','target':'division.py','expression':''}
    calls=[]
    service.model.inline_code_answer=lambda *args: calls.append(args) or {'answer':'```python\nprint(8 / 2)\n```'}
    monkeypatch.setattr(service.coding,'get',lambda *_:pytest.fail('Chat cannot open a project'))
    monkeypatch.setattr(service.store,'active_chunks',lambda *_:pytest.fail('Code is unrelated to evidence'))
    result=service.ask('Create division code',[],history=['User: Summarize my report'])
    assert result['status']=='conversation' and result['sources']==[]
    assert result['answer'].startswith('```python')
    assert calls[0][2]=='division.py'


def test_chat_web_pair_returns_two_inline_files_without_project_writes(service, monkeypatch):
    service.model.plan_task=lambda *_: {'action':'application_tools','response':'','target':'','expression':''}
    calls=[]
    service.model.inline_code_answer=lambda *args: calls.append(args) or {
        'answer':'**index.html**\n```html\n<html></html>\n```\n\n**style.css**\n```css\nbody{}\n```'}
    monkeypatch.setattr(service.coding,'get',lambda *_:pytest.fail('Chat cannot open a project'))
    result=service.ask('generate html and css file for simple html web page',[])
    assert result['status']=='conversation'
    assert '**index.html**' in result['answer'] and '**style.css**' in result['answer']
    assert len(calls)==1


def test_inline_web_pair_calls_model_for_each_file(monkeypatch):
    model=LocalModel('http://127.0.0.1:8087')
    replies=iter(['<html><head></head><body>Hello</body></html>', 'body { color: teal; }'])
    prompts=[]
    monkeypatch.setattr(model,'complete_code',lambda messages,max_tokens=2048: (
        prompts.append(messages) or {'code':next(replies)}))
    result=model.inline_code_answer('generate html and css file for simple html web page')
    assert len(prompts)==2
    assert 'href="style.css"' in result['answer']
    assert '```html' in result['answer'] and '```css' in result['answer']


def test_agent_moves_recent_generated_web_files_into_folder(service):
    workspace=service.coding.create('Web files')['workspace_id']
    service.coding.write(workspace,'index.html','<html>Existing</html>')
    service.coding.write(workspace,'style.css','body { color: teal; }')
    service.model.plan_task=lambda *_:{'action':'answer','response':'Cannot move files','target':''}
    result=service.run_auto_agent('put those files in a folder',[],workspace,
        history=['User: generate html and css files',
                 'Assistant: Saved index.html, style.css in the project. Docker validation was not run.'])
    assert result['status']=='completed'
    assert {item['name'] for item in service.coding.get(workspace)['files']}=={
        'web-page/index.html','web-page/style.css'}


def test_agent_moves_only_unambiguous_web_files_from_ide(service):
    workspace=service.coding.create('IDE web files')['workspace_id']
    service.coding.write(workspace,'index.html','<html>Existing</html>')
    service.coding.write(workspace,'style.css','body { color: teal; }')
    service.coding.write(workspace,'notes.py','print("keep")')
    service.model.plan_task=lambda *_:{'action':'answer','response':'No','target':''}
    result=service.run_auto_agent('put the files related to web in a single folder',[],workspace)
    assert result['status']=='completed'
    assert {item['name'] for item in service.coding.get(workspace)['files']}=={
        'web-page/index.html','web-page/style.css','notes.py'}


def test_agent_can_create_arithmetic_folder_without_filename_clarification(service,monkeypatch):
    workspace=service.coding.create('Math files')['workspace_id']
    service.coding.write(workspace,'first.py','pass')
    service.coding.write(workspace,'second.py','pass')
    service.model.plan_task=lambda *_:{'action':'answer','response':'No','target':''}
    calls=[]
    monkeypatch.setattr(service,'run_coding_project_task',lambda *args,**kwargs:
        calls.append(args) or {'state':'completed','changes':[{'action':'create','path':'arithmetic/operations.py'}],
            'checks':{'container_executed':False}})
    result=service.run_auto_agent('can u generate folder containg a code that does simple arithmetic operations',[],workspace)
    assert result['status']=='completed'
    assert calls[0][:2]==(workspace,'')


def test_agent_creates_code_in_empty_project_and_does_not_prefetch_sources(service, monkeypatch):
    service.model.plan_task=lambda *_: {'action':'edit_code','response':'','target':'division.py','expression':''}
    monkeypatch.setattr(service.coding,'get',lambda *_: {'files':[]})
    monkeypatch.setattr(service.coding,'read',lambda *_:pytest.fail('No speculative source reads'))
    monkeypatch.setattr(service,'_verified_coding_sandbox',lambda:None)
    calls=[]
    monkeypatch.setattr(service,'run_coding_project_task',lambda *args,**kwargs:
        calls.append((args,kwargs)) or {'target':'division.py','state':'completed'})
    result=service.run_auto_agent('Create division code',[],workspace_id='empty-project')
    assert result['workspace_id']=='empty-project'
    assert calls[0][0]==('empty-project','division.py','Create division code')
    assert calls[0][1]['routed'] is True
