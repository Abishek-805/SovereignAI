import json,time,hashlib
from pathlib import Path
from scripts.full_qa_inventory import http
out=Path('outputs/interaction-repair');out.mkdir(exist_ok=True)
source=http('/coding/workspaces/f2ac2ecf555048b6964e64eded90fc2e')['body']
w=http('/coding/workspaces','POST',{'name':'Calculator history isolation '+str(time.time_ns())})['body']['workspace_id']
before={}
for entry in source['files']:
 if entry['name'].endswith('.java'):
  content=http('/coding/workspaces/f2ac2ecf555048b6964e64eded90fc2e/files/'+entry['name'])['body']['content']
  http('/coding/workspaces/'+w+'/files/'+entry['name'],'PUT',{'content':content});before[entry['name']]=hashlib.sha256(content.encode()).hexdigest()
payload={'goal':'can u create a simple calculator app','workspace_id':w,'document_ids':[],
 'history':['User: Create Java linear and binary search code in the existing array_search folder.',
 'Assistant: Staged array_search/LinearSearch.java, array_search/BinarySearch.java for review. Docker validation passed.']}
ad=http('/agent/jobs','POST',payload);assert ad['status']==200,ad
for _ in range(600):
 final=http('/coding/jobs/'+ad['body']['job_id'])['body']
 (out/'calculator-history.json').write_text(json.dumps({'workspace_id':w,'request':payload,'admission':ad,'final':final,'original_hashes':before},indent=2),encoding='utf-8')
 if final['state']!='running':break
 time.sleep(1)
print(final['state'],final.get('result',{}).get('answer',final.get('error')))
