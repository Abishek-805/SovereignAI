"""Small local smoke test, not an accuracy benchmark. Saves raw outputs."""
import json
from pathlib import Path
import time
import urllib.request

cases = [
    ('grounding', 'Source [Report p.2]: Pump P-101 vibration measured 8.2 mm/s. Source [SOP p.7]: Investigate vibration above 7.1 mm/s. In under 100 words, identify the finding, cite the sources, and say whether these sources authorize shutdown. Do not invent instructions.'),
    ('missing_evidence', 'Source [Report p.3]: Motor M-2 temperature was 78 degrees Celsius. No permitted temperature limit is supplied. Is the motor above its permitted temperature? Answer in at most 50 words, using only the supplied evidence.'),
    ('structured_extraction', 'Return only JSON with keys equipment, reading, unit, source_page. Source page 4: Pump P-104 pressure was 6.2 bar.'),
]
results = []
for name, prompt in cases:
    payload = {'messages': [{'role': 'system', 'content': 'You are a concise industrial document assistant. Use only supplied sources.'}, {'role': 'user', 'content': prompt}], 'temperature': 0, 'max_tokens': 256, 'stream': True, 'stream_options': {'include_usage': True}}
    request = urllib.request.Request('http://127.0.0.1:8087/v1/chat/completions', data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
    start = time.perf_counter()
    first = None
    answer = ''
    usage = None
    timings = None
    finish = None
    with urllib.request.urlopen(request, timeout=180) as response:
        for raw in response:
            line = raw.decode().strip()
            if not line.startswith('data: ') or line == 'data: [DONE]':
                continue
            event = json.loads(line[6:])
            if event.get('usage'):
                usage = event['usage']
            if event.get('timings'):
                timings = event['timings']
            for choice in event.get('choices', []):
                content = choice.get('delta', {}).get('content') or ''
                if content and first is None:
                    first = time.perf_counter() - start
                answer += content
                finish = choice.get('finish_reason') or finish
    item = {'case': name, 'prompt': prompt, 'answer': answer, 'ttft_seconds': first, 'elapsed_seconds': time.perf_counter() - start, 'usage': usage, 'timings': timings, 'finish_reason': finish}
    results.append(item)
    print(json.dumps(item, indent=2), flush=True)
output = Path(__file__).with_name('smoke-results.json')
output.write_text(json.dumps(results, indent=2), encoding='utf-8')
