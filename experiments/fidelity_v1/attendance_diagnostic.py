"""Diagnose saved attendance candidates; no new attendance LLM retry."""
import ast,hashlib,json,re
from pathlib import Path
from experiments.fidelity_v1.tasks import ROOT,OUT
from experiments.kernel_docker import DockerCommands
from experiments.fidelity_v1.evaluate import save
PROBE='''import importlib.util,json,re
from pathlib import Path
checks=[]
def add(name,passed,detail=''):
 checks.append({'property':name,'passed':bool(passed),'detail':str(detail)[:1500]})
try:
 source=next(p for p in Path('.').rglob('*.py') if not p.name.startswith('test_') and 'Flask(' in p.read_text())
 spec=importlib.util.spec_from_file_location('candidate_app',source);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
 app=getattr(m,'app',None)
 if app is None and hasattr(m,'create_app'):app=m.create_app()
 client=app.test_client();routes=list(app.url_map.iter_rules());add('runnable_flask',True)
 students=next(r.rule for r in routes if 'POST' in r.methods and 'student' in r.rule and not r.arguments)
 attendance=next(r.rule for r in routes if 'POST' in r.methods and 'attendance' in r.rule)
 created=client.post(students,json={'id':734,'name':'Independent diagnostic student'})
 data=created.get_json(silent=True);add('student_creation_json',200<=created.status_code<300 and isinstance(data,dict),str((created.status_code,data)))
 identity=data.get('id',data.get('student',{}).get('id')) if isinstance(data,dict) else None
 listed=client.get(students);add('student_stored',listed.status_code==200 and listed.is_json and 'Independent diagnostic student' in listed.get_data(as_text=True))
 if identity is None:
  collection=listed.get_json(silent=True)
  if isinstance(collection,dict):collection=collection.get('students',[])
  if isinstance(collection,list):identity=next((s.get('id') for s in collection if s.get('name')=='Independent diagnostic student'),None)
 target=re.sub(r'<(?:[^:>]+:)?([^>]+)>',lambda match:str(identity),attendance)
 body={'student_id':identity,'date':'2026-10-06','status':'present'}
 valid=client.post(target,json=body);add('valid_attendance_json',identity is not None and 200<=valid.status_code<300 and valid.is_json,str((target,valid.status_code,valid.get_data(as_text=True)[:500])))
 for label,b in [('missing_fields',{}),('invalid_status',{**body,'status':'not-a-valid-status'}),('invalid_date',{**body,'date':'not-a-date'})]:
  response=client.post(target,json=b);add(label,400<=response.status_code<500 and response.is_json,str((response.status_code,response.get_data(as_text=True)[:500])))
 malformed=client.post(target,data='{broken',content_type='application/json');add('malformed_json_rejected_as_json',400<=malformed.status_code<500 and malformed.is_json,str((malformed.status_code,malformed.get_data(as_text=True)[:500])))
 unknown=re.sub(r'<(?:[^:>]+:)?([^>]+)>','999999',attendance)
 response=client.post(unknown,json={**body,'student_id':999999});add('unknown_student_rejected',400<=response.status_code<500 and response.is_json,str((response.status_code,response.get_data(as_text=True)[:500])))
except Exception as exc:add('diagnostic_execution',False,type(exc).__name__+': '+str(exc))
add('readme_present',any(p.name.lower().startswith('readme') for p in Path('.').rglob('*') if p.is_file()))
add('requested_test_present',any(Path('.').rglob('test_*.py')))
print('ATTENDANCE_DIAGNOSTIC='+json.dumps(checks))
'''
WRAPPER='''import os,shutil,subprocess,sys
from pathlib import Path
root=Path('/output/project');shutil.copytree('/input',root,ignore=lambda source,names:{'program.py'} if Path(source)==Path('/input') else set());os.chdir(root)
result=subprocess.run([sys.executable,'-c',PROBE],capture_output=True,text=True,timeout=25)
print(result.stdout,end='');print(result.stderr,end='',file=sys.stderr);sys.exit(result.returncode)
'''.replace('PROBE',repr(PROBE))
def inventory(files):
 result={}
 for path,source in files.items():
  if not path.endswith('.py'):continue
  try:tree=ast.parse(source)
  except SyntaxError as exc:result[path]={'parse_error':str(exc)};continue
  functions=[];routes=[]
  for node in ast.walk(tree):
   if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):
    functions.append({'name':node.name,'args':[a.arg for a in node.args.args]})
    for decorator in node.decorator_list:
     if isinstance(decorator,ast.Call) and isinstance(decorator.func,ast.Attribute) and decorator.func.attr in {'route','get','post'} and decorator.args and isinstance(decorator.args[0],ast.Constant):routes.append({'path':decorator.args[0].value,'method_decorator':decorator.func.attr,'function':node.name})
  result[path]={'functions':functions,'routes':routes,'sha256':hashlib.sha256(source.encode()).hexdigest()}
 return result
def main():
 rows=json.loads((OUT/'results.json').read_text())['records'];valid_runner=[r for r in rows if r['phase']=='runners']
 if len(valid_runner)!=45 or any(r['status']=='BLOCKED' for r in valid_runner):raise RuntimeError('Complete controlled runner stage before attendance diagnosis')
 old=ROOT/'outputs/agent-kernel-rebuild';selected=[]
 for directory in sorted(old.glob('browser-*')):
  path=directory/'terminal-task.json'
  if path.exists():
   result=json.loads(path.read_text())
   if result.get('instruction','').startswith('Create a small Flask attendance application.') and result.get('events'):selected.append((path,result))
 selected=selected[-3:];all_rows=[]
 sandbox=DockerCommands(ROOT,OUT/'attendance-diagnostic/sandbox').sandbox;sandbox._ready()
 save(OUT/'attendance-diagnostic/requirements.json',{'request':'Create a small Flask attendance application. Store students, provide POST attendance, reject invalid requests, return JSON, README, runnable app and simple test.','interpretation':'Assess JSON on success and invalid-input responses. Storage persistence across restarts was not explicitly requested and is not imposed.','new_model_calls':0,'previous_unlogged_handoff_context':'Unavailable; no guess that handoff caused failure.'})
 for path,result in selected:
  directory=OUT/'attendance-diagnostic'/result['task_id'];directory.mkdir(parents=True,exist_ok=True)
  save(directory/'source-reference.json',{'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'original_state':result.get('state'),'original_metrics':result.get('metrics'),'original_error':result.get('error')})
  files={};before_properties=set();prior_inventory={};seen=set();stage=0
  for index,event in enumerate(result['events']):
   name=event['tool'];args=event.get('arguments') or {};observation=event.get('result') or {}
   if observation.get('error'):continue
   target=args.get('path','').removeprefix('/output/project/').removeprefix('./')
   if name=='write_file' and isinstance(args.get('content'),str):files[target]=args['content']
   elif name=='apply_patch' and target in files and files[target].count(args.get('old_text',''))==1:files[target]=files[target].replace(args['old_text'],args['new_text'],1)
   elif name=='delete_file':files.pop(target,None)
   else:continue
   if not any(p.endswith('.py') and not Path(p).name.startswith('test_') and 'Flask(' in s for p,s in files.items()):continue
   revision=hashlib.sha256(json.dumps(files,sort_keys=True).encode()).hexdigest()
   if revision in seen:continue
   seen.add(revision);stage+=1;stage_dir=directory/('candidate-'+str(stage).zfill(2));stage_dir.mkdir(exist_ok=True)
   evidence=stage_dir/'result.json'
   if evidence.exists():row=json.loads(evidence.read_text())
   else:
    raw=sandbox.execute(WRAPPER,timeout=30,input_files={p:s.encode() for p,s in files.items()})
    found=re.search(r'^ATTENDANCE_DIAGNOSTIC=(.+)$',raw.stdout,re.M);checks=json.loads(found.group(1)) if found else []
    current=inventory(files);symbols={p:{f['name'] for f in d.get('functions',[])} for p,d in current.items()}
    old_symbols={p:{f['name'] for f in d.get('functions',[])} for p,d in prior_inventory.items()}
    passed={c['property'] for c in checks if c['passed']};lost=sorted(before_properties-passed)
    row={'task_id':result['task_id'],'stage':stage,'event_index':index,'operation':name,'path':target,'candidate_revision':revision,'inventory':current,'checks':checks,
     'passed_properties':sorted(passed),'lost_previously_passing_properties':lost,'removed_symbols':{p:sorted(names-symbols.get(p,set())) for p,names in old_symbols.items() if names-symbols.get(p,set())},
     'container_executed':raw.executed,'exit_code':raw.exit_code,'stdout':raw.stdout,'stderr':raw.stderr,
     'failure_category':'REPAIR' if lost and name=='apply_patch' else 'GENERATION' if any(not c['passed'] for c in checks) else None,
     'classification_basis':'Independently executed observable properties; no router or handoff blame inferred.'}
    save(stage_dir/'candidate-files.json',files);save(evidence,row)
   all_rows.append(row);before_properties=set(row['passed_properties']);prior_inventory=row['inventory']
  observations=[{'event':i,'tool':e['tool'],'result':e['result']} for i,e in enumerate(result['events']) if e['tool'] in {'run_tests','run_command','finish'}]
  save(directory/'original-execution-observations.json',observations)
  save(directory/'stage-map.json',{'A_requirement_interpretation':'Original request and generated README; private interpretation/exact prior system context was not logged.','B_interface_inventory':'AST symbols/routes plus executed request/response probes per candidate.','C_implementation':'Candidate files and revision hashes reconstructed from successful file actions.','D_test_execution':'Original exact tool observations; authored tests are supplemental.','E_repair':'Candidate transitions, property deltas and removed-symbol lists.','all_original_outcomes_preserved':True,'new_model_calls':0})
 save(OUT/'attendance-diagnostic/summary.json',{'trajectories':len(selected),'candidate_stages':len(all_rows),'rows':all_rows,'new_model_calls':0,'no_attendance_retry':True,'original_outcomes_unchanged':True})
 print('Attendance evidence diagnosis complete: '+str(len(selected))+' saved trajectories, '+str(len(all_rows))+' candidate stages',flush=True)
if __name__=='__main__':main()
