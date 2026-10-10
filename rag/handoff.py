"""Resolve supplied evidence references against the active source snapshot."""
from backend.contracts import WorkbenchError


def active_evidence(store, chunk_ids, document_ids=None):
    if not isinstance(chunk_ids,list) or len(chunk_ids)>12 or any(not isinstance(key,str) for key in chunk_ids):
        raise WorkbenchError('invalid_request','Invalid prior evidence references')
    allowed=set(document_ids) if document_ids is not None else None
    versions={d['document_id']:d['active_hash'] for d in store.documents()}
    result=[]
    for key in dict.fromkeys(chunk_ids):
        try:chunk=store.get_chunk(key)
        except WorkbenchError as exc:
            if exc.code=='unknown_source':continue
            raise
        if versions.get(chunk.document_id)!=chunk.version_hash or allowed is not None and chunk.document_id not in allowed:
            continue
        result.append(chunk)
    return result
