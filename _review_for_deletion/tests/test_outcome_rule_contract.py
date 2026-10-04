import pytest

from rag.answer import _query_presentation
from rag.tables import compile_outcome_query, execute_query, population_binding_catalog


def test_comparison_calculates_each_literal_cohort_over_its_own_denominator():
    table={'name':'Results','columns':['Identity','Exam A','Exam B'],'records':[
        {'Identity':'YEARRED01','Exam A':25,'Exam B':24},
        {'Identity':'YEARRED02','Exam A':'AB','Exam B':26},
        {'Identity':'YEARBLUE01','Exam A':30,'Exam B':20}]}
    intent={'operation':'percentage','outcome':'pass','rule_outcome':'fail',
        'threshold':25,'threshold_operator':'lt','score_columns':['Exam A','Exam B'],
        'entity_values':['red','blue'],'group_entities':True,'scope':'all'}
    plan=compile_outcome_query(intent,{'T1':({'document_id':'d'},table)},
        'Compare red and blue passing percentages; below 25 fails')
    plans=[plan,*plan['additional_queries']]
    assert [p['cohort'] for p in plans]==['red','blue']
    results=[execute_query(table,{**p,'operation':plan['operation']})['summaries'] for p in plans]
    assert [row['total'] for row in results[0]]==[2,2]
    assert [row['percentage'] for row in results[0]]==[50,50]
    assert [row['percentage'] for row in results[1]]==[100,0]


def test_comparison_rejects_lost_group():
    from backend.contracts import WorkbenchError
    with pytest.raises(WorkbenchError,match='every requested group'):
        compile_outcome_query({'entity_values':['red'],'group_entities':True},{},'Compare red and blue')


def test_identity_field_disambiguates_groups_from_matching_names():
    table={'name':'Results','columns':['ID','Name','Score'],'records':[
        {'ID':'YEARRED01','Name':'Blue','Score':25},
        {'ID':'YEARBLUE01','Name':'Red','Score':24}]}
    intent={'operation':'percentage','outcome':'pass','rule_outcome':'pass',
        'threshold':25,'threshold_operator':'gte','score_columns':['Score'],
        'entity_values':['red','blue'],'group_entities':True,'entity_column':'ID'}
    plan=compile_outcome_query(intent,{'T1':({'document_id':'d'},table)},
        'Compare red and blue with threshold 25')
    assert plan['filters']==[{'column':'ID','operator':'contains','value':'red'}]
    assert execute_query(table,plan)['summaries'][0]['percentage']==100


def test_population_binding_catalog_uses_actual_matching_records():
    table={'name':'Results','columns':['ID','Email'],'records':[
        {'ID':'RED01','Email':'blue@example.com'},
        {'ID':'RED02','Email':'red@example.com'},
        {'ID':'BLUE01','Email':'red@example.com'}]}
    candidates=population_binding_catalog({'T1':({'document_id':'d'},table)},['red','blue'])
    by_column={candidate['column']:candidate for candidate in candidates}
    assert by_column['ID']['matching_records']=={'red':2,'blue':1}
    assert by_column['ID']['examples']=={'red':['RED01','RED02'],'blue':['BLUE01']}
    assert by_column['Email']['matching_records']=={'red':2,'blue':1}


def test_executor_rendering_numbers_are_supported_but_added_claims_are_not():
    from rag.answer import _unsupported_numbers
    sources=[{'label':'S1','text':'Original scores 24 and 25.',
        'query_result':{'table':'Exam','operation':'percentage','scanned_rows':2,'matched_rows':2,
            'requested_outcome':'pass','summaries':[{'column':'Exam','passed':1,'total':2,'percentage':50}]}}]
    rendered=_query_presentation(sources)
    assert _unsupported_numbers(rendered,sources)==[]
    assert '999' in _unsupported_numbers(rendered+'\n\nAn additional 999 passed [S1].',sources)


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
