"""Export bounded probe evidence; never executes models or generated project code."""
import base64, hashlib, json, math, statistics, subprocess, zipfile
from pathlib import Path

def export(root, current, pipeline):
    assert globals().get('RUN_TRAIN',False) is False
    def read(p):return json.loads(p.read_text())
    def write(p,v):p.write_text(json.dumps(v,indent=2,default=str)+'\n')
    original=read(pipeline.run/'artifact-hashes.json')
    for name,wanted in original.items():
        assert hashlib.sha256((pipeline.run/name).read_bytes()).hexdigest()==wanted,name
    package=read(pipeline.data/'package-manifest.json')
    for name,wanted in package['files'].items():
        assert hashlib.sha256((pipeline.data/name).read_bytes()).hexdigest()==wanted,name
    predictions=pipeline.run/pipeline.stages['baseline']['directory']/'base-predictions.json'
    prediction_hash=hashlib.sha256(predictions.read_bytes()).hexdigest()
    assert prediction_hash=='1862f1aa4967557670bfd6e82579b6a63e98d4624ad7291ab648ad9e2c6b5e54'
    counts=read(predictions.with_name('baseline-counts.json'))
    assert counts['captured']==131 and not counts['missing'] and counts['duplicates']==0
    stats=read(root/'stats'/'training-supervised-target-stats.json')
    def percentile(values):
        v=sorted(values)
        return {str(p):v[round((len(v)-1)*p/100)] for p in (0,50,90,95,99,100)}
    stats['record_max_targets_percentiles']=percentile([v['max_supervised_targets'] for v in stats['per_record']])
    stats['density_percentiles']=percentile([v['density'] for v in stats['per_assistant_turn']])
    write(root/'training-supervised-target-stats.json',stats)
    results={}
    for name in ['sparse','representative','high','dense','long0','long1','long2','accumulation','trainer']:
        choices=list(root.rglob(name+'/result.json'))
        # Valid new attempts supersede only in this derived view; originals remain untouched.
        choices.sort(key=lambda p:('recovery-v3' in str(p),'recovery-v2' in str(p)))
        path=choices[-1] if choices else None
        result=read(path) if path else {'status':'NOT_TESTED'}
        if 'warmup_ratio' in str(result.get('error','')) and 'current_microbatch' not in result:
            result=dict(result,raw_status=result['status'],status='NOT_TESTED_HARNESS_API',failure_category='HARNESS_API')
        elif result.get('status')=='RUNNING':
            result=dict(result,raw_status='RUNNING',status='NOT_COMPLETED',failure_category='ENVIRONMENT_INTERRUPTION_OR_TIMEOUT')
        results[name]=dict(result,evidence_file=str(path.relative_to(root)) if path else None)
    trainer=results['trainer'];accum=results['accumulation']
    measured=list(trainer.get('microbatches',[]))+accum.get('microbatches',[])[:16]
    if measured:
        times=[v['seconds'] for v in measured]
        predictions_time=[]
        for turn in stats['per_assistant_turn']:
            nearest=sorted(measured,key=lambda v:abs(math.log((v['tokens']+1)/(turn['tokens']+1)))+
                           .5*abs(math.log((v['targets']+1)/(turn['targets']+1))))[:3]
            predictions_time.append(statistics.median(v['seconds'] for v in nearest))
        epoch=sum(predictions_time)
        estimate={'status':'ESTIMATE','measured_microbatches':len(measured),'median_microbatch_seconds':statistics.median(times),
                  'p95_microbatch_seconds':percentile(times)['95'],'epoch_compute_seconds':epoch,
                  'two_epoch_compute_seconds':2*epoch,'epoch_training_turns':stats['assistant_turn_count'],
                  'estimated_optimizer_steps_per_epoch':math.ceil(stats['assistant_turn_count']/16),
                  'method':'nearest three observed token/target profiles, median timing; sum over actual 813 TRAIN turns',
                  'validation_overhead':'UNKNOWN; no validation sweep measured',
                  'checkpoint_overhead':'UNKNOWN as isolated duration; actual saves occurred inside Trainer lifecycle',
                  'optimizer_dataloader_load_logging_overhead':'not included in compute estimate',
                  'not_a_full_training_benchmark':True}
    else:estimate={'status':'UNKNOWN','reason':'No completed timed real microbatches'}
    dense={k:results[k] for k in ('sparse','representative','high','dense')}
    longest={k:results[k] for k in ('long0','long1','long2')}
    memory=accum.get('memory_growth',{'status':'NOT_TESTED'})
    gates={'dense_4096':results['dense'].get('status','NOT_TESTED'),
           'longest_train_examples':'PASS' if all(v.get('status')=='PASS' for v in longest.values()) else 'NOT_COMPLETE',
           'accumulation':'PASS' if accum.get('accumulation_success') else accum.get('status','NOT_TESTED'),
           'memory_stability':memory.get('status','NOT_TESTED'),
           'trainer_integration':trainer.get('trainer_integration','NOT_TESTED'),
           'checkpoint_resume':trainer.get('checkpoint_resume','NOT_TESTED')}
    final='TRAINING_READY' if all(v=='PASS' for v in gates.values()) else 'TRAINING_BLOCKED'
    preserved={'dataset_integrity':'PASS','dataset_files_unchanged':True,'split_counts':{'train':579,'validation':65,'internal-test':66},
               'original_readiness_hashes_verified':len(original),'baseline_prediction_sha256':prediction_hash,
               'baseline_predictions_preserved':131,'missing':0,'duplicates':0,'independent_baseline_review':'NOT_TESTED',
               'RUN_TRAIN':False,'full_training_executed':False,
               'gpu_processes':subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader'],text=True).strip()}
    assert not preserved['gpu_processes'],'GPU process still active; do not export mid-probe'
    summary={'status':final,'gates':gates,'preservation':preserved,'estimate':estimate,'current_checkpoint':str(current),
             'limitations':['Dense stress failure is synthetic, not a demonstrated failure of all real TRAIN records',
                            'No full-epoch proof, baseline semantic/Docker review pending',
                            'BF16 is emulated on T4; no model, precision, sequence or dataset substitution',
                            'Missing probes are NOT_TESTED, never fabricated FAIL or PASS'],
             'model':'Qwen/Qwen3.5-4B-Base','revision':'1001bb4d826a52d1f399e183466143f4da7b741b','sequence_limit':4096}
    write(root/'readiness-summary.json',summary)
    for name,obj in [('dense-4096-stress-results.json',dense),('longest-example-results.json',longest),
                     ('accumulation-stability-results.json',accum),('memory-growth-results.json',memory),
                     ('trainer-integration-result.json',trainer),('checkpoint-resume-result.json',trainer),
                     ('training-time-estimate.json',estimate),('preservation.json',preserved)]:
        write(root/name,obj)
    lines=['# SovereignAI final pre-training readiness','', '**Final status: '+final+'**',
           '', 'Full training: **DISABLED**. RUN_TRAIN=False. No full epoch, merge, GGUF, deployment or production adapter.',
           '', '## 1. Dataset integrity','', '710 records, split 579/65/66 unchanged. All package and original readiness hashes verified. The 131 existing Base predictions are preserved; no regeneration. T01–T15 were not inspected.',
           '', '## 2. TRAIN target distribution','', '579 TRAIN records expand into '+str(stats['assistant_turn_count'])+' official assistant-only training turns. Counts below are per assistant turn; per-record maxima and all record/turn metadata are in training-supervised-target-stats.json.',
           '', 'Target percentiles: '+json.dumps(stats['target_percentiles'])+'. Maximum sequence length: '+str(stats['max_sequence_length'])+'. Maximum density: '+str(stats['max_density'])+'.',
           '', 'Above target thresholds: '+json.dumps(stats['above_threshold'])+'. No source text or evaluator answers are exported in the statistics.',
           '', '## 3. Synthetic 4096 stress and 4. longest real examples','',
           '| Probe | Status | Tokens | Targets | Peak allocated GiB | Peak reserved GiB | CPU peak GiB | Lifecycle seconds |',
           '|---|---|---:|---:|---:|---:|---:|---:|']
    for name,value in results.items():
        memories=[v['memory'] for v in value.get('measurements',[])]+[v['memory'] for v in value.get('microbatches',[])]
        pa=max((m['peak_allocated'] for m in memories),default=0)/2**30
        pr=max((m['peak_reserved'] for m in memories),default=0)/2**30
        cpu=max((m['cpu_peak_rss_kib'] for m in memories),default=0)/2**20
        targets=value.get('supervised_targets',value.get('source_target_count','—'))
        metrics=[f'{v:.3f}' for v in (pa,pr,cpu)] if memories else ['—']*3
        elapsed=f"{value['elapsed_seconds']:.2f}" if 'elapsed_seconds' in value else '—'
        lines.append(f"| {name} | {value.get('status')} | {value.get('input_tokens','varied')} | {targets} | {' | '.join(metrics)} | {elapsed} |")
    lines += ['', 'The sparse/representative/high cases use 22/p50/p99 observed target COUNTS at 4096 inputs; these are not a density-scaled synthetic worst case. The dense case supervises 4095 next-token targets. The real-example probes retain original inputs/masks and add only ignored-label diagnostic padding to 4096.',
              '', 'Dense error: '+str(results['dense'].get('error','NOT_TESTED')),
              '', '## 5. Accumulation and 6. memory growth','',
              'Accumulation gate: '+gates['accumulation']+'. Memory gate: '+gates['memory_stability']+'. Microbatch=1, accumulation=16. Four additional equivalent disposable steps check retention without repeated empty_cache. This bounded check is not proof against long-run leaks.',
              '', '## 7. Actual Trainer integration and 8. checkpoint resume','',
              'Trainer: '+gates['trainer_integration']+'. Resume: '+gates['checkpoint_resume']+'. The shared SupervisedPositionTrainer calls the installed parent loss with logits_to_keep/shift_labels, retaining parent accumulation normalization. The experimental full-training source uses this same class, arguments and collator; its full-training guard remains closed.',
              '', 'Initial API attempt failed because pinned Transformers 5.19 removed warmup_ratio. Installed get_warmup_steps proved warmup_steps=0.03 preserves the intended 3% ratio. Original failed outputs are retained.',
              '', 'The first resume micro-test changed its scheduler horizon after reaching zero LR; it restored adapter and optimizer and executed 48 microbatches, but the post-resume parameter-change assertion failed. The corrected bounded test uses a fixed three-step horizon, stops deliberately after step two, destroys Trainer/model/optimizer, restores checkpoint and continues to step three. Both attempts remain available; no model-specific tuning occurred.',
              '', 'All checkpoint directories are disposable and removed. Successful result receipts record Base hashes, nonzero/finite LoRA gradients, parameter changes, masks and dataset preservation. No-target batches are explicitly rejected; they are not assigned fabricated finite loss.',
              '', '## 9. Measured latency and 10. full-training ESTIMATES','',
              json.dumps(estimate,indent=2),
              '', 'These are compute estimates based on observed real microbatches and the actual turn distribution. They exclude unmeasured validation/checkpoint/loading overhead and do not guarantee a one-hour completion.',
              '', '## 11. GPU memory and 12. limitations','',
              'Tesla T4; exact Base/revision above. BF16 emulation, NF4 double quantization, rank 16, alpha 32, dropout 0.05, AdamW, learning rate 1e-4, seed 42, checkpointing enabled, cache disabled. Environment, exact bytes, stage timing, OOM tracebacks, loss, RSS, per-microbatch metrics and configuration are preserved in raw JSON/logs.',
              '', 'PyTorch allocated/reserved values exclude some driver memory. Missing/unfinished checks remain NOT_TESTED/NOT_COMPLETE. Dataset distribution is sparse; a dense synthetic OOM does not prove real-data OOM. Conversely sparse successes cannot satisfy the required dense gate.',
              '', 'Independent semantic/Docker/stateful Base validation remains NOT_TESTED; raw predictions are not correctness. No GPU model generation or generated project code execution was added.',
              '', '## Final gates','',json.dumps(gates,indent=2),
              '', 'RUN_TRAIN=False. '+final+'.']
    (root/'final-pretraining-readiness.md').write_text('\n'.join(lines)+'\n')
    artifacts={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file() and p.name!='final-artifact-hashes.json'}
    write(root/'final-artifact-hashes.json',artifacts)
    archive=Path('/content/sovereignai-final-readiness-probes.zip')
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for p in root.rglob('*'):
            if p.is_file():z.write(p,str(p.relative_to(root)))
    with zipfile.ZipFile(archive) as z:assert z.testzip() is None
    print('READINESS_SUMMARY',json.dumps(summary),flush=True)
    print('READINESS_ARCHIVE_SHA256='+hashlib.sha256(archive.read_bytes()).hexdigest(),flush=True)
    print('READINESS_ARCHIVE_BASE64='+base64.b64encode(archive.read_bytes()).decode(),flush=True)

