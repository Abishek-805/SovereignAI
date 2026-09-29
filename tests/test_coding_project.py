import pytest

from backend.contracts import WorkbenchError
from router.sandbox import SandboxResult
from router.task_ledger import TaskLedger
from workflows.coding_workspace import CodingWorkspace


class ProjectModel:
    def __init__(self, operations, *codes):
        self.operations=operations
        self.codes=iter(codes)
        self.tree=None

    def plan_workspace_edit(self, instruction, files, folders, current_file):
        self.tree=(files,folders,current_file)
        return self.operations

    def complete_code(self, messages, max_tokens=3072):
        return {'code':next(self.codes)}


class Sandbox:
    image_id='sha256:'+'a'*64

    def __init__(self, exit_code=0):
        self.exit_code=exit_code
        self.snapshots=[]

    def _ready(self):
        pass

    def execute(self, code, input_files):
        self.snapshots.append(input_files.copy())
        return SandboxResult(self.exit_code,'checked','',True)


def test_project_task_creates_folder_and_file_without_editing_current_tab(tmp_path):
    work=CodingWorkspace(tmp_path)
    workspace_id=work.create('Project')['workspace_id']
    work.write(workspace_id,'current.py','print("keep")\n')
    model=ProjectModel([{'action':'mkdir','path':'tools','reason':'group utilities'},
                        {'action':'create','path':'tools/add.py','reason':'new requested file'}],
                       'def add(a, b):\n    return a + b\n')
    sandbox=Sandbox()
    task=work.run_project(workspace_id,'current.py','Create an addition utility in tools/add.py',model,sandbox,TaskLedger(tmp_path))
    assert task['state']=='completed'
    assert [change['path'] for change in task['changes']]==['tools','tools/add.py']
    assert work.read(workspace_id,'current.py')['content']=='print("keep")\n'
    assert work.read(workspace_id,'tools/add.py')['content'].startswith('def add')
    assert sandbox.snapshots[0]['tools/add.py'].startswith(b'def add')
    assert 'current.py' in model.tree[0]
    work.undo(workspace_id,task['task_id'])
    assert 'tools' not in work.get(workspace_id)['folders']
    assert [item['name'] for item in work.get(workspace_id)['files']]==['current.py']


def test_new_html_css_project_saves_files_without_docker(tmp_path):
    work=CodingWorkspace(tmp_path)
    workspace_id=work.create('Web project')['workspace_id']
    model=ProjectModel([], 'project_folder\\index.html\n\n<!doctype html><html><head></head><body><h1>Hello</h1></body></html>\n',
                       'project_folder\\style.css\n\nh1 { color: teal; }\n')
    result=work.run_project(workspace_id,'',
        'Create a project folder with a simple HTML page and CSS in it',
        model,None,TaskLedger(tmp_path))
    assert result['state']=='completed'
    assert result['validation']=='not run; Docker unavailable'
    assert result['checks']['container_executed'] is False
    assert {item['name'] for item in work.get(workspace_id)['files']}=={'index.html','style.css'}
    assert 'style.css' in work.read(workspace_id,'index.html')['content']
    assert work.read(workspace_id,'index.html')['content'].startswith('<!doctype html>')
    assert work.read(workspace_id,'style.css')['content'].startswith('h1 {')
    work.undo(workspace_id,result['task_id'])
    assert work.get(workspace_id)['files']==[]


def test_project_task_validates_all_edits_before_commit_and_supports_undo(tmp_path):
    work=CodingWorkspace(tmp_path)
    workspace_id=work.create('Project')['workspace_id']
    work.write(workspace_id,'a.py','A=1\n')
    work.write(workspace_id,'b.py','B=1\n')
    operations=[{'action':'edit','path':path,'reason':'update'} for path in ('a.py','b.py')]
    failed=work.run_project(workspace_id,'a.py','Update both files',ProjectModel(operations,'A=2\n','B=2\n'),Sandbox(1),TaskLedger(tmp_path))
    assert failed['state']=='failed'
    assert work.read(workspace_id,'a.py')['content']=='A=1\n'
    assert work.read(workspace_id,'b.py')['content']=='B=1\n'
    applied=work.run_project(workspace_id,'a.py','Update both files',ProjectModel(operations,'A=2\n','B=2\n'),Sandbox(),TaskLedger(tmp_path))
    assert applied['state']=='completed'
    assert len(applied['changes'])==2
    work.undo(workspace_id,applied['task_id'])
    assert work.read(workspace_id,'a.py')['content']=='A=1\n'
    assert work.read(workspace_id,'b.py')['content']=='B=1\n'


def test_project_task_rejects_unrequested_delete_and_escaping_path(tmp_path):
    work=CodingWorkspace(tmp_path)
    workspace_id=work.create('Project')['workspace_id']
    work.write(workspace_id,'keep.py','print("keep")\n')
    with pytest.raises(WorkbenchError):
        work.run_project(workspace_id,'keep.py','Improve this project',ProjectModel([
            {'action':'delete','path':'keep.py','reason':'remove'}]),Sandbox(),TaskLedger(tmp_path))
    with pytest.raises(WorkbenchError):
        work.run_project(workspace_id,'keep.py','Create a file',ProjectModel([
            {'action':'create','path':'../outside.py','reason':'escape'}]),Sandbox(),TaskLedger(tmp_path))
    assert work.read(workspace_id,'keep.py')['content']=='print("keep")\n'


def test_create_only_request_does_not_edit_open_file_even_if_model_plans_it(tmp_path):
    work=CodingWorkspace(tmp_path)
    workspace_id=work.create('Project')['workspace_id']
    work.write(workspace_id,'open.py','print("keep")\n')
    operations=[{'action':'create','path':'addition.py','reason':'new file'},
                {'action':'edit','path':'open.py','reason':'unnecessary edit'}]
    result=work.run_project(workspace_id,'open.py','Create a new file named addition.py. Leave open.py unchanged.',
                            ProjectModel(operations,'def add(a, b):\n    return a + b\n'),Sandbox(),TaskLedger(tmp_path))
    assert result['state']=='completed'
    assert [change['path'] for change in result['changes']]==['addition.py']
    assert work.read(workspace_id,'open.py')['content']=='print("keep")\n'


def test_model_new_files_scope_blocks_collateral_edits_before_generation(tmp_path):
    work=CodingWorkspace(tmp_path)
    ident=work.create('Scoped project')['workspace_id']
    work.write(ident,'notes.md','Original notes')
    model=ProjectModel({'scope':'new_files','operations':[
        {'action':'create','path':'new.md','reason':'requested'},
        {'action':'edit','path':'notes.md','reason':'unrequested'}]})
    with pytest.raises(WorkbenchError,match='cannot modify existing'):
        work.run_project(ident,'notes.md','Create a standalone document',model,Sandbox(),TaskLedger(tmp_path))
    assert work.read(ident,'notes.md')['content']=='Original notes'
    assert [item['name'] for item in work.get(ident)['files']]==['notes.md']


def test_model_new_files_scope_does_not_send_unrelated_contents_to_generator(tmp_path):
    import json
    work=CodingWorkspace(tmp_path)
    ident=work.create('Scoped project')['workspace_id']
    work.write(ident,'notes.md','Unrelated existing content')
    class CapturingModel(ProjectModel):
        def complete_code(self,messages,max_tokens=3072):
            self.generated_context=json.loads(messages[-1]['content'])['file_contents']
            return {'code':'# Requested new document\n'}
    model=CapturingModel({'scope':'new_files','operations':[
        {'action':'create','path':'new.md','reason':'requested'}]})
    result=work.run_project(ident,'notes.md','Create a standalone document',model,Sandbox(),TaskLedger(tmp_path))
    assert result['state']=='completed'
    assert model.generated_context=={}
    assert work.read(ident,'notes.md')['content']=='Unrelated existing content'


def test_named_existing_target_rejects_changes_to_duplicate_file(tmp_path):
    work=CodingWorkspace(tmp_path)
    ident=work.create('Precise project')['workspace_id']
    for path in ('docs/notes.md','copies/notes.md'):work.write(ident,path,'# Notes\nOld item.\n')
    model=ProjectModel({'scope':'existing_files','operations':[
        {'action':'edit','path':path,'reason':'change copied text'} for path in ('docs/notes.md','copies/notes.md')]})
    with pytest.raises(WorkbenchError,match='outside the explicitly named'):
        work.run_project(ident,'docs/notes.md','Replace the old item in docs/notes.md',model,Sandbox(),TaskLedger(tmp_path))
    assert work.read(ident,'docs/notes.md')['content']=='# Notes\nOld item.\n'
    assert work.read(ident,'copies/notes.md')['content']=='# Notes\nOld item.\n'


def test_literal_replacement_preserves_heading_and_skips_full_file_generation(tmp_path):
    work=CodingWorkspace(tmp_path)
    ident=work.create('Precise project')['workspace_id']
    work.write(ident,'docs/notes.md','# Heading\n\nOld item.\n\nOther content.\n')
    model=ProjectModel({'scope':'existing_files','operations':[
        {'action':'edit','path':'docs/notes.md','reason':'requested replacement',
         'replacements':[{'old_text':'Old item.','new_text':'Reviewed item.'}]}]})
    result=work.run_project(ident,'docs/notes.md','Replace Old item. with Reviewed item. in docs/notes.md',model,Sandbox(),TaskLedger(tmp_path))
    assert result['state']=='completed'
    assert work.read(ident,'docs/notes.md')['content']=='# Heading\n\nReviewed item.\n\nOther content.\n'
    work.undo(ident,result['task_id'])
    assert work.read(ident,'docs/notes.md')['content']=='# Heading\n\nOld item.\n\nOther content.\n'


def test_ambiguous_literal_replacement_never_publishes_any_file(tmp_path):
    work=CodingWorkspace(tmp_path)
    ident=work.create('Precise project')['workspace_id']
    work.write(ident,'notes.md','Old item.\nOld item.\n')
    model=ProjectModel({'scope':'existing_files','operations':[
        {'action':'edit','path':'notes.md','reason':'ambiguous',
         'replacements':[{'old_text':'Old item.','new_text':'Reviewed item.'}]}]})
    with pytest.raises(WorkbenchError,match='exactly one original'):
        work.run_project(ident,'notes.md','Change the old item in notes.md',model,Sandbox(),TaskLedger(tmp_path))
    assert work.read(ident,'notes.md')['content']=='Old item.\nOld item.\n'


def test_project_task_deletes_requested_file_and_can_restore_it(tmp_path):
    work=CodingWorkspace(tmp_path)
    workspace_id=work.create('Project')['workspace_id']
    work.write(workspace_id,'obsolete.py','print("old")\n')
    result=work.run_project(workspace_id,'obsolete.py','Delete obsolete.py',ProjectModel([
        {'action':'delete','path':'obsolete.py','reason':'explicitly requested'}]),Sandbox(),TaskLedger(tmp_path))
    assert result['state']=='completed'
    assert work.get(workspace_id)['files']==[]
    work.undo(workspace_id,result['task_id'])
    assert work.read(workspace_id,'obsolete.py')['content']=='print("old")\n'


def test_project_task_tracks_implicit_parent_folders_for_undo(tmp_path):
    work=CodingWorkspace(tmp_path)
    workspace_id=work.create('Project')['workspace_id']
    result=work.run_project(workspace_id,'','Create a new file nested/add.py',ProjectModel([
        {'action':'create','path':'nested/add.py','reason':'requested file'}],
        'def add(a, b):\n    return a + b\n'),Sandbox(),TaskLedger(tmp_path))
    assert [change['path'] for change in result['changes']]==['nested','nested/add.py']
    work.undo(workspace_id,result['task_id'])
    assert work.get(workspace_id)['folders']==[]
