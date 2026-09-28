"""Live model/Docker acceptance on an exact asset clone; never edits Summa."""
import hashlib,json,time,sys
from pathlib import Path
import httpx

c=httpx.Client(base_url='http://127.0.0.1:8088',timeout=30)
out=Path('benchmarks/mixed-project-agent-results.json')
results=[]
def api(path,body=None):
    r=c.post(path,json=body) if body is not None else c.get(path)
    r.raise_for_status();return r.json()
def hashes(wid):
    return {f['name']:hashlib.sha256(c.get('/coding/workspaces/'+wid+'/assets/'+f['name']).raise_for_status().content).hexdigest() for f in api('/coding/workspaces/'+wid)['files']}
def job(goal,wid,history=[]):
    start=api('/agent/jobs',dict(goal=goal,workspace_id=wid,document_ids=[],history=history))
    Path('benchmarks/mixed-project-current-job.json').write_text(json.dumps(start),encoding='utf-8')
    deadline=time.monotonic()+180
    while time.monotonic()<deadline:
        state=api('/coding/jobs/'+start['job_id'])
        if state['state']!='running':
            results.append(dict(goal=goal,job=state));out.write_text(json.dumps(results,indent=2),encoding='utf-8')
            assert state['state']=='completed',state
            assert state.get('result',{}).get('status')!='failed',state
            print(json.dumps(dict(goal=goal,elapsed=state['elapsed'],action=state['result']['plan']['action'])),flush=True)
            return state['result']
        time.sleep(.5)
    api('/coding/jobs/'+start['job_id']+'/stop',{});raise AssertionError('180 second deadline')

summa=next(w for w in api('/coding/workspaces') if w['name']=='Summa')
sid=summa['workspace_id'];before=hashes(sid)
clone=api('/coding/workspaces/'+sys.argv[1]) if len(sys.argv)>1 else api('/coding/workspaces',{'name':'Mixed project acceptance '+str(int(time.time()))});wid=clone['workspace_id']
if len(sys.argv)==1:
    for name in before:
        data=c.get('/coding/workspaces/'+sid+'/assets/'+name).raise_for_status().content
        c.post('/coding/workspaces/'+wid+'/import-files/'+name,content=data,headers={'Content-Type':'application/octet-stream'}).raise_for_status()
    assert hashes(wid)==before
history=['User: Summarize the documents and export a cited Word report.','Assistant: Finished the document report.']
if 'division.py' not in hashes(wid):
    first=job('Create division.py containing a Python division program that asks for two numbers, handles division by zero and invalid numeric input.',wid,history)
    assert first['plan']['action']=='edit_code',first
assert 'division.py' in hashes(wid)
for name,digest in before.items():assert hashes(wid)[name]==digest
run=job('Run division.py and provide 12 then 3 as its input.',wid,history+['User: Create division.py','Assistant: Created division.py.'])
assert run['plan']['action']=='application_tools' and '4.0' in run['answer'],run
code_name='multiplication_check_'+str(int(time.time()))+'.py'
multi=job('Create '+code_name+' with a function multiply(a,b), then run it to print multiply(6,7).',wid,history)
assert multi['plan']['action']=='application_tools' and '42' in multi['answer'],multi
assert code_name in hashes(wid)
name='agent-tools-acceptance-'+str(int(time.time()))+'.txt'
job('Create a new Knowledge document named '+name+' containing exactly: Application tools acceptance.',wid)
job('Rename the Knowledge document '+name+' to renamed-'+name+'.',wid)
job('Delete the Knowledge document renamed-'+name+' from the library.',wid)
job('List my automations.',wid)
assert hashes(sid)==before
assert all(hashes(wid)[name]==digest for name,digest in before.items())
out.write_text(json.dumps({'passed':True,'workspace_id':wid,'original_hashes':before,'checks':results},indent=2),encoding='utf-8')
print('Mixed project and application tool acceptance passed.',flush=True)
