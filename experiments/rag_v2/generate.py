"""At most ten existing questions per arm, unchanged local Qwen answer contract."""
import json,sys,time
from pathlib import Path
import httpx,psutil
from backend.contracts import Chunk
from backend.model import LocalModel
from rag.answer import answer
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'evidence/rag-fast-comparison/20261009'
def main(arm):
    manifest=json.loads((OUT/'manifest.json').read_text(encoding='utf-8'))
    source=OUT/arm/'retrieval.json'
    if not source.exists():raise RuntimeError('No completed retrieval evidence for '+arm)
    rows=json.loads(source.read_text(encoding='utf-8'))
    chosen=[r for r in rows if r['repeat']==0 and r['id'] in manifest['generation_subset']]
    model=LocalModel(verify_semantics=False);results=[]
    props=httpx.get('http://127.0.0.1:8087/props',timeout=30).json()
    assert props['model_path'].endswith('Qwen3.5-4B-Q4_K_M.gguf'),props['model_path']
    for row in chosen:
        start=time.perf_counter()
        result=answer(row['question'],[Chunk(**c) for c in row['final_chunks']],model,context=16384,output_tokens=4096,safety_tokens=64,max_repairs=1)
        results.append({'id':row['id'],'question':row['question'],'result':result,'retrieval_seconds':row['retrieval_seconds'],'answer_seconds':time.perf_counter()-start,'total_request_seconds':row['retrieval_seconds']+time.perf_counter()-start,'rss':psutil.Process().memory_info().rss,'runtime_identity':{'model_path':props['model_path'],'alias':props['model_alias'],'context':props['default_generation_settings']['n_ctx']}})
        p=OUT/arm/'answers.json';tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(results,indent=2,ensure_ascii=False),encoding='utf-8');tmp.replace(p)
        print(arm,'answer',len(results),'/10',row['id'],round(results[-1]['answer_seconds'],2),flush=True)
    model.close()
if __name__=='__main__':main(sys.argv[1])
