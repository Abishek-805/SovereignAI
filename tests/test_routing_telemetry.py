from router.telemetry import RoutingDecision, CURRENT_ROUTE, observe_completion
from backend.cancellation import cancellable_model_job
from backend.contracts import WorkbenchError
from contextlib import nullcontext
import pytest


def test_unknowns_and_measured_completion_are_distinct():
    trace=RoutingDecision()
    assert trace.snapshot()['inference_time'] is None
    token=CURRENT_ROUTE.set(trace)
    try:
        observe_completion({'usage':{'prompt_tokens':12},'timings':{'prompt_ms':20,'predicted_ms':80}},.7)
    finally:CURRENT_ROUTE.reset(token)
    assert trace.inference_time==.1
    assert trace.model_request_time==.7
    assert trace.model_load_time is None


def test_coding_request_records_public_features_without_private_reasoning():
    trace=RoutingDecision()
    trace.coding_request({'original_request':'creat main.py','normalized_request':'create main.py',
                          'task_type':'CODE_GENERATION','complexity':'simple','worker_role':'code',
                          'features':{'active_file':'main.py','file_count':1},
                          'reasoning':'private text'},normalization_seconds=.002)
    snapshot=trace.snapshot()
    assert snapshot['original_request']=='creat main.py'
    assert snapshot['normalized_request']=='create main.py'
    assert snapshot['task_type']=='CODE_GENERATION'
    assert snapshot['coding_context']['active_file']=='main.py'
    assert snapshot['timings']['normalization_ms']==2
    assert 'private text' not in str(snapshot)


class Service:
    model=object()
    def remember_route(self,value):self.saved=value
    @cancellable_model_job
    def outer(self,question,job=None):
        self.inner(question)
        return {'plan':{'action':'answer'},'answer':'Actual response'}
    @cancellable_model_job
    def inner(self,question,job=None):
        assert CURRENT_ROUTE.get() is not None
        return {'status':'conversation'}
    @cancellable_model_job
    def fail(self,question,job=None):raise WorkbenchError('model_unavailable','No admissible model')


def test_nested_scopes_share_one_decision_and_restore():
    service=Service()
    response=service.outer('hello')
    decision=response['routing']['decision']
    assert decision['request_id']==service.saved['request_id']
    assert decision['intent']=='answer'
    assert CURRENT_ROUTE.get() is None
    assert service.outer('another')['routing']['decision']['request_id']!=decision['request_id']


def test_failure_retains_real_reason_without_fallback():
    service=Service()
    with pytest.raises(WorkbenchError) as error:service.fail('question')
    assert service.saved['errors']==[{'code':'model_unavailable','message':'No admissible model'}]
    assert error.value.routing['fallback'] is None
    assert CURRENT_ROUTE.get() is None

@pytest.mark.parametrize('value', [True, -1, float('nan'), float('inf')])
def test_invalid_runtime_timing_is_not_reported_as_measured(value):
    trace=RoutingDecision()
    token=CURRENT_ROUTE.set(trace)
    try:
        observe_completion({'timings':{'prompt_ms':value,'predicted_ms':10}},.1)
    finally:CURRENT_ROUTE.reset(token)
    assert trace.inference_time is None
