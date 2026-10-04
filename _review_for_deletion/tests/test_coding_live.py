"""Opt-in live container test; set SOVEREIGN_LIVE_SANDBOX_IMAGE to run."""
import csv
import io
import os
import pytest

from backend.settings import Settings
from router.sandbox import CodeSandbox
from router.task_ledger import TaskLedger
from workflows.coding import run_csv_demo
from workflows.coding_workspace import CodingWorkspace

IMAGE = os.environ.get('SOVEREIGN_LIVE_SANDBOX_IMAGE')

GOOD_CODE = '''import csv
from collections import defaultdict
totals = defaultdict(int)
with open('/input/data.csv', newline='') as source:
    reader = csv.DictReader(source)
    if not reader.fieldnames or not {'category', 'value'} <= set(reader.fieldnames):
        raise ValueError('Missing required columns')
    for row in reader:
        try:
            totals[row['category']] += int(row['value'])
        except (ValueError, TypeError):
            raise ValueError('Invalid value')
with open('/output/result.csv', 'w', newline='') as target:
    writer = csv.writer(target)
    writer.writerow(['category', 'total'])
    for category in sorted(totals):
        writer.writerow([category, totals[category]])
'''


@pytest.mark.skipif(not IMAGE, reason='Live Docker image ID not supplied')
def test_live_result_file_is_readable_on_host(tmp_path):
    sandbox = CodeSandbox('docker', image_id=IMAGE, task_root=tmp_path/'runs')
    result = sandbox.execute(GOOD_CODE, input_files={'data.csv': b'category,value\nA,2\nA,5\n'})
    assert result.executed and result.exit_code == 0, result.stderr
    assert list(csv.DictReader(io.StringIO(result.output_files['result.csv'].decode('utf-8')))) == [
        {'category': 'A', 'total': '7'}
    ]


@pytest.mark.skipif(not IMAGE, reason='Live Docker image ID not supplied')
def test_live_csv_workflow(tmp_path):
    class Model:
        def complete_code(self,messages):
            return {'code':GOOD_CODE}
    settings=Settings(data_dir=tmp_path/'data')
    sandbox=CodeSandbox('docker',image_id=IMAGE,task_root=tmp_path/'runs')
    ledger=TaskLedger(settings.data_dir)
    result=run_csv_demo(Model(),sandbox,ledger,settings)
    assert result['status']=='completed'
    assert result['attempts']==1
    assert all(result['checks'].values())
    assert ledger.read(result['task_id'])['state']=='completed'


@pytest.mark.skipif(not IMAGE, reason='Live Docker image ID not supplied')
def test_live_csv_workflow_bounded_failure(tmp_path):
    class BrokenModel:
        def complete_code(self,messages):
            return {'code':'print("no result")'}
    settings=Settings(data_dir=tmp_path/'data')
    sandbox=CodeSandbox('docker',image_id=IMAGE,task_root=tmp_path/'runs')
    ledger=TaskLedger(settings.data_dir)
    result=run_csv_demo(BrokenModel(),sandbox,ledger,settings)
    assert result['status']=='failed'
    assert result['attempts']==3
    assert not all(result['checks'].values())
    trace=ledger.read(result['task_id'])
    assert trace['state']=='failed'
    assert trace['error_code']=='trusted_tests_failed'


@pytest.mark.skipif(not IMAGE, reason='Live Docker image ID not supplied')
def test_live_workspace_edits_only_after_container_tests(tmp_path):
    workspace = CodingWorkspace(tmp_path)
    workspace_id = workspace.create('Live Python task')['workspace_id']
    workspace.write(workspace_id, 'solution.py', 'def add(a, b):\n    return 0\n')
    workspace.write(workspace_id, 'test_solution.py',
                    'import unittest\nfrom solution import add\n\n'
                    'class AdditionTest(unittest.TestCase):\n'
                    '    def test_add(self):\n'
                    '        self.assertEqual(add(2, 3), 5)\n')
    class Model:
        def complete_code(self, messages, max_tokens=1024):
            return {'code': 'def add(a, b):\n    return a + b\n'}
    sandbox = CodeSandbox('docker', image_id=IMAGE, task_root=tmp_path/'runs')
    result = workspace.run(workspace_id, 'solution.py', 'Make add sum its arguments',
                           Model(), sandbox, TaskLedger(tmp_path))
    assert result['state'] == 'completed', result['stderr']
    assert result['checks']['tests_passed']
    assert 'Ran 1 test' in result['stderr']
    assert workspace.read(workspace_id, 'solution.py')['content'].endswith('return a + b\n')


@pytest.mark.skipif(not IMAGE, reason='Live Docker image ID not supplied')
def test_live_workspace_repairs_after_failed_container_test(tmp_path):
    workspace = CodingWorkspace(tmp_path)
    workspace_id = workspace.create('Repair task')['workspace_id']
    workspace.write(workspace_id, 'solution.py', 'def add(a, b):\n    return 0\n')
    workspace.write(workspace_id, 'test_solution.py',
                    'import unittest\nfrom solution import add\n'
                    'class Check(unittest.TestCase):\n'
                    '    def test_sum(self): self.assertEqual(add(2, 3), 5)\n')
    class Model:
        def __init__(self): self.calls = 0
        def complete_code(self, messages, max_tokens=1024):
            self.calls += 1
            return {'code': 'def add(a, b):\n    return 0\n' if self.calls == 1
                    else 'def add(a, b):\n    return a + b\n'}
    model = Model()
    result = workspace.run(workspace_id, 'solution.py', 'Fix add', model,
                           CodeSandbox('docker', image_id=IMAGE, task_root=tmp_path/'runs'),
                           TaskLedger(tmp_path))
    assert result['state'] == 'completed' and result['attempts'] == 2
    assert any(event['event'] == 'test_failed' for event in result['events'])
    assert any(event['event'] == 'repair_attempt_1' for event in result['events'])
    assert workspace.read(workspace_id, 'solution.py')['content'].endswith('return a + b\n')
