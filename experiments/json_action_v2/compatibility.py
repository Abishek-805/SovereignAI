"""Raw Stage 1 metadata/completion capture; never dispatches actions."""
import copy
import hashlib
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from experiments.fidelity_v1.runners import load_native
from experiments.fidelity_v1.run_status import inspect_status
from experiments.fidelity_v1.tasks import OUT


def post(directory, payload, endpoint='v1/chat/completions'):
    directory.mkdir(parents=True, exist_ok=False)
    raw = json.dumps(payload, ensure_ascii=False).encode()
    (directory/'request.json').write_bytes(raw)
    headers = {'Content-Type': 'application/json'}
    (directory/'request-headers.json').write_text(json.dumps(headers))
    started = time.monotonic()
    result = {'endpoint': endpoint, 'request_sha256': hashlib.sha256(raw).hexdigest()}
    try:
        with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8087/'+endpoint, data=raw, headers=headers), timeout=620) as response:
            body = response.read(); status = response.status; returned_headers = dict(response.headers)
    except urllib.error.HTTPError as error:
        body = error.read(); status = error.code; returned_headers = dict(error.headers)
    except Exception as error:
        result.update(status='TRANSPORT_ERROR', error=str(error), latency=time.monotonic()-started)
        (directory/'result.json').write_text(json.dumps(result, indent=2)); raise
    (directory/'response.body').write_bytes(body)
    (directory/'response-headers.json').write_text(json.dumps(returned_headers, indent=2))
    result.update(status=status, latency=time.monotonic()-started)
    try: result['response'] = json.loads(body)
    except ValueError: result['parse_error'] = True
    (directory/'result.json').write_text(json.dumps(result, indent=2))
    return result


def main():
    execution = Path(sys.argv[1]); base = execution.parent
    manifest = json.loads((base/'experiment-manifest.json').read_text())
    assert hashlib.sha256((base/'PREREGISTRATION.md').read_bytes()).hexdigest() == manifest['preregistration_sha256']
    assert not inspect_status(OUT)['running_verified']
    with urllib.request.urlopen('http://127.0.0.1:8087/slots', timeout=5) as response:
        assert not any(row['is_processing'] for row in json.load(response))
    schema = {'type':'object','properties':{'ok':{'type':'boolean','const':True}},'required':['ok'],'additionalProperties':False}
    payload = {'model':'sovereign-text','messages':[{'role':'user','content':'Return only a JSON object with ok set to true.'}],
               'temperature':0,'max_tokens':4096,'chat_template_kwargs':{'enable_thinking':False},
               'response_format':{'type':'json_schema','json_schema':{'name':'compatibility','strict':True,'schema':schema}}}
    first = post(base/'compatibility'/execution.name/'schema-only', payload)
    print('schema-only', first['status'], flush=True)
    if first['status'] != 200:
        fallback = copy.deepcopy(payload); fallback.pop('response_format')
        fallback['grammar'] = 'root ::= "{" ws "\\\"ok\\\"" ws ":" ws "true" ws "}"\nws ::= [ \\t\\n\\r]*'
        result = post(base/'compatibility'/execution.name/'same-schema-gbnf', fallback)
        print('fallback', result['status']); return
    native = load_native(); registry = native.ToolRegistry()
    combined = copy.deepcopy(payload)
    combined.update(tools=[registry.schemas()[0]], tool_choice='auto', parallel_tool_calls=False)
    second = post(base/'compatibility'/execution.name/'schema-plus-tools', combined)
    print('schema-plus-tools', second['status'], flush=True)


if __name__ == '__main__': main()
