"""Canonical projects must remain untouched until a validated task is accepted."""
import hashlib
from pathlib import Path

import pytest

from backend.contracts import WorkbenchError
from router.task_ledger import TaskLedger
from tests.test_coding_project import ProjectModel, Sandbox
from workflows.coding_workspace import CodingWorkspace


def digest(work, workspace_id):
    return {name: hashlib.sha256(data).hexdigest() for name, data in work.raw_files(workspace_id).items()}


def test_staged_multifile_accept_and_discard(tmp_path):
    work = CodingWorkspace(tmp_path)
    wid = work.create('Publication fixture')['workspace_id']
    work.write(wid, 'a.py', 'A = 1\n')
    original = digest(work, wid)
    operations = {'scope': 'existing_files', 'operations': [
        {'action': 'edit', 'path': 'a.py', 'reason': 'requested edit'},
        {'action': 'create', 'path': 'nested/b.py', 'reason': 'requested addition'},
    ]}
    task = work.run_project(wid, '', 'Edit a.py and create nested/b.py',
                            ProjectModel(operations, 'A = 2\n', 'B = 2\n'), Sandbox(), TaskLedger(tmp_path))
    assert task['publication_state'] == 'staged'
    assert digest(work, wid) == original
    assert (work.root / wid / 'tasks' / task['task_id'] / 'staged' / 'nested' / 'b.py').read_text() == 'B = 2\n'
    work.discard(wid, task['task_id'])
    assert digest(work, wid) == original
    with pytest.raises(WorkbenchError): work.accept(wid, task['task_id'])


def test_accept_rechecks_external_revision_and_preserves_draft(tmp_path):
    work = CodingWorkspace(tmp_path)
    wid = work.create('Revision fixture')['workspace_id']
    work.write(wid, 'a.py', 'A = 1\n')
    task = work.run_project(wid, 'a.py', 'Edit a.py', ProjectModel(
        [{'action': 'edit', 'path': 'a.py', 'reason': 'requested'}], 'A = 2\n'),
        Sandbox(), TaskLedger(tmp_path))
    work.write(wid, 'a.py', 'A = 99\n')
    with pytest.raises(WorkbenchError, match='changed externally'):
        work.accept(wid, task['task_id'])
    assert work.read(wid, 'a.py')['content'] == 'A = 99\n'
    assert work.result(wid, task['task_id'])['publication_state'] == 'staged'


def test_docker_unavailable_cannot_publish_even_new_source(tmp_path):
    work = CodingWorkspace(tmp_path)
    wid = work.create('Unavailable fixture')['workspace_id']
    task = work.run_project(wid, '', 'Create a.py', ProjectModel(
        [{'action': 'create', 'path': 'a.py', 'reason': 'requested'}], 'print(1)\n'),
        None, TaskLedger(tmp_path))
    assert work.raw_files(wid) == {}
    with pytest.raises(WorkbenchError, match='Docker validation'):
        work.accept(wid, task['task_id'])
    assert work.raw_files(wid) == {}


def test_saved_offline_draft_can_be_validated_then_accepted(tmp_path):
    work = CodingWorkspace(tmp_path)
    wid = work.create('Later validation fixture')['workspace_id']
    task = work.run_project(wid, '', 'Create a.py', ProjectModel(
        [{'action': 'create', 'path': 'a.py', 'reason': 'requested'}], 'print(1)\n'),
        None, TaskLedger(tmp_path))
    sandbox = Sandbox()
    validated = work.validate_staged(wid, task['task_id'], sandbox)
    assert validated['validation'] == 'passed'
    assert sandbox.snapshots[0]['a.py'] == b'print(1)\n'
    assert work.raw_files(wid) == {}
    work.accept(wid, task['task_id'])
    assert work.read(wid, 'a.py')['content'] == 'print(1)\n'


def test_failed_later_validation_keeps_draft_and_project_unchanged(tmp_path):
    work = CodingWorkspace(tmp_path)
    wid = work.create('Later failure fixture')['workspace_id']
    task = work.run_project(wid, '', 'Create a.py', ProjectModel(
        [{'action': 'create', 'path': 'a.py', 'reason': 'requested'}], 'print(1)\n'),
        None, TaskLedger(tmp_path))
    with pytest.raises(WorkbenchError, match='could not validate'):
        work.validate_staged(wid, task['task_id'], Sandbox(exit_code=1))
    assert work.raw_files(wid) == {}
    assert work.result(wid, task['task_id'])['publication_state'] == 'staged'


def test_accept_publishes_only_reviewed_files(tmp_path):
    work = CodingWorkspace(tmp_path)
    wid = work.create('Accept fixture')['workspace_id']
    work.write(wid, 'keep.py', 'print("keep")\n')
    before = digest(work, wid)
    task = work.run_project(wid, '', 'Create add.py', ProjectModel(
        {'scope': 'new_files', 'operations': [{'action': 'create', 'path': 'add.py', 'reason': 'requested'}]},
        'def add(a, b):\n    return a + b\n'), Sandbox(), TaskLedger(tmp_path))
    assert digest(work, wid) == before
    result = work.accept(wid, task['task_id'])
    assert result['publication_state'] == 'published' and result['checks']['target_committed']
    assert work.read(wid, 'add.py')['content'].startswith('def add')
    assert digest(work, wid)['keep.py'] == before['keep.py']


def test_publication_exception_rolls_back_prior_file(tmp_path, monkeypatch):
    work = CodingWorkspace(tmp_path)
    wid = work.create('Rollback fixture')['workspace_id']
    work.write(wid, 'a.py', 'A = 1\n')
    before = digest(work, wid)
    task = work.run_project(wid, '', 'Edit a.py and create b.py', ProjectModel(
        {'scope': 'existing_files', 'operations': [
            {'action': 'edit', 'path': 'a.py', 'reason': 'requested'},
            {'action': 'create', 'path': 'b.py', 'reason': 'requested'}]},
        'A = 2\n', 'B = 2\n'), Sandbox(), TaskLedger(tmp_path))
    replace = Path.replace
    failed = False

    def fail_second_publication(source, target):
        nonlocal failed
        if not failed and str(target).endswith('b.py'):
            failed = True
            raise OSError('injected publication failure')
        return replace(source, target)

    monkeypatch.setattr(Path, 'replace', fail_second_publication)
    with pytest.raises(OSError, match='injected'):
        work.accept(wid, task['task_id'])
    assert failed
    assert digest(work, wid) == before
    assert work.result(wid, task['task_id'])['publication_state'] == 'staged'


def test_agent_moves_files_into_existing_folder_only_after_accept(tmp_path):
    work = CodingWorkspace(tmp_path)
    wid = work.create('Move fixture')['workspace_id']
    work.file_operation(wid, 'mkdir', 'web-page')
    work.write(wid, 'index.html', '<html>Old</html>')
    work.write(wid, 'style.css', 'body { color: teal; }')
    before = digest(work, wid)
    operations = [
        {'tool':'file_move','target':name,'value':'web-page/'+name,'input':''}
        for name in ('index.html', 'style.css')
    ]
    task = work.stage_file_operations(wid, operations, Sandbox(), TaskLedger(tmp_path))
    assert task['publication_state'] == 'staged'
    assert digest(work, wid) == before
    result = work.accept(wid, task['task_id'])
    assert result['publication_state'] == 'published'
    assert {item['name'] for item in work.get(wid)['files']} == {
        'web-page/index.html', 'web-page/style.css'}


def test_existing_folder_create_is_idempotent_without_publication(tmp_path):
    work = CodingWorkspace(tmp_path)
    wid = work.create('Existing folder')['workspace_id']
    work.file_operation(wid, 'mkdir', 'web')
    result = work.stage_file_operations(wid, [
        {'tool':'folder_create','target':'web','value':'','input':''}],
        Sandbox(), TaskLedger(tmp_path))
    assert result['already_exists'] and result['changes'] == []
    assert work.get(wid)['folders'] == ['web']


def test_agent_binary_move_preserves_bytes(tmp_path):
    work = CodingWorkspace(tmp_path)
    wid = work.create('Binary move fixture')['workspace_id']
    work.import_bytes(wid, 'picture.png', b'\x89PNG\r\n\x1a\n' + b'0' * 20)
    original = work.raw_files(wid)['picture.png']
    operations = [{'tool':'file_move','target':'picture.png',
                   'value':'assets/picture.png','input':''}]
    task = work.stage_file_operations(wid, operations, Sandbox(), TaskLedger(tmp_path))
    assert work.raw_files(wid)['picture.png'] == original
    work.accept(wid, task['task_id'])
    assert work.raw_files(wid)['assets/picture.png'] == original
    work.undo(wid, task['task_id'])
    assert work.raw_files(wid)['picture.png'] == original
    assert 'assets/picture.png' not in work.raw_files(wid)


def test_existing_destination_is_reviewed_replacement_and_revision_checked(tmp_path):
    work = CodingWorkspace(tmp_path)
    wid = work.create('Existing destination')['workspace_id']
    work.write(wid, 'index.html', '<html>New</html>')
    work.write(wid, 'web/index.html', '<html>Old</html>')
    operations = [{'tool':'file_move','target':'index.html',
                   'value':'web/index.html','input':''}]
    task = work.stage_file_operations(wid, operations, Sandbox(), TaskLedger(tmp_path))
    assert work.read(wid, 'web/index.html')['content'] == '<html>Old</html>'
    work.write(wid, 'web/index.html', '<html>External</html>')
    with pytest.raises(WorkbenchError, match='changed externally'):
        work.accept(wid, task['task_id'])
    assert work.read(wid, 'index.html')['content'] == '<html>New</html>'
    assert work.read(wid, 'web/index.html')['content'] == '<html>External</html>'
    refreshed = work.stage_file_operations(wid, operations, Sandbox(), TaskLedger(tmp_path))
    work.accept(wid, refreshed['task_id'])
    assert work.read(wid, 'web/index.html')['content'] == '<html>New</html>'
    assert 'index.html' not in work.raw_files(wid)
