import json
from types import SimpleNamespace
import pytest
from backend.contracts import WorkbenchError
from workflows.web_preview import preview_request


class Coding:
    def read(self, wid, target):return {'content':'from flask import Flask'}
    def raw_files(self, wid):return {'app.py':b'from flask import Flask\napp=Flask(__name__)'}


def test_preview_runs_only_inside_sandbox_and_retains_separate_database(tmp_path):
    snapshots=[]
    def execute(script,timeout,input_files):
        compile(script,'docker-wrapper','exec')
        snapshots.append(input_files)
        return SimpleNamespace(exit_code=0,output_files={
            'web-response.json':json.dumps({'status':200,'body':'ok','content_type':'text/html'}).encode(),
            'preview-state.db':b'isolated-db'},stderr='')
    sandbox=SimpleNamespace(execute=execute)
    for _ in range(2):
        assert preview_request(Coding(),sandbox,tmp_path,'workspace','app.py')['status']==200
    assert '__preview_state__.db' not in snapshots[0]
    assert snapshots[1]['__preview_state__.db']==b'isolated-db'


@pytest.mark.parametrize('path',['https://example.com','//example.com','x'])
def test_preview_rejects_external_request_paths(tmp_path,path):
    with pytest.raises(WorkbenchError,match='application-relative'):
        preview_request(Coding(),None,tmp_path,'workspace','app.py',path)


def test_preview_surfaces_docker_failure(tmp_path):
    sandbox=SimpleNamespace(execute=lambda *a,**k:SimpleNamespace(exit_code=1,stderr='actual import failure'))
    with pytest.raises(WorkbenchError,match='actual import failure'):
        preview_request(Coding(),sandbox,tmp_path,'workspace','app.py')
