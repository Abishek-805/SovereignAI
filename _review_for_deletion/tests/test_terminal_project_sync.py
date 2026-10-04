import base64
import json
from types import SimpleNamespace

import pytest

from backend.contracts import WorkbenchError
from backend.jobs import Job
from tests.test_service import service


def encoded(data):
    return base64.b64encode(data).decode('ascii')


def test_terminal_delta_preserves_assets_and_nested_files(service):
    workspace = service.coding.create('Terminal fixture')['workspace_id']
    service.coding.write(workspace, 'old.py', 'print(1)')
    service.coding.import_bytes(workspace, 'assets/image.png', b'\x89PNG\x00asset')
    service.coding.write(workspace, 'nested/program.py', 'print(2)')
    original = service.coding.raw_files(workspace)
    result = service.coding.apply_terminal_changes(workspace, original,
        {'changed': {'new/output.txt': encoded(b'result'), 'old.py': encoded(b'print(3)')}, 'deleted': []})
    assert result['changed_files'] == ['new/output.txt', 'old.py']
    assert service.coding.raw_files(workspace) == {**original, 'new/output.txt': b'result', 'old.py': b'print(3)'}


@pytest.mark.parametrize('manifest', [
    {'changed': {'../outside.txt': encoded(b'bad')}, 'deleted': []},
    {'changed': {'valid.txt': encoded(b'valid')}, 'deleted': ['missing.py']},
    {'changed': {'valid.txt': 'invalid base64'}, 'deleted': []},
])
def test_invalid_terminal_delta_never_writes(service, manifest):
    workspace = service.coding.create('Terminal validation')['workspace_id']
    service.coding.write(workspace, 'old.py', 'print(1)')
    original = service.coding.raw_files(workspace)
    with pytest.raises(WorkbenchError):
        service.coding.apply_terminal_changes(workspace, original, manifest)
    assert service.coding.raw_files(workspace) == original


def test_terminal_delta_rejects_concurrent_host_edit(service):
    workspace = service.coding.create('Terminal revision')['workspace_id']
    service.coding.write(workspace, 'old.py', 'print(1)')
    original = service.coding.raw_files(workspace)
    service.coding.write(workspace, 'old.py', 'user edit')
    with pytest.raises(WorkbenchError, match='Project changed'):
        service.coding.apply_terminal_changes(workspace, original,
            {'changed': {'new.py': encoded(b'generated')}, 'deleted': ['old.py']})
    assert service.coding.raw_files(workspace) == {'old.py': b'user edit'}


@pytest.mark.parametrize('exit_code', [0, 1])
def test_terminal_applies_only_successful_manifest(service, monkeypatch, exit_code):
    workspace = service.coding.create('Terminal integration')['workspace_id']
    service.coding.write(workspace, 'old.py', 'print(1)')
    def execute(script, **kwargs):
        compile(script, '<terminal-wrapper>', 'exec')
        assert "Path(directory)==source" in script
        return SimpleNamespace(exit_code=exit_code, stdout='output', stderr='',
            output_files={'project-sync.json': json.dumps({'changed': {'new.py': encoded(b'print(2)')}, 'deleted': ['old.py']}).encode()})
    monkeypatch.setattr(service, '_verified_coding_sandbox', lambda: SimpleNamespace(execute=execute))
    result = service.execute_terminal(workspace, 'python task.py', Job('terminal'))
    assert result['state'] == ('completed' if exit_code == 0 else 'failed')
    assert service.coding.raw_files(workspace) == ({'new.py': b'print(2)'} if exit_code == 0 else {'old.py': b'print(1)'})


def test_project_inspection_skips_binary_assets_and_keeps_source(service):
    workspace = service.coding.create('Inspection assets')['workspace_id']
    for index in range(9):
        service.coding.import_bytes(workspace, f'a{index}.png', b'\x89PNG\x00asset')
    service.coding.write(workspace, 'source.py', 'print("real source")')
    service.model.plan_task = lambda *_: {'action': 'inspect_code', 'response': ''}
    seen = []
    def answer(instruction, **kwargs):
        seen.extend(kwargs['files'])
        return 'Source explanation'
    service.model.conversation_answer = answer
    result = service.run_coding_project_task(workspace, '', 'Explain the project')
    assert result['state'] == 'answered'
    assert [item['name'] for item in seen] == ['source.py']
    assert seen[0]['source_excerpt'] == 'print("real source")'
