import json
import pytest
from workflows.build_contract import compile_contract, validator_script


def test_output_preservation_requires_unique_existing_executable():
    files={'main.py':b'from helpers import value\nprint(value())\n',
           'helpers.py':b'def value():\n return 42\n'}
    request='Rename a function across the files. The program must still print 42.'
    checks=compile_contract(request,{'operations':[]},files)['acceptance_checks']
    assert any(c['kind']=='cli' and c['file']=='main.py' and c['stdout']=='42' for c in checks)
    ambiguous={**files,'other.py':b'print(99)\n'}
    assert not compile_contract(request,{'operations':[]},ambiguous)['acceptance_checks']
    assert not compile_contract(request+' Do not run the program.',{'operations':[]},files)['acceptance_checks']


@pytest.mark.parametrize('module,symbol,args', [
    ('pricing','total','[-1], 10'), ('temperature','convert','-1'),
    ('age','validate','-1'), ('email','validate',"'not-an-email'")])
def test_immutable_exception_oracle_becomes_file_obligation(module,symbol,args):
    fixture=f'''import unittest
from {module} import {symbol}
class Acceptance(unittest.TestCase):
 def test_invalid(self):
  with self.assertRaises(ValueError): {symbol}({args})
'''
    contract=compile_contract('Create a project; reject invalid input with ValueError.',plan(),{'test_acceptance.py':fixture.encode()})
    check=next(c for c in contract['acceptance_checks'] if c['kind']=='python_exception')
    assert check['file']==module+'.py' and check['symbol']==symbol and check['expected']=='ValueError'
    assert check['evidence']=='test_acceptance.py:5' and check['oracle_sha256']
    assert set(contract['requirement_classes'])=={'FILE','INTERFACE','NORMAL','INVALID_INPUT','ERROR','OUTPUT','PERSISTENCE','PRESERVATION','ENTRYPOINT','ACCEPTANCE'}
    compile(validator_script(contract),'trusted-validator','exec')


def test_literal_loop_expands_all_invalid_cases_without_executing_fixture():
    from scripts.model_project_transfer_diagnostic import CASES
    contract=compile_contract(CASES[0]['request'],plan(),{'test_acceptance.py':CASES[0]['acceptance'].encode()})
    checks=[c for c in contract['acceptance_checks'] if c['kind']=='python_exception']
    assert [c['args'] for c in checks]==[[[-1],10],[[2],-1],[[2],101]]


def test_unknown_fixture_expressions_are_not_evaluated():
    from workflows.build_contract import independent_exception_cases
    fixture=b'import unittest\nfrom age import validate\nwith self.assertRaises(ValueError): validate(__import__("os").system("bad"))\n'
    assert independent_exception_cases({'test_acceptance.py':fixture})==[]


def test_explicit_run_output_is_an_independent_repair_obligation():
    contract=compile_contract('Fix the helper, then run main.py to verify it prints 17.',plan(),{})
    check=next(c for c in contract['acceptance_checks'] if c['kind']=='cli')
    assert check['file']=='main.py' and check['stdout']=='17'
    assert not any(c['kind']=='cli' for c in compile_contract('Do not run main.py; it prints 17.',plan(),{})['acceptance_checks'])


@pytest.mark.parametrize('framework,entry', [('Flask','app.py'),('Node on port 3000','server.js')])
def test_explicit_malformed_http_obligation_is_executable(framework,entry):
    contract=compile_contract(f'Create {framework} API. POST /double accepts JSON. Malformed JSON returns HTTP 400.',plan(entry),{})
    check=next(c for c in contract['acceptance_checks'] if c.get('invalid_input'))
    assert check['method']=='POST' and check['body']=='{broken' and check['status']==400
    compile(validator_script(contract),'trusted-validator','exec')


def test_normal_oracle_cannot_hide_unchecked_explicit_error_requirement(tmp_path):
    from workflows.coding_workspace import CodingWorkspace
    from router.task_ledger import TaskLedger
    class Worker:
        def plan_workspace_edit(self,*args,**kwargs):
            return {'scope':'new_files','contract':{'deliverable':'application','entrypoint':'main.py','requirements':['normal and invalid behavior']},
                    'operations':[{'action':'create','path':'main.py','reason':'CLI'}]}
        def complete_code(self,*args,**kwargs):return {'code':'print(42)\n'}
    class Docker:
        image_id='test'
        def _ready(self):pass
        def execute(self,*args,**kwargs):raise AssertionError('Unresolved acceptance should stop before execution')
    work=CodingWorkspace(tmp_path/'work');wid=work.create('Unchecked error')['workspace_id']
    result=work.run_project(wid,'','Create a CLI main.py that prints 42 and rejects empty usernames.',Worker(),Docker(),TaskLedger(tmp_path/'ledger'))
    assert result['state']=='failed' and not result['checks']['target_committed']
    assert 'acceptance' in result.get('error','').lower()


def plan(entry='main.py'):
    return {'contract':{'deliverable':'application','entrypoint':entry},'operations':[{'action':'create','path':entry}]}


def test_literal_requirements_are_request_bound_not_model_claims():
    request='Create main.py, helpers.py and README.md. helpers.answer() must return 42.'
    contract=compile_contract(request,plan(),{})
    assert contract['original_request']==request
    assert contract['required_files']==['main.py','helpers.py','README.md']
    check=next(c for c in contract['acceptance_checks'] if c['kind']=='python_return')
    assert check['expected']==42 and check['symbol']=='answer'
    assert check['evidence'] in request
    compile(validator_script(contract),'trusted-validator','exec')


def test_cli_keeps_argv_and_checks_invalid_exit_without_inventing_output():
    contract=compile_contract('Create a Python CLI accepting --temperature 25 and reject negative values.',plan(),{})
    cli=[c for c in contract['acceptance_checks'] if c['kind']=='cli']
    assert cli[0]['args']==['--temperature','25'] and cli[0]['exit']=='zero'
    assert cli[1]['args']==['--temperature','-1'] and cli[1]['exit']=='nonzero'
    assert all('stdout' not in c for c in cli)


def test_ambiguity_is_not_fabricated_as_executable_semantics():
    contract=compile_contract('Create a temperature application.',plan(),{})
    assert contract['arguments']==[] and contract['acceptance_checks']==[]
    assert 'literal' in contract['coverage']


@pytest.mark.parametrize('goal,entry,kind',[
    ('Create a Flask API with /health returning 200.','app.py','flask_http'),
    ('Create a Node HTTP service on port 3000 with /health returning 200.','server.js','node_http'),
    ('Create a Java CLI that prints 42.','Main.java','cli')])
def test_runtime_adapters_have_request_bound_expectations(goal,entry,kind):
    contract=compile_contract(goal,plan(entry),{})
    assert contract['acceptance_checks'][0]['kind']==kind
    compile(validator_script(contract),'trusted-validator','exec')


def test_preservation_hashes_come_from_actual_snapshot():
    import hashlib
    contract=compile_contract('Create main.py and preserve keep.txt unchanged.',plan(),{'keep.txt':b'original'})
    assert contract['preservation_rules']['keep.txt']==hashlib.sha256(b'original').hexdigest()
    assert compile_contract('Refactor legacy.py and preserve behavior.',plan(),{'legacy.py':b'old'})['preservation_rules']=={}


def test_damaged_workspace_does_not_hide_healthy_workspaces(tmp_path):
    from workflows.coding_workspace import CodingWorkspace
    work=CodingWorkspace(tmp_path);healthy=work.create('Healthy')['workspace_id'];broken=work.create('Broken')['workspace_id']
    (work._directory(broken)/'workspace.json').write_text('corrupt')
    listed=work.list()
    assert any(item['workspace_id']==healthy and item['name']=='Healthy' for item in listed)
    assert next(item for item in listed if item['workspace_id']==broken)['unavailable'] is True


def test_dockerfile_is_an_artifact_not_sandbox_execution_authority():
    from workflows.code_runtime import runner,source_language
    from backend.contracts import WorkbenchError
    assert source_language('Dockerfile')=='Dockerfile'
    compile(runner('Dockerfile',mode='check'),'trusted-text-check','exec')
    with pytest.raises(WorkbenchError,match='approved sandbox image'):
        runner('Dockerfile',mode='run')


def test_targeted_repair_reuses_other_generated_files_and_reruns_whole_contract(tmp_path):
    from workflows.coding_workspace import CodingWorkspace
    from router.sandbox import SandboxResult
    from router.task_ledger import TaskLedger
    class Worker:
        calls=[]
        def plan_workspace_edit(self,*a,**k):
            return {'scope':'new_files','contract':{'deliverable':'application','entrypoint':'main.py','requirements':['helper returns 42']},
                'operations':[{'action':'create','path':'helpers.py','reason':'API'},{'action':'create','path':'main.py','reason':'entry'}]}
        def complete_code(self,messages,**k):
            data=json.loads(messages[1]['content']);self.calls.append(data['path'])
            return {'code':'def answer():\n return 42\n' if data['path']=='helpers.py' else 'from helpers import answer\nif __name__ == "__main__":\n print(answer())\n'}
    class Docker:
        image_id='test';runs=0
        def _ready(self):pass
        def execute(self,script,input_files):
            if 'BUILD_CONTRACT_RESULT=' not in script:return SandboxResult(0,'syntax','',True)
            self.runs+=1
            passed=self.runs>1
            return SandboxResult(0 if passed else 1,'BUILD_CONTRACT_RESULT='+json.dumps([{'kind':'python_return','file':'helpers.py','symbol':'answer','expected':42,'evidence':'helpers.answer() must return 42','passed':passed}]),'',True)
    work=CodingWorkspace(tmp_path);wid=work.create('Targeted')['workspace_id'];worker=Worker();docker=Docker();ledger=TaskLedger(tmp_path/'ledger')
    goal='Create main.py and helpers.py. helpers.answer() must return 42.'
    first=work.run_project(wid,'',goal,worker,docker,ledger)
    assert first['state']=='failed'
    second=work.run_project(wid,'',goal,worker,docker,ledger,reusable_plan=first['operation_plan'],repair_candidate=first)
    assert second['state']=='completed'
    assert worker.calls==['helpers.py','main.py','helpers.py']
    assert docker.runs==2
    assert second['changes'][1]['after']==first['changes'][1]['after']
