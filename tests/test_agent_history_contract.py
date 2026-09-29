"""Regression for Code chat growing beyond the agent request history limit."""
import time

from fastapi.testclient import TestClient
from backend.app import create_app
from tests.test_service import service


def test_agent_job_accepts_eight_exchanges_and_rejects_oversized_history(service, monkeypatch):
    calls = []

    def run(goal, documents, workspace, history, job):
        calls.append((goal, history))
        return {'status': 'answered', 'answer': 'A model response'}

    monkeypatch.setattr(service, 'run_auto_agent', run)
    history = [item for index in range(8) for item in
               (f'User: Question {index}', f'Assistant: Answer {index}')]
    with TestClient(create_app(service), base_url='http://127.0.0.1:8088') as client:
        rejected = client.post('/agent/jobs', json={'goal': 'hi', 'history': history + ['extra']})
        assert rejected.status_code == 422
        assert rejected.json()['detail'][0]['loc'] == ['body', 'history']
        assert not calls
        accepted = client.post('/agent/jobs', json={'goal': 'how are you?', 'history': history})
        assert accepted.status_code == 200, accepted.text
        job_id = accepted.json()['job_id']
        for _ in range(100):
            job = client.get(f'/coding/jobs/{job_id}').json()
            if job['state'] != 'running':
                break
            time.sleep(0.01)
        assert job['state'] == 'completed'
        assert job['result']['answer'] == 'A model response'
        assert calls == [('how are you?', history)]
