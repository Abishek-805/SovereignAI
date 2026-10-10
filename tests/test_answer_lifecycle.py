import threading
from backend.jobs import Job, Jobs
from router.task_completion import observe_completion
from rag.grounding import abstention


def grounded_result():
    return {'status':'answered','answer':'Confirmed. [S1]','checks':{
        'semantic_support':'claim_assessed_with_exact_quote_bindings',
        'evidence_assessment':{'passed':True},'citation_ids_valid':True,
        'numeric_claims_supported':True}}


def test_verified_answer_completion_requires_grounding():
    result=grounded_result()
    assert observe_completion(result)['state']=='completed'
    result['checks']['evidence_assessment']['passed']=False
    assert observe_completion(result)['state']=='unverified'
    result['status']='insufficient_evidence'
    assert observe_completion(result)['state']=='needs_input'


def test_terminal_job_ignores_late_progress_and_drafts():
    job=Job('agent');job.state='completed';job.stage='Finished'
    job.progress('Generating sourced answer');job.preview('late draft','answer')
    assert job.stage=='Finished' and job.snapshot()['partial_answer']=='' and not job.events
    job.state='running';job.cancel.set();job.progress('Verifying sourced answer')
    assert job.stage=='Finished'


def test_job_commits_once_and_clears_draft():
    jobs=Jobs();release=threading.Event();calls=[]
    def run(job):
        calls.append(job.id);job.preview('provisional','answer');release.wait(2)
        return grounded_result()
    started=jobs.start('document',run);job=jobs.get(started['job_id'])
    assert job.snapshot()['state']=='running'
    release.set()
    for _ in range(100):
        if job.state!='running':break
        threading.Event().wait(.01)
    snapshots=[job.snapshot() for _ in range(3)]
    assert len(calls)==1 and all(s['state']=='completed' and s['stage']=='Finished' and not s['partial_answer'] for s in snapshots)


def test_missing_reason_does_not_require_model_to_list_missing_field():
    check={'supported_claims':[{'source_bound':True,'quotes':[{'label':'S1','text':'The calibration interval is 90 days.'}]}],
           'unsupported_claims':[],'missing_evidence':[],'sufficient_for_answer':False,'rationale_supported':False}
    text=abstention(check,'Why is this interval required?')
    assert '90 days' in text and 'requested rationale' in text and 'authorized source' in text
    assert 'does not state why' not in text  # Failed support alone cannot prove source absence.


def test_retrieval_cannot_restart_an_assessed_answer():
    from rag.recovery import recover_evidence
    initial={'status':'insufficient_evidence','answer':'Evidence does not support this.',
             'checks':{'evidence_assessment':{'passed':False},'repair':{'attempts':1}}}
    def unexpected(*args):raise AssertionError('Terminal assessment must not regenerate')
    result=recover_evidence(initial,[],refine=unexpected,retrieve=unexpected,generate=unexpected,checkpoint=unexpected)
    assert result['checks']['retrieval_recovery']['outcome']=='assessment_terminal'
    assert result['checks']['repair']['attempts']==1


def test_grouped_citations_preserve_grounding_and_unknown_label_rejection():
    from rag.answer import _normalize_table_identifiers,_validate_result
    from rag.grounding import assess
    from types import SimpleNamespace
    source={'label':'S1','document_id':'d','version_hash':'v','chunk_id':'c','line_start':1,'text':'Admission is 12.5 credits.'}
    other={**source,'label':'S2'}
    draft=_normalize_table_identifiers({'status':'answered','answer':'Admission is 12.5 credits. [S1, S2]'},[source,other])
    assert draft['answer']=='Admission is 12.5 credits. [S1] [S2]'
    assert _validate_result(draft,[source,other],0)['numeric_claims_supported']
    model=SimpleNamespace(assess_evidence=lambda *a:{'claims':[{'text':draft['answer'],'support':'FACT_SUPPORTED','quotes':[{'label':'S1','text':source['text']},{'label':'S2','text':other['text']}]}],'missing_evidence':[],'sufficient_for_answer':True,'rationale_supported':False})
    assert assess('How much is admission?',draft,[source,other],model)['passed']
    unknown=_normalize_table_identifiers({'status':'answered','answer':'Admission is 12.5 credits. [S1, S999]'},[source])
    assert _validate_result(unknown,[source],0)['unknown_citations']==['S999']
