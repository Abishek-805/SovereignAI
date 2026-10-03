"""Independent offline Phase D analysis, never input to evaluated workers."""
import ast,hashlib,importlib.util,json,statistics,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,ROOT/path);m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m
prior=load('phase_d_analysis_helpers','benchmarks/analyze-code-fidelity.py')
contract=load('phase_d_public','benchmarks/phase-d-contract.py')
OUT=ROOT/'benchmarks/phase-d-handoff'
def _parse_message(content):
 try:return json.loads(content) if isinstance(content,str) else None
 except (ValueError,TypeError):return None
def main():
 p=json.loads((OUT/'results.json').read_text());cases={c['id']:c for c in json.loads((OUT/'tasks.json').read_text())['cases']}
 secondary=ROOT/'benchmarks/phase-d-repair-feedback/results.json';q=json.loads(secondary.read_text()) if secondary.exists() else {'state':'NOT_STARTED','rows':[]}
 rows=p['rows']+q['rows'];review=[]
 for row in rows:
  case=cases[row['case_id']];trace=row['fidelity_trace'];attempts=trace['candidate_attempts'];audits=[]
  for attempt in attempts:
   if 'result' not in attempt:continue
   files=prior.ev.candidate_unchecked(case,attempt['result'])
   audits.append({'preservation':contract.preservation(case,files),'stderr':attempt['result'].get('stderr'),'state':attempt['result'].get('state')})
  source=[]
  for g in trace['source_generations']:
   if 'candidate' not in g:continue
   text=g['candidate'].get('code','')
   try:ast.parse(text);valid=True
   except SyntaxError:valid=False
   source.append({'syntax_valid':valid,'original_verbatim':any(isinstance(_parse_message(m.get('content')),dict) and _parse_message(m.get('content')).get('task')==case['request'] for m in g['exact_handoff_messages'])})
  error=row['operational_result'].get('error') or {};msg=error.get('message','');tags=[]
  status='PASS' if row['status']=='PASS' else 'FAIL' if error or row['status']=='FAIL' else 'NOT VERIFIED'
  if status!='PASS':
   if error.get('code') in {'model_unavailable','timeout'}:tags.append('RUNTIME')
   elif error.get('code') in {'sandbox_unavailable','docker_unavailable'}:tags.append('SANDBOX')
   elif 'plan' in msg.lower() or 'fixture-protected' in msg:tags.append('PLAN')
   elif error.get('code')=='generation_format':tags.append('MODEL_GENERATION' if trace['source_generations'] else 'PLAN')
   elif error:tags.append('TOOL')
   if any(v.get('artifact_verified') is False for v in row['validation_trajectory']) or any(not g['syntax_valid'] for g in source):tags.append('MODEL_GENERATION')
   if len(attempts)>1:tags.append('REPAIR')
   if any(not g['original_verbatim'] for g in source):tags.append('HANDOFF')
   if not tags:tags.append('VALIDATION')
  grounded=bool(trace['qwen_plans']) and 'public_source_contract' in str(trace['qwen_plans'][0]['arguments'])
  public_contract=trace.get('public_contract') or {}
  expected_interfaces=sum(len([n for n in __import__('ast').parse(text).body if isinstance(n,(__import__('ast').FunctionDef,__import__('ast').AsyncFunctionDef))]) for text in case['context']['initial_files'].values())
  supplied_interfaces=sum(len(v.get('functions',[])) for v in public_contract.get('exact_public_interfaces',{}).values())
  coder_handoffs=[g['exact_handoff_messages'] for g in trace['source_generations']]
  contract_handoff_complete=(all(any(isinstance(_parse_message(m.get('content')),dict) and _parse_message(m.get('content')).get('task')==case['request'] and
   any('Public handoff contract' in item and 'original_user_request' in item for item in _parse_message(m.get('content')).get('recent_conversation',[])) for m in messages) for messages in coder_handoffs) if coder_handoffs else None)
  review.append({'case_id':row['case_id'],'arm':row['arm'],'status':status,'raw_status':row['status'],'failure_classes':sorted(set(tags)),'boundary_error':error,
   'source_grounding_supplied':grounded,'source_interface_completeness':{'expected':expected_interfaces,'supplied':supplied_interfaces,'complete':supplied_interfaces==expected_interfaces} if row['arm'] in {'C','R'} else None,
   'public_contract_valid':bool(public_contract) if row['arm'] in {'C','R'} else None,'coder_handoff_complete':contract_handoff_complete if row['arm'] in {'C','R'} else None,'source_candidates':source,'candidate_preservation':audits,
   'repair_failure':len(attempts)>1 and status!='PASS','repair_verified_recovery':row.get('repair_succeeded') is True,
   'publication':row['publication'],'original_sources_preserved':row['validation'].get('original_sources_preserved'),
   'semantic_plan_validity':'UNKNOWN until semantic trace review; grounded input alone is not a valid plan',
   'behavioral_status':'PASS under private finite oracle' if status=='PASS' else 'FAIL/NOT VERIFIED; see exact trajectory'})
 summary={}
 for arm in 'ABCR':
  rs=[r for r in rows if r['arm']==arm]
  if not rs:continue
  summary[arm]={'n':len(rs),'pass':sum(r['status']=='PASS' for r in rs),'median_seconds':statistics.median(r['measurements']['latency_seconds'] for r in rs),
   'model_calls':sum(r['measurements'].get('model_calls') or 0 for r in rs),'switches':sum(r['measurements'].get('model_switches') or 0 for r in rs),
   'verified_repairs':sum(r.get('repair_succeeded') is True for r in rs),'repair_tasks':sum(len(r['fidelity_trace']['candidate_attempts'])>1 for r in rs),
   'verified_behavioral_repairs':sum(r.get('repair_succeeded') is True and any(v['phase']=='trusted_tests' and v.get('artifact_verified') is False for v in r['validation_trajectory']) for r in rs),
   'peak_ram_mib':max(r['measurements']['peak_ram_mib'] for r in rs),'peak_vram_mib':max(r['measurements']['peak_vram_mib'] for r in rs)}
 pairs={}
 for left,right in [('A','B'),('B','C'),('A','C'),('C','R')]:
  x={r['case_id']:r for r in rows if r['arm']==left};y={r['case_id']:r for r in rows if r['arm']==right};keys=sorted(set(x)&set(y))
  if not keys:continue
  delta=[int(y[k]['status']=='PASS')-int(x[k]['status']=='PASS') for k in keys]
  pairs[left+right]={'n_tasks':len(keys),'left_only_pass':sum(v==-1 for v in delta),'right_only_pass':sum(v==1 for v in delta),'pass_delta':statistics.mean(delta),'task_bootstrap95':prior.boot(delta),
   'median_paired_latency_delta':statistics.median(y[k]['measurements']['latency_seconds']-x[k]['measurements']['latency_seconds'] for k in keys)}
  if right=='R':
   def first_candidate(row):
    attempt=next((at['result'] for at in row['fidelity_trace']['candidate_attempts'] if 'result' in at),None)
    return [(c.get('action'),c.get('path'),c.get('after')) for c in attempt.get('changes',[])] if attempt else None
   pairs[left+right]['initial_candidate_identical_tasks']=[k for k in keys if first_candidate(x[k]) is not None and first_candidate(x[k])==first_candidate(y[k])]
 frozen=json.loads((OUT/'baseline-preservation.json').read_text());changes=[name for name,digest in frozen['files'].items() if not (ROOT/name).exists() or hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest]
 result={'primary_state':p['state'],'secondary_state':q['state'],'summary':summary,'paired':pairs,'review':review,'frozen_changes':changes,
 'limits':['20 multi-file contracts share an adapter skeleton; not broad application tasks.','One execution per arm, rotating order with warm residency carryover.','Secondary R is run later; temporal/resource drift can confound latency.','Preservation gate common to all arms changes evaluation controls, not production scaffold.','Source-grounding and structured handoff change together in C; they cannot be individually attributed.','Private oracles are finite; do not prove every requested corner case.','Structured repair feedback flags public-source risks, not hidden assertion values.']}
 (OUT/'analysis.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
 print(json.dumps({'summary':summary,'paired':pairs,'frozen_changes':changes},indent=2))
if __name__=='__main__':main()
