from pathlib import Path
from backend.settings import Settings
from backend.service import Workbench
from tests.test_service import service


def test_maintenance_draft_uses_measurements_and_reports_missing_limits(service,tmp_path):
    report=tmp_path/'inspection.txt'
    report.write_text('Pump P-101 vibration measured 8.2 mm/s.\nMotor M-2 temperature measured 78 degrees Celsius.\n',encoding='utf-8')
    sop=tmp_path/'sop.txt'
    sop.write_text('Investigate Pump P-101 vibration above 7.1 mm/s.\nThis does not authorize shutdown.\n',encoding='utf-8')
    ids=[service.import_file(path)['document_id'] for path in (report,sop)]
    result=service.create_maintenance_draft(ids)
    assert result['status']=='completed'
    assert result['findings'][0]['status']=='exceeds investigation threshold'
    assert result['calculations'][0]['result'] > 1.0
    assert any('M-2' in issue for issue in result['open_questions'])
    assert Path(result['word_path']).is_file()
    assert Path(result['excel_path']).is_file()
