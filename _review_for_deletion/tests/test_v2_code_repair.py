"""Unit contracts for bounded repair; these do not claim live Docker proof."""
import json
from types import SimpleNamespace
import pytest
from backend.contracts import WorkbenchError
from tests.test_service import service
from tests.test_coding_workspace import workspace, Model
from router.sandbox import SandboxResult
from router.task_ledger import TaskLedger
from tests.test_coding_project import ProjectModel, Sandbox
from workflows.coding_workspace import CodingWorkspace


def prepare(service, monkeypatch):
    wid=service.coding.create('Repair contract')['workspace_id']
    service.coding.write(wid,'solution.py','def f():\n    return 0\n')
    monkeypatch.setattr(service,'_verified_coding_sandbox',lambda:SimpleNamespace(_ready=lambda:None))
    return wid


def test_repair_preserves_structured_candidate_identity_and_persists_counts(service,monkeypatch):
    wid=prepare(service,monkeypatch); calls=[]; saved=[]
    monkeypatch.setattr(service.coding,'_save_result',lambda workspace,result:saved.append(json.loads(json.dumps(result))))
    def run(*args,**kwargs):
        calls.append(kwargs['history'])
        return {'task_id':'unit','state':'failed' if len(calls)==1 else 'completed',
                'checks':{'container_executed':True},'stderr':'actual error',
                'changes':[{'action':'edit','path':'solution.py','after':'x'*12000}]}
    monkeypatch.setattr(service.coding,'run_project',run)
    result=service.run_coding_project_task(wid,'solution.py','Fix solution.py',routed=True)
    context=json.loads(calls[1][-1].split('\n',1)[1])
    assert context['previous_candidate'][0]['path']=='solution.py'
    assert context['previous_candidate'][0]['content_complete'] is False
    assert len(context['previous_candidate'][0]['sha256'])==64
    assert context['original_request']=='Fix solution.py'
    assert context['workspace_id']==wid
    assert context['actual_error']=='actual error'
    assert saved[-1]['supervisor_attempts']==result['supervisor_attempts']==2
    assert saved[-1]['repair_count']==1


def test_external_revision_change_stops_before_retry(service,monkeypatch):
    wid=prepare(service,monkeypatch); calls=[]
    def run(*args,**kwargs):
        calls.append(True)
        service.coding.write(wid,'solution.py','def f():\n    return 99\n')
        return {'state':'failed','checks':{'container_executed':True},'stderr':'actual error','changes':[]}
    monkeypatch.setattr(service.coding,'run_project',run)
    with pytest.raises(WorkbenchError) as error:
        service.run_coding_project_task(wid,'solution.py','Fix solution.py',routed=True)
    assert error.value.code=='workspace_conflict'
    assert len(calls)==1


@pytest.mark.parametrize('executed,count',[(False,1),(True,2)])
def test_legacy_repair_stops_unavailable_or_repeated_failure(tmp_path,executed,count):
    work,wid=workspace(tmp_path); generated=[]
    class Generator:
        def complete_code(self,*args,**kwargs):
            generated.append(True)
            return {'code':'def add(a,b):\n    return a-b\n'}
    class Validator:
        def _ready(self):pass
        def execute(self,*args,**kwargs):return SandboxResult(1,'','same actual failure',executed,{})
    result=work.run(wid,'solution.py','Update the addition function',Generator(),Validator(),TaskLedger(tmp_path/'ledger'))
    assert len(generated)==count
    assert result['state']=='failed'
    assert result['repair_stop_reason']==('validation_unavailable' if not executed else 'repeated_failure')


@pytest.mark.parametrize('mode,independent',[
    ('unchanged',True),('created',False),('edited',False),('extra',False)])
def test_goal_check_provenance_excludes_model_authored_tests(tmp_path,mode,independent):
    work=CodingWorkspace(tmp_path);wid=work.create('Goal checks')['workspace_id']
    work.write(wid,'solution.py','def answer():\n    return 0\n')
    original_test='import unittest\nclass Checks(unittest.TestCase):\n    def test_answer(self):\n        self.assertEqual(1, 1)\n'
    if mode!='created':work.write(wid,'test_solution.py',original_test)
    operations=[{'action':'edit','path':'solution.py','reason':'requested'}]
    codes=['def answer():\n    return 1\n']
    if mode in {'created','edited','extra'}:
        path='test_extra.py' if mode=='extra' else 'test_solution.py'
        operations.append({'action':'edit' if mode=='edited' else 'create','path':path,'reason':'requested tests'})
        codes.append('import unittest\nclass Checks(unittest.TestCase):\n    def test_answer(self):\n        self.assertTrue(True)\n')
    result=work.run_project(wid,'solution.py','Update the solution and the requested project tests',
        ProjectModel(operations,*codes),Sandbox(),TaskLedger(tmp_path/'ledger'))
    assert result['checks']['tests_passed'] is True
    assert result['goal_checks_independent'] is independent
    assert work.result(wid,result['task_id'])['goal_checks_independent'] is independent


def test_legacy_supplied_checks_provenance_is_independent(tmp_path):
    work,wid=workspace(tmp_path)
    from tests.test_coding_workspace import Sandbox as AdditionSandbox
    result=work.run(wid,'solution.py','Fix add',Model('def add(a, b):\n    return a + b\n'),
        AdditionSandbox(),TaskLedger(tmp_path/'ledger'))
    assert result['goal_checks_independent'] is True
