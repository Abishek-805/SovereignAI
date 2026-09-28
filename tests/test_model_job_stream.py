"""SSE jobs retain the completion contract and close only their own response."""
import json
from threading import Event
import httpx
import pytest
from backend.contracts import WorkbenchError
from backend.model import LocalModel

class Events(httpx.SyncByteStream):
    def __init__(self, chunks, cancel=None):
        self.chunks=chunks;self.cancel=cancel;self.closed=False
    def __iter__(self):
        for index,chunk in enumerate(self.chunks):
            if self.cancel is not None and index==1:self.cancel.set()
            yield chunk
    def close(self):self.closed=True

def event(value):return ('data: '+json.dumps(value)+'\n\n').encode()

def completion_stream():
    return Events([
        b': heartbeat\n\n',
        event({'choices':[{'index':0,'delta':{'role':'assistant','content':'{"status":'}}]}),
        event({'choices':[{'index':0,'delta':{'content':'"answered","answer":"Hi"}'}}]}),
        event({'choices':[{'index':0,'delta':{},'finish_reason':'stop'}]}),
        event({'choices':[],'usage':{'prompt_tokens':23,'completion_tokens':10},'timings':{'predicted_ms':42}}),
        b'data: [DONE]\n\n'])

def test_sse_partial_content_usage_and_response_close():
    stream=completion_stream();seen=[]
    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200,headers={'content-type':'text/event-stream'},stream=stream)
    model=LocalModel(transport=httpx.MockTransport(handler))
    with model.cancel_scope(Event()):result=model.complete([])
    assert result['result']=={'status':'answered','answer':'Hi'}
    assert result['usage']=={'prompt_tokens':23,'completion_tokens':10}
    assert result['timings']=={'predicted_ms':42}
    assert seen[0]['stream'] is True
    assert seen[0]['stream_options']=={'include_usage':True}
    assert stream.closed


def test_stop_mid_stream_closes_request_and_restores_other_request_scope():
    cancelled=Event();stream=Events([event({'choices':[{'delta':{'content':'Partial'}}]}),
                                     event({'choices':[{'delta':{'content':'discard'},'finish_reason':'stop'}]})],cancelled)
    paths=[]
    def handler(request):
        paths.append(request.url.path)
        if request.url.path=='/props':return httpx.Response(200,json={'is_sleeping':False})
        return httpx.Response(200,headers={'content-type':'text/event-stream'},stream=stream)
    model=LocalModel(transport=httpx.MockTransport(handler))
    with model.cancel_scope(cancelled),pytest.raises(WorkbenchError) as error:model.complete([])
    assert error.value.code=='cancelled'
    assert stream.closed
    assert model.status()['available'] is True
    assert paths==['/v1/chat/completions','/props'] # No global stop/kill endpoint.


@pytest.mark.parametrize('chunks',[ [b'data: [DONE]\n\n'],
    [event({'choices':[{'delta':{'content':'unfinished'}}]})],
    [b'data: malformed\n\n'], [event({'error':{'message':'bad request'}})] ])
def test_truncated_or_invalid_sse_does_not_publish_partial_answer(chunks):
    stream=Events(chunks)
    model=LocalModel(transport=httpx.MockTransport(lambda request:httpx.Response(
        200,headers={'content-type':'text/event-stream'},stream=stream)))
    with model.cancel_scope(Event()),pytest.raises(WorkbenchError) as error:model.complete([])
    assert error.value.code=='generation_format'
    assert stream.closed


def test_job_stream_json_fallback_and_loading_error():
    for status,body,expected in [(200,{'choices':[{'finish_reason':'stop','message':{'content':'{"status":"answered","answer":"Hi"}'}}]},None),
                                 (503,{'error':{'message':'Loading model'}},'model_loading')]:
        model=LocalModel(transport=httpx.MockTransport(lambda request:httpx.Response(status,json=body)))
        with model.cancel_scope(Event()):
            if expected:
                with pytest.raises(WorkbenchError) as error:model.complete([])
                assert error.value.code==expected
            else:assert model.complete([])['result']['answer']=='Hi'
