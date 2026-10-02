from tests.test_service import service
from types import SimpleNamespace
import pytest
from router.tool_registry import explicit_operation_requested


@pytest.mark.parametrize('prompt',['Rename this variable','Refactor this function','Debug main.py','Restore the layout in index.html'])
def test_explicit_code_operations_remain_separate_from_classifier(prompt):
    assert explicit_operation_requested(prompt,'file_edit')
    assert not explicit_operation_requested('Explain how to '+prompt,'file_edit')
    assert not explicit_operation_requested('Do not '+prompt,'file_edit')


def test_clear_selected_code_edit_needs_no_semantic_intent_call(service,monkeypatch):
    leases=[]
    monkeypatch.setattr(service,'_lease',lambda capability,**kwargs:leases.append(kwargs.get('worker_role')) or capability)
    monkeypatch.setattr(service.model,'plan_task',lambda *args:(_ for _ in ()).throw(AssertionError('Unexpected intent inference')))
    plan=service._request_plan('Fix the syntax error in main.py',[],[{'name':'main.py'}])
    assert plan['action']=='edit_code' and plan['target']=='main.py'
    assert leases==['code']


def test_selected_function_explanation_needs_no_semantic_intent_call(service,monkeypatch):
    leases=[]
    monkeypatch.setattr(service,'_lease',lambda capability,**kwargs:leases.append(kwargs.get('worker_role')) or capability)
    monkeypatch.setattr(service.model,'plan_task',lambda *args:(_ for _ in ()).throw(AssertionError('Unexpected intent inference')))
    plan=service._request_plan('Explain this function',[],[{'name':'main.py'}])
    assert plan['action']=='inspect_code'
    assert leases==['lightweight']


def test_direct_code_panel_skips_intent_inference(service,monkeypatch):
    monkeypatch.setattr(service.model,'plan_task',lambda *args:(_ for _ in ()).throw(AssertionError('Unexpected intent inference')))
    monkeypatch.setattr(service,'_verified_coding_sandbox',lambda:SimpleNamespace(_ready=lambda:None))
    monkeypatch.setattr(service.coding,'run_project',lambda *args,**kwargs:{'state':'completed','publication_state':'staged'})
    result=service.run_coding_project_task('selected','main.py','Fix the syntax error in main.py')
    assert result['publication_state']=='staged'


@pytest.mark.parametrize('routed',[False,True])
def test_complex_strategy_is_persisted_before_coder_handoff(service,monkeypatch,routed):
    from backend.task_supervisor import CURRENT_SUPERVISOR
    order=[]
    monkeypatch.setattr(service,'_verified_coding_sandbox',lambda:SimpleNamespace(_ready=lambda:None))
    def lease(capability,**kwargs):
        role=kwargs['worker_role']
        if role=='code':assert CURRENT_SUPERVISOR.get().task_state['plan']['strategy']=='Use bounded module interfaces.'
        order.append(role)
        return capability
    monkeypatch.setattr(service,'_lease',lease)
    monkeypatch.setattr(service.model,'plan_code_strategy',lambda *args:'Use bounded module interfaces.',raising=False)
    monkeypatch.setattr(service.model,'plan_task',lambda *args:pytest.fail('Upfront code strategy resolves clear intent already'))
    monkeypatch.setattr(service.model,'replan_code',lambda *args:pytest.fail('Initial planning is not an observed failed validation'),raising=False)
    monkeypatch.setattr(service.coding,'get',lambda *_:{'files':[]})
    monkeypatch.setattr(service.coding,'run_project',lambda *args,**kwargs:{'state':'completed','publication_state':'staged'})
    service.run_coding_project_task('selected','main.py','Refactor architecture across the project',routed=routed)
    assert order==['reasoning','code']


def test_clear_complex_agent_request_defers_acquisition_to_bounded_strategy(service,monkeypatch):
    monkeypatch.setattr(service,'_lease',lambda *args,**kwargs:pytest.fail('Do not acquire Coder before complex strategy'))
    monkeypatch.setattr(service.model,'plan_task',lambda *args:pytest.fail('Clear code intent does not need another semantic plan'))
    plan=service._request_plan('Refactor authentication across the project',[],[{'name':'auth.py'},{'name':'app.py'}])
    assert plan['action']=='edit_code'

def test_mixed_explanation_and_edit_preserves_requested_edit(service,monkeypatch):
    monkeypatch.setattr(service,'_lease',lambda capability,**kwargs:capability)
    monkeypatch.setattr(service.model,'plan_task',lambda *args:pytest.fail('Clear mixed edit needs no semantic intent call'))
    plan=service._request_plan('Explain app.py and then fix the bug',[],[{'name':'app.py'}])
    assert plan['action']=='edit_code'

def test_multifile_execution_keeps_complex_context_and_strategy(service,monkeypatch):
    from backend.task_supervisor import CURRENT_SUPERVISOR
    order=[]
    monkeypatch.setattr(service,'_verified_coding_sandbox',lambda:SimpleNamespace(_ready=lambda:None))
    monkeypatch.setattr(service.coding,'get',lambda *_:{'files':[{'name':'app.py'},{'name':'utils.py'}]})
    monkeypatch.setattr(service.model,'plan_code_strategy',lambda *args:'Share the helper across both files.',raising=False)
    def lease(capability,**kwargs):
        role=kwargs['worker_role'];order.append(role)
        if role=='code':assert CURRENT_SUPERVISOR.get().task_state['plan']['strategy']=='Share the helper across both files.'
        return capability
    monkeypatch.setattr(service,'_lease',lease)
    monkeypatch.setattr(service.coding,'run_project',lambda *args,**kwargs:{'state':'completed','publication_state':'staged'})
    result=service.run_coding_project_task('selected','app.py','Update app.py and utils.py to share the helper',routed=True)
    assert order==['reasoning','code']
    assert result['routing']['decision']['task_type']=='MULTI_FILE_CHANGE'


def test_image_observation_persisted_before_coder(service, monkeypatch, tmp_path):
    from PIL import Image
    from backend.task_supervisor import CURRENT_SUPERVISOR
    image=tmp_path/'ui.png'
    Image.new('RGB',(2,2)).save(image)
    order=[]
    monkeypatch.setattr(service,'_verified_coding_sandbox',lambda:SimpleNamespace(_ready=lambda:order.append('sandbox')))
    def lease(capability,**kwargs):
        role=kwargs['worker_role']
        if role=='code':
            assert CURRENT_SUPERVISOR.get().task_state['observations'][-1]['answer']=='Button overlaps heading.'
        order.append(role)
        return capability
    monkeypatch.setattr(service,'_lease',lease)
    monkeypatch.setattr('backend.service.ask_vision',lambda image,question:{'answer':'Button overlaps heading.'})
    monkeypatch.setattr(service.model,'plan_task',lambda *args:pytest.fail('Visual code needs no semantic intent call'))
    def run(*args,**kwargs):
        assert 'Button overlaps heading.' in kwargs['history'][-1]
        return {'state':'completed','publication_state':'staged'}
    monkeypatch.setattr(service.coding,'run_project',run)
    result=service.run_coding_project_task('selected','app.py','Fix the UI problem shown in the screenshot',image_path=image)
    assert order[:3]==['sandbox','vision','code']
    assert result['routing']['decision']['task_type']=='VISION_ASSISTED_CODE'


def test_image_code_unavailable_sandbox_stops_before_vision(service, monkeypatch):
    from backend.contracts import WorkbenchError
    def unavailable():raise WorkbenchError('sandbox_unavailable','Validation unavailable')
    monkeypatch.setattr(service,'_verified_coding_sandbox',unavailable)
    monkeypatch.setattr(service,'_lease',lambda *args,**kwargs:pytest.fail('No model before sandbox'))
    with pytest.raises(WorkbenchError):
        service.run_coding_project_task('selected','app.py','Fix the UI problem',image_path='missing.png')


def test_image_cannot_authorize_code_edit(service, monkeypatch):
    monkeypatch.setattr(service,'_lease',lambda *args,**kwargs:pytest.fail('No image worker without edit authority'))
    from backend.contracts import WorkbenchError
    with pytest.raises(WorkbenchError):
        service.run_coding_project_task('selected','app.py','Describe this screenshot',image_path='missing.png')


@pytest.mark.parametrize('request_text',[
    'Can you explain how to restore index.html?',
    'Could you please describe how to fix index.html?',
    'How can I restore index.html?',
    'How do we modify index.html?',
    'How to repair index.html?',
    'Please explain how to restore index.html.',
    'How can you fix index.html?',
])
def test_interrogative_explanation_does_not_authorize_visual_mutation(service, monkeypatch, request_text):
    from backend.contracts import WorkbenchError
    from router.tool_registry import explicit_operation_requested
    from router.coding_router import classify_coding_request
    assert not explicit_operation_requested(request_text,'file_edit')
    assert classify_coding_request(request_text,{'visual_input_present':True}).steps==('vision',)
    monkeypatch.setattr(service,'_lease',lambda *args,**kwargs:pytest.fail('Read-only question cannot acquire a writing worker'))
    monkeypatch.setattr(service,'_verified_coding_sandbox',lambda:pytest.fail('Read-only question cannot enter writing workflow'))
    with pytest.raises(WorkbenchError):
        service.run_coding_project_task('selected','index.html',request_text,image_path='missing.png')


@pytest.mark.parametrize('request_text',[
    'Can you restore index.html?',
    'Could you please fix index.html?',
    'Can you explain index.html and then restore its layout?',
    'Describe index.html then modify its layout.',
])
def test_explicit_interrogative_or_separate_edit_remains_authorized(request_text):
    from router.tool_registry import explicit_operation_requested
    assert explicit_operation_requested(request_text,'file_edit')
