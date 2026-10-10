"""Isolated, passive timing of existing Workbench plus single-variable RAG probes."""
import copy, hashlib, importlib.util, json, re, sqlite3, sys, time
from pathlib import Path
from datetime import datetime,timezone,timedelta
import httpx, numpy as np
from backend.model import LocalModel
from backend.settings import Settings
from rag.store import Store
from rag.embedding import Embedder
from rag.ingest import extract,chunk_pages
from rag.retrieve import retrieve
from router.model_registry import ModelRegistry
from experiments.fidelity_v1.run_status import inspect_status
from experiments.fidelity_v1.tasks import OUT
ROOT=Path(__file__).resolve().parents[2]
QUESTIONS=[('python','What Python version does the document require for installation?',r'3\.12'),('backend','Which port serves the backend interface according to the document?',r'8088'),('modelport','Which port does the local llama.cpp server listen on according to the document?',r'8087'),('embedding','Which embedding model does the document use for RAG?',r'bge.small.en.v1.5'),('projects','Where are live code project files stored by default according to the document?',r'Documents.*SovereignAI.*Projects')]
CURRENT=None
def save(path,value): path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value,indent=2,ensure_ascii=False,default=str),encoding='utf-8')
def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def event(name):
    if CURRENT is not None: CURRENT['events'].append({'name':name,'monotonic_ns':time.perf_counter_ns()})
def timed(name,fn,*args,**kw):
    start=time.perf_counter_ns();event(name+'_start')
    try:return fn(*args,**kw)
    finally:
        event(name+'_end')
        if CURRENT is not None:CURRENT['durations'].setdefault(name,[]).append((time.perf_counter_ns()-start)/1e9)
class Vector:
    def __init__(self,vector): self.vector=vector
    def __matmul__(self,other):return timed('vector_search',lambda:self.vector@other)
class TimedStore(Store):
    cached=False
    def active_chunks(self,ids=None):
        def get():
            version=tuple((d['document_id'],d['active_hash'],d['embedding_revision']) for d in self.documents())
            key=(version,tuple(ids) if ids is not None else None)
            if self.cached and key==getattr(self,'cache_key',None):
                if CURRENT is not None:CURRENT['cache_hit']=True
                return self.cache_value
            result=super(TimedStore,self).active_chunks(ids)
            values=[(c,Vector(v)) for c,v in result]
            if self.cached:self.cache_key=key;self.cache_value=values
            return values
        return timed('vector_store_loading',get)
    def lexical(self,*args,**kwargs):return timed('bm25',super().lexical,*args,**kwargs)
class TimedEmbedder:
    def __init__(self,path):self.path=path;self.delegate=None;self.revision=Embedder.revision
    def encode(self,texts,query=False):
        if self.delegate is None:self.delegate=timed('embedding_initialization',Embedder,self.path)
        if CURRENT is not None:CURRENT.setdefault('embedding_inputs',[]).append({'texts':texts,'query':query})
        return timed('embedding',self.delegate.encode,texts,query=query)
class CaptureStream(httpx.SyncByteStream):
    def __init__(self,stream,cell):self.stream=stream;self.cell=cell;self.buf=b'';self.first=None
    def __iter__(self):
        with (self.cell/'wire.body').open('wb') as f:
            for chunk in self.stream:
                now=time.perf_counter_ns();f.write(chunk);f.flush();self.buf+=chunk
                if self.first is None:
                    for line in self.buf.splitlines():
                        if line.startswith(b'data: '):
                            try:
                                item=json.loads(line[6:]);delta=item.get('choices',[{}])[0].get('delta',{})
                                if delta.get('content') or delta.get('reasoning_content') or delta.get('tool_calls'):self.first=now;event('first_token_time');break
                            except (ValueError,IndexError):pass
                yield chunk
    def close(self):self.stream.close()
class CaptureTransport(httpx.BaseTransport):
    def __init__(self):self.delegate=httpx.HTTPTransport();self.n=0
    def handle_request(self,request):
        is_model=request.url.path=='/v1/chat/completions'
        if is_model:
            self.n+=1; cell=CURRENT['directory']/'model-request-captures'/str(self.n).zfill(3);cell.mkdir(parents=True)
            (cell/'request.body').write_bytes(request.content);save(cell/'request.json',json.loads(request.content));save(cell/'request-headers.json',dict(request.headers));event('prompt_submit_start')
        response=self.delegate.handle_request(request)
        if is_model:
            event('prompt_submit_end');save(cell/'response-headers.json',dict(response.headers));return httpx.Response(response.status_code,headers=response.headers,stream=CaptureStream(response.stream,cell),extensions=response.extensions)
        return response
    def close(self):self.delegate.close()
class TimedModel(LocalModel):
    def _request_raw(self,method,path,**kwargs):
        if path!='/v1/chat/completions':return timed('context_build',super()._request_raw,method,path,**kwargs)
        start=time.perf_counter_ns()
        try:
            result=super()._request_raw(method,path,**kwargs)
            CURRENT.setdefault('model_responses',[]).append(result);event('generation_end');return result
        finally:CURRENT['durations'].setdefault('model_roundtrip',[]).append((time.perf_counter_ns()-start)/1e9)
def load_service():
    spec=importlib.util.spec_from_file_location('isolated_rag_service',ROOT/'backend/service.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    original=module.retrieve;module.TOP_K=6
    def instrumented(store,embedder,question,document_ids=None,**kwargs):
        passages=timed('retrieval',original,store,embedder,question,document_ids,limit=module.TOP_K)
        if CURRENT is not None:CURRENT.setdefault('retrievals',[]).append({'query':question,'ids':[c.chunk_id for c in passages],'chunks':[c.to_dict() for c in passages],'raw_characters':sum(len(c.text) for c in passages)})
        return passages
    module.retrieve=instrumented
    cls=module.Workbench
    class Instrumented(cls):
        def _lease(self,*args,**kwargs):return timed('model_lease',super()._lease,*args,**kwargs)
        def _request_plan(self,*args,**kwargs):return timed('router',super()._request_plan,*args,**kwargs)
    return module,Instrumented
def call(wb,out,identity,question,pattern=None,history=None,forced=True):
    global CURRENT
    cell=out/identity;cell.mkdir();row={'id':identity,'question':question,'history':history or [],'forced_documents':forced,'events':[],'durations':{},'directory':cell,'reranker':'not present in retrieve.py','switch':'not requested unless observed registry result'};CURRENT=row;event('request_received');start=time.perf_counter_ns()
    try:
        result=wb.ask(question,document_ids=['readme'],history=history,force_documents=forced);row['result']=result
        row['correct']=bool(re.search(pattern,result.get('answer',''),re.I)) if pattern else None
        if pattern:
            texts='\n'.join(s['text'] for s in result.get('sources',[]));row['evidence_present']=bool(re.search(pattern,texts,re.I));row['failure_category']=None if row['correct'] else 'MODEL_GENERATION_FAILURE' if row['evidence_present'] else 'RETRIEVAL_FAILURE'
    except Exception as error:row['error']=str(error);row['failure_category']='UNKNOWN'
    event('answer_returned');row['total_seconds']=(time.perf_counter_ns()-start)/1e9
    row['stage_seconds']={k:sum(v) for k,v in row['durations'].items()};row['model_calls']=len(row.get('model_responses',[]));row['directory']=str(cell.relative_to(ROOT));save(cell/'result.json',row);CURRENT=None
    print(identity,round(row['total_seconds'],3),row.get('correct'),row.get('error',''),flush=True);return row
def register():
    out=ROOT/'evidence/latency-rag-recovery'/datetime.now(timezone(timedelta(hours=5,minutes=30))).strftime('%Y%m%d-%H%M%S');out.mkdir(parents=True)
    (out/'README.md').write_bytes((ROOT/'README.md').read_bytes());save(out/'retrieval-queries.json',QUESTIONS)
    prereg='''# Latency/RAG recovery preregistration
Measure unchanged production Workbench request path in isolated module/workspace; no source edits. Fixed frozen corpus is byte-exact project README snapshot, authentic existing source, not fabricated passages. Offline extraction/chunk/embedding/publish initialization separate from query. Five fixed QA regex oracles grounded in source: Python3.12, backend8088, model8087, BGE-small-en-v1.5, default Documents/SovereignAI/Projects. Regex oracle is limited literal semantic check, no universal correctness claim. Raw prompts/results preserved, no answer repair by harness. Existing application bounded repairs/recovery retained and counted.
Baseline one application-cold ONNX query plus three warm same Python question; worker stays resident, not model-cold. Five QA baseline with first reused from warm sample. Experiment1 TOP_K6->5 only, same five questions. Experiment2 add active-chunk/version cache only to top5, same five queries. Cache invalidates on full document active_hash/embedding_revision list and requested scope; persisted FTS unchanged. No reranker exists. No extra controllers. Existing arithmetic branch tested on five required expressions through Workbench with selected docs, retrieval/model counters must zero. Also20%of450 and code/general route metadata checks. Followup sequence document Python prerequisite, bare version followup, why-version question: production ask without forced-doc bypass on followups, preserve exact source/history. Third reason answer must admit unsupported reason if README does not establish it. Mixed document port plus17+25 through existing ask, no second planner; both8088/42 expected, do not hand-correct.
Model existing registry-owned Qwen3.5-4B Q4_K_M b11132/context16384/KVq8_0q8_0/temp0/output4096/thinkingfalse. Model broker/lease policy preserved. One heavy model; wait idle before run. No tool/candidate code actions, no Stage1B/T10/Stage2. Passive wrappers instrument monotonic_ns request, router, embedding, FTS BM25, vector dot, active-store reload, lease, context tokenization, HTTP submit/first content token/end. Unavailable stages null/not-applicable, never zero invented. Server prompt_ms/predicted_ms recorded as separate actual runtime telemetry. SSE wire captured unchanged; first token measurable only streaming calls. Prompt audits inspect actual requests, not merely source. Warm p50/p95 linear percentile across3warm; sample small. No production promotion or arbitrary latency promises. Preserve stage1A2/native evidence and hash production before/after; verifier18checks before/after. Stop on frozen changes or worker conflict. Sequential progress saved after every request. Report after measured work and stop.
'''
    (out/'PREREGISTRATION.md').write_text(prereg)
    protected=[p for folder in ('backend','rag','router','workflows','scripts','evidence/json-action-adapter-v2/stage-1a-2','evidence/code-agent-fidelity-v1/native/snapshot') for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in str(p)]+[ROOT/'start-local-model.ps1',ROOT/'start-sovereign.ps1']
    hashes={str(p.relative_to(ROOT)):digest(p) for p in protected}
    assets=[ROOT/'models/Qwen3.5-4B-Q4_K_M.gguf',ROOT/'runtime/llama-b11132/llama-server.exe',ROOT/'models/bge-small-en-v1.5/onnx/model.onnx',ROOT/'models/bge-small-en-v1.5/tokenizer.json']
    save(out/'manifest.json',{'preregistration_sha256':digest(out/'PREREGISTRATION.md'),'corpus_sha256':digest(out/'README.md'),'definitions_sha256':digest(out/'retrieval-queries.json'),'frozen_sha256':hashes,'assets_sha256':{str(p.relative_to(ROOT)):digest(p) for p in assets}})
    print(out,flush=True);return out
def execute(out):
    out=out.resolve()
    assert not inspect_status(OUT)['running_verified'];registry=ModelRegistry();assert registry.verified_residency()=='Qwen/Qwen3.5-4B'
    with httpx.Client(trust_env=False) as client:assert not any(r['is_processing'] for r in client.get('http://127.0.0.1:8087/slots').json());save(out/'runtime-before.json',client.get('http://127.0.0.1:8087/props').json())
    from scripts.verify_docker_sandbox import verify
    image='sha256:6f6ac11cda347a185454338dee35d77003e066579a3261b52b7c6ff1048c8573';checks=verify(image);save(out/'docker-before.json',checks);assert len(checks)==18 and all(checks.values())
    initial=time.perf_counter_ns();embed=Embedder(ROOT/'models/bge-small-en-v1.5');extraction=extract(out/'README.md');chunks=chunk_pages(extraction,embed.tokenizer,'readme','README.md');vectors=embed.encode([c.text for c in chunks]);store=TimedStore(out/'workspace/index.sqlite');store.publish('readme','README.md',str(out/'README.md'),extraction.source_hash,chunks,vectors,embed.revision,[]);save(out/'index-initialization.json',{'seconds':(time.perf_counter_ns()-initial)/1e9,'chunks':len(chunks),'document_embeddings':len(chunks),'query_time_document_processing':False});del embed
    service,WB=load_service();model=TimedModel(transport=CaptureTransport(),verify_semantics=False);wb=WB(Settings(data_dir=out/'workspace',project_dir=out/'projects',context=16384,output_tokens=4096),store=store,embedder=TimedEmbedder(ROOT/'models/bge-small-en-v1.5'),model=model,registry=registry)
    rows=[]
    for i in range(4):rows.append(call(wb,out,'baseline-'+str(i),QUESTIONS[0][1],QUESTIONS[0][2]))
    for name,q,expected in QUESTIONS[1:]:rows.append(call(wb,out,'qa-baseline-'+name,q,expected))
    service.TOP_K=5
    for name,q,expected in QUESTIONS:rows.append(call(wb,out,'top5-'+name,q,expected))
    store.cached=True
    for name,q,expected in QUESTIONS:rows.append(call(wb,out,'cached-'+name,q,expected))
    for i,(q,expected) in enumerate([('17 + 25',42),('120 / 8',15),('15 * 13',195),('450 * 0.20',90),('99 - 37',62),('20% of 450',90)]):
        row=call(wb,out,'compute-'+str(i),q,forced=False);row['expected']=expected;row['correct']=row.get('result',{}).get('result',{}).get('result')==expected and row['model_calls']==0 and not row.get('retrievals');rows.append(row)
    history=[]
    for i,q in enumerate(['What Python version does the document require for installation?','What version is required?','Why is that version required?']):
        row=call(wb,out,'followup-'+str(i),q,QUESTIONS[0][2] if i<2 else None,history,forced=i==0);history.append(q);rows.append(row)
    rows.append(call(wb,out,'mixed','What port does the document give for the backend, and what is 17 + 25?',history=None,forced=False))
    save(out/'all-results.json',rows)
    manifest=json.loads((out/'manifest.json').read_text());changed=[p for p,d in manifest['frozen_sha256'].items() if digest(ROOT/p)!=d];asset_changed=[p for p,d in manifest['assets_sha256'].items() if digest(ROOT/p)!=d];save(out/'integrity.json',{'source_or_evidence_changes':changed,'asset_changes':asset_changed});assert not changed and not asset_changed
    after=verify(image);save(out/'docker-after.json',after);assert all(after.values());model.close()
if __name__=='__main__':
    if sys.argv[1]=='register': register()
    elif sys.argv[1]=='execute': execute(Path(sys.argv[2]))
