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

    def plan_workspace_edit(self, instruction, files, folders, current_file, history=None):
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
    assert not (work.files_directory(workspace_id)/'tools/add.py').exists()
    work.accept(workspace_id,task['task_id'])
    assert work.read(workspace_id,'tools/add.py')['content'].startswith('def add')
    assert sandbox.snapshots[0]['tools/add.py'].startswith(b'def add')
    assert 'current.py' in model.tree[0]
    work.undo(workspace_id,task['task_id'])
    assert 'tools' not in work.get(workspace_id)['folders']
    assert [item['name'] for item in work.get(workspace_id)['files']]==['current.py']


def test_new_html_css_project_saves_files_without_docker(tmp_path):
    work=CodingWorkspace(tmp_path)
    workspace_id=work.create('Web project')['workspace_id']
    model=ProjectModel({'scope':'new_files','operations':[
        {'action':'create','path':'site/index.html','reason':'HTML page'},
        {'action':'create','path':'site/style.css','reason':'Linked stylesheet'}]},
        '<!doctype html><html><head><link rel="stylesheet" href="style.css"></head><body><h1>Hello</h1></body></html>\n',
        'h1 { color: teal; }\n')
    result=work.run_project(workspace_id,'',
        'Create a project folder with a simple HTML page and CSS in it',
        model,None,TaskLedger(tmp_path))
    assert result['state']=='completed'
    assert result['validation']=='validation unavailable'
    assert result['checks']['container_executed'] is False
    assert work.get(workspace_id)['files']==[]
    with pytest.raises(WorkbenchError,match='Docker validation'):
        work.accept(workspace_id,result['task_id'])
    work.discard(workspace_id,result['task_id'])
    assert work.get(workspace_id)['files']==[]


def test_new_web_pair_uses_unused_names_in_selected_project(tmp_path):
    work=CodingWorkspace(tmp_path)
    workspace_id=work.create('Existing project')['workspace_id']
    work.write(workspace_id,'index.html','<html>Old</html>')
    work.write(workspace_id,'style.css','body { color: red; }')
    model=ProjectModel({'scope':'new_files','operations':[
        {'action':'create','path':'page2.html','reason':'New HTML page'},
        {'action':'create','path':'page2.css','reason':'New stylesheet'}]},
        '<html><head><link rel="stylesheet" href="page2.css"></head><body>New</body></html>',
        'body { color: blue; }')
    result=work.run_project(workspace_id,'',
        'generate html and css file for simple html web page',model,None,TaskLedger(tmp_path))
    assert result['state']=='completed'
    assert {item['name'] for item in work.get(workspace_id)['files']}=={'index.html','style.css'}
    with pytest.raises(WorkbenchError,match='Docker validation'):
        work.accept(workspace_id,result['task_id'])
    assert {change['path'] for change in result['changes']}=={'page2.html','page2.css'}
    work.discard(workspace_id,result['task_id'])
    assert work.read(workspace_id,'index.html')['content']=='<html>Old</html>'


def test_arithmetic_folder_creates_nested_program_without_touching_existing_files(tmp_path):
    work=CodingWorkspace(tmp_path)
    workspace_id=work.create('Math project')['workspace_id']
    work.write(workspace_id,'old.py','print("unchanged")')
    model=ProjectModel({'scope':'new_files','operations':[
        {'action':'create','path':'arithmetic/operations.py','reason':'Arithmetic program'}]},
        'def calculate(first, second, operation):\n    return first / second if operation == "/" else first + second\n')
    result=work.run_project(workspace_id,'',
        'generate folder containing code that does simple arithmetic operations',
        model,None,TaskLedger(tmp_path))
    assert result['state']=='completed'
    assert 'arithmetic/operations.py' not in {item['name'] for item in work.get(workspace_id)['files']}
    generated=next(change['after'] for change in result['changes'] if change['path']=='arithmetic/operations.py')
    assert 'def calculate(' in generated and 'first / second' in generated
    assert work.read(workspace_id,'old.py')['content']=='print("unchanged")'


def test_search_algorithms_generated_in_existing_folder(tmp_path):
    work=CodingWorkspace(tmp_path)
    workspace_id=work.create('Search project')['workspace_id']
    work.file_operation(workspace_id,'mkdir','array_search_types')
    model=ProjectModel({'scope':'new_files','operations':[
        {'action':'create','path':'array_search_types/SearchAlgorithms.java','reason':'Array search algorithms'}]},
        'public class SearchAlgorithms { static int linearSearch(int[] a, int x) { return -1; } static int binarySearch(int[] a, int x) { return -1; } }')
    result=work.run_project(workspace_id,'array_search_types/SearchAlgorithms.java',
        'Create Java array search code in folder array_search_types',model,None,TaskLedger(tmp_path))
    assert result['state']=='completed'
    source=next(change['after'] for change in result['changes'] if change['path']=='array_search_types/SearchAlgorithms.java')
    assert 'linearSearch' in source and 'binarySearch' in source


def test_model_can_include_redundant_mkdir_for_existing_code_folder(tmp_path):
    work=CodingWorkspace(tmp_path)
    wid=work.create('Existing search folder')['workspace_id']
    work.file_operation(wid,'mkdir','array_search')
    model=ProjectModel({'scope':'new_files','operations':[
        {'action':'mkdir','path':'array_search','reason':'Reuse folder'},
        {'action':'create','path':'array_search/LinearSearch.java','reason':'Linear search'},
        {'action':'create','path':'array_search/BinarySearch.java','reason':'Binary search'}]},
        'public class LinearSearch { public static int find(int[] a, int x) { return -1; } }',
        'public class BinarySearch { public static int find(int[] a, int x) { return -1; } }')
    task=work.run_project(wid,'','Create linear and binary search code in array_search',
                          model,Sandbox(),TaskLedger(tmp_path))
    assert task['state']=='completed'
    assert {change['path'] for change in task['changes']}=={
        'array_search/LinearSearch.java','array_search/BinarySearch.java'}
    assert work.get(wid)['files']==[]
    work.accept(wid,task['task_id'])
    assert {item['name'] for item in work.get(wid)['files']}=={
        'array_search/LinearSearch.java','array_search/BinarySearch.java'}


def test_creation_request_repairs_model_edits_of_nonexistent_files(tmp_path):
    work=CodingWorkspace(tmp_path)
    wid=work.create('Search model repair')['workspace_id']
    work.file_operation(wid,'mkdir','array_search')
    model=ProjectModel({'scope':'existing_files','operations':[
        {'action':'edit','path':'array_search/LinearSearch.java','reason':'New linear search'},
        {'action':'edit','path':'array_search/BinarySearch.java','reason':'New binary search'}]},
        'public class LinearSearch {}','public class BinarySearch {}')
    result=work.run_project(wid,'','Create linear and binary search Java codes in array_search',
                            model,Sandbox(),TaskLedger(tmp_path))
    assert result['state']=='completed'
    assert {change['action'] for change in result['changes']}=={'create'}
    assert work.get(wid)['files']==[]


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
    assert work.read(workspace_id,'a.py')['content']=='A=1\n'
    work.accept(workspace_id,applied['task_id'])
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
    assert work.read(ident,'docs/notes.md')['content']=='# Heading\n\nOld item.\n\nOther content.\n'
    work.accept(ident,result['task_id'])
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
    assert work.read(workspace_id,'obsolete.py')['content']=='print("old")\n'
    work.accept(workspace_id,result['task_id'])
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
    work.accept(workspace_id,result['task_id'])
    work.undo(workspace_id,result['task_id'])
    assert work.get(workspace_id)['folders']==[]
