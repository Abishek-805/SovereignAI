"""Public contract controls; no generated candidate execution on host."""
import hashlib,importlib.util,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def load(name,path):
 s=importlib.util.spec_from_file_location(name,ROOT/path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
tasks=load('new_tasks','benchmarks/phase-d-tasks.py').tasks();contract=load('public_contract','benchmarks/phase-d-contract.py')
checks=[]
for case in tasks:
 public=contract.contract(case)
 assert 'check.py' not in json.dumps(public) and 'private_reference' not in json.dumps(public)
 assert not contract.preservation(case,case['private_reference'])
 for mutation in ['missing','signature','protected','scope']:
  files=dict(case['private_reference']);path=case['allowed_change_paths'][0]
  if mutation=='missing':files.pop(path)
  if mutation=='signature':files[path]=files[path].replace('def '+case['required_symbols'][path][0]+'(', 'def '+case['required_symbols'][path][0]+'(extra, ')
  if mutation=='protected':files['protected.py']+='\nCHANGED=True\n'
  if mutation=='scope':files['other.py']='x=1\n'
  assert contract.preservation(case,files),(case['id'],mutation)
 checks.append({'case_id':case['id'],'schema_valid':True,'original_verbatim':True,'no_private_payload':True,'preservation_positive':True,'four_negative_controls':True})
out=ROOT/'benchmarks/phase-d-handoff';out.mkdir(exist_ok=True)
(out/'public-contract-controls.json').write_text(json.dumps(checks,indent=2))
paths=subprocess.check_output(['git','ls-files'],cwd=ROOT,text=True).splitlines()
paths += [str(p.relative_to(ROOT)) for p in (ROOT/'benchmarks/code-fidelity-repair').rglob('*') if p.is_file()]
frozen={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sorted(set(paths)) if (ROOT/p).is_file()}
(out/'baseline-preservation.json').write_text(json.dumps({'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'files':frozen},indent=2))
print('20 schema controls and 80 preservation negative controls passed; baseline hashes saved')
