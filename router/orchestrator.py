import logging
import time
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Callable

from backend.contracts import WorkbenchError
from router.tool_registry import ToolRegistry
from router.model_registry import ModelRegistry

logger = logging.getLogger(__name__)

class TaskState(Enum):
    CREATED = "created"
    PLANNING = "planning"
    RUNNING = "running"
    CHECKING = "checking"
    COMPLETED = "completed"
    REPAIRING = "repairing"
    NEEDS_INPUT = "needs_input"
    FAILED = "failed"
    CANCELLED = "cancelled"

ALLOWED_TRANSITIONS = {
    TaskState.CREATED: {TaskState.PLANNING, TaskState.RUNNING, TaskState.CANCELLED, TaskState.FAILED},
    TaskState.PLANNING: {TaskState.RUNNING, TaskState.NEEDS_INPUT, TaskState.CANCELLED, TaskState.FAILED},
    TaskState.RUNNING: {TaskState.CHECKING, TaskState.REPAIRING, TaskState.NEEDS_INPUT, TaskState.CANCELLED, TaskState.FAILED},
    TaskState.CHECKING: {TaskState.PLANNING, TaskState.COMPLETED, TaskState.REPAIRING, TaskState.FAILED},
    TaskState.REPAIRING: {TaskState.RUNNING, TaskState.NEEDS_INPUT, TaskState.CANCELLED, TaskState.FAILED},
    TaskState.NEEDS_INPUT: {TaskState.PLANNING, TaskState.CANCELLED, TaskState.FAILED},
    TaskState.COMPLETED: set(), TaskState.FAILED: set(), TaskState.CANCELLED: set()
}

@dataclass
class OrchestratorTask:
    task_id: str
    prompt: str
    state: TaskState = TaskState.CREATED
    history: List[Dict[str, Any]] = field(default_factory=list)
    step_count: int = 0
    repair_count: int = 0
    max_steps: int = 8
    max_repairs: int = 2
    on_change: Optional[Callable] = field(default=None, repr=False)
    
    def transition(self, new_state: TaskState, reason: str = ""):
        if new_state != self.state and new_state not in ALLOWED_TRANSITIONS[self.state]:
            raise WorkbenchError('invalid_state', f'Cannot move from {self.state.value} to {new_state.value}')
        if new_state == TaskState.COMPLETED:
            raise WorkbenchError('invalid_state', 'Use complete_task with verified checks')
        self.state = new_state
        self.history.append({
            "timestamp": time.time(),
            "state": new_state.value,
            "reason": reason
        })
        if self.on_change:
            self.on_change(self)
        logger.info(f"Task {self.task_id} transitioned to {new_state.value}: {reason}")

class Orchestrator:
    def __init__(self, tools: ToolRegistry, models: ModelRegistry):
        self.tools = tools
        self.models = models
        self.tasks: Dict[str, OrchestratorTask] = {}
        
    def create_task(self, task_id: str, prompt: str, on_change=None) -> OrchestratorTask:
        if task_id in self.tasks:
            raise WorkbenchError('invalid_task', 'Task ID already exists')
        task = OrchestratorTask(task_id=task_id, prompt=prompt, on_change=on_change)
        task.transition(TaskState.CREATED, "Task initialized")
        self.tasks[task_id] = task
        return task

    def complete_task(self, task_id: str, checks: Dict[str, bool]):
        task = self.tasks.get(task_id)
        if task is None:
            raise WorkbenchError('invalid_task', 'Task not found')
        if task.state != TaskState.CHECKING or not checks or not all(value is True for value in checks.values()):
            raise WorkbenchError('invalid_state', 'Required checks have not passed')
        task.history.append({'timestamp': time.time(), 'checks': checks})
        task.state = TaskState.COMPLETED
        task.history.append({'timestamp': time.time(), 'state': TaskState.COMPLETED.value, 'reason': 'Checks passed'})
        if task.on_change:
            task.on_change(task)
        return task
        
    def run_step(self, task_id: str, tool_name: str, kwargs: dict, *, retryable=True):
        task = self.tasks.get(task_id)
        if not task:
            raise WorkbenchError('invalid_task', "Task not found")
            
        if task.state not in (TaskState.CREATED, TaskState.PLANNING, TaskState.RUNNING, TaskState.REPAIRING):
            raise WorkbenchError('invalid_state', f"Cannot run step from state {task.state.value}")
            
        if task.step_count >= task.max_steps:
            task.transition(TaskState.FAILED, "Budget exhausted")
            raise WorkbenchError('step_limit', 'Agent step budget exhausted')
            
        task.step_count += 1
        task.transition(TaskState.RUNNING, f"Executing {tool_name}")
        
        try:
            result = self.tools.execute(tool_name, kwargs)
            recorded = ({key: result[key] for key in ('status', 'state', 'task_id', 'answer', 'rounded')
                         if key in result} if isinstance(result, dict) else {'type': type(result).__name__})
            if 'answer' in recorded:
                recorded['answer'] = str(recorded['answer'])[:500]
            task.history.append({
                "tool": tool_name,
                "inputs": sorted(kwargs),
                "result": recorded,
                "status": "success"
            })
            task.transition(TaskState.CHECKING, "Tool execution completed")
        except WorkbenchError as e:
            task.history.append({
                "tool": tool_name,
                "kwargs": kwargs,
                "error": str(e),
                "status": "error"
            })
            if retryable and task.repair_count < task.max_repairs:
                task.repair_count += 1
                task.transition(TaskState.REPAIRING, f"Attempting repair ({task.repair_count}/{task.max_repairs})")
            else:
                task.transition(TaskState.FAILED, "Tool failed" if not retryable else "Repair budget exhausted")
            if not retryable:
                raise
        return result if task.state == TaskState.CHECKING else None
