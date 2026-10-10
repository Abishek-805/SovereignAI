from types import SimpleNamespace
import threading
import pytest
from rag.model_routing import ACTIVE_RAG,rag_workflow
from backend.model import LocalModel
from backend.service import Workbench
from backend.contracts import WorkbenchError
from router.model_registry import ModelRegistry


def workbench():
    wb=Workbench.__new__(Workbench)
    spec=SimpleNamespace(identifier='google/gemma-4-E2B-it',alias='sovereign-rag',context=16384)
    wb.registry=SimpleNamespace(specs={'rag':spec},installed=lambda s:True,launch_args=lambda key:['gemma'],
        _runtime_profile_matches=lambda args:True,acquire_lease=lambda *a,**k:{'selected_model_id':spec.identifier})
    return wb


@pytest.mark.parametrize('stage',['plan_task','refine_retrieval','plan_table_query','bind_population_column','evidence_handoff','complete','assess_evidence','repair'])
def test_shared_call_boundary_overrides_other_model_and_verifies_runtime(stage):
    wb=workbench();model=LocalModel();seen=[]
    model._request_raw=lambda method,path,**kwargs:seen.append(kwargs['json']) or {'choices':[{'message':{'content':'{}'},'finish_reason':'stop'}],'usage':{'total_tokens':3}}
    token=ACTIVE_RAG.set({'workbench':wb,'stage':stage})
    try:model._request('POST','/v1/chat/completions',json={'model':'sovereign-code','messages':[{'role':'user','content':'question'}],'max_tokens':32})
    finally:ACTIVE_RAG.reset(token);model.close()
    assert seen[0]['model']=='sovereign-rag'


def test_wrong_or_missing_rag_worker_cannot_fallback():
    wb=workbench();wb.registry._runtime_profile_matches=lambda args:False
    with pytest.raises(WorkbenchError,match='does not match'):wb._rag_lease()
    wb.registry.specs={}
    with pytest.raises(WorkbenchError,match='no alternate'):wb._rag_lease()


def test_rag_context_overflow_and_cancellation_precede_generation():
    wb=workbench()
    with pytest.raises(WorkbenchError,match='exceeds'):wb._rag_lease(16385)
    model=LocalModel();event=threading.Event();event.set()
    model._request_raw=lambda *a,**k:pytest.fail('cancelled request reached runtime')
    token=ACTIVE_RAG.set({'workbench':wb,'stage':'complete'})
    try:
        with model.cancel_scope(event),pytest.raises(WorkbenchError,match='stopped'):
            model._request('POST','/v1/chat/completions',json={'messages':[],'max_tokens':32})
    finally:ACTIVE_RAG.reset(token);model.close()


def test_non_rag_payload_unchanged():
    model=LocalModel();seen=[]
    model._request_raw=lambda *a,**k:seen.append(k['json']) or {'choices':[{'message':{'content':'{}'}}]}
    model._request('POST','/v1/chat/completions',json={'model':'sovereign-code','messages':[],'max_tokens':32})
    assert seen[0]['model']=='sovereign-code';model.close()


def test_installed_rag_profile_does_not_replace_nonrag_model_map():
    registry=ModelRegistry()
    if 'rag' not in registry.specs:pytest.skip('Gemma not installed')
    assert registry.specs['rag'].identifier=='google/gemma-4-E2B-it'
    assert registry.models['google/gemma-4-E2B-it'].alias=='sovereign-text-light'
    assert registry.specs['text'].identifier=='Qwen/Qwen3.5-4B'


def test_workflow_scope_restored_after_failure_without_model_load():
    class Subject:
        @rag_workflow
        def ask(self,question,document_ids=None,force_documents=False):
            assert ACTIVE_RAG.get() is not None
            raise ValueError('no model called')
    with pytest.raises(ValueError):Subject().ask('source question',['doc'])
    assert ACTIVE_RAG.get() is None


def test_sentence_punctuation_after_multiple_filenames_preserves_authorized_scope():
    from rag.retrieve import document_scope_for_question
    docs=[{'document_id':'a','display_name':'equipment-v1.txt'},{'document_id':'b','display_name':'equipment-v2.txt'}]
    assert document_scope_for_question(docs,'Compare equipment-v1.txt and equipment-v2.txt.',['a','b'])==['a','b']
    with pytest.raises(WorkbenchError):document_scope_for_question(docs,'Compare equipment-v1.txt and equipment-v2.txt.',['a'])


def test_document_question_cannot_be_redirected_to_nonexistent_code_project():
    wb=Workbench.__new__(Workbench);wb.model=SimpleNamespace(plan_task=lambda *a:{'action':'inspect_code','response':'','target':''})
    wb._coding_request=lambda *a,**k:SimpleNamespace(features={})
    wb._lease=lambda *a,**k:'rag';wb._cpu_readonly_plan=lambda *a,**k:None
    plan=wb._request_plan('Why is that interval required in procedure.txt?',[{'display_name':'procedure.txt'}],[])
    assert plan['action']=='search_documents'


def test_related_requirement_does_not_satisfy_a_why_question():
    from rag.grounding import assess
    source={'label':'S1','document_id':'d','version_hash':'v','chunk_id':'c','line_start':1,'text':'The location C-17 is mandatory.'}
    review={'claims':[{'text':'The location C-17 is mandatory.','support':'FACT_SUPPORTED','quotes':[{'label':'S1','text':source['text']}]}],
        'missing_evidence':[],'rationale_supported':False,'sufficient_for_answer':True}
    model=SimpleNamespace(assess_evidence=lambda *a:review)
    result=assess('Why is that location required?',{'answer':'The location C-17 is mandatory. [S1]'},[source],model)
    assert not result['passed'] and not result['quoted_answer_supported']


def test_handoff_uses_existing_json_prefix_grammar_and_keeps_query_bounds():
    import json
    model=LocalModel();seen=[]
    model._request=lambda *a,**k:seen.append(k['json']) or {'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'reuse':True,'query':'same source'})}}]}
    assert model.evidence_handoff('Why?',[],[])['reuse']
    assert seen[0]['max_tokens']==384 and 'grammar' in seen[0] and 'response_format' not in seen[0]
    model._request=lambda *a,**k:{'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'reuse':True,'query':'x'*2001})}}]}
    with pytest.raises(WorkbenchError):model.evidence_handoff('Why?',[],[])
    model.close()


def test_preview_ids_cannot_define_an_unrequested_population():
    from rag.tables import _table,bind_selection_request,execute_query
    table=_table('Source',[['Asset','Score'],['AX-001',14],['AX-002',30]])
    plan={'operation':'select','columns':['Score'],'filters':[{'column':'Asset','operator':'in','value':['AX-001','AX-002']}]}
    with pytest.raises(WorkbenchError,match='absent from your request'):
        bind_selection_request(plan,table,'Which warranty period applies?')
    bound=bind_selection_request(plan,table,'Show the score of AX-001')
    assert execute_query(table,bound)['records']==[{'Score':14}]


def test_indexed_documents_do_not_turn_general_chat_into_rag():
    class Subject:
        def documents(self):return [{'document_id':'d','display_name':'manual.txt'}]
        @rag_workflow
        def ask(self,question,document_ids=None):return ACTIVE_RAG.get() is not None
    assert Subject().ask('Tell me about space') is False
    assert Subject().ask('What does manual.txt say?') is True
    assert Subject().ask(None) is False


def test_existing_task_plan_carries_semantic_evidence_operation():
    import json
    model=LocalModel();captured=[]
    model.count_messages=lambda *a:10
    def request(method,path,**kwargs):
        if method=='GET':return {'default_generation_settings':{'n_ctx':16384}}
        captured.append(kwargs['json'])
        return {'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'action':'search_documents','response':'','evidence_mode':'passages'})}}]}
    model._request=request
    try:
        plan=model.plan_task('Describe the institution',[{'name':'reference.txt'},{'name':'scores.csv'}],[])
        assert plan['evidence_mode']=='passages'
        assert 'evidence' in captured[0]['grammar'] and 'knowledge ::=' in captured[0]['grammar']
        assert 'Connected tables and past statistics do not authorize' in captured[0]['messages'][0]['content']
    finally:model.close()
