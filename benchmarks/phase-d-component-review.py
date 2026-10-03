"""Offline answer-bound check replay. No extra model retries or private feedback."""
import inspect,json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'benchmarks'))
import importlib.util
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,ROOT/path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
helpers=load('phase_d_offline_helpers','benchmarks/analyze-code-fidelity.py')
# Same independently controlled observer, adapting only the public adapter name.
source=inspect.getsource(helpers.controls).replace("=='service'","=='adapter'").replace("=='run'","=='execute'")
namespace=dict(vars(helpers));exec(source,namespace);controls=namespace['controls']
from backend.settings import Settings
from backend.service import Workbench
def main():
 out=ROOT/'benchmarks/phase-d-handoff';primary=json.loads((out/'results.json').read_text())
 if primary['state']!='COMPLETED':raise RuntimeError('Primary comparison must finish first')
 tasks={c['id']:c for c in json.loads((out/'tasks.json').read_text())['cases']}
 secondary=ROOT/'benchmarks/phase-d-repair-feedback/results.json';extra=json.loads(secondary.read_text()) if secondary.exists() else {'rows':[]}
 work=Workbench(settings=Settings());sandbox=work._verified_coding_sandbox();sandbox._ready()
 path=out/'component-review.json';saved=json.loads(path.read_text()) if path.exists() else {'controls':{},'candidates':{}}
 with helpers.ev.base.LiveSuiteLock(ROOT/'data/smart-code-router-live.lock'):
  for case in tasks.values():
   if case['id'] in saved['controls']:continue
   result=controls(case,case['private_reference'],sandbox)
   assert result['executed'] and result['exit_code']==0 and result['checks'] and all(c['passed'] for c in result['checks']),case['id']
   saved['controls'][case['id']]=result;path.write_text(json.dumps(saved,indent=2));print('control',case['id'],flush=True)
  for row in primary['rows']+extra['rows']:
   for index,attempt in enumerate(row['fidelity_trace']['candidate_attempts']):
    if 'result' not in attempt:continue
    key=f"{row['case_id']}-{row['arm']}-{index+1}"
    if key in saved['candidates']:continue
    files=helpers.ev.candidate_unchecked(tasks[row['case_id']],attempt['result']);saved['candidates'][key]=controls(tasks[row['case_id']],files,sandbox)
    path.write_text(json.dumps(saved,indent=2));print(key,flush=True)
if __name__=='__main__':main()
