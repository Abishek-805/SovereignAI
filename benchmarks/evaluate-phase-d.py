"""Phase C â€” Phase D Grounded Handoff. Disposable observation-only harness."""
import argparse,ast,dataclasses,hashlib,importlib.util,json,shutil,sys,time
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,ROOT/path);module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module);return module
base=load('fidelity_base','benchmarks/evaluate-smart-code-router.py')
suite_module=load('fidelity_tasks','benchmarks/phase-d-tasks.py')
contract_module=load('phase_d_contract','benchmarks/phase-d-contract.py')
OriginalProxy=base.TrustedSandboxProxy
class PreservationProxy(OriginalProxy):
 def execute(self,code,timeout=30,input_files=None):
  diagnostics=contract_module.preservation(self.case,input_files or {})
  if diagnostics:
   from router.sandbox import SandboxResult
   gate=self._sandbox.execute('import sys\nsys.exit(1)',timeout=min(timeout,30))
   self.trajectory.append({'phase':'preservation','artifact_verified':False,'diagnostics':diagnostics,'container_executed':gate.executed,'exit_code':gate.exit_code})
   return SandboxResult(1,'','Public preservation check failed: '+json.dumps(diagnostics),gate.executed)
  return super().execute(code,timeout=timeout,input_files=input_files)
base.TrustedSandboxProxy=PreservationProxy
def hashes():
 return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for folder in ['backend','router','workflows'] for p in sorted((ROOT/folder).rglob('*.py'))}
def symbols(text):
 if isinstance(text,bytes):text=text.decode('utf-8')
 try:return sorted(n.name for n in ast.parse(text).body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)))
 except SyntaxError:return []
def candidate_unchecked(case,result):
 candidate=dict(case['context']['initial_files'])
 for change in result.get('changes',[]):
  if change.get('action')=='delete':candidate.pop(change['path'],None)
  elif isinstance(change.get('after'),str):candidate[change['path']]=change['after']
 return candidate
def removed(case,results):
 records=[]
 for index,result in enumerate(results):
  candidate=candidate_unchecked(case,result)
  records.append({'attempt':index+1,'removed_files':sorted(set(case['context']['initial_files'])-set(candidate)),
   'missing_required_symbols':{p:sorted(set(names)-set(symbols(candidate.get(p,'')))) for p,names in case['required_symbols'].items()},
   'protected_files_changed':[p for p,t in case['context']['initial_files'].items() if p not in case['allowed_change_paths'] and candidate.get(p) not in (t,t.encode())]})
 return records
def observe(work,case,arm,args):
 public_contract=contract_module.contract(case)
 traces={'public_contract':public_contract,'model_requests':[],'source_generations':[],'qwen_plans':[],'candidate_attempts':[],'policy_decisions':[]}
 request=work.model._request
 def recorded_request(method,path,**kwargs):
  if method=='POST' and 'messages' in kwargs.get('json',{}):
   payload=kwargs['json'];traces['model_requests'].append({'path':path,'payload':payload})
  return request(method,path,**kwargs)
 work.model._request=recorded_request
 source=work.model.complete_code
 def recorded_source(messages,*a,**kw):
  entry={'exact_handoff_messages':messages,'generation_options':kw};traces['source_generations'].append(entry)
  try:entry['candidate']=source(messages,*a,**kw);return entry['candidate']
  except Exception as exc:entry['error']={'code':getattr(exc,'code',type(exc).__name__),'message':str(exc)};raise
 work.model.complete_code=recorded_source
 plan=work.model.plan_code_strategy
 def recorded_plan(*a,**kw):
  if arm=='C':a=(a[0],[{'public_source_contract':public_contract}])
  entry={'arguments':a,'options':kw};traces['qwen_plans'].append(entry)
  entry['plan']=plan(*a,**kw);return entry['plan']
 work.model.plan_code_strategy=recorded_plan
 classify=work._coding_request
 def classified(*a,**kw):
  decision=classify(*a,**kw)
  effective=dataclasses.replace(decision,worker_role='code',steps=('code',) if arm=='A' else ('reasoning','code')) if arm in {'A','B','C'} else decision
  traces['policy_decisions'].append({'current_router':decision.to_dict(),'effective':effective.to_dict(),'override':arm if arm!='C' else None})
  return effective
 work._coding_request=classified
 run=work.coding.run_project
 def recorded_run(*a,**kw):
  if arm=='C':
   public_contract['workspace']=a[0];contract_module.validate(public_contract,case)
   kw['history']=[*(kw.get('history') or []),'assistant: Public handoff contract (original request remains authoritative): '+json.dumps(public_contract)]
  entry={'repair_history':kw.get('history',[]),'reusable_plan':kw.get('reusable_plan')};traces['candidate_attempts'].append(entry)
  try:entry['result']=run(*a,**kw);return entry['result']
  except Exception as exc:entry['error']={'code':getattr(exc,'code',type(exc).__name__),'message':str(exc)};raise
 work.coding.run_project=recorded_run
 try:row=base.capture(case,work,args)
 finally:
  work.model._request=request;work.model.complete_code=source;work.model.plan_code_strategy=plan;work._coding_request=classify;work.coding.run_project=run
 row.update(arm=arm,original_request=case['request'],explicit_requirements=case['requirements'],fidelity_trace=traces)
 raw=ROOT/'benchmarks/phase-d-handoff/raw';raw.mkdir(exist_ok=True)
 (raw/f'{case["id"]}-{arm}-{time.time_ns()}.json').write_text(json.dumps(row,indent=2,default=str),encoding='utf-8')
 results=[x['result'] for x in traces['candidate_attempts'] if 'result' in x]
 row['preservation_audit']=removed(case,results)
 row['status']='PASS' if row['correctness'] is True else 'FAIL' if row['operational_result'].get('state')=='failed' or row['correctness'] is False else 'NOT_VERIFIED'
 row['failure_classification']={'labels':(['MODEL_GENERATION']+(['REPAIR'] if len(results)>1 else [])) if row['status']=='FAIL' and results else [],'review_required':True,'router_blame_established':False}
 return row
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--live',action='store_true');parser.add_argument('--resume',action='store_true');parser.add_argument('--timeout',type=float,default=300);args=parser.parse_args()
 output=ROOT/'benchmarks/phase-d-handoff';output.mkdir(exist_ok=True)
 cases=suite_module.tasks();dataset={'name':'Phase D Grounded Handoff','author':'Independent Codex diagnostic author, not evaluated Qwen/Coder models','cases':cases}
 dataset_path=output/'tasks.json';dataset_bytes=json.dumps(dataset,indent=2).encode()
 if dataset_path.exists() and dataset_path.read_bytes()!=dataset_bytes:raise ValueError('Diagnostic tasks changed')
 dataset_path.write_bytes(dataset_bytes)
 for case in cases:
  for path,text in case['context']['initial_files'].items():compile(text,path,'exec')
  compile(case['oracle']['trusted_files']['check.py'],'check.py','exec')
 if not args.live:print(json.dumps({'name':dataset['name'],'tasks':len(cases),'executions':len(cases)*3,'live':False}));return
 from backend.settings import Settings
 from backend.service import Workbench
 from router.model_registry import ModelRegistry
 settings=Settings();initial=hashes();provenance={'production':initial,'dataset_sha256':hashlib.sha256(dataset_bytes).hexdigest(),
  'harness_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'timeout':args.timeout,
  'policy':'Phase D: A Coder direct, B existing Qwen plan then Coder, C same Qwen/Coder with grounded structured handoff. Common preservation validation, unchanged repair budget/feedback. Isolated instance overrides only, router production frozen.'}
 result_path=output/'results.json'
 if result_path.exists():
  if not args.resume:raise ValueError('Evidence exists; use explicit strict resume')
  report=json.loads(result_path.read_text());assert report['provenance']==provenance,'Resume provenance changed'
 else:report={'name':dataset['name'],'provenance':provenance,'state':'RUNNING','oracle_controls':[],'rows':[]}
 def save():
  tmp=result_path.with_suffix('.tmp');tmp.write_text(json.dumps(report,indent=2,default=str),encoding='utf-8');tmp.replace(result_path)
 with base.LiveSuiteLock(ROOT/'data/smart-code-router-live.lock'),TemporaryDirectory(prefix='code-fidelity-') as temp:
  report['idle_check']=base.check_backend_idle(settings,'http://127.0.0.1:8765',[])
  isolated=Settings(data_dir=Path(temp)/'data',project_dir=Path(temp)/'projects',supervisor_seconds=args.timeout)
  isolated.data_dir.mkdir();shutil.copyfile(settings.data_dir/'sandbox-validation.json',isolated.data_dir/'sandbox-validation.json')
  work=Workbench(settings=isolated,registry=ModelRegistry(8087));work._record_model_outcome=lambda *a,**kw:None
  sandbox=work._verified_coding_sandbox();sandbox._ready()
  completed_controls={x['case_id'] for x in report['oracle_controls']}
  for case in cases:
   if case['id'] in completed_controls:continue
   positive=base.validate_candidate(case,case['private_reference'],sandbox,120)
   negative=base.validate_candidate(case,case['context']['initial_files'],sandbox,120)
   report['oracle_controls'].append({'case_id':case['id'],'positive':positive,'negative':negative});save()
   if not positive['artifact_verified'] or negative['artifact_verified']:raise RuntimeError('Oracle control failed: '+case['id'])
  args.dataset=dataset_path;args.sample_resources=True
  done={(r['case_id'],r['arm']) for r in report['rows']}
  for i,case in enumerate(cases):
   order=['A','B','C'];order=order[i%3:]+order[:i%3]
   for arm in order:
    if (case['id'],arm) in done:continue
    if hashes()!=initial:raise RuntimeError('Production changed; stop without mixing evidence')
    row=observe(work,case,arm,args);report['rows'].append(row);save()
    print(json.dumps({'case':case['id'],'arm':arm,'status':row['status'],'completed':len(report['rows'])}),flush=True)
    if base.should_stop(row['operational_result']):report['state']='STOPPED';save();return
  report['state']='COMPLETED';report['production_unchanged']=hashes()==initial;save()
if __name__=='__main__':main()
