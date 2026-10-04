"""Isolated task contract for the replacement kernel; no production entry point.

Execution, resource ownership and publication remain with existing adapters.
"""
from dataclasses import dataclass
import json
from uuid import uuid4


@dataclass(frozen=True)
class TaskRoot:
    task_id: str
    request: str
    workspace_id: str
    workspace_revision: str
    task_type: str
    requirements: tuple[str, ...]
    context_manifest: tuple[str, ...]
    model: str
    max_model_calls: int = 8
    max_sandbox_runs: int = 4

    def __post_init__(self):
        for name in ('task_id', 'request', 'workspace_id', 'workspace_revision', 'task_type', 'model'):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f'{name} must be nonempty text')
        for name in ('requirements', 'context_manifest'):
            value = getattr(self, name)
            if not isinstance(value, tuple) or any(not isinstance(item, str) for item in value):
                raise ValueError(f'{name} must be an immutable tuple of text')
        for name in ('max_model_calls', 'max_sandbox_runs'):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f'{name} must be a positive integer')

    @classmethod
    def create(cls, **fields):
        return cls(task_id=str(uuid4()), **fields)

    def context(self, *, workspace_id, workspace_revision, current_state, current_diff='',
                actual_error='', test_result=''):
        """Build one task-bound call; never merge another task's chat history."""
        if workspace_id != self.workspace_id or workspace_revision != self.workspace_revision:
            raise ValueError('Task workspace identity or snapshot revision changed')
        observations = (current_state, current_diff, actual_error, test_result)
        if any(not isinstance(value, str) for value in observations):
            raise ValueError('Observations must be text')
        return json.dumps({
            'task_id': self.task_id, 'original_request': self.request,
            'workspace_id': self.workspace_id, 'snapshot_revision': self.workspace_revision,
            'task_type': self.task_type, 'requirements': self.requirements,
            'context_manifest': self.context_manifest, 'selected_model': self.model,
            'current_state': current_state, 'current_diff': current_diff,
            'actual_error': actual_error, 'test_result': test_result,
        }, ensure_ascii=False)
