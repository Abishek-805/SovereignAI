import pytest

from backend.contracts import WorkbenchError
from router.sandbox import SandboxResult
from router.task_ledger import TaskLedger
from workflows.coding_workspace import CodingWorkspace


class Model:
    def __init__(self, *codes):
        self.codes = iter(codes)

    def complete_code(self, messages, max_tokens=1024):
        return {'code': next(self.codes)}


class Sandbox:
    def _ready(self):
        pass

    def execute(self, code, input_files):
        assert "unittest" in code
        assert 'test_solution.py' in input_files
        good = b'return a + b' in input_files['solution.py']
        return SandboxResult(0 if good else 1, '', '1 test failed' if not good else '1 test passed',
                             True, {'result.csv': b'answer\n5\n'} if good else {})


def workspace(tmp_path):
    work = CodingWorkspace(tmp_path)
    created = work.create('Small Python task')
    workspace_id = created['workspace_id']
    work.write(workspace_id, 'solution.py', 'def add(a, b):\n    return 0\n')
    work.write(workspace_id, 'test_solution.py', 'import unittest\n')
    return work, workspace_id


def test_delete_project_removes_only_selected_workspace(tmp_path):
    projects=tmp_path/'Projects'
    work=CodingWorkspace(tmp_path/'data',projects)
    first=work.create('Delete me')['workspace_id']
    second=work.create('Keep me')['workspace_id']
    first_path=work.files_directory(first)
    second_path=work.files_directory(second)
    work.write(first,'nature.txt','nature')
    work.write(second,'keep.txt','keep')
    result=work.delete(first)
    assert result['workspace_id']==first
    assert not first_path.exists()
    assert not (work.root/first).exists()
    assert second_path.is_dir()
    assert work.read(second,'keep.txt')['content']=='keep'
    with pytest.raises(WorkbenchError):work.delete(first)


def test_workspace_file_boundary_and_roundtrip(tmp_path):
    work, workspace_id = workspace(tmp_path)
    assert work.read(workspace_id, 'solution.py')['content'].endswith('return 0\n')
    assert [item['name'] for item in work.get(workspace_id)['files']] == ['solution.py', 'test_solution.py']
    for name in ('../secret.py', 'C:\\secret.py', '/tmp/secret.py', '%HOME%.py', 'program.py'):
        with pytest.raises(WorkbenchError):
            work.write(workspace_id, name, 'x')
    with pytest.raises(WorkbenchError):
        work.write(workspace_id, 'large.py', 'x' * (2*1024*1024+1))


def test_workspace_file_context_actions(tmp_path):
    work, workspace_id = workspace(tmp_path)
    original = work.read(workspace_id, 'solution.py')['content']
    copied = work.file_operation(workspace_id, 'copy', 'solution.py', 'src/solution copy.py')
    assert any(item['name'] == 'src/solution copy.py' for item in copied['workspace']['files'])
    assert work.read(workspace_id, 'src/solution copy.py')['content'] == original
    moved = work.file_operation(workspace_id, 'move', 'src/solution copy.py', 'renamed.py')
    assert any(item['name'] == 'renamed.py' for item in moved['workspace']['files'])
    with pytest.raises(WorkbenchError):
        work.read(workspace_id, 'src/solution copy.py')
    with pytest.raises(WorkbenchError):
        work.file_operation(workspace_id, 'copy', 'solution.py', 'renamed.py')
    with pytest.raises(WorkbenchError):
        work.file_operation(workspace_id, 'move', 'solution.py', '../escape.py')
    work.file_operation(workspace_id, 'delete', 'renamed.py')
    with pytest.raises(WorkbenchError):
        work.read(workspace_id, 'renamed.py')
    assert work.read(workspace_id, 'solution.py')['content'] == original


def test_workspace_folder_context_actions(tmp_path):
    work, workspace_id = workspace(tmp_path)
    created = work.file_operation(workspace_id, 'mkdir', 'src/components')
    assert 'src/components' in created['workspace']['folders']
    work.write(workspace_id, 'src/components/button.py', 'print("ok")')
    copied = work.file_operation(workspace_id, 'copy', 'src', 'src copy')
    assert work.read(workspace_id, 'src copy/components/button.py')['content'] == 'print("ok")'
    assert 'src copy/components' in copied['workspace']['folders']
    with pytest.raises(WorkbenchError):
        work.file_operation(workspace_id, 'move', 'src', 'src/nested')
    work.file_operation(workspace_id, 'move', 'src', 'renamed')
    assert work.read(workspace_id, 'renamed/components/button.py')['content'] == 'print("ok")'
    work.file_operation(workspace_id, 'delete', 'renamed')
    with pytest.raises(WorkbenchError):
        work.read(workspace_id, 'renamed/components/button.py')
    assert work.read(workspace_id, 'src copy/components/button.py')['content'] == 'print("ok")'


def test_symlink_escape_is_rejected_when_supported(tmp_path):
    work, workspace_id = workspace(tmp_path)
    try:
        (work.root / workspace_id / 'files' / 'link.py').symlink_to(tmp_path / 'outside.py')
    except OSError as exc:
        if getattr(exc, 'winerror', None) != 1314:
            raise
        pytest.skip('This Windows session lacks the symlink privilege')
    with pytest.raises(WorkbenchError):
        work.read(workspace_id, 'link.py')


def test_repair_tests_diff_and_commit(tmp_path):
    work, workspace_id = workspace(tmp_path)
    ledger = TaskLedger(tmp_path)
    result = work.run(workspace_id, 'solution.py', 'Fix add', Model(
        'def add(a, b):\n    return 0\n',
        'def add(a, b):\n    return a + b\n'
    ), Sandbox(), ledger)
    assert result['state'] == 'completed'
    assert result['attempts'] == 2
    assert [event['event'] for event in result['events']].count('test_failed') == 1
    assert '+    return a + b' in result['diff']
    assert work.read(workspace_id, 'solution.py')['content'].endswith('return 0\n')
    work.accept(workspace_id,result['task_id'])
    assert work.read(workspace_id, 'solution.py')['content'].endswith('return a + b\n')
    assert work.result(workspace_id, result['task_id'])['checks']['tests_passed']
    assert result['output_files'][0]['name'] == 'result.csv'
    artifact = work.artifact(workspace_id, result['task_id'], 'result.csv')
    assert artifact.read_bytes() == b'answer\n5\n'
    artifact.write_bytes(b'tampered')
    with pytest.raises(WorkbenchError):
        work.artifact(workspace_id, result['task_id'], 'result.csv')
    assert ledger.read(result['task_id'])['state'] == 'completed'


def test_failed_tests_do_not_commit(tmp_path):
    work, workspace_id = workspace(tmp_path)
    result = work.run(workspace_id, 'solution.py', 'Fix add', Model(*(
        'def add(a, b):\n    return 0\n' for _ in range(3)
    )), Sandbox(), TaskLedger(tmp_path))
    assert result['state'] == 'failed' and result['attempts'] == 3
    assert result['checks']['target_committed'] is False
    assert work.read(workspace_id, 'solution.py')['content'].endswith('return 0\n')


def test_error_repair_runs_file_and_can_be_undone(tmp_path):
    work=CodingWorkspace(tmp_path)
    wid=work.create('Broken program')['workspace_id']
    work.write(wid,'broken.py','print(sales)\n')
    class RuntimeSandbox:
        def _ready(self): pass
        def execute(self,code,input_files):
            assert '"run"' in code
            failing=input_files['broken.py']!=b'print(42)\n'
            return SandboxResult(1 if failing else 0,'42\n' if not failing else '',
                                 'NameError: sales is not defined' if failing else '',True)
    result=work.run(wid,'broken.py','Solve the runtime error',Model('print(sales)\n','print(42)\n'),RuntimeSandbox(),TaskLedger(tmp_path))
    assert result['state']=='completed' and result['validation']=='runtime_check'
    assert result['checks']['runtime_passed'] and '+print(42)' in result['diff']
    work.accept(wid,result['task_id'])
    assert work.undo(wid,result['task_id'])['state']=='undone'
    assert work.read(wid,'broken.py')['content']=='print(sales)\n'


def test_undo_does_not_overwrite_later_edits(tmp_path):
    work,wid=workspace(tmp_path)
    result=work.run(wid,'solution.py','Fix add',Model('def add(a, b):\n    return a + b\n'),Sandbox(),TaskLedger(tmp_path))
    work.accept(wid,result['task_id'])
    work.write(wid,'solution.py','def add(a, b):\n    return 99\n')
    with pytest.raises(WorkbenchError) as error:
        work.undo(wid,result['task_id'])
    assert error.value.code=='workspace_conflict'


def test_unchanged_candidate_is_not_reported_as_applied(tmp_path):
    work=CodingWorkspace(tmp_path)
    wid=work.create('No change')['workspace_id']
    work.write(wid,'main.js','console.log(1)')
    class CheckSandbox:
        def _ready(self): pass
        def execute(self,code,input_files): return SandboxResult(0,'Check passed','',True)
    result=work.run(wid,'main.js','Improve the output',Model(*(['console.log(1)']*3)),CheckSandbox(),TaskLedger(tmp_path))
    assert result['state']=='failed' and not result['checks']['target_committed']
    assert work.read(wid,'main.js')['content']=='console.log(1)'


def test_comment_only_candidate_cannot_pass_container_stub_and_stage(tmp_path):
    work = CodingWorkspace(tmp_path)
    wid = work.create('Web')['workspace_id']
    work.write(wid, 'index.html', '<p>Original</p>')
    class PassingSandbox:
        def _ready(self): pass
        def execute(self, code, input_files):
            return SandboxResult(0, 'syntax checked', '', True)
    result = work.run(wid, 'index.html', 'Improve this page',
                      Model(*(['<!-- implementation later -->'] * 3)),
                      PassingSandbox(), TaskLedger(tmp_path))
    assert result['state'] == 'failed'
    assert result['attempts'] == 3
    assert 'markup' in result['stderr']
    assert not result.get('staged_files')
    assert work.read(wid, 'index.html')['content'] == '<p>Original</p>'
    with pytest.raises(WorkbenchError):
        work.accept(wid, result['task_id'])


def test_single_file_regenerates_missing_source_before_staging(tmp_path):
    work = CodingWorkspace(tmp_path)
    wid = work.create('Web')['workspace_id']
    work.write(wid, 'style.css', 'p { color: red; }')
    class PassingSandbox:
        def _ready(self): pass
        def execute(self, code, input_files):
            return SandboxResult(0, '', '', True)
    result = work.run(wid, 'style.css', 'Make the text blue',
                      Model('/* styles later */', 'p { color: blue; }'),
                      PassingSandbox(), TaskLedger(tmp_path))
    assert result['state'] == 'completed' and result['attempts'] == 2
    assert work.read(wid, 'style.css')['content'] == 'p { color: red; }'


@pytest.mark.parametrize('instruction,original,candidate', [
    ('Replace style.css with a comment-only file', 'p { color: red; }', '/* intentionally disabled */'),
    ('Make style.css an empty file', 'p { color: red; }', ''),
    ('Update the comment', '/* old explanation */', '/* new explanation */')])
def test_single_file_explicit_non_source_edits_remain_allowed(tmp_path, instruction, original, candidate):
    work = CodingWorkspace(tmp_path)
    wid = work.create('Styles')['workspace_id']
    work.write(wid, 'style.css', original)
    class PassingSandbox:
        def _ready(self): pass
        def execute(self, code, input_files): return SandboxResult(0, '', '', True)
    result = work.run(wid, 'style.css', instruction, Model(candidate), PassingSandbox(), TaskLedger(tmp_path))
    assert result['state'] == 'completed'
    assert result['changes'][0]['after'] == candidate


def test_requires_sandbox(tmp_path):
    work = CodingWorkspace(tmp_path)
    workspace_id = work.create('No tests')['workspace_id']
    work.write(workspace_id, 'solution.py', 'pass')
    work.write(workspace_id, 'test_solution.py', 'import unittest')
    class Unavailable(Sandbox):
        def _ready(self):
            raise WorkbenchError('sandbox_unavailable', 'Docker stopped')
    with pytest.raises(WorkbenchError) as error:
        work.run(workspace_id, 'solution.py', 'Fix it', Model('pass'), Unavailable(), TaskLedger(tmp_path))
    assert error.value.code == 'sandbox_unavailable'
    assert not list((work.root / workspace_id / 'tasks').iterdir())


def test_concurrent_file_change_is_not_overwritten(tmp_path):
    work, workspace_id = workspace(tmp_path)
    class ChangedDuringTest(Sandbox):
        def execute(self, code, input_files):
            work.write(workspace_id, 'solution.py', 'def add(a, b):\n    return 99\n')
            return SandboxResult(0, '', 'test passed', True)
    with pytest.raises(WorkbenchError) as error:
        work.run(workspace_id, 'solution.py', 'Fix add', Model(
            'def add(a, b):\n    return a + b\n'
        ), ChangedDuringTest(), TaskLedger(tmp_path))
    assert error.value.code == 'workspace_conflict'
    assert work.read(workspace_id, 'solution.py')['content'].endswith('return 99\n')


def test_nested_text_files_and_validation_without_tests(tmp_path):
    work=CodingWorkspace(tmp_path)
    wid=work.create('JavaScript project')['workspace_id']
    work.write(wid,'src/main.js','console.log(1)')
    work.write(wid,'README.md','x'*20000)
    assert work.read(wid,'src/main.js')['content']=='console.log(1)'
    for name in ['src/../../escape.js','src/CON.txt','a//b.js','src/../b.js']:
        with pytest.raises(WorkbenchError): work.write(wid,name,'bad')
    class CheckSandbox:
        def _ready(self): pass
        def execute(self,code,input_files):
            assert "node" in code and "--check" in code
            assert input_files['src/main.js']==b'console.log(42)'
            return SandboxResult(0,'Check passed','',True)
    result=work.run(wid,'src/main.js','Print 42',Model('console.log(42)'),CheckSandbox(),TaskLedger(tmp_path))
    assert result['checks']['syntax_or_format_checked']
    assert 'tests_passed' not in result['checks']
    assert result['validation']=='syntax_or_format_check'
    assert work.read(wid,'src/main.js')['content']=='console.log(1)'
    work.accept(wid,result['task_id'])
    assert work.read(wid,'src/main.js')['content']=='console.log(42)'


def test_cancel_during_generation_preserves_original(tmp_path):
    import threading
    work,wid=workspace(tmp_path);cancel=threading.Event()
    class CancelModel:
        def complete_code(self,*args,**kwargs):
            cancel.set();return {'code':'def add(a,b): return a+b'}
    with pytest.raises(WorkbenchError) as error:
        work.run(wid,'solution.py','Fix add',CancelModel(),Sandbox(),TaskLedger(tmp_path),cancel=cancel)
    assert error.value.code=='cancelled'
    assert work.read(wid,'solution.py')['content'].endswith('return 0\n')


def test_review_diff_separates_changes_without_final_newlines(tmp_path):
    work, workspace_id = workspace(tmp_path)
    work.write(workspace_id, 'solution.py', 'def add(a, b):\n    return 0')
    result = work.run(workspace_id, 'solution.py', 'Fix add',
                      Model('def add(a, b):\n    return a + b'), Sandbox(), TaskLedger(tmp_path))
    assert result['state'] == 'completed'
    assert '-    return 0\n\\ No newline at end of file\n+    return a + b' in result['diff']
    assert work.read(workspace_id, 'solution.py')['content'].endswith('return 0')
