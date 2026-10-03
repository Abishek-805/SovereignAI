"""Independent Docker authoring controls for the first Code Fidelity tasks.

The private tests are never included in model prompts. This script tests only
reference and deliberately incomplete starting files, not generated candidates.
"""
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from router.sandbox import CodeSandbox, SANDBOX_VERIFICATION_VERSION, SANDBOX_VERIFICATION_MAX_AGE, sandbox_policy_fingerprint
from workflows.code_runtime import runner


CASES = {
    'cf01': {
        'starting': '''def parse_invoice(text):
    fields = dict(line.split(':', 1) for line in text.splitlines() if ':' in line)
    if 'invoice_number' not in fields:
        return {'error': 'invoice_number'}
    return {'invoice_number': fields['invoice_number'].strip(), 'total': float(fields.get('total', 0))}
''',
        'reference': '''def parse_invoice(text):
    fields = dict(line.split(':', 1) for line in text.splitlines() if ':' in line)
    if 'invoice_number' not in fields:
        raise KeyError('invoice_number')
    if 'total' not in fields:
        raise KeyError('total')
    return {'invoice_number': fields['invoice_number'].strip(), 'total': float(fields['total'].strip())}
''',
        'tests': '''import unittest
from solution import parse_invoice
class TestInvoice(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(parse_invoice('invoice_number: A-2\\ntotal: 13.5'), {'invoice_number':'A-2','total':13.5})
    def test_missing_number_raises(self):
        with self.assertRaisesRegex(KeyError, 'invoice_number'):
            parse_invoice('total: 2')
    def test_missing_total_raises(self):
        with self.assertRaisesRegex(KeyError, 'total'):
            parse_invoice('invoice_number: B')
    def test_no_false_total(self):
        with self.assertRaises(KeyError):
            parse_invoice('note: total 44\\ninvoice_number: C')
''',
    },
    'cf04': {
        'starting': '''def calculate_tax(subtotal, rate):
    return round(subtotal * rate, 2)

def invoice_total(subtotal, rate):
    return round(subtotal + calculate_tax(subtotal, rate), 2)

def export_invoice(rows):
    return 'item,amount\\n' + ''.join(f"{item},{amount}\\n" for item, amount in rows)
''',
        'reference': '''import csv
import io

def calculate_tax(subtotal, rate):
    return round(subtotal * rate, 2)

def invoice_total(subtotal, rate):
    return round(subtotal + calculate_tax(subtotal, rate), 2)

def export_invoice(rows):
    stream = io.StringIO(newline='')
    writer = csv.writer(stream, lineterminator='\\n')
    writer.writerow(['item', 'amount'])
    writer.writerows(rows)
    return stream.getvalue()
''',
        'tests': '''import csv, io, unittest
from solution import calculate_tax, invoice_total, export_invoice
class TestInvoiceCSV(unittest.TestCase):
    def test_preserved_symbols(self):
        self.assertEqual(calculate_tax(100, .1), 10)
        self.assertEqual(invoice_total(100, .1), 110)
    def test_round_trip(self):
        rows = [['Widget, large', '2'], ['A "quoted" part', '5']]
        self.assertEqual(list(csv.reader(io.StringIO(export_invoice(rows)))), [['item','amount'], *rows])
    def test_empty(self):
        self.assertEqual(list(csv.reader(io.StringIO(export_invoice([])))), [['item','amount']])
''',
    },
    'cf18': {
        'starting': '''def pass_report(rows, columns):
    return {name: {'passed': sum(float(row[name]) > 25 for row in rows), 'total': len(rows)} for name in columns}
''',
        'reference': '''def pass_report(rows, columns):
    answer = {}
    for name in columns:
        passed = failed = missing = invalid = 0
        for row in rows:
            value = row.get(name)
            if value is None or value == '':
                missing += 1
                continue
            try:
                score = float(value)
            except (TypeError, ValueError):
                invalid += 1
                continue
            if score != score:
                invalid += 1
            elif score < 25:
                failed += 1
            else:
                passed += 1
        answer[name] = {'passed': passed, 'failed': failed, 'missing': missing,
                        'invalid': invalid, 'total': len(rows),
                        'percentage': round(100 * passed / len(rows), 2) if rows else None}
    return answer
''',
        'tests': '''import unittest
from solution import pass_report
class TestPassReport(unittest.TestCase):
    def test_boundary_and_missing(self):
        rows = [{'WAT1':24,'WAT2':25},{'WAT1':25,'WAT2':None},{'WAT1':'bad','WAT2':30},{'WAT1':'','WAT2':10}]
        out = pass_report(rows, ['WAT1','WAT2'])
        self.assertEqual(out['WAT1'], {'passed':1,'failed':1,'missing':1,'invalid':1,'total':4,'percentage':25.0})
        self.assertEqual(out['WAT2'], {'passed':2,'failed':1,'missing':1,'invalid':0,'total':4,'percentage':50.0})
    def test_empty(self):
        self.assertEqual(pass_report([], ['CAT'])['CAT']['percentage'], None)
    def test_nan_is_invalid(self):
        self.assertEqual(pass_report([{'A': float('nan')}], ['A'])['A']['invalid'], 1)
''',
    },
}


def main():
    validation = json.loads((ROOT / 'data/sandbox-validation.json').read_text())
    if validation.get('verification_version') != SANDBOX_VERIFICATION_VERSION or validation.get('policy_fingerprint') != sandbox_policy_fingerprint() or not 0 <= time.time() - validation['validated_at'] <= SANDBOX_VERIFICATION_MAX_AGE:
        raise RuntimeError('Docker verification missing, stale or mismatched')
    sandbox = CodeSandbox('docker', image_id=validation['image_id'], task_root=HERE / 'docker-tasks')
    sandbox._ready()
    records = []
    for task_id, case in CASES.items():
        pair = {}
        for arm in ('starting', 'reference'):
            files = {'solution.py': case[arm].encode(), 'test_contract.py': case['tests'].encode()}
            result = sandbox.execute(runner('solution.py', mode='run', tests=True), timeout=60, input_files=files)
            pair[arm] = {'executed': result.executed, 'exit_code': result.exit_code,
                         'stdout': result.stdout, 'stderr': result.stderr,
                         'file_sha256': hashlib.sha256(files['solution.py']).hexdigest(),
                         'private_test_sha256': hashlib.sha256(files['test_contract.py']).hexdigest()}
        if not pair['reference']['executed'] or pair['reference']['exit_code'] != 0 or not pair['starting']['executed'] or pair['starting']['exit_code'] == 0:
            raise AssertionError(f'Authoring control failed for {task_id}: {pair}')
        records.append({'task_id': task_id, **pair})
        print(task_id, 'reference PASS; starting FAIL', flush=True)
    report = {'name': 'Code Fidelity & Repair authoring controls', 'status': 'AUTHORING_CONTROLS_ONLY',
              'task_manifest_sha256': hashlib.sha256((HERE/'code-fidelity-tasks.json').read_bytes()).hexdigest(),
              'sandbox_image_id': validation['image_id'], 'cases': records}
    (HERE/'code-fidelity-authoring-results.json').write_text(json.dumps(report, indent=2)+'\n')


if __name__ == '__main__':
    main()
