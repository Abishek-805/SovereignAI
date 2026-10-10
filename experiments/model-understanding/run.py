"""Read-only worker comparison using existing plans, baseline retrieval and tools."""
import csv,hashlib,json,os,subprocess,sys,time
from dataclasses import asdict,replace
from pathlib import Path
import httpx,psutil
from backend.model import LocalModel
from backend.contracts import Chunk,Page
from rag.answer import answer,_query_presentation
from rag.calculator import evaluate_expression
from rag.embedding import Embedder
from rag.ingest import chunk_pages,extract
from rag.retrieve import retrieve,document_scope_for_question
from rag.store import Store
from rag.tables import load_tables,literal_entity_coverage,compile_outcome_query,bind_selection_request,execute_query
from router.model_registry import ModelRegistry,default_specs
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
def load(p):return json.loads(p.read_text(encoding='utf-8'))
def save(p,v):
 tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(v,indent=2,ensure_ascii=False)+'\n',encoding='utf-8');tmp.replace(p)
def digest(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for block in iter(lambda:f.read(2**20),b''):h.update(block)
 return h.hexdigest()
def servers():return [p for p in psutil.process_iter(['name','cmdline']) if (p.info['name'] or '').lower()=='llama-server.exe']
def resource(pid=None):
 result={'system_available_ram':psutil.virtual_memory().available,'rss':psutil.Process(pid).memory_info().rss if pid else None}
 try:result['gpu']=subprocess.check_output(['nvidia-smi','--query-gpu=name,memory.used,memory.total','--format=csv,noheader,nounits'],text=True,timeout=4).strip()
 except Exception as e:result['gpu_error']=str(e)
 return result
class ObservedModel(LocalModel):
 def __init__(self):
  super().__init__(verify_semantics=False);self.events=[];self.client.timeout=httpx.Timeout(120,connect=5)
 def _request(self,method,path,**kwargs):
  start=time.perf_counter();result=super()._request(method,path,**kwargs)
  if method=='POST' and path=='/v1/chat/completions':
   payload=kwargs.get('json',{});choices=result.get('choices',[])
   # Public structured outputs only; deliberately omit private reasoning fields.
   self.events.append({'seconds':time.perf_counter()-start,'max_tokens':payload.get('max_tokens'),
    'schema':payload.get('response_format'),'prompt_sha256':hashlib.sha256(json.dumps(payload.get('messages'),sort_keys=True,ensure_ascii=False).encode()).hexdigest(),
    'public_choices':[{'content':c.get('message',{}).get('content'),'finish_reason':c.get('finish_reason')} for c in choices],
    'usage':result.get('usage'),'timings':result.get('timings')})
  return result
def prepare():
 old=ROOT/'evidence/rag-fast-comparison/20261009'
 chunks=[Chunk(**c) for c in load(old/'chunks.json')]
 encoder=Embedder(ROOT/'models/bge-small-en-v1.5');store=Store(OUT/'index.sqlite')
 # Reuse frozen existing vectors rather than re-embed the original corpus.
 source=Store(ROOT/'evidence/rag-v2-comparison/20261009/CURRENT_BASELINE/baseline.sqlite')
 frozen=source.active_chunks();assert {c.chunk_id for c,v in frozen}=={c.chunk_id for c in chunks}
 import numpy as np
 for doc in sorted({c.document_id for c in chunks}):
  selected=[(c,v) for c,v in frozen if c.document_id==doc];c=selected[0][0]
  store.publish(doc,c.display_name,'frozen',c.version_hash,[c for c,v in selected],np.asarray([v for c,v in selected]),encoder.revision,[])
 for name,text in [('policy-current','Policy revision 2026-10-09. P-909 inspection interval is 12 days. This revision supersedes policy-old revision 2026-01-01.'),('policy-old','Policy revision 2026-01-01. P-909 inspection interval is 30 days. Superseded by policy-current revision 2026-10-09.')]:
  p=OUT/(name+'.txt');p.write_text(text,encoding='utf-8');h=digest(p)
  cs=chunk_pages(extract(p),encoder.tokenizer,name,p.name,384,48);store.publish(name,p.name,str(p),h,cs,encoder.encode([c.text for c in cs]),encoder.revision,[])
 p=OUT/'students.csv';h=digest(p)
 cs=chunk_pages(extract(p),encoder.tokenizer,'students',p.name,384,48)
 vectors=encoder.encode([c.text for c in cs])
 for i,c in enumerate(cs):
  if c.retrieval_kind=='lexical':vectors[i]=0
 store.publish('students',p.name,str(p),h,cs,vectors,encoder.revision,[])
 return store,encoder,load_tables(p)[0]
def table_catalog(table,question,history):
 return [{'id':'T1','document':'students.csv','sheet':table['name'],'title_rows':table['rows'][:table['header_row']],
  'columns':table['columns'],'row_count':len(table['records']),'sample':table['records'][:2],
  'literal_entity_coverage':literal_entity_coverage(table,question),'history_entity_coverage':literal_entity_coverage(table,'\n'.join(history)),
  'categorical_values':{c:sorted({str(r[c]) for r in table['records'] if isinstance(r[c],str)}) for c in table['columns']}}]
def measured_case(case,model,store,encoder,table,pid):
 start=time.perf_counter();t={'T0':0};row={'id':case['id'],'category':case['category'],'request':case['question'],'oracle':case['oracle'],'history':case['history'],'status':'RUNNING'}
 model.events=[];tools=[];row['resources_before']=resource(pid)
 try:
  t['T1']=time.perf_counter()-start
  docs=[d for d in store.planning_context(case['scope'],case['question'],total_chars=6000)] if case['scope'] else []
  plan=model.plan_task(case['question'],docs,[],case['history']);row['task_plan']=plan;t['T2']=time.perf_counter()-start
  action=plan['action'];t['T3']=time.perf_counter()-start
  passages=retrieve(store,encoder,case['question'],case['scope'],limit=6) if action=='search_documents' else []
  row['retrieval_calls']=int(action=='search_documents');t['T4']=time.perf_counter()-start
  row['retrieval_plan']={'required':action=='search_documents','document_scope_mode':plan['document_scope'],
   'model_selected_document_ids':None,'software_scope':document_scope_for_question(store.documents(),case['question'],case['scope']) if action=='search_documents' else [],
   'query':case['question'],'version_constraint_model_field':None,'schema_inspection':action=='search_documents' and 'students' in case['scope']}
  query=None
  if action=='search_documents' and 'students' in case['scope']:
   catalog=table_catalog(table,case['question'],case['history']);row['catalog']=catalog
   query=model.plan_table_query(case['question'],catalog,case['history']);row['raw_table_plan']=query
   if query.get('_measure'):
    query=compile_outcome_query(query['_measure'],{'T1':({'document_id':'students','display_name':'students.csv'},table)},case['question'],case['history'])
   if query.get('operation')!='none':query=bind_selection_request(query,table,case['question'])
  row['table_plan']=query;t['T5']=time.perf_counter()-start
  if action=='calculate':
   value=asdict(evaluate_expression(plan['expression']));tools.append({'tool':'calculator','input':plan['expression'],'result':value})
   text='Deterministic calculator observation: '+json.dumps(value)
   passages=[Chunk(hashlib.sha256(text.encode()).hexdigest(),'calculator','request-bound','Calculator result',text,None,None,None)]
  elif query and query.get('operation')!='none':
   if query.get('table')!='T1':raise ValueError('Unavailable table selected')
   value=execute_query(table,query);tools.append({'tool':'table_query','input':query,'result':value})
   original=next(c for c,v in store.active_chunks(['students']))
   structured=replace(original,query_result=value,text='Verified read-only table query over complete source.\n'+json.dumps(value))
   row['deterministic_production_presentation']=_query_presentation([{**structured.to_dict(),'label':'S1'}])
   # Diagnostic prose uses the same evidence prompt, rather than scoring the software formatter as model performance.
   passages=[replace(structured,query_result=None)]
  t['T6']=time.perf_counter()-start;row['evidence']=[p.to_dict() for p in passages]
  t['T7']=time.perf_counter()-start
  if action in {'calculate','search_documents'}:
   final=answer(case['question'],passages,model,context=16384,output_tokens=4096,safety_tokens=64,history=case['history'],max_repairs=1)
  else:final={'status':'answered','answer':plan.get('response',''),'sources':[]}
  row['final']=final;row['status']='COMPLETED'
 except Exception as e:
  row.update(status='ERROR',error={'type':type(e).__name__,'code':getattr(e,'code',None),'message':str(e)})
 finally:
  t['T8']=time.perf_counter()-start;row['timestamps_seconds']=t;row['model_events']=model.events;row['tool_observations']=tools
  row['model_calls']=len(model.events);row['tool_calls']=len(tools);row['model_switches']=0;row['retries']=0
  row['latency']={name:t[b]-t[a] if a in t and b in t else None for name,a,b in [('pre_retrieval','T0','T3'),('retrieval','T3','T4'),('tool_planning','T4','T5'),('tool_execution','T5','T6'),('final_generation','T7','T8'),('total','T0','T8')]}
  row['resources_after']=resource(pid)
 return row
def main():
 suite=load(OUT/'suite.json');assert digest(OUT/'suite.json')==load(OUT/'preregistration.json')['suite_sha256']
 assert not (OUT/'qwen-results.json').exists(),'Do not overwrite existing trajectories'
 qwen=default_specs()['text'];assert qwen.model_file=='Qwen3.5-4B-Q4_K_M.gguf'
 granite=replace(qwen,model_file='Granite-4.2-3B/granite-4.2-3b-Q4_K_M.gguf',model_id='ibm-granite/granite-4.2-3b',display_name='Granite 4.2 3B',provider_repository='ibm-granite/granite-4.2-3b-GGUF',revision='c40945d71cd90f249a56985e8155551a9188dc30',license_source='https://huggingface.co/ibm-granite/granite-4.2-3b-GGUF')
 identities=[]
 expected=['00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4','e0406663965846ae22a403456eb826ccce5f450840491f71952f18a7cb78e7d5']
 for spec,h in zip([qwen,granite],expected):
  actual=digest(ROOT/'models'/spec.model_file);assert actual==h,'Model hash mismatch'
  identities.append({**asdict(spec),'sha256':actual,'runtime':'llama.cpp b11132','runtime_sha256':digest(ROOT/'runtime/llama-b11132/llama-server.exe')})
 save(OUT/'model-identities.json',identities)
 store,encoder,table=prepare();original=servers();assert len(original)<=1
 original_command=original[0].info['cmdline'] if original else None
 if original:
  slots=httpx.get('http://127.0.0.1:8087/slots',timeout=30).json();assert not any(s.get('is_processing') for s in slots),'Existing model is busy'
  assert ModelRegistry()._owns_server(),'Cannot unload unowned model'
 runtime=[];process=None;loghandles=[]
 try:
  for name,spec in [('qwen',qwen),('granite',granite)]:
   started=time.perf_counter();entry={'arm':name,'baseline_resources':resource()};runtime.append(entry)
   if name=='qwen' and original:
    process=original[0];entry['load_seconds']=None;entry['load_note']='Existing warm approved runtime reused'
   else:
    assert not servers(),'Multiple heavy workers prohibited'
    logs=[(OUT/(name+'-'+suffix+'.log')).open('w',encoding='utf-8') for suffix in ['stdout','stderr']];loghandles.extend(logs)
    args=ModelRegistry(specs={'text':spec}).launch_args('text');process=subprocess.Popen(args,cwd=ROOT,stdout=logs[0],stderr=logs[1],creationflags=subprocess.CREATE_NO_WINDOW)
    for _ in range(240):
     if process.poll() is not None:raise RuntimeError('Model startup exited')
     try:
      if httpx.get('http://127.0.0.1:8087/health',timeout=2).status_code==200:break
     except httpx.HTTPError:pass
     time.sleep(.5)
    else:raise TimeoutError('Model load timeout')
    entry['load_seconds']=time.perf_counter()-started
   pid=process.pid;props=httpx.get('http://127.0.0.1:8087/props',timeout=30).json()
   assert Path(props['model_path']).resolve()==(ROOT/'models'/spec.model_file).resolve()
   assert props['default_generation_settings']['n_ctx']==16384
   entry.update(pid=pid,props=props,loaded_resources=resource(pid));save(OUT/'runtime.json',runtime)
   model=ObservedModel();rows=[];timeouts=0
   for case in suite['cases']:
    row=measured_case(case,model,store,encoder,table,pid);rows.append(row);save(OUT/(name+'-results.json'),rows)
    print(name,len(rows),'/30',case['id'],row['status'],round(row['latency']['total'],2),'seconds',flush=True)
    timeouts=timeouts+1 if row.get('error',{}).get('type') in {'ReadTimeout','TimeoutError'} else 0
    if timeouts>=2:entry['stop_reason']='Repeated model timeout';break
   model.close();unload=time.perf_counter();process.terminate()
   if isinstance(process,psutil.Process):process.wait(timeout=20)
   else:process.wait(timeout=20)
   entry.update(unload_seconds=time.perf_counter()-unload,after_unload=resource(),remaining_servers=[p.pid for p in servers()]);assert not servers()
   process=None;save(OUT/'runtime.json',runtime)
 except Exception as e:
  save(OUT/'environment-blocker.json',{'type':type(e).__name__,'message':str(e),'status':'GRANITE_BLOCKED' if runtime and runtime[-1]['arm']=='granite' else 'BENCHMARK_BLOCKED'})
  raise
 finally:
  if process:
   try:process.terminate();process.wait(timeout=20)
   except psutil.NoSuchProcess:pass
  if original_command and not servers():
   logs=[(OUT/('restored-qwen-'+s+'.log')).open('w',encoding='utf-8') for s in ['stdout','stderr']];loghandles.extend(logs)
   restored=subprocess.Popen(original_command,cwd=ROOT,stdout=logs[0],stderr=logs[1],creationflags=subprocess.CREATE_NO_WINDOW)
   (ROOT/'benchmarks/server.pid').write_text(str(restored.pid))
   for _ in range(240):
    try:
     if httpx.get('http://127.0.0.1:8087/health',timeout=2).status_code==200:break
    except httpx.HTTPError:pass
    time.sleep(.5)
   save(OUT/'restoration.json',{'pid':restored.pid,'original_command':original_command,'seconds_since_launch':None,'health':httpx.get('http://127.0.0.1:8087/health',timeout=30).json(),'resources':resource(restored.pid)})
  for h in loghandles:h.close()
if __name__=='__main__':main()
