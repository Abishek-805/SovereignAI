from dataclasses import replace
import pytest
from backend.contracts import WorkbenchError
from rag.store import Store
from tests.test_store import publish
from tests.test_service import service
from tests.test_api import client_for


def test_folder_persistence_and_version_conflicts(store,one_chunk,one_vector):
    publish(store,one_chunk,one_vector)
    moved=store.move_document(one_chunk.document_id,'Projects/Inspection','v1')
    assert moved['folder']=='Projects/Inspection'
    assert Store(store.path).current(one_chunk.document_id)['folder']=='Projects/Inspection'
    assert store.get_chunk(one_chunk.chunk_id).version_hash=='v1'
    for folder in ('../outside','/absolute','a//b','a\\b','a\x00b'):
        with pytest.raises(WorkbenchError): store.move_document(one_chunk.document_id,folder)
    publish(store,replace(one_chunk,chunk_id='next',version_hash='v2'),one_vector)
    assert store.current(one_chunk.document_id)['folder']=='Projects/Inspection'
    for call in (lambda:store.rename_document(one_chunk.document_id,'new.txt','v1'),lambda:store.move_document(one_chunk.document_id,'Other','v1'),lambda:store.remove_document(one_chunk.document_id,'v1')):
        with pytest.raises(WorkbenchError) as error:call()
        assert error.value.code=='document_conflict'
    assert store.get_chunk(one_chunk.chunk_id).version_hash=='v1'
    assert store.move_document(one_chunk.document_id,'','v2')['folder']==''


def test_management_api_update_preserves_identity_and_sources(service):
    with client_for(service) as client:
        original=client.post('/documents/import',files={'file':('management.txt',b'Original limit is 7.1 mm/s.')}).json()
        doc_id=original['document_id']; version=original['active_hash']
        original_content=client.get(f'/documents/{doc_id}/content').json()
        old_source=original_content['passages'][0]['chunk_id']
        assert client.patch(f'/documents/{doc_id}',json={'display_name':'Renamed.txt','expected_hash':version}).status_code==200
        assert client.post(f'/documents/{doc_id}/move',json={'folder':'Inspections/2026','expected_hash':version}).json()['folder']=='Inspections/2026'
        updated=client.post('/documents/import',data={'document_id':doc_id,'expected_hash':version},files={'file':('replacement.txt',b'Updated limit is 8.0 mm/s.')}).json()
        assert updated['document_id']==doc_id and updated['display_name']=='Renamed.txt'
        assert updated['active_hash']!=version and updated['folder']=='Inspections/2026'
        assert client.get(f'/sources/{old_source}').status_code==200
        assert client.get(f'/sources/{old_source}/original').content==b'Original limit is 7.1 mm/s.'
        rejected=client.post('/documents/import',data={'document_id':doc_id,'expected_hash':version},files={'file':('stale.txt',b'Stale update.')})
        assert rejected.status_code==409
        assert client.delete(f'/documents/{doc_id}',params={'expected_hash':version}).status_code==409
        assert client.get(f'/documents/{doc_id}/content').json()['active_hash']==updated['active_hash']
        assert client.delete(f'/documents/{doc_id}',params={'expected_hash':updated['active_hash']}).status_code==200
        assert client.get('/documents').json()==[]
        assert not list((service.settings.data_dir/'uploads').glob('*'))

def test_copy_reuses_index_and_immutable_original_with_new_identity(service,monkeypatch):
    with client_for(service) as client:
        original=client.post('/documents/import',files={'file':('copy-source.txt',b'Immutable source contents.')}).json()
        original_id=original['document_id']
        def forbidden(*args,**kwargs):raise AssertionError('Copy must not load/recompute embeddings')
        monkeypatch.setattr(service.embedder,'encode',forbidden)
        copied=client.post(f'/documents/{original_id}/copy',json={'folder':'Copied','expected_hash':original['active_hash']})
        assert copied.status_code==200,copied.text
        copy=copied.json()
        assert copy['document_id']!=original_id and copy['active_hash']==original['active_hash']
        assert copy['folder']=='Copied' and copy['copied_from']==original_id
        first=client.get(f'/documents/{original_id}/content').json()['passages'][0]['chunk_id']
        second=client.get(f"/documents/{copy['document_id']}/content").json()['passages'][0]['chunk_id']
        assert first!=second
        assert client.get(f'/sources/{first}/original').content==client.get(f'/sources/{second}/original').content
        assert client.post(f'/documents/{original_id}/copy',json={'expected_hash':'stale'}).status_code==409
        assert client.post(f'/documents/{original_id}/copy',json={'folder':'../invalid'}).status_code==400
        assert len(client.get('/documents').json())==2
        assert client.delete(f"/documents/{copy['document_id']}").status_code==200
        assert client.get(f'/sources/{first}/original').status_code==200
