import pytest
from router.request_normalization import normalize_request
from router.tool_registry import explicit_operation_requested
from router.coding_router import classify_coding_request
from tests.test_service import service


@pytest.mark.parametrize('verb,expected', [('Implment','Implement'),('generte','generate'),('refacor','refactor'),('renmae','rename')])
def test_single_edit_command_spelling_preserves_exact_target(verb,expected):
    request=f'{verb} literal_identifier in src/Implment_24.py'
    normalized=normalize_request(request)
    assert normalized.original==request
    assert normalized.normalized==f'{expected} literal_identifier in src/Implment_24.py'
    assert explicit_operation_requested(request,'file_edit')
    assert classify_coding_request(request,{'active_file':'src/Implment_24.py'}).task_type!='CLARIFICATION'


@pytest.mark.parametrize('user_text',[
    'Explain how to implment a function', 'Do not implment a function',
    'The documentation says "implment solution.py"',
    '`implment` is an identifier', 'This function implments a transformation',
    'def implment():\n    return 1', 'https://example.com/implment',
    'Refractor is an optical instrument',
])
def test_spelling_does_not_promote_reference_or_negative_text_to_command(user_text):
    assert normalize_request(user_text).normalized==user_text
    assert not explicit_operation_requested(user_text,'file_edit')


def test_interpretation_receives_selected_workspace_and_bounded_history(service,monkeypatch):
    wid=service.coding.create('Interpretation context')['workspace_id']
    service.coding.write(wid,'selected.py','x=1\n')
    service.coding.write(wid,'other.py','x=2\n')
    captured=[]
    def interpret(goal,documents,files,history):
        captured.append((goal,documents,files,history))
        return {'action':'answer','response':'Please specify a change.'}
    monkeypatch.setattr(service.model,'plan_task',interpret)
    history=['user: earlier scoped question','assistant: previous reply']
    result=service.run_coding_project_task(wid,'selected.py','What next?',history=history)
    assert result['state']=='answered'
    assert captured[0][2][0]['name']=='selected.py'
    assert captured[0][2][0]['active_file'] is True
    assert {item['name'] for item in captured[0][2]}=={'selected.py','other.py'}
    assert captured[0][3]==history
    assert service.coding.read(wid,'selected.py')['content']=='x=1\n'


def test_reference_history_is_bounded_and_marked_incomplete(service,monkeypatch):
    captured=[]
    monkeypatch.setattr(service.model,'plan_task',lambda goal,docs,files,history:
        captured.append(history) or {'action':'answer','response':'Clarify.'})
    wid=service.coding.create('Bounded context')['workspace_id']
    service.run_coding_project_task(wid,'','What next?',history=['x'*8000]*20)
    assert len(captured[0])==6
    assert all(len(entry)<2100 and 'excerpt' in entry for entry in captured[0])
