"""Bounded hierarchical coding workspaces. Generated code runs only in CodeSandbox."""
import difflib
import hashlib
import json
import re
import shutil
import time
from pathlib import Path
from uuid import uuid4

from backend.contracts import WorkbenchError
from router.sandbox import FILE_NAME, safe_relative_name
from workflows.code_runtime import runner, LANGUAGES

WORKSPACE_ID = re.compile(r'^[a-f0-9]{32}$')
ALLOWED_SUFFIXES = {'.py', '.txt', '.csv', '.json', '.md'}
MAX_FILES = 256
MAX_FILE_BYTES = 128_000
MAX_CONTEXT_CHARS = 20_000
TEST_RUNNER = '''import sys
import unittest
sys.path.insert(0, '/input')
suite = unittest.defaultTestLoader.discover('/input', pattern='test_*.py')
result = unittest.TextTestRunner(verbosity=2).run(suite)
sys.exit(0 if result.testsRun and result.wasSuccessful() else 1)
'''


class CodingWorkspace:
    def __init__(self, data_dir: Path):
        self.root = (Path(data_dir) / 'coding-workspaces').resolve()

    def _directory(self, workspace_id: str):
        if not WORKSPACE_ID.fullmatch(workspace_id):
            raise WorkbenchError('invalid_workspace', 'Invalid workspace ID')
        directory = self.root / workspace_id
        if directory.is_symlink() or not directory.is_dir() or not directory.resolve().is_relative_to(self.root):
            raise WorkbenchError('invalid_workspace', 'Workspace does not exist')
        return directory

    @staticmethod
    def _name(name: str):
        if not safe_relative_name(name) or name == 'program.py':
            raise WorkbenchError('invalid_file', 'Use a relative workspace path without parent traversal or reserved names')
        return name

    @staticmethod
    def _artifact_name(name: str):
        if not isinstance(name, str) or not FILE_NAME.fullmatch(name) or '..' in name:
            raise WorkbenchError('unknown_artifact', 'Invalid coding artifact name')
        return name

    def _file(self, workspace_id: str, name: str):
        directory = self._directory(workspace_id)
        name = self._name(name)
        files = directory / 'files'
        if files.is_symlink() or not files.is_dir() or not files.resolve().is_relative_to(directory):
            raise WorkbenchError('invalid_workspace', 'Workspace files are unavailable')
        path = files / name
        if any(p.is_symlink() or (hasattr(p, 'is_junction') and p.is_junction()) for p in [path, *path.parents] if p != files.parent) or not path.resolve().is_relative_to(files.resolve()):
            raise WorkbenchError('invalid_file', 'Workspace path escapes its boundary')
        return path

    def create(self, name: str):
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80:
            raise WorkbenchError('invalid_workspace', 'Enter a workspace name under 80 characters')
        self.root.mkdir(parents=True, exist_ok=True)
        workspace_id = uuid4().hex
        directory = self.root / workspace_id
        (directory / 'files').mkdir(parents=True, exist_ok=False)
        (directory / 'tasks').mkdir()
        (directory / 'workspace.json').write_text(json.dumps({
            'workspace_id': workspace_id, 'name': name.strip(), 'created_at': time.time()
        }), encoding='utf-8')
        return self.get(workspace_id)

    def get(self, workspace_id: str):
        directory = self._directory(workspace_id)
        metadata = json.loads((directory / 'workspace.json').read_text(encoding='utf-8'))
        files = directory / 'files'
        metadata['files'] = [{'name': path.relative_to(files).as_posix(), 'bytes': path.stat().st_size}
                             for path in sorted(files.rglob('*')) if path.is_file() and not path.is_symlink()]
        metadata['folders'] = [path.relative_to(files).as_posix() for path in sorted(files.rglob('*'))
                               if path.is_dir() and not path.is_symlink()]
        return metadata

    def list(self):
        if not self.root.is_dir():
            return []
        return [self.get(path.name) for path in sorted(self.root.iterdir())
                if path.is_dir() and not path.is_symlink() and WORKSPACE_ID.fullmatch(path.name)]

    def read(self, workspace_id: str, name: str):
        path = self._file(workspace_id, name)
        if not path.is_file():
            raise WorkbenchError('invalid_file', 'Workspace file does not exist')
        return {'name': name, 'content': path.read_text(encoding='utf-8')}

    def write(self, workspace_id: str, name: str, content: str):
        path = self._file(workspace_id, name)
        if not isinstance(content, str) or len(content.encode('utf-8')) > MAX_FILE_BYTES:
            raise WorkbenchError('invalid_file', 'Workspace file exceeds 128 KB')
        if not path.exists() and len(self.get(workspace_id)['files']) >= MAX_FILES:
            raise WorkbenchError('invalid_file', 'Workspace has reached its 256-file limit')
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + '.' + uuid4().hex + '.tmp')
        try:
            temporary.write_text(content, encoding='utf-8')
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
        return {'name': name, 'bytes': len(content.encode('utf-8'))}

    def file_operation(self, workspace_id: str, action: str, source: str, destination: str | None = None):
        if action not in {'copy', 'move', 'delete', 'mkdir'}:
            raise WorkbenchError('invalid_file', 'Choose copy, move, delete, or mkdir')
        source_path = self._file(workspace_id, source)
        if action == 'mkdir':
            if source_path.exists():
                raise WorkbenchError('workspace_conflict', 'That folder already exists')
            source_path.mkdir(parents=True)
            return {'action': action, 'source': source, 'workspace': self.get(workspace_id)}
        if not source_path.is_file() and not source_path.is_dir():
            raise WorkbenchError('invalid_file', 'The source does not exist')
        if source_path.is_dir() and any(path.is_symlink() or (hasattr(path, 'is_junction') and path.is_junction()) for path in source_path.rglob('*')):
            raise WorkbenchError('invalid_file', 'Folder contains an unsafe link')
        if action == 'delete':
            if source_path.is_dir():
                shutil.rmtree(source_path)
            else:
                source_path.unlink()
            return {'action': action, 'source': source, 'workspace': self.get(workspace_id)}

        if not destination:
            raise WorkbenchError('invalid_file', 'Choose a destination file name')
        destination_path = self._file(workspace_id, destination)
        if destination_path == source_path or destination_path.exists():
            raise WorkbenchError('workspace_conflict', 'A file with that name already exists')
        if source_path.is_dir() and destination_path.is_relative_to(source_path):
            raise WorkbenchError('invalid_file', 'Cannot place a folder inside itself')
        if action == 'copy' and len(self.get(workspace_id)['files']) + (sum(1 for p in source_path.rglob('*') if p.is_file()) if source_path.is_dir() else 1) > MAX_FILES:
            raise WorkbenchError('invalid_file', 'Workspace has reached its 256-file limit')
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        if action == 'move':
            source_path.replace(destination_path)
        elif source_path.is_dir():
            shutil.copytree(source_path, destination_path)
        else:
            temporary = destination_path.with_name(destination_path.name + '.' + uuid4().hex + '.tmp')
            try:
                temporary.write_bytes(source_path.read_bytes())
                temporary.replace(destination_path)
            finally:
                temporary.unlink(missing_ok=True)
        return {'action': action, 'source': source, 'destination': destination,
                'workspace': self.get(workspace_id)}

    def result(self, workspace_id: str, task_id: str):
        directory = self._directory(workspace_id) / 'tasks'
        if not WORKSPACE_ID.fullmatch(task_id):
            raise WorkbenchError('invalid_task', 'Invalid coding task ID')
        path = directory / (task_id + '.json')
        if path.is_symlink() or not path.is_file():
            raise WorkbenchError('invalid_task', 'Coding task does not exist')
        return json.loads(path.read_text(encoding='utf-8'))

    def undo(self, workspace_id: str, task_id: str):
        result = self.result(workspace_id, task_id)
        if result.get('state') != 'completed' or not isinstance(result.get('original_content'), str):
            raise WorkbenchError('invalid_task', 'Only an applied coding change can be undone')
        current = self.read(workspace_id, result['target'])['content']
        if hashlib.sha256(current.encode('utf-8')).hexdigest() != result.get('applied_hash'):
            raise WorkbenchError('workspace_conflict', 'The file changed since this task; review it before undoing')
        self.write(workspace_id, result['target'], result['original_content'])
        result['state'] = 'undone'
        result['checks']['target_committed'] = False
        self._save_result(workspace_id, result)
        return result

    def _save_result(self, workspace_id: str, result: dict):
        directory = self._directory(workspace_id) / 'tasks'
        path = directory / (result['task_id'] + '.json')
        temporary = directory / (uuid4().hex + '.tmp')
        try:
            temporary.write_text(json.dumps(result, indent=2), encoding='utf-8')
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)

    def artifact(self, workspace_id: str, task_id: str, name: str):
        self._artifact_name(name)
        result = self.result(workspace_id, task_id)
        entry = next((item for item in result['output_files'] if item['name'] == name), None)
        if entry is None:
            raise WorkbenchError('unknown_artifact', 'Coding artifact does not exist')
        path = self._directory(workspace_id) / 'tasks' / task_id / name
        if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != entry['sha256']:
            raise WorkbenchError('artifact_invalid', 'Coding artifact failed validation')
        return path

    def _store_artifacts(self, workspace_id: str, task_id: str, files: dict[str, bytes]):
        if len(files) > 8 or sum(len(data) for data in files.values()) > 4_000_000:
            raise WorkbenchError('sandbox_output', 'Container returned too many result files')
        directory = self._directory(workspace_id) / 'tasks' / task_id
        directory.mkdir(exist_ok=False)
        entries = []
        for name, data in sorted(files.items()):
            self._artifact_name(name)
            (directory / name).write_bytes(data)
            entries.append({'name': name, 'bytes': len(data),
                            'sha256': hashlib.sha256(data).hexdigest(),
                            'url': f'/coding/workspaces/{workspace_id}/tasks/{task_id}/artifacts/{name}'})
        return entries

    def run(self, workspace_id: str, target: str, instruction: str, model, sandbox, ledger,
            model_alias: str = 'sovereign-text', progress=None, cancel=None):
        def stage(message):
            if cancel is not None and cancel.is_set():raise WorkbenchError('cancelled','Task stopped; no pending edit was saved')
            if progress:progress(message)
        stage('Reading project files')
        target = self._name(target)
        if Path(target).suffix.lower() not in LANGUAGES or Path(target).name.startswith('test_'):
            raise WorkbenchError('invalid_file', 'Select a supported source file to edit')
        if not isinstance(instruction, str) or not 1 <= len(instruction.strip()) <= 1000:
            raise WorkbenchError('sandbox_input', 'Enter a coding task under 1,000 characters')
        files = {entry['name']: self.read(workspace_id, entry['name'])['content']
                 for entry in self.get(workspace_id)['files']}
        if target not in files:
            raise WorkbenchError('invalid_workspace', 'The selected source file does not exist')
        trusted_tests = target.endswith('.py') and any(Path(name).name.startswith('test_') and name.endswith('.py') for name in files)
        context_files = {target: files[target]}
        for name, content in sorted(files.items(), key=lambda item: (not Path(item[0]).name.startswith('test_'), item[0])):
            if name not in context_files and sum(map(len, context_files.values())) + len(content) <= MAX_CONTEXT_CHARS:
                context_files[name] = content
        if len(files[target]) > MAX_CONTEXT_CHARS:
            raise WorkbenchError('context_budget', 'Selected file is too large for one edit; split it into smaller modules')
        sandbox._ready()  # Fail before creating a task when verified Docker is unavailable.
        task = ledger.create('coding_workspace', [])
        original = files[target]
        runtime_check = not trusted_tests and target.endswith('.py') and bool(re.search(r'\b(fix|solve|repair|error|bug|crash|traceback|fail)\b', instruction, re.I))
        events = []
        result = {'task_id': task['task_id'], 'workspace_id': workspace_id, 'target': target,
                  'state': 'running', 'validation': 'supplied_tests' if trusted_tests else 'runtime_check' if runtime_check else 'syntax_or_format_check', 'context_files': sorted(context_files), 'omitted_context_files': sorted(set(files)-set(context_files)), 'attempts': 0, 'events': events, 'checks': {},
                  'diff': '', 'stdout': '', 'stderr': '', 'output_files': [],
                  'routing': {'capability': 'code', 'model': model_alias,
                              'reason': 'Configured local text model for bounded source editing'},
                  'sandbox': {'backend': 'docker', 'image_id': getattr(sandbox, 'image_id', None)}}
        self._save_result(workspace_id, result)
        try:
            ledger.step(task, 'plan', {'target': target, 'file_count': len(files)})
            events.append({'event': 'planning', 'detail': f'Edit {target}; validate in Docker using '+('supplied tests' if trusted_tests else 'syntax or format checks')})
            ledger.step(task, 'read_files', {'files': sorted(files)})
            events.append({'event': 'reading_files', 'files': sorted(files)})
            messages = [
                {'role': 'system', 'content': 'Return only the complete source code for the selected file in the JSON code field. Match its language. Edit only that file. Do not change supplied tests. The file will be checked in an isolated container.'},
                {'role': 'user', 'content': f'Task: {instruction.strip()}\nTarget: {target}\nFiles:\n' +
                 '\n'.join(f'--- {name} ---\n{content}' for name, content in sorted(context_files.items()))}
            ]
            base_messages = list(messages)
            if runtime_check:
                stage('Reproducing the reported error')
                baseline = sandbox.execute(runner(target, mode='run'), input_files={name: content.encode('utf-8') for name, content in files.items()})
                if baseline.stderr:
                    messages.append({'role':'user','content':'The current file fails when run in Docker. Fix this actual traceback, then return the complete corrected file:\n'+baseline.stderr[-2500:]})
                    base_messages = list(messages)
            for attempt in range(3):
                stage('Generating change' if attempt==0 else f'Repairing after failed check ({attempt+1}/3)')
                candidate = model.complete_code(messages, max_tokens=2048)['code']
                if len(candidate.encode('utf-8')) > MAX_FILE_BYTES:
                    raise WorkbenchError('sandbox_input', 'Generated file exceeds 128 KB')
                trial = dict(files)
                trial[target] = candidate
                events.append({'event': 'editing_file' if not attempt else f'repair_attempt_{attempt}', 'file': target})
                ledger.step(task, f'edit_{attempt + 1}', {'target': target, 'attempt': attempt + 1})
                stage('Running supplied tests' if trusted_tests else 'Checking source in Docker')
                execution = sandbox.execute(TEST_RUNNER if trusted_tests else runner(target, mode='run' if runtime_check else 'check'), input_files={name: content.encode('utf-8')
                                                                        for name, content in trial.items()})
                safe_stderr = execution.stderr.replace(str(self.root), '[workspace]')
                task_root = getattr(sandbox, 'task_root', None)
                if task_root is not None:
                    safe_stderr = safe_stderr.replace(str(task_root), '[sandbox task]')
                events.append({'event': 'running_tests' if trusted_tests else 'checking_source', 'attempt': attempt + 1,
                               'exit_code': execution.exit_code})
                ledger.step(task, f'test_{attempt + 1}', {'exit_code': execution.exit_code,
                                                           'executed': execution.executed})
                result.update(attempts=attempt + 1, stdout=execution.stdout, stderr=safe_stderr,
                              diff=''.join(difflib.unified_diff(original.splitlines(True),candidate.splitlines(True),
                                     fromfile='a/'+target,tofile='b/'+target)),
                              output_files=[])
                if execution.executed and execution.exit_code == 0 and candidate != original:
                    current = {entry['name']: self.read(workspace_id, entry['name'])['content']
                               for entry in self.get(workspace_id)['files']}
                    if current != files:
                        raise WorkbenchError('workspace_conflict', 'Workspace files changed during testing; rerun the task')
                    result['output_files'] = self._store_artifacts(workspace_id, task['task_id'],
                                                                    execution.output_files)
                    stage('Saving checked change')
                    self.write(workspace_id, target, candidate)
                    result['checks'] = {'container_executed': True, ('tests_passed' if trusted_tests else 'runtime_passed' if runtime_check else 'syntax_or_format_checked'): True,
                                        'target_committed': True}
                    result['original_content'] = original
                    result['applied_hash'] = hashlib.sha256(candidate.encode('utf-8')).hexdigest()
                    result['state'] = 'completed'
                    events.append({'event': 'verification', 'checks': result['checks']})
                    ledger.complete(task, result['checks'])
                    break
                if candidate == original and execution.exit_code == 0:
                    safe_stderr = 'The model returned the original file unchanged. Produce a real edit that addresses the request.'
                events.append({'event': 'test_failed', 'attempt': attempt + 1})
                if attempt < 2:
                    messages = base_messages + [
                        {'role': 'assistant', 'content': json.dumps({'code': candidate})},
                        {'role': 'user', 'content': 'Container validation failed. Repair only the target. Bounded stderr:\n' + safe_stderr[-2000:]}]
            if result['state'] != 'completed':
                result['output_files'] = self._store_artifacts(workspace_id, task['task_id'],
                                                                execution.output_files)
                result['state'] = 'failed'
                result['checks'] = {'container_executed': bool(execution.executed), ('tests_passed' if trusted_tests else 'runtime_passed' if runtime_check else 'syntax_or_format_checked'): False,
                                    'target_committed': False}
                ledger.fail(task, 'trusted_tests_failed' if trusted_tests else 'validation_failed')
            self._save_result(workspace_id, result)
            return result
        except Exception as exc:
            ledger.fail(task, exc.code if isinstance(exc, WorkbenchError) else 'coding_workspace_failed')
            result['state'] = 'failed'
            result['error'] = str(exc) if isinstance(exc, WorkbenchError) else 'Coding task failed; inspect local logs'
            self._save_result(workspace_id, result)
            raise
