"""Isolated policy wrappers around the frozen native loop, never production imports."""
import ast,copy,hashlib,importlib.util,json,re,time
import httpx
from contextlib import contextmanager
from pathlib import Path
from backend.contracts import WorkbenchError
from backend.model import LocalModel
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'evidence/code-agent-fidelity-v1'
def encoded(value):return json.dumps(value,sort_keys=True,ensure_ascii=False)
def digest(value):return hashlib.sha256(encoded(value).encode()).hexdigest()
def load_native():
 path=OUT/'native/snapshot/agent_kernel.py'
 expected=json.loads((OUT/'reports/baseline-manifest.json').read_text())['source_sha256']['workflows/agent_kernel.py']
 if hashlib.sha256(path.read_bytes()).hexdigest()!=expected:raise RuntimeError('Frozen baseline changed')
 spec=importlib.util.spec_from_file_location('isolated_native_'+str(time.time_ns()),path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
 return module
def property_results(validation):
 text=validation.get('stderr','');result={}
 for method,owner,status in re.findall(r'^(test_\w+)\s+\(([^)]+)\)\s+\.\.\.\s+(ok|FAIL|ERROR)$',text,re.M):result[owner+'.'+method]=status=='ok'
 return result
class WireStream(httpx.SyncByteStream):
 def __init__(self,stream,path):self.stream=stream;self.path=path
 def __iter__(self):
  with self.path.open('wb') as file:
   for chunk in self.stream:file.write(chunk);file.flush();yield chunk
 def close(self):self.stream.close()
class WireTransport(httpx.BaseTransport):
 """Passive exact HTTP body capture; does not parse or change tool responses."""
 def __init__(self,directory):self.transport=httpx.HTTPTransport();self.directory=directory;self.calls=0
 def handle_request(self,request):
  response=self.transport.handle_request(request)
  if request.url.path=='/v1/chat/completions':
   self.calls+=1
   return httpx.Response(response.status_code,headers=response.headers,stream=WireStream(response.stream,self.directory/('call-'+str(self.calls).zfill(3)+'.wire-body')),extensions=response.extensions)
  return response
 def close(self):self.transport.close()
class EvidenceModel(LocalModel):
 def __init__(self,directory,runner,task_id,wire_capture=False,**kwargs):
  if wire_capture:kwargs['transport']=WireTransport(directory)
  super().__init__(**kwargs);self.directory=directory;self.runner=runner;self.task_id=task_id;self.records=[];self.workspace=None;self.session=None;self.after_response=None
 def _request_raw(self,method,path,**kwargs):
  if method!='POST' or path!='/v1/chat/completions':return super()._request_raw(method,path,**kwargs)
  payload=copy.deepcopy(kwargs['json']);payload.update(stream=True,stream_options={'include_usage':True})
  messages=payload['messages'];workspace=self.workspace
  files=[]
  for name,data in sorted(workspace.files().items()) if workspace else []:
   symbols=[]
   if name.endswith('.py'):
    try:symbols=[{'name':n.name,'arguments':[a.arg for a in n.args.args]} for n in ast.walk(ast.parse(data.decode())) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))]
    except (UnicodeError,SyntaxError):pass
   files.append({'path':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'symbols':symbols})
  previous=next((m for m in reversed(messages) if m['role']=='tool'),None)
  record={'call':len(self.records)+1,'task_id':self.task_id,'agent_task_id':getattr(self.session,'task_id',None),'runner':self.runner,'model':payload['model'],'request':payload,
   'system_instructions_hash':digest([m for m in messages if m['role']=='system']),'task_prompt_hash':digest(messages[1]),
   'files_available':files,'files_supplied':[json.loads(m['content']).get('path') for m in messages if m['role']=='tool' and isinstance(m.get('content'),str) and m['content'].startswith('{')],
   'output_limit':payload['max_tokens'],'tool_definitions_hash':digest(payload['tools']),'previous_observation':previous,
   'repair_number':getattr(self.session,'repairs',0),'started_at':time.time()}
  self.records.append(record);start=time.monotonic();self._save(record)
  try:
   result=super()._request_raw(method,path,**kwargs);record['response']=copy.deepcopy(result)
   record['context_size']=result.get('usage',{}).get('prompt_tokens')
   record['generation_tokens']=result.get('usage',{}).get('completion_tokens')
   return result
  except Exception as exc:record['transport_error']={'code':getattr(exc,'code',None),'message':str(exc)};raise
  finally:record['latency_seconds']=time.monotonic()-start;self._save(record)
 def agent_tool_turn(self,*args,**kwargs):
  try:
   result=super().agent_tool_turn(*args,**kwargs)
   if self.after_response:self.after_response(result)
   return result
  except Exception as exc:
   if self.records:self.records[-1]['adapter_error']={'code':getattr(exc,'code',None),'message':str(exc)};self._save(self.records[-1])
   raise
 def _save(self,record):
  path=self.directory/('call-'+str(record['call']).zfill(3)+'.json')
  temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(record,indent=2,ensure_ascii=False),encoding='utf-8');temporary.replace(path)
class Trace:
 def __init__(self,directory,initial_properties=None):
  self.directory=directory;self.events=[];self.repairs=[];self.best_properties={k for k,v in (initial_properties or {}).items() if v};self.best_overlay={};self.last_overlay={};self.last_validation_revision=None;self.failed_validations=0;self.rollbacks=0
 def save(self,name,value):
  path=self.directory/(name+'.json');path.write_text(json.dumps(value,indent=2,ensure_ascii=False),encoding='utf-8')
def configure(module,runner,trace):
 """New module namespace per execution; no monkeypatch of production module."""
 BaseAdapter=module.ModelAdapter;BaseExecutor=module.ToolExecutor;BaseValidator=module.ValidationEngine
 class Adapter(BaseAdapter):
  def __init__(self,*args,**kwargs):super().__init__(*args,**kwargs);self.consecutive_format_errors=0;self.pending_error=None
  def fit(self,messages,schemas,workspace,validation):
   self.model.workspace=workspace
   self.model.session=getattr(trace,'session',None)
   if self.pending_error:
    messages=[*messages,{'role':'user','content':encoded({'provider_tool_error':self.pending_error,'partial_tool_executed':False})}];self.pending_error=None
   fitted=super().fit(messages,schemas,workspace,validation)
   trace.events.append({'event':'context_fit','before_hash':digest(messages),'after_hash':digest(fitted),'compacted':digest(messages)!=digest(fitted),'original_request_retained':messages[1]==fitted[1]})
   return fitted
  def turn(self,messages,schemas):
   try:message=super().turn(messages,schemas);self.consecutive_format_errors=0;return message
   except WorkbenchError as exc:
    if runner!='hermes_minimal' or exc.code!='generation_format':raise
    self.consecutive_format_errors+=1
    trace.events.append({'event':'format_error','code':exc.code,'message':str(exc),'consecutive':self.consecutive_format_errors})
    if self.consecutive_format_errors>=2:raise
    self.pending_error={'code':exc.code,'message':str(exc)}
    return {'role':'assistant','content':'','tool_calls':[]}
 class Validator(BaseValidator):
  def __init__(self,workspace,sandbox,session):
   super().__init__(workspace,sandbox,session);trace.session=session
  def validate(self):
   result=super().validate();properties=property_results(result);current=dict(self.workspace.overlay)
   revision=self.workspace.digest(self.workspace.files());passed={k for k,v in properties.items() if v}
   lost=sorted(trace.best_properties-passed) if properties else []
   attempt={'attempt':len(trace.repairs)+1,'revision':revision,'failure':result,'properties':properties,'lost_properties':lost,
    'candidate_diff':self.workspace.diff(),'previous_revision':trace.last_validation_revision,'validation_delta':len(passed)-len(trace.best_properties),'rolled_back':False}
   changed=revision!=trace.last_validation_revision
   if runner!='native_v1' and lost and changed:
    self.workspace.overlay=dict(trace.best_overlay);trace.rollbacks+=1;attempt['rolled_back']=True
    result={**result,'rolled_back':True,'lost_previously_passing_properties':lost,'workspace_revision_after_rollback':self.workspace.digest(self.workspace.files())}
   elif properties and passed>=trace.best_properties:
    trace.best_properties=passed;trace.best_overlay=current
   trace.last_overlay=current;trace.last_validation_revision=revision
   trace.repairs.append(attempt);trace.save('validation-'+str(len(trace.repairs)).zfill(3),attempt)
   if not result.get('passed'):trace.failed_validations+=1
   if runner!='native_v1' and trace.failed_validations>=3 and not result.get('passed'):
    raise WorkbenchError('repair_budget','Experimental bounded repair ceiling: three unsuccessful validations; candidate evidence retained')
   return result
 class Executor(BaseExecutor):
  def execute(self,name,args):
   event={'event':'tool','tool':name,'arguments':copy.deepcopy(args),'before_revision':self.workspace.digest(self.workspace.files()),'before_diff':self.workspace.diff()}
   if runner!='native_v1':trace.save('pending-'+str(len(trace.events)).zfill(4),event)
   start=time.monotonic()
   try:
    result=super().execute(name,args);event.update(result=copy.deepcopy(result),latency_seconds=time.monotonic()-start,after_revision=self.workspace.digest(self.workspace.files()),after_diff=self.workspace.diff());return result
   except Exception as exc:event['error']={'code':getattr(exc,'code',None),'message':str(exc)};raise
   finally:
    trace.events.append(event);trace.save('event-'+str(len(trace.events)).zfill(4),event)
 module.ModelAdapter=Adapter;module.ValidationEngine=Validator;module.ToolExecutor=Executor
 return module.AgentLoop()
