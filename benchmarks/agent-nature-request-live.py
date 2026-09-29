"""Exercise the reported Agent create/collision/follow-up flow in an isolated library."""
import json, sys, time, uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.service import Workbench
from backend.settings import Settings

class IsolatedSettings(Settings):
    @property
    def sources_dir(self):return self.data_dir/'sources'

own=ROOT/'benchmarks'/'nature-request-live'/uuid.uuid4().hex
service=Workbench(IsolatedSettings(data_dir=own/'data',project_dir=own/'projects'))
source=service.sources_dir/'nature_explanation.txt'
source.write_text('Earlier nature note.',encoding='utf-8')
service.import_file(source)
started=time.perf_counter()
first=service.run_auto_agent('CAN U crate a doc explaining about nature',[])
second=service.run_auto_agent('can u create a file in knowledge explaining about nature',[],history=[
    'User: CAN U crate a doc explaining about nature',f'Assistant: {first.get("answer","")}'])
third=service.run_auto_agent('so can u add more details to it',[],history=[
    'User: CAN U crate a doc explaining about nature',f'Assistant: {first.get("answer","")}',
    'User: can u create a file in knowledge explaining about nature',f'Assistant: {second.get("answer","")}'])
docs=service.documents()
names={item['display_name'] for item in docs}
checks={
    'typo_created':first['status']=='completed' and 'nature_explanation_2.txt' in names,
    'second_created':second['status']=='completed' and 'nature_explanation_3.txt' in names,
    'followup_updated':third['status']=='completed' and any(item['tool']=='document_update' and item['target']=='nature_explanation_3.txt' for item in third.get('result',{}).get('operations',[])),
    'original_preserved':source.read_text(encoding='utf-8')=='Earlier nature note.',
}
own.mkdir(parents=True,exist_ok=True)
(own/'result.json').write_text(json.dumps({'checks':checks,'seconds':time.perf_counter()-started,'results':[first,second,third]},indent=2),encoding='utf-8')
print(json.dumps({'checks':checks,'seconds':time.perf_counter()-started,'path':str(own)}),flush=True)
raise SystemExit(0 if all(checks.values()) else 1)
