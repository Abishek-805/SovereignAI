import sqlite3

import pytest

from scripts.backup_restore import backup, restore


def test_host_visible_project_backup_uses_live_files_and_restores_portably(tmp_path):
    from workflows.coding_workspace import CodingWorkspace
    data=tmp_path/'data'
    data.mkdir()
    with sqlite3.connect(data/'index.sqlite') as db:db.execute('CREATE TABLE example (value TEXT)')
    old=CodingWorkspace(data)
    ident=old.create('Live project')['workspace_id']
    old.write(ident,'notes.md','Initial snapshot')
    hosted=CodingWorkspace(data,tmp_path/'Documents/Projects')
    hosted.get(ident)
    hosted.write(ident,'notes.md','Latest live changes')
    hosted.write(ident,'new.md','New live file')
    archive=tmp_path/'backup'
    backup(data,archive,projects_dir=tmp_path/'Documents/Projects')
    restored=tmp_path/'restored'
    restore(archive,restored)
    portable=CodingWorkspace(restored)
    assert portable.read(ident,'notes.md')['content']=='Latest live changes'
    assert portable.read(ident,'new.md')['content']=='New live file'
    remigrated=CodingWorkspace(restored,tmp_path/'NewDocuments/Projects')
    assert remigrated.read(ident,'notes.md')['content']=='Latest live changes'
    assert hosted.read(ident,'notes.md')['content']=='Latest live changes'


def test_host_project_backup_missing_live_root_does_not_archive_stale_files(tmp_path):
    from workflows.coding_workspace import CodingWorkspace
    data=tmp_path/'data'
    data.mkdir()
    with sqlite3.connect(data/'index.sqlite') as db:db.execute('CREATE TABLE example (value TEXT)')
    work=CodingWorkspace(data,tmp_path/'Documents/Projects')
    work.create('Live project')
    archive=tmp_path/'backup'
    with pytest.raises(ValueError,match='Live project missing'):
        backup(data,archive,projects_dir=tmp_path/'WrongLocation')
    assert not archive.exists()


def test_backup_restore_retains_database_and_source_bytes(tmp_path):
    data = tmp_path / 'data'
    data.mkdir()
    with sqlite3.connect(data / 'index.sqlite') as db:
        db.execute('CREATE TABLE example (value TEXT)')
        db.execute('INSERT INTO example VALUES (?)', ('historical source',))
    (data / 'sources').mkdir()
    (data / 'sources' / 'source.txt').write_bytes(b'original bytes')
    archive, restored = tmp_path / 'archive', tmp_path / 'restored'
    backup(data, archive)
    restore(archive, restored)
    with sqlite3.connect(restored / 'index.sqlite') as db:
        assert db.execute('SELECT value FROM example').fetchone()[0] == 'historical source'
    assert (restored / 'sources' / 'source.txt').read_bytes() == b'original bytes'


def test_restore_rejects_tampered_source(tmp_path):
    data = tmp_path / 'data'
    data.mkdir()
    with sqlite3.connect(data / 'index.sqlite') as db:
        db.execute('CREATE TABLE example (value TEXT)')
    (data / 'sources').mkdir()
    (data / 'sources' / 'source.txt').write_bytes(b'original')
    archive = tmp_path / 'archive'
    backup(data, archive)
    (archive / 'sources' / 'source.txt').write_bytes(b'changed')
    with pytest.raises(ValueError, match='validation'):
        restore(archive, tmp_path / 'restored')
    assert not (tmp_path / 'restored').exists()


def test_full_recovery_preserves_artifacts_and_task_history(tmp_path):
    data = tmp_path / 'data'
    data.mkdir()
    with sqlite3.connect(data / 'index.sqlite') as db:
        db.execute('CREATE TABLE versions (id TEXT, source TEXT)')
        db.execute("INSERT INTO versions VALUES ('v1', 'sources/original.txt')")
    expected = {'sources/original.txt': b'historical evidence',
                'answers/a.json': b'{"version":"v1"}',
                'tasks/t.json': b'{"state":"completed"}',
                'coding-workspaces/w/main.py': b'print(1)',
                'code-tasks/t/result.txt': b'1'}
    for name, content in expected.items():
        path = data / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    outputs = tmp_path / 'outputs'
    outputs.mkdir()
    (outputs / 'report.docx').write_bytes(b'artifact bytes')
    archive = tmp_path / 'archive'
    backup(data, archive, outputs)
    restored, restored_outputs = tmp_path / 'restored', tmp_path / 'restored-outputs'
    with pytest.raises(ValueError, match='artifacts'):
        restore(archive, restored)
    assert not restored.exists()
    restore(archive, restored, restored_outputs)
    for name, content in expected.items():
        assert (restored / name).read_bytes() == content
    with sqlite3.connect(restored / 'index.sqlite') as db:
        source = db.execute("SELECT source FROM versions WHERE id='v1'").fetchone()[0]
    assert (restored / source).read_bytes() == b'historical evidence'
    assert (restored_outputs / 'report.docx').read_bytes() == b'artifact bytes'


def test_restore_rejects_absolute_manifest_path(tmp_path):
    import hashlib
    import json
    archive = tmp_path / 'archive'
    archive.mkdir()
    source = archive / 'source.txt'
    source.write_bytes(b'x')
    (archive / 'backup-manifest.json').write_text(json.dumps({'files': [
        {'path': str(source), 'sha256': hashlib.sha256(b'x').hexdigest()}]}))
    with pytest.raises(ValueError, match='manifest path'):
        restore(archive, tmp_path / 'restored')
    assert not (tmp_path / 'restored').exists()
