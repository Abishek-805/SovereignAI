"""Read an authorized workbook and exercise the real model on a disposable index."""
import sys,json,tempfile,time
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.model import LocalModel
from backend.service import Workbench
from backend.settings import Settings
from rag.store import Store

import argparse
parser=argparse.ArgumentParser();parser.add_argument("source");parser.add_argument("questions",nargs="*");parser.add_argument("--display-name");args=parser.parse_args()
source=Path(args.source)
with tempfile.TemporaryDirectory(prefix='sovereign-table-query-') as directory:
    root=Path(directory); model=LocalModel()
    service=Workbench(Settings(data_dir=root,project_dir=root/'projects'),Store(root/'index.sqlite'),
        model=model,registry=SimpleNamespace(acquire_lease=lambda route:None))
    started=time.perf_counter(); doc=service.import_file(source,display_name=args.display_name or source.name)
    print(json.dumps({'import_seconds':round(time.perf_counter()-started,3)},ensure_ascii=False),flush=True)
    questions=args.questions or ['How many students passed in CAT 1 of PST?',
               'What is the mark of 24ALR001 in CAT 1 of PST?']
    for question in questions:
        started=time.perf_counter()
        drafts=[]; complete=model.complete
        def capture(messages,max_tokens):
            response=complete(messages,max_tokens); drafts.append(response.get('result')); return response
        model.complete=capture
        result=service.ask(question,[doc['document_id']],force_documents=True)
        model.complete=complete
        print(json.dumps({'question':question,'status':result['status'],'answer':result['answer'],
            'query':result.get('table_query'),'checks':result.get('checks'),'drafts':drafts,'seconds':round(time.perf_counter()-started,3)},ensure_ascii=False),flush=True)
    model.close()
