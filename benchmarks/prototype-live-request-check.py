import sys,json,time,shutil,importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backend.settings import Settings
from backend.service import Workbench
from router.model_registry import ModelRegistry
spec=importlib.util.spec_from_file_location('baseline_harness',ROOT/'benchmarks/evaluate-smart-code-router.py');base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
settings=Settings(supervisor_seconds=300)
with base.LiveSuiteLock(ROOT/'data/smart-code-router-live.lock'),TemporaryDirectory(prefix='prototype-request-check-') as tmp:
    base.check_backend_idle(settings,'http://127.0.0.1:8765',[])
    isolated=Settings(data_dir=Path(tmp)/'data',project_dir=Path(tmp)/'projects',supervisor_seconds=300)
    isolated.data_dir.mkdir();shutil.copyfile(settings.data_dir/'sandbox-validation.json',isolated.data_dir/'sandbox-validation.json')
    work=Workbench(settings=isolated,registry=ModelRegistry(8087))
    wid=work.coding.create('selected-prototype-check')['workspace_id']
    history=['user: Create a Python folder for receipt parsing.','assistant: The previous request could not finish.']
    request='Create a text document in Knowledge explaining artificial intelligence, machine learning, and deep learning, including their relationship and examples. Name it ai_ml_dl_concepts.txt.'
    started=time.perf_counter();result=work.run_auto_agent(request,[],wid,history)
    docs=work.documents();contents=[]
    for doc in docs:
        p=work.sources_dir/(doc['active_hash']+doc['source_extension']);contents.append({'name':doc['display_name'],'text':p.read_text(encoding='utf-8-sig')})
    report={'request':request,'history':history,'latency_seconds':time.perf_counter()-started,'result':result,'created_documents':contents,'isolated':True}
    (ROOT/'benchmarks/prototype-document-live-final-20261003.json').write_text(json.dumps(report,indent=2,default=str),encoding='utf-8')
    print(json.dumps({'status':result.get('status'),'answer':result.get('answer'),'documents':[x['name'] for x in contents],'seconds':report['latency_seconds']},indent=2))

