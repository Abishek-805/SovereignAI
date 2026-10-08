import json,hashlib,time,urllib.request
from pathlib import Path
from scripts.full_qa_inventory import http
out=Path('outputs/release-repair')
for _ in range(30):
 if http('/health')['status']==200:break
 time.sleep(1)
snapshot=json.loads((out/'persistence/pre-restart-snapshot.json').read_text(encoding='utf-8'));checks=[]
for wid,data in snapshot.items():
 for name,prior in data['files'].items():
  response=http('/coding/workspaces/'+wid+'/files/'+name)
  current=hashlib.sha256(response['body']['content'].encode()).hexdigest() if response['status']==200 else None
  checks.append({'workspace_id':wid,'file':name,'before':prior['sha256'],'after':current,'status':'PASS' if current==prior['sha256'] else 'FAIL'})
for prior in json.loads((out/'artifacts/independent-browser-artifacts.json').read_text(encoding='utf-8')):
 with urllib.request.urlopen('http://127.0.0.1:8088/documents/'+prior['document_id']+'/original') as r:raw=r.read()
 digest=hashlib.sha256(raw).hexdigest();checks.append({'document_id':prior['document_id'],'name':prior['name'],'before':prior['sha256'],'after':digest,'status':'PASS' if digest==prior['sha256'] else 'FAIL'})
status=http('/status');result={'checks':checks,'runtime':status,'idle':not status['body'].get('busy') and not status['body'].get('active_jobs'),'status':'PASS' if all(c['status']=='PASS' for c in checks) else 'FAIL'}
(out/'persistence/restart-validation.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(result['status'],len(checks),'persisted checks; idle',result['idle'])
