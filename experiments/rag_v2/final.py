"""One frozen paired comparison; no training or historical evidence writes."""
import os
os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',CUDA_VISIBLE_DEVICES='')
import hashlib,json,sqlite3,time,sys,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT/'.app-venv/Lib/site-packages'))
import numpy as np,psutil,httpx
from dataclasses import replace,asdict
from backend.contracts import Chunk
import importlib.util
from rag.retrieve import retrieve,rrf,document_scope_for_question
from rag.store import Store
from rag.embedding import Embedder
from rag.handoff import active_evidence
from rag.tables import load_tables,execute_query,compile_outcome_query,bind_selection_request
from rag.calculator import evaluate_expression
from rag.answer import answer
from experiments.rag_v2.compare import bm25
spec=importlib.util.spec_from_file_location('prior_diagnostic',ROOT/'experiments/model-understanding/run.py')
prior=importlib.util.module_from_spec(spec);spec.loader.exec_module(prior)
OUT=ROOT/'evidence/rag-final-comparison/20261009'


def save(path,value):
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');temp.replace(path)


def prepare():
    assert not (OUT/'suite.json').exists(),'Frozen final suite already exists'
    OUT.mkdir(parents=True,exist_ok=True)
    cases=prior.load(ROOT/'experiments/model-understanding/suite.json')['cases']
    extras=[
        ('filter-count','filtering','In students.csv, count students whose Status is Pass.',{'operation':'count','value':5,'filters':[{'column':'Status','operator':'eq','value':'Pass'}]}),
        ('group-sum','grouping','In students.csv, sum Score separately for each Cohort.',{'operation':'aggregate','groups':{'A':108,'B':130},'group_by':['Cohort'],'metric':'sum','column':'Score'}),
        ('bottom-three','top_k','In students.csv, show the 3 lowest Score values with their student IDs, sorted ascending.',{'operation':'select','order_by':[{'column':'Score','direction':'asc'}],'limit':3,'records':[{'ID':'S07','Score':16},{'ID':'S01','Score':18},{'ID':'S04','Score':22}]}),
    ]
    for identifier,category,question,oracle in extras:
        cases.append({'id':identifier,'category':category,'question':question,'scope':['students'],'history':[],'oracle':oracle,'origin':'AUTHORIZED_EXISTING_ENGINEERING_FIXTURE'})
    save(OUT/'suite.json',cases)
    files=['backend/model.py','rag/retrieve.py','rag/tables.py','rag/answer.py','rag/handoff.py']
    save(OUT/'preregistration.json',{'cases_per_arm':len(cases),'arms':['CURRENT_BASELINE','E5_QDRANT_HYBRID'],
        'suite_sha256':prior.digest(OUT/'suite.json'),'source_sha256':prior.digest(ROOT/'experiments/model-understanding/suite.json'),
        'code_hashes':{f:prior.digest(ROOT/f) for f in files},'model':'Qwen3.5-4B-Q4_K_M.gguf','temperature':0,
        'context':16384,'output_tokens':4096,'timeout':120,'max_answer_repairs':1,'attempts_per_case':1,'reranker':False,
        'RUN_TRAIN':False,'dataset_modified':False,'oracle_in_model_context':False,
        'coverage_note':'Existing frozen cases retained, three additional operations over existing engineering fixture; followups overlap paraphrase; MIN covered by source numeric self-check, not extra LLM case.'})
    source=sqlite3.connect(ROOT/'experiments/model-understanding/index.sqlite')
    target=sqlite3.connect(OUT/'baseline.sqlite');source.backup(target);target.close();source.close()


class E5:
    def __init__(self,store):
        import torch
        from transformers import AutoModel,AutoTokenizer
        from qdrant_client import QdrantClient,models as qm
        self.torch=torch;self.qm=qm;torch.set_num_threads(2)
        folder=ROOT/'experiments/rag_v2/models/multilingual-e5-base'
        self.tokenizer=AutoTokenizer.from_pretrained(folder,local_files_only=True)
        self.model=AutoModel.from_pretrained(folder,local_files_only=True).eval()
        self.chunks=[c for c,v in store.active_chunks()];self.byid={c.chunk_id:c for c in self.chunks}
        sparse,self.sparsequery=bm25([c.text for c in self.chunks])
        self.client=QdrantClient(path=str(OUT/'qdrant'))
        if self.client.collection_exists('final'):
            assert self.client.count('final',exact=True).count==len(self.chunks)
            return
        vectors=self.encode([c.text for c in self.chunks])
        self.client.create_collection('final',vectors_config={'dense':qm.VectorParams(size=768,distance=qm.Distance.COSINE)},sparse_vectors_config={'sparse':qm.SparseVectorParams()})
        points=[qm.PointStruct(id=str(uuid.uuid5(uuid.NAMESPACE_URL,c.chunk_id)),vector={'dense':v.tolist(),'sparse':qm.SparseVector(indices=list(s),values=list(s.values()))},payload=c.to_dict()) for c,v,s in zip(self.chunks,vectors,sparse)]
        self.client.upsert('final',points=points,wait=True)
        assert self.client.count('final',exact=True).count==len(self.chunks)
    def encode(self,texts,query=False):
        formatted=[('query: ' if query else 'passage: ')+text for text in texts]
        assert all(len(self.tokenizer(text)['input_ids'])<=512 for text in formatted),'E5 input overflow; no truncation permitted'
        vectors=[]
        with self.torch.inference_mode():
            for offset in range(0,len(texts),4):
                batch=self.tokenizer(formatted[offset:offset+4],padding=True,truncation=False,return_tensors='pt')
                hidden=self.model(**batch).last_hidden_state.masked_fill(~batch['attention_mask'][...,None].bool(),0)
                pooled=hidden.sum(1)/batch['attention_mask'].sum(1)[...,None]
                vectors.extend(self.torch.nn.functional.normalize(pooled,p=2,dim=1).numpy())
        return np.asarray(vectors)
    def retrieve(self,store,query,scope):
        scope=document_scope_for_question(store.documents(),query,scope)
        filt=self.qm.Filter(must=[self.qm.FieldCondition(key='document_id',match=self.qm.MatchAny(any=scope))]) if scope is not None else None
        vector=self.encode([query],True)[0];sparse=self.sparsequery(query)
        dense=self.client.query_points('final',query=vector.tolist(),using='dense',query_filter=filt,limit=20).points
        lexical=self.client.query_points('final',query=self.qm.SparseVector(indices=list(sparse),values=list(sparse.values())),using='sparse',query_filter=filt,limit=20).points if sparse else []
        ranking=rrf([[p.payload['chunk_id'] for p in dense],[p.payload['chunk_id'] for p in lexical]])
        result=[]
        for key in ranking:
            c=self.byid[key]
            if not any((c.document_id,c.page,c.text)==(p.document_id,p.page,p.text) for p in result):result.append(c)
            if len(result)==6:break
        return result


def run_case(case,model,store,fetch,table):
    started=time.perf_counter();marks={};model.events=[]
    row={'id':case['id'],'category':case['category'],'request':case['question'],'oracle':case['oracle'],'status':'RUNNING','retrieval_calls':0,'tool_calls':0}
    def mark(name):marks[name]=time.perf_counter()-started
    try:
        plan=model.plan_task(case['question'],store.planning_context(case['scope'],case['question'],total_chars=6000) if case['scope'] else [],[],case['history'])
        row['understanding']=plan;mark('understanding_complete')
        scoped=document_scope_for_question(store.documents(),case['question'],case['scope']);row['scope']=scoped
        mark('retrieval_start');query=case['question'];passages=[]
        if case['history']:
            # Authorized preceding request is replayed through the same arm, not an oracle answer injected as evidence.
            antecedent=case['history'][0].split(':',1)[-1].strip()
            previous=fetch(antecedent,scoped);row['retrieval_calls']+=1
            bound=active_evidence(store,[p.chunk_id for p in previous],scoped)
            decision=model.evidence_handoff(query,case['history'],bound);row['handoff']=decision
            if decision['reuse']:passages=bound
            else:query=decision['query'].strip() or query
        if plan['action']=='search_documents' and not passages:
            passages=fetch(query,scoped);row['retrieval_calls']+=1
        row['retrieval_query']=query;mark('retrieval_complete');operation=None
        if plan['action']=='search_documents' and 'students' in case['scope']:
            operation=model.plan_table_query(case['question'],prior.table_catalog(table,case['question'],case['history']),case['history'])
            row['operation_plan']=operation
            if operation.get('_measure'):operation=compile_outcome_query(operation['_measure'],{'T1':({'document_id':'students'},table)},case['question'],case['history'])
            if operation.get('operation')!='none':operation=bind_selection_request(operation,table,case['question'])
            row['effective_operation']=operation
        mark('execution_start')
        if plan['action']=='calculate':
            calculated=asdict(evaluate_expression(plan['expression']));row['tool_result']=calculated;row['tool_calls']=1
            final={'status':'answered','answer':str(calculated),'sources':[],'checks':{'deterministic_calculator':True}}
        elif operation and operation.get('operation')!='none':
            result=execute_query(table,operation);row['tool_result']=result;row['tool_calls']=1
            source=next(c for c,v in store.active_chunks(['students']) if c.retrieval_kind=='schema')
            passages=[replace(source,query_result=result,text='Verified read-only complete-source query.\n'+json.dumps(result))]
        mark('execution_complete');row['evidence']=[p.to_dict() for p in passages];mark('generation_start')
        if plan['action']=='search_documents':final=answer(case['question'],passages,model,16384,4096,64,history=case['history'],max_repairs=1)
        elif plan['action']!='calculate':final={'status':'answered','answer':plan.get('response',''),'sources':[]}
        row['final']=final;row['status']='COMPLETED'
    except Exception as exc:row.update(status='ERROR',error={'type':type(exc).__name__,'code':getattr(exc,'code',None),'message':str(exc)})
    mark('generation_complete');row['timestamps']=marks;row['total_seconds']=time.perf_counter()-started
    row['model_events']=model.events;row['model_calls']=len(model.events);row['rss']=psutil.Process().memory_info().rss
    row['repairs']=sum(len(row.get('final',{}).get('checks',{}).get('prior_attempt_checks',[])) for _ in [0])
    return row


def main():
    if sys.argv[-1]=='prepare':prepare();return
    recovering=sys.argv[-1]=='resume'
    frozen=prior.load(OUT/'preregistration.json');assert prior.digest(OUT/'suite.json')==frozen['suite_sha256']
    assert all(prior.digest(ROOT/f)==h for f,h in frozen['code_hashes'].items()),'Frozen code changed'
    props=httpx.get('http://127.0.0.1:8087/props',timeout=20).json()
    assert Path(props['model_path']).name==frozen['model'] and props['default_generation_settings']['n_ctx']==16384
    assert not any(s.get('is_processing') for s in httpx.get('http://127.0.0.1:8087/slots',timeout=20).json())
    save(OUT/('recovery-runtime.json' if recovering else 'runtime.json'),{'props':props,'model_sha256':prior.digest(Path(props['model_path'])),'RUN_TRAIN':False})
    store=Store(OUT/'baseline.sqlite');encoder=Embedder(ROOT/'models/bge-small-en-v1.5')
    table=load_tables(ROOT/'experiments/model-understanding/students.csv')[0];cases=prior.load(OUT/'suite.json')
    for arm in frozen['arms']:
        if recovering and arm=='CURRENT_BASELINE':continue
        path=OUT/(arm+('-recovery' if recovering else '')+'.json');assert not path.exists(),'Raw evidence already exists'
        original=prior.load(OUT/(arm+'.json')) if recovering else []
        completed={r['id'] for r in original if r['status']=='COMPLETED'}
        start=time.perf_counter();candidate=E5(store) if arm=='E5_QDRANT_HYBRID' else None
        fetch=(lambda query,scope:candidate.retrieve(store,query,scope)) if candidate else (lambda query,scope:retrieve(store,encoder,query,scope,limit=6))
        save(OUT/(arm+('-recovery' if recovering else '')+'-initialization.json'),{'seconds':time.perf_counter()-start,'rss':psutil.Process().memory_info().rss,'reranker':False})
        model=prior.ObservedModel();rows=[]
        for case in cases:
            if case['id'] in completed:continue
            row=run_case(case,model,store,fetch,table);rows.append(row);save(path,rows)
            print(arm,len(rows),'/',len(cases),case['id'],row['status'],round(row['total_seconds'],2),flush=True)
            if row.get('error',{}).get('code')=='model_unavailable':
                raise RuntimeError('Runtime unavailable; arm stopped and raw evidence preserved')
        model.close()
        if candidate:candidate.client.close()
    save(OUT/'completed.json',{'requests':2*len(cases),'raw_capture':'COMPLETE','independent_review':'PENDING','RUN_TRAIN':False})


if __name__=='__main__':main()
