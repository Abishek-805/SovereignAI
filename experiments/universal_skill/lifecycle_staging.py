"""Isolated real application acceptance; no production startup or data access."""
from pathlib import Path
import json,hashlib
from experiments.rag_v2 import gemma_rag_acceptance as existing
ROOT=Path(__file__).resolve().parents[2]
OUT=Path((ROOT/'experiments/universal_skill/lifecycle-output.txt').read_text())
existing.OUT=OUT

def app():
    from backend.app import create_app
    from fastapi.staticfiles import StaticFiles
    fixtures=OUT/'fixtures';fixtures.mkdir(exist_ok=True)
    bodies={
      'KPRIET-reference.txt':'KPR Institute of Engineering and Technology (KPRIET) is an engineering institution at KPR Knowledge Campus, Avinashi Road, Arasur, Coimbatore â€“ 641 407, Tamil Nadu, India. Affiliated to Anna University and approved by AICTE.',
      'KPRIET-academics.txt':'KPRIET academic options include Choice Based Credit System (CBCS), Fast Track System and industry-oriented courses. KPRIET facilities include hostels, sports facilities, library resources and laboratories.',
      'Museum-reference.txt':'The Harbor Museum is a public museum in Northport. It opened in 1987. The museum has a maritime gallery and a reading room. Admission costs 12.5 credits. The website is https://example.org/museum.',
    }
    for name,body in bodies.items():(fixtures/name).write_text(body,encoding='utf-8')
    wb,ids=existing.build('gemma')
    (OUT/'document-ids.json').write_text(json.dumps(ids,indent=2))
    # Explicit test-only fault injection; preserve real model receipts before mutation.
    raw=wb.model._request_raw
    def request(method,path,**kwargs):
        response=raw(method,path,**kwargs)
        mode=(OUT/'fault-mode.txt').read_text().strip() if (OUT/'fault-mode.txt').exists() else ''
        from rag.model_routing import ACTIVE_RAG
        stage=(ACTIVE_RAG.get() or {}).get('stage')
        if mode in {'invalid_id','missing_id','quote_mismatch'} and stage=='assess_evidence' and method=='POST' and path=='/v1/chat/completions':
            response=json.loads(json.dumps(response));content=response['choices'][0]['message']['content'];review=json.loads(content)
            if mode=='invalid_id':review['claims'][0]['id']='C999'
            elif mode=='missing_id':review['claims']=[]
            else:
                for claim in review['claims']:
                    for quote in claim['quotes']:quote['text']='Deliberately non-verbatim controlled quote.'
            response['choices'][0]['message']['content']=json.dumps(review)
            with (OUT/'controlled-faults.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps({'mode':mode,'stage':stage,'mutated_review':review})+'\n')
        return response
    wb.model._request_raw=request
    complete=wb.model.complete
    def generate(*args,**kwargs):
        response=complete(*args,**kwargs)
        if (OUT/'fault-mode.txt').exists() and (OUT/'fault-mode.txt').read_text().strip()=='unsupported':
            response={**response,'result':{**response['result'],'answer':response['result']['answer']+' The institution operates an orbital campus on Mars. [S1]'}}
            with (OUT/'controlled-faults.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps({'mode':'unsupported','mutated_result':response['result']})+'\n')
        return response
    wb.model.complete=generate
    service=create_app(wb)
    service.router.routes[-1].app=StaticFiles(directory=str(OUT/'frontend-dist-complete'),html=True)
    hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [ROOT/'backend/jobs.py',ROOT/'router/task_completion.py',ROOT/'rag/grounding.py',ROOT/'rag/answer.py',ROOT/'backend/model.py',ROOT/'backend/service.py',ROOT/'rag/analytics.py',ROOT/'rag/tables.py',ROOT/'rag/recovery.py']}
    (OUT/'loaded-source-final.json').write_text(json.dumps(hashes,indent=2))
    return service
