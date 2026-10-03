"""Post-run independent probes drawn only from public task wording.

These probes never enter model or repair contexts and do not replace frozen
primary oracle verdicts. They can downgrade semantic confidence.
"""
import importlib.util,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
spec=importlib.util.spec_from_file_location('phase_d_eval',ROOT/'benchmarks/evaluate-phase-d.py');ev=importlib.util.module_from_spec(spec);sys.modules[spec.name]=ev;spec.loader.exec_module(ev)
OUT=ROOT/'benchmarks/phase-d-handoff'
CHECKS={
 'credits':"import math\nfor bad in (math.inf,-math.inf,math.nan):\n try: core.credit_total([bad]);raise AssertionError('accepted nonfinite')\n except (TypeError,ValueError):pass\n",
 'windows':"try: core.intersect((1,3),(4,2));raise AssertionError('accepted reversed second interval')\nexcept ValueError:pass\n",
 'baskets':"stock={'a':2};try_it=[('a',1),('a',2)]\ntry:core.purchase(stock,try_it);raise AssertionError('accepted cumulative shortage')\nexcept ValueError:pass\nassert stock=={'a':2}\n",
 'revision':"assert core.normalize('1.0.0')==(1,)\ntry:core.normalize('');raise AssertionError('accepted empty')\nexcept ValueError:pass\n",
 'runs':"v=[1,1,2];assert core.encode(v)==[(1,2),(2,1)] and v==[1,1,2]\n",
 'letters':"assert core.frequencies('..')=={}\n",
 'streams':"x=[[1,2],[3]];assert core.take_rounds(x,2)==[1,3] and x==[[1,2],[3]]\n",
 'config':"assert core.require({'x':False},'x') is False\n",
 'labels':"assert core.join_labels(['a,b','c'])=='\"a,b\",c'\n",
 'chunks':"x=[1,2,3];y=core.chunks(x,2);assert y==[[1,2],[3]] and x==[1,2,3] and y[0] is not x\n",
 'ranking':"d={'b':3,'a':3};assert core.rank(d)==['a','b'] and d=={'b':3,'a':3}\n",
 'pathsafe':"try:core.safe_parts('a\\\\b');raise AssertionError('accepted backslash')\nexcept ValueError:pass\n",
 'timestamps':"try:core.utc_hour('12:60');raise AssertionError('accepted minute 60')\nexcept ValueError:pass\n",
 'pairs':"assert core.pair_sum([1,3,2,2],4)==(0,1)\n",
 'rotation':"x=[1,2,3];y=core.rotate(x,0);assert y==x and y is not x and x==[1,2,3]\n",
 'catalog':"r={'id':0};assert core.index_unique([r])[0] is r\n",
 'distance':"assert core.manhattan([],[])==0\n",
 'brackets':"assert core.balanced('(') is False and core.balanced(']') is False\n",
 'updates':"base={'a':1};changes={'a':None,'b':False};assert core.patch(base,changes)=={'b':False} and base=={'a':1} and changes=={'a':None,'b':False}\n",
 'indentation':"assert core.indent('a\\n\\nb\\n','>')=='>a\\n\\n>b\\n'\n",
}
def main():
 result=json.loads((OUT/'results.json').read_text());assert result['state']=='COMPLETED'
 secondary_path=ROOT/'benchmarks/phase-d-repair-feedback/results.json'
 secondary=json.loads(secondary_path.read_text()) if secondary_path.exists() else {'state':'NOT_STARTED','rows':[]}
 if secondary['state']!='COMPLETED':raise RuntimeError('Secondary arm must finish before supplemental review')
 tasks={c['id']:c for c in json.loads((OUT/'tasks.json').read_text())['cases']}
 from backend.settings import Settings
 from backend.service import Workbench
 work=Workbench(settings=Settings());sandbox=work._verified_coding_sandbox();sandbox._ready()
 path=OUT/'supplemental-semantic-review.json';saved=json.loads(path.read_text()) if path.exists() else {}
 with ev.base.LiveSuiteLock(ROOT/'data/smart-code-router-live.lock'):
  for row in result['rows']+secondary['rows']:
   if row['status']!='PASS':continue
   key=f"{row['case_id']}-{row['arm']}"
   if key in saved:continue
   case=tasks[row['case_id']];attempts=row['fidelity_trace']['candidate_attempts'];last=next(a['result'] for a in reversed(attempts) if 'result' in a)
   candidate=ev.candidate_unchecked(case,last);module='feature_'+row['case_id'];script=f'import {module} as core\n'+CHECKS[row['case_id']]
   supplement=dict(case);supplement['oracle']={'kind':'trusted_tests','trusted_files':{'check.py':script},'command':['python','check.py'],'expected_exit_code':0}
   saved[key]=ev.base.validate_candidate(supplement,candidate,sandbox,60)
   path.write_text(json.dumps(saved,indent=2),encoding='utf-8');print(key,saved[key]['artifact_verified'],flush=True)
if __name__=='__main__':main()
