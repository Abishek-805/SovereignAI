"""Verify offline component observer against independent positive controls."""
import importlib.util,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
an=load('component_analysis',ROOT/'benchmarks/analyze-code-fidelity.py')
ref=load('positive_reference',ROOT/'benchmarks/code-fidelity-reference.py')
from backend.settings import Settings
from backend.service import Workbench
work=Workbench(settings=Settings());sandbox=work._verified_coding_sandbox();sandbox._ready()
cases=json.loads((an.OUT/'tasks.json').read_text())['cases'];results={}
with an.ev.base.LiveSuiteLock(ROOT/'data/smart-code-router-live.lock'):
 for case in cases:
  result=an.controls(case,ref.files(case),sandbox);results[case['id']]=result
  (an.OUT/'component-positive-controls.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
  assert result['executed'] and result['exit_code']==0 and result['checks'] and all(c['passed'] for c in result['checks']),case['id']
  print(case['id'],flush=True)
