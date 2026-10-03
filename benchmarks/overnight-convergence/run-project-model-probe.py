"""Fixed warm Coder entry-selection probe; all program execution stays in Docker."""
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
import time
from pathlib import Path

import httpx
import psutil

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from router.sandbox import CodeSandbox, SANDBOX_VERIFICATION_VERSION, SANDBOX_VERIFICATION_MAX_AGE, sandbox_policy_fingerprint
from workflows.code_runtime import runner

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('run_project_fixtures', HERE / 'run-project-probe.py')
fixtures_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures_module)


def current_coder(*, hash_model=False):
    servers = [p for p in psutil.process_iter(['name', 'cmdline']) if p.info['name'] and p.info['name'].lower() == 'llama-server.exe']
    if len(servers) != 1:
        raise RuntimeError(f'Expected one active llama-server; observed {len(servers)}')
    command = servers[0].info['cmdline'] or []
    model = next((command[i + 1] for i, token in enumerate(command[:-1]) if token == '-m'), None)
    if not model or Path(model).name != 'qwen2.5-coder-3b-instruct-q4_k_m.gguf':
        raise RuntimeError('Warm Coder is not the active model; do not switch for this fixed-model probe')
    return {'pid': servers[0].pid, 'model_path': model,
            'model_sha256': hashlib.sha256(Path(model).read_bytes()).hexdigest() if hash_model else None}


def public_context(files):
    allowed = {'README.md', 'package.json', 'pyproject.toml', 'Makefile'}
    return {'files': sorted(files), 'metadata': {name: files[name].decode('utf-8', 'replace')[:1200] for name in sorted(files) if name in allowed}}


def decide(client, files):
    payload = {'model': 'sovereign-code', 'temperature': 0, 'max_tokens': 160, 'stream': False,
               'messages': [
                   {'role': 'system', 'content': 'Select the entry file to run for this local project. Return only JSON {"entry": string|null, "reason": string}. If required dependencies are absent offline or multiple plausible entries remain, return null. Do not invent files. Do not run commands.'},
                   {'role': 'user', 'content': json.dumps(public_context(files), ensure_ascii=False)}]}
    started = time.perf_counter()
    response = client.post('/v1/chat/completions', json=payload)
    response.raise_for_status()
    body = response.json()
    raw = body['choices'][0]['message']['content']
    match = re.search(r'\{.*\}', raw, re.S)
    try:
        parsed = json.loads(match.group(0) if match else raw)
        if not isinstance(parsed, dict) or set(parsed) != {'entry', 'reason'} or parsed['entry'] is not None and not isinstance(parsed['entry'], str) or not isinstance(parsed['reason'], str):
            raise ValueError('Invalid decision schema')
    except (ValueError, TypeError) as exc:
        parsed = {'entry': None, 'reason': 'invalid model JSON: ' + str(exc)}
    return parsed, raw, body.get('usage'), time.perf_counter() - started


def main():
    identity = current_coder(hash_model=True)
    validation = json.loads((ROOT / 'data/sandbox-validation.json').read_text())
    if validation.get('verification_version') != SANDBOX_VERIFICATION_VERSION or validation.get('policy_fingerprint') != sandbox_policy_fingerprint() or not 0 <= time.time()-validation['validated_at'] <= SANDBOX_VERIFICATION_MAX_AGE:
        raise RuntimeError('Docker verification missing, stale or mismatched')
    sandbox = CodeSandbox('docker', image_id=validation['image_id'], task_root=HERE / 'docker-tasks')
    sandbox._ready()
    baseline = json.loads((HERE / 'run-project-probe-results.json').read_text())
    cases = fixtures_module.fixtures()
    rows = []
    with httpx.Client(base_url='http://127.0.0.1:8087', timeout=120) as client:
        for ident, files, expected_target, marker, expected_success in cases:
            if current_coder()['pid'] != identity['pid']:
                raise RuntimeError('Active model changed; stop fixed-model comparison')
            decision, raw, usage, selection_seconds = decide(client, files)
            target = decision['entry']
            row = {'id': ident, 'decision': decision, 'raw_model_output': raw, 'model_usage': usage,
                   'selection_seconds': selection_seconds, 'expected_target': expected_target, 'expected_success': expected_success,
                   'baseline_state': next(x['state'] for x in baseline['rows'] if x['id'] == ident)}
            if target is None:
                row.update(state='DECLINED', docker_executed=False)
            elif target not in files or not target.endswith(('.py', '.js', '.mjs', '.cjs', '.java')):
                row.update(state='INVALID_ENTRY', docker_executed=False)
            else:
                result = sandbox.execute(runner(target, 'run'), timeout=120, input_files=files)
                row.update(state='PASS' if result.executed and result.exit_code == 0 else 'EXECUTION_FAILED' if result.executed else 'BLOCKED_SANDBOX',
                           docker_executed=result.executed, exit_code=result.exit_code, stdout=result.stdout, stderr=result.stderr,
                           marker_present=marker in result.stdout + result.stderr)
            rows.append(row)
            print(ident, row['state'], flush=True)
            (HERE / 'run-project-model-results.json').write_text(json.dumps({'name': 'Fixed warm Coder run-project entry selection',
               'purpose': 'Model-assisted entry selection pilot; not full agent/scaffold evidence',
               'code_revision': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
               'fixture_sha256': baseline['task_sha256'], 'model': identity, 'sandbox_image_id': validation['image_id'], 'rows': rows}, indent=2) + '\n')


if __name__ == '__main__':
    main()
