import json
from backend.model import LocalModel

def response(content):
    return {'choices':[{'finish_reason':'stop','message':{'content':content}}]}

def test_review_only_contains_current_evidence(monkeypatch):
    model=LocalModel(verify_semantics=True)
    requests=[]
    def request(method,path,**kwargs):
        payload=kwargs['json'];requests.append(payload)
        if payload.get('response_format'):return response(json.dumps({'verdict':'accept','issues':[]}))
        return response('Create the requested text about AI, ML and DL.')
    monkeypatch.setattr(model,'_request',request)
    monkeypatch.setattr(model,'_public_completion',lambda *args:response('AI, ML and DL explanation'))
    model._planned_completion({'messages':[{'role':'user','content':'Create a text document about AI, ML and DL.'}]},task_context={'request':'Create a text document about AI, ML and DL.'})
    review=requests[-1]['messages']
    assert len(review)==2
    assert 'receipt parsing' not in json.dumps(review)
    assert 'AI, ML and DL' in review[-1]['content']

def test_no_duplicate_interpretation_for_unreviewed_stage(monkeypatch):
    model=LocalModel(verify_semantics=True)
    monkeypatch.setattr(model,'_request',lambda *args,**kwargs:(_ for _ in ()).throw(AssertionError('Unnecessary interpretation call')))
    expected=response('Current answer')
    monkeypatch.setattr(model,'_public_completion',lambda *args:expected)
    assert model._planned_completion({'messages':[{'role':'user','content':'Hello'}]},review_candidate=False,public_output='action_answer')==expected

def test_source_candidate_defers_to_real_validation(monkeypatch):
    model=LocalModel(verify_semantics=True)
    requests=[]
    def request(method,path,**kwargs):
        if path=='/props':return {'default_generation_settings':{'n_ctx':8192}}
        requests.append(kwargs['json'])
        return response('{"code":"def value():\\n    return 2\\n"}')
    monkeypatch.setattr(model,'_request',request)
    monkeypatch.setattr(model,'count_messages',lambda *args:100)
    assert 'return 2' in model.complete_code([{'role':'user','content':'Return 2'}])['code']
    assert len(requests)==1
    assert 'response_format' not in requests[0]
