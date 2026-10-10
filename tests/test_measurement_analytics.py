import hashlib
from types import SimpleNamespace
import pytest
from rag.analytics import compile_measurements
from rag.tables import _table,execute_query
from backend.contracts import WorkbenchError,Chunk
from backend.service import Workbench


def source(rows=None):
    table=_table('Measurements',rows or [['Key','Year','Phone','WAT 1','WAT 2','CAT 1','WAT 3'],
        ['24ALR056',2026,999,7,6,12.5,'AB'],['24ALR055',2025,123,20,10,5,None]])
    return {'T1':({'document_id':'synthetic','active_hash':'v1'},table)}


def result(question,available=None,prior=None):
    available=available or source()
    plan=compile_measurements(question,available,prior=prior)
    return execute_query(available[plan['table']][1],plan)


def test_overall_average_is_one_cell_mean_with_metadata_excluded():
    query=result('24ALR056 overall average')
    group=query['measurements'][0]
    assert group['value']==8.5 and group['denominator']==3 and group['sum']==25.5
    assert [c['measurement'] for c in group['included']]==['WAT 1','WAT 2','CAT 1']
    assert group['excluded'][0]['raw']=='AB'
    assert [c['row'] for c in group['included']]==[2,2,2]


def test_missing_exact_identifier_does_not_fall_through_to_measurement_planner():
    with pytest.raises(WorkbenchError,match='No exact matching record') as error:
        compile_measurements('Give total scores of 99ZZZ999',source())
    assert error.value.code=='needs_input'
    assert 'No measurement result was inferred' in str(error.value)
    assert compile_measurements('Tell me about the institution',source()) is None


def test_explicit_zero_policy_changes_denominator_only_when_requested():
    assert result('24ALR056 overall average AB as zero')['measurements'][0]['value']==6.375
    assert result('24ALR056 overall average')['missing_policy']=='exclude'


@pytest.mark.parametrize('question,expected',[
    ('24ALR056 best five marks',[12.5,7,6]),
    ('24ALR056 lowest five marks',[6,7,12.5]),
    ('24ALR056 highest mark',[12.5])])
def test_ranking_measurements_before_limit(question,expected):
    query=result(question)
    assert [c['value'] for c in query['measurements'][0]['selected']]==expected
    assert query['measurements'][0]['available_numeric']==3


def test_top_entities_is_distinct_from_top_measurements():
    query=result('best five students by WAT 1')
    assert query['operation']=='select' and [r['Key'] for r in query['records']]==['24ALR055','24ALR056']


@pytest.mark.parametrize('rows',[
    [['Serial','Response time'],['EQ-001',12],['EQ-002',3]],
    [['Invoice','Amount'],['INV-001',12],['INV-002',3]]])
def test_same_rank_operation_over_unrelated_schemas(rows):
    available=source(rows)
    query=result('top two records by '+rows[0][1],available)
    assert [r[rows[0][1]] for r in query['records']]==[12,3]


def test_long_and_wide_average_agree():
    available=source([['Key','Measurement','Score'],['24ALR056','Alpha',7],['24ALR056','Beta',6],
                      ['24ALR056','Gamma',12.5],['24ALR056','Delta','AB']])
    query=result('24ALR056 overall avg',available)
    assert query['measurements'][0]['value']==8.5
    assert [c['row'] for c in query['measurements'][0]['included']]==[2,3,4]


def test_duplicate_measurement_requires_rule():
    available=source([['Key','Measurement','Score'],['24ALR056','Alpha',7],['24ALR056','Alpha',6]])
    with pytest.raises(WorkbenchError,match='Repeated'):result('24ALR056 overall avg',available)


def test_units_and_unsupported_weights_do_not_invent_grade():
    available=source([['Key','Score (50M)','Total (100M)'],['24ALR056',7,6]])
    with pytest.raises(WorkbenchError,match='scales'):result('24ALR056 overall avg',available)
    with pytest.raises(WorkbenchError,match='policy'):result('24ALR056 weighted average')


def test_numeric_count_and_missing_status_are_not_official_attendance():
    assert result('24ALR056 attempted tests')['measurements'][0]['value']==3
    assert result('24ALR056 which tests did he miss')['measurements'][0]['selected'][0]['raw']=='AB'


def test_pronoun_cannot_inherit_assistant_prose_or_multiple_entities():
    with pytest.raises(WorkbenchError,match='verified'):compile_measurements('his overall avg',source(),['Assistant: 24ALR056'])
    prior={'requested_entities':['24ALR056','24ALR055'],'document_id':'synthetic','table':'Measurements','measurement_fields':['WAT 1']}
    with pytest.raises(WorkbenchError,match='multiple'):compile_measurements('his overall avg',source(),prior=prior)


@pytest.fixture
def wb(tmp_path):
    path=tmp_path/'results.csv';path.write_text('Key,WAT 1,WAT 2,CAT 1,WAT 3\n24ALR056,7,6,12.5,AB\n')
    version=hashlib.sha256(path.read_bytes()).hexdigest()
    doc={'document_id':'synthetic','active_hash':version,'display_name':'results.csv','source_extension':'.csv','chunk_count':1}
    chunk=Chunk('schema','synthetic',version,'results.csv','schema',None,1,2,retrieval_kind='schema')
    workbench=Workbench.__new__(Workbench)
    workbench.settings=SimpleNamespace(data_dir=tmp_path,context=16384,output_tokens=1024,safety_tokens=64)
    workbench.documents=lambda:[doc];workbench.document_original=lambda identity:path
    workbench.store=SimpleNamespace(active_chunks=lambda scope:[(chunk,None)],current=lambda identity:doc,documents=lambda:[doc],get_chunk=lambda key:chunk)
    def forbidden(*args,**kwargs):raise AssertionError('Deterministic calculation invoked model')
    workbench.model=SimpleNamespace(count_messages=forbidden,complete=forbidden)
    return workbench


def test_followup_uses_saved_verified_receipt_and_current_evidence(wb):
    first=wb._exact_document_lookup('24ALR056 all test results in results.csv',['synthetic'])
    assert first is not None
    second=wb._exact_document_lookup('tell me his overall avg',['synthetic'],['User: '+first['original_question']],evidence_ids=['schema'])
    assert second['table_query']['measurements'][0]['value']==8.5
    assert second['counters']['model_calls']==0 and 'Formula: 25.5 / 3' in second['answer']
    third=wb._exact_document_lookup('all his test results',['synthetic'],['User: '+second['original_question']],evidence_ids=['schema'])
    assert third['table_query']['records'][0]['WAT 3']=='AB'
    fourth=wb._exact_document_lookup('which tests did he miss?',['synthetic'],['User: '+third['original_question']],evidence_ids=['schema'])
    assert fourth['table_query']['measurements'][0]['selected'][0]['raw']=='AB'


def test_followup_rejects_missing_or_stale_evidence(wb):
    first=wb._exact_document_lookup('24ALR056 all test results in results.csv',['synthetic'])
    with pytest.raises(WorkbenchError,match='verified'):wb._exact_document_lookup('his avg',['synthetic'],['User: '+first['original_question']],evidence_ids=[])
    wb.store.documents=lambda:[]
    with pytest.raises(WorkbenchError,match='verified'):wb._exact_document_lookup('his avg',['synthetic'],['User: '+first['original_question']],evidence_ids=['schema'])


def test_actual_identity_precedes_assessment_prefix_guess():
    available=source([['Key','CAT 1'],['CAT056',7]])
    assert result('CAT056 overall avg',available)['measurements'][0]['value']==7


def test_ties_use_source_order_and_non_numeric_entities_do_not_rank():
    available=source([['Key','Score'],['EQ-001',8],['EQ-002','AB'],['EQ-003',8]])
    query=result('top two records by Score',available)
    assert [r['Key'] for r in query['records']]==['EQ-001','EQ-003']


def test_filter_and_compound_operations_are_not_silently_ignored():
    for question in ['24ALR056 best five above 10','24ALR056 overall avg last year','24ALR056 average and highest mark']:
        with pytest.raises(WorkbenchError):result(question)


def test_all_missing_measurements_remain_visible_without_dividing_by_zero():
    available=source([['Key','WAT 1','WAT 2'],['24ALR056','AB',None]])
    group=result('24ALR056 overall avg',available)['measurements'][0]
    assert group['value'] is None and group['denominator']==0 and len(group['excluded'])==2


def test_overall_does_not_silently_drop_unclassified_numeric_field():
    available=source([['Key','Score','Other measurement'],['24ALR056',7,6]])
    with pytest.raises(WorkbenchError,match='partial overall'):
        result('24ALR056 overall avg',available)


def test_long_format_units_must_agree():
    available=source([['Key','Measurement','Score','Unit'],['24ALR056','Latency A',7,'ms'],['24ALR056','Latency B',6,'s']])
    with pytest.raises(WorkbenchError,match='units differ'):result('24ALR056 overall avg',available)


def test_entity_total_uses_source_cells_without_ordering_or_grading_inference():
    query=result('give me total professional skill test of 24alr056')
    assert query['operation']=='measurement_sum'
    group=query['measurements'][0]
    assert group['value']==25.5 and group['denominator']==3 and group['excluded'][0]['raw']=='AB'
    assert all(c['row']==2 for c in group['included'])
    assert 'order_by' not in query
