"""Disposable browser acceptance server: never uses canonical user data."""
import tempfile
import time
import sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import uvicorn
from starlette.responses import JSONResponse
from backend.app import create_app
from backend.service import Workbench
from backend.settings import Settings
from rag.store import Store
from tests.test_service import TestEmbedder
from tests.test_answer import FakeModel

class SlowEmbedder(TestEmbedder):
    def encode(self, texts, query=False):
        time.sleep(.5)
        return super().encode(texts, query)

with tempfile.TemporaryDirectory(prefix='sovereign-import-browser-') as directory:
    root=Path(directory)
    model=FakeModel(); model.status=lambda: {'available': False, 'is_sleeping': True}
    service=Workbench(Settings(data_dir=root/'data', project_dir=root/'projects'),
                      Store(root/'index.sqlite'), SlowEmbedder(), model,
                      SimpleNamespace(acquire_lease=lambda capability: None))
    app=create_app(service)
    server=None
    @app.middleware('http')
    async def fixture_identity(request,call_next):
        if request.url.path=='/__audit_shutdown__' and request.method=='POST':
            server.should_exit=True
            response=JSONResponse({'stopping':True})
        else:
            response=await call_next(request)
        response.headers['x-sovereign-audit']='disposable'
        return response
    server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=8088,log_level='error'))
    server.run()
