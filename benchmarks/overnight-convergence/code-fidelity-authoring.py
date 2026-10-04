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
    'cf02': {
        'starting': '''import json
from pathlib import Path

def read_settings(path, defaults):
    if not Path(path).exists():
        return defaults
    return json.loads(Path(path).read_text())
''',
        'reference': '''import json
from pathlib import Path

def read_settings(path, defaults):
    result = dict(defaults)
    try:
        data = json.loads(Path(path).read_text(encoding='utf-8'))
    except FileNotFoundError:
        return result
    except json.JSONDecodeError as exc:
        raise ValueError(f'{path}: malformed JSON') from exc
    if not isinstance(data, dict):
        raise ValueError(f'{path}: settings must be an object')
    result.update(data)
    return result
''',
        'tests': '''import tempfile, unittest
from pathlib import Path
from solution import read_settings
class TestSettings(unittest.TestCase):
    def test_missing_independent(self):
        defaults = {'theme':'dark'}
        out = read_settings('/output/absent-settings.json', defaults)
        self.assertEqual(out, defaults)
        self.assertIsNot(out, defaults)
    def test_valid_overlay(self):
        with tempfile.TemporaryDirectory(dir='/output') as folder:
            path = Path(folder)/'settings.json'
            path.write_text('{"theme":"light"}')
            defaults = {'theme':'dark','font':12}
            self.assertEqual(read_settings(path, defaults), {'theme':'light','font':12})
            self.assertEqual(defaults, {'theme':'dark','font':12})
    def test_bad_json(self):
        with tempfile.TemporaryDirectory(dir='/output') as folder:
            path = Path(folder)/'bad.json'
            path.write_text('{')
            with self.assertRaisesRegex(ValueError, 'bad.json'):
                read_settings(path, {})
''',
    },
    'cf03': {
        'starting': '''def parse_bounded_int(value, maximum):
    return int(value)

def main(argv):
    print(parse_bounded_int(argv[0], int(argv[1])))
    return 0
''',
        'reference': '''def parse_bounded_int(value, maximum):
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError('not an integer') from exc
    if str(number) != str(value).strip() or number < 0 or number > maximum:
        raise ValueError('integer outside allowed range')
    return number

def main(argv):
    import sys
    try:
        if len(argv) != 2:
            raise ValueError('expected value and maximum')
        print(parse_bounded_int(argv[0], int(argv[1])))
        return 0
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
''',
        'tests': '''import contextlib, io, unittest
from solution import parse_bounded_int, main
class TestBoundedCLI(unittest.TestCase):
    def test_boundaries(self):
        self.assertEqual(parse_bounded_int('0', 25), 0)
        self.assertEqual(parse_bounded_int('25', 25), 25)
    def test_rejection(self):
        for value in ('-1','26','2.5','abc'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_bounded_int(value, 25)
    def test_cli_error_no_traceback(self):
        error = io.StringIO()
        with contextlib.redirect_stderr(error):
            self.assertNotEqual(main(['26','25']), 0)
        self.assertNotIn('Traceback', error.getvalue())
    def test_cli_success(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(['25','25']), 0)
        self.assertEqual(output.getvalue().strip(), '25')
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
    'cf05': {
        'starting': '''CONTACTS = {'Alice':'111', 'ALAN':'222', 'Bob':'333'}

def get_contact(name):
    return CONTACTS.get(name)

def list_contacts():
    return sorted(CONTACTS)

def search_contacts(prefix):
    return [name for name in CONTACTS if name.startswith(prefix)]
''',
        'reference': '''CONTACTS = {'Alice':'111', 'ALAN':'222', 'Bob':'333'}

def get_contact(name):
    return CONTACTS.get(name)

def list_contacts():
    return sorted(CONTACTS)

def search_contacts(prefix):
    return sorted(name for name in CONTACTS if name.casefold().startswith(prefix.casefold()))
''',
        'tests': '''import unittest
from solution import get_contact, list_contacts, search_contacts
class TestContacts(unittest.TestCase):
    def test_existing(self):
        self.assertEqual(get_contact('Alice'), '111')
        self.assertIsNone(get_contact('alice'))
        self.assertEqual(list_contacts(), ['ALAN','Alice','Bob'])
    def test_prefix(self):
        self.assertEqual(search_contacts('al'), ['ALAN','Alice'])
        self.assertEqual(search_contacts('BO'), ['Bob'])
    def test_empty(self):
        self.assertEqual(search_contacts(''), ['ALAN','Alice','Bob'])
''',
    },
    'cf06': {
        'starting': '''from collections import OrderedDict
class LRUCache:
    def __init__(self, capacity):
        self.capacity = capacity
        self.data = OrderedDict()
    def put(self, key, value):
        self.data[key] = value
        if len(self.data) > self.capacity:
            self.data.popitem(last=True)
    def get(self, key):
        return self.data.get(key)
    def delete(self, key):
        return self.data.pop(key, None) is not None
''',
        'reference': '''from collections import OrderedDict
class LRUCache:
    def __init__(self, capacity):
        self.capacity = capacity
        self.data = OrderedDict()
    def put(self, key, value):
        self.data[key] = value
        self.data.move_to_end(key)
        if len(self.data) > self.capacity:
            self.data.popitem(last=False)
    def get(self, key):
        if key not in self.data:
            return None
        self.data.move_to_end(key)
        return self.data[key]
    def delete(self, key):
        if key not in self.data:
            return False
        del self.data[key]
        return True
''',
        'tests': '''import unittest
from solution import LRUCache
class TestCache(unittest.TestCase):
    def test_eviction_and_refresh(self):
        cache = LRUCache(2)
        self.assertIsNone(cache.put('a',1))
        cache.put('b',2)
        self.assertEqual(cache.get('a'),1)
        cache.put('c',3)
        self.assertIsNone(cache.get('b'))
        self.assertEqual(cache.get('a'),1)
    def test_update_size_and_delete(self):
        cache = LRUCache(1)
        cache.put('x',1)
        cache.put('x',2)
        self.assertEqual(len(cache.data),1)
        self.assertTrue(cache.delete('x'))
        self.assertFalse(cache.delete('x'))
        self.assertIsNone(cache.get('x'))
''',
    },
    'cf11': {
        'starting': '''def add(a, b):
    return a + b

def multiply(a, b):
    return a * b
''',
        'reference': '''def add(a, b):
    return a + b

def subtract(a, b):
    return a - b

def multiply(a, b):
    return a * b
''',
        'tests': '''import unittest, solution
class TestArithmetic(unittest.TestCase):
    def test_symbols(self):
        self.assertTrue(all(callable(getattr(solution, n, None)) for n in ('add','subtract','multiply')))
        self.assertFalse(hasattr(solution, 'divide'))
    def test_values(self):
        self.assertEqual(solution.add(-3,2), -1)
        self.assertEqual(solution.subtract(-3,2), -5)
        self.assertEqual(solution.multiply(-3,2), -6)
''',
    },
    'cf12': {
        'starting': '''import csv, io
def parse_csv(text):
    return [line.split(',') for line in text.splitlines() if line]
''',
        'reference': '''import csv, io
def parse_csv(text):
    rows = list(csv.reader(io.StringIO(text, newline='')))
    if not rows:
        return []
    return [rows[0], *(row for row in rows[1:] if row)]
''',
        'tests': '''import unittest
from solution import parse_csv
class TestCSV(unittest.TestCase):
    def test_header_and_empty(self):
        self.assertEqual(parse_csv('name,value\\n\\nAlice,1\\n'), [['name','value'],['Alice','1']])
    def test_multiline_and_empty_field(self):
        self.assertEqual(parse_csv('name,note\\nBob,"two\\nlines"\\nCara,\\n'),
                         [['name','note'],['Bob','two\\nlines'],['Cara','']])
    def test_header_only(self):
        self.assertEqual(parse_csv('name,value\\n'), [['name','value']])
''',
    },
    'cf13': {
        'starting': '''import hmac
def compare_secret(candidate, stored):
    return hmac.compare_digest(candidate, stored)

def verify_password(candidate, stored):
    return compare_secret(candidate, stored)
''',
        'reference': '''import hmac
def compare_secret(candidate, stored):
    return hmac.compare_digest(candidate, stored)

def verify_password(candidate, stored):
    matched = compare_secret(candidate, stored)
    return bool(matched and len(candidate) >= 8)
''',
        'tests': '''import contextlib, inspect, io, unittest
from solution import compare_secret, verify_password
class TestPassword(unittest.TestCase):
    def test_short(self):
        self.assertIs(verify_password('abc', 'abc'), False)
    def test_valid(self):
        self.assertIs(verify_password('longpass', 'longpass'), True)
        self.assertIs(verify_password('longpass', 'different'), False)
    def test_compare_preserved(self):
        self.assertTrue(compare_secret('same','same'))
        self.assertIn('compare_digest', inspect.getsource(compare_secret))
    def test_no_secret_output(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            verify_password('confidential-password', 'confidential-password')
        self.assertEqual(output.getvalue(), '')
''',
    },
    'cf14': {
        'starting': '''def filter_range(events, start, end):
    return [event for event in events if start <= event['at'] <= end]
''',
        'reference': '''def filter_range(events, start, end):
    values = [start, end, *(event['at'] for event in events)]
    if any(value.tzinfo is None or value.utcoffset() is None for value in values):
        raise ValueError('naive datetime is not allowed')
    return [event for event in events if start <= event['at'] < end]
''',
        'tests': '''import unittest
from datetime import datetime, timezone, timedelta
from solution import filter_range
class TestRange(unittest.TestCase):
    def test_timezones_and_edges(self):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        end = start + timedelta(hours=2)
        plus_two = timezone(timedelta(hours=2))
        events = [{'id':'before','at':start-timedelta(seconds=1)},
                  {'id':'start','at':start.astimezone(plus_two)},
                  {'id':'middle','at':start+timedelta(hours=1)},
                  {'id':'end','at':end}]
        self.assertEqual([event['id'] for event in filter_range(events,start,end)], ['start','middle'])
    def test_naive_rejected(self):
        start = datetime(2026,1,1,tzinfo=timezone.utc)
        with self.assertRaises(ValueError):
            filter_range([{'at':datetime(2026,1,1)}], start, start+timedelta(days=1))
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
    'cf21': {
        'source_path': 'router/validation_feedback.py',
        'source_sha256': '55725e80075e7dd33cf83f34dcf23898b822f02cdeb83c859d3ebfae7e85cbd1',
        'mutate_from': 'signature=exceptions[-1] if exceptions else',
        'mutate_to': 'signature=exceptions[0] if exceptions else',
        'tests': '''import hashlib, re, unittest
from solution import failure_fingerprint
class TestFingerprint(unittest.TestCase):
    def test_final_exception(self):
        final = 'ValueError: final failure'
        expected = hashlib.sha256(final.encode()).hexdigest()
        self.assertEqual(failure_fingerprint('KeyError: first\\n'+final), expected)
    def test_digest_normalization(self):
        prefix = 'RuntimeError: digest '
        a = prefix + 'a'*64
        b = prefix + 'b'*64
        self.assertEqual(failure_fingerprint(a), failure_fingerprint(b))
    def test_path_and_line_noise(self):
        a = 'File /foo/a.py, line 3\\nRuntimeError: same'
        b = 'File /bar/b.py, line 900\\nRuntimeError: same'
        self.assertEqual(failure_fingerprint(a), failure_fingerprint(b))
    def test_digest_format(self):
        self.assertRegex(failure_fingerprint('error'), r'^[0-9a-f]{64}$')
''',
    },
    'cf22': {
        'source_path': 'workflows/source_quality.py',
        'source_sha256': '25cc1a91358f406901508eb9e9fa2790cb72610074ec68742178e7cf322d97aa',
        'mutate_from': '    def handle_startendtag(self, tag, attrs):\n        self.elements += 1\n',
        'mutate_to': '    def handle_startendtag(self, tag, attrs):\n        return\n',
        'tests': '''import unittest
from solution import source_issue
class TestSourceQuality(unittest.TestCase):
    def test_self_closing_html(self):
        self.assertIsNone(source_issue('view.html', '<img src="x"/>'))
    def test_normal_html(self):
        self.assertIsNone(source_issue('view.html', '<main>Hello</main>'))
    def test_plain_text_html(self):
        self.assertIsNotNone(source_issue('view.html', 'Only prose'))
    def test_other_source_checks(self):
        self.assertIsNone(source_issue('run.py', 'print(1)'))
        self.assertIsNotNone(source_issue('run.py', '# only a comment'))
        self.assertIsNone(source_issue('theme.css', 'body { color: red; }'))
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
        if 'source_path' in case:
            source_bytes = (ROOT / case['source_path']).read_bytes()
            if hashlib.sha256(source_bytes).hexdigest() != case['source_sha256']:
                raise RuntimeError(f'Frozen source snapshot changed for {task_id}')
            source = source_bytes.decode('utf-8')
            if source.count(case['mutate_from']) != 1:
                raise RuntimeError(f'Expected one mutation site for {task_id}')
            case = {**case, 'reference': source,
                    'starting': source.replace(case['mutate_from'], case['mutate_to'], 1)}
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
