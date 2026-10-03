"""Isolated, tool-first run-project feasibility probe; never edits product workspaces."""
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from router.sandbox import CodeSandbox, SANDBOX_VERIFICATION_VERSION, SANDBOX_VERIFICATION_MAX_AGE, sandbox_policy_fingerprint
from workflows.code_runtime import runner

OUT = Path(__file__).resolve().parent


def fixtures():
    return [
        ('python-direct', {'README.md': b'Run: python app.py\n', 'app.py': b'print("PY_OK")\n'}, 'app.py', 'PY_OK', True),
        ('python-package', {'pyproject.toml': b'[project]\nname="tinyapp"\nversion="0.1"\n', 'src/main.py': b'print("PY_PACKAGE_OK")\n'}, 'src/main.py', 'PY_PACKAGE_OK', True),
        ('python-broken', {'README.md': b'Run: python main.py\n', 'main.py': b'raise RuntimeError("BROKEN_PY")\n'}, 'main.py', 'BROKEN_PY', False),
        ('node-direct', {'package.json': b'{"name":"tiny","scripts":{"start":"node app.js"}}', 'app.js': b'console.log("NODE_OK")\n'}, 'app.js', 'NODE_OK', True),
        ('node-main', {'package.json': b'{"name":"tiny","main":"src/index.js"}', 'src/index.js': b'console.log("NODE_MAIN_OK")\n'}, 'src/index.js', 'NODE_MAIN_OK', True),
        ('node-broken', {'package.json': b'{"name":"tiny","scripts":{"start":"node app.js"}}', 'app.js': b'throw new Error("BROKEN_NODE")\n'}, 'app.js', 'BROKEN_NODE', False),
        ('java-main', {'README.md': b'Run: javac Main.java && java Main\n', 'Main.java': b'public class Main { public static void main(String[] a) { System.out.println("JAVA_OK"); } }\n'}, 'Main.java', 'JAVA_OK', True),
        ('java-broken', {'Main.java': b'public class Main { public static void main(String[] a) { missing(); } }\n'}, 'Main.java', 'cannot find symbol', False),
        ('vite-unavailable', {'package.json': b'{"name":"tiny-vite","scripts":{"dev":"vite"},"dependencies":{"vite":"*"}}', 'index.html': b'<div id="app"></div>\n'}, None, 'offline dependency required', None),
        ('ambiguous-python', {'one.py': b'print("ONE")\n', 'two.py': b'print("TWO")\n'}, None, 'ambiguous entry point', None),
    ]


def detect(files):
    names = set(files)
    if 'package.json' in names:
        package = json.loads(files['package.json'])
        start = package.get('scripts', {}).get('start', '')
        if start.startswith('node ') and start[5:] in names:
            return start[5:], 'package script'
        main = package.get('main')
        if main in names and main.endswith(('.js', '.mjs', '.cjs')):
            return main, 'package main'
        if 'vite' in json.dumps(package).lower():
            return None, 'offline dependency required'
    for path in ('app.py', 'main.py', 'src/main.py', 'Main.java'):
        if path in names:
            return path, 'recognized entry'
    candidates = [name for name in names if name.endswith(('.py', '.js', '.java'))]
    return (candidates[0], 'single source') if len(candidates) == 1 else (None, 'ambiguous entry point')


def main():
    validation = json.loads((ROOT / 'data/sandbox-validation.json').read_text())
    if validation.get('verification_version') != SANDBOX_VERIFICATION_VERSION or validation.get('policy_fingerprint') != sandbox_policy_fingerprint() or not 0 <= time.time()-validation['validated_at'] <= SANDBOX_VERIFICATION_MAX_AGE:
        raise RuntimeError('Docker verification missing, stale or mismatched')
    sandbox = CodeSandbox('docker', image_id=validation['image_id'], task_root=OUT / 'docker-tasks')
    sandbox._ready()
    cases = fixtures()
    task_hash = hashlib.sha256(json.dumps([(i, sorted((k, v.decode()) for k, v in f.items()), t, marker, expected) for i, f, t, marker, expected in cases], sort_keys=True).encode()).hexdigest()
    rows = []
    for ident, files, expected_target, marker, expected_success in cases:
        started = time.perf_counter()
        target, reason = detect(files)
        if target is None:
            rows.append({'id': ident, 'target': None, 'reason': reason, 'state': 'BLOCKED_DEPENDENCY' if reason == 'offline dependency required' else 'NEEDS_INPUT', 'expected_marker': marker, 'elapsed_seconds': time.perf_counter()-started, 'docker_executed': False})
        else:
            result = sandbox.execute(runner(target, mode='run'), timeout=120, input_files=files)
            stream = result.stdout + result.stderr
            rows.append({'id': ident, 'target': target, 'reason': reason, 'state': 'PASS' if result.executed and result.exit_code == 0 else 'EXECUTION_FAILED' if result.executed else 'BLOCKED_SANDBOX', 'exit_code': result.exit_code, 'stdout': result.stdout, 'stderr': result.stderr, 'marker_present': marker in stream, 'expected_success': expected_success, 'expected_target': expected_target, 'elapsed_seconds': time.perf_counter()-started, 'docker_executed': result.executed})
        print(ident, rows[-1]['state'], flush=True)
    report = {'name': 'Overnight run-project tool-first feasibility', 'purpose': 'Fixture validation, not agent or model evaluation', 'task_sha256': task_hash, 'code_revision': __import__('subprocess').check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(), 'sandbox_image_id': validation['image_id'], 'rows': rows}
    (OUT / 'run-project-probe-results.json').write_text(json.dumps(report, indent=2)+'\n')
    assert len(rows) == 10
    assert all(row['target'] == target and row['marker_present'] and (row['state'] == 'PASS') == expected for row, (_, _, target, _, expected) in zip(rows[:8], cases[:8]))
    assert rows[8]['state'] == 'BLOCKED_DEPENDENCY' and rows[9]['state'] == 'NEEDS_INPUT'


if __name__ == '__main__':
    main()
