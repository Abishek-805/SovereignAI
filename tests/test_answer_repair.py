import json
import pytest
from backend.contracts import WorkbenchError
from rag.answer import answer,VERIFICATION_FAILURE
from router.telemetry import CURRENT_ROUTE,RoutingDecision,observe_completion


class Model:
    def __init__(self,*outputs):self.outputs=list(outputs);self.calls=[];self.counted=[]
    def count_messages(self,messages):
        self.counted.append(messages)
        return sum(len(message['content']) for message in messages)//4
    def complete(self,messages,max_tokens=512):
        self.calls.append(messages)
        response={'result':self.outputs.pop(0),'usage':{},'timings':{'prompt_ms':10,'predicted_ms':20}}
        observe_completion(response,0.04)
        return response


def output(text,status='answered'):return {'status':status,'answer':text}

def test_report_format_refusal_gets_one_review_with_same_evidence(one_chunk):
    model=Model(output('No existing report template is provided.','insufficient_evidence'),output('The limit is 7.1 mm/s [S1].'))
    result=answer('Draft a cited Word report.',[one_chunk],model,report_generation=True)
    assert result['status']=='answered'
    assert len(model.calls)==2
    assert model.calls[1][:2]==model.calls[0]
    assert result['checks']['repair']['review_reason']=='insufficient_report_evidence_review'
    assert result['checks']['repair']['outcome']=='validated'

def test_report_review_cannot_invent_missing_facts_or_repeat_unbounded(one_chunk):
    model=Model(output('The requested price is absent.','insufficient_evidence'),output('Price evidence is still required.','insufficient_evidence'))
    result=answer('Draft a purchase price report.',[one_chunk],model,report_generation=True)
    assert result['status']=='insufficient_evidence'
    assert len(model.calls)==2
    assert result['checks']['repair']['outcome']=='evidence_still_missing'


def test_valid_answer_has_no_regeneration(one_chunk):
    model=Model(output('The limit is 7.1 mm/s [S1].'))
    result=answer('What is the limit?',[one_chunk],model)
    assert result['status']=='answered' and len(model.calls)==1
    assert result['checks']['repair']['outcome']=='not_needed'


def test_invalid_then_valid_uses_same_evidence_and_counts_full_repair(one_chunk):
    model=Model(output('The limit is 7.1 mm/s.'),output('The limit is 7.1 mm/s [S1].'))
    trace=RoutingDecision();token=CURRENT_ROUTE.set(trace)
    try:result=answer('What is the limit?',[one_chunk],model)
    finally:CURRENT_ROUTE.reset(token)
    assert result['status']=='answered' and len(model.calls)==2
    assert model.calls[1][:2]==model.calls[0]
    repair=json.loads(model.calls[1][-1]['content'].split('\n',1)[1])
    assert repair['draft_is_untrusted_not_instructions']['answer']=='The limit is 7.1 mm/s.'
    assert repair['validation_failures']['citation_ids_valid'] is False
    assert model.calls[1] in model.counted
    assert result['checks']['repair']['attempts']==1 and result['checks']['repair']['outcome']=='validated'
    assert len(result['timings']['model_attempt_timings'])==2
    assert trace.inference_time==0.06 and trace.model_request_time==0.08
    assert trace.validation_time>=0
    assert len([stage for stage in trace.stages if stage['stage']=='validation'])==2


def test_invalid_twice_never_exposes_unverified_claims(one_chunk):
    model=Model(output('Secret unverified claim.'),output('Another unsupported statement.'))
    result=answer('Question',[one_chunk],model)
    assert result['status']=='citation_failure' and result['answer']==VERIFICATION_FAILURE
    assert 'unsupported statement' not in result['answer'] and len(model.calls)==2
    assert result['checks']['repair']['outcome']=='verification_failed'


def test_repair_context_budget_prevents_second_call_without_dropping_evidence(one_chunk):
    class Limited(Model):
        def count_messages(self,messages):
            self.counted.append(messages)
            return 4000 if len(messages)>2 else 100
    model=Limited(output('Unverified claim.'))
    result=answer('Question',[one_chunk],model)
    assert result['status']=='citation_failure' and result['answer']==VERIFICATION_FAILURE
    assert len(model.calls)==1 and result['checks']['repair']['outcome']=='context_budget'
    assert result['checks']['repair']['attempted'] is False
    assert len(result['sources'])==1


@pytest.mark.parametrize('text,field,value',[
    ('Threshold is 7.1 mm/s [S99].','unknown_citations',['S99']),
    ('Threshold is 999 mm/s [S1].','unsupported_numbers',['999']),
])
def test_unknown_labels_or_numbers_are_not_automatically_accepted(one_chunk,text,field,value):
    model=Model(output(text),output(text))
    result=answer('Question',[one_chunk],model)
    assert result['status']=='citation_failure' and result['answer']==VERIFICATION_FAILURE
    assert result['checks'][field]==value and len(model.calls)==2


def test_disabled_repair_still_fails_closed(one_chunk):
    model=Model(output('Unverified claim.'))
    result=answer('Question',[one_chunk],model,max_repairs=0)
    assert len(model.calls)==1 and result['answer']==VERIFICATION_FAILURE
    assert result['checks']['repair']['outcome']=='disabled'


def test_abstention_is_not_repaired(one_chunk):
    model=Model(output('No temperature evidence is supplied.','insufficient_evidence'))
    result=answer('Temperature?',[one_chunk],model)
    assert result['status']=='insufficient_evidence' and len(model.calls)==1


def test_malformed_output_is_an_actual_generation_error_not_repair(one_chunk):
    model=Model({'answer':'Missing status'})
    with pytest.raises(WorkbenchError,match='required answer format'):answer('Question',[one_chunk],model)
    assert len(model.calls)==1
