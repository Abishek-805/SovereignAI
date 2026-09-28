"""Stop only this acceptance job; observe runtime state, never cancel a slot globally."""
import json,time,httpx
from pathlib import Path
c=httpx.Client(base_url='http://127.0.0.1:8088',timeout=30,trust_env=False)
runtime=httpx.Client(base_url='http://127.0.0.1:8087',timeout=5,trust_env=False)
warm=c.post('/agent/jobs',json={'goal':'What is two plus two?','document_ids':[],'history':[]});warm.raise_for_status();warm_id=warm.json()['job_id']
while True:
 warm_snap=c.get('/coding/jobs/'+warm_id).json()
 if warm_snap['state']!='running':break
 time.sleep(.2)
assert warm_snap['state']=='completed',warm_snap
started=time.perf_counter();snap=c.post('/agent/jobs',json={'goal':'Explain how to fix errors in a JavaScript project, including debugging, tests, dependency management, and runtime errors.','document_ids':[],'history':[]}).json()
assert snap.get('job_id'),snap
jid=snap['job_id'];observations=[];deadline=time.perf_counter()+90
while time.perf_counter()<deadline:
 snap=c.get('/coding/jobs/'+jid).json()
 try:slots=runtime.get('/slots').json()
 except Exception as exc:slots={'unavailable':str(exc)}
 observations.append({'seconds':round(time.perf_counter()-started,3),'job_state':snap['state'],'slots':slots})
 if snap['state']!='running':raise AssertionError('Job finished before Stop: '+json.dumps(snap))
 # The pinned runtime exposes is_processing plus next_token counters when available.
 if time.perf_counter()-started>5 and isinstance(slots,list) and any(s.get('is_processing') for s in slots):break
 time.sleep(.25)
else:
 c.post('/coding/jobs/'+jid+'/stop').raise_for_status()
 raise AssertionError('No processing slot observed before Stop')
stop=time.perf_counter();ack=c.post('/coding/jobs/'+jid+'/stop');ack.raise_for_status()
while time.perf_counter()-stop<30:
 snap=c.get('/coding/jobs/'+jid).json()
 if snap['state']!='running':break
 time.sleep(.1)
assert snap['state']=='cancelled',snap
cancel_latency=round(time.perf_counter()-stop,3)
idle=None
for _ in range(30):
 try:
  slots=runtime.get('/slots').json()
  if isinstance(slots,list) and all(not s.get('is_processing',False) for s in slots):idle=round(time.perf_counter()-stop,3);break
 except Exception:pass
 time.sleep(.1)
result={'warmup':warm_snap,'request':'Long general tutorial, no files or code','time_before_stop_seconds':round(stop-started,3),'cancelled_job_latency_seconds':cancel_latency,'observed_runtime_idle_after_stop_seconds':idle,'job':snap,'observations':observations,'final_slots':slots}
Path('benchmarks/final-router-stop-results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({key:result[key] for key in ('request','time_before_stop_seconds','cancelled_job_latency_seconds','observed_runtime_idle_after_stop_seconds')},ensure_ascii=False),flush=True)
c.close();runtime.close()
