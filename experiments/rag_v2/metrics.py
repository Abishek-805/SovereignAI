"""Binary source relevance metrics; unknown oracles never become zero scores."""
import json,math,statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'evidence/rag-fast-comparison/20261009'
def load(p):return json.loads(p.read_text(encoding='utf-8'))
def quality(ranking,grades):
    ranking=list(dict.fromkeys(ranking))
    relevant={k for k,v in grades.items() if v>0}
    if not relevant:return None
    positions=[i for i,k in enumerate(ranking,1) if k in relevant]
    values={f'Recall@{k}':len(set(ranking[:k])&relevant)/len(relevant) for k in [1,3,5,10]}
    values['MRR']=1/min(positions) if positions else 0
    dcg=sum((2**grades.get(k,0)-1)/math.log2(i+2) for i,k in enumerate(ranking[:10]))
    ideal=sum((2**v-1)/math.log2(i+2) for i,v in enumerate(sorted(grades.values(),reverse=True)[:10]))
    values['nDCG@10']=dcg/ideal
    return values
def main():
    qrels=load(OUT/'qrels.json')['grades'];queries=load(OUT/'queries.json');result={}
    for arm in ['CURRENT_BASELINE','E5_QDRANT_HYBRID','BGE_M3_QDRANT_HYBRID']:
        p=OUT/arm/'retrieval.json'
        if not p.exists():result[arm]={'status':'NOT_RUN'};continue
        rows=load(p);scored=[]
        for row in rows:
            if row['id'] in qrels and row['repeat']==0:
                score=quality(row['ranking'],qrels[row['id']]);scored.append({'id':row['id'],'repeat':row['repeat'],**score,'final_evidence_recall':len({c['chunk_id'] for c in row['final_chunks']}&set(qrels[row['id']]))/len(qrels[row['id']])})
        stages=sorted({k for row in rows for k in row['stage_seconds']})
        result[arm]={'status':'COMPLETE' if len(rows)==len(queries)*3 else 'PARTIAL','measurements':len(rows),'unique_queries':len({r['id'] for r in rows}),'relevance_oracle_queries':len({r['id'] for r in scored}),'metrics':{k:statistics.mean(r[k] for r in scored) for k in ['Recall@1','Recall@3','Recall@5','Recall@10','MRR','nDCG@10','final_evidence_recall']} if scored else None,'retrieval_median_seconds':statistics.median(r['retrieval_seconds'] for r in rows),'stage_medians_seconds':{k:statistics.median(r['stage_seconds'][k] for r in rows if k in r['stage_seconds']) for k in stages},'cpu_seconds_median':statistics.median(r['cpu_seconds'] for r in rows),'representative_peak_observed_rss':max(r['rss'] for r in rows),'index':load(OUT/arm/'index.json'),'per_query_quality':scored,'temporal_correctness':'UNKNOWN: no temporal fixture with reliable oracle','semantic_answer_correctness':'NOT_YET_REVIEWED'}
    (OUT/'retrieval-metrics.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    first={a:[r for r in load(OUT/a/'retrieval.json') if r['repeat']==0] for a in result if (OUT/a/'retrieval.json').exists()}
    common=set.intersection(*[{r['id'] for r in rows} for rows in first.values()]) if len(first)==3 else set()
    paired={a:{'paired_queries':len(common),'retrieval_median_seconds':statistics.median(r['retrieval_seconds'] for r in rows if r['id'] in common) if common else None,'stage_medians_seconds':{k:statistics.median(r['stage_seconds'][k] for r in rows if r['id'] in common and k in r['stage_seconds']) for k in sorted({k for r in rows if r['id'] in common for k in r['stage_seconds']})},'CPU_seconds_median':statistics.median(r['cpu_seconds'] for r in rows if r['id'] in common) if common else None} for a,rows in first.items()}
    (OUT/'paired-retrieval-timings.json').write_text(json.dumps({'query_ids':sorted(common),'arms':paired,'method':'Matched initial pass only. Partial repeat measurements retained separately; no biased mixed-repeat median used for ranking.'},indent=2),encoding='utf-8')
    print(json.dumps({a:{k:v for k,v in r.items() if k in ['status','metrics','retrieval_median_seconds','measurements']} for a,r in result.items()},indent=2))
def check():
    assert quality(['a','b'],{'b':1})['MRR']==.5
    assert quality(['a','a'],{'a':1,'b':1})['Recall@3']==.5
    assert quality([],{}) is None
    assert quality(['a'],{'a':1})['nDCG@10']==1
if __name__=='__main__':check();main()
