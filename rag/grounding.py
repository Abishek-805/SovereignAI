"""Fail-closed claim coverage and exact source support bindings."""
import re
from backend.contracts import WorkbenchError


def draft_claims(text):
    """Bind assessment IDs to software-owned spans, never model paraphrases."""
    # Keep the tail contiguous and complete within the existing 24-claim cap.
    spans=[span.strip() for span in re.split(r'(?<=[.!?])\s+(?=[A-Z])|\n+',text,maxsplit=23) if span.strip()]
    return [{'id':f'C{i+1}','text':span} for i,span in enumerate(spans)]


def assess(question, result, sources, model, history=None):
    assessment=model.assess_evidence(question,result,sources,history)
    if not isinstance(assessment,dict) or not isinstance(assessment.get('claims'),list) or not isinstance(assessment.get('missing_evidence'),list):
        raise WorkbenchError('generation_format','Invalid evidence assessment contract')
    text=result['answer'];covered=set();supported=[];unsupported=[]
    citation_chars={i for match in re.finditer(r'\[S\d+\]',text) for i in range(match.start(),match.end())}
    # Reviewers may omit inline citations while retaining the sentence punctuation.
    omitted={i for match in re.finditer(r'[ \t]*\[S\d+\]',text) for i in range(match.start(),match.end())}
    positions=[i for i in range(len(text)) if i not in omitted]
    uncited=''.join(text[i] for i in positions)
    bylabel={s['label']:s for s in sources}
    for claim in assessment.get('claims',[]):
        span=claim.get('text','');start=text.find(span) if span else -1
        if start>=0:covered.update(range(start,start+len(span)))
        elif span:
            claim_text=re.sub(r'[ \t]*\[S\d+\]','',span)
            offset=uncited.find(claim_text) if claim_text else -1
            if offset>=0:
                matched=positions[offset:offset+len(claim_text)]
                start=matched[0];covered.update(matched)
        cited_context=text[text.rfind('\n',0,max(start,0))+1:text.find('\n',max(start,0)) if '\n' in text[max(start,0):] else len(text)]
        quotes=claim.get('quotes',[])
        bound=bool(quotes)
        for quote in quotes:
            source=bylabel.get(quote.get('label'))
            bound=bound and bool(source and source.get('document_id') and source.get('version_hash') and source.get('chunk_id')
                and (source.get('page') is not None or source.get('line_start') is not None)
                and quote.get('text') and quote['text'] in source['text']
                and '['+quote['label']+']' in cited_context)
        causal=bool(re.search(r'\b(?:because|due to|so that|in order to|ensures?|reason|justification)\b',span,re.I))
        literal=any(re.sub(r'\[S\d+\]','',span).strip() in quote.get('text','') for quote in quotes) if span else False
        valid=start>=0 and bound and claim.get('support') in {'FACT_SUPPORTED','RATIONALE_SUPPORTED'}
        if causal:valid=valid and (claim['support']=='RATIONALE_SUPPORTED' or literal) and assessment.get('rationale_supported') is True
        (supported if valid else unsupported).append({**claim,'source_bound':bool(bound),'supported':bool(valid),
            'literal_source_claim':bool(literal and bound and claim.get('support') in {'FACT_SUPPORTED','RATIONALE_SUPPORTED'}
                and (not causal or assessment.get('rationale_supported') is True))})
    coverage=all(i in covered or i in citation_chars for i,c in enumerate(text) if c.isalnum())
    sufficient=assessment.get('sufficient_for_answer') is True
    rationale_request=bool(re.search(r'\b(?:why|reason|justification)\b',question,re.I))
    rationale_satisfied=not rationale_request or assessment.get('rationale_supported') is True
    valid=coverage and not unsupported and bool(supported) and sufficient and rationale_satisfied
    return {'supported_claims':supported,'unsupported_claims':unsupported,'claim_coverage':coverage,
        'missing_evidence':assessment.get('missing_evidence',[]),'rationale_supported':assessment.get('rationale_supported') is True,
        'source_bound':bool(supported) and all(c['source_bound'] for c in supported) and not unsupported,
        'sufficient_for_answer':sufficient,'passed':valid,
        'quoted_answer_supported':sufficient and rationale_satisfied and bool(supported or unsupported) and all(c['literal_source_claim'] for c in supported+unsupported)}


def source_quotes(assessment):
    # Only exact source quotations survive a rejected draft; no inferred prose.
    quotes=[]
    for claim in assessment['supported_claims']+assessment['unsupported_claims']:
        if not claim['source_bound']:continue
        for quote in claim['quotes']:
            item='> '+quote['text'].replace('\n','\n> ')+' ['+quote['label']+']'
            if item not in quotes:quotes.append(item)
    return '\n\n'.join(quotes[:4])


def abstention(assessment,question):
    missing=bool(assessment['missing_evidence']) and not assessment['sufficient_for_answer']
    gap=(('The supplied source does not state why. An authorized source explaining the rationale is needed.' if missing else 'The supplied evidence does not establish the requested rationale. An authorized source explaining why is needed.') if not assessment['rationale_supported'] and re.search(r'\b(?:why|reason|justification)\b',question,re.I)
         else 'The supplied evidence does not establish the requested answer or explanation.' if missing
         else 'I could not verify the drafted answer against the supplied evidence.')
    return '\n\n'.join(part for part in (source_quotes(assessment),gap) if part)
