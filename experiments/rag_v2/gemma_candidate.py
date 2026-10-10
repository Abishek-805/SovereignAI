"""Explicit isolated CPU candidate. Never changes the app embedding index."""
import os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'evidence/rag-value-first/20261009'
os.environ['HF_HOME']=str(OUT/'gemma-cache')
os.environ['HF_HUB_DISABLE_PROGRESS_BARS']='1'
import json,time,traceback,importlib.metadata
import numpy as np
import torch,psutil
from sentence_transformers import SentenceTransformer

REVISION='914f7f89142e33e77833254d9c9b90c3cef7303b'

def main():
    result={'model':'google/embeddinggemma-2','revision':REVISION,'device':'cpu',
        'vision_config':None,'audio_config':None,'dimensions':768,'promoted':False,
        'versions':{k:importlib.metadata.version(k) for k in ['torch','transformers','sentence-transformers']}}
    start=time.perf_counter()
    try:
        torch.set_num_threads(4)
        model=SentenceTransformer(result['model'],revision=REVISION,device='cpu',
            config_kwargs={'vision_config':None,'audio_config':None},model_kwargs={'dtype':torch.float32})
        result['load_seconds']=time.perf_counter()-start
        corpus=json.loads((OUT/'retrieval-probes.json').read_text(encoding='utf-8'))
        start=time.perf_counter()
        docs=model.encode([d['text'] for d in corpus['documents']],prompt_name='Document',normalize_embeddings=True)
        query=model.encode([q['question'] for q in corpus['queries']],prompt_name='SearchQuery',normalize_embeddings=True)
        assert docs.shape[1]==768 and np.isfinite(docs).all() and np.isfinite(query).all()
        scores=query@docs.T
        result['queries']=[{**q,'top_document':corpus['documents'][int(np.argmax(s))]['id'],
            'passed':corpus['documents'][int(np.argmax(s))]['id']==q['expected'],
            'scores':s.tolist()} for q,s in zip(corpus['queries'],scores)]
        result.update(status='PASS',encode_seconds=time.perf_counter()-start,
            cpu_rss_bytes=psutil.Process().memory_info().rss,passed=sum(q['passed'] for q in result['queries']),
            total=len(result['queries']))
    except Exception:
        result.update(status='BLOCKED',error=traceback.format_exc(),elapsed_seconds=time.perf_counter()-start)
    (OUT/'gemma-results.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in {'queries'}}),flush=True)

if __name__=='__main__':main()
