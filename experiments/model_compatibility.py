"""Sequential runtime smoke checks; preserves original runtime command.

Compatibility output is not validated task-completion evidence.
"""
import json
from pathlib import Path
import subprocess
import time
import sys
from datetime import datetime, timezone
from benchmark_resources import ResourceSamples
import httpx
import psutil

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'benchmarks/model-comparison'


def servers():
    return [p for p in psutil.process_iter(['name','cmdline'])
            if (p.info['name'] or '').lower()=='llama-server.exe']


def launch(command, stdout, stderr):
    return subprocess.Popen(command,cwd=ROOT,stdout=stdout,stderr=stderr,
                            creationflags=subprocess.CREATE_NO_WINDOW)


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    # Evidence I/O maintenance only; all frozen worker/fixture hashes stay exact.
    if '--tasks' in sys.argv:
        from evidence_io import install
        install(ROOT)
    existing=servers()
    if len(existing)>1:raise RuntimeError('Multiple existing model servers; abort')
    original=existing[0].info['cmdline'] if existing else None
    if existing:
        response=httpx.get('http://127.0.0.1:8087/slots',timeout=5)
        response.raise_for_status()
        slots=response.json()
        if not isinstance(slots,list) or any(s.get('is_processing') for s in slots):
            raise RuntimeError('Existing runtime is busy or idle state cannot be verified')
        existing[0].terminate()
        existing[0].wait(timeout=20)
    candidates=[('coder','models/qwen2.5-coder-3b-instruct-q4_k_m.gguf'),
                ('granite','models/Granite-4.2-3B/granite-4.2-3b-Q4_K_M.gguf'),
                ('mini-coder','models/mini-coder-1.7B/mini-coder-1.7b-iq4_nl-imat.gguf'),
                ('qwen3.5','models/Qwen3.5-4B-Q4_K_M.gguf')]
    rows=[]
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    log_directory = OUT/'runtime-runs'/run_id
    log_directory.mkdir(parents=True,exist_ok=True)
    try:
        for name,path in candidates:
            if servers():raise RuntimeError('Another heavy server appeared; abort')
            command=[str(ROOT/'runtime/llama-b11132/llama-server.exe'),'-m',str(ROOT/path),
                     '-c','4096','-ngl','999','-np','1','--host','127.0.0.1','--port','8087']
            row={'model':name,'command':command,'status':'STARTING'}
            baseline = ResourceSamples(0)
            baseline.sample()
            row['baseline_resources'] = baseline.samples[-1]
            rows.append(row)
            with (log_directory/(name+'-stdout.log')).open('w') as out,(log_directory/(name+'-stderr.log')).open('w') as err:
                process=launch(command,out,err)
                started=time.monotonic()
                try:
                    while time.monotonic()-started<90:
                        if process.poll() is not None:raise RuntimeError('Runtime exited '+str(process.returncode))
                        try:
                            health=httpx.get('http://127.0.0.1:8087/health',timeout=2)
                            if health.status_code==200:break
                        except httpx.HTTPError:pass
                        time.sleep(.5)
                    else:raise TimeoutError('Runtime readiness deadline')
                    row['load_seconds'] = time.monotonic()-started
                    row['pid'] = process.pid
                    response=httpx.post('http://127.0.0.1:8087/v1/chat/completions',timeout=60,json={
                        'model':name,'messages':[{'role':'user','content':'Return JSON with one key ready and value true.'}],
                        'temperature':0,'max_tokens':128,'response_format':{'type':'json_object'}})
                    response.raise_for_status()
                    row.update(status='API_RESPONSE',response=response.json(),elapsed_seconds=time.monotonic()-started,
                               rss_bytes=psutil.Process(process.pid).memory_info().rss)
                    if '--tasks' in sys.argv:
                        from model_task_tranche import run
                        task_rows = run(name, path)
                        row['authored_task_count'] = len(task_rows)
                        row['validated_task_passes'] = sum(r['result']['state']=='READY_FOR_REVIEW' for r in task_rows)
                    try:
                        row['gpu_observation']=subprocess.check_output(['nvidia-smi','--query-gpu=memory.used,memory.total',
                            '--format=csv,noheader,nounits'],text=True,timeout=3).strip()
                    except Exception as error:row['gpu_observation_error']=type(error).__name__
                except Exception as error:row.update(status='BLOCKED',error=type(error).__name__+': '+str(error))
                finally:
                    unloading = time.monotonic()
                    if process.poll() is None:process.terminate()
                    process.wait(timeout=20)
                    row['unload_seconds'] = time.monotonic()-unloading
                    row['final_returncode'] = process.returncode
                    row['heavy_servers_after_unload'] = [p.pid for p in servers()]
            result_name = 'task-tranche-runtime.json' if '--tasks' in sys.argv else 'compatibility.json'
            (OUT/result_name).write_text(json.dumps({'not_task_quality_evidence':True,'rows':rows},indent=2))
            (log_directory/'runtime-results.json').write_text(json.dumps({'rows':rows},indent=2))
            print(name,row['status'],flush=True)
    finally:
        if original and not servers():
            with (OUT/'restored-runtime.log').open('w') as log:
                restored=launch(original,log,log)
                (OUT/'restored-runtime.json').write_text(json.dumps({'pid':restored.pid,'command':original}))


if __name__=='__main__':main()
