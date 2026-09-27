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
    assert seen[0]['response_format']['json_schema']['schema']['required']==['code']


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
