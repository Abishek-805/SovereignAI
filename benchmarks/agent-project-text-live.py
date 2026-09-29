"""Live project TXT creation in a disposable workspace, never Summa."""
import json,sys,uuid,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backend.service import Workbench
from backend.settings import Settings
class IsolatedSettings(Settings):
 @property
 def sources_dir(self):return self.data_dir/'sources'
own=ROOT/'benchmarks'/'project-text-live'/uuid.uuid4().hex
service=Workbench(IsolatedSettings(data_dir=own/'data',project_dir=own/'projects'))
service.settings.data_dir.mkdir(parents=True,exist_ok=True)
(service.settings.data_dir/'sandbox-validation.json').write_bytes((ROOT/'data/sandbox-validation.json').read_bytes())
workspace=service.coding.create('Text fixture')['workspace_id'];start=time.perf_counter()
result=service.run_auto_agent('can u create a txt file explaining abt nature',[],workspace,history=[])
files=service.coding.get(workspace)['files'];text_files=[f['name'] for f in files if f['name'].endswith('.txt')]
checks={'completed':result['status']=='completed','project_file':len(text_files)==1,'no_library_write':service.documents()==[]}
if text_files:checks['nonempty']=len(service.coding.read(workspace,text_files[0])['content'])>50
(own/'result.json').write_text(json.dumps({'checks':checks,'seconds':time.perf_counter()-start,'result':result},indent=2),encoding='utf-8')
print(json.dumps({'checks':checks,'seconds':time.perf_counter()-start,'path':str(own)}),flush=True)
raise SystemExit(0 if all(checks.values()) else 1)
