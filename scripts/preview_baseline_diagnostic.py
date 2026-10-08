import json,time
from pathlib import Path
from types import SimpleNamespace
from scripts.full_qa_inventory import http
from workflows.web_preview import preview_request
from router.sandbox import CodeSandbox
out=Path('outputs/interaction-repair');latest=json.loads((out/'preview-live.json').read_text(encoding='utf-8'));w=latest['workspace_id']
files={item['name']:http('/coding/workspaces/'+w+'/files/'+item['name'])['body']['content'].encode() for item in http('/coding/workspaces/'+w)['body']['files']}
coding=SimpleNamespace(read=lambda *args:{},raw_files=lambda *args:files)
sandbox=CodeSandbox('docker','sha256:6f6ac11cda347a185454338dee35d77003e066579a3261b52b7c6ff1048c8573')
proxy=SimpleNamespace(execute=sandbox.execute);results=[]
for _ in range(3):
 start=time.monotonic();response=preview_request(coding,proxy,out/'legacy-state',w,'app.py','/increment','POST')
 results.append({'latency':time.monotonic()-start,'response':response})
(out/'preview-one-shot-baseline.json').write_text(json.dumps(results,indent=2),encoding='utf-8');print(results)
