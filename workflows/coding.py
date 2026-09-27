"""A bounded, fixed CSV coding demonstration with trusted container tests."""
import csv
import hashlib
import io
import json
from pathlib import Path

from backend.contracts import WorkbenchError

SPEC = """Write only Python code. Read /input/data.csv with csv.DictReader and write /output/result.csv.
Required input columns are category and value. Group by category, sum integer values, and write
category,total columns sorted by category. An empty input writes just the output header.
If columns are missing, raise ValueError('Missing required columns').
If a value is not an integer, raise ValueError('Invalid value').
Use only Python standard library. Do not use network, subprocess, extra files, or external packages."""

CASES = (
    ('normal', b'category,value\nA,2\nB,3\nA,5\n', {'A':7,'B':3}),
    ('empty', b'category,value\n', {}),
    ('missing_columns', b'category,amount\nA,2\n', None),
    ('nonnumeric', b'category,value\nA,nope\n', None),
)


def _check_output(result, expected):
    if not result.executed or result.exit_code != 0:
        return False
    raw = result.output_files.get('result.csv')
    if raw is None:
        return False
    try:
        reader = csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))
        if reader.fieldnames != ['category','total']:
            return False
        rows = list(reader)
        if any(set(row) != {'category','total'} or None in row.values() for row in rows):
            return False
        actual = {row['category']:int(row['total']) for row in rows}
        return len(rows) == len(expected) and actual == expected and list(actual) == sorted(actual)
    except (UnicodeError,ValueError,TypeError):
        return False


def test_candidate(sandbox, code):
    checks = {}
    for name, source, expected in CASES:
        result = sandbox.execute(code, input_files={'data.csv':source})
        if expected is not None:
            checks[name] = _check_output(result, expected)
        else:
            marker = 'Missing required columns' if name == 'missing_columns' else 'Invalid value'
            checks[name] = result.executed and result.exit_code != 0 and marker in result.stderr
    return checks


def run_csv_demo(model, sandbox, ledger, settings):
    task = ledger.create('csv_coding_demo', [])
    try:
        sandbox._ready()
        ledger.step(task, 'plan', {'task':'category integer sum', 'case_count':len(CASES)})
        messages = [{'role':'system','content':'You are writing a small Python CSV script for a locked-down Linux container. Return the code in the required JSON field.'},
                    {'role':'user','content':SPEC}]
        checks = {}
        code = ''
        for attempt in range(3):
            generated = model.complete_code(messages)
            code = generated['code']
            ledger.step(task, 'generate' if attempt == 0 else f'repair_{attempt}',
                        {'attempt':attempt + 1, 'code_sha256':hashlib.sha256(code.encode()).hexdigest()})
            checks = test_candidate(sandbox, code)
            ledger.step(task, f'test_{attempt + 1}', {'checks':checks})
            if all(checks.values()):
                break
            messages.append({'role':'assistant','content':json.dumps({'code':code})})
            messages.append({'role':'user','content':'Trusted tests failed: '+json.dumps(checks)+
                             '. Repair the script. Keep the same required paths and error messages.'})
        if not all(checks.values()):
            ledger.fail(task, 'trusted_tests_failed')
            return {'status':'failed','task_id':task['task_id'],'checks':checks,'attempts':3,
                    'message':'Generated code failed trusted container tests and was not approved.'}
        directory = settings.data_dir.parent / 'outputs' / task['task_id']
        directory.mkdir(parents=True, exist_ok=False)
        script = directory / 'program.py'
        script.write_text(code, encoding='utf-8')
        report = {'task_id':task['task_id'],'checks':checks,'attempts':attempt + 1,
                  'code_sha256':hashlib.sha256(code.encode()).hexdigest(),
                  'sandbox_image':sandbox.image_id}
        (directory / 'test-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        ledger.complete(task, checks)
        return {'status':'completed','task_id':task['task_id'],'checks':checks,
                'attempts':attempt + 1,'code':code,'report':report}
    except Exception as exc:
        ledger.fail(task,exc.code if isinstance(exc,WorkbenchError) else 'coding_workflow_failed')
        raise
