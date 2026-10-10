"""Isolated CPU retrieval arms over immutable chunks; generation stays on the existing worker."""
import os
os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',CUDA_VISIBLE_DEVICES='')
import collections, gc, hashlib, json, math, re, sys, time, uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
sys.path.append(str(ROOT/'.app-venv/Lib/site-packages'))
import numpy as np, psutil
from backend.contracts import Chunk
from rag.retrieve import retrieve, rrf
from rag.store import Store
from rag.embedding import Embedder

OUT=Path(os.environ.get('RAG_COMPARISON_OUT',ROOT/'evidence/rag-v2-comparison/20261009'))
MODELS=ROOT/'experiments/rag_v2/models'
def load(p):return json.loads(p.read_text(encoding='utf-8'))
def save(p,v):
    tmp=p.with_suffix(p.suffix+'.tmp');tmp.write_text(json.dumps(v,indent=2,ensure_ascii=False)+'\n',encoding='utf-8');tmp.replace(p)
def timed(stages,key,fn):
    start=time.perf_counter();value=fn();stages[key]=time.perf_counter()-start;return value
def words(t):return re.findall(r'\w+',t.casefold(),re.UNICODE)
def bm25(texts):
    counts=[collections.Counter(words(t)) for t in texts];vocab={w:i for i,w in enumerate(sorted({w for c in counts for w in c}))}
    df=collections.Counter(w for c in counts for w in c);avg=sum(sum(c.values()) for c in counts)/len(counts)
    docs=[{vocab[w]:tf*2.2/(tf+1.2*(.25+.75*sum(c.values())/avg)) for w,tf in c.items()} for c in counts]
    def query(t):return {vocab[w]:math.log(1+(len(counts)-df[w]+.5)/(df[w]+.5)) for w in set(words(t)) if w in vocab}
    return docs,query

def main(arm):
    phase_start=time.perf_counter()
    path=OUT/arm;path.mkdir(exist_ok=False)
    manifest=load(OUT/'manifest.json')
    for name in ['chunks','queries']:assert hashlib.sha256((OUT/(name+'.json')).read_bytes()).hexdigest()==manifest[name+'_sha256']
    chunks=[Chunk(**c) for c in load(OUT/'chunks.json')];queries=load(OUT/'queries.json')
    byid={c.chunk_id:c for c in chunks};stages={};cpu0=time.process_time();start=time.perf_counter()
    cached=ROOT/'evidence/rag-v2-comparison/20261009'/arm
    reuse=OUT!=ROOT/'evidence/rag-v2-comparison/20261009' and (cached/'index.json').exists()
    if arm=='CURRENT_BASELINE':
        encoder=Embedder(ROOT/'models/bge-small-en-v1.5')
        store=Store((cached if reuse else path)/'baseline.sqlite')
        if not reuse:
            vectors=encoder.encode([c.text for c in chunks])
            for i,c in enumerate(chunks):
                if c.retrieval_kind=='lexical':vectors[i]=0
            for doc in sorted({c.document_id for c in chunks}):
                ids=[i for i,c in enumerate(chunks) if c.document_id==doc];c=chunks[ids[0]]
                store.publish(doc,c.display_name,'frozen',c.version_hash,[chunks[i] for i in ids],vectors[ids],encoder.revision,[])
        assert {c.chunk_id for c,_ in store.active_chunks()}==set(byid)
        dim=384;revision=encoder.revision
    else:
        import torch
        from transformers import AutoModel,AutoTokenizer,AutoModelForSequenceClassification
        from qdrant_client import QdrantClient,models as qm
        torch.set_num_threads(manifest['policy'].get('cpu_threads',2))
        if arm=='E5_QDRANT_HYBRID':
            folder=MODELS/'multilingual-e5-base';tokenizer=AutoTokenizer.from_pretrained(folder,local_files_only=True)
            encoder=AutoModel.from_pretrained(folder,local_files_only=True).eval()
            def encode(texts,query=False):
                formatted=[('query: ' if query else 'passage: ')+t for t in texts]
                assert all(len(tokenizer(t)['input_ids'])<=512 for t in formatted),'E5 input exceeds512; no truncation permitted'
                result=[]
                with torch.inference_mode():
                    for offset in range(0,len(texts),4):
                        batch=tokenizer(formatted[offset:offset+4],padding=True,truncation=False,return_tensors='pt')
                        hidden=encoder(**batch).last_hidden_state.masked_fill(~batch['attention_mask'][...,None].bool(),0)
                        pooled=hidden.sum(1)/batch['attention_mask'].sum(1)[...,None]
                        result.extend(torch.nn.functional.normalize(pooled,p=2,dim=1).cpu().numpy())
                return np.asarray(result)
            vectors=encode([c.text for c in chunks]) if not reuse else None;sparse,sparsequery=bm25([c.text for c in chunks]);dim=768;revision=manifest['models']['e5']
        else:
            from FlagEmbedding import BGEM3FlagModel
            encoder=BGEM3FlagModel(str(MODELS/'bge-m3'),use_fp16=False,devices=['cpu'])
            assert all(len(encoder.tokenizer(c.text)['input_ids'])<=8192 for c in chunks)
            encoded=encoder.encode([c.text for c in chunks],batch_size=4,max_length=8192,return_dense=True,return_sparse=True,return_colbert_vecs=False)
            vectors=encoded['dense_vecs'];sparse=[{int(k):float(v) for k,v in s.items()} for s in encoded['lexical_weights']];dim=1024;revision=manifest['models']['bgem3']
        if not reuse:assert len(vectors)==len(chunks) and np.isfinite(vectors).all()
        client=QdrantClient(path=str((cached if reuse else path)/'qdrant'));collection='sovereignai_rag_e5' if dim==768 else 'sovereignai_rag_bgem3'
        if not reuse:client.create_collection(collection,vectors_config={'dense':qm.VectorParams(size=dim,distance=qm.Distance.COSINE)},sparse_vectors_config={'sparse':qm.SparseVectorParams()})
        points=[]
        for c,v,s in zip(chunks,vectors if not reuse else [],sparse):
            payload={**c.to_dict(),'locator':{'page':c.page,'line_start':c.line_start,'line_end':c.line_end},'embedding_model':'intfloat/multilingual-e5-base' if dim==768 else 'BAAI/bge-m3','model_revision':revision,'dimension':dim,'generation_metadata':{'device':'cpu','no_truncation':True}}
            points.append(qm.PointStruct(id=str(uuid.uuid5(uuid.NAMESPACE_URL,c.chunk_id)),vector={'dense':v.tolist(),'sparse':qm.SparseVector(indices=list(s),values=list(s.values()))},payload=payload))
        if not reuse:client.upsert(collection,points=points,wait=True)
        assert client.count(collection,exact=True).count==len(chunks)
        reranktoken=AutoTokenizer.from_pretrained(MODELS/'bge-reranker-v2-m3',local_files_only=True)
        reranker=AutoModelForSequenceClassification.from_pretrained(MODELS/'bge-reranker-v2-m3',local_files_only=True).eval()
    save(path/'index.json',{'reused_index':reuse,'original_index':str(cached) if reuse else None,'chunks':len(chunks),'documents':len({c.document_id for c in chunks}),'versions':len({(c.document_id,c.version_hash) for c in chunks}),'dimension':dim,'revision':revision,'initialization_seconds':time.perf_counter()-start,'cpu_seconds':time.process_time()-cpu0,'rss':psutil.Process().memory_info().rss,'disk_bytes':sum(p.stat().st_size for p in (cached if reuse else path).rglob('*') if p.is_file())})
    rows=[]
    for repeat in range(3):
        for q in queries:
            stages={};start=time.perf_counter();cpu0=time.process_time();question=q['question'].strip()
            if arm=='CURRENT_BASELINE':
                selected=timed(stages,'retrieval_total',lambda:retrieve(store,encoder,question,q['scope'],limit=10));ranked=[c.chunk_id for c in selected]
            else:
                if dim==768:
                    dense=timed(stages,'query_embedding',lambda:encode([question],query=True)[0]);sq=timed(stages,'sparse_encoding',lambda:sparsequery(question))
                else:
                    assert len(encoder.tokenizer(question)['input_ids'])<=8192
                    e=timed(stages,'query_embedding_and_sparse',lambda:encoder.encode([question],batch_size=1,max_length=8192,return_dense=True,return_sparse=True,return_colbert_vecs=False))
                    dense=e['dense_vecs'][0];sq={int(k):float(v) for k,v in e['lexical_weights'][0].items()}
                filt=qm.Filter(must=[qm.FieldCondition(key='document_id',match=qm.MatchAny(any=q['scope']))])
                dr=timed(stages,'dense_retrieval',lambda:client.query_points(collection,query=dense.tolist(),using='dense',query_filter=filt,limit=20).points)
                sr=timed(stages,'sparse_retrieval',lambda:client.query_points(collection,query=qm.SparseVector(indices=list(sq),values=list(sq.values())),using='sparse',query_filter=filt,limit=20).points) if sq else []
                fused=timed(stages,'rrf',lambda:rrf([[p.payload['chunk_id'] for p in dr],[p.payload['chunk_id'] for p in sr]]))[:20]
                pairs=[[question,byid[k].text] for k in fused]
                assert all(len(reranktoken(*pair)['input_ids'])<=8192 for pair in pairs),'Reranker truncation prohibited'
                def score():
                    scores=[]
                    with torch.inference_mode():
                        for offset in range(0,len(pairs),4):
                            batch=reranktoken(pairs[offset:offset+4],padding=True,truncation=False,return_tensors='pt')
                            scores.extend(reranker(**batch).logits.view(-1).tolist())
                    return scores
                scores=timed(stages,'reranker',score)
                ranked=[k for _,k in sorted(zip(scores,fused),key=lambda v:(-v[0],v[1]))]
                selected=[]
                for k in ranked:
                    c=byid[k]
                    if not any((v.document_id,v.page,v.text)==(c.document_id,c.page,c.text) for v in selected):selected.append(c)
            row={'arm':arm,'repeat':repeat,'id':q['id'],'question':question,'scope':q['scope'],'ranking':ranked,'final_chunks':[c.to_dict() for c in selected[:6]],'stage_seconds':stages,'retrieval_seconds':time.perf_counter()-start,'cpu_seconds':time.process_time()-cpu0,'rss':psutil.Process().memory_info().rss,'oracle':q['oracle_kind']}
            rows.append(row);save(path/'retrieval.json',rows);print(arm,'query',len(rows),'/',len(queries)*3,q['id'],'elapsed',round(time.perf_counter()-phase_start,1),'seconds',round(row['retrieval_seconds'],3),flush=True)
    if arm!='CURRENT_BASELINE':client.close()

if __name__=='__main__':main(sys.argv[1])
