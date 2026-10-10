import json
import pytest
from backend.model import LocalModel
from backend.contracts import WorkbenchError
from rag.grounding import draft_claims,assess


def test_claims_preserve_conjunctions_numbers_urls_and_long_tail():
    text='It is affiliated and approved. [S1]\nCost is 12.5 units. Visit https://example.org/info. [S2]'
    claims=draft_claims(text)
    assert claims[0]['text']=='It is affiliated and approved. [S1]'
    assert all(c['text'] in text for c in claims)
    long='\n\n'.join(f'Fact {i}. [S1]' for i in range(30))
    assert len(draft_claims(long))==24
    assert draft_claims(long)[-1]['text'] in long and 'Fact 29.' in draft_claims(long)[-1]['text']


@pytest.mark.parametrize('ids',[['C1'],[],['C1','C1'],['C99']])
def test_assessor_binds_ids_and_rejects_missing_duplicate_or_unknown(ids):
    model=LocalModel();seen=[]
    source={'label':'S1','document_id':'d','version_hash':'v','chunk_id':'c','line_start':1,
        'text':'It is affiliated and approved.'}
    def request(method,path,**kwargs):
        if method=='GET':return {'default_generation_settings':{'n_ctx':16384}}
        seen.append(kwargs['json'])
        return {'choices':[{'finish_reason':'stop','message':{'content':json.dumps({
            'claims':({i:{'support':'FACT_SUPPORTED','quotes':[{'span_id':'S1.P1'}]} for i in ids} if len(set(ids))==len(ids) else ids),
            'missing_evidence':[],'rationale_supported':False,'sufficient_for_answer':True})}}]}
    model._request=request;model.count_messages=lambda *a:10
    from backend.jobs import Job
    job=Job('agent')
    try:
        if ids==['C1']:
            with model.job_scope(job):
                checked=assess('Give an overview',{'answer':source['text']+' [S1]'},[source],model)
            assert job.stage=='Verifying sourced answer'
            assert checked['passed'] and checked['claim_coverage']
            assert checked['supported_claims'][0]['text']==source['text']+' [S1]'
        else:
            with pytest.raises(WorkbenchError) as error:model.assess_evidence('Overview',{'answer':source['text']+' [S1]'},[source])
            assert error.value.code=='generation_format'
            assert 'draft was withheld' in str(error.value) and 'same selected documents' in str(error.value)
            assert 'does not mean' in str(error.value)
    finally:model.close()


@pytest.mark.parametrize('quote,expected',[
    ('**Name:** Example Institute\n1. Physics\n2. Chemistry', True),
    ('Name: Example Institute\n1. Physics\n2. Chemistry', False),
    ('Example Institute offers Physics and Chemistry', False),
])
def test_markdown_evidence_still_requires_exact_quote(quote, expected):
    source={'label':'S1','document_id':'d','version_hash':'v','chunk_id':'c','line_start':1,
            'text':'**Name:** Example Institute\n1. Physics\n2. Chemistry'}
    answer='Example Institute lists Physics and Chemistry [S1].'
    class Review:
        def assess_evidence(self,*args):
            return {'claims':[{'id':'C1','text':answer,'support':'FACT_SUPPORTED',
                               'quotes':[{'label':'S1','text':quote}]}],
                    'missing_evidence':[], 'rationale_supported':False,'sufficient_for_answer':True}
    assert assess('Give an overview',{'answer':answer},[source],Review())['passed'] is expected


@pytest.mark.parametrize('reference',[{'span_id':'S99.P1'},{'span_id':'S1.P99'},
                                    {'label':'S1','text':'a fabricated quotation'}])
def test_assessor_rejects_unbound_source_span(reference):
    model=LocalModel()
    source={'label':'S1','text':'**Name:** Example Institute\n\n1. Physics\n2. Chemistry'}
    def request(method,path,**kwargs):
        if method=='GET':return {'default_generation_settings':{'n_ctx':16384}}
        return {'choices':[{'finish_reason':'stop','message':{'content':json.dumps({
            'claims':{'C1':{'support':'FACT_SUPPORTED','quotes':[reference]}},
            'missing_evidence':[],'rationale_supported':False,'sufficient_for_answer':True})}}]}
    model._request=request;model.count_messages=lambda *a:10
    try:
        with pytest.raises(WorkbenchError) as error:
            model.assess_evidence('Overview',{'answer':'Example Institute [S1].'},[source])
        assert error.value.code=='generation_format'
    finally:model.close()


def test_source_spans_materialize_original_markdown_and_line_breaks():
    model=LocalModel();seen=[]
    source={'label':'S1','text':'**Name:** Example Institute\n\n1. Physics\n2. Chemistry'}
    def request(method,path,**kwargs):
        if method=='GET':return {'default_generation_settings':{'n_ctx':16384}}
        seen.append(json.loads(kwargs['json']['messages'][-1]['content']))
        return {'choices':[{'finish_reason':'stop','message':{'content':json.dumps({
            'claims':{'C1':{'support':'FACT_SUPPORTED','quotes':[{'span_id':'S1.P2'}]}},
            'missing_evidence':[],'rationale_supported':False,'sufficient_for_answer':True})}}]}
    model._request=request;model.count_messages=lambda *a:10
    try:
        review=model.assess_evidence('Overview',{'answer':'Physics and Chemistry [S1].'},[source])
        assert review['claims'][0]['quotes']==[{'label':'S1','text':'1. Physics\n2. Chemistry'}]
        assert all(span['text'] in source['text'] for span in seen[0]['evidence'])
    finally:model.close()


def test_every_draft_claim_is_required_by_the_runtime_schema():
    model=LocalModel();seen=[]
    def request(method,path,**kwargs):
        if method=='GET':return {'default_generation_settings':{'n_ctx':16384}}
        seen.append(kwargs['json']['response_format']['json_schema']['schema'])
        return {'choices':[{'finish_reason':'stop','message':{'content':json.dumps({
            'claims':{'C1':{'support':'FACT_SUPPORTED','quotes':[{'span_id':'S1.P1'}]}},
            'missing_evidence':[],'rationale_supported':False,'sufficient_for_answer':True})}}]}
    model._request=request;model.count_messages=lambda *a:10
    try:
        with pytest.raises(WorkbenchError):
            model.assess_evidence('Overview',{'answer':'Physics is offered. [S1]\nChemistry is offered. [S1]'},
                                  [{'label':'S1','text':'Physics and Chemistry are offered.'}])
        assert seen[0]['properties']['claims']['required']==['C1','C2']
        assert seen[0]['properties']['claims']['additionalProperties'] is False
    finally:model.close()
