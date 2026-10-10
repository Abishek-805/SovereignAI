"""Record bounded acceptance requests against the active local application."""
import json, time, hashlib, sys
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parents[2]
OUT = Path((ROOT/'experiments/universal_skill/production-readiness-output.txt').read_text().strip())
def save(name, value):
    (OUT/name).write_text(json.dumps(value, indent=2, default=str), encoding='utf-8')

with httpx.Client(base_url=sys.argv[1] if len(sys.argv)>1 else 'http://127.0.0.1:8088', timeout=60) as client:
    docs = client.get('/documents').raise_for_status().json()
    save('documents.json', docs)
    scope = [d['document_id'] for d in docs]
    cases = [('overview', 'Tell me about KPR college.'),
             ('missing_rationale', 'Why did 24ALR051 receive 6 in WAT 2?'),
             ('exact_id', 'give me total professional skill test of 24ALR051'),
             ('missing_id', 'give me total professional skill test of 99ZZZ999'),
             ('missing_file', 'What does unavailable-lifecycle-reference.txt say?'),
             ('cancellation', 'Tell me about KPR college.')]
    results = []
    for name, goal in cases:
        payload = {'goal': goal, 'document_ids': scope}
        started = time.perf_counter()
        job = client.post('/agent/jobs', json=payload).raise_for_status().json()
        trace = [job]; stopped = False
        while job['state'] == 'running':
            if name == 'cancellation' and not stopped and job.get('partial_answer'):
                client.post('/coding/jobs/'+job['job_id']+'/stop').raise_for_status()
                stopped = True
            if time.perf_counter()-started > 240:
                client.post('/coding/jobs/'+job['job_id']+'/stop')
                raise RuntimeError('Acceptance request exceeded 240 seconds: '+name)
            time.sleep(.3)
            job = client.get('/coding/jobs/'+job['job_id']).raise_for_status().json()
            trace.append(job)
        results.append({'case': name, 'request': payload, 'seconds': time.perf_counter()-started,
                        'stop_sent': stopped, 'snapshots': trace})
        save('live-requests.json', results)
        print(name, job['state'], job.get('error'), flush=True)
    save('status.json', client.get('/status').raise_for_status().json())
manifest = json.loads((ROOT/'evidence/rag-lifecycle-followup/1791525271511/protected-manifest.json').read_text())
changed = [p for p,h in manifest.items() if not (ROOT/p).exists() or hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=h]
save('protected-integrity.json', {'checked': len(manifest), 'changed': changed})
