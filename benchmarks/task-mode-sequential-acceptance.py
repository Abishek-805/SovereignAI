"""Actual installed model and Docker; only a new suite-owned project is mutated."""
import json,time
from pathlib import Path
import httpx

base='http://127.0.0.1:8088'
out=Path('benchmarks/task-mode-sequential-results.json')
checks=[]
client=httpx.Client(base_url=base,timeout=30)
def api(path,body=None,method=None):
    response=client.request(method or ('POST' if body is not None else 'GET'),path,json=body)
    response.raise_for_status()
    return response.json()
def job(path,payload):
    admitted=api(path,payload)
    deadline=time.monotonic()+150
    while time.monotonic()<deadline:
        result=api('/coding/jobs/'+admitted['job_id'])
        if result['state']!='running':
            checks.append({'request':json.loads(json.dumps(payload)),'job':result})
            out.write_text(json.dumps({'checks':checks},indent=2),encoding='utf-8')
            assert result['state']=='completed',result
            print(json.dumps({'request':payload.get('goal',payload.get('question',payload.get('instruction'))),'elapsed':result['elapsed'],'action':result.get('result',{}).get('plan',{}).get('action')}),flush=True)
            return result
        time.sleep(.5)
    api('/coding/jobs/'+admitted['job_id']+'/stop',{})
    raise AssertionError('Task exceeded150seconds')

workspace=api('/coding/workspaces',{'name':'Task mode acceptance '+str(int(time.time()))})
wid=workspace['workspace_id']
docs=api('/documents')
chosen=next((d for d in docs if d['display_name']=='sop.txt'),docs[0] if docs else None)
history=[]
if chosen:
    summary=job('/agent/jobs',{'goal':'Summarize this connected document.','document_ids':[chosen['document_id']],'workspace_id':wid})
    assert summary['result']['plan']['action']=='search_documents'
    history=['User: Summarize this connected document.','Assistant: '+summary['result']['answer'][:1000]]
chat=job('/documents/jobs',{'kind':'ask','question':'can u create a code to do division operation','document_ids':[],'history':history})
assert chat['result']['status']=='conversation' and '```' in chat['result']['answer'] and not chat['result']['sources']
assert api('/coding/workspaces/'+wid)['files']==[]
first=job('/agent/jobs',{'goal':'can u create a code to do division operation','document_ids':[],'workspace_id':wid,'history':history})
assert first['result']['plan']['action']=='edit_code'
files=api('/coding/workspaces/'+wid)['files']
assert len(files)==1,files
original={f['name']:api('/coding/workspaces/'+wid+'/files/'+f['name']) for f in files}
history+=['User: can u create a code to do division operation','Assistant: '+first['result']['answer']]
second=job('/agent/jobs',{'goal':'Create multiplication.py containing a multiplication function.','document_ids':[],'workspace_id':wid,'history':history[-8:]})
assert second['result']['plan']['action']=='edit_code'
for name,content in original.items():assert api('/coding/workspaces/'+wid+'/files/'+name)==content
assert 'multiplication.py' in {f['name'] for f in api('/coding/workspaces/'+wid)['files']}
code=job('/coding/workspaces/'+wid+'/jobs',{'kind':'edit','target':'subtraction.py','instruction':'Create subtraction.py containing a subtraction function.'})
assert code['result']['state']=='completed'
for entry in checks[1:] if chosen else checks:
    assert not any('document' in event.get('stage','').lower() or 'sourced' in event.get('stage','').lower() for event in entry['job'].get('events',[])),entry
out.write_text(json.dumps({'passed':True,'workspace_id':wid,'checks':checks},indent=2),encoding='utf-8')
print('All sequential task and Chat/Agent separation checks passed.',flush=True)
