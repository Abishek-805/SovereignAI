import hashlib
import sqlite3
import pytest
from backend.settings import Settings
from backend.service import Workbench
from backend.contracts import WorkbenchError
from scripts.backup_restore import backup

def test_knowledge_folder_migrates_preserving_legacy(tmp_path, monkeypatch):
    data = tmp_path / 'data'
    old = data / 'sources'
    old.mkdir(parents=True)
    content = b'Library source'
    name = hashlib.sha256(content).hexdigest() + '.txt'
    (old / name).write_bytes(content)
    live = tmp_path / 'Documents' / 'SovereignAI' / 'Knowledge'
    monkeypatch.setenv('SOVEREIGN_KNOWLEDGE_DIR', str(live))
    service = Workbench(Settings(data_dir=data))
    assert service.sources_dir == live
    assert (live / name).read_bytes() == content
    assert (old / name).read_bytes() == content
    Workbench(Settings(data_dir=data))
    archive = tmp_path / 'archive'
    newer = live / 'new.txt'
    newer.write_text('New source', encoding='utf-8')
    backup(data, archive)
    assert (archive / 'sources' / 'new.txt').read_text() == 'New source'

def test_knowledge_collision_never_overwrites(tmp_path, monkeypatch):
    data = tmp_path / 'data'
    old = data / 'sources'
    old.mkdir(parents=True)
    (old / 'source.txt').write_text('old')
    live = tmp_path / 'Knowledge'
    live.mkdir()
    (live / 'source.txt').write_text('existing')
    monkeypatch.setenv('SOVEREIGN_KNOWLEDGE_DIR', str(live))
    with pytest.raises(WorkbenchError):
        Workbench(Settings(data_dir=data))
    assert (live / 'source.txt').read_text() == 'existing'
