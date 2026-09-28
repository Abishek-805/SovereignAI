"""Import and Docker execution use one bounded, byte-preserving asset contract."""
import hashlib
import os
from io import BytesIO
from pathlib import Path

import pytest

from backend.contracts import WorkbenchError
from router.sandbox import CodeSandbox, MAX_INPUT_BYTES, MAX_INPUT_FILE_BYTES
from router.task_ledger import TaskLedger
from tests.test_coding_project import ProjectModel
from workflows.code_runtime import runner
from workflows.coding_workspace import CodingWorkspace


def test_execution_stages_large_mixed_project_assets_without_truncation(tmp_path, monkeypatch):
    samples={'assets/photo.png':b'\x89PNG\0'+b'p'*1_100_000,
             'images/nested/full.bin':b'x'*MAX_INPUT_FILE_BYTES,
             'vectors/diagram.svg':b'<svg xmlns="http://www.w3.org/2000/svg"/>'}
    calls=[]
    class Process:
        def __init__(self,args,**kwargs):
            calls.append(args)
            mount=args[args.index('--mount')+1]
            source=Path(mount.split('src=',1)[1].split(',dst=',1)[0])
            for name,expected in samples.items():assert (source/name).read_bytes()==expected
            assert (source/'program.py').read_text()=='print(1)'
            self.stdout=BytesIO(b'ok\n');self.stderr=BytesIO()
        def wait(self,timeout=None):return 0
    sandbox=CodeSandbox('docker','sha256:'+'a'*64,tmp_path/'runs','docker')
    monkeypatch.setattr(sandbox,'_ready',lambda:None)
    monkeypatch.setattr('router.sandbox.subprocess.Popen',Process)
    assert sandbox.execute('print(1)',input_files=samples).executed
    assert '--ulimit=fsize=33554432:33554432' in calls[0]
    assert samples['assets/photo.png'].endswith(b'p'*100)


@pytest.mark.parametrize('files,message', [
    ({'../escape.png':b'x'}, 'safe relative'),
    ({'program.py':b'x'}, 'reserved'),
    ({'photo.png':'text'}, 'bytes'),
    ({'big.png':b'x'*(MAX_INPUT_FILE_BYTES+1)}, '20 MiB'),
    (dict.fromkeys((str(index)+'.bin' for index in range(MAX_INPUT_BYTES//MAX_INPUT_FILE_BYTES+1)),
                   b'x'*MAX_INPUT_FILE_BYTES), '256 MiB'),
])
def test_asset_budget_failures_happen_before_starting_docker(tmp_path,monkeypatch,files,message):
    sandbox=CodeSandbox('docker','sha256:'+'a'*64,tmp_path/'runs','docker')
    monkeypatch.setattr(sandbox,'_ready',lambda:pytest.fail('Rejected input must not reach Docker'))
    with pytest.raises(WorkbenchError,match=message):sandbox.execute('print(1)',input_files=files)
    assert not (tmp_path/'runs').exists()


IMAGE=os.environ.get('SOVEREIGN_LIVE_SANDBOX_IMAGE')


@pytest.mark.skipif(not IMAGE,reason='Live Docker image ID not supplied')
def test_live_mixed_project_assets_survive_validation_execution_and_undo(tmp_path):
    workspace=CodingWorkspace(tmp_path/'data')
    ident=workspace.create('Suite owned mixed assets')['workspace_id']
    samples={'assets/photo.png':b'\x89PNG\0'+b'p'*1_100_000,
             'assets/full-size.bin':b'\0'+b'x'*(MAX_INPUT_FILE_BYTES-1),
             'vectors/diagram.svg':b'<svg xmlns="http://www.w3.org/2000/svg"/>'}
    for name,data in samples.items():workspace.import_bytes(ident,name,data)
    workspace.write(ident,'main.py','print("original")\n')
    expected={name:hashlib.sha256(data).hexdigest() for name,data in samples.items()}
    code=('from pathlib import Path\nimport hashlib\n'
          f'expected = {expected!r}\n'
          'for name, digest in expected.items():\n'
          '    assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == digest\n'
          '    try:\n'
          '        Path("/input", name).write_bytes(b"changed")\n'
          '    except OSError:\n'
          '        pass\n'
          '    else:\n'
          '        raise AssertionError("Input mount should be read-only")\n'
          'print("All mixed asset checksums match; original input is read-only.")\n')
    sandbox=CodeSandbox('docker',IMAGE,tmp_path/'runs')
    result=workspace.run_project(ident,'main.py','Update main.py to verify asset integrity',
        ProjectModel({'scope':'existing_files','operations':[{'action':'edit','path':'main.py','reason':'requested'}]},code),
        sandbox,TaskLedger(tmp_path/'data'))
    assert result['state']=='completed',result.get('stderr')
    actual=sandbox.execute(runner('main.py',mode='run'),input_files=workspace.raw_files(ident))
    assert actual.executed and actual.exit_code==0,actual.stderr
    assert 'All mixed asset checksums match' in actual.stdout
    workspace.undo(ident,result['task_id'])
    assert workspace.read(ident,'main.py')['content']=='print("original")\n'
    for name,data in samples.items():assert workspace.raw_files(ident)[name]==data
