"""Real Agent UI acceptance on isolated synthetic data; no production restart."""
from pathlib import Path
import os,json,time,hashlib,sys,importlib.util
import psutil

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'evidence/universal-report/20261009'


def app():
    mode=os.environ.get('SOVEREIGN_REPORT_TEST_ARM','after')
    names=['rag/tables.py','rag/identifiers.py','rag/grounding.py','rag/answer.py','backend/service.py']
    if mode=='before':
        for name in names:
            key=name[:-3].replace('/','.')
            spec=importlib.util.spec_from_file_location(key,OUT/'rollback'/name)
            module=importlib.util.module_from_spec(spec);sys.modules[key]=module;spec.loader.exec_module(module)
    from backend.app import create_app
    from backend.service import Workbench
    from backend.settings import Settings
    from backend.model import LocalModel
    run_id=str(time.time_ns());directory=OUT/mode;directory.mkdir(exist_ok=True)
    settings=Settings(data_dir=directory/'ui-data',context=16384,output_tokens=1024)
    model=LocalModel(verify_semantics=False)
    wb=Workbench(settings,model=model)
    fixtures=OUT/'fixtures';fixtures.mkdir(exist_ok=True)
    path=fixtures/'synthetic-measurements.csv'
    data='Key,Year,Phone,WAT 1,WAT 2,CAT 1,WAT 3\n24ALR056,2026,999,7,6,12.5,AB\n24ALR055,2025,123,20,10,5,\n'
    if not path.exists():path.write_text(data,encoding='utf-8')
    wb.import_file(path,display_name=path.name)
    if os.environ.get('SOVEREIGN_REPORT_DOC_PROBES')=='1':
        for filename,body in [('synthetic-procedure-v1.txt','Operating procedure revision 1. The calibration interval is 90 days. No reason for this interval is documented.'),
                              ('synthetic-procedure-v2.txt','Operating procedure revision 2. The calibration interval is 60 days. No reason for this interval is documented.')]:
            source=fixtures/filename
            if not source.exists():source.write_text(body,encoding='utf-8')
            wb.import_file(source,display_name=filename)
    from rag.tables import _load
    _load.cache_clear()
    (directory/'sources.json').write_text(json.dumps(wb.documents(),indent=2))
    snapshot=directory/run_id;snapshot.mkdir()
    for name in names+(['rag/analytics.py'] if mode=='after' else []):
        source=OUT/'rollback'/name if mode=='before' else ROOT/name
        target=snapshot/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(source.read_bytes())
    (snapshot/'runtime.json').write_text(json.dumps({'arm':mode,'run_id':run_id,'python':sys.version,'executable':sys.executable,
        'source_hashes':{name:hashlib.sha256((snapshot/name).read_bytes()).hexdigest() for name in names}},indent=2))
    calls=[];original=model._request
    def request(method,path,**kwargs):
        start=time.perf_counter();receipt={'method':method,'path':path}
        try:
            response=original(method,path,**kwargs)
            if path=='/v1/chat/completions':
                receipt['usage']=response.get('usage',{})
                receipt['public_messages']=[{key:choice.get('message',{}).get(key) for key in ['role','content','tool_calls']} for choice in response.get('choices',[])]
            return response
        except Exception as exc:
            receipt['error']=str(exc);raise
        finally:
            receipt['seconds']=time.perf_counter()-start;calls.append(receipt)
    model._request=request
    assess=model.assess_evidence
    def assessment(question,draft,sources,history=None):
        result=assess(question,draft,sources,history)
        with (directory/'grounding-trajectories.jsonl').open('a',encoding='utf-8') as handle:
            handle.write(json.dumps({'question':question,'draft':draft,'sources':sources,'assessment':result,'run_id':run_id},ensure_ascii=False)+'\n')
        return result
    model.assess_evidence=assessment
    execute=wb.run_auto_agent
    def agent(goal,*args,**kwargs):
        start=time.perf_counter();index=len(calls);process=psutil.Process()
        receipt={'question':goal,'arm':mode,'run_id':run_id,'rss_before':process.memory_info().rss,
                 'reader_cache_before':_load.cache_info()._asdict(),
                 'history':args[2] if len(args)>2 else kwargs.get('history'), 'evidence_ids':kwargs.get('evidence_ids')}
        try:
            result=execute(goal,*args,**kwargs);receipt['result']=result;return result
        except Exception as exc:
            receipt['error']=str(exc);receipt['error_code']=getattr(exc,'code',None);raise
        finally:
            receipt.update(seconds=time.perf_counter()-start,rss_after=process.memory_info().rss,model_requests=calls[index:],reader_cache_after=_load.cache_info()._asdict())
            with (directory/'trajectories.jsonl').open('a',encoding='utf-8') as handle:handle.write(json.dumps(receipt,ensure_ascii=False)+'\n')
    wb.run_auto_agent=agent
    result=create_app(wb)
    staging=OUT/'frontend-dist'
    if staging.exists():
        from fastapi.staticfiles import StaticFiles
        result.router.routes[-1].app=StaticFiles(directory=str(staging),html=True)
    return result
