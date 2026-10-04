"""Hashable, multi-file development controls for Code Fidelity & Repair.

Runs reference and unfinished snapshots only in the verified Docker sandbox.
The private contract tests must not be included in later model context.
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


TASKS = {
    'cp01': {
        'request': ('Repair the existing multi-file receipt importer. Preserve parse_receipts(text), '
                    'invoice_totals(receipts), and main(argv). Parse quoted CSV correctly, use Decimal '
                    'for money, accept negative refunds, reject missing invoice_id/item/amount or invalid '
                    'amount with ValueError, and write sorted JSON totals as decimal strings. Keep the '
                    'existing CLI input/output arguments and all project files.'),
        'requirements': ['three public symbols remain', 'quoted CSV round trips', 'Decimal totals',
                         'refunds accepted', 'malformed rows raise ValueError', 'sorted JSON CLI output',
                         'all project files preserved'],
        'starting_files': {
            'billing/__init__.py': '',
            'billing/parser.py': '''def parse_receipts(text):
    lines = text.splitlines()[1:]
    rows = []
    for line in lines:
        if not line.strip():
            continue
        invoice_id, item, amount = line.split(',')
        rows.append({'invoice_id': invoice_id, 'item': item, 'amount': float(amount)})
    return rows
''',
            'billing/report.py': '''def invoice_totals(receipts):
    totals = {}
    for row in receipts:
        key = row['invoice_id']
        totals[key] = totals.get(key, 0) + row['amount']
    return totals
''',
            'main.py': '''import argparse
from pathlib import Path
from billing.parser import parse_receipts
from billing.report import invoice_totals

def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args(argv)
    totals = invoice_totals(parse_receipts(Path(args.input).read_text()))
    Path(args.output).write_text(str(totals))
    return 0

if __name__ == '__main__':
    raise SystemExit(main(__import__('sys').argv[1:]))
''',
        },
        'reference_files': {
            'billing/__init__.py': '',
            'billing/parser.py': '''import csv
import io
from decimal import Decimal, InvalidOperation

def parse_receipts(text):
    reader = csv.DictReader(io.StringIO(text, newline=''))
    if reader.fieldnames is None or not {'invoice_id', 'item', 'amount'} <= set(reader.fieldnames):
        raise ValueError('required columns: invoice_id, item, amount')
    rows = []
    for row in reader:
        if not row or all(value is None or not str(value).strip() for value in row.values()):
            continue
        invoice_id = (row.get('invoice_id') or '').strip()
        item = (row.get('item') or '').strip()
        amount_text = (row.get('amount') or '').strip()
        if not invoice_id or not item or not amount_text:
            raise ValueError('missing invoice_id, item or amount')
        try:
            amount = Decimal(amount_text)
        except InvalidOperation as exc:
            raise ValueError('invalid amount') from exc
        if not amount.is_finite():
            raise ValueError('invalid amount')
        rows.append({'invoice_id': invoice_id, 'item': item, 'amount': amount})
    return rows
''',
            'billing/report.py': '''from decimal import Decimal

def invoice_totals(receipts):
    totals = {}
    for row in receipts:
        key = row['invoice_id']
        totals[key] = totals.get(key, Decimal('0')) + row['amount']
    return {key: str(totals[key]) for key in sorted(totals)}
''',
            'main.py': '''import argparse
import json
from pathlib import Path
from billing.parser import parse_receipts
from billing.report import invoice_totals

def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args(argv)
    totals = invoice_totals(parse_receipts(Path(args.input).read_text(encoding='utf-8')))
    Path(args.output).write_text(json.dumps(totals, sort_keys=True), encoding='utf-8')
    return 0

if __name__ == '__main__':
    raise SystemExit(main(__import__('sys').argv[1:]))
''',
        },
        'private_test': '''import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from billing.parser import parse_receipts
from billing.report import invoice_totals
from main import main

CSV = 'invoice_id,item,amount\\nB,"Cable, long",0.10\\nA,Adapter,3.00\\nB,Refund,-0.05\\nB,Small,0.20\\n'

class TestReceiptProject(unittest.TestCase):
    def test_public_symbols_and_exact_money(self):
        rows = parse_receipts(CSV)
        self.assertEqual(rows[0]['item'], 'Cable, long')
        self.assertIsInstance(rows[0]['amount'], Decimal)
        self.assertEqual(invoice_totals(rows), {'A':'3.00', 'B':'0.25'})
    def test_errors(self):
        for csv_text in ('invoice_id,item,amount\\nA,x,\\n',
                         'invoice_id,item,amount\\nA,x,abc\\n',
                         'invoice_id,item,amount\\nA,,1\\n',
                         'invoice_id,item,amount\\nA,x,NaN\\n',
                         'invoice_id,item\\nA,x\\n'):
            with self.subTest(csv_text=csv_text), self.assertRaises(ValueError):
                parse_receipts(csv_text)
    def test_cli_json(self):
        with tempfile.TemporaryDirectory(dir='/output') as folder:
            input_path = Path(folder)/'in.csv'
            output_path = Path(folder)/'out.json'
            input_path.write_text(CSV)
            self.assertEqual(main(['--input',str(input_path),'--output',str(output_path)]), 0)
            self.assertEqual(json.loads(output_path.read_text()), {'A':'3.00', 'B':'0.25'})
            self.assertLess(output_path.read_text().index('"A"'), output_path.read_text().index('"B"'))
''',
    },
    'cp02': {
        'request': ('Repair the multi-file SQLite task queue. A worker must acknowledge a task only '
                    'after its handler succeeds; acknowledged tasks must not run again after reopening '
                    'the same database. Preserve QueueStore.add, QueueStore.next_task, '
                    'QueueStore.ack and Worker.run_once, FIFO order, and the project files.'),
        'requirements': ['four public methods preserved', 'ack persists across restart',
                         'unacknowledged task remains available', 'FIFO order',
                         'handler failure does not acknowledge', 'no unrelated file removal'],
        'starting_files': {
            'queuepkg/__init__.py': '',
            'queuepkg/store.py': '''import sqlite3

class QueueStore:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.execute('CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY, payload TEXT, done INTEGER DEFAULT 0)')
        self.db.commit()
        self.acked = set()

    def add(self, payload):
        cursor = self.db.execute('INSERT INTO tasks(payload) VALUES (?)', (payload,))
        self.db.commit()
        return cursor.lastrowid

    def next_task(self):
        row = self.db.execute('SELECT id, payload FROM tasks WHERE done = 0 ORDER BY id LIMIT 1').fetchone()
        return row

    def ack(self, task_id):
        self.acked.add(task_id)

    def close(self):
        self.db.close()
''',
            'queuepkg/worker.py': '''class Worker:
    def __init__(self, store, handler):
        self.store = store
        self.handler = handler

    def run_once(self):
        task = self.store.next_task()
        if task is None:
            return False
        task_id, payload = task
        self.handler(payload)
        self.store.ack(task_id)
        return True
''',
            'main.py': '''from queuepkg.store import QueueStore
from queuepkg.worker import Worker

def main(path, handler):
    store = QueueStore(path)
    try:
        return Worker(store, handler).run_once()
    finally:
        store.close()
''',
        },
        'reference_files': {
            'queuepkg/__init__.py': '',
            'queuepkg/store.py': '''import sqlite3

class QueueStore:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.execute('CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY, payload TEXT, done INTEGER DEFAULT 0)')
        self.db.commit()

    def add(self, payload):
        cursor = self.db.execute('INSERT INTO tasks(payload) VALUES (?)', (payload,))
        self.db.commit()
        return cursor.lastrowid

    def next_task(self):
        return self.db.execute('SELECT id, payload FROM tasks WHERE done = 0 ORDER BY id LIMIT 1').fetchone()

    def ack(self, task_id):
        self.db.execute('UPDATE tasks SET done = 1 WHERE id = ?', (task_id,))
        self.db.commit()

    def close(self):
        self.db.close()
''',
            'queuepkg/worker.py': '''class Worker:
    def __init__(self, store, handler):
        self.store = store
        self.handler = handler

    def run_once(self):
        task = self.store.next_task()
        if task is None:
            return False
        task_id, payload = task
        self.handler(payload)
        self.store.ack(task_id)
        return True
''',
            'main.py': '''from queuepkg.store import QueueStore
from queuepkg.worker import Worker

def main(path, handler):
    store = QueueStore(path)
    try:
        return Worker(store, handler).run_once()
    finally:
        store.close()
''',
        },
        'private_test': '''import tempfile
import unittest
from pathlib import Path
from queuepkg.store import QueueStore
from queuepkg.worker import Worker
from main import main

class TestQueueProject(unittest.TestCase):
    def test_persistent_fifo_ack(self):
        with tempfile.TemporaryDirectory(dir='/output') as folder:
            path = Path(folder)/'tasks.sqlite'
            store = QueueStore(path)
            first, second = store.add('first'), store.add('second')
            self.assertLess(first, second)
            seen = []
            self.assertTrue(Worker(store, seen.append).run_once())
            self.assertEqual(seen, ['first'])
            store.close()
            self.assertTrue(main(path, seen.append))
            self.assertEqual(seen, ['first','second'])
            self.assertFalse(main(path, seen.append))
    def test_handler_error_not_acked(self):
        with tempfile.TemporaryDirectory(dir='/output') as folder:
            path = Path(folder)/'tasks.sqlite'
            store = QueueStore(path)
            store.add('retry-me')
            def fail(_):
                raise RuntimeError('handler failed')
            with self.assertRaises(RuntimeError):
                Worker(store, fail).run_once()
            store.close()
            seen = []
            self.assertTrue(main(path, seen.append))
            self.assertEqual(seen, ['retry-me'])
''',
    },
}


def digest_files(files):
    return hashlib.sha256(json.dumps({k: hashlib.sha256(v.encode()).hexdigest() for k, v in sorted(files.items())}, sort_keys=True).encode()).hexdigest()


def main():
    validation = json.loads((ROOT/'data/sandbox-validation.json').read_text())
    if validation.get('verification_version') != SANDBOX_VERIFICATION_VERSION or validation.get('policy_fingerprint') != sandbox_policy_fingerprint() or not 0 <= time.time()-validation['validated_at'] <= SANDBOX_VERIFICATION_MAX_AGE:
        raise RuntimeError('Docker verification missing, stale or mismatched')
    sandbox = CodeSandbox('docker', image_id=validation['image_id'], task_root=HERE/'docker-tasks')
    sandbox._ready()
    rows = []
    for task_id, task in TASKS.items():
        runs = {}
        for name in ('starting_files', 'reference_files'):
            files = {key: value.encode() for key, value in task[name].items()}
            files['test_contract.py'] = task['private_test'].encode()
            result = sandbox.execute(runner('main.py', mode='run', tests=True), timeout=60, input_files=files)
            runs[name] = {'executed': result.executed, 'exit_code': result.exit_code,
                          'stdout': result.stdout, 'stderr': result.stderr,
                          'snapshot_sha256': digest_files(task[name])}
        if not runs['reference_files']['executed'] or runs['reference_files']['exit_code'] != 0 or not runs['starting_files']['executed'] or runs['starting_files']['exit_code'] == 0:
            raise AssertionError(f'Authoring controls failed for {task_id}: {runs}')
        rows.append({'id': task_id, 'request': task['request'], 'requirements': task['requirements'],
                     'private_test_sha256': hashlib.sha256(task['private_test'].encode()).hexdigest(),
                     **runs})
        print(task_id, 'reference PASS; starting FAIL', flush=True)
    (HERE/'complex-project-authoring-results.json').write_text(json.dumps({
        'name': 'Isolated complex project authoring controls', 'status': 'AUTHORING_CONTROLS_ONLY',
        'sandbox_image_id': validation['image_id'], 'rows': rows}, indent=2)+'\n')


if __name__ == '__main__':
    main()
