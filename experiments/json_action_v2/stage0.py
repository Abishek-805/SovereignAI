"""Read-only source/wire audit; never calls a completion or acquires a lease."""
import hashlib
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
import subprocess
import urllib.request

import psutil
from experiments.fidelity_v1.run_status import inspect_status
from experiments.fidelity_v1.tasks import OUT

ROOT = Path(__file__).resolve().parents[2]
DEST = ROOT / 'evidence/json-action-adapter-v2'
OLD = ROOT / 'evidence/t10-exact-replay/20261007-202627'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(name, value):
    (DEST / 'stage-0' / name).write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding='utf-8')


def inventory(value, path='', result=None):
    result = defaultdict(lambda: {'occurrences': 0, 'characters': 0, 'types': set()}) if result is None else result
    if isinstance(value, dict):
        for key, item in value.items(): inventory(item, path + '.' + key if path else key, result)
    elif isinstance(value, list):
        for item in value: inventory(item, path + '[]', result)
    elif value is not None and value != '':
        row = result[path]; row['occurrences'] += 1; row['types'].add(type(value).__name__)
        if isinstance(value, str): row['characters'] += len(value)
    return result


def processes():
    rows = []
    for process in psutil.process_iter(['pid', 'name', 'cmdline', 'create_time']):
        try:
            command = process.info['cmdline'] or []
            name = (process.info['name'] or '').lower()
            # Ignore shells whose script text includes these names.
            if name.startswith('llama-server') or (name.startswith('python') and any(
                    marker in command for marker in ['experiments.fidelity_v1.evaluate', 'backend.app:create_app'])):
                rows.append(process.info)
        except psutil.Error: pass
    return rows


def main():
    manifest = json.loads((DEST / 'manifest.json').read_text(encoding='utf-8'))
    assert digest(DEST / 'PREREGISTRATION.md') == manifest['preregistration_sha256']
    for path, expected in manifest['frozen_sha256'].items(): assert digest(ROOT / path) == expected, path
    write('run-status.json', inspect_status(OUT))
    write('processes.json', processes())
    nonstream = json.loads((OLD / 'nonstream.response.body').read_text(encoding='utf-8'))
    events = []
    wire = (OLD / 'stream.response.body').read_text(encoding='utf-8')
    done = 0
    for line in wire.splitlines():
        if not line.startswith('data:'): continue
        data = line[5:].strip()
        if data == '[DONE]': done += 1
        else: events.append(json.loads(data))
    summaries = {}
    for mode, bodies in [('nonstream', [nonstream]), ('stream', events)]:
        fields = defaultdict(lambda: {'occurrences': 0, 'characters': 0, 'types': set()})
        strings = defaultdict(list); representations = []; finish = []; usage = []
        for body in bodies:
            inventory(body, result=fields)
            if body.get('usage'): usage.append(body['usage'])
            for choice in body.get('choices', []):
                if choice.get('finish_reason'): finish.append(choice['finish_reason'])
                message = choice.get('message', choice.get('delta', {}))
                for key, value in message.items():
                    if isinstance(value, str): strings[key].append(value)
                    if key not in {'content', 'reasoning_content', 'role'} and value not in (None, '', [], {}):
                        representations.append({'field': key, 'value': value})
        merged = {key: ''.join(parts) for key, parts in strings.items()}
        parsed = json.loads((OLD / (mode + '.parsed.json')).read_text(encoding='utf-8'))
        summaries[mode] = {'event_count': len(bodies), 'finish_reasons': finish, 'usage': usage,
            'string_characters': {key: len(text) for key, text in merged.items()},
            'content_sha256': hashlib.sha256(merged.get('content', '').encode()).hexdigest(),
            'alternate_message_fields': representations,
            'field_inventory': {key: {**row, 'types': sorted(row['types'])} for key, row in fields.items()},
            'preserved_parsed_keys': list(parsed), 'fingerprints': sorted({b.get('system_fingerprint', '') for b in bodies})}
    summaries['content_identical'] = summaries['stream']['content_sha256'] == summaries['nonstream']['content_sha256']
    summaries['sse_done_markers'] = done
    write('response-fields.json', summaries)
    requests = {mode: json.loads((OLD / (mode + '.request.json')).read_text(encoding='utf-8')) for mode in ['stream', 'nonstream']}
    write('request-settings.json', {mode: {key: payload.get(key, 'NOT SUPPLIED') for key in
        ['model', 'stream', 'temperature', 'seed', 'max_tokens', 'tool_choice', 'response_format', 'chat_template_kwargs']} for mode, payload in requests.items()})
    runtime = {'captured_at': datetime.now(timezone(timedelta(hours=5, minutes=30))).isoformat(), 'timezone': 'Asia/Calcutta', 'historical_command': json.loads((OLD / 'runtime.json').read_text())}
    for endpoint in ['props', 'slots', 'v1/models']:
        try:
            with urllib.request.urlopen('http://127.0.0.1:8087/' + endpoint, timeout=5) as response:
                runtime[endpoint] = {'status': response.status, 'headers': dict(response.headers), 'body': json.load(response)}
        except Exception as exc: runtime[endpoint] = {'status': 'UNAVAILABLE', 'error': str(exc), 'effective_state': 'UNKNOWN'}
    try:
        result = subprocess.run(['docker', 'ps', '--no-trunc', '--format', '{{json .}}'], capture_output=True, text=True, timeout=15)
        runtime['docker_ps'] = {'exit_code': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr}
    except Exception as exc: runtime['docker_ps'] = {'status': 'UNAVAILABLE', 'error': str(exc)}
    write('current-runtime.json', runtime)
    changes = [path for path, expected in manifest['frozen_sha256'].items() if digest(ROOT / path) != expected]
    write('integrity.json', {'unchanged': not changes, 'changed_paths': changes, 'model_calls': 0, 'tool_dispatches': 0,
                            'docker_executions': 0, 'preregistration_unchanged': digest(DEST / 'PREREGISTRATION.md') == manifest['preregistration_sha256']})
    assert not changes
    print(json.dumps({key: {name: value for name, value in row.items() if name != 'field_inventory'} if isinstance(row, dict) else row for key, row in summaries.items()}, indent=2))


if __name__ == '__main__': main()
