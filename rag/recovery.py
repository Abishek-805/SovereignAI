"""Bounded evidence recovery; the original question remains controlling."""
from backend.contracts import WorkbenchError


def recover_evidence(initial, passages, *, refine, retrieve, generate, checkpoint, progress=None, attempts=2):
    if isinstance(attempts,bool) or not isinstance(attempts,int) or not 0<=attempts<=2:
        raise ValueError('Evidence recovery is limited to two refinements')
    result=initial
    seen={tuple((p.document_id,p.chunk_id,p.text) for p in passages)}
    observations=[]
    stop='not_needed'
    for attempt in range(attempts):
        if result.get('status') not in {'insufficient_evidence','citation_failure'}:break
        checkpoint()
        if progress:progress(f'Supervisor refining missing evidence ({attempt+1}/{attempts})')
        try:
            query=refine(result.get('answer',''))
            checkpoint()
            revised=retrieve(query)
        except WorkbenchError as error:
            if error.code in {'cancelled','supervisor_budget','resource_limit'}:raise
            observations.append({'attempt':attempt+1,'error_code':error.code})
            stop='refinement_unavailable';break
        identity=tuple((p.document_id,p.chunk_id,p.text) for p in revised)
        if not revised or identity in seen:
            observations.append({'attempt':attempt+1,'passage_count':len(revised),'outcome':'no_new_evidence'})
            stop='no_new_evidence';break
        seen.add(identity)
        result=generate(revised)
        observations.append({'attempt':attempt+1,'passage_count':len(revised),'answer_status':result.get('status')})
        stop='recovered' if result.get('status')=='answered' else 'budget_exhausted'
    checks={**result.get('checks',{}),'retrieval_recovery':{'attempts':len(observations),'outcome':stop,'observations':observations}}
    return {**result,'checks':checks}
