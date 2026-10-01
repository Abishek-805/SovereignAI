import pytest

from rag.answer import _query_presentation
from rag.tables import compile_outcome_query, execute_query


@pytest.mark.parametrize('literal,requested,expected',[
    ('lt','pass',[25,26]),('lte','pass',[26]),
    ('gt','pass',[24,25]),('gte','pass',[24]),
    ('lt','fail',[24]),('lte','fail',[24,25]),
])
def test_literal_failure_rule_is_complemented_once(literal,requested,expected):
    table={'name':'Exam','columns':['ID','Score'],'records':[
        {'ID':'GROUP01','Score':24},{'ID':'GROUP02','Score':25},
        {'ID':'GROUP03','Score':26},{'ID':'GROUP04','Score':'AB'}]}
    intent={'operation':'percentage','outcome':requested,'rule_outcome':'fail',
        'threshold':25,'threshold_operator':literal,'score_columns':['Score']}
    original=dict(intent)
    plan=compile_outcome_query(intent,{'T1':({'document_id':'d'},table)},'Use threshold 25')
    result=execute_query(table,plan)
    assert intent==original  # Conversation state remains the literal rule.
    assert result['summaries'][0]['passed']==len(expected)
    assert result['summaries'][0]['total']==4
    assert result['requested_outcome']==requested
    presentation=_query_presentation([{'label':'S1','query_result':result}])
    assert ('Passed' if requested=='pass' else 'Failed') in presentation


def test_arbitrary_percentage_is_not_labelled_passed():
    query={'table':'Exam','operation':'percentage','scanned_rows':2,'matched_rows':2,
        'summaries':[{'column':'Category','passed':1,'total':2,'percentage':50}]}
    rendered=_query_presentation([{'label':'S1','query_result':query}])
    assert 'Matched' in rendered and 'Passed' not in rendered


def test_followup_does_not_infer_unrelated_historical_cohorts():
    table={'name':'Exam','columns':['ID','Score'],'records':[
        {'ID':'OLD01','Score':40},{'ID':'TEAM01','Score':25},{'ID':'TEAM02','Score':24}]}
    intent={'operation':'percentage','outcome':'pass','rule_outcome':'fail',
        'threshold':25,'threshold_operator':'lt','score_columns':['Score'],
        'entity_values':['TEAM'],'followup':True}
    plan=compile_outcome_query(intent,{'T1':({'document_id':'d'},table)},
        'Below 25 fails; show the same report',[
            'user: Look up OLD01','user: Pass percentage for TEAM'])
    result=execute_query(table,plan)
    assert result['matched_rows']==2
    assert result['summaries'][0]['percentage']==50.0
