from types import SimpleNamespace
import pytest
from backend.contracts import WorkbenchError
from rag.recovery import recover_evidence


def passage(identity):return SimpleNamespace(document_id='permitted',chunk_id=identity,text=identity)


def test_missing_evidence_recovered_without_changing_answer_request():
    old=passage('irrelevant');new=passage('relevant');feedback=[];generated=[]
    result=recover_evidence({'status':'insufficient_evidence','answer':'Missing interval'},[old],
        refine=lambda value:feedback.append(value) or 'inspection interval',retrieve=lambda query:[new],
        generate=lambda evidence:generated.append(evidence) or {'status':'answered','answer':'Inspect every year. [S1]'},
        checkpoint=lambda:None)
    assert result['status']=='answered'
    assert feedback==['Missing interval'] and generated==[[new]]
    assert result['checks']['retrieval_recovery']['outcome']=='recovered'


def test_repeated_evidence_does_not_keep_generating():
    old=passage('same')
    def forbidden(*args):raise AssertionError('Must stop before another answer')
    result=recover_evidence({'status':'insufficient_evidence','answer':'Missing'},[old],
        refine=lambda feedback:'other query',retrieve=lambda query:[old],generate=forbidden,checkpoint=lambda:None)
    assert result['status']=='insufficient_evidence'
    assert result['checks']['retrieval_recovery']['outcome']=='no_new_evidence'


def test_recovery_budget_stops_unproductive_new_passages():
    count=[]
    def lookup(query):count.append(query);return [passage(str(len(count)))]
    result=recover_evidence({'status':'citation_failure','answer':'Invalid'},[passage('initial')],
        refine=lambda feedback:'refined',retrieve=lookup,
        generate=lambda evidence:{'status':'insufficient_evidence','answer':'Still missing'},checkpoint=lambda:None)
    assert len(count)==2 and result['checks']['retrieval_recovery']['outcome']=='budget_exhausted'


def test_cancellation_is_not_converted_to_missing_evidence():
    def cancelled():raise WorkbenchError('cancelled','Stopped')
    with pytest.raises(WorkbenchError,match='Stopped'):
        recover_evidence({'status':'insufficient_evidence'},[],refine=lambda feedback:'query',
            retrieve=lambda query:[],generate=lambda evidence:{},checkpoint=cancelled)


def test_success_does_not_trigger_extra_model_work():
    def forbidden(*args):raise AssertionError('Unnecessary retry')
    result=recover_evidence({'status':'answered','answer':'Supported'},[],refine=forbidden,
        retrieve=forbidden,generate=forbidden,checkpoint=forbidden)
    assert result['checks']['retrieval_recovery']['outcome']=='not_needed'
