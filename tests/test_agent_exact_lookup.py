import pytest
from rag.identifiers import resolve_identifiers,compile_exact_lookup
from rag.tables import _table,execute_query,load_tables,_load
from backend.contracts import WorkbenchError

FIRST='24ALR056 and 24ALR055 professional skill training test results?'
SECOND='24ALR056 and 55 professional skill training test results?'

def available(rows=None):
    return {'T1':({'document_id':'synthetic','version_hash':'v1'},_table('Skills',rows or [
        ['Communication','Register Number','Professional Skills'],
        [78,'24ALR056',85],[90,'24ALR055',70]]))}


def test_numeric_measurements_do_not_become_categorical_filters():
    source=available([['ID','WAT 1','WAT 2'],['24ALR051',25,6],['24ALR052',2,32]])
    plan=compile_exact_lookup('Show 24ALR051 score 6 in WAT 2',source)
    assert plan['filters']==[{'column':'ID','operator':'in','value':['24ALR051']}]
    result=execute_query(source['T1'][1],plan)
    assert result['matched_rows']==1 and result['records'][0]['WAT 2']==6


@pytest.mark.parametrize('word',['Why','reason','rationale','justification'])
def test_rationale_is_not_answered_by_exact_record_lookup(word):
    assert compile_exact_lookup(word+' did 24ALR056 receive 85 in Professional Skills',available()) is None

def test_full_ids_and_context_shorthand():
    source=available()
    for question,history in [(FIRST,[]),(SECOND,['User: '+FIRST,'Assistant: untrusted 24ALR999'])]:
        plan=compile_exact_lookup(question,source,history)
        assert plan['requested_entities']==['24ALR056','24ALR055']
        result=execute_query(source['T1'][1],plan)
        assert [r['Professional Skills'] for r in result['records']]==[85,70]
        assert [r['row'] for r in result['record_locators']]==[2,3]
        assert plan['identity_column']=='Register Number'

@pytest.mark.parametrize('history',[
    [],['Assistant: '+FIRST],['User: '+FIRST,'User: Tell me about space'],
    ['User: 24ALR055 and 99XX055 professional skills results']])
def test_shorthand_does_not_inherit_unrelated_or_assistant(history):
    source=available()
    if history and '99XX055' in history[-1]:
        source['T1'][1]['records'].append({'Register Number':'99XX055','Professional Skills':10})
    resolved=resolve_identifiers(SECOND,source,history)
    assert resolved.canonical==['24ALR056'] and resolved.unresolved==['55']

def test_replacement_not_union():
    plan=compile_exact_lookup('24ALR055 professional skills results',available(),['User: '+FIRST])
    assert plan['requested_entities']==['24ALR055']

def test_missing_id_and_prefix_are_not_fuzzy_matches():
    for value in ['24ALR999','24ALR05']:
        plan=compile_exact_lookup(value+' professional skills results',available())
        result=execute_query(available()['T1'][1],plan)
        assert not result['records'] and result['missing_entities']==[value]

def test_long_format_duplicate_identity_assessment_filter():
    source=available([['ID','Assessment','Score'],['24ALR056','Professional Skills',85],
        ['24ALR056','Communication',78],['24ALR055','Professional Skills',70]])
    plan=compile_exact_lookup(FIRST,source)
    result=execute_query(source['T1'][1],plan)
    assert [r['Score'] for r in result['records']]==[85,70]
    assert [r['row'] for r in result['record_locators']]==[2,4]

def test_zeros_and_punctuation_preserved():
    source=available([['Key','Professional Skills'],['00Ab-056',85],['Ab-056',5]])
    result=execute_query(source['T1'][1],compile_exact_lookup('00Ab-056 professional skills results',source))
    assert result['records']==[{'Key':'00Ab-056','Professional Skills':85}]

@pytest.mark.parametrize('question',['24ALR056 and 25 marks professional skills results',
    'Count 24ALR056 professional skills','24ALR056 passed professional skills'])
def test_numeric_operations_not_shorthand_lookup(question):
    assert '24ALR055' not in resolve_identifiers(question,available(),['User: '+FIRST]).canonical
    if 'Count' in question or 'passed' in question:assert compile_exact_lookup(question,available()) is None

def test_multiple_sources_require_clarification():
    source=available();source['T2']=source['T1']
    with pytest.raises(WorkbenchError,match='multiple source'):compile_exact_lookup(FIRST,source)

def test_cached_reader_invalidates_source_change(tmp_path):
    path=tmp_path/'data.csv';path.write_text('Key,Professional Skills\n24ALR056,85\n')
    first=load_tables(path);before=_load.cache_info().hits
    assert load_tables(path) is first and _load.cache_info().hits==before+1
    path.write_text('Key,Professional Skills\n24ALR056,100\n')
    assert load_tables(path)[0]['records'][0]['Professional Skills']!=first[0]['records'][0]['Professional Skills']

def test_source_named_wide_summary_beats_unrelated_table():
    doc={'document_id':'skills','display_name':'24GCL51 - Professional Skills Training All Marks.xlsx'}
    source={'T1':(doc,_table('Summary',[['Member Id','WAT 1','CAT 1'],['24ALR056',85,70],['24ALR055',80,60]])),
        'T2':(doc,_table('Week',[['Member Id','Total'],['24ALR056',85],['24ALR055',80]])),
        'T3':({'document_id':'unrelated'},_table('Unrelated',[['Name','Group','Score','Result'],['Ann','X',10,'PASS']]))}
    question=FIRST+' in '+doc['display_name']
    plan=compile_exact_lookup(question,source)
    assert plan['table']=='T1' and plan['columns']==['Member Id','WAT 1','CAT 1']
    assert plan['identity_resolution']['canonical']==['24ALR056','24ALR055']

def test_immediate_other_cohort_does_not_authorize_alias():
    assert resolve_identifiers(SECOND,available(),['User: 24ALR055 professional skills results']).unresolved==['55']

def test_numeric_string_id_in_lookup():
    source=available([['Key','Professional Skills'],['000056',85],['56',10]])
    assert execute_query(source['T1'][1],compile_exact_lookup('000056 professional skills results',source))['records']==[{'Key':'000056','Professional Skills':85}]

@pytest.fixture
def lookup_workbench(tmp_path):
    import hashlib
    from types import SimpleNamespace
    from backend.service import Workbench
    from backend.contracts import Chunk
    path=tmp_path/'skills.csv';path.write_text('Register Number,Professional Skills\n24ALR056,85\n24ALR055,70\n')
    version=hashlib.sha256(path.read_bytes()).hexdigest()
    doc={'document_id':'skills','active_hash':version,'display_name':'skills.csv','source_extension':'.csv','chunk_count':1}
    wb=Workbench.__new__(Workbench)
    wb.settings=SimpleNamespace(context=16384,output_tokens=1024,safety_tokens=64)
    wb.documents=lambda:[doc]
    wb.document_original=lambda identity:path
    chunk=Chunk('schema','skills',version,'skills.csv','schema',None,1,3,retrieval_kind='schema')
    wb.store=SimpleNamespace(active_chunks=lambda scope:[(chunk,None)],current=lambda identity:doc)
    def forbidden(*args,**kwargs):raise AssertionError('Exact lookup must not invoke model planning or generation')
    wb.model=SimpleNamespace(count_messages=forbidden,complete=forbidden,plan_table_query=forbidden)
    return wb

def test_complete_lookup_uses_executor_citations_and_no_model(lookup_workbench):
    result=lookup_workbench._exact_document_lookup(FIRST,['skills'])
    assert result['counters']=={'model_calls':0,'tool_calls':1,'retrieval_calls':0,'repair_attempts':0}
    assert result['timings']['total_seconds']<15
    assert result['table_query']['identity_resolution']['canonical']==['24ALR056','24ALR055']
    assert result['checks']['citation_ids_valid'] and result['checks']['numeric_claims_supported']
    assert '24ALR055 | 70' in result['answer']

def test_configured_deadline_rejects_without_model(lookup_workbench,monkeypatch):
    monkeypatch.setenv('SOVEREIGN_EXACT_LOOKUP_SECONDS','0')
    with pytest.raises(WorkbenchError,match='deadline'):lookup_workbench._exact_document_lookup(FIRST,['skills'])

def test_lookup_scope_cannot_be_expanded_by_filename(lookup_workbench):
    with pytest.raises(WorkbenchError):lookup_workbench._exact_document_lookup(FIRST+' in skills.csv',['other'])

def test_source_change_prevents_final_answer(lookup_workbench):
    lookup_workbench.store.current=lambda identity:None
    with pytest.raises(WorkbenchError,match='Source changed'):lookup_workbench._exact_document_lookup(FIRST,['skills'])

@pytest.mark.parametrize('long',[False,True])
def test_assessment_code_does_not_enter_canonical_ids(long):
    source=available([['ID','Assessment','Score'],['24ALR056','WAT1',85]] if long else
        [['ID','WAT 1'],['24ALR056',85]])
    assert resolve_identifiers('24ALR056 WAT1 results',source).canonical==['24ALR056']
    plan=compile_exact_lookup('24ALR056 WAT1 results',source)
    assert plan is not None
    assert execute_query(source['T1'][1],plan)['matched_rows']==1

def test_specific_assessment_code_does_not_select_every_week():
    source=available([['ID','WAT 1','WAT 2'],['24ALR056',85,70]])
    assert compile_exact_lookup('24ALR056 WAT1 results',source)['columns']==['ID','WAT 1']

def test_missing_assessment_is_not_a_missing_student():
    source=available([['ID','WAT 1','WAT 2'],['24ALR056',85,70]])
    with pytest.raises(WorkbenchError,match='assessment is unavailable'):
        compile_exact_lookup('24ALR056 WAT9 results',source)
