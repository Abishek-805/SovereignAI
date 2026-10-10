"""Fresh-process dataset-envelope probes; no full training entrypoint."""
import hashlib, importlib.metadata, json, os, subprocess, sys, time, zipfile
from pathlib import Path

ROOT=Path(__file__).parent
DATA=ROOT/'package'
OUT=ROOT/'results'
OUT.mkdir(exist_ok=False)
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v): p.write_text(json.dumps(v,indent=2)+'\n')
def extract(p,d):
    with zipfile.ZipFile(p) as z:
        assert z.testzip() is None
        assert all(not Path(n).is_absolute() and '..' not in Path(n).parts for n in z.namelist())
        z.extractall(d)
package=ROOT/'sovereignai-pretraining-readiness-colab.zip'
assert sha(package)=='11179a62a2fb762dd81920e975ece57d20741316abd7382b1d1d995ea2b209d3'
extract(package,DATA)
# Recover metadata and prior raw stress evidence without rerunning baseline or dense stress.
prior=ROOT/'prior-evidence'
extract(ROOT/'sovereignai-final-readiness-probes.zip',prior)
manifest=json.loads((prior/'final-artifact-hashes.json').read_text())
assert all(sha(prior/n)==h for n,h in manifest.items())
stats=prior/'training-supervised-target-stats.json'
versions={n:importlib.metadata.version(n) for n in ['torch','transformers','peft','bitsandbytes','accelerate','datasets']}
assert versions=={'torch':'2.11.0+cu130','transformers':'5.19.0','peft':'0.21.1','bitsandbytes':'0.50.2','accelerate':'1.15.0','datasets':'4.8.5'},versions
save(OUT/'source-identity.json',{'versions':versions,'package_sha256':sha(package),'prior_archive_sha256':sha(ROOT/'sovereignai-final-readiness-probes.zip'),'source_hashes':{p.name:sha(p) for p in ROOT.glob('*.py')},'RUN_TRAIN':False})
env=dict(os.environ,PYTHONPATH=str(ROOT),PYTHONHASHSEED='42',CUBLAS_WORKSPACE_CONFIG=':4096:8')
progress=[]
# real0 is both the actual maximum-target check and first of the top-three turns.
for probe in ['real0','target26','target85','target113','target191','target243','real1','real2']:
    assert not subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader'],text=True).strip()
    print('START',probe,flush=True)
    with (OUT/(probe+'.log')).open('w') as log:
        try:
            rc=subprocess.run([sys.executable,str(ROOT/'final_probes.py'),probe,'--data',str(DATA),'--output',str(OUT/probe),'--stats',str(stats)],env=env,stdout=log,stderr=subprocess.STDOUT,timeout=900).returncode
        except subprocess.TimeoutExpired: rc=124
    result_path=OUT/probe/'result.json'
    result=json.loads(result_path.read_text()) if result_path.exists() else {'status':'NOT_COMPLETED'}
    progress.append({'probe':probe,'exit_code':rc,'raw_status':result['status'],'status':result['status'] if rc!=124 else 'NOT_COMPLETED_TIMEOUT','OOM':result.get('OOM',False),'error':result.get('error')})
    save(OUT/'progress.json',progress)
    print('RESULT',json.dumps(progress[-1]),flush=True)
    if rc and not result.get('OOM'): break
rows=[]
for p in progress:
    result=json.loads((OUT/p['probe']/'result.json').read_text()) if (OUT/p['probe']/'result.json').exists() else {}
    samples=result.get('measurements',[])
    capacity=max((v['device_memory']['capacity_bytes'] for v in samples),default=0)
    allocated=max((v['memory']['peak_allocated'] for v in samples),default=0)
    reserved=max((v['memory']['peak_reserved'] for v in samples),default=0)
    rows.append(dict(p,source_id=result.get('source_id'),source_turn=result.get('source_turn'),source_tokens=result.get('source_tokens'),targets=result.get('supervised_targets',result.get('source_target_count')),input_tokens=result.get('input_tokens'),loss=result.get('current_microbatch',{}).get('loss'),backward=result.get('backward_success',False),optimizer=result.get('optimizer_success',False),base_unchanged=result.get('base_hash_unchanged',False),adapter_changed=result.get('adapter_parameters_changed',False),peak_allocated=allocated,peak_reserved=reserved,capacity=capacity,capacity_minus_peak_allocated=capacity-allocated,capacity_minus_peak_reserved=capacity-reserved,device_used_max_sample=max((v['device_memory']['used_bytes'] for v in samples),default=0),device_consumption_peak_not_measured=True,elapsed_seconds=result.get('elapsed_seconds')))
ready=len(rows)==8 and all(v['status']=='PASS' and v['exit_code']==0 for v in rows)
status='TRAINING_READY_REAL_DATA_4096' if ready else 'TRAINING_BLOCKED_REAL_DATA_4096'
summary={'status':status,'RUN_TRAIN':False,'full_training':False,'distribution':json.loads(stats.read_text())['target_percentiles'],'probes':rows,'prior_dense':'STRESS_CASE_OOM','prior_dense_blocks_this_gate':False,'independent_baseline_review':'NOT_TESTED','source_identity':json.loads((OUT/'source-identity.json').read_text())}
save(OUT/'real-data-4096-readiness-results.json',summary)
lines=['# Dataset-grounded 4096 readiness','',status,'','RUN_TRAIN=False. No full epoch, production adapter, merge, GGUF or deployment.','', 'Frozen dataset: 710 records, split579/65/66;813 TRAIN assistant turns. No truncation or source/mask modification. Target percentiles: '+json.dumps(summary['distribution']), '', 'Exact Qwen/Qwen3.5-4B-Base revision1001bb4d826a52d1f399e183466143f4da7b741b. Shared SupervisedPositionTrainer/training_components; source hashes and exact environment are recorded. Microbatch1, accumulation16 configuration, checkpointing, cache disabled, NF4 double quant, unchanged LoRA. Fresh process for every probe. real0 satisfies both maximum-real-target and top-three rank0 checks.','', '| Probe | Status | Targets | Source tokens | Allocated GiB | Reserved GiB | Capacity GiB | Capacity minus reserved GiB | Runtime seconds |','|---|---|---:|---:|---:|---:|---:|---:|---:|']
for v in rows:
    lines.append(f"| {v['probe']} | {v['status']} | {v['targets']} | {v['source_tokens']} | {v['peak_allocated']/2**30:.3f} | {v['peak_reserved']/2**30:.3f} | {v['capacity']/2**30:.3f} | {v['capacity_minus_peak_reserved']/2**30:.3f} | {v['elapsed_seconds']} |")
lines+=['','Headroom is a measured byte difference, not an invented safety percentage. Allocated/reserved are PyTorch counters. Total device usage is sampled at stage boundaries; its true transient peak is not measured. Raw JSON includes both capacity-minus-allocated and capacity-minus-reserved plus CPU RSS, loss, gradients, hashes and OOM tracebacks.','', 'Artificial4095-target case remains STRESS_CASE_OOM in preserved prior evidence, and does not block this revised dataset-grounded gate.','', '4096 training is verified for the observed workload envelope of the frozen710-record dataset through the measured maximum of243 supervised targets.' if ready else 'The actual observed workload envelope is not fully verified; no readiness claim.', '', 'A bounded workload-envelope PASS is not full-epoch stability or model-quality proof. Independent baseline semantic/Docker review remains pending.']
(OUT/'real-data-4096-readiness-report.md').write_text('\n'.join(lines)+'\n')
hashes={str(p.relative_to(ROOT)):sha(p) for p in ROOT.rglob('*') if p.is_file()}
save(OUT/'artifact-hashes.json',hashes)
archive=ROOT.parent/'sovereignai-real-data-4096-readiness.zip'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
    for p in ROOT.rglob('*'):
        if p.is_file(): z.write(p,str(p.relative_to(ROOT)))
print('REAL_DATA_SUMMARY',json.dumps(summary),flush=True)
print('REAL_DATA_ARCHIVE_SHA256='+sha(archive),flush=True)
import base64
# Export only results/source/prior evidence; canonical package already exists locally.
small=ROOT.parent/'sovereignai-real-data-4096-results.zip'
with zipfile.ZipFile(small,'w',zipfile.ZIP_DEFLATED) as z:
    for p in ROOT.rglob('*'):
        if p.is_file() and not p.is_relative_to(DATA) and p!=package: z.write(p,str(p.relative_to(ROOT)))
print('REAL_DATA_RESULTS_SHA256='+sha(small),flush=True)
print('REAL_DATA_RESULTS_BASE64='+base64.b64encode(small.read_bytes()).decode(),flush=True)
