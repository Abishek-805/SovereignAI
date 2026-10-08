"""Sequential isolated fidelity evaluation, shared infrastructure and frozen fixtures."""
import argparse,csv,hashlib,json,re,shutil,threading,time
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import httpx,psutil
from backend.task_supervisor import TaskSupervisor,SupervisorLimits,CURRENT_SUPERVISOR
from router.coding_router import classify_coding_request
from router.model_registry import ModelRegistry,default_specs
from router.model_broker import ModelBroker
from workflows.coding_workspace import CodingWorkspace
from experiments.kernel_docker import DockerCommands
from experiments.benchmark_resources import ResourceSamples
from experiments.fidelity_v1.tasks import ROOT,OUT
from experiments.fidelity_v1.runners import load_native,configure,Trace,EvidenceModel,digest
from experiments.fidelity_v1.controls import check
ARMS=('native_v1','nanobot_minimal','hermes_minimal')
FOLDERS={'native_v1':'native','nanobot_minimal':'nanobot','hermes_minimal':'hermes'}
def save(path,value):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
 temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(value,indent=2,ensure_ascii=False),encoding='utf-8');temporary.replace(path)
def sources_unchanged():
 manifest=json.loads((OUT/'reports/baseline-manifest.json').read_text())
 for name,expected in manifest['source_sha256'].items():
  if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=expected:raise RuntimeError('Frozen shared source changed: '+name)
 path=OUT/'reports/tasks.json'
 if hashlib.sha256(path.read_bytes()).hexdigest()!=(OUT/'reports/tasks.sha256').read_text():raise RuntimeError('Frozen task suite changed')
def servers():return [p for p in psutil.process_iter(['name','cmdline']) if (p.info['name'] or '').lower()=='llama-server.exe']
def idle():
 status=httpx.get('http://127.0.0.1:8088/status',timeout=5).json()
 if status.get('busy') or status.get('active_jobs'):raise RuntimeError('Production API has an active job; experiment must yield')
 processes=servers()
 if len(processes)>1:raise RuntimeError('Multiple heavy model servers observed; no experiment launch permitted')
 if processes:
  slots=httpx.get('http://127.0.0.1:8087/slots',timeout=5).json()
  if not isinstance(slots,list) or any(s.get('is_processing') for s in slots):raise RuntimeError('Active generation; do not switch or interrupt')
 return processes
def current_identity():
 processes=servers()
 if len(processes)!=1:raise RuntimeError('Expected exactly one heavy worker')
 arguments=processes[0].info['cmdline'];path=next(arguments[i+1] for i,arg in enumerate(arguments[:-1]) if arg in ('-m','--model'))
 return {'pid':processes[0].pid,'path':str(Path(path).resolve()),'command':arguments}
def failure(result,exception,trace):
 message=str(exception or result.get('error') or '')
 code=getattr(exception,'code',None) or (trace.events[-1].get('error',{}).get('code') if trace.events else None)
 if 'output budget' in message or 'budget' in message or 'BUDGET' in result.get('agent_state',''):return 'BUDGET'
 if 'Workspace changed' in message or code=='workspace_conflict':return 'CONTEXT'
 if 'sandbox' in message.lower() or code=='sandbox_unavailable':return 'SANDBOX'
 if code in {'model_unavailable','model_loading','model_timeout'}:return 'HARNESS'
 if code=='generation_format' or 'invalid JSON' in message:return 'GENERATION'
 if trace.repairs and not trace.repairs[-1]['failure'].get('passed'):return 'REPAIR' if len(trace.repairs)>1 else 'GENERATION'
 if result.get('agent_state')=='BLOCKED':return 'VALIDATION'
 return 'OTHER'
def run_one(task,runner,model_name,identity,stage):
 sources_unchanged();idle()
 folder=OUT/FOLDERS[runner] if stage=='runners' else OUT/'models'/model_name
 directory=folder/task['task_id'];directory.mkdir(parents=True,exist_ok=True)
 completed=directory/'row.json'
 if completed.exists():
  previous=json.loads(completed.read_text())
  adjudication=directory/'environment-adjudication.json'
  if not adjudication.exists() or not json.loads(adjudication.read_text()).get('rerun_authorized'):return previous
  if previous.get('model_calls')!=0 or previous.get('failure_category')!='SANDBOX':return previous
  archive=directory/'row.environment-blocked.json'
  if not archive.exists():shutil.copy2(completed,archive)
 # Environment admission before model generation. Never sweep an unavailable
 # Docker engine across the suite as if each task were a model failure.
 DockerCommands(ROOT,directory/'preflight-sandbox').sandbox._ready()
 prior=len(list(directory.glob('attempt-*')));attempt=directory/('attempt-'+str(prior+1).zfill(2));attempt.mkdir()
 coding=CodingWorkspace(attempt/'workspaces')
 wid=hashlib.sha256(task['task_id'].encode()).hexdigest()[:32]
 with patch('workflows.coding_workspace.uuid4',lambda:SimpleNamespace(hex=wid)):coding.create(task['task_id'])
 for name,content in task['files'].items():coding.write(wid,name,content)
 original=coding.raw_files(wid);cancel=threading.Event();job=SimpleNamespace(cancel=cancel)
 supervisor=TaskSupervisor(task['request'],{'workspace_id':wid,'document_ids':[]},SupervisorLimits(model_calls=32,tool_calls=64,model_switches=1,seconds=660),job)
 native=load_native();initial=json.loads((OUT/'reports/oracle-controls'/(task['task_id']+'.json')).read_text())['negative']['properties']
 trace=Trace(attempt,initial);model=EvidenceModel(attempt,runner,task['task_id'],skills_enabled=True,wire_capture=stage=='models')
 oracle=DockerCommands(ROOT,attempt/'sandbox').sandbox
 observed=classify_coding_request(task['request'],{'workspace_available':True,'requested_files':tuple(n for n in task['files'] if n.endswith(('.py','.js','.html')) and not n.startswith('test_') and n in task['request'])})
 save(attempt/'fixture.json',{'task_id':task['task_id'],'request':task['request'],'files':task['files'],'mode':task['mode'],'workspace_id':wid,'initial_revision':native.WorkspaceManager.digest(original),'router_proposal':observed.to_dict(),'fixed_worker':model_name,'source_suite_hash':(OUT/'reports/tasks.sha256').read_text()})
 triggered=[False]
 def injection(message):
  if triggered[0]:return
  triggered[0]=True
  if task['mode']=='cancel':cancel.set();trace.events.append({'event':'controlled_cancellation','boundary':'after first real model response; before tool execution'})
  if task['mode']=='conflict':
   token=CURRENT_SUPERVISOR.set(None)
   try:coding.write(wid,'keep.txt','external actor revision\n')
   finally:CURRENT_SUPERVISOR.reset(token)
   trace.events.append({'event':'controlled_external_revision','path':'keep.txt'})
 model.after_response=injection
 start=time.monotonic();result={};error=None;post=None;accepted=False;validated=False;control=task['task_id']>='T12'
 token=CURRENT_SUPERVISOR.set(supervisor)
 sampler=ResourceSamples(identity['pid'])
 try:
  with sampler,model.cancel_scope(cancel):
   # No new supervisor/router/registry. A fresh snapshot namespace isolates wrappers.
   loop=configure(native,runner,trace)
   result=loop.run(coding,wid,task['request'],model,oracle,'sovereign-text',cancel=cancel,timeout_seconds=600)
  save(attempt/'result.json',result)
 except Exception as exc:
  error=exc;result={'state':'failed','error':str(exc),'error_code':getattr(exc,'code',None)};save(attempt/'exception.json',result)
 finally:
  CURRENT_SUPERVISOR.reset(token);model.close();trace.save('trajectory',trace.events)
  save(attempt/'supervisor.json',supervisor.snapshot());save(attempt/'resources.json',sampler.result())
  for name in ('server.stdout.log','server.stderr.log'):
   path=ROOT/'benchmarks'/name
   if path.exists():shutil.copy2(path,attempt/('runtime-'+name))
 unchanged=coding.raw_files(wid)==original
 if task['mode']=='cancel':validated=result.get('agent_state')=='CANCELLED' and unchanged
 elif task['mode']=='conflict':validated=getattr(error,'code',None)=='workspace_conflict' and coding.read(wid,'lifecycle.py')['content']==task['files']['lifecycle.py'] and coding.read(wid,'keep.txt')['content']=='external actor revision\n'
 elif result.get('state')=='completed' and unchanged:
  if task['mode']=='reject':
   rejection=coding.discard(wid,result['task_id']);save(attempt/'explicit-rejection.json',rejection);validated=coding.raw_files(wid)==original and rejection['publication_state']=='discarded'
  else:
   save(attempt/'accept-intent.json',{'actor':'separate authorized QA acceptance harness','workspace_id':wid,'task_id':result['task_id'],'source':'Master prompt acceptance test; isolated fixtures only','not_model_action':True})
   try:
    publication=coding.accept(wid,result['task_id']);save(attempt/'explicit-accept.json',publication);accepted=publication.get('publication_state')=='published'
    post=check({n:b.decode() for n,b in coding.raw_files(wid).items()},oracle);save(attempt/'post-accept-oracle.json',post)
    validated=post['container_executed'] and post['exit_code']==0 and coding.read(wid,'keep.txt')['content']==task['files']['keep.txt']
   except Exception as exc:error=exc;save(attempt/'accept-error.json',{'code':getattr(exc,'code',None),'message':str(exc)})
 metrics=result.get('metrics') or (getattr(model,'session',None).__dict__ if getattr(model,'session',None) else {})
 resources=sampler.result();properties=post.get('properties') if post else trace.repairs[-1].get('properties') if trace.repairs else {}
 row={'phase':stage,'task_id':task['task_id'],'category':task['category'],'control':control,'runner':runner,'model':model_name,'accepted':accepted,'validated':bool(validated),
  'status':'PASS' if validated and (control or accepted) else 'BLOCKED' if not model.records and getattr(error,'code',None) in {'sandbox_unavailable','model_unavailable','model_loading','model_timeout'} else 'CANCELLED' if result.get('agent_state')=='CANCELLED' else 'FAIL',
  'repair_count':metrics.get('repairs',0),'rollback_count':trace.rollbacks,'tool_calls':metrics.get('tool_calls',supervisor.counts['tool_calls']),
  'model_calls':len(model.records),'model_switches':0,'latency_seconds':time.monotonic()-start,
  'peak_vram_mb':resources['gpu_peak_used_mib'],'vram_scope':'whole GPU including display; process allocation unavailable',
  'peak_ram_mb':resources['worker_peak_rss_bytes']/2**20 if resources['worker_peak_rss_bytes'] is not None else None,
  'generation_tokens':sum(r['generation_tokens'] for r in model.records) if all(r.get('generation_tokens') is not None for r in model.records) else None,'token_usage_complete':all(r.get('generation_tokens') is not None for r in model.records),
  'properties':properties,'failure_category':None if validated else failure(result,error,trace),'failure_detail':str(error or result.get('error') or ''),
  'router_proposal':observed.to_dict(),'execution_result':result.get('validation_exit_code'),'validation_result':bool(validated),'evidence':str(attempt.relative_to(ROOT)),
  'initial_request_hash':digest(model.records[0]['request']) if model.records else None,'canonical_unchanged_before_accept':unchanged,'sandbox_image_id':oracle.image_id}
 save(completed,row);print(stage,runner,model_name,task['task_id'],row['status'],round(row['latency_seconds'],1),flush=True)
 return row
def project_results(status='RUNNING'):
 rows=[]
 for name in ('native','nanobot','hermes','models'):
  for file in (OUT/name).rglob('row.json'):
   row=json.loads(file.read_text());adjudication=file.parent/'environment-adjudication.json'
   if adjudication.exists() and row.get('model_calls')==0 and row.get('failure_category')=='SANDBOX':row={**row,'original_record_status':row['status'],'status':'BLOCKED','adjudication':str(adjudication.relative_to(ROOT))}
   rows.append(row)
 rows.sort(key=lambda r:(r['phase'],r['model'],r['runner'],r['task_id']))
 save(OUT/'results.json',{'status':status,'records':rows,'production_migrated':False})
 fields=['phase','task_id','category','control','runner','model','status','accepted','validated','repair_count','rollback_count','tool_calls','model_calls','model_switches','latency_seconds','generation_tokens','peak_vram_mb','peak_ram_mb','failure_category','evidence']
 with (OUT/'summary.csv').open('w',newline='',encoding='utf-8') as f:
  writer=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');writer.writeheader();writer.writerows(rows)
 return rows
def model_definitions():
 defaults=default_specs();qwen=defaults['text'];coder=defaults['code']
 # Existing registry implementation, one ephemeral experiment configuration.
 return {'qwen35':qwen,'coder25':replace(coder,capability='text',alias='sovereign-text',capabilities=('text','code'),worker_roles=('reasoning',)),
  'granite42':replace(qwen,model_file='Granite-4.2-3B/granite-4.2-3b-Q4_K_M.gguf',model_id='ibm-granite/granite-4.2-3b',display_name='Granite 4.2 3B',provider_repository='ibm-granite/granite-4.2-3b-GGUF',revision='c40945d71cd90f249a56985e8155551a9188dc30',license_id='Apache-2.0',license_source='https://huggingface.co/ibm-granite/granite-4.2-3b-GGUF'),
  'mini17':replace(qwen,model_file='mini-coder-1.7B/mini-coder-1.7b-iq4_nl-imat.gguf',model_id='ricdomolm/mini-coder-1.7b',display_name='mini-coder 1.7B IQ4_NL',provider_repository='sizzlebop/mini-coder-1.7b-IQ4_NL-GGUF',quantization='IQ4_NL',revision='59e704821fce313e7576ec8131d73106d5dbcb8a',license_id='MIT',license_source='https://huggingface.co/sizzlebop/mini-coder-1.7b-IQ4_NL-GGUF')}
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--phase',choices=['runners','models'],required=True);args=parser.parse_args()
 sources_unchanged();tasks=json.loads((OUT/'reports/tasks.json').read_text());definitions=model_definitions()
 if args.phase=='models':
  rows=project_results()
  runner_rows=[r for r in rows if r['phase']=='runners']
  if len(runner_rows)!=45 or any(r['status']=='BLOCKED' for r in runner_rows):raise RuntimeError('Runner comparison must finish with no unresolved environment blocks first')
  if not (OUT/'attendance-diagnostic/summary.json').exists():raise RuntimeError('Attendance diagnosis must finish before model comparison')
  if not (OUT/'reports/model-source-review.json').exists():raise RuntimeError('Verify existing model files and sources before model comparison')
 originals=default_specs();active=idle();original=current_identity() if active else None
 registry=ModelRegistry();broker=ModelBroker(registry);model_names=['qwen35'] if args.phase=='runners' else ['qwen35','coder25','mini17','granite42']
 save(OUT/'reports'/('runtime-before-'+args.phase+'.json'),{'runtime':original,'production_source_unchanged':True})
 try:
  for model_name in model_names:
   spec=definitions[model_name];registry.specs={'text':spec};idle()
   selection=broker.select('reasoning',required_context=16384,use_history=False);lease=broker.acquire(selection)
   identity=current_identity();save(OUT/'reports'/('lease-'+args.phase+'-'+model_name+'.json'),{'selection':selection.to_dict() if hasattr(selection,'to_dict') else selection.__dict__,'lease':lease,'identity':identity})
   if str((ROOT/'models'/spec.model_file).resolve()).casefold()!=identity['path'].casefold():raise RuntimeError('Fixed worker identity mismatch')
   schedule=[(arm,task) for task in tasks for arm in ARMS] if args.phase=='runners' else [('native_v1',task) for task in tasks]
   for arm,task in schedule:
    save(OUT/'progress.json',{'phase':args.phase,'runner':arm,'model':model_name,'task_id':task['task_id'],'status':'EXECUTING'})
    row=run_one(task,arm,model_name,identity,args.phase);project_results()
    if row['status']=='BLOCKED':raise RuntimeError('Environment block: stop the affected arm; evidence preserved')
   idle();start=time.monotonic();registry.kill_server();save(OUT/'reports'/('unload-'+args.phase+'-'+model_name+'.json'),{'seconds':time.monotonic()-start,'remaining_heavy_workers':[p.pid for p in servers()]})
  project_results('RUNNER_STAGE_COMPLETE' if args.phase=='runners' else 'MODEL_STAGE_COMPLETE');save(OUT/'progress.json',{'phase':args.phase,'status':'COMPLETE'})
 finally:
  # Never interrupt another task to restore residency.
  try:
   idle();registry.specs=originals
   if original:
    key=next((k for k,s in originals.items() if str((ROOT/'models'/s.model_file).resolve()).casefold()==original['path'].casefold()),None)
    if key:registry.acquire_lease(key)
  except Exception as exc:save(OUT/'reports'/('restore-note-'+args.phase+'.json'),{'error':str(exc),'no_active_task_interrupted':True})
if __name__=='__main__':
 from experiments.fidelity_v1.run_status import EvaluatorHeartbeat
 import sys
 # Passive liveness only. Does not alter models, fixtures, budgets or outcomes.
 phase=sys.argv[sys.argv.index('--phase')+1] if '--phase' in sys.argv else 'unknown'
 with EvaluatorHeartbeat(OUT,phase):main()
