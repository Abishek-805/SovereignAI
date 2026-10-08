"""Harness correctness checks, not model-success evidence."""
import json
import pytest
from backend.contracts import WorkbenchError
from workflows.coding_workspace import CodingWorkspace
from experiments.fidelity_v1.runners import load_native,configure,Trace,digest
def fixture(tmp_path):
 coding=CodingWorkspace(tmp_path/'store');wid=coding.create('test')['workspace_id'];coding.write(wid,'a.py','x=1\n')
 module=load_native();workspace=module.WorkspaceManager(coding,wid,'Edit a.py');workspace.read.add('a.py')
 return module,workspace
def test_initial_context_and_tools_identical(tmp_path):
 hashes=[]
 for arm in ('native_v1','nanobot_minimal','hermes_minimal'):
  path=tmp_path/arm;path.mkdir();module,workspace=fixture(path);trace=Trace(path);configure(module,arm,trace)
  class Model:pass
  messages=[{'role':'system','content':module.SYSTEM},{'role':'user','content':'original request'}]
  adapter=module.ModelAdapter(Model(),'fixed')
  hashes.append(digest({'messages':adapter.fit(messages,module.ToolRegistry().schemas(),workspace,{}),'schemas':module.ToolRegistry().schemas()}))
 assert len(set(hashes))==1
@pytest.mark.parametrize('arm,rolled',[('native_v1',False),('nanobot_minimal',True),('hermes_minimal',True)])
def test_only_adaptations_rollback_property_regression(tmp_path,monkeypatch,arm,rolled):
 module,workspace=fixture(tmp_path);trace=Trace(tmp_path,{'test_keep (test_case.Check)':True})
 # property parser uses owner + method; configure exact initial independent property.
 trace.best_properties={'test_case.Check.test_keep'}
 monkeypatch.setattr(module.ValidationEngine,'validate',lambda self:{'passed':False,'independent':True,'stderr':'test_keep (test_case.Check) ... FAIL\n'})
 configure(module,arm,trace);workspace.write('a.py','x=0\n')
 validator=module.ValidationEngine(workspace,None,module.AgentSession('request',workspace.wid,'fixed'))
 result=validator.validate()
 assert bool(result.get('rolled_back'))==rolled
 assert workspace.files()['a.py']==(b'x=1\n' if rolled else b'x=0\n')
 assert trace.repairs[0]['candidate_diff'] and trace.repairs[0]['lost_properties']
def test_format_recovery_has_two_error_ceiling(tmp_path):
 module,workspace=fixture(tmp_path);trace=Trace(tmp_path);configure(module,'hermes_minimal',trace)
 class Model:
  def agent_tool_turn(self,*args):raise WorkbenchError('generation_format','exact bounded output error')
 adapter=module.ModelAdapter(Model(),'fixed');messages=[{'role':'system','content':module.SYSTEM},{'role':'user','content':'original'}]
 assert adapter.turn(messages,[])['tool_calls']==[]
 next_messages=adapter.fit(messages,[],workspace,{})
 assert 'exact bounded output error' in json.dumps(next_messages)
 with pytest.raises(WorkbenchError):adapter.turn(next_messages,[])
 assert len(trace.events)>=2
def test_pending_checkpoint_precedes_tool_dispatch(tmp_path):
 module,workspace=fixture(tmp_path);trace=Trace(tmp_path);configure(module,'nanobot_minimal',trace)
 executor=module.ToolExecutor(workspace,None,module.ToolRegistry())
 result=executor.execute('list_dir',{})
 assert result['files']==['a.py']
 pending=list(tmp_path.glob('pending-*.json'));assert len(pending)==1
 assert 'result' not in json.loads(pending[0].read_text())
 assert trace.events[-1]['result']==result
