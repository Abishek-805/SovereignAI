"""Real byte-preserving project import, asset isolation, and API boundary regressions."""
import hashlib
from pathlib import Path

import pytest

from backend.contracts import WorkbenchError
from router.task_ledger import TaskLedger
from router.sandbox import SandboxResult
from tests.test_api import client_for, service
from tests.test_coding_project import ProjectModel, Sandbox
from workflows.coding_workspace import CodingWorkspace, MAX_IMPORT_BYTES, MAX_EDITOR_BYTES


def test_mixed_import_preserves_exact_host_bytes_and_survives_reopen(tmp_path):
    work=CodingWorkspace(tmp_path/'data',tmp_path/'Documents'/'SovereignAI'/'Projects')
    ident=work.create('Mixed import')['workspace_id']
    samples={'src/index.ts':b'export const n = 1;\r\n',
             'assets/photo.jpg':b'\xff\xd8\xff\0'+bytes(range(256))*1200,
             'assets/config.svg':b'<svg xmlns="http://www.w3.org/2000/svg"/>',
             'notes/data.pdf':b'%PDF-1.7\n\0binary\xff',
             'README.md':b'# Project\n'}
    for name,data in samples.items():
        result=work.import_bytes(ident,name,data)
        assert result['sha256']==hashlib.sha256(data).hexdigest()
        assert (Path(work.get(ident)['host_path'])/name).read_bytes()==data
    reopened=CodingWorkspace(tmp_path/'data',tmp_path/'Documents'/'SovereignAI'/'Projects')
    assert reopened.raw_files(ident)==samples
    image=work.read(ident,'assets/photo.jpg')
    assert image['binary'] and not image['editable'] and image['content']==''
    assert work.read(ident,'assets/config.svg')['editable']
    work.file_operation(ident,'copy','assets/photo.jpg','assets/copied.jpg')
    work.file_operation(ident,'move','assets/copied.jpg','images/copied.jpg')
    assert work.raw_files(ident)['images/copied.jpg']==samples['assets/photo.jpg']
    with pytest.raises(WorkbenchError,match='cannot be overwritten'):
        work.write(ident,'assets/photo.jpg','')


def test_import_collision_traversal_size_and_editor_bounds(tmp_path):
    work=CodingWorkspace(tmp_path)
    ident=work.create('Limits')['workspace_id']
    work.import_bytes(ident,'data.bin',b'\0original')
    with pytest.raises(WorkbenchError,match='never overwrite'):
        work.import_bytes(ident,'data.bin',b'other')
    assert work.raw_files(ident)['data.bin']==b'\0original'
    for name in ('../outside.jpg','/outside.jpg','C:/outside.jpg','program.py'):
        with pytest.raises(WorkbenchError):work.import_bytes(ident,name,b'data')
    with pytest.raises(WorkbenchError,match='20 MiB'):
        work.import_bytes(ident,'too-big.bin',b'x'*(MAX_IMPORT_BYTES+1))
    work.import_bytes(ident,'large.txt',b'a'*200_000)
    assert len(work.read(ident,'large.txt')['content'])==200_000
    work.write(ident,'large.txt','b'*200_000)
    work.import_bytes(ident,'huge.txt',b'a'*(MAX_EDITOR_BYTES+1))
    assert not work.read(ident,'huge.txt')['editable']
    with pytest.raises(WorkbenchError):work.write(ident,'huge.txt','')


def test_project_edit_preserves_assets_in_validation_and_rejects_asset_edits(tmp_path):
    work=CodingWorkspace(tmp_path)
    ident=work.create('Assets plus code')['workspace_id']
    work.write(ident,'main.py','print(1)\n')
    asset=b'\xff\xd8\0exact asset'
    work.import_bytes(ident,'assets/photo.jpg',asset)
    sandbox=Sandbox()
    model=ProjectModel([{'action':'edit','path':'main.py','reason':'change output'}],'print(2)\n')
    result=work.run_project(ident,'main.py','Change output in main.py',model,sandbox,TaskLedger(tmp_path))
    assert result['state']=='completed'
    assert 'Read-only project asset' in model.tree[0]['assets/photo.jpg']
    assert sandbox.snapshots[0]['assets/photo.jpg']==asset
    assert work.raw_files(ident)['assets/photo.jpg']==asset
    bad=ProjectModel([{'action':'create','path':'assets/photo.jpg','reason':'replace asset'}],'x')
    with pytest.raises(WorkbenchError,match='cannot be changed'):
        work.run_project(ident,'main.py','Create a replacement',bad,Sandbox(),TaskLedger(tmp_path))
    assert work.raw_files(ident)['assets/photo.jpg']==asset


def test_raw_import_api_download_and_error_contract(service):
    with client_for(service) as client:
        ident=client.post('/coding/workspaces',json={'name':'Asset API fixture'}).json()['workspace_id']
        data=b'\xff\xd8\0'+b'a'*150_000
        response=client.post(f'/coding/workspaces/{ident}/import-files/assets/photo.jpg',content=data,
                             headers={'Content-Type':'application/octet-stream'})
        assert response.status_code==200,response.text
        assert response.json()['bytes']==len(data)
        asset=client.get(f'/coding/workspaces/{ident}/assets/assets/photo.jpg')
        assert asset.content==data
        assert 'attachment' in asset.headers['content-disposition']
        assert asset.headers['x-content-type-options']=='nosniff'
        assert client.get(f'/coding/workspaces/{ident}/files/assets/photo.jpg').json()['binary']
        assert client.post(f'/coding/workspaces/{ident}/import-files/assets/photo.jpg',content=b'overwrite').status_code==409
        assert client.put(f'/coding/workspaces/{ident}/files/src/large.txt',json={'content':'a'*200_000}).status_code==200
        assert client.post(f'/coding/workspaces/{ident}/import-files/big.bin',content=b'a'*(MAX_IMPORT_BYTES+1)).status_code==413
        hostile=client.post(f'/coding/workspaces/{ident}/import-files/new.txt',content=b'data',headers={'Origin':'https://evil.example'})
        assert hostile.status_code==403


def test_run_and_terminal_receive_exact_binary_assets(service):
    ident=service.coding.create('Binary execution fixture')['workspace_id']
    service.coding.import_bytes(ident,'main.py',b'print("hello")\r\n')
    data=b'\xff\xd8\0preserve'
    service.coding.import_bytes(ident,'assets/photo.jpg',data)
    snapshots=[]
    class Runtime:
        def execute(self,code,timeout,input_files):
            snapshots.append(input_files)
            return SandboxResult(0,'hello','',True,
                {'project-sync.json':b'{"changed":{},"deleted":[]}'} if 'project-sync.json' in code else {})
    service._verified_coding_sandbox=lambda:Runtime()
    assert service.execute_coding_file(ident,'main.py')['state']=='completed'
    class Job:
        cancel=None
        input=None
        def append(self,*args):pass
        def progress(self,*args):pass
    assert service.execute_terminal(ident,'ls',Job())['state']=='completed'
    assert len(snapshots)==2
    for snapshot in snapshots:
        assert snapshot['assets/photo.jpg']==data
        assert snapshot['main.py']==b'print("hello")\r\n'
    assert service.coding.raw_files(ident)==snapshots[0]
