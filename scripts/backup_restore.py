"""Back up and restore a stopped workbench's document collection."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
from pathlib import Path


def _digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def backup(data_dir: Path, destination: Path, outputs_dir: Path | None = None) -> None:
    data_dir, destination = data_dir.resolve(), destination.resolve()
    if destination.exists() or destination.is_relative_to(data_dir):
        raise ValueError('Choose a new backup directory outside the live data directory')
    db_file = data_dir / 'index.sqlite'
    if not db_file.is_file():
        raise FileNotFoundError(db_file)
    destination.mkdir(parents=True)
    try:
        with sqlite3.connect(db_file) as source, sqlite3.connect(destination / 'index.sqlite') as target:
            source.backup(target)
        for name in ('sources', 'ocr', 'answers', 'tasks', 'code-tasks', 'coding-workspaces'):
            if (data_dir / name).exists():
                _reject_links(data_dir / name)
                shutil.copytree(data_dir / name, destination / name)
        if outputs_dir is not None:
            outputs_dir = outputs_dir.resolve()
            if not outputs_dir.is_dir() or destination.is_relative_to(outputs_dir):
                raise ValueError('Outputs must be an existing directory outside the backup')
            _reject_links(outputs_dir)
            shutil.copytree(outputs_dir, destination / 'outputs')
        files = sorted(path for path in destination.rglob('*') if path.is_file())
        manifest = [{'path': path.relative_to(destination).as_posix(), 'sha256': _digest(path)} for path in files]
        (destination / 'backup-manifest.json').write_text(json.dumps({'schema': 1, 'files': manifest}, indent=2), encoding='utf-8')
    except BaseException:
        shutil.rmtree(destination)
        raise


def _reject_links(directory: Path) -> None:
    for path in [directory, *directory.rglob('*')]:
        if path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction()):
            raise ValueError('Backup cannot follow filesystem links')


def restore(archive: Path, destination: Path, outputs_dir: Path | None = None) -> None:
    archive, destination = archive.resolve(), destination.resolve()
    if destination.exists() or destination.is_relative_to(archive):
        raise ValueError('Restore requires a new directory outside the backup')
    manifest = json.loads((archive / 'backup-manifest.json').read_text(encoding='utf-8'))
    files = manifest.get('files')
    if not isinstance(files, list) or not files:
        raise ValueError('Invalid backup manifest')
    _reject_links(archive)
    has_outputs = any(Path(item['path']).parts[:1] == ('outputs',) for item in files)
    if has_outputs:
        if outputs_dir is None:
            raise ValueError('This backup includes artifacts; specify a new outputs directory')
        outputs_dir = outputs_dir.resolve()
        if (outputs_dir.exists() or outputs_dir.is_relative_to(archive)
                or outputs_dir.is_relative_to(destination) or destination.is_relative_to(outputs_dir)):
            raise ValueError('Restore outputs requires a separate new directory')
    seen = set()
    for item in files:
        relative = Path(item['path'])
        if relative.is_absolute() or '..' in relative.parts or not relative.parts or str(relative).lower() in seen:
            raise ValueError('Invalid backup manifest path')
        seen.add(str(relative).lower())
        source = (archive / relative).resolve()
        if not source.is_relative_to(archive) or not source.is_file() or _digest(source) != item['sha256']:
            raise ValueError(f'Backup file failed validation: {relative}')
    with sqlite3.connect(archive / 'index.sqlite') as db:
        if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('Backup database failed integrity check')
    destination.mkdir(parents=True)
    try:
        if has_outputs:
            outputs_dir.mkdir(parents=True)
        for item in files:
            relative = Path(item['path'])
            target = (outputs_dir / Path(*relative.parts[1:]) if relative.parts[0] == 'outputs'
                      else destination / relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(archive / relative, target)
    except BaseException:
        shutil.rmtree(destination)
        if has_outputs and outputs_dir.exists():
            shutil.rmtree(outputs_dir)
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('backup', 'restore'))
    parser.add_argument('source', type=Path)
    parser.add_argument('destination', type=Path)
    parser.add_argument('--outputs-dir', type=Path, help='Existing outputs for backup; separate new outputs path for restore')
    options = parser.parse_args()
    (backup if options.action == 'backup' else restore)(options.source, options.destination, options.outputs_dir)
