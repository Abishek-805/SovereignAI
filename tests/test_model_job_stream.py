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


@pytest.mark.parametrize('text,expected', [
    ('{"answer":"Hello', 'Hello'),
    ('{"answer":"line\\nnext', 'line\nnext'),
    ('{"answer":"ok\\u26', 'ok'),
    ('{"plan":{"answer":"private"},"answer":"public', 'public'),
    ('{"plan":{"answer":"private', ''),
    ('{"thinking":"secret', ''),
])
def test_public_prefix_exposes_only_top_level_public_string(text, expected):
    from backend.model import public_json_prefix
    assert public_json_prefix(text, 'answer') == expected


def test_live_job_preview_accumulates_public_answer_before_final_and_hides_after_stop():
    from backend.jobs import Job
    job=Job('ask');observed=[]
    class PreviewEvents(Events):
        def __iter__(self):
            for chunk in self.chunks:
                observed.append(job.snapshot()['partial_answer'])
                yield chunk
    stream=PreviewEvents([
        event({'choices':[{'delta':{'content':'{"answer":"Hel'}}]}),
        event({'choices':[{'delta':{'content':'lo","status":"answered"}'}}]}),
        event({'choices':[{'delta':{},'finish_reason':'stop'}]}),
        b'data: [DONE]\n\n'])
    model=LocalModel(transport=httpx.MockTransport(lambda request:httpx.Response(
        200,headers={'content-type':'text/event-stream'},stream=stream)))
    with model.cancel_scope(job.cancel), model.job_scope(job):
        model._request_raw('POST','/v1/chat/completions',json={'response_format':{'json_schema':{'name':'grounded_answer'}}})
    assert 'Hel' in observed and job.snapshot()['partial_answer']=='Hello'
    job.cancel.set()
    assert job.snapshot()['partial_answer']=='' and job.snapshot()['partial_kind'] is None


def test_internal_planning_stream_does_not_change_public_preview():
    from backend.jobs import Job
    job=Job('agent')
    model=LocalModel(transport=httpx.MockTransport(lambda request:httpx.Response(
        200,headers={'content-type':'text/event-stream'},stream=completion_stream())))
    with model.cancel_scope(job.cancel),model.job_scope(job):
        model._request_raw('POST','/v1/chat/completions',json={'response_format':{'json_schema':{'name':'internal_plan'}}})
    assert job.snapshot()['partial_answer']=='' and job.snapshot()['partial_kind'] is None


def test_code_preview_is_display_only_and_completed_snapshot_hides_it():
    from backend.jobs import Job
    from backend.model import CODE_GRAMMAR
    job=Job('edit')
    stream=Events([
        event({'choices':[{'delta':{'content':'{"code":"print('}}]}),
        event({'choices':[{'delta':{'content':'1)"}'},'finish_reason':'stop'}]}),
        b'data: [DONE]\n\n'])
    model=LocalModel(transport=httpx.MockTransport(lambda request:httpx.Response(
        200,headers={'content-type':'text/event-stream'},stream=stream)))
    with model.cancel_scope(job.cancel),model.job_scope(job):
        response=model._request_raw('POST','/v1/chat/completions',json={'grammar':CODE_GRAMMAR})
    assert job.snapshot()['partial_answer']=='print(1)'
    assert job.snapshot()['partial_kind']=='code'
    assert json.loads(response['choices'][0]['message']['content'])=={'code':'print(1)'}
    assert job.result is None  # A streamed draft cannot publish or complete the task.
    job.state='completed'
    assert job.snapshot()['partial_answer']==''


def test_preview_waits_for_complete_escaped_surrogate_pair():
    from backend.model import public_json_prefix
    assert public_json_prefix('{"answer":"Hi \\ud83d', 'answer')=='Hi '
    assert public_json_prefix('{"answer":"Hi \\ud83d\\ude00', 'answer')=='Hi '+chr(0x1f600)


def test_simple_public_plain_answer_streams_but_reasoning_delta_is_never_public():
    from backend.jobs import Job
    job=Job('agent');observed=[]
    class PublicEvents(Events):
        def __iter__(self):
            for chunk in self.chunks:
                observed.append(job.snapshot()['partial_answer'])
                yield chunk
    stream=PublicEvents([
        event({'choices':[{'delta':{'reasoning_content':'private chain'}}]}),
        event({'choices':[{'delta':{'content':'Hello'}}]}),
        event({'choices':[{'delta':{'content':' there'},'finish_reason':'stop'}]}),
        b'data: [DONE]\n\n'])
    model=LocalModel(transport=httpx.MockTransport(lambda request:httpx.Response(
        200,headers={'content-type':'text/event-stream'},stream=stream)))
    with model.cancel_scope(job.cancel),model.job_scope(job):answer=model.simple_answer('Hi')
    assert answer=='Hello there'
    assert 'Hello' in observed and job.snapshot()['partial_answer']=='Hello there'
    assert all('private chain' not in text for text in observed)


@pytest.mark.parametrize('action,expected',[('answer','Natural reply'),('edit_code','')])
def test_action_plan_exposes_response_only_after_complete_answer_action(action,expected):
    from backend.jobs import Job
    job=Job('agent')
    stream=Events([
        event({'choices':[{'delta':{'content':'{"action":"'+action+'","response":"Natural'}}]}),
        event({'choices':[{'delta':{'content':' reply"}'},'finish_reason':'stop'}]}),
        b'data: [DONE]\n\n'])
    model=LocalModel(transport=httpx.MockTransport(lambda request:httpx.Response(
        200,headers={'content-type':'text/event-stream'},stream=stream)))
    with model.cancel_scope(job.cancel),model.job_scope(job):
        model._public_completion({'messages':[]},'action_answer')
    assert job.snapshot()['partial_answer']==expected


def test_plain_public_scope_does_not_leak_into_subsequent_internal_generation():
    from backend.jobs import Job
    job=Job('agent')
    def handler(request):
        stream=Events([event({'choices':[{'delta':{'content':'PUBLIC'},'finish_reason':'stop'}]}),b'data: [DONE]\n\n'])
        return httpx.Response(200,headers={'content-type':'text/event-stream'},stream=stream)
    model=LocalModel(transport=httpx.MockTransport(handler))
    with model.cancel_scope(job.cancel),model.job_scope(job):
        model._public_completion({'messages':[]},'plain_answer')
        job.preview('',None)
        model._request_raw('POST','/v1/chat/completions',json={'messages':[]})
    assert job.snapshot()['partial_answer']==''


def test_public_conversation_candidate_streams_while_interpretation_and_review_remain_private():
    from backend.jobs import Job
    job=Job('agent');observed=[]
    class ObservedEvents(Events):
        def __iter__(self):
            for chunk in self.chunks:
                observed.append(job.snapshot()['partial_answer'])
                yield chunk
    def handler(request):
        payload=json.loads(request.content)
        if payload.get('response_format'):
            content='{"verdict":"accept","issues":[]}'
        elif payload['messages'][0]['content'].startswith('Describe the CURRENT'):
            content='PRIVATE INTERPRETATION'
        else:content='Public explanation'
        return httpx.Response(200,headers={'content-type':'text/event-stream'},stream=ObservedEvents([
            event({'choices':[{'delta':{'content':content},'finish_reason':'stop'}]}),b'data: [DONE]\n\n']))
    model=LocalModel(transport=httpx.MockTransport(handler),verify_semantics=True)
    with model.cancel_scope(job.cancel),model.job_scope(job):
        result=model._planned_completion({'model':'test','messages':[{'role':'system','content':'Answer naturally'},{'role':'user','content':'Explain it'}]},public_output='plain_answer')
    assert result['choices'][0]['message']['content']=='Public explanation'
    assert 'Public explanation' in observed
    assert all('PRIVATE' not in text and 'verdict' not in text for text in observed)
