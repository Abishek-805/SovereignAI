"""Independent behavior oracle for the documented API of the accepted QA app."""
import argparse,json,time
from pathlib import Path
from workflows.coding_workspace import CodingWorkspace
from workflows.agent_kernel import WorkspaceManager,AgentSession,ValidationEngine
from experiments.kernel_docker import DockerCommands
ROOT=Path(__file__).resolve().parents[1]
ORACLE='''import importlib,json
m=importlib.import_module("app")
client=m.app.test_client()
checks=[]
def check(name,value):
 checks.append({"check":name,"passed":bool(value)})
 assert value,name
created=client.post('/students',json={'name':'Independent student'})
check('create student JSON',200<=created.status_code<300 and created.is_json)
payload=created.get_json()
student_id=payload.get('id',payload.get('student',{}).get('id'))
check('created student identity returned',student_id is not None)
listed=client.get('/students')
check('student stored and retrievable',listed.status_code==200 and listed.is_json and 'Independent student' in listed.get_data(as_text=True))
valid=client.post(f'/attendance/{student_id}',json={'date':'2026-10-06','status':'present'})
check('valid attendance accepted JSON',200<=valid.status_code<300 and valid.is_json)
for label,data in [('invalid status',{'date':'2026-10-07','status':'nonsense'}),('invalid date',{'date':'not-a-date','status':'present'}),('missing fields',{})]:
 response=client.post(f'/attendance/{student_id}',json=data)
 check(label,400<=response.status_code<500 and response.is_json)
response=client.post(f'/attendance/{student_id}',data='{broken',content_type='application/json')
check('malformed JSON rejected as JSON',400<=response.status_code<500 and response.is_json)
response=client.post('/attendance/9999',json={'date':'2026-10-06','status':'present'})
check('unknown student rejected as JSON',400<=response.status_code<500 and response.is_json)
from pathlib import Path
check('README present',Path('README.md').is_file())
check('test present',bool(list(Path('.').glob('test_*.py'))))
print('INDEPENDENT_ATTENDANCE_RESULT='+json.dumps(checks))
'''
def main():
 p=argparse.ArgumentParser();p.add_argument('workspace_id');args=p.parse_args()
 out=ROOT/'outputs/agent-kernel-rebuild'/('attendance-oracle-'+str(time.time_ns()));out.mkdir(parents=True)
 coding=CodingWorkspace(ROOT/'data/coding-workspaces');workspace=WorkspaceManager(coding,args.workspace_id,'Independently verify the accepted attendance application')
 sandbox=DockerCommands(ROOT,out/'sandbox').sandbox
 result=ValidationEngine(workspace,sandbox,AgentSession('oracle',args.workspace_id,'fixed')).command('python -c '+__import__('shlex').quote(ORACLE))
 (out/'oracle.py').write_text(ORACLE);(out/'result.json').write_text(json.dumps(result,indent=2))
 assert result['container_executed'] and result['exit_code']==0,result
 print('PASS independent accepted attendance '+str(out),flush=True)
if __name__=='__main__':main()
