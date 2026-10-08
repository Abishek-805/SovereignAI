"""Final live contract checks; all generated execution remains in Docker."""
import json,time,hashlib,ast
from pathlib import Path
from scripts.full_qa_inventory import http
OUT=Path('outputs/release-repair')
def save(name,value):
 p=OUT/name;p.parent.mkdir(parents=True,exist_ok=True)
 if p.exists():p.rename(p.with_name(p.stem+'-'+str(time.time_ns())+p.suffix))
 p.write_text(json.dumps(value,indent=2,ensure_ascii=False),encoding='utf-8')
def find(value):
 if isinstance(value,dict):
  if value.get('publication_state')=='staged' and value.get('state')=='completed':return value
  for child in value.values():
   found=find(child)
   if found:return found
 if isinstance(value,list):
  for child in value:
   found=find(child)
   if found:return found
cases=[]
for prompt,expected in [('Return exactly JSON containing answer=42.',{'answer':42}),('Return exactly JSON with key items containing [1, null, {"text":"a quote: \\" and slash: \\\\"}], and key enabled set to true.',None)]:
 r=http('/v1/chat/completions','POST',{'model':'sovereign-text','messages':[{'role':'user','content':prompt}],'stream':False,'temperature':0,'max_tokens':512})
 try:
  parsed=json.loads(r['body']['choices'][0]['message']['content'])
  valid=parsed==expected if expected is not None else isinstance(parsed.get('items'),list) and parsed['items'][1] is None and isinstance(parsed['items'][2]['text'],str) and parsed.get('enabled') is True
 except Exception:parsed=None;valid=False
 cases.append({'response':r,'parsed':parsed,'status':'PASS' if r['status']==200 and valid else 'FAIL'})
save('model/json-final-contracts.json',cases)
j=json.loads((OUT/'agent/AT-07.json').read_text());draft=find(j);assert draft
contents={c['path']:c['after'] for c in draft['changes'] if c['action'] in {'create','edit'}}
tree=ast.parse(contents.get('main.py',''))
imports=any(isinstance(n,ast.ImportFrom) and n.module=='helpers' and any(a.name=='answer' for a in n.names) or isinstance(n,ast.Import) and any(a.name=='helpers' for a in n.names) for n in ast.walk(tree))
calls=any(isinstance(n,ast.Call) and (isinstance(n.func,ast.Name) and n.func.id=='answer' or isinstance(n.func,ast.Attribute) and isinstance(n.func.value,ast.Name) and n.func.value.id=='helpers' and n.func.attr=='answer') for n in ast.walk(tree))
checks={'exact_files':set(contents)=={'main.py','helpers.py','README.md'},'cross_file_import':imports and calls,'helper_function':'def answer(' in contents.get('helpers.py',''),'readme_command':'python main.py' in contents.get('README.md','')}
w=draft['workspace_id'];tid=draft['task_id'];accept=http(f'/coding/workspaces/{w}/tasks/{tid}/accept','POST',{})
run=http(f'/coding/workspaces/{w}/jobs','POST',{'kind':'run','target':'main.py'})
if run['status']==200:
 for _ in range(120):
  final=http('/coding/jobs/'+run['body']['job_id'])['body']
  if final['state']!='running':break
  time.sleep(1)
else:final={}
checks['docker_run']=final.get('result',{}).get('exit_code')==0 and final.get('result',{}).get('stdout','').strip().startswith('42')
save('agent/AT-07-independent.json',{'checks':checks,'contents':contents,'accept':accept,'run':final,'status':'PASS' if all(checks.values()) else 'FAIL'})
snapshot={}
for case in ['AT-07-independent','AT-13-oracle','AT-14-oracle','AT-20-oracle']:
 value=json.loads((OUT/f'agent/{case}.json').read_text());wid=w if case=='AT-07-independent' else value['workspace_id']
 workspace=http('/coding/workspaces/'+wid)['body'];snapshot[wid]={'workspace':workspace,'files':{}}
 for entry in workspace['files']:
  name=entry if isinstance(entry,str) else entry['name']
  response=http('/coding/workspaces/'+wid+'/files/'+name)
  snapshot[wid]['files'][name]={'sha256':hashlib.sha256(response['body']['content'].encode()).hexdigest(),'response':response}
save('persistence/pre-restart-snapshot.json',snapshot)
print(json.dumps({'json':[c['status'] for c in cases],'AT-07':checks,'snapshot_workspaces':len(snapshot)}))
