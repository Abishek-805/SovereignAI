from dataclasses import replace
import numpy as np
import pytest
from backend.contracts import WorkbenchError
from rag.store import Store

def publish(store,chunk,vector):
    return store.publish(chunk.document_id,chunk.display_name,'a.txt',chunk.version_hash,[chunk],vector,'emb1',[])

def test_publish_unchanged_replace(store,one_chunk,one_vector):
    assert publish(store,one_chunk,one_vector)['status']=='indexed'
    assert publish(store,one_chunk,one_vector)['status']=='unchanged'
    new=replace(one_chunk,chunk_id='c2',version_hash='v2',text='P-101 limit 9.0 mm/s.')
    assert publish(store,new,one_vector)['status']=='replaced'
    assert store.documents()[0]['active_hash']=='v2'
    assert [c.chunk_id for c,v in store.active_chunks()]==['c2']
    assert store.get_chunk('c1').version_hash=='v1'

def test_failed_replacement_keeps_old(store,one_chunk,one_vector):
    publish(store,one_chunk,one_vector)
    with pytest.raises(WorkbenchError):
        publish(store,replace(one_chunk,chunk_id='c2',version_hash='v2'),np.zeros((0,384)))
    assert store.documents()[0]['active_hash']=='v1'

def test_transaction_rollback(store,one_chunk,one_vector):
    publish(store,one_chunk,one_vector)
    with store.connect() as db:
        db.execute("CREATE TRIGGER fail_publish BEFORE INSERT ON chunks WHEN NEW.version_hash='v2' BEGIN SELECT RAISE(ABORT, 'test failure'); END")
    with pytest.raises(WorkbenchError):
        publish(store,replace(one_chunk,chunk_id='c2',version_hash='v2'),one_vector)
    assert store.documents()[0]['active_hash']=='v1'
    assert store.get_chunk('c1').text==one_chunk.text

def test_same_name_distinct_ids_and_scope(store,one_chunk,one_vector):
    publish(store,one_chunk,one_vector)
    publish(store,replace(one_chunk,chunk_id='c2',document_id='d2'),one_vector)
    assert len(store.documents())==2
    assert len(store.active_chunks(['d2']))==1
    assert store.active_chunks([])==[]
    with pytest.raises(WorkbenchError): store.active_chunks(['missing'])

def test_bad_vectors_revision_identity(store,one_chunk,one_vector):
    with pytest.raises(WorkbenchError): publish(store,one_chunk,np.full((1,384),np.nan))
    publish(store,one_chunk,one_vector)
    with pytest.raises(WorkbenchError):
        store.publish('d2','x','x','v2',[one_chunk],one_vector,'emb1',[])
    with pytest.raises(WorkbenchError):
        store.publish('d1','a','a','v1',[one_chunk],one_vector,'different',[])

def test_collection_limit(tmp_path,one_chunk,one_vector):
    store=Store(tmp_path/'i.sqlite',max_chunks=1)
    publish(store,one_chunk,one_vector)
    with pytest.raises(WorkbenchError): publish(store,replace(one_chunk,chunk_id='c2',document_id='d2'),one_vector)
    assert len(store.documents())==1

def test_lexical_active_before_limit(store,one_chunk,one_vector):
    publish(store,one_chunk,one_vector)
    publish(store,replace(one_chunk,chunk_id='c2',version_hash='v2'),one_vector)
    assert store.lexical('"P"',limit=1)==['c2']

def test_document_management_keeps_other_documents(store, one_chunk, one_vector):
    publish(store, one_chunk, one_vector)
    publish(store, replace(one_chunk, chunk_id='c2', document_id='d2'), one_vector)
    assert store.rename_document(one_chunk.document_id, 'renamed.txt')['display_name'] == 'renamed.txt'
    assert store.get_chunk(one_chunk.chunk_id).display_name == 'renamed.txt'
    assert store.remove_document(one_chunk.document_id)['removed']
    assert [doc['document_id'] for doc in store.documents()] == ['d2']
    assert [chunk.chunk_id for chunk, _ in store.active_chunks()] == ['c2']
    with store.connect() as db:
        assert db.execute('SELECT count(*) FROM chunk_fts WHERE chunk_id=?', (one_chunk.chunk_id,)).fetchone()[0] == 0
    with pytest.raises(WorkbenchError):
        store.remove_document(one_chunk.document_id)
