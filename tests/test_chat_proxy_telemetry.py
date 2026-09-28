import json
import httpx
import pytest
from fastapi.testclient import TestClient
from backend.app import create_app
from backend.contracts import WorkbenchError
from backend.model import LocalModel
from tests.test_service import service


def upstream(monkeypatch,response=None,error=None):
    forwarded=[]
    class Client:
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def request(self,method,url,**kwargs):
            forwarded.append(kwargs)
            if error:raise error
            return response or httpx.Response(200,json={'choices':[]})
    monkeypatch.setattr('backend.app.httpx.AsyncClient',lambda **kwargs:Client())
    return forwarded

@pytest.mark.parametrize('stream',[False,True])
def test_formal_arithmetic_uses_tool_without_upstream_or_model_lease(service,monkeypatch,stream):
    sent=upstream(monkeypatch)
    service._lease=lambda *args,**kwargs: (_ for _ in ()).throw(AssertionError('Calculator must not load a model'))
    with TestClient(create_app(service),base_url='http://127.0.0.1:8088') as client:
        response=client.post('/v1/chat/completions',json={'messages':[{'role':'user','content':'18.5 * 24'}],'stream':stream})
    assert response.status_code==200,response.text
    assert not sent
    assert '444.0' in response.text
    if stream:assert response.text.endswith('data: [DONE]\n\n')
    trace=service.routing_decision(response.headers['x-sovereign-request-id'])
    assert trace['intent']=='calculate'
    assert trace['selected_model'] is None
    assert trace['evidence_used'] is False
    assert trace['inference_time'] is None


def test_actual_template_tokenizer_and_bounded_output_before_generation(service,monkeypatch):
    token_calls=[];leases=[]
    def runtime(request):
        token_calls.append(request.url.path)
        if request.url.path=='/apply-template':return httpx.Response(200,json={'prompt':'actual chat template'})
        return httpx.Response(200,json={'tokens':list(range(17))})
    service.model=LocalModel(transport=httpx.MockTransport(runtime))
    service._lease=lambda capability,required_context=None:leases.append((capability,required_context)) or 'text'
    sent=upstream(monkeypatch,httpx.Response(200,json={'choices':[],'timings':{'prompt_ms':12,'predicted_ms':28}}))
    with TestClient(create_app(service),base_url='http://127.0.0.1:8088') as client:
        response=client.post('/v1/chat/completions',json={'messages':[{'role':'user','content':'Question'}],'max_tokens':-1})
    assert response.status_code==200 and not service.ask_lock.locked()
    assert token_calls==['/apply-template','/tokenize']
    assert leases==[('text',None),('text',17+4096+64)]
    assert json.loads(sent[0]['content'])['max_tokens']==4096
    trace=service.routing_decision(response.headers['x-sovereign-request-id'])
    assert trace['required_context']==4177 and trace['inference_time']==0.04
    assert trace['model_request_time']>=0 and trace['errors']==[]


def test_context_rejection_records_actual_failure_and_does_not_generate(service,monkeypatch):
    service.model=LocalModel();service.model.count_messages=lambda messages,payload=None:9000
    def lease(capability,required_context=None):
        if required_context:raise WorkbenchError('context_budget','Measured context exceeds candidate limit')
        return 'text'
    service._lease=lease
    sent=upstream(monkeypatch)
    with TestClient(create_app(service),base_url='http://127.0.0.1:8088') as client:response=client.post('/v1/chat/completions',json={'messages':[],'max_tokens':10})
    assert response.status_code==422 and sent==[] and not service.ask_lock.locked()
    trace=service.routing_decision(response.headers['x-sovereign-request-id'])
    assert trace['errors']==[{'code':'context_budget','message':'Measured context exceeds candidate limit'}]
    assert trace['required_context']==9074 and trace['inference_time'] is None


def test_upstream_failure_remembers_request_error(service,monkeypatch):
    upstream(monkeypatch,error=httpx.ConnectError('Actual connection failure'))
    with TestClient(create_app(service),base_url='http://127.0.0.1:8088') as client:response=client.post('/v1/chat/completions',json={'messages':[]})
    assert response.status_code==503 and not service.ask_lock.locked()
    trace=service.routing_decision(response.headers['x-sovereign-request-id'])
    assert trace['errors'][0]['message']=='Actual connection failure'
    assert trace['inference_time'] is None


def test_nonstream_upstream_http_failure_keeps_status_and_telemetry(service,monkeypatch):
    upstream(monkeypatch,httpx.Response(429,json={'error':{'message':'Rate limit'}}))
    with TestClient(create_app(service),base_url='http://127.0.0.1:8088') as client:response=client.post('/v1/chat/completions',json={'messages':[]})
    assert response.status_code==429
    trace=service.routing_decision(response.headers['x-sovereign-request-id'])
    assert trace['errors'][0]['code']=='upstream_429' and trace['model_request_time']>=0


def test_unknown_route_is_404_and_busy_has_request_identity(service,monkeypatch):
    service.ask_lock.acquire()
    try:
        with TestClient(create_app(service),base_url='http://127.0.0.1:8088') as client:
            assert client.get('/routing/decisions/no-such-request').status_code==404
            response=client.post('/v1/chat/completions',json={'messages':[]})
        assert response.status_code==409
        assert service.routing_decision(response.headers['x-sovereign-request-id'])['errors'][0]['code']=='busy'
    finally:service.ask_lock.release()


def test_image_context_expansion_remains_unknown(service,monkeypatch):
    leases=[];service.model=LocalModel()
    service.model.count_messages=lambda _:(_ for _ in ()).throw(AssertionError('Must not fake vision patch count'))
    service._lease=lambda capability,required_context=None:leases.append((capability,required_context)) or 'vision'
    upstream(monkeypatch)
    with TestClient(create_app(service),base_url='http://127.0.0.1:8088') as client:response=client.post('/v1/chat/completions',json={'messages':[{'role':'user','content':[{'type':'image_url','image_url':{'url':'data:image/png;base64,AA=='}}]}]})
    assert response.status_code==200 and leases==[('vision',None)]
    trace=service.routing_decision(response.headers['x-sovereign-request-id'])
    assert trace['required_context'] is None and trace['modality']=='image'

@pytest.mark.parametrize('value',[True,-1,float('nan'),float('inf'),None])
def test_stream_invalid_timings_remain_unknown(service,monkeypatch,value):
    class Bytes(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield ('data: '+json.dumps({'timings':{'prompt_ms':value,'predicted_ms':10}})+'\n\n').encode()
            yield b'data: [DONE]\n\n'
    class Client:
        def build_request(self,method,url,**kwargs):return httpx.Request(method,url,**kwargs)
        async def send(self,request,stream=False):return httpx.Response(200,headers={'content-type':'text/event-stream'},stream=Bytes())
        async def aclose(self):pass
    monkeypatch.setattr('backend.app.httpx.AsyncClient',lambda **kwargs:Client())
    with TestClient(create_app(service),base_url='http://127.0.0.1:8088') as client:
        response=client.post('/v1/chat/completions',json={'messages':[],'stream':True})
    assert response.status_code==200
    trace=service.routing_decision(response.headers['x-sovereign-request-id'])
    assert trace['inference_time'] is None and trace['model_request_time']>=0
    assert not service.ask_lock.locked()
