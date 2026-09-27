from dataclasses import replace
import pytest
from backend.contracts import WorkbenchError
from rag.answer import answer

class FakeModel:
    def __init__(self):
        self.output={'status':'answered','answer':'The limit is 7.1 mm/s [S1].'}
        self.calls=[]
    def count_messages(self,messages): return sum(len(m['content']) for m in messages)//4
    def complete(self,messages,max_tokens=512):
        self.calls.append(messages)
        return {'result':self.output,'usage':{},'timings':{}}

def test_valid(one_chunk):
    result=answer('limit?',[one_chunk],FakeModel())
    assert result['status']=='answered'
    assert result['sources'][0]['chunk_id']=='c1'
    assert result['checks']['semantic_support']=='not_automatically_proven'

def test_followup_history_is_context_not_evidence(one_chunk):
    model=FakeModel()
    result=answer('What about that limit?',[one_chunk],model,history=['What is the limit?'])
    payload=model.calls[0][-1]['content']
    assert result['status']=='answered'
    assert 'previous_user_questions_for_reference_only' in payload
    assert 'What is the limit?' in payload
    assert result['sources'][0]['display_name']==one_chunk.display_name

@pytest.mark.parametrize('text,unknown',[('Limit is 7.1 mm/s.',[]),('Limit is 7.1 [S9].',['S9'])])
def test_invalid_citations(one_chunk,text,unknown):
    model=FakeModel(); model.output['answer']=text
    result=answer('limit?',[one_chunk],model)
    assert result['status']=='citation_failure'
    assert result['checks']['unknown_citations']==unknown


def test_numeric_claim_must_be_supported_by_its_cited_passages(one_chunk):
    limit=replace(one_chunk,text='Investigation threshold 7.1 mm/s.')
    measured=replace(one_chunk,chunk_id='c2',document_id='d2',display_name='inspection.txt',text='Measured vibration 8.2 mm/s.')
    model=FakeModel()
    model.output['answer']='Vibration was 8.2 mm/s against a 7.1 mm/s threshold [S1].'
    result=answer('compare',[limit,measured],model)
    assert result['status']=='citation_failure'
    assert result['checks']['unsupported_numbers']==['8.2']
    model.output['answer']='Vibration was 8.2 mm/s [S2], against a 7.1 mm/s threshold [S1].'
    result=answer('compare',[limit,measured],model)
    assert result['status']=='answered'
    assert result['checks']['numeric_claims_supported'] is True

def test_abstain(one_chunk):
    model=FakeModel(); model.output={'status':'insufficient_evidence','answer':'No temperature limit supplied.'}
    assert answer('temperature?',[one_chunk],model)['status']=='insufficient_evidence'

def test_no_evidence_never_calls_model():
    assert answer('limit?',[],None)['status']=='insufficient_evidence'

def test_budget(one_chunk):
    with pytest.raises(WorkbenchError) as error: answer('x'*16000,[one_chunk],FakeModel())
    assert error.value.code=='question_too_long'
    huge=replace(one_chunk,chunk_id='c2',text='z'*16000)
    result=answer('limit?',[one_chunk,huge],FakeModel())
    assert len(result['sources'])==1

def test_errors_not_abstention(one_chunk):
    class Failed(FakeModel):
        def complete(self,*args,**kwargs): raise WorkbenchError('model_timeout','timeout')
    with pytest.raises(WorkbenchError) as error: answer('limit?',[one_chunk],Failed())
    assert error.value.code=='model_timeout'

def test_bad_structured_response(one_chunk):
    model=FakeModel(); model.output={'answer':'guess'}
    with pytest.raises(WorkbenchError): answer('limit?',[one_chunk],model)
