"""Actual HTTP calculator checks; no generation or model management calls."""
import json
from pathlib import Path
from statistics import median
from time import perf_counter
import httpx

output=Path(__file__).with_name('cpu-calculator-live-results.json')
if output.exists():
    prior=json.loads(output.read_text(encoding='utf-8'))
    if 'source_sha256' not in prior:
        prior['valid_for_latency_claims']=False
        prior['collection_error']='Initial comprehension reused a previous response for streamed cases; timings and sample count are invalid. Superseded by explicit request loop.'
        output.with_name('cpu-calculator-live-results-invalid-draft.json').write_text(json.dumps(prior,indent=2),encoding='utf-8')
rows=[]
with httpx.Client(base_url='http://127.0.0.1:8088',timeout=20) as client:
    for expression in ['18.5 * 24','(144 / 12) + 7','sqrt(196)','(-3 + 8) / 2']:
        for stream in (False,True):
            for repetition in range(3):
                started=perf_counter()
                response=client.post('/v1/chat/completions',json={'messages':[{'role':'user','content':expression}],'stream':stream})
                seconds=perf_counter()-started
                response.raise_for_status()
                decision=client.get('/routing/decisions/'+response.headers['x-sovereign-request-id']).raise_for_status().json()
                assert decision['selected_model'] is None and decision['inference_time'] is None and decision['evidence_used'] is False
                if stream:assert response.text.endswith('data: [DONE]\n\n')
                rows.append({'expression':expression,'stream':stream,'repetition':repetition,'seconds':seconds,'status':response.status_code,'response':response.text if stream else response.json(),'decision':decision})
import hashlib
data={'valid_for_latency_claims':True,'sample_count':len(rows),'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'boundary':'HTTP request through full response completion; subsequent routing lookup excluded','median_seconds':median(row['seconds'] for row in rows),'p95_seconds':None,'samples':rows}
output.write_text(json.dumps(data,indent=2),encoding='utf-8')
print(json.dumps({key:value for key,value in data.items() if key!='samples'}))
