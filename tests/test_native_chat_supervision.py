import asyncio
import json
import httpx
import pytest
from backend.task_supervisor import CURRENT_SUPERVISOR,consume,operational_event
from tests.test_api import client_for
from tests.test_service import service


def records(service):
    return [json.loads(path.read_text(encoding='utf-8')) for path in (service.settings.data_dir/'supervision').glob('*.json')]


class FakeClient:
    def __init__(self,callback):self.callback=callback
    async def __aenter__(self):return self
    async def __aexit__(self,*args):pass
    async def aclose(self):pass
    def build_request(self,method,url,**kwargs):return httpx.Request(method,url,**kwargs)
    async def request(self,method,url,**kwargs):return self.callback()
    async def send(self,request,**kwargs):return self.callback()


def test_native_chat_persists_original_scope_and_counts_direct_inference(service,monkeypatch):
    observed=[]
    def lease(capability,*args,**kwargs):
        current=CURRENT_SUPERVISOR.get();assert current is not None
        observed.append(current.id)
        consume('model_switches','warm-general')
        operational_event('MODEL_READY',selected_model='warm-general')
        return 'text'
    monkeypatch.setattr(service,'_lease',lease)
    def respond():
        current=CURRENT_SUPERVISOR.get();assert current is not None
        assert current.counts['model_calls']==1
        return httpx.Response(200,json={'choices':[{'message':{'content':'A response'},'finish_reason':'stop'}]})
    monkeypatch.setattr('backend.app.httpx.AsyncClient',lambda **kwargs:FakeClient(respond))
    with client_for(service) as client:
        response=client.post('/v1/chat/completions',json={'messages':[
            {'role':'user','content':'Prior request'}, {'role':'assistant','content':'Prior response'},
            {'role':'user','content':'Explain the next topic'}]})
    assert response.status_code==200
    saved=records(service);assert len(saved)==1
    assert saved[0]['supervisor_id']==observed[0]
    assert saved[0]['goal']=='Explain the next topic'
    assert saved[0]['context']['document_ids']==[] and saved[0]['context']['workspace_id'] is None
    assert saved[0]['context']['reference_history']==['user: Prior request','assistant: Prior response']
    assert saved[0]['counts']['model_calls']==1
    assert saved[0]['completion']['state']=='unverified' and not saved[0]['completion']['achieved']
    assert saved[0]['task_state']['intent']=='GENERAL'
    assert saved[0]['task_state']['workflow']=='CHAT' and saved[0]['task_state']['modality']=='text'
    assert CURRENT_SUPERVISOR.get() is None and not service.ask_lock.locked()


def test_native_chat_planner_and_direct_request_share_budget_no_code_execution(service,monkeypatch):
    calls=[]
    service.supervisor_limits={'model_calls':1}
    monkeypatch.setattr(service,'_lease',lambda *args,**kwargs:'code')
    def plan(*args):
        consume('model_calls');return {'action':'edit_code','target':'main.py','response':''}
    monkeypatch.setattr(service.model,'plan_task',plan)
    monkeypatch.setattr(service.coding,'run_project',lambda *args,**kwargs:pytest.fail('Native Chat cannot execute or stage code'))
    monkeypatch.setattr('backend.app.httpx.AsyncClient',lambda **kwargs:FakeClient(lambda:calls.append(True) or httpx.Response(200,json={})))
    with client_for(service) as client:
        response=client.post('/v1/chat/completions',json={'messages':[{'role':'user','content':'Create a Python program'}]})
    assert response.status_code==400 and response.json()['code']=='supervisor_budget'
    assert not calls and not service.ask_lock.locked()
    saved=records(service)[0]
    assert saved['counts']['model_calls']==1 and saved['completion']['state']=='failed'


@pytest.mark.parametrize('stream,expected',[
    (b'data: {"choices":[{"delta":{"content":"Reply"},"finish_reason":null}]}\n\ndata: [DONE]\n\n','unverified'),
    (b'data: {"choices":[{"delta":{"content":"Partial"},"finish_reason":null}]}\n\n','failed'),
    (b'data: {"choices":[{"delta":{"content":"Partial"},"finish_reason":"length"}]}\n\ndata: [DONE]\n\n','failed'),
    (b'data: {"error":{"message":"failed"}}\n\ndata: [DONE]\n\n','failed'),
])
def test_native_chat_stream_terminal_observation_and_lock_release(service,monkeypatch,stream,expected):
    monkeypatch.setattr(service,'_lease',lambda *args,**kwargs:'text')
    monkeypatch.setattr('backend.app.httpx.AsyncClient',lambda **kwargs:FakeClient(lambda:httpx.Response(200,content=stream,headers={'content-type':'text/event-stream'})))
    with client_for(service) as client:
        response=client.post('/v1/chat/completions',json={'stream':True,'messages':[{'role':'user','content':'Hello'}]})
    assert response.status_code==200 and response.content==stream
    saved=records(service)[0]
    assert saved['counts']['model_calls']==1 and saved['completion']['state']==expected
    assert not saved['completion']['achieved'] and not service.ask_lock.locked()


def test_native_chat_cancelled_stream_is_recorded_without_success(service,monkeypatch):
    class CancelledStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b'data: {"choices":[]}\n\n'
            raise asyncio.CancelledError('Client cancelled')
    monkeypatch.setattr(service,'_lease',lambda *args,**kwargs:'text')
    monkeypatch.setattr('backend.app.httpx.AsyncClient',lambda **kwargs:FakeClient(lambda:httpx.Response(200,stream=CancelledStream(),headers={'content-type':'text/event-stream'})))
    with client_for(service) as client:
        client.post('/v1/chat/completions',json={'stream':True,'messages':[{'role':'user','content':'Hello'}]})
    saved=records(service)[0]
    assert saved['completion']['state']=='cancelled' and saved['task_state']['cancellation_state']
    assert not saved['completion']['achieved'] and not service.ask_lock.locked()


def test_native_calculator_uses_same_envelope_and_no_worker(service,monkeypatch):
    monkeypatch.setattr(service,'_lease',lambda *args,**kwargs:pytest.fail('Calculator requires no model'))
    with client_for(service) as client:
        response=client.post('/v1/chat/completions',json={'messages':[{'role':'user','content':'12 * 5'}]})
    assert '60' in response.json()['choices'][0]['message']['content']
    saved=records(service);assert len(saved)==1
    assert saved[0]['counts']['model_calls']==0
    assert saved[0]['completion']['state']=='completed'


@pytest.mark.parametrize('completion',[
    {'choices':[{'message':{'content':'Partial'},'finish_reason':'length'}]},
    {'error':{'message':'Model failed'}},
])
def test_native_nonstream_incomplete_generation_is_not_delivered_success(service,monkeypatch,completion):
    monkeypatch.setattr(service,'_lease',lambda *args,**kwargs:'text')
    monkeypatch.setattr('backend.app.httpx.AsyncClient',lambda **kwargs:FakeClient(lambda:httpx.Response(200,json=completion)))
    with client_for(service) as client:
        response=client.post('/v1/chat/completions',json={'messages':[{'role':'user','content':'Hello'}]})
    assert response.status_code==200  # Preserve the upstream transport contract.
    saved=records(service)[0]
    assert saved['completion']['state']=='failed' and not saved['completion']['achieved']
    assert not saved['completion']['response_delivered']


@pytest.mark.parametrize('preference',[None,False,True])
def test_native_chat_disables_thinking_by_default_and_strips_private_response(service,monkeypatch,preference):
    monkeypatch.setattr(service,'_lease',lambda *args,**kwargs:'text')
    captured=[]
    class CaptureClient(FakeClient):
        async def request(self,method,url,**kwargs):
            captured.append(json.loads(kwargs['content']))
            return self.callback()
    result={'choices':[{'message':{'content':'Hello','reasoning_content':'PRIVATE SECRET','reasoning':{'thoughts':'PRIVATE SECRET'}},'finish_reason':'stop'}]}
    monkeypatch.setattr('backend.app.httpx.AsyncClient',lambda **kwargs:CaptureClient(lambda:httpx.Response(200,json=result)))
    payload={'messages':[{'role':'user','content':'Hi'}]}
    if preference is not None:payload['chat_template_kwargs']={'enable_thinking':preference,'other':'preserved'}
    with client_for(service) as client:response=client.post('/v1/chat/completions',json=payload)
    assert response.status_code==200
    assert captured[0]['chat_template_kwargs']['enable_thinking'] is (False if preference is None else preference)
    if preference is not None:assert captured[0]['chat_template_kwargs']['other']=='preserved'
    assert response.json()['choices'][0]['message']=={'content':'Hello'}
    assert 'PRIVATE SECRET' not in response.text
    assert 'PRIVATE SECRET' not in json.dumps(records(service))


def test_native_chat_sanitizes_split_sse_private_reasoning_preserves_unicode_and_framing(service,monkeypatch):
    monkeypatch.setattr(service,'_lease',lambda *args,**kwargs:'text')
    raw=('data: '+json.dumps({'choices':[{'delta':{'reasoning_content':'PRIVATE SECRET','content':'h\u00e9llo\U0001f600'},'finish_reason':None}]},ensure_ascii=False)+'\r\n\r\ndata: [DONE]\r\n\r\n').encode()
    class SplitStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            for byte in raw:yield bytes([byte])
    monkeypatch.setattr('backend.app.httpx.AsyncClient',lambda **kwargs:FakeClient(lambda:httpx.Response(200,stream=SplitStream(),headers={'content-type':'text/event-stream'})))
    with client_for(service) as client:
        response=client.post('/v1/chat/completions',json={'messages':[{'role':'user','content':'Hi'}],'stream':True})
    assert response.status_code==200 and 'PRIVATE SECRET' not in response.text and 'reasoning_content' not in response.text
    assert response.content.endswith(b'data: [DONE]\r\n\r\n')
    event=json.loads(response.text.split('\r\n')[0][5:])
    assert event['choices'][0]['delta']=={'content':'h\u00e9llo\U0001f600'}
    assert not service.ask_lock.locked() and records(service)[0]['completion']['state']=='unverified'



def test_native_rejoined_stream_keeps_sse_identity_and_hides_reasoning(service,monkeypatch):
    raw=b'id: 12\nevent: message\ndata: {"choices":[{"delta":{"reasoning_content":"PRIVATE SECRET","content":"Visible"}}]}\n\ndata: [DONE]\n\n'
    monkeypatch.setattr('backend.app.httpx.AsyncClient',lambda **kwargs:FakeClient(lambda:httpx.Response(200,content=raw,headers={'content-type':'text/event-stream'})))
    with client_for(service) as client:response=client.get('/v1/stream?conv_id=chat-12&from=0')
    assert response.status_code==200 and response.content.startswith(b'id: 12\nevent: message\n')
    assert 'PRIVATE SECRET' not in response.text and 'Visible' in response.text
    assert response.content.endswith(b'data: [DONE]\n\n')
    assert not service.ask_lock.locked()
