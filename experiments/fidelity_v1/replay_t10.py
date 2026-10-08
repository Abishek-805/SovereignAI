"""Exact saved call-8 transport diagnostic. No generated actions are executed."""
import copy
import hashlib
import json
import time
from pathlib import Path

import httpx
import psutil

from backend.model import LocalModel
from experiments.fidelity_v1.evaluate import current_identity, servers, sources_unchanged
from experiments.fidelity_v1.run_status import write_atomic
from experiments.fidelity_v1.tasks import OUT
from router.model_registry import ModelRegistry, PID_FILE, RUNTIME


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False).encode('utf-8')


def paired_payloads(payload):
    streaming = copy.deepcopy(payload)
    plain = copy.deepcopy(payload)
    streaming['stream'] = True
    plain['stream'] = False
    assert {k: v for k, v in plain.items() if k != 'stream'} == {k: v for k, v in streaming.items() if k != 'stream'}
    return [('stream', streaming), ('nonstream', plain)]


def summarize(result):
    choice = result.get('choices', [{}])[0]
    message = choice.get('message', {})
    return {'finish_reason': choice.get('finish_reason'), 'tool_calls': message.get('tool_calls', []),
            'public_content_characters': len(message.get('content') or ''), 'usage': result.get('usage'),
            'reasoning_tokens': (result.get('usage') or {}).get('completion_tokens_details', {}).get('reasoning_tokens')}


def main():
    sources_unchanged()
    source = OUT / 'native/T10/attempt-02/call-008.json'
    record = json.loads(source.read_text(encoding='utf-8'))
    directory = OUT.parent / 't10-exact-replay' / time.strftime('%Y%m%d-%H%M%S')
    directory.mkdir(parents=True)
    write_atomic(directory / 'manifest.json', {'source': str(source), 'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
                 'scope': 'diagnostic replay only; no tools executed; no baseline outcomes replaced',
                 'allowed_request_difference': ['stream'], 'production_migrated': False})
    # Refuse an existing heavy worker: this diagnostic never preempts another task.
    if servers():
        raise RuntimeError('Existing heavy worker: replay requires an exclusive empty runtime window')
    try:
        status = httpx.get('http://127.0.0.1:8088/status', timeout=3, trust_env=False).json()
        if status.get('busy') or status.get('active_jobs'):
            raise RuntimeError('Production has an active task')
    except httpx.ConnectError:
        pass  # Backend offline; no model process exists, checked above.
    registry = ModelRegistry()
    original_args = json.loads((OUT / 'reports/lease-runners-qwen35.json').read_text())['identity']['command']
    if registry.launch_args('text')[1:] != original_args[1:]:
        raise RuntimeError('Runtime configuration differs from frozen Qwen worker')
    if PID_FILE.exists():
        saved = PID_FILE.read_bytes()
        pid = int(saved.decode().strip())
        try:
            process = psutil.Process(pid)
            if Path(process.exe()).resolve() == RUNTIME.resolve():
                raise RuntimeError('Runtime PID exists; do not clear or preempt it')
            stale = {'saved_pid': pid, 'observed_process_name': process.name(), 'reason': 'PID reused by unrelated process; not terminated'}
        except psutil.NoSuchProcess:
            stale = {'saved_pid': pid, 'reason': 'process no longer exists'}
        if servers() or PID_FILE.read_bytes() != saved:
            raise RuntimeError('Runtime ownership changed during admission')
        write_atomic(directory / 'stale-pid-adjudication.json', stale)
        PID_FILE.replace(directory / 'server.pid.stale')
    try:
        registry.acquire_lease('text')
        write_atomic(directory / 'runtime.json', current_identity())
        results = []
        with httpx.Client(timeout=700, trust_env=False) as client:
            for name, payload in paired_payloads(record['request']):
                write_atomic(directory / (name + '.request.json'), payload)
                start = time.monotonic()
                body_path = directory / (name + '.response.body')
                with client.stream('POST', 'http://127.0.0.1:8087/v1/chat/completions', json=payload) as response:
                    headers = dict(response.headers)
                    write_atomic(directory / (name + '.response.headers.json'), {'status': response.status_code, 'headers': headers})
                    with body_path.open('wb') as output:
                        for chunk in response.iter_bytes():
                            output.write(chunk)
                            output.flush()
                    response.raise_for_status()
                body = body_path.read_bytes()
                if name == 'stream':
                    # Feed captured bytes through the production parser offline.
                    transport = httpx.MockTransport(lambda request: httpx.Response(200, headers=headers, content=body))
                    adapter = LocalModel(transport=transport)
                    try:
                        parsed = adapter._stream_job_completion(json=payload)
                    finally:
                        adapter.client.close()
                    chunks = [json.loads(line[5:].strip()) for line in body.decode('utf-8').splitlines()
                              if line.startswith('data:') and line[5:].strip() != '[DONE]']
                    raw_tool_fragments = sum(len(c.get('delta', {}).get('tool_calls', [])) for chunk in chunks for c in chunk.get('choices', []))
                else:
                    parsed = json.loads(body)
                    raw_tool_fragments = len(parsed.get('choices', [{}])[0].get('message', {}).get('tool_calls', []))
                write_atomic(directory / (name + '.parsed.json'), parsed)
                results.append({'transport': name, 'latency_seconds': time.monotonic() - start,
                                'raw_tool_fragments': raw_tool_fragments, **summarize(parsed)})
                write_atomic(directory / 'results.json', {'status': 'COMPLETE' if len(results) == 2 else 'INCOMPLETE', 'results': results,
                             'request_only_difference': 'stream', 'no_generated_code_executed': True,
                             'limitations': ['Warm cache/order confound; this is a paired transport diagnostic, not a latency ranking.',
                                             'Sampled output variation does not by itself prove runtime or model causality.']})
                print(name, summarize(parsed), flush=True)
    except BaseException as exc:
        write_atomic(directory / 'interruption.json', {'error': str(exc), 'existing_evidence_preserved': True})
        raise
    finally:
        if registry._owns_server():
            slots = httpx.get('http://127.0.0.1:8087/slots', timeout=5).json()
            if all(not s.get('is_processing') for s in slots):
                registry.kill_server()
    print('Evidence:', directory, flush=True)


if __name__ == '__main__':
    main()
