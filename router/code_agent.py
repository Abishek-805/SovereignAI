"""Bounded tool-feedback runner; authority remains with registered tools and caller."""
from dataclasses import dataclass
from typing import Any, Callable, Mapping
from types import MappingProxyType
from backend.contracts import WorkbenchError
from router.tool_registry import ToolRegistry
from router.validation_feedback import failure_fingerprint

def _freeze(value):
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value

@dataclass(frozen=True)
class Action:
    tool: str
    arguments: Mapping[str, Any]

    @classmethod
    def parse(cls, value):
        if not isinstance(value, dict) or set(value) != {'tool', 'arguments'}:
            raise WorkbenchError('tool_input', 'Code action requires exactly tool and arguments')
        if not isinstance(value['tool'], str) or not value['tool'].strip() or not isinstance(value['arguments'], dict):
            raise WorkbenchError('tool_input', 'Code action has invalid tool or arguments')
        return cls(value['tool'], dict(value['arguments']))

@dataclass(frozen=True)
class Observation:
    result: Mapping[str, Any]
    state: str
    validation_executed: bool
    feedback: str = ''
    validation_exit_code: int | None = None

    @classmethod
    def from_result(cls, result):
        if not isinstance(result, dict) or not isinstance(result.get('state'), str):
            raise WorkbenchError('tool_execution_failed', 'Code tool returned an invalid observation')
        checks = result.get('checks', {})
        executed = isinstance(checks, dict) and checks.get('container_executed') is True
        exit_code = result.get('validation_exit_code')
        if exit_code is not None and (not isinstance(exit_code, int) or isinstance(exit_code, bool)):
            raise WorkbenchError('tool_execution_failed', 'Code tool returned an invalid validation exit code')
        feedback = result.get('stderr') or result.get('stdout') or ''
        if not isinstance(feedback, str):
            raise WorkbenchError('tool_execution_failed', 'Code tool returned invalid validation feedback')
        return cls(_freeze(result), result['state'], executed, feedback[-3000:], exit_code)

@dataclass(frozen=True)
class RepairDecision:
    retry: bool
    stop_reason: str
    fingerprint: str | None = None


def repair_decision(observation: Observation, attempt: int, seen: set[str] | frozenset[str], max_attempts: int = 3) -> RepairDecision:
    """Pure policy over observed tool results; attempt is one-based."""
    if observation.state != 'failed':
        validated = observation.state == 'completed' and observation.validation_executed and observation.validation_exit_code == 0
        return RepairDecision(False, 'validated' if validated else 'unverified' if observation.state == 'completed' else 'not_applicable')
    contract_checked=observation.result.get('checks',{}).get('request_contract_checked') is True
    if not observation.validation_executed and not contract_checked:
        return RepairDecision(False, 'validation_unavailable')
    fingerprint = failure_fingerprint(observation.feedback)
    if not observation.feedback:
        return RepairDecision(False, 'missing_feedback', fingerprint)
    if fingerprint in seen:
        return RepairDecision(False, 'repeated_failure', fingerprint)
    if attempt >= max_attempts:
        return RepairDecision(False, 'attempt_budget', fingerprint)
    return RepairDecision(True, 'repair_pending', fingerprint)

@dataclass(frozen=True)
class RunResult:
    last_result: Mapping[str, Any]
    observations: tuple[Observation, ...]
    attempts: int
    stop_reason: str
    failure_fingerprints: tuple[str, ...]

class CodeAgent:
    """Executes only caller-admitted registered actions; never chooses a model.

    Registered tools retain scope, validation, lease and publication controls.
    The action producer receives actual observations; it cannot manufacture a
    completion action. Callbacks may persist state/progress outside this runner.
    """
    def __init__(self, registry: ToolRegistry, *, allowed_tools: tuple[str, ...], max_attempts: int = 3):
        if not isinstance(max_attempts, int) or isinstance(max_attempts, bool) or not 1 <= max_attempts <= 3:
            raise ValueError('max_attempts must be between 1 and 3')
        if not allowed_tools or any(name not in registry.tools for name in allowed_tools):
            raise ValueError('allowed_tools must reference existing registered tools')
        self.registry = registry
        self.allowed_tools = frozenset(allowed_tools)
        self.max_attempts = max_attempts

    def run(self, produce_action: Callable, *, observe_result: Callable = Observation.from_result,
            cancelled: Callable[[], bool] | None = None, before_attempt: Callable | None = None,
            after_observation: Callable | None = None) -> RunResult:
        observations = []
        failures = set()
        for attempt in range(1, self.max_attempts + 1):
            if cancelled and cancelled():
                raise WorkbenchError('cancelled', 'Task stopped before code attempt')
            if before_attempt:
                before_attempt(attempt, tuple(observations))
            action = produce_action(attempt, tuple(observations))
            if isinstance(action, Action):
                action = Action.parse({'tool': action.tool, 'arguments': action.arguments})
            else:
                action = Action.parse(action)
            if action.tool not in self.allowed_tools:
                raise WorkbenchError('tool_input', 'Code action is outside the admitted tool scope')
            if cancelled and cancelled():
                raise WorkbenchError('cancelled', 'Task stopped before code tool execution')
            raw = self.registry.execute(action.tool, dict(action.arguments))
            observation = observe_result(raw)
            if not isinstance(observation, Observation):
                raise WorkbenchError('tool_execution_failed', 'Code observer returned an invalid observation')
            observation = Observation(_freeze(observation.result), observation.state, observation.validation_executed,
                                      observation.feedback, observation.validation_exit_code)
            observations.append(observation)
            decision = repair_decision(observation, attempt, failures, self.max_attempts)
            if decision.fingerprint:
                failures.add(decision.fingerprint)
            if after_observation:
                after_observation(attempt, observation, decision, frozenset(failures))
            if not decision.retry:
                return RunResult(raw, tuple(observations), attempt, decision.stop_reason, tuple(sorted(failures)))
        raise AssertionError('bounded runner exhausted without a stop decision')
