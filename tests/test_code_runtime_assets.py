"""The generated runner must exclude only its wrapper, never project modules."""
import subprocess
import sys

from workflows.code_runtime import runner
import pytest
from backend.contracts import WorkbenchError


def test_browser_documents_require_preview_not_fake_execution():
    for name in ('index.html', 'INDEX.HTM', 'style.css'):
        with pytest.raises(WorkbenchError, match='Preview'):
            runner(name, mode='run')
        assert 'read_text' in runner(name, mode='check')


def test_runner_keeps_nested_program_dependency_but_excludes_root_wrapper(tmp_path):
    inputs=tmp_path/'input'
    outputs=tmp_path/'output'/'project'
    (inputs/'helpers').mkdir(parents=True)
    outputs.parent.mkdir(parents=True)
    (inputs/'program.py').write_text('raise AssertionError("sandbox wrapper must not be copied")\n')
    dependency=b'def result():\n    return 42\n'
    (inputs/'helpers'/'program.py').write_bytes(dependency)
    (inputs/'main.py').write_text('from helpers.program import result\nprint("Nested dependency:", result())\n')
    # Execute the actual runner locally against only test-owned paths. Docker's
    # mount/isolation contract has separate live coverage; no container is needed
    # to demonstrate that recursive copy preserves this package dependency.
    script=runner('main.py',mode='run')
    script=script.replace("'/input'",repr(str(inputs))).replace("'/output/project'",repr(str(outputs)))
    script=script.replace("['python', target]",f'[{sys.executable!r}, target]')
    completed=subprocess.run([sys.executable,'-I','-c',script],cwd=tmp_path,capture_output=True,text=True,timeout=15)
    assert completed.returncode==0,completed.stderr
    assert 'Nested dependency: 42' in completed.stdout
    assert not (outputs/'program.py').exists()
    assert (outputs/'helpers'/'program.py').read_bytes()==dependency


@pytest.mark.parametrize('name', ['main.cs','main.R','main.lua','main.pl','main.rb'])
def test_removed_heavy_or_optional_adapters_are_not_enabled(name):
    with pytest.raises(WorkbenchError,match='no local execution adapter'):
        runner(name,mode='run')


def test_unknown_language_is_not_falsely_enabled():
    with pytest.raises(WorkbenchError,match='no local execution adapter'):
        runner('main.kt',mode='run')
