from collections import defaultdict
import re
import numpy as np
from backend.contracts import WorkbenchError


def fts_query(text):
    terms=list(dict.fromkeys(re.findall(r'\w+',text,flags=re.UNICODE)))[:32]
    return ' OR '.join('"'+term.replace('"','""')+'"' for term in terms)


def rrf(rankings):
    scores=defaultdict(float)
    for ranking in rankings:
        for rank,key in enumerate(dict.fromkeys(ranking),1):
            scores[key]+=1/(60+rank)
    return sorted(scores,key=lambda key:(-scores[key],key))


def retrieve(store, embedder, question, document_ids=None, limit=6):
    active=store.active_chunks(document_ids)
    if not active:
        return []
    revisions={d['embedding_revision'] for d in store.documents() if document_ids is None or d['document_id'] in document_ids}
    if revisions!={embedder.revision}:
        raise WorkbenchError('embedding_mismatch','Reindex with the configured embedding model')
    query=embedder.encode([question],query=True)[0]
    dense=sorted(((chunk.chunk_id,float(vector@query)) for chunk,vector in active),key=lambda pair:(-pair[1],pair[0]))[:12]
    lexical=store.lexical(fts_query(question),12,document_ids)
    by_id={chunk.chunk_id:chunk for chunk,_ in active}
    order=rrf([lexical,[key for key,_ in dense]])
    selected=[]
    for key in order:
        # Another import can commit between the lexical and dense reads.
        if key not in by_id:
            continue
        candidate=by_id[key]
        duplicate=False
        for chosen in selected:
            if (chosen.document_id,chosen.page)!=(candidate.document_id,candidate.page):
                continue
            # Similar wording may contain conflicting numbers or negation.
            if candidate.text==chosen.text:
                duplicate=True
                break
        if not duplicate:
            selected.append(candidate)
        if len(selected)==limit:
            break
    return selected
