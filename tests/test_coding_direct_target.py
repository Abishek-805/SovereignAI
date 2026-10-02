import pytest

from router.task_ledger import TaskLedger
from tests.test_coding_project import ProjectModel, Sandbox
from workflows.coding_workspace import CodingWorkspace


@pytest.mark.parametrize('existing,instruction', [
    (True, 'Fix the syntax error in main.py'),
    (True, 'Add a double function to this file'),
    (False, 'Create main.py containing a double function'),
])
def test_clear_single_target_skips_model_plan(tmp_path, existing, instruction):
    work = CodingWorkspace(tmp_path)
    wid = work.create('Direct')['workspace_id']
    if existing:
        work.write(wid, 'main.py', 'def double(x): return x\n')
    work.write(wid, 'other.py', 'print("preserve")\n')
    class DirectModel(ProjectModel):
        def plan_workspace_edit(self, *args, **kwargs):
            pytest.fail('Clear single-target task must not generate a workspace plan')
    model = DirectModel([], 'def double(x): return x * 2\n')
    sandbox = Sandbox()
    result = work.run_project(wid, 'main.py', instruction, model, sandbox, TaskLedger(tmp_path))
    assert result['publication_state'] == 'staged'
    assert result['checks']['container_executed'] is True
    assert [change['path'] for change in result['changes']] == ['main.py']
    assert sandbox.snapshots[0]['main.py'] == b'def double(x): return x * 2\n'
    assert work.read(wid, 'other.py')['content'] == 'print("preserve")\n'


@pytest.mark.parametrize('instruction', [
    'Refactor authentication across the project',
    'Fix main.py and other.py',
    'Create a script',
    'Explain main.py',
    'Delete main.py',
])
def test_ambiguous_or_non_edit_request_keeps_planner(tmp_path, instruction):
    work = CodingWorkspace(tmp_path)
    wid = work.create('Scoped')['workspace_id']
    work.write(wid, 'main.py', 'print(1)\n')
    work.write(wid, 'other.py', 'print(2)\n')
    class PlannerReached(Exception):
        pass
    class Model:
        def plan_workspace_edit(self, *args, **kwargs):
            raise PlannerReached()
    if instruction == 'Delete main.py':
        result = work.run_project(wid, 'main.py', instruction, Model(), Sandbox(), TaskLedger(tmp_path))
        assert result['changes'][0]['action'] == 'delete'
    else:
        with pytest.raises(PlannerReached):
            work.run_project(wid, 'main.py', instruction, Model(), Sandbox(), TaskLedger(tmp_path))
