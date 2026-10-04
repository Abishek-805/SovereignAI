import json

import pytest

from backend.contracts import WorkbenchError
from backend.model import LocalModel


@pytest.mark.parametrize('target,authorized',[('main.py',True),('other.py',False)])
def test_workspace_plan_review_respects_delegation_but_preserves_target_authority(monkeypatch,target,authorized):
    model=LocalModel(verify_semantics=True)
    calls=[]
    plan={'scope':'existing_files','operations':[{'action':'edit','path':target,
        'reason':'Implement requested function','replacements':[]}]}
    def request(method,path,**kwargs):
        if path=='/props':return {'default_generation_settings':{'n_ctx':16384}}
        payload=kwargs['json'];calls.append(payload)
        name=payload.get('response_format',{}).get('json_schema',{}).get('name')
        if name=='semantic_review':
            policy=payload['messages'][0]['content']
            assert 'replacements [] or omitted replacements delegates implementation' in policy
            assert 'reject unrelated targets' in policy
            evidence=json.loads(payload['messages'][-1]['content'])
            assert json.loads(evidence['candidate'])==plan
            assert json.loads(evidence['request_and_evidence'][-1]['content'])['task']=='Implement double(x) in main.py only'
            value={'verdict':'accept','issues':[]} if authorized else {
                'verdict':'clarify','issues':['User authorizes main.py only; candidate edits unrelated other.py.']}
        elif payload.get('grammar'):value=plan
        else:value='Implement double(x) in main.py only; preserve unrelated files.'
        return {'choices':[{'finish_reason':'stop','message':{'content':json.dumps(value) if isinstance(value,dict) else value}}]}
    monkeypatch.setattr(model,'_request',request)
    monkeypatch.setattr(model,'count_messages',lambda *args,**kwargs:100)
    if authorized:
        result=model.plan_workspace_edit('Implement double(x) in main.py only',{'main.py':'def double(x): return None'},[],'main.py')
        assert result==plan
    else:
        with pytest.raises(WorkbenchError) as error:
            model.plan_workspace_edit('Implement double(x) in main.py only',{'main.py':'def double(x): return None','other.py':'unrelated'},[],'main.py')
        assert error.value.code in {'semantic_uncertainty','needs_input'}
    assert len(calls)==3
