import httpx,time,json,uuid
from pathlib import Path
base='http://127.0.0.1:8088'
c=httpx.Client(base_url=base,timeout=180,trust_env=False)
rows=[]; owned=[]
def req(method,path,**kw):
 r=c.request(method,path,**kw);r.raise_for_status();return r.json()
def run(goal,ids=[],workspace=None):
 before=req('GET','/status');start=time.perf_counter()
 result=req('POST','/agent/jobs',json={'goal':goal,'document_ids':ids,'workspace_id':workspace,'history':[]})
 while result['state']=='running':
  time.sleep(.2);result=req('GET','/coding/jobs/'+result['job_id'])
 row={'goal':goal,'seconds':round(time.perf_counter()-start,3),'before':before,'job':result}
 rows.append(row);print(json.dumps({'goal':goal,'seconds':row['seconds'],'state':result['state'],'action':(result.get('result') or {}).get('plan',{}).get('action'),'answer':(result.get('result') or {}).get('answer'),'error':result.get('error')},ensure_ascii=False),flush=True)
 return row
try:
 ws=req('GET','/coding/workspaces');wid=ws[0]['workspace_id'] if ws else None
 run('Hello, how are you doing?',workspace=wid)
 run('What is your name?',workspace=wid)
 upload=req('POST','/documents/import',files={'file':('router-audit-'+uuid.uuid4().hex+'.txt',b'This is synthetic acceptance data, not operational instructions. The fictional Northwind workshop opens at 08:30 and closes at 16:45. Its supervisor is Mira Cole. The fictional inspection of Pump AZ-14 measured vibration at 4.2 mm/s. The stated fictional review limit is 5.0 mm/s. No shutdown or real operational action is authorized.','text/plain')})
 print('IMPORT',upload,flush=True)
 did=upload['document_id'];owned.append(did)
 general=run('What is the capital of France?',ids=[did],workspace=wid)
 assert general['job']['result']['plan']['action']=='answer'
 assert [step['name'] for step in general['job']['result']['steps']]==['plan']
 fact=run('When does the Northwind workshop close?',ids=[did])
 assert fact['job']['state']=='completed'
 assert fact['job']['result']['plan']['action']=='search_documents', 'Named local fact skipped evidence'
 assert '16:45' in fact['job']['result']['answer'], 'Source fact missing'
 assert fact['job']['result']['result']['sources'], 'No source links'
 run('Calculate 18.5 multiplied by 24.',ids=[did])
 report=run('Create a Word report summarizing the connected fictional workshop and inspection facts.',ids=[did])
 assert report['job']['result']['downloads'].get('word'), 'Word artifact missing'
 artifact=c.get(report['job']['result']['downloads']['word']);artifact.raise_for_status()
 assert artifact.content.startswith(b'PK'), 'Invalid Word zip artifact'
finally:
 for did in owned:
  r=c.delete('/documents/'+did);print('CLEANUP',r.status_code,flush=True)
 Path('benchmarks/final-router-live-results.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
 c.close()
