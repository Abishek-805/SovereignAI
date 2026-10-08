import json,time
from pathlib import Path
from scripts.full_qa_inventory import http
out=Path('outputs/interaction-repair');w=json.loads((out/'preview-live.json').read_text())['workspace_id']
previous=out/'large-response.json'
if previous.exists():previous.rename(previous.with_name('large-response-'+str(time.time_ns())+'.json'))
code=http('/coding/workspaces/'+w+'/files/app.py')['body']['content']
if '@app.get("/large")' not in code:http('/coding/workspaces/'+w+'/files/app.py','PUT',{'content':code+'\n@app.get("/large")\ndef large():return "X"*100000\n'})
results=[]
for path,method in [('/increment','POST'),('/large','GET'),('/increment','POST')]:
 r=http('/coding/workspaces/'+w+'/web-preview','POST',{'target':'app.py','path':path,'method':method})
 results.append({'path':path,'status':r['status'],'latency':r['latency'],'response_length':len(r.get('body',{}).get('body','')),'body':r.get('body',{}).get('body','') if path!='/large' else None})
previous.write_text(json.dumps({'results':results},indent=2),encoding='utf-8')
checks=[results[1]['response_length']==100000,all(r['status']==200 for r in results),json.loads(results[0]['body'])['count']==1,json.loads(results[2]['body'])['count']==2]
(out/'large-response.json').write_text(json.dumps({'results':results,'checks':checks,'status':'PASS' if all(checks) else 'FAIL'},indent=2),encoding='utf-8');print(results,checks)
