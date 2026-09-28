"""Balanced excerpt coverage for a planner-requested collection overview."""
from collections import defaultdict


def overview_passages(active, passages_per_document=3):
    """Offer one complete passage from every document before offering more.

    This is an excerpt overview, not a claim to read complete large files. Keep
    inference/tokenization bounded; coverage metadata records the omitted chunks.
    """
    grouped = defaultdict(list)
    for chunk, _ in active:
        grouped[chunk.document_id].append(chunk)
    groups = [sorted(chunks, key=lambda chunk: (
        chunk.page or 0, chunk.line_start or 0, chunk.chunk_id
    )) for _, chunks in sorted(grouped.items())]
    return [chunks[index] for index in range(passages_per_document)
            for chunks in groups if index < len(chunks)]


def overview_documents(active):
    grouped = {}
    for chunk, _ in active:
        entry = grouped.setdefault(chunk.document_id, {
            'document_id': chunk.document_id,
            'display_name': chunk.display_name,
            'indexed_passages': 0,
        })
        entry['indexed_passages'] += 1
    return [grouped[key] for key in sorted(grouped)]


def overview_coverage(documents, sources):
    included = defaultdict(int)
    for source in sources:
        included[source['document_id']] += 1
    return {
        'mode': 'overview',
        'basis': 'indexed_passages',
        'requested_documents': len(documents),
        'covered_documents': sum(bool(included[doc['document_id']]) for doc in documents),
        'all_documents_represented': all(included[doc['document_id']] for doc in documents),
        'all_indexed_passages_included': all(
            included[doc['document_id']] == doc['indexed_passages'] for doc in documents
        ),
        'documents': [{**doc, 'included_passages': included[doc['document_id']]} for doc in documents],
    }
