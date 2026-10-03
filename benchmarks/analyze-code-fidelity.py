"""Offline Phase C paired analysis; optionally check each saved candidate in Docker.

No observations here enter the model or modify production behavior.
"""
import argparse,ast,hashlib,importlib.util,json,math,random,statistics,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
spec=importlib.util.spec_from_file_location('fidelity_eval',ROOT/'benchmarks/evaluate-code-fidelity.py');ev=importlib.util.module_from_spec(spec);spec.loader.exec_module(ev)
OUT=ROOT/'benchmarks/code-fidelity-repair'
def bindings(text):
 try:
  names=set()
  for node in ast.parse(text).body:
   if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)):names.add(node.name)
   if isinstance(node,(ast.Assign,ast.AnnAssign)):
    for target in node.targets if isinstance(node,ast.Assign) else [node.target]:
     if isinstance(target,ast.Name):names.add(target.id)
  return names
 except SyntaxError:return None
def preservation(case,result):
 candidate=ev.candidate_unchecked(case,result);missing={}
 for path,names in case['required_symbols'].items():
  found=bindings(candidate.get(path,''));missing[path]=sorted(set(names)-found) if found is not None else None
 return {'removed_files':sorted(set(case['context']['initial_files'])-set(candidate)), 'missing_required_bindings':missing,
  'protected_paths_targeted':sorted({c['path'] for c in result.get('changes',[]) if c['path'] not in case['allowed_change_paths']}),
  'protected_files_changed':[p for p,t in case['context']['initial_files'].items() if p not in case['allowed_change_paths'] and candidate.get(p)!=t]}
def controls(case,candidate,sandbox):
 oracle=case['oracle']['trusted_files']['check.py']
 script='''import ast,json,os,sys,shutil
shutil.copytree('/input/candidate','/output/candidate')
os.chdir('/output/candidate');sys.path.insert(0,'/output/candidate')
tree=ast.parse(open('/input/trusted/check.py').read());namespace={};results=[]
for index,node in enumerate(tree.body):
    check=isinstance(node,ast.Assert) or (isinstance(node,ast.Expr) and isinstance(node.value,ast.Call) and isinstance(node.value.func,ast.Name) and node.value.func.id=='raises')
    try:
        exec(compile(ast.Module(body=[node],type_ignores=[]),'<trusted-component>','exec'),namespace)
        if check:results.append({'index':index,'passed':True})
    except Exception as error:
        results.append({'index':index,'passed':False,'error':type(error).__name__,'setup':not check})
try:
    import copy,importlib
    target=next(n.left for statement in tree.body if isinstance(statement,ast.Assert) for n in [statement.test] if isinstance(n,ast.Compare) and isinstance(n.left,ast.Call) and isinstance(n.left.func,ast.Attribute) and isinstance(n.left.func.value,ast.Name) and n.left.func.value.id=='service' and n.left.func.attr=='run')
    importlib.reload(namespace['core']);namespace['f']=getattr(namespace['core'],next(n.value.attr for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='f' for t in n.targets)))
    arguments=eval(compile(ast.fix_missing_locations(ast.Expression(ast.Tuple(elts=target.args,ctx=ast.Load()))),'<trusted-arguments>','eval'),namespace)
    before=copy.deepcopy(arguments);namespace['f'](*arguments)
    results.append({'index':-1,'passed':arguments==before,'check':'sample-input-preservation'})
except Exception as error:
    results.append({'index':-1,'passed':False,'error':type(error).__name__,'check':'sample-input-preservation'})
print('FIDELITY_COMPONENTS='+json.dumps(results))
'''
 inputs={'candidate/'+p:t if isinstance(t,bytes) else t.encode() for p,t in candidate.items()};inputs['trusted/check.py']=oracle.encode()
 result=sandbox.execute(script,timeout=60,input_files=inputs)
 lines=[x for x in result.stdout.splitlines() if x.startswith('FIDELITY_COMPONENTS=')]
 return {'executed':result.executed,'exit_code':result.exit_code,'checks':json.loads(lines[-1].split('=',1)[1]) if lines else None,'stderr':result.stderr}
def boot(values):
 if not values:return None
 rng=random.Random(31003);samples=sorted(statistics.mean(rng.choices(values,k=len(values))) for _ in range(5000))
 return [samples[125],samples[4874]]
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--validate-components',action='store_true');args=parser.parse_args()
 report=json.loads((OUT/'results.json').read_text());cases={c['id']:c for c in json.loads((OUT/'tasks.json').read_text())['cases']}
 for row in report['rows']:
  row['raw_status']=row['status']
  if row['status']=='NOT_VERIFIED' and row['operational_result'].get('error'):row['status']='FAIL'
 components_path=OUT/'component-validation.json';components=json.loads(components_path.read_text()) if components_path.exists() else {}
 if args.validate_components:
  if report['state']!='COMPLETED':raise RuntimeError('Wait for complete comparison before offline candidate analysis')
  from backend.settings import Settings
  from backend.service import Workbench
  work=Workbench(settings=Settings());sandbox=work._verified_coding_sandbox();sandbox._ready()
  with ev.base.LiveSuiteLock(ROOT/'data/smart-code-router-live.lock'):
   for row in report['rows']:
    for i,attempt in enumerate(row['fidelity_trace']['candidate_attempts']):
     if 'result' not in attempt:continue
     key=f'{row["case_id"]}-{row["arm"]}-{i+1}'
     if key in components:continue
     candidate=ev.candidate_unchecked(cases[row['case_id']],attempt['result'])
     components[key]=controls(cases[row['case_id']],candidate,sandbox)
     components_path.write_text(json.dumps(components,indent=2),encoding='utf-8')
     print(key,flush=True)
 reviewed=[]
 for row in report['rows']:
  trace=row['fidelity_trace'];labels=[];evidence=[]
  attempts=trace['candidate_attempts'];generated=[g for g in trace['source_generations'] if 'candidate' in g]
  all_present=all(any(row['original_request'] in str(m.get('content','')) or (isinstance(m.get('content'),str) and row['original_request'] in str(_parse(m['content']))) for m in g['exact_handoff_messages']) for g in generated) if generated else None
  if row['status']!='PASS':
   error=row['operational_result'].get('error',{});code=error.get('code')
   if code in {'sandbox_unavailable','docker_unavailable'}:labels.append('SANDBOX')
   elif code in {'generation_format','semantic_uncertainty'}:
    labels.append('MODEL_GENERATION' if trace['source_generations'] else 'PLAN');evidence.append('Observed generation/semantic contract error: '+str(error.get('message','')))
   elif code=='invalid_file' and 'plan' in str(error.get('message','')).lower():labels.append('PLAN');evidence.append('Existing tool rejected a malformed workspace operation plan; rejection is not evidence of a tool malfunction.')
   elif code in {'workspace_conflict','invalid_file','invalid_workspace','tool_input'}:labels.append('TOOL');evidence.append('Tool boundary error: '+str(error.get('message','')))
   elif generated:labels.append('MODEL_GENERATION');evidence.append('Saved source candidate failed independent contract validation.')
   elif trace['qwen_plans']:labels.append('PLAN');evidence.append('Qwen planning path did not reach a saved source candidate; inspect exact planner response/error before assigning cause.')
   else:labels.append('VALIDATION');evidence.append('No independently verified artifact; root cause requires raw trace review.')
   if len(attempts)>1:labels.append('REPAIR');evidence.append('Bounded repair did not produce an independently passing final artifact.')
   if any(v.get('artifact_verified') is False for v in row['validation_trajectory']) and 'MODEL_GENERATION' not in labels:labels.append('MODEL_GENERATION');evidence.append('An assembled source candidate independently failed trusted validation before the final boundary error.')
   if all_present is False:labels.append('CONTEXT');evidence.append('Literal original request missing from at least one source handoff; semantic omission requires review.')
  regressions=[]
  prior=None
  for i,attempt in enumerate(attempts):
   key=f'{row["case_id"]}-{row["arm"]}-{i+1}';checks=components.get(key,{}).get('checks')
   current={c['index']:c['passed'] for c in checks or [] if not c.get('setup') and c['index'] != -1}
   if prior is not None:regressions.append({'attempt':i+1,'previously_passing_checks_now_failed':[k for k,v in prior.items() if v and current.get(k) is False]})
   prior=current if checks is not None else None
  syntax=[]
  for i,g in enumerate(generated):
   code=g['candidate'].get('code','')
   try:ast.parse(code);syntax.append({'generation':i+1,'syntax_valid':True})
   except SyntaxError as exc:syntax.append({'generation':i+1,'syntax_valid':False,'line':exc.lineno,'error':exc.msg})
  audited=[preservation(cases[row['case_id']],a['result']) for a in attempts if 'result' in a]
  generation_audits=[]
  for g in generated:
   context=next((_parse(m['content']) for m in g['exact_handoff_messages'] if isinstance(m.get('content'),str) and isinstance(_parse(m['content']),dict) and 'path' in _parse(m['content'])),{})
   path=context.get('path');code=g['candidate']['code'];found=bindings(code)
   generation_audits.append({'path':path,'syntax_valid':found is not None,'missing_required_bindings':sorted(set(cases[row['case_id']]['required_symbols'].get(path,[]))-found) if found is not None else None,
    'protected_path_proposal_changed':path not in cases[row['case_id']]['allowed_change_paths'] and code!=cases[row['case_id']]['context']['initial_files'].get(path)})
  if any(a['protected_paths_targeted'] for a in audited) and 'PLAN' not in labels:labels.append('PLAN');evidence.append('Workspace plan targeted an explicitly protected file; distinguish targeted paths from actual byte changes.')
  reviewed.append({'case_id':row['case_id'],'arm':row['arm'],'status':row['status'],'raw_status':row['raw_status'],'failure_classes':labels,'evidence':evidence,'source_syntax':syntax,'generation_preservation':generation_audits,
   'original_request_in_all_source_handoffs':all_present,'repair_regressions':regressions,'preservation_audit':audited,
   'router_fault_established':False,'semantic_plan_review_required':True})
 summary={}
 for arm in 'ABC':
  rows=[r for r in report['rows'] if r['arm']==arm]
  summary[arm]={'n':len(rows),'pass':sum(r['status']=='PASS' for r in rows),'fail':sum(r['status']=='FAIL' for r in rows),'not_verified':sum(r['status']=='NOT_VERIFIED' for r in rows),
   'latency_median':statistics.median(r['measurements']['latency_seconds'] for r in rows) if rows else None,
   'model_calls':sum(r['measurements'].get('model_calls') or 0 for r in rows),'switches':sum(r['measurements'].get('model_switches') or 0 for r in rows),
   'independently_verified_recoveries':sum(r.get('repair_succeeded') is True for r in rows)}
 pairs={}
 for a,b in [('A','B'),('A','C'),('B','C')]:
  left={r['case_id']:r for r in report['rows'] if r['arm']==a};right={r['case_id']:r for r in report['rows'] if r['arm']==b};keys=sorted(left.keys()&right.keys())
  wins_a=sum(left[k]['status']=='PASS' and right[k]['status']!='PASS' for k in keys);wins_b=sum(right[k]['status']=='PASS' and left[k]['status']!='PASS' for k in keys);n=wins_a+wins_b
  deltas=[(right[k]['status']=='PASS')-(left[k]['status']=='PASS') for k in keys]
  pairs[a+b]={'paired_tasks':len(keys),a+'_only_pass':wins_a,b+'_only_pass':wins_b,'pass_rate_delta_'+b+'_minus_'+a:statistics.mean(deltas) if deltas else None,
   'task_cluster_bootstrap_95_interval':boot(deltas),'exact_discordant_binomial_p':min(1,2*sum(math.comb(n,i) for i in range(min(wins_a,wins_b)+1))/2**n) if n else 1,
   'latency_delta_median':statistics.median(right[k]['measurements']['latency_seconds']-left[k]['measurements']['latency_seconds'] for k in keys) if keys else None}
 freeze=json.loads((OUT/'freeze-manifest.json').read_text());historical=json.loads((OUT/'historical-evidence-manifest.json').read_text());frozen={**freeze['files'],**historical['files']};changed=[p for p,h in frozen.items() if not (ROOT/p).exists() or hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=h]
 result={'state':report['state'],'summary':summary,'paired_analysis':pairs,'review':reviewed,'freeze_changes':changed,
  'limits':['20 distinct two-file contracts, common service skeleton; not 60 independent tasks or a large-application sample.',
   'Paired bootstrap resamples task contracts, not individual arm executions; confidence intervals are exploratory.',
   'Carryover residency is recorded and arm order rotates; latency is not a cold-start equalized trial.',
   'Offline per-statement checks share setup and execute sequentially; they expose regressions but do not exhaust all possible behavior.',
   'Plans require exact semantic reading; full request retention alone does not prove model comprehension.']}
 (OUT/'analysis.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps({'summary':summary,'paired_analysis':pairs,'freeze_changes':changed},indent=2))
 evidence=[]
 for row in report['rows']:
  trace=row['fidelity_trace'];attempts=trace['candidate_attempts']
  evidence.append({'case_id':row['case_id'],'arm':row['arm'],
   '1_original_request':row['original_request'],'2_explicit_requirements':row['explicit_requirements'],
   '3_router_decision':trace['policy_decisions'],'4_selected_model':row['prediction'],
   '5_qwen_plan':trace['qwen_plans'],'6_exact_coder_handoff':[g['exact_handoff_messages'] for g in trace['source_generations']],
   '7_generated_candidate':[g.get('candidate',g.get('error')) for g in trace['source_generations']],
   '8_candidate_diff':[a.get('result',{}).get('diff') for a in attempts],
   '9_docker_result':row['validation_trajectory'],
   '10_exact_bounded_error':[a.get('result',{}).get('stderr',a.get('error')) for a in attempts],
   '11_repair_context':[a['repair_history'] for a in attempts[1:]],
   '12_repaired_candidate':[a.get('result',{}).get('changes') for a in attempts[1:]],
   '13_independent_validation':row['validation'],'14_preservation_audit':next(r['preservation_audit'] for r in reviewed if r['case_id']==row['case_id'] and r['arm']==row['arm']),
   '15_latency':row['measurements']['latency_seconds'],'16_model_calls':row['measurements']['model_calls'],
   '17_model_switches':row['measurements']['model_switches'],
   'nonexecution_note':'Empty validation trajectory means no complete candidate reached Docker trusted tests; inspect captured stage error, not a passing result.'})
 (OUT/'evidence-index.json').write_text(json.dumps({'state':report['state'],'records':evidence},indent=2),encoding='utf-8')
def _parse(text):
 try:return json.loads(text)
 except (ValueError,TypeError):return text
if __name__=='__main__':main()
