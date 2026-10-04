import json

import pytest

from scripts.eval_runner import run_evaluation


class FakeWorkbench:
    def ask(self, question, document_ids=None):
        return {'status': 'answered', 'answer': 'Pump P-101 reached 8.2 mm/s [S1].',
                'checks': {'citation_ids_valid': True}, 'sources': [{'label': 'S1'}]}


def test_eval_checks_content_and_keeps_raw_result(tmp_path):
    tasks = tmp_path / 'tasks.json'
    tasks.write_text(json.dumps([{'id': 'pump', 'question': 'What did P-101 reach?',
                                  'expected_status': 'answered', 'required_terms': ['8.2 mm/s'],
                                  'forbidden_terms': ['shutdown']}]), encoding='utf-8')
    result_file = tmp_path / 'results.json'
    assert run_evaluation(FakeWorkbench(), tasks, result_file)
    result = json.loads(result_file.read_text(encoding='utf-8'))
    assert result['passed'] == 1
    assert result['results'][0]['result']['sources'] == [{'label': 'S1'}]


def test_eval_rejects_empty_task_set(tmp_path):
    tasks = tmp_path / 'tasks.json'
    tasks.write_text('[]', encoding='utf-8')
    with pytest.raises(ValueError, match='nonempty'):
        run_evaluation(FakeWorkbench(), tasks, tmp_path / 'results.json')
