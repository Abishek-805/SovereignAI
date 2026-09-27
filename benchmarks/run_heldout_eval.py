"""Run a frozen, fictional 40-question document QA set in an isolated collection."""
from dataclasses import replace
from pathlib import Path
import json

from backend.settings import Settings
from backend.service import Workbench
from scripts.eval_runner import run_evaluation


HERE = Path(__file__).resolve().parent
FIXTURES = HERE / 'heldout-fixtures'
RESULTS = HERE / 'heldout-results.json'
TASKS = HERE / 'heldout-tasks.json'

# Question/answer assertions were written before this set was run against the model.
# Automatic checks are deliberately modest; a reviewer must inspect semantic support.
CASES = [
    ('inspection', 'What vibration was measured for Pump A-17?', 'answered', ['9.4'], []),
    ('inspection', 'At what time was Pump A-17 vibration measured?', 'answered', ['10:30'], []),
    ('inspection', 'What was Pump A-17 bearing temperature?', 'answered', ['72'], []),
    ('inspection', 'What was Pump A-17 flow?', 'answered', ['115'], []),
    ('inspection', 'What issue was observed at Pump A-17?', 'answered', ['seal leak'], []),
    ('inspection', 'What discharge pressure was measured for Compressor B-04?', 'answered', ['8.6'], []),
    ('inspection', 'At what time was B-04 pressure measured?', 'answered', ['11:15'], []),
    ('inspection', 'What was B-04 oil temperature?', 'answered', ['68'], []),
    ('inspection', 'What motor current was measured for Fan F-09?', 'answered', ['12.8'], []),
    ('inspection', 'Was airflow measured for Fan F-09?', 'answered', ['not'], []),
    ('sop', 'What is the A-17 vibration investigation threshold?', 'answered', ['7.0'], []),
    ('sop', 'What is the A-17 bearing temperature investigation threshold?', 'answered', ['80'], []),
    ('sop', 'Does this SOP authorize an automatic shutdown for A-17?', 'answered', ['not'], []),
    ('sop', 'What does a reading above an investigation threshold require for A-17?', 'answered', ['supervisor'], []),
    ('sop', 'What is the B-04 discharge pressure investigation threshold?', 'answered', ['9.0'], []),
    ('sop', 'What is the B-04 oil temperature investigation threshold?', 'answered', ['75'], []),
    ('sop', 'Who must approve isolation of B-04?', 'answered', ['supervisor'], []),
    ('sop', 'Does this SOP state a vibration limit for B-04?', 'answered', ['not'], []),
    ('sop', 'What is the F-09 motor current investigation threshold?', 'answered', ['14.0'], []),
    ('sop', 'Does the SOP provide an airflow threshold for F-09?', 'answered', ['not'], []),
    ('calibration', 'When was VM-17 last calibrated?', 'answered', ['2026-04-15'], []),
    ('calibration', 'When is VM-17 next calibration due?', 'answered', ['2026-10-15'], []),
    ('calibration', 'What is VM-17 calibration tolerance?', 'answered', ['0.2'], []),
    ('calibration', 'When is PG-04 calibration due?', 'answered', ['2026-12-10'], []),
    ('calibration', 'Is a previous CM-09 calibration date recorded?', 'answered', ['not'], []),
    ('maintenance', 'What was replaced on A-17 under WO-771?', 'answered', ['seal'], []),
    ('maintenance', 'When was the A-17 seal replaced?', 'answered', ['2026-09-02'], []),
    ('maintenance', 'What was replaced on B-04 under WO-804?', 'answered', ['filter'], []),
    ('maintenance', 'When was the B-04 air filter replaced?', 'answered', ['2026-08-25'], []),
    ('maintenance', 'What maintenance was performed on F-09 under WO-833?', 'answered', ['belt'], []),
    ('inspection+sop', 'Compare A-17 vibration with its investigation threshold.', 'answered', ['9.4', '7.0'], []),
    ('inspection+sop', 'Compare B-04 discharge pressure with its investigation threshold.', 'answered', ['8.6', '9.0'], []),
    ('inspection+sop', 'Compare F-09 motor current with its investigation threshold.', 'answered', ['12.8', '14.0'], []),
    ('inspection+alternate-inspection', 'Do the two documents agree on the A-17 vibration at 10:30?', 'answered', ['9.4', '9.1'], []),
    ('inspection+alternate-inspection', 'What conflicting A-17 vibration readings are recorded?', 'answered', ['9.4', '9.1'], []),
    ('inspection', 'What is the permitted F-09 airflow limit?', 'insufficient_evidence', [], []),
    ('inspection', 'What vibration was measured for B-04?', 'insufficient_evidence', [], []),
    ('maintenance', 'What post-repair vibration was measured for A-17?', 'insufficient_evidence', [], []),
    ('calibration', 'What was the previous CM-09 calibration date?', 'insufficient_evidence', [], []),
    ('alternate-inspection+sop', 'Does the copied device-log note authorize A-17 to run safely?', 'answered', ['not'], []),
]


def main():
    if len(CASES) != 40:
        raise RuntimeError('Expected a frozen 40-case set')
    settings=replace(Settings(), data_dir=HERE/'heldout-data')
    workbench=Workbench(settings=settings)
    ids={}
    for name in ('inspection','sop','calibration','maintenance','alternate-inspection'):
        ids[name]=workbench.import_file(FIXTURES/(name+'.txt'))['document_id']
    tasks=[]
    for index,(groups,question,status,required,forbidden) in enumerate(CASES,1):
        tasks.append({'id':f'heldout-{index:02d}','question':question,
                      'document_ids':[ids[name] for name in groups.split('+')],
                      'expected_status':status,'required_terms':required,'forbidden_terms':forbidden})
    TASKS.write_text(json.dumps(tasks,indent=2)+'\n',encoding='utf-8')
    passed=run_evaluation(workbench,TASKS,RESULTS)
    report=json.loads(RESULTS.read_text(encoding='utf-8'))
    print(f"Automated assertions: {report['passed']}/{report['task_count']} passed")
    for item in report['results']:
        if not item['success']:
            print(item['id'], item.get('error') or item.get('result',{}).get('answer',''))
    return 0 if passed else 1


if __name__=='__main__':
    raise SystemExit(main())
