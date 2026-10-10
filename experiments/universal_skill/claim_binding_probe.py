"""Real Gemma probes of repaired claim bindings; no production activation."""
from pathlib import Path
import json,time,hashlib
from backend.model import LocalModel
from backend.contracts import Chunk
from rag.answer import answer
from router.model_registry import ModelRegistry

def main():
    root=Path(__file__).resolve().parents[2];out=root/'evidence/rag-claim-binding'/str(time.time_ns());out.mkdir(parents=True)
    registry=ModelRegistry();registry.acquire_lease('rag');model=LocalModel(verify_semantics=False)
    raw=model._request_raw;calls=[]
    def request(method,path,**kwargs):
        if method=='POST' and path=='/v1/chat/completions':
            if not registry._runtime_profile_matches(registry.launch_args('rag')):raise RuntimeError('Runtime mismatch')
            kwargs['json']={**kwargs['json'],'model':registry.specs['rag'].alias}
            receipt={'request':kwargs['json'],'runtime':registry.verified_residency()}
            response=raw(method,path,**kwargs);receipt['response']=response;calls.append(receipt)
            with (out/'calls.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(receipt,ensure_ascii=False)+'\n')
            return response
        return raw(method,path,**kwargs)
    model._request_raw=request
    cases=[('multi_source_overview','tell me about kpr college',[
        'KPR Institute of Engineering and Technology (KPRIET) is an engineering institution at KPR Knowledge Campus, Avinashi Road, Arasur, Coimbatore – 641 407, Tamil Nadu, India. Affiliated to Anna University and approved by AICTE.',
        'Academic options include Choice Based Credit System (CBCS), Fast Track System, student choice of project teammates, value-added certification courses and industry-oriented courses. Facilities include hostels, sports facilities, library resources and laboratories.',
        'General contact email: info@kpriet.ac.in. General contact phone: +91 422 263 5600. Admissions email: admission@kpriet.ac.in.']),
        ('missing_rationale','Why is the calibration interval 90 days?',[
            'The calibration interval is 90 days. No reason for this interval is documented.'])]
    results=[]
    try:
        for case,question,bodies in cases:
            start=time.perf_counter();offset=len(calls)
            chunks=[Chunk(f'c{i}',f'd{i}',hashlib.sha256(body.encode()).hexdigest(),f'reference-{i}.txt',body,None,1,5) for i,body in enumerate(bodies)]
            try:result=answer(question,chunks,model,context=16384,output_tokens=1024,max_repairs=1)
            except Exception as exc:result={'error':str(exc)}
            row={'case':case,'question':question,'bodies':bodies,'result':result,'seconds':time.perf_counter()-start,'model_calls':len(calls)-offset}
            results.append(row);(out/'results.json').write_text(json.dumps(results,indent=2,ensure_ascii=False))
            print(json.dumps({'case':case,'status':result.get('status'),'seconds':row['seconds'],'model_calls':row['model_calls']}),flush=True)
    finally:model.close()
    print(str(out),flush=True)

if __name__=='__main__':main()
