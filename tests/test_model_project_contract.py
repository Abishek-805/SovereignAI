import json
import pytest
from backend.contracts import WorkbenchError
from workflows.request_contract import validate_contract
from workflows.coding_workspace import CodingWorkspace
from router.sandbox import SandboxResult
from router.task_ledger import TaskLedger
from router.tool_registry import explicit_operation_requested

CONTRACT={'deliverable':'application','requirements':['Read a CLI argument','Call the helper and print its result'],'entrypoint':'main.py'}

@pytest.mark.parametrize('wording,authorized',[
 ('Build a Python application.',True),
 ('Could you build a web application?',True),
 ('Explain how to build a Python application.',False),
 ('Do not build an application.',False),
 ('Describe "build an application".',False)])
def test_build_creation_is_authorized_but_discussion_is_not(wording,authorized):
 assert explicit_operation_requested(wording,'file_edit') is authorized

def test_contract_is_bounded_and_application_requires_entrypoint():
 assert validate_contract(CONTRACT)==CONTRACT
 for bad in [{**CONTRACT,'entrypoint':''},{**CONTRACT,'requirements':[]},{**CONTRACT,'requirements':['x'*401]},{**CONTRACT,'extra':'authorization'}]:
  with pytest.raises(ValueError):validate_contract(bad)

class Model:
 def __init__(self,entry=True):self.messages=[];self.entry=entry
 def plan_workspace_edit(self,*args,**kwargs):
  return {'scope':'new_files','contract':CONTRACT,'operations':[
   {'action':'create','path':'helper.py','reason':'Provide the required callable'},
   *([{'action':'create','path':'main.py','reason':'Provide CLI entrypoint'}] if self.entry else [])]}
 def complete_code(self,messages,**kwargs):
  self.messages.append(messages);payload=json.loads(messages[1]['content'])
  return {'code':'def double(value):\n return value*2\n' if payload['path']=='helper.py' else 'from helper import double\nimport sys\nif __name__ == "__main__":\n print(double(int(sys.argv[1])))\n'}
class Sandbox:
 image_id='sha256:'+'a'*64
 def __init__(self):self.calls=[]
 def _ready(self):pass
 def execute(self,code,input_files):self.calls.append((code,input_files));return SandboxResult(0,'checked','',True)

def test_contract_survives_generation_and_request_bound_plan_reuse(tmp_path):
 work=CodingWorkspace(tmp_path);wid=work.create('QA')['workspace_id'];model=Model();sandbox=Sandbox()
 request='Create a runnable CLI project in main.py and helper.py that doubles a numeric argument.'
 first=work.run_project(wid,'',request,model,sandbox,TaskLedger(tmp_path/'ledger'),history=['Create search.java'])
 assert first['operation_plan']['contract']==CONTRACT
 assert first['validation_kind']=='syntax_or_format'  # No guessed, argument-free launch.
 for messages in model.messages:
  data=json.loads(messages[1]['content'])
  assert data['request_contract']==CONTRACT and data['current_request']==request
  assert list(data)[-1]=='current_request'
  if data['path']=='main.py':assert data['file_role']=='entrypoint'
  else:assert data['file_role']=='support'
 second=work.run_project(wid,'',request,model,sandbox,TaskLedger(tmp_path/'ledger'),reusable_plan=first['operation_plan'])
 assert second['events'][0]['event']=='PLAN_REUSED'
 assert second['operation_plan']['contract']==CONTRACT
 changed={**first['operation_plan'],'contract':{**CONTRACT,'entrypoint':'other.py'}}
 third=work.run_project(wid,'',request,model,sandbox,TaskLedger(tmp_path/'ledger'),reusable_plan=changed)
 assert third['events'][0]['event']=='PLAN_REUSE_REJECTED'

def test_missing_application_entrypoint_rejected_before_generation(tmp_path):
 work=CodingWorkspace(tmp_path);wid=work.create('QA')['workspace_id'];model=Model(entry=False)
 with pytest.raises(WorkbenchError,match='omits its runnable entrypoint'):
  work.run_project(wid,'','Create a runnable CLI application.',model,Sandbox(),TaskLedger(tmp_path/'ledger'))
 assert not model.messages and not work.raw_files(wid)

def test_current_request_descriptor_reaches_source_generation_without_losing_language():
 import httpx
 from backend.model import LocalModel
 observed=[]
 def handle(request):
  if request.url.path=='/props':return httpx.Response(200,json={'default_generation_settings':{'n_ctx':16384}})
  data=json.loads(request.content)
  if request.url.path=='/apply-template':return httpx.Response(200,json={'prompt':'formatted'})
  if request.url.path=='/tokenize':return httpx.Response(200,json={'tokens':[1]})
  observed.append(data)
  return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'code':'print(42)\n'})}}]})
 model=LocalModel(transport=httpx.MockTransport(handle))
 try:
  model.complete_code([{'role':'system','content':'Generate source'}, {'role':'user','content':json.dumps({
   'current_request':'Create a Python CLI that prints 42.','path':'main.py','language':'Python',
   'request_contract':CONTRACT,'reference_history':['Create an unrelated search program.'],
   'repair_validation':{'stderr':'AssertionError: requested invalid input did not raise','exit_code':1}})}])
 finally:model.close()
 live=observed[-1]['messages'][-1]['content']
 assert 'Original request:\nCreate a Python CLI that prints 42.' in live
 assert 'Python file contents for main.py' in live
 assert live.index('reference_history')<live.index('Original request:')
 assert 'Proposed task contract' in live
 assert 'Repair this retained candidate now.' in live
 assert live.index('Original request:')<live.index('Repair this retained candidate now.')
 assert live.count('requested invalid input did not raise')==1
 assert 'candidate failed validation' in live
