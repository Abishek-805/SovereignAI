import json
import httpx
import pytest
from backend.contracts import WorkbenchError
from backend.model import LocalModel

def test_remote_endpoint_rejected():
    with pytest.raises(ValueError): LocalModel('https://example.com')

def test_loading_is_distinct_from_offline():
    model=LocalModel(transport=httpx.MockTransport(lambda request:httpx.Response(503,json={'error':{'message':'Loading model'}})))
    with pytest.raises(WorkbenchError) as error: model.status()
    assert error.value.code=='model_loading'

def test_status_and_count():
    requests=[]
    def handler(request):
        requests.append(request.url.path)
        if request.url.path=='/props': return httpx.Response(200,json={'is_sleeping':True})
        if request.url.path=='/apply-template': return httpx.Response(200,json={'prompt':'formatted'})
        return httpx.Response(200,json={'tokens':[1,2,3]})
    model=LocalModel(transport=httpx.MockTransport(handler))
    assert model.status()['is_sleeping'] is True
    assert model.count_messages([{'role':'user','content':'hi'}])==3
    assert requests==['/props','/apply-template','/tokenize']

def test_count_includes_completion_tools_and_template_options():
    sent=[]
    def handler(request):
        sent.append(json.loads(request.content))
        if request.url.path=='/apply-template':return httpx.Response(200,json={'prompt':'rendered tools and messages'})
        return httpx.Response(200,json={'tokens':[1,2,3,4]})
    payload={'messages':[{'role':'user','content':'Inspect'}],
             'tools':[{'type':'function','function':{'name':'inspect','parameters':{'type':'object'}}}],
             'tool_choice':'auto','chat_template_kwargs':{'enable_thinking':False},'max_tokens':10}
    model=LocalModel(transport=httpx.MockTransport(handler))
    try:assert model.count_messages(payload['messages'],payload)==4
    finally:model.close()
    assert sent[0]==payload
    assert sent[1]['content']=='rendered tools and messages'

@pytest.mark.parametrize('exception,code',[(httpx.ConnectError,'model_unavailable'),(httpx.ReadTimeout,'model_timeout')])
def test_connection_errors(exception,code):
    def handler(request): raise exception('fail',request=request)
    with pytest.raises(WorkbenchError) as error: LocalModel(transport=httpx.MockTransport(handler)).status()
    assert error.value.code==code

def test_truncated_output_rejected():
    def handler(request): return httpx.Response(200,json={'choices':[{'finish_reason':'length','message':{'content':'{}'}}]})
    with pytest.raises(WorkbenchError) as error: LocalModel(transport=httpx.MockTransport(handler)).complete([])
    assert error.value.code=='generation_format'


def test_structured_code_generation():
    seen=[]
    def handler(request):
        if request.url.path == '/props':
            return httpx.Response(200,json={'default_generation_settings':{'n_ctx':4096}})
        if request.url.path == '/apply-template':
            return httpx.Response(200,json={'prompt':'formatted'})
        if request.url.path == '/tokenize':
            return httpx.Response(200,json={'tokens':[1,2,3]})
        seen.append(json.loads(request.content))
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop',
            'message':{'content':json.dumps({'code':'print(1)'})}}], 'usage':{'completion_tokens':8}})
    model=LocalModel(transport=httpx.MockTransport(handler))
    assert model.complete_code([{'role':'user','content':'write code'}])['code']=='print(1)'
    from backend.model import CODE_GRAMMAR
    assert seen[0]['grammar']==CODE_GRAMMAR
    assert seen[0]['chat_template_kwargs']=={'enable_thinking':False}
    assert 'response_format' not in seen[0]
    assert CODE_GRAMMAR.splitlines()[0].startswith('root ::= "{"')


def test_code_context_overflow_rejected_before_generation():
    def handler(request):
        if request.url.path == '/props':
            return httpx.Response(200,json={'default_generation_settings':{'n_ctx':4096}})
        if request.url.path == '/apply-template':
            return httpx.Response(200,json={'prompt':'formatted'})
        if request.url.path == '/tokenize':
            return httpx.Response(200,json={'tokens':[1] * 3500})
        pytest.fail('Overflow must not reach generation')
    with pytest.raises(WorkbenchError) as error:
        LocalModel(transport=httpx.MockTransport(handler)).complete_code([],max_tokens=1024)
    assert error.value.code == 'context_budget'


def test_structured_plan_rejects_unlisted_workflow():
    def reply(workflow):
        return httpx.MockTransport(lambda request:httpx.Response(200,json={'choices':[{
            'finish_reason':'stop','message':{'content':json.dumps({'workflow':workflow,'reason':'test'})}}]}))
    assert LocalModel(transport=reply('maintenance_draft')).complete_plan([])['workflow']=='maintenance_draft'
    with pytest.raises(WorkbenchError) as error:
        LocalModel(transport=reply('run_shell')).complete_plan([])
    assert error.value.code=='generation_format'

@pytest.mark.parametrize('short_answer', ['Hello! What would you like to work on?', ''])
def test_task_plan_short_answer_or_budgeted_conversation(short_answer):
    generated=[]
    def handler(request):
        if request.url.path=='/props':
            return httpx.Response(200,json={'default_generation_settings':{'n_ctx':4096}})
        if request.url.path=='/apply-template': return httpx.Response(200,json={'prompt':'formatted'})
        if request.url.path=='/tokenize': return httpx.Response(200,json={'tokens':[1]*200})
        payload=json.loads(request.content); generated.append(payload)
        content=json.dumps({'action':'answer','target':'','expression':'','response':short_answer}) if len(generated)==1 else 'A detailed model-generated explanation.'
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':content}}]})
    model=LocalModel(transport=httpx.MockTransport(handler))
    result=model.plan_task('Explain the concept',[],[],['Earlier question','Earlier answer'])
    assert result['response']==(short_answer or 'A detailed model-generated explanation.')
    assert len(generated)==(1 if short_answer else 2)
    if not short_answer:
        assert generated[-1]['max_tokens']==2048
        assert 'response_format' not in generated[-1]
        assert 'Earlier question' in generated[-1]['messages'][-1]['content']


def test_cancelled_plan_never_starts_deferred_conversation_generation():
    from threading import Event
    cancelled=Event();generations=[]
    def handler(request):
        if request.url.path=='/props': return httpx.Response(200,json={'default_generation_settings':{'n_ctx':4096}})
        if request.url.path=='/apply-template': return httpx.Response(200,json={'prompt':'formatted'})
        if request.url.path=='/tokenize': return httpx.Response(200,json={'tokens':[1]})
        generations.append(request.url.path);cancelled.set()
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'action':'answer','target':'','expression':'','response':'','document_scope':'focused'})}}]})
    model=LocalModel(transport=httpx.MockTransport(handler))
    with model.cancel_scope(cancelled),pytest.raises(WorkbenchError) as error:
        model.plan_task('Explain this in detail',[],[])
    assert error.value.code=='cancelled'
    assert len(generations)==1
    # Context must be restored after this job so another request is unaffected.
    assert model.status()['available'] is True


def test_image_metadata_is_available_to_intent_planner_without_image_pixels():
    seen=[]
    def handler(request):
        if request.url.path=='/props': return httpx.Response(200,json={'default_generation_settings':{'n_ctx':4096}})
        if request.url.path=='/apply-template': return httpx.Response(200,json={'prompt':'formatted'})
        if request.url.path=='/tokenize': return httpx.Response(200,json={'tokens':[1]})
        payload=json.loads(request.content);seen.append(payload)
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'action':'analyze_image','target':'','expression':'','response':'Read the attached image','document_scope':'focused'})}}]})
    result=LocalModel(transport=httpx.MockTransport(handler)).plan_task('What is shown?',[],[],images=[{'name':'screenshot.png'}])
    assert result['action']=='analyze_image'
    assert json.loads(seen[0]['messages'][1]['content'])['attached_images']==[{'name':'screenshot.png'}]
    assert 'attachment alone does not turn greetings' in seen[0]['messages'][0]['content']
    assert 'image_url' not in seen[0]['messages'][-1]['content']


@pytest.mark.parametrize('scope,action,valid', [
    ('new_files','create',True), ('new_files','edit',False),
    ('new_files','delete',False), ('existing_files','edit',True),
    ('project','edit',True), ('unknown','create',False)])
def test_workspace_plan_scope_is_validated(scope, action, valid):
    def handler(request):
        if request.url.path == '/props':
            return httpx.Response(200,json={'default_generation_settings':{'n_ctx':4096}})
        if request.url.path == '/apply-template':return httpx.Response(200,json={'prompt':'formatted'})
        if request.url.path == '/tokenize':return httpx.Response(200,json={'tokens':[1,2,3]})
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':json.dumps({
            'scope':scope,'operations':[{'action':action,'path':'requested.js','reason':'User request'}]})}}]})
    model=LocalModel(transport=httpx.MockTransport(handler))
    if valid:
        plan=model.plan_workspace_edit('Create a standalone JavaScript file',{},[],None)
        assert plan['scope']==scope
        assert plan['operations'][0]['action']==action
    else:
        with pytest.raises(WorkbenchError) as error:
            model.plan_workspace_edit('Create a standalone JavaScript file',{},[],None)
        assert error.value.code=='generation_format'


@pytest.mark.parametrize('action,replacements,valid', [
    ('edit',[{'old_text':'Old item','new_text':'Reviewed item'}],True),
    ('edit',[],True), ('create',[{'old_text':'x','new_text':'y'}],False),
    ('edit',[{'old_text':'','new_text':'y'}],False),
    ('edit',[{'old_text':'x','new_text':None}],False),
    ('edit',[{'old_text':'x','new_text':'y','extra':'bad'}],False)])
def test_workspace_literal_replacement_contract(action, replacements, valid):
    def handler(request):
        if request.url.path=='/props':return httpx.Response(200,json={'default_generation_settings':{'n_ctx':4096}})
        if request.url.path=='/apply-template':return httpx.Response(200,json={'prompt':'formatted'})
        if request.url.path=='/tokenize':return httpx.Response(200,json={'tokens':[1,2,3]})
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':json.dumps({
            'scope':'existing_files','operations':[{'action':action,'path':'docs/notes.md','reason':'Named edit','replacements':replacements}]})}}]})
    model=LocalModel(transport=httpx.MockTransport(handler))
    if valid:
        assert model.plan_workspace_edit('Replace Old item with Reviewed item in docs/notes.md',{},[],None)['operations'][0]['replacements']==replacements
    else:
        with pytest.raises(WorkbenchError) as error:model.plan_workspace_edit('Edit notes',{},[],None)
        assert error.value.code=='generation_format'


def test_conversational_plan_uses_compact_schema_without_document_routing_handles():
    generated=[]
    document_id='6f0af1c0fe6e42398ec20bbda5e7ed0e'
    def handler(request):
        if request.url.path=='/props': return httpx.Response(200,json={'default_generation_settings':{'n_ctx':4096}})
        if request.url.path=='/apply-template': return httpx.Response(200,json={'prompt':'formatted'})
        if request.url.path=='/tokenize': return httpx.Response(200,json={'tokens':[1]*200})
        payload=json.loads(request.content);generated.append(payload)
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'action':'answer','response':'I am SovereignAI, your local assistant.'})}}]})
    result=LocalModel(transport=httpx.MockTransport(handler)).plan_task('Tell me your name',[{'document_id':document_id,'name':'Inspection report.pdf'}],[])
    assert result=={'action':'answer','response':'I am SovereignAI, your local assistant.','target':'','expression':'','document_scope':'focused'}
    assert len(generated)==1
    from backend.model import TASK_PLAN_GRAMMAR
    assert generated[0]['grammar']==TASK_PLAN_GRAMMAR
    assert 'response_format' not in generated[0]
    assert 'reasoning_budget_tokens' not in generated[0]
    # No root branch permits a thinking prelude before the JSON object.
    assert TASK_PLAN_GRAMMAR.splitlines()[0].startswith('root ::= "{"')
    assert document_id not in generated[0]['messages'][1]['content']
    assert json.loads(generated[0]['messages'][1]['content'])['documents']==[{'name':'Inspection report.pdf'}]


@pytest.mark.parametrize('tool_plan',[
    {'action':'search_documents','response':''},
    {'action':'create_report','response':'','document_scope':'overview'},
    {'action':'edit_code','response':'','target':'calculator.py'},
    {'action':'calculate','response':'','expression':'7*8'},
])
def test_compact_tool_plan_preserves_selected_action_and_arguments(tool_plan):
    def handler(request):
        if request.url.path=='/props': return httpx.Response(200,json={'default_generation_settings':{'n_ctx':4096}})
        if request.url.path=='/apply-template': return httpx.Response(200,json={'prompt':'formatted'})
        if request.url.path=='/tokenize': return httpx.Response(200,json={'tokens':[1]})
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':json.dumps(tool_plan)}}]})
    result=LocalModel(transport=httpx.MockTransport(handler)).plan_task('Current request',[{'name':'Inspection report.pdf'}],[])
    assert result['action']==tool_plan['action']
    assert result['response']==''
    for key in ('target','expression','document_scope'):
        assert result[key]==tool_plan.get(key,'focused' if key=='document_scope' else '')


@pytest.mark.parametrize('field,value',[('target',None),('expression',{}),('document_scope','invalid')])
def test_compact_plan_rejects_invalid_optional_tool_argument(field,value):
    def handler(request):
        if request.url.path=='/props': return httpx.Response(200,json={'default_generation_settings':{'n_ctx':4096}})
        if request.url.path=='/apply-template': return httpx.Response(200,json={'prompt':'formatted'})
        if request.url.path=='/tokenize': return httpx.Response(200,json={'tokens':[1]})
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'action':'calculate','response':'',field:value})}}]})
    with pytest.raises(WorkbenchError) as error:
        LocalModel(transport=httpx.MockTransport(handler)).plan_task('7*8',[],[])
    assert error.value.code=='generation_format'
