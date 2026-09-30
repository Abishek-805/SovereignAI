"""Durable publication recovery, with conservative handling of external writers.

The project lock coordinates cooperating processes only. Path checks cannot stop
an uncooperative host process swapping a parent between a check and an OS call.
Callers must hold ProjectLock across prepare, publication and recovery.
"""
import hashlib
import json
import os
import tempfile
from pathlib import Path, PurePosixPath

from backend.contracts import WorkbenchError


def _error(message):
    return WorkbenchError('publication_recovery', message)


def _linked(path):
    if not path.exists() and not path.is_symlink(): return False
    return (path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction()) or
            bool(getattr(path.lstat(), 'st_file_attributes', 0) & 0x400))


def _check(path):
    path = Path(os.path.abspath(path))
    if any(_linked(part) for part in (path, *path.parents)):
        raise _error('Linked or reparse publication path rejected')
    return path


def _path(root, relative):
    if not isinstance(relative, str) or '\\' in relative or ':' in relative:
        raise _error('Invalid publication path')
    parts = PurePosixPath(relative)
    if parts.is_absolute() or not parts.parts or any(p in {'.', '..'} for p in relative.split('/')):
        raise _error('Invalid publication path')
    path = _check(root / relative)
    if not path.is_relative_to(root): raise _error('Publication path escaped project')
    return path


def _hash(data):
    return hashlib.sha256(data).hexdigest() if data is not None else None


def _bytes(path):
    _check(path)
    if path.exists() and not path.is_file(): raise _error('Expected regular publication file')
    return path.read_bytes() if path.is_file() else None


def _atomic(path, data):
    _check(path); _check(path.parent)
    # A destination-derived name plus UUID can exceed Windows MAX_PATH even
    # when the journal destination itself is valid. mkstemp creates a short,
    # exclusive sibling, retaining same-filesystem atomic replacement.
    descriptor, name = tempfile.mkstemp(prefix='.pub-', dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        _check(path); _check(path.parent)
        os.replace(temporary, path)
        # Directory fsync is supported on POSIX; Windows does not expose it here.
        if os.name != 'nt':
            descriptor = os.open(path.parent, os.O_RDONLY)
            try: os.fsync(descriptor)
            finally: os.close(descriptor)
    finally:
        temporary.unlink(missing_ok=True)


class ProjectLock:
    """OS advisory lock shared by cooperating backend instances."""
    def __init__(self, project_root):
        self.root = _check(project_root)
        self.stream = None

    def __enter__(self):
        # Lock metadata must not become execution input or project content.
        path = _check(self.root.parent / ('.' + self.root.name + '.sovereign-publication.lock'))
        self.stream = path.open('a+b')
        if path.stat().st_size == 0:
            self.stream.write(b'0'); self.stream.flush()
        self.stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.stream.close(); self.stream = None
            raise _error('Another process is publishing this project')
        return self

    def __exit__(self, *args):
        try:
            self.stream.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.stream.fileno(), fcntl.LOCK_UN)
        finally: self.stream.close(); self.stream = None


class PublicationJournal:
    def __init__(self, project_root, transaction_dir, project_id, task_id):
        self.project = _check(project_root)
        self.directory = _check(transaction_dir)
        if self.directory.is_relative_to(self.project):
            raise _error('Journal must be outside canonical project')
        self.project_id = project_id; self.task_id = task_id
        self.path = self.directory / 'journal.json'

    def _save(self, record):
        _check(self.directory)
        _atomic(self.path, json.dumps(record, sort_keys=True, indent=2).encode('utf-8'))
        return record

    def load(self):
        record = json.loads(_bytes(self.path))
        if (record.get('version') != 1 or record.get('project_root') != str(self.project) or
            record.get('project_id') != self.project_id or record.get('task_id') != self.task_id):
            raise _error('Publication journal identity mismatch')
        if record.get('state') not in {'preparing','publishing','committed','failed','recovery_required'}:
            raise _error('Invalid publication state')
        return record

    def prepare(self, changes, expected_revisions, staged_dir):
        if self.path.exists(): raise _error('Publication transaction already exists')
        stage = _check(staged_dir)
        self.directory.mkdir(parents=True, exist_ok=True)
        backups = _check(self.directory / 'backups'); backups.mkdir(exist_ok=True)
        entries = []; seen = set()
        for index, change in enumerate(changes):
            name = change['path']; path = _path(self.project, name)
            if name in seen: raise _error('Duplicate publication path')
            seen.add(name); action = change['action']
            if action not in {'create','edit','delete','mkdir','rmdir'}: raise _error('Unsupported publication action')
            entry = {'path':name,'action':action,'before_hash':None,'staged_hash':None,'backup':None}
            if action in {'mkdir','rmdir'}:
                if action == 'mkdir' and path.exists(): raise _error('Created directory already exists')
                if action == 'rmdir' and not path.is_dir(): raise _error('Removed directory does not exist')
            else:
                before = _bytes(path)
                if _hash(before) != expected_revisions.get(name): raise _error('Project revision changed before preparation')
                entry['before_hash'] = _hash(before)
                if before is not None:
                    entry['backup'] = f'backups/{index}.bin'
                    _atomic(_path(self.directory, entry['backup']), before)
                if action != 'delete':
                    staged = _bytes(_path(stage, name))
                    if staged is None or _hash(staged) != change.get('staged_hash'): raise _error('Staged bytes changed')
                    entry['staged_hash'] = _hash(staged)
            entries.append(entry)
        return self._save({'version':1,'project_root':str(self.project),'project_id':self.project_id,
                           'task_id':self.task_id,'state':'preparing','entries':entries,'conflicts':[]})

    def mark_publishing(self):
        record = self.load()
        if record['state'] != 'preparing': raise _error('Transaction is not prepared')
        record['state'] = 'publishing'; return self._save(record)

    def commit(self):
        record = self.load()
        if record['state'] != 'publishing': raise _error('Transaction is not publishing')
        for entry in record['entries']:
            path = _path(self.project, entry['path'])
            if entry['action'] == 'mkdir': valid = path.is_dir()
            elif entry['action'] == 'rmdir': valid = not path.exists()
            else: valid = _hash(_bytes(path)) == entry['staged_hash']
            if not valid: raise _error('Publication verification failed')
        record['state'] = 'committed'; return self._save(record)

    def recover(self):
        record = self.load()
        if record['state'] in {'committed','failed'}: return record
        # A durable PREPARING record precedes all canonical writes.
        if record['state'] == 'preparing':
            record['state'] = 'failed'; return self._save(record)
        conflicts = []
        for entry in reversed(record['entries']):
            name = entry['path']
            try:
                path = _path(self.project, name); action = entry['action']
                if action == 'mkdir':
                    if path.exists():
                        if not path.is_dir() or any(path.iterdir()): raise _error('Created directory has external content')
                        path.rmdir()
                elif action == 'rmdir':
                    if not path.exists():
                        _check(path.parent)
                        path.mkdir()
                    elif not path.is_dir(): raise _error('Removed directory replaced externally')
                else:
                    current = _hash(_bytes(path))
                    if current == entry['before_hash']: continue
                    if current != entry['staged_hash']: raise _error('External revision preserved')
                    before = None
                    if entry['before_hash'] is not None:
                        before = _bytes(_path(self.directory, entry['backup']))
                        if _hash(before) != entry['before_hash']: raise _error('Backup hash mismatch')
                    # Recheck immediately before rollback; still not a host CAS.
                    if _hash(_bytes(path)) != current: raise _error('External revision preserved')
                    if before is None: path.unlink(missing_ok=True)
                    else: _atomic(path, before)
            except (WorkbenchError, OSError, ValueError, KeyError, TypeError): conflicts.append(name)
        record['conflicts'] = conflicts
        record['state'] = 'recovery_required' if conflicts else 'failed'
        return self._save(record)
