"""Isolated real API/UI acceptance with synthetic sources and real Qwen."""
from pathlib import Path
import json,time,hashlib
import numpy as np
from backend.app import create_app
from backend.settings import Settings
from backend.service import Workbench
from backend.model import LocalModel
from rag.embedding import Embedder

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'evidence/rag-value-first/20261009'

def app():
    OUT.mkdir(parents=True,exist_ok=True)
    model=LocalModel(verify_semantics=False)
    original=model._planned_completion
    def capture(payload,**kwargs):
        response=original(payload,**kwargs)
        with (OUT/'model-trajectories.jsonl').open('a',encoding='utf-8') as handle:
            handle.write(json.dumps({'request':payload,'response':response},ensure_ascii=False)+'\n')
        return response
    model._planned_completion=capture
    workbench=Workbench(Settings(data_dir=OUT/'ui-data',context=16384,output_tokens=1024),model=model)
    fixtures=OUT/'fixtures';fixtures.mkdir(exist_ok=True)
    source=fixtures/'synthetic-skills.csv'
    source.write_text('Register Number,Professional Skills,Communication\n24ALR056,85,78\n24ALR055,70,90\n',encoding='utf-8')
    manual=fixtures/'synthetic-manual.txt'
    manual.write_text('Python 3.12 is required. The deployment owner is Mira Chen. No date of birth is recorded.',encoding='utf-8')
    for path in [source,manual]:workbench.import_file(path,display_name=path.name)
    (OUT/'ui-sources.json').write_text(json.dumps(workbench.documents(),indent=2),encoding='utf-8')
    planner=model.plan_table_query
    def wrong_column_probe(question,*args,**kwargs):
        plan=planner(question,*args,**kwargs)
        if '24ALR056' in question and plan.get('operation')=='select':
            faulty={**plan,'filters':[{'column':'Member Id','operator':'eq','value':'24ALR056'}]}
            with (OUT/'fault-injection.jsonl').open('a',encoding='utf-8') as handle:
                handle.write(json.dumps({'question':question,'actual_plan':plan,'injected_plan':faulty})+'\n')
            return faulty
        return plan
    model.plan_table_query=wrong_column_probe
    actual_ask=workbench.ask
    def capture_ask(question,*args,**kwargs):
        start=time.perf_counter()
        try:
            result=actual_ask(question,*args,**kwargs)
            receipt={'question':question,'result':result,'seconds':time.perf_counter()-start}
        except Exception as error:
            receipt={'question':question,'error':str(error),'seconds':time.perf_counter()-start}
            raise
        finally:
            with (OUT/'api-trajectories.jsonl').open('a',encoding='utf-8') as handle:
                handle.write(json.dumps(receipt,ensure_ascii=False)+'\n')
        return result
    workbench.ask=capture_ask
    return create_app(workbench)

if __name__=='__main__':
    corpus=json.loads((OUT/'retrieval-probes.json').read_text())
    encoder=Embedder(ROOT/'models/bge-small-en-v1.5')
    docs=encoder.encode([d['text'] for d in corpus['documents']])
    queries=encoder.encode([q['question'] for q in corpus['queries']],query=True)
    scores=queries@docs.T
    rows=[{**q,'top_document':corpus['documents'][int(np.argmax(s))]['id'],
           'passed':corpus['documents'][int(np.argmax(s))]['id']==q['expected'],'scores':s.tolist()} for q,s in zip(corpus['queries'],scores)]
    (OUT/'baseline-retrieval.json').write_text(json.dumps({'model':'CURRENT_BASELINE','queries':rows,'passed':sum(r['passed'] for r in rows),'total':len(rows)},indent=2))
