"""Actual Agent endpoint/UI acceptance; isolated data, unchanged model runtime."""
from pathlib import Path
import json,time,shutil,hashlib,sys
from backend.app import create_app
from backend.service import Workbench
from backend.settings import Settings
from backend.model import LocalModel

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'evidence/agent-rag-critical/20261009'

def app():
    run_id=str(time.time_ns())
    runtime=OUT/'runtimes'/run_id;runtime.mkdir(parents=True)
    files=['backend/service.py','rag/identifiers.py','rag/tables.py','rag/answer.py','rag/retrieve.py','backend/app.py']
    hashes={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in files}
    for name in files:
        dest=runtime/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes((ROOT/name).read_bytes())
    (runtime/'runtime.json').write_text(json.dumps({'run_id':run_id,'source_hashes':hashes,'python':sys.version,'executable':sys.executable},indent=2))
    target=OUT/'ui-data'
    if not target.exists():shutil.copytree(ROOT/'evidence/rag-value-first/20261009/ui-data',target)
    model=LocalModel(verify_semantics=False)
    wb=Workbench(Settings(data_dir=target,context=16384,output_tokens=1024),model=model)
    original=model._planned_completion
    calls=[]
    def capture(payload,**kwargs):
        calls.append(time.perf_counter())
        return original(payload,**kwargs)
    model._planned_completion=capture
    request=model._request
    runtime_calls=[]
    def runtime_capture(method,path,**kwargs):
        runtime_calls.append({'method':method,'path':path})
        return request(method,path,**kwargs)
    model._request=runtime_capture
    agent=wb.run_auto_agent
    def run(goal,*args,**kwargs):
        start=time.perf_counter();before=len(calls);before_runtime=len(runtime_calls)
        receipt={'question':goal,'run_id':run_id}
        try:
            result=agent(goal,*args,**kwargs)
            receipt['result']=result
            return result
        except Exception as error:
            receipt['error']=str(error)
            raise
        finally:
            receipt.update(seconds=time.perf_counter()-start,observed_model_calls=len(calls)-before)
            receipt['model_runtime_requests']=runtime_calls[before_runtime:]
            with (OUT/'agent-trajectories.jsonl').open('a',encoding='utf-8') as handle:
                handle.write(json.dumps(receipt,ensure_ascii=False)+'\n')
    wb.run_auto_agent=run
    return create_app(wb)
