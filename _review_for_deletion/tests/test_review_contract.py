import json
import pytest
from backend.model import LocalModel, ReviewContract
from backend.contracts import WorkbenchError


def contract():
    return ReviewContract('workspace_operation_plan', ('scope','operation_intent'),
        ('scope','operations','reason','replacements'), ('complete_source','runtime_validation'))


def reply(value):
    return {'choices':[{'finish_reason':'stop','message':{'content':json.dumps(value)}}]}


def issue(requirement='intent', field='reason', obligation='operation_intent'):
    return {'obligation':obligation,'field':field,'requirement':requirement,
        'evidence':'User requests an existing-file edit','defect':'Requested interface is missing'}


def setup(monkeypatch, reviews):
    model=LocalModel(verify_semantics=True,review_attempts=2)
    calls=[];sequence=iter(reviews);generated=[]
    def generate(payload, output=None):
        generated.append(payload)
        return reply({'scope':'existing_files','operations':[{'action':'edit','path':'a.py','reason':'Implement requested behavior'}]})
    def request(method,path,**kwargs):
        if 'response_format' not in kwargs['json']:
            return reply({'task_interpretation':'Edit the selected file only'})
        calls.append(kwargs['json']);return reply(next(sequence))
    monkeypatch.setattr(model,'_public_completion',generate)
    monkeypatch.setattr(model,'_request',request)
    return model,calls,generated


def run(model):
    return model._planned_completion({'messages':[{'role':'user','content':'Edit the selected file'}]},
        review_contract=contract())


def test_valid_accept_has_no_extra_review_call(monkeypatch):
    model,calls,generated=setup(monkeypatch,[{'verdict':'accept','issues':[]}])
    run(model)
    assert len(calls)==len(generated)==1
    assert calls[0]['response_format']['json_schema']['schema']['properties']['issues']['items']['type']=='object'


@pytest.mark.parametrize('bad',[issue('nonempty_replacements','replacements'),
    issue('complete_source'), issue(field='source'), issue(obligation='unknown')])
def test_inexpressible_review_corrected_once_same_candidate(monkeypatch,bad):
    model,calls,generated=setup(monkeypatch,[{'verdict':'revise','issues':[bad]},
        {'verdict':'accept','issues':[]}])
    run(model)
    assert len(calls)==2 and len(generated)==1
    assert 'SAME candidate' in calls[1]['messages'][-1]['content']
    assert calls[0]['messages'][-1]['content']==calls[1]['messages'][-2]['content']


def test_invalid_corrected_review_never_autoaccepts(monkeypatch):
    bad={'verdict':'revise','issues':[issue('complete_source')]}
    model,calls,generated=setup(monkeypatch,[bad,bad])
    with pytest.raises(WorkbenchError):run(model)
    assert len(calls)==2 and len(generated)==1


def test_valid_rejection_still_repairs_candidate(monkeypatch):
    model,calls,generated=setup(monkeypatch,[{'verdict':'revise','issues':[issue()]},
        {'verdict':'accept','issues':[]}])
    run(model)
    assert len(calls)==len(generated)==2
    assert 'validation_feedback' in generated[1]['messages'][-1]['content']


def test_cancellation_before_correction(monkeypatch):
    model,calls,generated=setup(monkeypatch,[{'verdict':'revise','issues':[issue('complete_source')]}])
    def cancelled():
        if calls:raise WorkbenchError('cancelled','Stopped')
    monkeypatch.setattr(model,'_check_cancelled',cancelled)
    with pytest.raises(WorkbenchError) as error:run(model)
    assert error.value.code=='cancelled' and len(calls)==1


def test_legacy_prose_transport_remains_compatible(monkeypatch):
    model,calls,generated=setup(monkeypatch,[{'verdict':'revise','issues':['Wrong authorized target']},
        {'verdict':'accept','issues':[]}])
    run(model)
    assert len(calls)==len(generated)==2


def test_contract_correction_budget_is_shared_across_plan_attempts(monkeypatch):
    bad={'verdict':'revise','issues':[issue('complete_source')]}
    model,calls,generated=setup(monkeypatch,[bad, {'verdict':'revise','issues':[issue()]}, bad])
    with pytest.raises(WorkbenchError):run(model)
    assert len(calls)==3 and len(generated)==2


def test_existing_request_budget_failure_propagates(monkeypatch):
    model,calls,generated=setup(monkeypatch,[{'verdict':'revise','issues':[issue('complete_source')]}])
    original=model._request
    def bounded(method,path,**kwargs):
        if calls:raise WorkbenchError('budget_exceeded','Model-call budget exhausted')
        return original(method,path,**kwargs)
    monkeypatch.setattr(model,'_request',bounded)
    with pytest.raises(WorkbenchError) as error:run(model)
    assert error.value.code=='budget_exceeded' and len(generated)==1


def test_workspace_plan_trace_hashes_candidate_without_replacement_source(monkeypatch):
    import hashlib
    from router.telemetry import CURRENT_ROUTE, RoutingDecision
    model,calls,generated=setup(monkeypatch,[{'verdict':'accept','issues':[]}])
    artifact={'scope':'existing_files','operations':[{'action':'edit','path':'a.py',
        'reason':'Preserve requested interface','replacements':[{'old_text':'SECRET OLD SOURCE',
        'new_text':'SECRET NEW SOURCE'}], 'source':'SECRET WHOLE SOURCE'}]}
    encoded=json.dumps(artifact)
    monkeypatch.setattr(model,'_public_completion',lambda *args: reply(artifact))
    trace=RoutingDecision();token=CURRENT_ROUTE.set(trace)
    try:run(model)
    finally:CURRENT_ROUTE.reset(token)
    recorded=next(s for s in trace.stages if s['stage']=='workspace_plan_candidate')
    assert recorded['candidate_sha256']==hashlib.sha256(encoded.encode()).hexdigest()
    assert recorded['scope']=='existing_files' and recorded['complete'] is True
    assert recorded['operations']==[{'action':'edit','path':'a.py','reason':'Preserve requested interface',
        'replacements_count':1}]
    assert 'SECRET' not in json.dumps(trace.stages)
