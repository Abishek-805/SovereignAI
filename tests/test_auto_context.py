from rag.context import chat_evidence, relevant_passages
from tests.test_retrieve import FakeEmbedder


def test_related_chat_question_uses_index_without_explicit_selection(store, one_chunk, one_vector):
    store.publish('d1', 'a.txt', 'a', 'v1', [one_chunk], one_vector, 'emb1', [])
    matches = relevant_passages(store, FakeEmbedder(), 'What is the P-101 vibration threshold?')
    assert matches and matches[0].document_id == 'd1'
    context = chat_evidence(matches)
    assert '[S1]' in context and '/sources/c1' in context
    assert 'P-101 vibration threshold' in context


def test_unrelated_chat_does_not_attach_library_passages(store, one_chunk, one_vector):
    store.publish('d1', 'a.txt', 'a', 'v1', [one_chunk], one_vector, 'emb1', [])
    assert relevant_passages(store, FakeEmbedder(), 'Write a Python hello world program') == []
    assert chat_evidence([]) is None


def test_greeting_skips_document_catalog_and_embeddings():
    class UnreadableStore:
        def documents(self):
            raise AssertionError('Greeting must not inspect document metadata')
    assert relevant_passages(UnreadableStore(), object(), 'Hi!') == []
