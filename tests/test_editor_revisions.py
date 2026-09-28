from concurrent.futures import ThreadPoolExecutor
import hashlib
import pytest
from backend.contracts import WorkbenchError
from workflows.coding_workspace import CodingWorkspace
from tests.test_service import service
from fastapi.testclient import TestClient
from backend.app import create_app


def test_editor_stale_save_preserves_latest_file(tmp_path):
    work = CodingWorkspace(tmp_path)
    wid = work.create('Revision check')['workspace_id']
    work.write(wid, 'notes.md', 'Original', expected_sha256='')
    opened = work.read(wid, 'notes.md')
    assert opened['sha256'] == hashlib.sha256(b'Original').hexdigest()
    saved = work.write(wid, 'notes.md', 'Other editor', expected_sha256=opened['sha256'])
    with pytest.raises(WorkbenchError, match='draft has been kept') as error:
        work.write(wid, 'notes.md', 'Stale draft', expected_sha256=opened['sha256'])
    assert error.value.code == 'workspace_conflict'
    assert work.read(wid, 'notes.md')['content'] == 'Other editor'
    assert work.read(wid, 'notes.md')['sha256'] == saved['sha256']


def test_only_one_concurrent_save_can_publish_same_revision(tmp_path):
    work = CodingWorkspace(tmp_path)
    wid = work.create('Concurrent editors')['workspace_id']
    revision = work.write(wid, 'notes.md', 'Original')['sha256']
    def save(content):
        try:
            return work.write(wid, 'notes.md', content, expected_sha256=revision)
        except WorkbenchError as error:
            return error.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(save, ['First editor', 'Second editor']))
    assert results.count('workspace_conflict') == 1
    assert work.read(wid, 'notes.md')['content'] in {'First editor', 'Second editor'}


def test_create_expectation_does_not_overwrite_existing_file(tmp_path):
    work = CodingWorkspace(tmp_path)
    wid = work.create('Create only')['workspace_id']
    work.write(wid, 'notes.md', 'Keep', expected_sha256='')
    with pytest.raises(WorkbenchError) as error:
        work.write(wid, 'notes.md', 'Overwrite', expected_sha256='')
    assert error.value.code == 'workspace_conflict'
    assert work.read(wid, 'notes.md')['content'] == 'Keep'


def test_removed_file_does_not_get_recreated_by_stale_editor(tmp_path):
    work = CodingWorkspace(tmp_path)
    wid = work.create('Removed file')['workspace_id']
    revision = work.write(wid, 'notes.md', 'Original')['sha256']
    work.file_operation(wid, 'delete', 'notes.md')
    with pytest.raises(WorkbenchError) as error:
        work.write(wid, 'notes.md', 'Stale', expected_sha256=revision)
    assert error.value.code == 'workspace_conflict'
    assert work.get(wid)['files'] == []


def test_editor_revision_api_rejects_stale_and_invalid_revisions(service):
    with TestClient(create_app(service), base_url='http://127.0.0.1:8088') as client:
        wid = client.post('/coding/workspaces', json={'name':'Revision API'}).json()['workspace_id']
        url = f'/coding/workspaces/{wid}/files/notes.md'
        first = client.put(url, json={'content':'Original','expected_sha256':''})
        assert first.status_code == 200
        revision = client.get(url).json()['sha256']
        assert revision == first.json()['sha256']
        assert client.put(url,json={'content':'Current','expected_sha256':revision}).status_code == 200
        stale = client.put(url,json={'content':'Stale','expected_sha256':revision})
        assert stale.status_code == 409
        assert client.get(url).json()['content'] == 'Current'
        assert client.put(url,json={'content':'Invalid','expected_sha256':'broken'}).status_code == 422
