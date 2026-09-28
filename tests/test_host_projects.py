import hashlib
from pathlib import Path

import pytest

from backend.contracts import WorkbenchError
from workflows.coding_workspace import CodingWorkspace


def test_existing_workspace_migrates_once_and_host_edits_are_live(tmp_path):
    old = CodingWorkspace(tmp_path / 'data')
    workspace = old.create('My project')
    ident = workspace['workspace_id']
    old.write(ident, 'src/notes.md', '# Original\n')
    hosted = CodingWorkspace(tmp_path / 'data', tmp_path / 'Documents' / 'Projects')
    current = hosted.get(ident)
    path = Path(current['host_path']) / 'src/notes.md'
    assert path.read_text() == '# Original\n'
    assert (old.root / ident / 'files/src/notes.md').read_text() == '# Original\n'
    opened = hosted.read(ident, 'src/notes.md')
    path.write_text('# Changed in File Explorer\n')
    assert hosted.read(ident, 'src/notes.md')['content'] == '# Changed in File Explorer\n'
    with pytest.raises(WorkbenchError, match='changed outside'):
        hosted.write(ident, 'src/notes.md', '# Draft', expected_sha256=opened['sha256'])
    hosted.write(ident, 'src/new.md', '# New', expected_sha256='')
    hosted.file_operation(ident, 'move', 'src/new.md', 'docs/new.md')
    assert (Path(current['host_path']) / 'docs/new.md').read_text() == '# New'
    reopened = CodingWorkspace(tmp_path / 'data', tmp_path / 'Documents' / 'Projects')
    assert reopened.get(ident)['host_path'] == current['host_path']
    assert reopened.read(ident, 'src/notes.md')['content'] == '# Changed in File Explorer\n'


def test_host_project_folder_metadata_cannot_escape_boundary(tmp_path):
    import json
    work = CodingWorkspace(tmp_path / 'data', tmp_path / 'projects')
    ident = work.create('Boundary')['workspace_id']
    metadata_path = work.root / ident / 'workspace.json'
    metadata = json.loads(metadata_path.read_text())
    metadata['project_folder'] = '../outside'
    metadata_path.write_text(json.dumps(metadata))
    with pytest.raises(WorkbenchError, match='Invalid project directory'):
        work.get(ident)


def test_migration_never_overwrites_an_existing_project_destination(tmp_path):
    old = CodingWorkspace(tmp_path / 'data')
    ident = old.create('Boundary')['workspace_id']
    old.write(ident, 'notes.md', 'original')
    destination = tmp_path / 'projects' / ('Boundary-' + ident)
    destination.mkdir(parents=True)
    (destination / 'notes.md').write_text('external')
    work = CodingWorkspace(tmp_path / 'data', tmp_path / 'projects')
    with pytest.raises(WorkbenchError, match='destination already exists'):
        work.get(ident)
    assert (destination / 'notes.md').read_text() == 'external'
    assert old.read(ident, 'notes.md')['content'] == 'original'
