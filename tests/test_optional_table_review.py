import json

import pytest

from backend.contracts import WorkbenchError
from backend.model import LocalModel
from tests.test_service import service


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


def test_abstract_table_plan_defers_review_to_execution_checks(monkeypatch):
    intent={'operation':'percentage','outcome':'pass','threshold':None,'result_values':['PASS'],
        'entity_values':[],'scope':'all','assessments':[],'followup':False}
    model,calls=model_with_candidate(monkeypatch,json.dumps(intent))
    query=model.plan_table_query('Pass percentage',[
        {'id':'T1','sheet':'Students','columns':['ID','Result']}])
    assert query['_measure']['operation']=='percentage'
    assert len(calls)==2
    assert not any(call.get('response_format',{}).get('json_schema',{}).get('name')=='semantic_review' for call in calls)


@pytest.mark.parametrize('operation,expected',[('count',1),('sum',2.0)])
def test_abstract_plan_executes_complete_source_before_numeric_answer(service,tmp_path,monkeypatch,operation,expected):
    path=tmp_path/'scores.csv';path.write_text('ID,Score\nTEAM01,2\nTEAM02,0\n')
    doc=service.import_file(path)
    model=LocalModel(verify_semantics=True)
    calls=[]
    def request(method,path,**kwargs):
        payload=kwargs['json'];calls.append(payload)
        name=payload.get('response_format',{}).get('json_schema',{}).get('name')
        if name=='semantic_review':
            content=json.dumps({'verdict':'accept','issues':[]})
        elif name=='query_measure':
            content=json.dumps({'operation':operation,'outcome':'other','threshold':None,
                'result_values':[],'entity_values':[],'scope':'one','assessments':[],'followup':False})
        elif name=='table_query':
            content=json.dumps({'table':'T1','operation':operation,
                'columns':['Score'] if operation=='sum' else [],
                'filters':[] if operation=='sum' else [{'column':'Score','operator':'gt','value':'1'}]})
        else:content='Resolve the requested numeric operation without computing it.'
        return {'choices':[{'finish_reason':'stop','message':{'content':content}}]}
    monkeypatch.setattr(model,'_request',request)
    service.model.plan_table_query=model.plan_table_query
    monkeypatch.setattr(model,'count_messages',lambda *args,**kwargs:100)
    monkeypatch.setattr(model,'context_capacity',lambda:8192)
    service.model.output={'status':'answered','answer':f'The result is {expected}. [S1]'}
    result=service.ask('Sum all scores' if operation=='sum' else 'Count scores above 1',
        [doc['document_id']],force_documents=True)
    assert result['table_query']['value']==expected
    assert result['table_query']['scanned_rows']==2
    assert result['status']=='answered'
    # The concrete source-bound plan still retains its own review.
    assert sum(call.get('response_format',{}).get('json_schema',{}).get('name')=='semantic_review' for call in calls)==1
    concrete=next(call for call in calls if call.get('response_format',{}).get('json_schema',{}).get('name')=='table_query')
    branches=concrete['response_format']['json_schema']['schema']['anyOf']
    assert all(branch['properties']['operation']['enum']==[operation] for branch in branches)
    assert all(branch['properties']['table']['enum']==['T1'] for branch in branches)
    # Interpretation uses the real task, rather than few-shot example tasks.
    contexts=[call['messages'] for call in calls if not call.get('response_format')]
    assert len(contexts)==2
    assert contexts[-1][-1]['content']==('Sum all scores' if operation=='sum' else 'Count scores above 1')


def test_source_binding_cannot_downgrade_a_validated_measure(monkeypatch):
    model=LocalModel(verify_semantics=True)
    replies=iter([{'operation':'count','outcome':'other','threshold':None,'result_values':[]},
        {'table':'','operation':'none','columns':[],'filters':[]}])
    monkeypatch.setattr(model,'_planned_completion',lambda *args,**kwargs:{'choices':[
        {'finish_reason':'stop','message':{'content':json.dumps(next(replies))}}]})
    monkeypatch.setattr(model,'count_messages',lambda *args,**kwargs:100)
    monkeypatch.setattr(model,'context_capacity',lambda:8192)
    with pytest.raises(WorkbenchError,match='changed the requested measure') as error:
        model.plan_table_query('Count records',[{'id':'T1','sheet':'Records','columns':['ID']}])
    assert error.value.code=='invalid_query'


@pytest.mark.parametrize('candidate,finish',[('not JSON','stop'),('{"operation":"none"}','length')])
def test_invalid_abstention_does_not_bypass_validation(monkeypatch,candidate,finish):
    model,calls=model_with_candidate(monkeypatch,candidate,finish)
    with pytest.raises(WorkbenchError) as error:
        model.plan_table_query('Who supervises inspections?',[
            {'id':'T1','sheet':'Students','columns':['ID','Score']}])
    assert error.value.code=='generation_format'
    assert len(calls)==2
