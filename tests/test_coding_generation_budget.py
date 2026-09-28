import json

import httpx
import pytest

from backend.contracts import WorkbenchError
from backend.model import CODE_GRAMMAR, WORKSPACE_PLAN_GRAMMAR, LocalModel


@pytest.mark.parametrize('kind', ['source', 'plan'])
def test_coding_template_budget_matches_nonthinking_generation(kind):
    templates=[]
    generated=[]
    def handler(request):
        if request.url.path=='/props':
            return httpx.Response(200,json={'default_generation_settings':{'n_ctx':4096}})
        payload=json.loads(request.content)
        if request.url.path=='/apply-template':
            templates.append(payload)
            return httpx.Response(200,json={'prompt':'actual nonthinking template'})
        if request.url.path=='/tokenize':
            return httpx.Response(200,json={'tokens':[1,2,3]})
        generated.append(payload)
        content=({'code':'def divide(a, b):\n    return a / b\n'} if kind=='source' else
                 {'scope':'new_files','operations':[{'action':'create','path':'division.py','reason':'Requested standalone program','replacements':[]}]})
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':json.dumps(content)}}]})
    model=LocalModel(transport=httpx.MockTransport(handler))
    try:
        if kind=='source':model.complete_code([{'role':'user','content':'Create division'}])
        else:model.plan_workspace_edit('Create division',{'other.py':'keep'},[],None)
    finally:model.close()
    assert templates==generated
    assert generated[0]['grammar']==(CODE_GRAMMAR if kind=='source' else WORKSPACE_PLAN_GRAMMAR)
    assert generated[0]['chat_template_kwargs']=={'enable_thinking':False}
    assert 'response_format' not in generated[0]


@pytest.mark.parametrize('kind', ['source', 'plan'])
def test_truncated_coding_generation_remains_failure(kind):
    def handler(request):
        if request.url.path=='/props':return httpx.Response(200,json={'default_generation_settings':{'n_ctx':4096}})
        if request.url.path=='/apply-template':return httpx.Response(200,json={'prompt':'formatted'})
        if request.url.path=='/tokenize':return httpx.Response(200,json={'tokens':[1]})
        return httpx.Response(200,json={'choices':[{'finish_reason':'length','message':{'content':'{"code":"partial'}}]})
    model=LocalModel(transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(WorkbenchError) as error:
            if kind=='source':model.complete_code([])
            else:model.plan_workspace_edit('Create a file',{},[],None)
        assert error.value.code=='generation_format'
    finally:model.close()
