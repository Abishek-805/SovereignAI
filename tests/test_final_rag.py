import pytest
from backend.contracts import WorkbenchError
from rag.retrieve import document_scope_for_question
from rag.tables import execute_query
from rag.handoff import active_evidence
from backend.contracts import Chunk
from rag.answer import _validate_result
from backend.model import LocalModel
from rag.tables import compile_outcome_query
import json


def test_scope_requires_document_reference():
    docs=[{'document_id':'a','display_name':'conflict.txt'}, {'document_id':'b','display_name':'policy.txt'}]
    assert document_scope_for_question(docs,'Explain the conflict',['a','b'])==['a','b']
    assert document_scope_for_question(docs,'Explain conflict.txt',['a','b'])==['a']
    assert document_scope_for_question(docs,'Read the conflict document',['a','b'])==['a']
    with pytest.raises(WorkbenchError,match='unavailable'):
        document_scope_for_question(docs,'Read conflict.txt',['b'])


def test_order_limit_uses_complete_filtered_source():
    table={'name':'Scores','columns':['ID','Score'],'records':[{'ID':str(i),'Score':i} for i in range(60)]}
    result=execute_query(table,{'operation':'select','columns':['ID','Score'],'filters':[{'column':'Score','operator':'gte','value':25}],
        'order_by':[{'column':'Score','direction':'desc'}],'limit':3})
    assert [r['Score'] for r in result['records']]==[59,58,57]
    assert result['matched_rows']==35 and not result['truncated']
    with pytest.raises(WorkbenchError):
        execute_query(table,{'operation':'select','order_by':[{'column':'Unknown','direction':'desc'}]})
    with pytest.raises(WorkbenchError):
        execute_query(table,{'operation':'select','limit':True})


def test_filtered_grouped_sum_sorted_before_limit():
    table={'name':'Scores','columns':['Cohort','Score','Status'],'records':[
        {'Cohort':'A','Score':20,'Status':'Fail'}, {'Cohort':'A','Score':30,'Status':'Pass'},
        {'Cohort':'B','Score':40,'Status':'Pass'}, {'Cohort':'B','Score':35,'Status':'Pass'}]}
    result=execute_query(table,{'operation':'aggregate','filters':[{'column':'Status','operator':'eq','value':'Pass'}],
        'metrics':[{'operation':'sum','column':'Score'}],'group_by':['Cohort'],
        'order_by':[{'column':'Score','direction':'desc'}],'limit':1})
    assert result['groups']==[{'keys':{'Cohort':'B'},'metrics':[{'operation':'sum','column':'Score','value':75,'numeric_rows':2}]}]
    assert result['matched_rows']==3


def test_handoff_rejects_stale_and_out_of_scope_chunks():
    class Store:
        def documents(self):return [{'document_id':'a','active_hash':'new'},{'document_id':'b','active_hash':'v1'}]
        def get_chunk(self,key):
            if key=='gone':raise WorkbenchError('unknown_source','removed')
            return Chunk(key,'b' if key=='other' else 'a','old' if key=='stale' else 'v1' if key=='other' else 'new','doc','text',1,1,1)
    assert [c.chunk_id for c in active_evidence(Store(),['stale','other','gone','valid','valid'],['a'])]==['valid']


def test_citation_validation_uses_only_supplied_evidence():
    sources=[{'label':'S1','text':'Interval is 12 days.'}]
    checks=_validate_result({'status':'answered','answer':'Interval is 12 days [S2].'},sources,0)
    assert not checks['citation_ids_valid'] and checks['unknown_citations']==['S2']


@pytest.mark.parametrize('operation,expected',[('count',2),('sum',70),('average',35),('min',30),('max',40)])
def test_complete_filtered_numeric_operations(operation,expected):
    table={'name':'Metrics','columns':['Score','Status'],'records':[
        {'Score':10,'Status':'Fail'},{'Score':30,'Status':'Pass'},{'Score':40,'Status':'Pass'}]}
    result=execute_query(table,{'operation':operation,'columns':['Score'],
        'filters':[{'column':'Status','operator':'eq','value':'Pass'}]})
    assert result['value']==expected


def test_outcome_count_preserves_predicate_when_model_also_supplies_metric():
    model=LocalModel(verify_semantics=True)
    intent={'operation':'count','outcome':'pass','followup':False,'rule_outcome':'pass','threshold':None,
        'threshold_operator':'none','score_columns':[],'result_values':[],'entity_values':[],
        'entity_column':None,'group_entities':False,'scope':'all','assessments':[],
        'metrics':[{'operation':'count','column':None}],'group_by':[],'order_by':[],'limit':None,'filters':[]}
    resolutions=[]
    def resolve(payload, **kwargs):
        name=payload['response_format']['json_schema']['name']
        if name=='requested_groups':
            resolutions.append(name)
            content={'entity_values':[],'group_entities':False}
        else:
            content=intent
        return {'choices':[{'finish_reason':'stop','message':{'content':json.dumps(content)}}]}
    model._planned_completion=resolve
    table={'name':'Scores','columns':['Status'],'records':[{'Status':'Pass'},{'Status':'Fail'},{'Status':'Pass'}]}
    query=model.plan_table_query('Count students whose Status is Pass',[{'id':'T1','columns':['Status'],'sheet':'Scores'}])
    compiled=compile_outcome_query(query['_measure'],{'T1':({'document_id':'scores'},table)},'Count students whose Status is Pass')
    assert execute_query(table,compiled)['value']==2
    assert resolutions, 'Outcome path must preserve independent population resolution'
    model.close()
