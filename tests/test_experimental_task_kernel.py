"""Task isolation checks; these tests execute no generated code."""
import json
import unittest
import tempfile
from pathlib import Path
from dataclasses import FrozenInstanceError
from experiments.task_kernel import TaskRoot
from experiments.minimal_execution import MinimalKernel, TaskBudget, project_map


class TaskKernelTests(unittest.TestCase):
    def make_task(self, request='Create an AI/ML text document'):
        return TaskRoot.create(request=request, workspace_id='selected-workspace',
                               workspace_revision='snapshot-1', task_type='agent',
                               requirements=('Create a text document',),
                               context_manifest=('notes.txt',), model='fixed-worker')

    def test_new_task_does_not_reuse_old_request(self):
        old = self.make_task('Create a receipt parser')
        new = self.make_task()
        context = new.context(workspace_id='selected-workspace', workspace_revision='snapshot-1',
                              current_state='notes.txt exists', actual_error='write failed')
        self.assertNotEqual(old.task_id, new.task_id)
        self.assertNotIn('receipt parser', context)
        self.assertEqual(json.loads(context)['original_request'], new.request)

    def test_model_and_request_are_immutable(self):
        task = self.make_task()
        with self.assertRaises(FrozenInstanceError):
            task.model = 'another-model'
        with self.assertRaises(ValueError):
            TaskRoot.create(request='x', workspace_id='w', workspace_revision='r', task_type='code',
                            requirements=['mutable'], context_manifest=(), model='m')

    def test_repair_keeps_request_and_real_feedback(self):
        task = self.make_task()
        context = json.loads(task.context(workspace_id=task.workspace_id,
                                         workspace_revision=task.workspace_revision,
                                         current_state='candidate', current_diff='+new file',
                                         actual_error='PermissionError: denied', test_result='exit 1'))
        self.assertEqual(context['original_request'], task.request)
        self.assertEqual(context['actual_error'], 'PermissionError: denied')
        self.assertEqual(context['selected_model'], task.model)

    def test_wrong_workspace_or_revision_rejected(self):
        task = self.make_task()
        for workspace, revision in (('other','snapshot-1'), ('selected-workspace','snapshot-2')):
            with self.assertRaises(ValueError):
                task.context(workspace_id=workspace, workspace_revision=revision, current_state='')

    def test_unconfirmed_execution_cannot_finish(self):
        task = self.make_task()
        model = lambda *args: ({'action':'finish','reason':'done'},1)
        kernel = MinimalKernel(task,{},model,None,lambda *args: {
            'docker_executed':False,'exit_code':0,'stdout':'','stderr':''})
        self.assertEqual(kernel.run()['state'],'BLOCKED')

    def test_token_overrun_cannot_run_action(self):
        task = self.make_task()
        model = lambda *args: ({'action':'finish','reason':'done'},100)
        kernel = MinimalKernel(task,{},model,None,None,TaskBudget(max_output_tokens=10))
        self.assertEqual(kernel.run()['state'],'BUDGET_EXHAUSTED')
        self.assertEqual(kernel.counts['sandbox_runs'],0)

    def test_project_map_marks_conventions_as_candidates(self):
        mapping = project_map({'main.py':'print(1)','pyproject.toml':'[project]\nname="app"'})
        self.assertIn('not a documented entry point',mapping['commands'][0]['basis'])

    def test_budget_rejects_nonfinite_deadline(self):
        with self.assertRaises(ValueError):
            TaskBudget(timeout_seconds=float('nan'))

    def test_plain_output_parsed_and_trajectory_saved(self):
        class Adapter:
            last_usage = {'completion_tokens':1}
            def generate(self, messages, **settings):
                return '{"action":"finish","reason":"done"}'
        validator = lambda *args: {'docker_executed':True,'exit_code':0,'stdout':'ok','stderr':''}
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'trajectory.json'
            kernel = MinimalKernel(self.make_task(),{},Adapter(),None,validator,record_path=path)
            self.assertEqual(kernel.run()['state'],'READY_FOR_REVIEW')
            saved = json.loads(path.read_text())
            self.assertEqual(saved['events'][0]['model_output'],'{"action":"finish","reason":"done"}')
            self.assertEqual(saved['events'][1]['observation']['exit_code'],0)


if __name__ == '__main__':
    unittest.main()
