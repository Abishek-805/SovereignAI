import hashlib

import pytest

from backend.contracts import WorkbenchError
from workflows.publication_journal import PublicationJournal, ProjectLock


def fixture(tmp_path):
    project = tmp_path / 'project'; project.mkdir()
    (project / 'old').mkdir()
    stage = tmp_path / 'stage'; stage.mkdir()
    (project / 'a.txt').write_bytes(b'before')
    (stage / 'a.txt').write_bytes(b'after')
    journal = PublicationJournal(project, tmp_path / 'transaction', 'project1', 'task1')
    journal.prepare([{'path':'a.txt','action':'edit','staged_hash':hashlib.sha256(b'after').hexdigest()}],
                    {'a.txt':hashlib.sha256(b'before').hexdigest()}, stage)
    return project, journal


def test_partial_publish_recovers_and_is_idempotent(tmp_path):
    project, journal = fixture(tmp_path)
    journal.mark_publishing()
    (project / 'a.txt').write_bytes(b'after')
    assert journal.recover()['state'] == 'failed'
    assert (project / 'a.txt').read_bytes() == b'before'
    assert journal.recover()['state'] == 'failed'


def test_recovery_preserves_external_edit(tmp_path):
    project, journal = fixture(tmp_path)
    journal.mark_publishing()
    (project / 'a.txt').write_bytes(b'external')
    result = journal.recover()
    assert result['state'] == 'recovery_required'
    assert result['conflicts'] == ['a.txt']
    assert (project / 'a.txt').read_bytes() == b'external'


def test_committed_transaction_is_never_rolled_back(tmp_path):
    project, journal = fixture(tmp_path)
    journal.mark_publishing(); (project / 'a.txt').write_bytes(b'after')
    journal.commit()
    assert journal.recover()['state'] == 'committed'
    assert (project / 'a.txt').read_bytes() == b'after'


def test_backup_tampering_blocks_recovery(tmp_path):
    project, journal = fixture(tmp_path)
    journal.mark_publishing(); (project / 'a.txt').write_bytes(b'after')
    (journal.directory / 'backups' / '0.bin').write_bytes(b'tampered')
    assert journal.recover()['state'] == 'recovery_required'
    assert (project / 'a.txt').read_bytes() == b'after'


def test_traversal_rejected(tmp_path):
    project, journal = fixture(tmp_path)
    with pytest.raises(WorkbenchError):
        journal.prepare([{'path':'../escape','action':'delete'}], {}, tmp_path / 'stage')


def test_identity_mismatch_rejected(tmp_path):
    project, journal = fixture(tmp_path)
    other = PublicationJournal(project, journal.directory, 'project1', 'other')
    with pytest.raises(WorkbenchError): other.recover()


def test_directory_recovery_keeps_external_content(tmp_path):
    project = tmp_path / 'project'; project.mkdir()
    (project / 'old').mkdir()
    stage = tmp_path / 'stage'; stage.mkdir()
    journal = PublicationJournal(project, tmp_path / 'transaction', 'p', 't')
    journal.prepare([{'path':'new','action':'mkdir'},{'path':'old','action':'rmdir'}], {}, stage)
    journal.mark_publishing()
    (project / 'old').rmdir(); (project / 'new').mkdir()
    (project / 'new' / 'external.txt').write_bytes(b'external')
    assert journal.recover()['state'] == 'recovery_required'
    assert (project / 'old').is_dir()
    assert (project / 'new' / 'external.txt').read_bytes() == b'external'


def test_project_lock_releases_after_exception(tmp_path):
    tmp_path.joinpath('project').mkdir()
    with pytest.raises(RuntimeError):
        with ProjectLock(tmp_path / 'project'): raise RuntimeError()
    with ProjectLock(tmp_path / 'project'): pass


def test_project_lock_rejects_second_owner(tmp_path):
    project = tmp_path / 'project'; project.mkdir()
    with ProjectLock(project):
        with pytest.raises(WorkbenchError):
            with ProjectLock(project): pass


def test_create_and_delete_recover(tmp_path):
    project = tmp_path / 'project'; project.mkdir()
    stage = tmp_path / 'stage'; stage.mkdir()
    (project / 'deleted').write_bytes(b'old')
    (stage / 'created').write_bytes(b'new')
    journal = PublicationJournal(project, tmp_path / 'transaction', 'p', 't')
    journal.prepare([{'path':'deleted','action':'delete'},
                     {'path':'created','action':'create','staged_hash':hashlib.sha256(b'new').hexdigest()}],
                    {'deleted':hashlib.sha256(b'old').hexdigest(),'created':None}, stage)
    journal.mark_publishing()
    (project / 'deleted').unlink(); (project / 'created').write_bytes(b'new')
    assert journal.recover()['state'] == 'failed'
    assert (project / 'deleted').read_bytes() == b'old'
    assert not (project / 'created').exists()


def test_reparse_check_prevents_recovery_write(tmp_path, monkeypatch):
    project, journal = fixture(tmp_path)
    journal.mark_publishing(); (project / 'a.txt').write_bytes(b'after')
    import workflows.publication_journal as module
    original = module._linked
    monkeypatch.setattr(module, '_linked', lambda path: path == project / 'a.txt' or original(path))
    assert journal.recover()['state'] == 'recovery_required'
    assert (project / 'a.txt').read_bytes() == b'after'


def test_prepare_crash_never_touches_canonical(tmp_path):
    project, journal = fixture(tmp_path)
    assert journal.recover()['state'] == 'failed'
    assert (project / 'a.txt').read_bytes() == b'before'


def test_prepare_flushes_backup_and_journal(tmp_path, monkeypatch):
    import workflows.publication_journal as module
    calls = []; original = module.os.fsync
    monkeypatch.setattr(module.os, 'fsync', lambda descriptor: (calls.append(descriptor), original(descriptor))[1])
    project, journal = fixture(tmp_path)
    assert len(calls) >= 2
    with ProjectLock(project):
        assert sorted(path.name for path in project.iterdir()) == ['a.txt', 'old']


def workspace_draft(tmp_path):
    from tests.test_coding_project import ProjectModel, Sandbox
    from workflows.coding_workspace import CodingWorkspace
    from router.task_ledger import TaskLedger
    work = CodingWorkspace(tmp_path)
    wid = work.create('Recovery')['workspace_id']
    work.write(wid, 'a.py', 'A = 1\n')
    task = work.run_project(wid, '', 'Edit a.py and create nested/b.py',
                            ProjectModel([{'action':'edit','path':'a.py','reason':'requested'},
                                          {'action':'create','path':'nested/b.py','reason':'requested'}],
                                         'A = 2\n', 'B = 2\n'), Sandbox(), TaskLedger(tmp_path))
    return work, wid, task


def test_workspace_restart_recovers_process_crash(tmp_path, monkeypatch):
    from pathlib import Path
    from workflows.coding_workspace import CodingWorkspace
    work, wid, task = workspace_draft(tmp_path)
    original = Path.replace
    def crash(path, target):
        if str(target).endswith('b.py'): raise KeyboardInterrupt('simulated process death')
        return original(path, target)
    with monkeypatch.context() as patch:
        patch.setattr(Path, 'replace', crash)
        with pytest.raises(KeyboardInterrupt): work.accept(wid, task['task_id'])
    assert work.read(wid, 'a.py')['content'] == 'A = 2\n'
    restarted = CodingWorkspace(tmp_path)
    assert restarted.read(wid, 'a.py')['content'] == 'A = 1\n'
    assert not (restarted.files_directory(wid) / 'nested').exists()
    assert restarted.result(wid, task['task_id'])['publication_transaction_state'] == 'failed'
    assert restarted.accept(wid, task['task_id'])['publication_state'] == 'published'
    assert restarted.read(wid, 'nested/b.py')['content'] == 'B = 2\n'


def test_workspace_external_edit_during_failure_blocks_mutation(tmp_path, monkeypatch):
    from pathlib import Path
    work, wid, task = workspace_draft(tmp_path)
    original = Path.replace
    def fail(path, target):
        if str(target).endswith('b.py'):
            (work.files_directory(wid) / 'a.py').write_bytes(b'external')
            raise OSError('injected later failure')
        return original(path, target)
    with monkeypatch.context() as patch:
        patch.setattr(Path, 'replace', fail)
        with pytest.raises(OSError): work.accept(wid, task['task_id'])
    assert work.read(wid, 'a.py')['content'] == 'external'
    assert work.result(wid, task['task_id'])['publication_state'] == 'recovery_required'
    with pytest.raises(WorkbenchError): work.write(wid, 'unrelated.py', 'print(1)')


def test_workspace_restart_recovers_commit_metadata_and_undo(tmp_path):
    from workflows.coding_workspace import CodingWorkspace
    work, wid, task = workspace_draft(tmp_path)
    work.accept(wid, task['task_id'])
    saved = work.result(wid, task['task_id']); saved['publication_state'] = 'staged'
    work._save_result(wid, saved)
    restarted = CodingWorkspace(tmp_path)
    assert restarted.result(wid, task['task_id'])['publication_state'] == 'published'
    restarted.undo(wid, task['task_id'])
    again = CodingWorkspace(tmp_path)
    assert again.result(wid, task['task_id'])['state'] == 'undone'
    assert again.read(wid, 'a.py')['content'] == 'A = 1\n'
    assert not (again.files_directory(wid) / 'nested').exists()


@pytest.mark.parametrize('damage', ['missing_task', 'corrupt_task', 'corrupt_journal', 'journal_schema'])
@pytest.mark.parametrize('transaction_state', ['committed', 'publishing'])
def test_corrupt_recovery_quarantines_only_affected_workspace(tmp_path, damage, transaction_state):
    import json
    from workflows.coding_workspace import CodingWorkspace
    work, wid, task = workspace_draft(tmp_path)
    work.accept(wid, task['task_id'])
    healthy = work.create('Healthy')['workspace_id']
    task_path = work._directory(wid) / 'tasks' / (task['task_id'] + '.json')
    journal_path = next((work._directory(wid) / 'pub').glob('*/*/journal.json'))
    record = json.loads(journal_path.read_text()); record['state'] = transaction_state
    journal_path.write_text(json.dumps(record), encoding='utf-8')
    if damage == 'missing_task': task_path.unlink()
    elif damage == 'corrupt_task': task_path.write_text('{broken', encoding='utf-8')
    elif damage == 'corrupt_journal': journal_path.write_text('{broken', encoding='utf-8')
    else:
        record = json.loads(journal_path.read_text()); record['entries'] = None
        journal_path.write_text(json.dumps(record), encoding='utf-8')
    evidence = journal_path.read_bytes()
    before = work.raw_files(wid)
    restarted = CodingWorkspace(tmp_path)
    assert restarted.get(wid)['publication_recovery']['state'] == 'recovery_required'
    assert len(restarted.list()) == 2
    assert restarted.raw_files(wid) == before
    assert journal_path.read_bytes() == evidence
    restarted.write(healthy, 'good.py', 'print(1)')
    with pytest.raises(WorkbenchError): restarted.write(wid, 'blocked.py', 'print(2)')
    assert not (restarted.files_directory(wid) / 'blocked.py').exists()
def test_atomic_publication_handles_deep_metadata_paths(tmp_path):
    from workflows.publication_journal import _atomic
    parent = tmp_path
    while len(str(parent.resolve())) < 227:
        remaining = 227 - len(str(parent.resolve())) - 1
        parent = parent / ('d' * max(1, min(remaining, 40)))
    parent.mkdir(parents=True)
    target = parent / 'journal.json'
    _atomic(target, b'{"state":"prepared"}')
    assert target.read_bytes() == b'{"state":"prepared"}'
    assert list(parent.iterdir()) == [target]
