import pytest
from backend.application_tools import ApplicationTools
from backend.contracts import WorkbenchError
from tests.test_service import service
from rag.tables import execute_query
from rag.tables import compile_outcome_query
from workflows.code_runtime import desktop_requirements


@pytest.mark.parametrize('goal',['Create an OpenCV project for face detection',
    'create a open cv project in python file the project is like with the laptop camera it should detect the users face is there are not'])
def test_program_project_keeps_selected_workspace(service,monkeypatch,goal):
    identifier=service.coding.create('Selected')['workspace_id']
    calls=[]
    monkeypatch.setattr(service,'run_coding_project_task',lambda workspace,*args,**kwargs:
        calls.append(workspace) or {'state':'completed'})
    operations=[{'tool':'project_create','target':'face_detection','value':'','input':''},
                {'tool':'file_edit','target':'main.py','value':'','input':''}]
    result=ApplicationTools(service,identifier,goal=goal).execute(operations,service.tasks.create('test',[]))
    assert result['workspace_id']==identifier and calls==[identifier]
    assert len(service.coding.list())==1


def test_explicit_separate_project_can_create_workspace(service):
    identifier=service.coding.create('Selected')['workspace_id']
    tool=ApplicationTools(service,identifier,goal='Create a separate project for face detection')
    result=tool._execute('project_create','New','','')
    assert result['workspace_id']!=identifier


def test_per_assessment_percentage_uses_cohort_and_independent_numerators():
    table={'name':'Tests','columns':['ID','Test 1','Test 2'],'records':[
        {'ID':'24ALR001','Test 1':'PASS','Test 2':'FAIL'},
        {'ID':'24ALR002','Test 1':'FAIL','Test 2':'PASS'},
        {'ID':'OTHER','Test 1':'PASS','Test 2':'PASS'}]}
    result=execute_query(table,{'operation':'percentage','columns':[],
        'filters':[{'column':'ID','operator':'contains','value':'24alr'}],
        'criteria':[{'column':column,'operator':'in','value':['PASS']} for column in ['Test 1','Test 2']]})
    assert [(s['passed'],s['total'],s['percentage']) for s in result['summaries']]==[(1,2,50.0),(1,2,50.0)]
    with pytest.raises(WorkbenchError,match='explicit result'):
        execute_query(table,{'operation':'percentage','columns':['Test 1'],'filters':[]})


def test_multi_column_numeric_aggregates_keep_separate_sample_counts():
    table={'name':'Tests','columns':['A','B'],'records':[{'A':10,'B':20},{'A':'AB','B':40}]}
    result=execute_query(table,{'operation':'average','columns':['A','B'],'filters':[]})
    assert result['summaries']==[{'column':'A','numeric_rows':1,'value':10.0},{'column':'B','numeric_rows':2,'value':30.0}]


def test_percentage_compiler_binds_prefix_across_complementary_assessments():
    doc={'document_id':'results'}
    available={
        'T1':(doc,{'name':'Summary','columns':['ID','Score'],'records':[{'ID':'TEAM01','Score':12}]}),
        'T2':(doc,{'name':'Exam A','columns':['ID','Result'],'records':[{'ID':'TEAM01','Result':'PASS'}]}),
        'T3':(doc,{'name':'Exam B','columns':['ID','Passed'],'records':[{'ID':'TEAM01','Passed':'FAIL'},{'ID':'TEAM02','Passed':'PASS'}]})}
    plan=compile_outcome_query({'result_values':['PASS','PASS'],'entity_values':['TEAM']},available,'Pass percentage of TEAM in each exam')
    assert plan['table']=='T2' and plan['filters']==[{'column':'ID','operator':'contains','value':'TEAM'}]
    assert [q['table'] for q in plan['additional_queries']]==['T3']
    assert plan['unavailable_assessments']==['Summary']
    count=compile_outcome_query({'operation':'count','result_values':['PASS'],'entity_values':['TEAM'],'scope':'one','assessments':['Exam B']},available,'How many TEAM students passed Exam B?')
    assert count['table']=='T3' and not count['additional_queries']
    assert execute_query(available['T3'][1],count)['value']==1
    with pytest.raises(WorkbenchError,match='current question'):
        compile_outcome_query({'result_values':['PASS'],'entity_values':['OTHER']},available,'Pass percentage of TEAM')


def test_desktop_capabilities_depend_on_calls_not_import_or_file_name():
    assert desktop_requirements('import cv2\ncv2.VideoCapture(0)\ncv2.imshow("Camera", frame)')==['camera','desktop window']
    assert desktop_requirements('import cv2\ncv2.VideoCapture("video.mp4")')==[]


def test_camera_run_returns_local_environment_command_before_docker(service,monkeypatch):
    identifier=service.coding.create('Camera')['workspace_id']
    service.coding.write(identifier,'main.py','import cv2\ncv2.VideoCapture(0)')
    monkeypatch.setattr(service,'_verified_coding_sandbox',lambda:pytest.fail('Desktop capability is checked before Docker availability'))
    with pytest.raises(WorkbenchError,match='run-workspace-python.ps1') as exc:
        service.execute_coding_file(identifier,'main.py')
    assert exc.value.code=='desktop_required'


def test_percentage_answer_keeps_denominator_and_unavailable_coverage(service,tmp_path):
    from openpyxl import Workbook
    book=Workbook(); summary=book.active;summary.title='Summary';summary.append(['ID','Score']);summary.append(['TEAM01',40])
    sheet=book.create_sheet('Exam');sheet.append(['ID','Result']);sheet.append(['TEAM01','PASS']);sheet.append(['TEAM02','FAIL'])
    path=tmp_path/'results.xlsx';book.save(path);doc=service.import_file(path)
    service.model.plan_table_query=lambda *args,**kwargs:{'operation':'percentage','_measure':{'result_values':['PASS'],'entity_values':['TEAM'],'scope':'all'}}
    service.model.complete=lambda *args,**kwargs:pytest.fail('Verified percentages do not need generated prose')
    result=service.ask('Pass percentage of TEAM in each exam',[doc['document_id']],force_documents=True)
    assert result['status']=='answered' and '50.0' in result['answer']
    assert 'denominator' in result['answer'] and 'Summary' in result['answer'] and '[S1]' in result['answer']
