"""Small durable, metadata-only record of bounded local workflows."""
import json
import os
import re
import time
from pathlib import Path
from uuid import uuid4

from backend.contracts import WorkbenchError


class TaskLedger:
    def __init__(self, data_dir: Path):
        self.directory = Path(data_dir) / 'tasks'

    def _path(self, task_id):
        if not re.fullmatch(r'[a-f0-9]{32}', task_id):
            raise WorkbenchError('invalid_task', 'Invalid task ID')
        return self.directory / (task_id + '.json')

    def _save(self, task):
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self._path(task['task_id'])
        temporary = self.directory / (uuid4().hex + '.tmp')
        try:
            temporary.write_text(json.dumps(task, indent=2), encoding='utf-8')
            for attempt in range(5):
                try:
                    os.replace(temporary, path)
                    break
                except PermissionError:
                    if attempt==4:
                        raise
                    time.sleep(.02 * (attempt+1))
        finally:
            temporary.unlink(missing_ok=True)

    def create(self, kind, document_ids):
        task = {'task_id': uuid4().hex, 'kind': kind, 'state': 'created',
                'created_at': time.time(), 'document_ids': list(document_ids),
                'steps': [], 'checks': {}}
        self._save(task)
        return task

    def read(self, task_id):
        path = self._path(task_id)
        if not path.is_file():
            raise WorkbenchError('invalid_task', 'Task not found')
        return json.loads(path.read_text(encoding='utf-8'))

    def step(self, task, name, details):
        if task['state'] not in ('created', 'running') or len(task['steps']) >= 8:
            raise WorkbenchError('invalid_state', 'Task step budget or state invalid')
        task['state'] = 'running'
        task['steps'].append({'name': name, 'at': time.time(), 'details': details})
        self._save(task)

    def complete(self, task, checks):
        if task['state'] != 'running' or not checks or not all(checks.values()):
            raise WorkbenchError('invalid_state', 'Task checks did not pass')
        task['checks'] = checks
        task['state'] = 'completed'
        task['finished_at'] = time.time()
        self._save(task)

    def fail(self, task, code):
        task['state'] = 'failed'
        task['error_code'] = code
        task['finished_at'] = time.time()
        self._save(task)

    def needs_input(self, task, code):
        task['state'] = 'needs_input'
        task['error_code'] = code
        task['finished_at'] = time.time()
        self._save(task)

    def record_agent(self, task, agent):
        """Persist the orchestrator's authoritative state and bounded event history."""
        task['agent_state'] = agent.state.value
        task['agent_history'] = agent.history
        task['step_count'] = agent.step_count
        task['repair_count'] = agent.repair_count
        self._save(task)
