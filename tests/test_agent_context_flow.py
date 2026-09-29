"""Agent dispatch preserves context without speculative retrieval or stopped answers."""
import pytest

from backend.contracts import WorkbenchError
from backend.jobs import Job
from tests.test_service import service


def planned(action, response='Plan from the model'):
    return {'action': action, 'target': '', 'expression': '', 'response': response}


@pytest.mark.parametrize('action', ['search_documents', 'create_report'])
def test_document_action_retrieves_only_in_dispatched_workflow(service, monkeypatch, action):
    """A selection is metadata until the chosen workflow needs actual evidence."""
    monkeypatch.setattr(service, 'documents', lambda: [
        {'document_id': 'selected', 'display_name': 'Assessment.pdf'}])
    service.model.plan_task = lambda *_: planned(action)

    def premature_read(*_, **__):
        raise AssertionError('Dispatch must not load vectors or prefetch unused evidence')

    monkeypatch.setattr(service.store, 'active_chunks', premature_read)
    monkeypatch.setattr(type(service), 'embedder', property(premature_read))
    calls = []
    history = ['User: Tell me about Abishek', 'Assistant: His assessment is connected.']

    def workflow(question, ids, history=None, job=None, **kwargs):
        calls.append((question, ids, history, kwargs))
        return {'status': 'answered', 'answer': 'Excellent [S1].', 'sources': []}

    monkeypatch.setattr(service, 'ask' if action == 'search_documents' else 'create_document_report', workflow)
    result = service.run_auto_agent('What rating did he receive?', ['selected'], history=history)
    assert result['answer'] == 'Excellent [S1].'
    assert calls == [('What rating did he receive?', ['selected'], history,
                      {'force_documents': True} if action == 'search_documents' else {})]


def test_planner_keeps_up_to_eight_complete_recent_conversation_pairs(service):
    history = [entry for index in range(5)
               for entry in (f'User: Question {index}', f'Assistant: Answer {index}')]
    seen = []

    def plan(goal, documents, files, context):
        seen.append(context)
        return planned('answer', 'A natural model answer')

    service.model.plan_task = plan
    result = service.run_auto_agent('Continue explaining', history=history)
    assert result['answer'] == 'A natural model answer'
    assert seen[0][:-1] == history[-16:]
    assert seen[0][0] == 'User: Question 0'


def test_stop_during_intent_generation_does_not_complete_answer(service, monkeypatch):
    job = Job('agent')
    completed = []
    monkeypatch.setattr(service.tasks, 'complete', lambda *args: completed.append(args))

    def plan(*args):
        job.cancel.set()
        return planned('answer', 'This answer must not complete after Stop')

    service.model.plan_task = plan
    with pytest.raises(WorkbenchError) as error:
        service.run_auto_agent('How are you?', job=job)
    assert error.value.code == 'cancelled'
    assert not completed
    assert not service.ask_lock.locked()


def test_connected_context_unrelated_answer_never_reads_evidence(service, monkeypatch):
    monkeypatch.setattr(service, 'documents', lambda: [
        {'document_id': 'selected', 'display_name': 'Inspection.pdf'}])

    def unexpected(*args, **kwargs):
        raise AssertionError('General answers must not inspect connected document contents')

    monkeypatch.setattr(service.store, 'active_chunks', unexpected)
    monkeypatch.setattr(service.coding, 'get', lambda *_: {'files':[{'name':'notes.md'}]})
    monkeypatch.setattr(service.coding, 'read', unexpected)
    service.model.plan_task = lambda *_: planned('answer', 'Paris is the capital of France.')
    result = service.run_auto_agent('What is the capital of France?', ['selected'], workspace_id='unused')
    assert result['answer'] == 'Paris is the capital of France.'
    assert [step['name'] for step in result['steps']] == ['plan']


def test_repair_vocabulary_does_not_override_document_intent(service, monkeypatch):
    """A model-selected evidence workflow cannot be promoted to a code write."""
    monkeypatch.setattr(service, 'documents', lambda: [
        {'document_id': 'selected', 'display_name': 'Project repair notes.txt'}])
    service.model.plan_task = lambda *_: planned('search_documents')
    monkeypatch.setattr(service.coding, 'get', lambda *_: {'files':[{'name':'notes.md'}]})
    monkeypatch.setattr(service.coding, 'read', lambda *_: pytest.fail('Unexpected project read'))
    monkeypatch.setattr(service, 'run_coding_project_task', lambda *_: pytest.fail('Unexpected edit'))
    monkeypatch.setattr(service, 'ask', lambda *_, **__: {
        'status': 'answered', 'answer': 'The notes describe how to fix errors in the project [S1].'})
    result = service.run_auto_agent('Explain how to fix errors in the project described in the notes',
                                    ['selected'], workspace_id='unused')
    assert result['plan']['action'] == 'search_documents'
    assert 'notes describe' in result['answer']
