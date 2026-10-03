import pytest
from backend.contracts import WorkbenchError
from router.code_agent import Action, CodeAgent, Observation, repair_decision
from router.tool_registry import ToolRegistry, ToolContract


def runner(results):
    registry = ToolRegistry()
    calls = []
    def tool(attempt):
        calls.append(attempt)
        return results[attempt - 1]
    registry.register('candidate', tool, ToolContract(('attempt',), ('attempt',)))
    return CodeAgent(registry, allowed_tools=('candidate',)), calls


def failed(error, executed=True):
    return {'state': 'failed', 'checks': {'container_executed': executed}, 'stderr': error, 'validation_exit_code': 1}


def action(attempt, observations):
    return Action('candidate', {'attempt': attempt})


def test_actual_failure_replayed_then_validated():
    agent, calls = runner([failed('TypeError: bad value'), {'state': 'completed', 'checks': {'container_executed': True}, 'validation_exit_code': 0}])
    seen = []
    def producer(attempt, observations):
        seen.append(observations)
        return action(attempt, observations)
    result = agent.run(producer)
    assert calls == [1, 2]
    assert seen[1][0].feedback == 'TypeError: bad value'
    assert result.stop_reason == 'validated' and result.attempts == 2
    assert result.last_result['validation_exit_code'] == 0


def test_repeated_real_failure_stops_before_third_call():
    agent, calls = runner([failed('TypeError: bad value')] * 3)
    result = agent.run(action)
    assert calls == [1, 2]
    assert result.stop_reason == 'repeated_failure'


def test_distinct_failures_hit_three_attempt_budget():
    agent, calls = runner([failed(f'ValueError: {i}') for i in range(3)])
    result = agent.run(action)
    assert calls == [1, 2, 3]
    assert result.stop_reason == 'attempt_budget' and len(result.failure_fingerprints) == 3


@pytest.mark.parametrize('payload, reason', [(failed('engine unavailable', False), 'validation_unavailable'), (failed(''), 'missing_feedback'), ({'state': 'needs_input'}, 'not_applicable')])
def test_no_retry_without_candidate_validation(payload, reason):
    agent, calls = runner([payload])
    assert agent.run(action).stop_reason == reason
    assert calls == [1]


@pytest.mark.parametrize('value', [{'tool': 'candidate', 'arguments': {}, 'done': True}, {'tool': 'publish', 'arguments': {}}, {'tool': 'candidate', 'arguments': []}])
def test_action_cannot_expand_scope_or_claim_done(value):
    agent, calls = runner([])
    with pytest.raises(WorkbenchError):
        agent.run(lambda *_: value)
    assert calls == []


def test_cancel_after_producer_prevents_tool():
    agent, calls = runner([])
    cancelled = [False]
    def producer(*_):
        cancelled[0] = True
        return Action('candidate', {'attempt': 1})
    with pytest.raises(WorkbenchError):
        agent.run(producer, cancelled=lambda: cancelled[0])
    assert calls == []


def test_scope_guard_error_prevents_generation():
    agent, calls = runner([])
    def guard(*_):
        raise WorkbenchError('workspace_conflict', 'Changed')
    with pytest.raises(WorkbenchError):
        agent.run(action, before_attempt=guard)
    assert calls == []


def test_same_registry_contract_rejects_invalid_arguments():
    agent, calls = runner([])
    with pytest.raises(WorkbenchError):
        agent.run(lambda *_: Action('candidate', {'attempt': 1, 'workspace': 'other'}))
    assert calls == []


def test_observation_requires_real_boolean_execution():
    observation = Observation.from_result(failed('error', 'true'))
    assert repair_decision(observation, 1, set()).stop_reason == 'validation_unavailable'


@pytest.mark.parametrize('budget', [0, 4, True])
def test_budget_cannot_be_unbounded(budget):
    registry = ToolRegistry()
    registry.register('candidate', lambda: None)
    with pytest.raises(ValueError):
        CodeAgent(registry, allowed_tools=('candidate',), max_attempts=budget)


def test_completed_state_does_not_claim_validation_without_exit_code():
    agent, calls = runner([{'state': 'completed', 'checks': {'container_executed': True}}])
    assert agent.run(action).stop_reason == 'unverified'
    assert calls == [1]


def test_observations_cannot_be_mutated_by_action_producer():
    candidate = failed('ValueError: first')
    candidate['changes'] = [{'path': 'main.py', 'after': 'bad'}]
    agent, calls = runner([candidate, {'state': 'needs_input'}])
    def producer(attempt, observations):
        if observations:
            with pytest.raises(TypeError):
                observations[0].result['changes'][0]['after'] = 'fabricated'
            with pytest.raises(TypeError):
                observations[0].result['checks']['container_executed'] = False
        return action(attempt, observations)
    agent.run(producer)
    assert candidate['changes'][0]['after'] == 'bad' and calls == [1, 2]
