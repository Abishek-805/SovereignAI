import json

import pytest

from backend.contracts import WorkbenchError
from backend.model import LocalModel


def model_with_candidate(monkeypatch,candidate,finish='stop'):
    model=LocalModel(verify_semantics=True)
    calls=[]
    def request(method,path,**kwargs):
        payload=kwargs['json'];calls.append(payload)
        name=payload.get('response_format',{}).get('json_schema',{}).get('name')
        content=json.dumps({'verdict':'accept','issues':[]}) if name=='semantic_review' else candidate if name=='query_measure' else 'Interpret the user request using selected sources.'
        return {'choices':[{'finish_reason':finish if name=='query_measure' else 'stop','message':{'content':content}}]}
    monkeypatch.setattr(model,'_request',request)
    return model,calls


def test_valid_optional_table_abstention_defers_without_review(monkeypatch):
    model,calls=model_with_candidate(monkeypatch,'{"operation":"none"}')
    query=model.plan_table_query('Who supervises inspections?',[
        {'id':'T1','sheet':'Students','columns':['ID','Score']}])
    assert query=={'operation':'none'} and len(calls)==2
    assert not any(call.get('response_format',{}).get('json_schema',{}).get('name')=='semantic_review' for call in calls)


def test_nonempty_table_plan_retains_semantic_review(monkeypatch):
    intent={'operation':'percentage','outcome':'pass','threshold':None,'result_values':['PASS'],
        'entity_values':[],'scope':'all','assessments':[],'followup':False}
    model,calls=model_with_candidate(monkeypatch,json.dumps(intent))
    query=model.plan_table_query('Pass percentage',[
        {'id':'T1','sheet':'Students','columns':['ID','Result']}])
    assert query['_measure']['operation']=='percentage'
    assert any(call.get('response_format',{}).get('json_schema',{}).get('name')=='semantic_review' for call in calls)


@pytest.mark.parametrize('candidate,finish',[('not JSON','stop'),('{"operation":"none"}','length')])
def test_invalid_abstention_does_not_bypass_validation(monkeypatch,candidate,finish):
    model,calls=model_with_candidate(monkeypatch,candidate,finish)
    with pytest.raises(WorkbenchError) as error:
        model.plan_table_query('Who supervises inspections?',[
            {'id':'T1','sheet':'Students','columns':['ID','Score']}])
    assert error.value.code=='generation_format'
    if finish=='stop':
        assert any(call.get('response_format',{}).get('json_schema',{}).get('name')=='semantic_review' for call in calls)
