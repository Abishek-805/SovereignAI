"""Literal file authority preserves path boundaries and sentence punctuation."""
import pytest
from backend.contracts import WorkbenchError
from router.task_ledger import TaskLedger
from workflows.coding_workspace import CodingWorkspace
from tests.test_coding_project import ProjectModel, Sandbox


def make_project(tmp_path):
    work=CodingWorkspace(tmp_path)
    wid=work.create('Literal scope')['workspace_id']
    work.write(wid,'solution.py','from legacy import value\n')
    work.write(wid,'legacy.py','def value():\n    return 0\n')
    return work,wid


@pytest.mark.parametrize('punctuation',['.','!','?',',',';',')'])
def test_sentence_punctuation_does_not_hide_explicit_second_file(tmp_path,punctuation):
    work,wid=make_project(tmp_path)
    model=ProjectModel({'scope':'existing_files','operations':[
        {'action':'edit','path':'solution.py','reason':'implementation'},
        {'action':'edit','path':'legacy.py','reason':'backward import'}]},
        'def value():\n    return 1\n','from solution import value\n')
    result=work.run_project(wid,'solution.py',
        'Refactor into solution.py and leave a backward-compatible import in legacy.py'+punctuation+' Preserve behavior.',
        model,Sandbox(),TaskLedger(tmp_path/'ledger'))
    assert result['state']=='completed'
    assert {item['path'] for item in result['changes']}=={'solution.py','legacy.py'}
    assert work.read(wid,'legacy.py')['content']=='def value():\n    return 0\n'


@pytest.mark.parametrize('mention',['legacy.py.backup','legacy.py/child','legacy.py\\child','legacy.py_name','legacy.py-extra','prefixlegacy.py','folder/legacy.py','folder\\legacy.py'])
def test_extended_path_does_not_authorize_basename_edit(tmp_path,mention):
    work,wid=make_project(tmp_path)
    model=ProjectModel({'scope':'existing_files','operations':[
        {'action':'edit','path':'solution.py','reason':'implementation'},
        {'action':'edit','path':'legacy.py','reason':'unauthorized basename'}]},
        'def value():\n    return 1\n','from solution import value\n')
    sandbox=Sandbox()
    with pytest.raises(WorkbenchError,match='outside the explicitly named targets'):
        work.run_project(wid,'solution.py','Refactor solution.py and update '+mention+'.',model,sandbox,TaskLedger(tmp_path/'ledger'))
    assert sandbox.snapshots==[]
    assert work.read(wid,'legacy.py')['content']=='def value():\n    return 0\n'
