"""Actual Agent planner execution against an isolated Knowledge index."""
import json,sys,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.service import Workbench
from backend.settings import Settings
class IsolatedSettings(Settings):
    @property
    def sources_dir(self):return self.data_dir/'sources'
own=ROOT/'benchmarks'/'agent-duplicate-live'/uuid.uuid4().hex
service=Workbench(IsolatedSettings(data_dir=own/'data',project_dir=own/'projects'))
for name,text in [('original.txt','One exact reference.'),('duplicate.txt','One exact reference.'),('different.txt','Different reference.')]:
    path=service.sources_dir/name;path.write_text(text,encoding='utf-8');service.import_file(path)
before={p.name:p.read_bytes() for p in service.sources_dir.iterdir() if p.is_file()}
result=service.run_auto_agent('can u delete the duplicate files in the knowledge',[],history=['User: Create division.py','Assistant: Created it.'])
assert result['status']=='completed',result
assert result['plan']['action']=='application_tools',result
assert len(service.documents())==2
assert before=={p.name:p.read_bytes() for p in service.sources_dir.iterdir() if p.is_file()}
assert result['result']['operations'][0]['tool']=='document_deduplicate'
(own/'results.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps({'passed':True,'results':str(own/'results.json'),'remaining_documents':2,'source_files_unchanged':True}))
