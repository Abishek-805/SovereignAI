"""Live model/tool follow-up acceptance; all documents belong to an isolated fixture."""
import json,sys,time,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backend.service import Workbench
from backend.settings import Settings
from backend.model import LocalModel
class IsolatedSettings(Settings):
 @property
 def sources_dir(self):return self.data_dir/'sources'
own=ROOT/'benchmarks'/'document-followup-live'/uuid.uuid4().hex
service=Workbench(IsolatedSettings(data_dir=own/'data',project_dir=own/'projects'))
source=service.sources_dir/'nature_explanation.txt';source.write_text('Nature on Earth includes forests, oceans, plants and animals.',encoding='utf-8')
first=service.import_file(source);before=first['active_hash'];started=time.perf_counter()
result=service.run_auto_agent('make the doc more detailed, the actual nature thts the earth',[],history=[
 'User: can u add a txt file explaining abt nature', 'Assistant: Completed: document create nature_explanation.txt.'])
docs=service.documents()
checks={'completed':result['status']=='completed','updated_not_created':len(docs)==1 and docs[0]['document_id']==first['document_id'] and docs[0]['active_hash']!=before,
 'tool_update':any(o['tool']=='document_update' for o in result.get('result',{}).get('operations',[])),
 'original_preserved':source.read_text()=='Nature on Earth includes forests, oceans, plants and animals.'}
(own/'result.json').write_text(json.dumps({'checks':checks,'seconds':time.perf_counter()-started,'result':result},indent=2),encoding='utf-8')
print(json.dumps({'checks':checks,'seconds':time.perf_counter()-started,'path':str(own)}),flush=True)
raise SystemExit(0 if all(checks.values()) else 1)
