import sys,json,time,ast,subprocess,psutil
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from router.model_registry import ModelRegistry,ModelSpec
from router.telemetry import CURRENT_ROUTE,RoutingDecision
from backend.model import LocalModel
root=Path(__file__).resolve().parents[1]
specs={key:ModelSpec('text',key,file,context=16384,license_reference='docs/model-and-runtime-notices.md',license_id='Apache-2.0',license_reviewed=True) for key,file in [('baseline','Qwen3-4B-Instruct-2507-Q4_K_M.gguf'),('coder','qwen2.5-coder-3b-instruct-q4_k_m.gguf'),('qwen35','Qwen3.5-4B-Q4_K_M.gguf'),('gemma4','gemma-4-E2B-it-Q4_K_M.gguf')]}
reg=ModelRegistry(specs=specs);model=LocalModel();records=[]
for key in sys.argv[1:] or list(specs):
 if not (root/'models'/specs[key].model_file).is_file():continue
 entry={'model':key,'context':16384,'cases':[]};records.append(entry)
 try:
  entry['lease']=reg.acquire_lease(key)
  token=CURRENT_ROUTE.set(RoutingDecision(runtime_alias=key))
  for goal,expected in [('I have to do a project now but I do not have any idea in my mind','answer'),('Create a python file that detects faces using my laptop camera with OpenCV','edit_code'),('Can you explain this project?','inspect_code')]:
   start=time.perf_counter()
   try:
    plan=model.plan_task(goal,[],[{'name':'python_file.py','content':'# starter'}]);entry['cases'].append({'task':goal,'expected':expected,'actual':plan['action'],'pass':plan['action']==expected,'seconds':time.perf_counter()-start,'response':plan})
   except Exception as exc:entry['cases'].append({'task':goal,'pass':False,'error':str(exc),'seconds':time.perf_counter()-start})
  start=time.perf_counter()
  try:
   code=model.complete_code([{'role':'system','content':'Write complete working Python source. Return JSON with the code field. Do not use placeholders.'},{'role':'user','content':'Create a single Python file using OpenCV and camera 0 to detect faces live with a Haar cascade. Handle unavailable camera, check each frame, draw face rectangles, exit with q, and always release camera and destroy windows.'}],max_tokens=2048)['code'];ast.parse(code)
   entry['cases'].append({'task':'OpenCV generation syntax and required API contract','pass':all(x in code for x in ('VideoCapture','detectMultiScale','release','destroyAllWindows')),'seconds':time.perf_counter()-start,'code':code})
  except Exception as exc:entry['cases'].append({'task':'OpenCV generation','pass':False,'error':str(exc),'seconds':time.perf_counter()-start})
  start=time.perf_counter()
  try:
   tables=[{'id':'marks','document_title':'Professional Skills Training All Marks','sheet_name':'All','columns':['Member Id','Name','WAT 1','WAT 2','CAT 1'],'sample_values':[['24STU001','Learner A',24,16,36.5],['24STU051','Student',20,18,28]]}]
   query=model.plan_table_query('Compare the marks of 24stu001 and 24stu051 in all past tests',tables)
   ids=[f for f in query['filters'] if f['operator']=='in' and isinstance(f['value'],list)]
   passed=query['operation']=='select' and {'WAT 1','WAT 2','CAT 1'}<=set(query['columns']) and any({v.upper() for v in f['value']}=={'24STU001','24STU051'} for f in ids)
   entry['cases'].append({'task':'Multi-entity all-measurement table comparison','pass':passed,'seconds':time.perf_counter()-start,'response':query})
  except Exception as exc:entry['cases'].append({'task':'table comparison','pass':False,'seconds':time.perf_counter()-start,'error':str(exc)})
  entry['runtime_rss_mib']=round(psutil.Process(int((root/'benchmarks/server.pid').read_text())).memory_info().rss/1024**2,1)
  entry['gpu']=subprocess.check_output(['nvidia-smi','--query-gpu=memory.used,memory.free','--format=csv,noheader,nounits'],text=True).strip()
  CURRENT_ROUTE.reset(token)
 except Exception as exc:entry['error']=str(exc)
 (root/'benchmarks/model-comparison-local.json').write_text(json.dumps(records,indent=2))
 print(key,json.dumps({k:v for k,v in entry.items() if k!='cases'}),[(c['task'],c['pass'],round(c['seconds'],1)) for c in entry['cases']],flush=True)
reg.kill_server()
