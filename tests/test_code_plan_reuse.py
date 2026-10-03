import copy
import pytest
from backend.contracts import WorkbenchError
from router.sandbox import SandboxResult
from router.task_ledger import TaskLedger
from workflows.coding_workspace import CodingWorkspace


class Model:
    def __init__(self, plan):
        self.plan = plan
        self.plans = self.generations = 0
    def plan_workspace_edit(self, *args, **kwargs):
        self.plans += 1
        return copy.deepcopy(self.plan)
    def complete_code(self, *args, **kwargs):
        self.generations += 1
        return {'code': 'def value():\n    return %d\n' % self.generations}


class Sandbox:
    image_id = 'test-image'
    def __init__(self): self.inputs = []
    def _ready(self): pass
    def execute(self, code, input_files):
        self.inputs.append(copy.deepcopy(input_files))
        return SandboxResult(1 if len(self.inputs) == 1 else 0, '', 'ValueError: first candidate failed', True)


def setup(tmp_path):
    work = CodingWorkspace(tmp_path)
    wid = work.create('Reuse')['workspace_id']
    work.write(wid, 'test_value.py', 'import unittest\nclass Test(unittest.TestCase):\n    def test_ok(self): self.assertTrue(True)\n')
    model = Model({'scope':'new_files','operations':[{'action':'create','path':'value.py','reason':'implementation'}]})
    return work, wid, model, Sandbox(), TaskLedger(tmp_path)


def test_reuse_skips_only_planning_and_keeps_original_tests_and_staging(tmp_path):
    work,wid,model,sandbox,ledger = setup(tmp_path)
    first = work.run_project(wid, '', 'Implement value module', model, sandbox, ledger)
    second = work.run_project(wid, '', 'Implement value module', model, sandbox, ledger, reusable_plan=first['operation_plan'])
    assert model.plans == 1 and model.generations == 2 and len(sandbox.inputs) == 2
    assert first['state'] == 'failed'
    assert second['operation_plan'] == first['operation_plan']
    assert second['events'][0]['event'] == 'PLAN_REUSED'
    assert sandbox.inputs[0]['test_value.py'] == sandbox.inputs[1]['test_value.py']
    assert b'return 2' in sandbox.inputs[1]['value.py']
    assert not (work.files_directory(wid)/'value.py').exists()
    work.accept(wid, second['task_id'])
    assert 'return 2' in work.read(wid,'value.py')['content']


def test_stale_revision_stops_before_planner_generation_or_execution(tmp_path):
    work,wid,model,sandbox,ledger = setup(tmp_path)
    first = work.run_project(wid,'','Implement value module',model,sandbox,ledger)
    work.write(wid,'other.py','answer = 7\n')
    with pytest.raises(WorkbenchError, match='changed'):
        work.run_project(wid,'','Implement value module',model,sandbox,ledger,reusable_plan=first['operation_plan'])
    assert model.plans == model.generations == len(sandbox.inputs) == 1


@pytest.mark.parametrize('key,value',[('workspace_id','other'),('target','other.py'),('request_sha256','bad'),('plan_sha256','bad')])
def test_mismatched_or_malformed_cache_uses_fresh_authorized_plan(tmp_path,key,value):
    work,wid,model,sandbox,ledger = setup(tmp_path)
    first = work.run_project(wid,'','Implement value module',model,sandbox,ledger)
    cache = copy.deepcopy(first['operation_plan']); cache[key] = value
    second = work.run_project(wid,'','Implement value module',model,sandbox,ledger,reusable_plan=cache)
    assert model.plans == 2
    assert second['events'][0]['event'] == 'PLAN_REUSE_REJECTED'


@pytest.mark.parametrize('path,action',[('../escape.py','create'),('/escape.py','create'),('value.exe','create'),('test_value.py','delete'),('missing.py','edit')])
def test_fresh_and_reused_preflight_policy_parity(tmp_path,path,action):
    work,wid,model,sandbox,ledger = setup(tmp_path)
    bad = {'scope':None,'operations':[{'action':action,'path':path,'reason':'invalid'}]}
    model.plan = bad
    with pytest.raises(WorkbenchError):
        work.run_project(wid,'','Implement value module',model,sandbox,ledger)
    assert model.generations == len(sandbox.inputs) == 0
    # Only envelope provenance is synthesized; identical executable operation preflight must reject it.
    raw = work.raw_files(wid)
    import hashlib
    cache = {'version':1,'workspace_id':wid,'target':'','request_sha256':work._plan_digest('Implement value module'),
             'revision_sha256':work._plan_digest({'files':{n:hashlib.sha256(d).hexdigest() for n,d in raw.items()},'folders':work.get(wid)['folders']}),**bad}
    cache['plan_sha256'] = work._plan_digest(cache)
    with pytest.raises(WorkbenchError):
        work.run_project(wid,'','Implement value module',model,sandbox,ledger,reusable_plan=cache)
    assert model.plans == 1 and model.generations == len(sandbox.inputs) == 0


def test_literal_reuse_always_restarts_from_original_source(tmp_path):
    work,wid,model,sandbox,ledger = setup(tmp_path)
    work.write(wid,'value.py','def value():\n    return 1\n')
    model.plan = {'scope':'existing_files','operations':[{'action':'edit','path':'value.py','reason':'literal',
                  'replacements':[{'old_text':'return 1','new_text':'return 2'}]}]}
    first = work.run_project(wid,'value.py','Replace return 1 with return 2 in value.py',model,sandbox,ledger)
    second = work.run_project(wid,'value.py','Replace return 1 with return 2 in value.py',model,sandbox,ledger,reusable_plan=first['operation_plan'])
    assert model.plans == 1 and model.generations == 0
    assert sandbox.inputs[0]['value.py'] == sandbox.inputs[1]['value.py']
    assert 'return 1' in work.read(wid,'value.py')['content']
    assert second['events'][0]['event'] == 'PLAN_REUSED'


@pytest.mark.parametrize('operations',[
    [{'action':'create','path':'value.py','reason':'one'},{'action':'create','path':'value.py','reason':'two'}],
    [{'action':'edit','path':'test_value.py','reason':'bad span','replacements':[{'old_text':'absent','new_text':'x'}]}],
    [{'action':'launch','path':'value.py','reason':'unsupported'}],
])
def test_entire_plan_is_checked_before_first_generation(tmp_path,operations):
    work,wid,model,sandbox,ledger = setup(tmp_path)
    model.plan = {'scope':None,'operations':operations}
    with pytest.raises(WorkbenchError):
        work.run_project(wid,'','Implement value module',model,sandbox,ledger)
    assert model.generations == len(sandbox.inputs) == 0

