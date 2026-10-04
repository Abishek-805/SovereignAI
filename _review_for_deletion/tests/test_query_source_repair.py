import pytest
from openpyxl import Workbook

from backend.contracts import WorkbenchError
from tests.test_service import service


@pytest.mark.parametrize('repair_valid',[True,False])
def test_source_validation_feedback_repairs_once_or_rejects(service,tmp_path,repair_valid):
    book=Workbook();sheet=book.active;sheet.title='Exam'
    sheet.append(['ID','Score']);sheet.append(['TEAM01',25]);sheet.append(['TEAM02',24])
    path=tmp_path/'results.xlsx';book.save(path)
    doc=service.import_file(path)
    calls=[]
    def plan(question,tables,history,feedback=None):
        calls.append(feedback)
        return {'operation':'percentage','_measure':{
            'operation':'percentage','outcome':'pass','rule_outcome':'fail',
            'threshold':25,'threshold_operator':'lt','entity_values':['TEAM'],
            'score_columns':['Score'] if feedback and repair_valid else [],'scope':'all'}}
    service.model.plan_table_query=plan
    service.model.complete=lambda *a,**kw:pytest.fail('Source arithmetic must not be rewritten by prose generation')
    request='Pass percentage of TEAM; below 25 fails'
    if repair_valid:
        result=service.ask(request,[doc['document_id']],force_documents=True)
        assert result['status']=='answered'
        assert 'Passed' in result['answer'] and '50.0' in result['answer']
        assert 'at least 25' in result['answer']
    else:
        with pytest.raises(WorkbenchError,match='assessment score columns'):
            service.ask(request,[doc['document_id']],force_documents=True)
    assert len(calls)==2 and calls[0] is None
    assert 'assessment score columns' in calls[1]
