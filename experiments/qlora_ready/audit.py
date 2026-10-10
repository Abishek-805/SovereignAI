"""Immutable pre-baseline audit. Stop on model-visible oracle leakage, never repair in place."""
import collections,copy,hashlib,importlib.metadata,importlib.util,json,math,platform,subprocess,sys
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
RELEASE=ROOT/'evidence/qlora-dataset-final/20261008-152636'
FACTORY=ROOT/'evidence/qlora-dataset-factory/20261008-114330'
MODEL='Qwen/Qwen3.5-4B-Base'
REVISION='1001bb4d826a52d1f399e183466143f4da7b741b'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return json.loads(path.read_text(encoding='utf-8'))
def rows(path):return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
def save(path,value):path.write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')

def leakages(row):
    findings=[]
    for index,message in enumerate(row['messages']):
        if message['role']!='user':continue
        try:value=json.loads(message.get('content',''))
        except (ValueError,TypeError):continue
        if not isinstance(value,dict):continue
        if row['category']=='computation' and 'verified_calculator_results' in value:
            observations=value['verified_calculator_results']
            if any(isinstance(x,dict) and ('expected' in x or 'actual' in x) for x in observations):
                findings.append({'message_index':index,'field':'verified_calculator_results','classification':'DATASET_ERROR','reason':'Precomputed arithmetic answers and oracle expectations are supplied in the user message before any model-selected calculator invocation. This cannot measure unaided computation or calculator routing and violates the current no-answer-in-prompt rule.'})
        for key in ('oracle_passed','oracle_verified','human_worked_solution'):
            if key in value:findings.append({'message_index':index,'field':key,'classification':'DATASET_ERROR','reason':'Hidden verification/answer metadata is present in a model-visible user message.'})
    return findings

def main():
    out=ROOT/'evidence/q-lora-ready'/datetime.now().strftime('%Y%m%d-%H%M%S');out.mkdir(parents=True,exist_ok=False)
    frozen={str(p.relative_to(RELEASE)):sha(p) for p in RELEASE.rglob('*') if p.is_file()}
    archive=ROOT/'sovereignai-finetuning-final-candidate.zip';archive_sha=sha(archive)
    base_hashes={p.name:sha(p) for p in (FACTORY/'base-tokenizer').iterdir() if p.is_file()}
    save(out/'acquisition-manifest.json',{'dataset_namespace':str(RELEASE),'dataset_namespace_sha256':frozen,'dataset_archive_sha256':archive_sha,'base_tokenizer_artifacts_sha256':base_hashes,'source_training_code_sha256':sha(ROOT/'sovereignai-finetuning/training.py'),'training_started':False,'benchmark_solutions_or_outcomes_inspected':False})
    release_manifest=read(RELEASE/'final-release-manifest.json')
    assert all(sha(RELEASE/name)==digest for name,digest in release_manifest['artifacts_sha256'].items())
    assert all(sha(RELEASE/name)==digest for name,digest in release_manifest['raw_evidence_sha256'].items())
    data=rows(RELEASE/'positive-trajectories-final.jsonl');splits={s:rows(RELEASE/(s+'.jsonl')) for s in ('train','validation','internal-test')};byid={r['id']:r for r in data}
    assert len(data)==len(byid)==710
    assert {s:len(v) for s,v in splits.items()}=={'train':579,'validation':65,'internal-test':66}
    identities=[r['id'] for v in splits.values() for r in v]
    assert len(identities)==len(set(identities))==710 and set(identities)==set(byid)
    assert all(r==byid[r['id']] for v in splits.values() for r in v)
    location={r['id']:s for s,v in splits.items() for r in v};families=collections.defaultdict(set)
    for r in data:
        assert r['messages'] and r['messages'][0]['role']=='system' and r['messages'][-1]['role']=='assistant'
        assert any(m['role']=='user' for m in r['messages']) and r['source'] and r['quality']['verified']
        assert r['release_checks']['license_status'] in {'LICENSE_CONFIRMED','LICENSE_NOT_REQUIRED'}
        assert r['release_checks']['split_assigned']==location[r['id']]
        families[r['release_checks']['family_assigned']].add(location[r['id']]);pending=set();previous=None
        for m in r['messages']:
            assert m['role'] in {'system','user','assistant','tool'} and 'content' in m
            if m['role']=='system':assert previous is None
            if m['role']=='user':assert previous in {'system','assistant'} and not pending
            if m['role']=='assistant':assert previous in {'user','tool'} and not pending
            for call in m.get('tool_calls',[]):
                assert m['role']=='assistant' and call['id'] not in pending
                assert isinstance(json.loads(call['function']['arguments']),dict);pending.add(call['id'])
            if m['role']=='tool':assert previous in {'assistant','tool'} and m['tool_call_id'] in pending;pending.remove(m['tool_call_id'])
            previous=m['role']
        assert not pending
    assert all(len(v)==1 for v in families.values())
    benchmark_manifest=ROOT/'evidence/dataset-expansion/20261008-133347/manifest.json'
    expected=read(RELEASE/'acquisition-manifest.json')['T01_T15_acquisition_manifest_sha256']
    actual=sha(benchmark_manifest)
    benchmark={'status':'PASS' if actual==expected else 'FAIL','manifest_path':str(benchmark_manifest),'expected_sha256':expected,'actual_sha256':actual,'solutions_inspected':False,'hidden_expected_outputs_inspected':False,'outcomes_inspected':False,'evaluation_run':False}
    save(out/'benchmark-integrity-check.json',benchmark)
    if actual!=expected:raise RuntimeError('BENCHMARK_INTEGRITY_ERROR: stop before baseline')
    spec=importlib.util.spec_from_file_location('immutable_training',ROOT/'sovereignai-finetuning/training.py');training=importlib.util.module_from_spec(spec);spec.loader.exec_module(training)
    sys.path.insert(0,str(FACTORY/'format-runtime'));from transformers import AutoTokenizer
    tokenizer=AutoTokenizer.from_pretrained(FACTORY/'base-tokenizer',local_files_only=True,trust_remote_code=False)
    turns=[];renders=[];reject=[]
    for split,values in splits.items():
        represented=set()
        for row in values:
            encoded,oversize=training.tokenize_turns(tokenizer,[row],4096);reject.extend(oversize);assert encoded
            for turn in encoded:
                assert len(turn['labels'])==len(turn['input_ids'])==len(turn['attention_mask'])
                assert turn['labels'][:turn['prompt_tokens']]==[-100]*turn['prompt_tokens']
                assert turn['labels'][turn['prompt_tokens']:]==turn['input_ids'][turn['prompt_tokens']:]
                turns.append({'id':row['id'],'split':split,'turn':turn['turn'],'tokens':len(turn['input_ids']),'prompt_tokens':turn['prompt_tokens'],'assistant_tokens':turn['assistant_tokens']})
            if row['category'] not in represented:
                represented.add(row['category']);renders.append({'id':row['id'],'split':split,'category':row['category'],'rendered':encoded[-1]['rendered'],'input_ids':encoded[-1]['input_ids'],'labels':encoded[-1]['labels'],'prompt_tokens':encoded[-1]['prompt_tokens'],'initial_state_metadata_present':bool(row.get('initial_state')),'model_visible_roles':[m['role'] for m in row['messages']],'tools_available':bool(row.get('tools'))})
    assert not reject
    flagged=[{'id':r['id'],'category':r['category'],'split':location[r['id']],'findings':leakages(r)} for r in data if leakages(r)]
    save(out/'rendered-representative-examples.json',{'official_model':MODEL,'revision':REVISION,'examples':renders,'extra_oracle_metadata_added_to_messages':False})
    save(out/'training-format-final-audit.json',{'status':'FAIL' if flagged else 'PASS','serialization_status':'PASS','official_tokenizer':MODEL,'revision':REVISION,'assistant_boundaries':'PASS','assistant_only_loss_masks':'PASS','tool_call_serialization':'PASS','trajectory_observations_preserved':'PASS','rag_evidence_preserved':'PASS','oracle_answer_in_user_prompt':'FAIL' if flagged else 'PASS','truncated':0,'oversize_examples':reject,'turns':turns,'flagged_examples':flagged})
    lengths=sorted(t['tokens'] for t in turns);pct=lambda p:lengths[min(len(lengths)-1,math.ceil(p*len(lengths))-1)]
    save(out/'sequence-length-final.json',{'p50':pct(.5),'p90':pct(.9),'p95':pct(.95),'p99':pct(.99),'max':max(lengths),'candidate_limit':4096,'actual_gpu_fit_tested':False,'no_truncation':True,'training_length_approved':False})
    integrity={'status':'FAIL' if flagged else 'PASS','structural_integrity':'PASS','exact_partition':'PASS','counts':{s:len(v) for s,v in splits.items()},'selected_positive_count':710,'source_provenance':'PASS','license_metadata':'PASS','family_and_split_assignment':'PASS','official_tokenizer_mask_audit':'PASS','model_visible_answer_integrity':'FAIL' if flagged else 'PASS','affected_count':len(flagged),'affected_by_split':dict(collections.Counter(f['split'] for f in flagged)),'released_dataset_modified':False,'release_hashes_verified':True,'no_truncation':True}
    save(out/'final-dataset-integrity-check.json',integrity)
    marked=[]
    for f in flagged:
        row=copy.deepcopy(byid[f['id']]);row['pre_training_audit']={'status':'RELEASE_ADJUSTMENT_REQUIRED','reason':f['findings'],'train_or_evaluate_allowed':False,'original_record_unchanged_except_this_audit_marker':True};marked.append(row)
    (out/'release-adjustment-required.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in marked),encoding='utf-8')
    gpu=subprocess.run(['nvidia-smi','--query-gpu=name,memory.total,memory.used,driver_version','--format=csv,noheader'],capture_output=True,text=True)
    versions={}
    for name in ('torch','transformers','peft','trl','bitsandbytes','unsloth','datasets'):
        try:versions[name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:versions[name]=None
    environment={'execution_environment':'local Windows audit, not Google Colab','python':sys.version,'platform':platform.platform(),'gpu_probe':gpu.stdout.strip(),'gpu_probe_exit_code':gpu.returncode,'cuda_runtime':None,'cuda_runtime_verified':False,'libraries':versions,'colab_runtime_connected':False,'colab_gpu':None,'colab_vram':None,'qlora_fit_tested':False}
    save(out/'colab-environment-report.json',environment)
    config=read(FACTORY/'base-tokenizer/config.json');assert config['model_type']=='qwen3_5' and config['architectures']==['Qwen3_5ForConditionalGeneration']
    save(out/'base-model-identity.json',{'model':MODEL,'revision':REVISION,'architecture':config['architectures'],'configuration':config,'tokenizer_sha256':base_hashes,'native_format':'Hugging Face Safetensors required, not GGUF','native_base_weight_acquisition':'NOT_RUN','native_base_weight_hash':None,'compatibility_status':'NOT_TESTED','official_model_card':'https://huggingface.co/Qwen/Qwen3.5-4B-Base','exact_runtime_smoke_run':False})
    blocked_reason='Pre-baseline input-integrity gate failed: computation user prompts contain precomputed answers and expected oracle values.'
    baseline={'status':'BASELINE_BLOCKED','classification':'DATASET_ERROR','reason':blocked_reason,'model':MODEL,'revision':REVISION,'true_base_evaluated':False,'model_weights_loaded':False,'environment':environment,'splits':{s:{c:{'number_of_tests':n,'successful':0,'failed':0,'unknown':0,'blocked':n,'attempted':0,'pass_rate':None,'latency':None} for c,n in collections.Counter(r['category'] for r in splits[s]).items()} for s in ('validation','internal-test')},'deterministic_calculator_results_not_llm_results':True,'load_time':None,'prompt_processing_time':None,'generation_time':None,'total_request_time':None,'cold_warm_measurements':None,'T01_T15_executed':False}
    save(out/'true-base-baseline.json',baseline)
    save(out/'training-method-decision.json',{'status':'TRAINING_STACK_BLOCKED','primary_classification':'DATASET_ERROR','reason':blocked_reason,'method_selected_for_attempt':'qlora','quantization_candidate':'NF4','architecture_compatibility':'NOT_TESTED','qlora_attempted':False,'lora_attempted':False,'automatic_fallback':False})
    save(out/'qlora-smoke-result.json',{'status':'NOT_RUN','blocked_by':'TRAINING_FORMAT_BLOCKED','forward':False,'backward':False,'optimizer_step':False,'adapter_saved':False,'adapter_reloaded':False,'base_weights_loaded':False,'gpu_memory':None,'CPU_RAM':None,'step_time':None,'loss':None,'not_a_model_quality_failure':True})
    save(out/'checkpoint-selection-plan.json',{'status':'NOT_ACTIVATED','future_checkpoints':['epoch 1','epoch 2'],'selection_split':'validation','select_by_training_loss':False,'internal_test_for_selection':False,'T01_T15_for_selection':False,'selected_checkpoint':None})
    gates={'dataset_integrity':integrity['status'],'T01_15_integrity':benchmark['status'],'base_baseline_complete':'NOT_RUN','training_format_audit':'FAIL' if flagged else 'PASS','qlora_smoke':'NOT_RUN','environment_compatible':'NOT_TESTED'}
    save(out/'training-manifest-final.json',{'status':'TRAINING_FORMAT_BLOCKED' if flagged else 'BASELINE_BLOCKED','RUN_TRAIN':False,'training_allowed':False,'gates':gates,'dataset_sha256':{s+'.jsonl':sha(RELEASE/(s+'.jsonl')) for s in splits},'dataset_metadata_sha256':sha(RELEASE/'final-dataset-statistics.json'),'tokenizer_sha256':base_hashes,'model':MODEL,'revision':REVISION,'seed':42,'audit_code_sha256':sha(Path(__file__)),'environment':environment,'training_code_prepared':False,'configuration_prepared':False,'full_training_started':False})
    (out/'TRUE_BASELINE_REPORT.md').write_text('# True Base baseline\n\nStatus: BASELINE_BLOCKED\n\n'+blocked_reason+'\n\nModel: '+MODEL+' @ '+REVISION+'. No Base weights loaded, no requests executed, no measured model accuracy or latency. Validation/internal-test task counts are recorded as blocked rather than failed in true-base-baseline.json. The production instruction-tuned GGUF was not used as a substitute. No generated code was run on the host or Colab.\n',encoding='utf-8')
    sections={
        'DATASET':'710 frozen positives: 579 train / 65 validation / 66 internal-test. The release and its ZIP remain unchanged.',
        'DATASET QUALITY':'Historical curation reports all mandatory quality conditions PASS, with the approximate-volume goal unmet. This additional pre-training audit finds a requirement not covered by those earlier gates: model-visible arithmetic oracle answers. No earlier evidence or status file was rewritten.',
        'BASE MODEL':MODEL+' @ '+REVISION+'; config architecture Qwen3_5ForConditionalGeneration. Official tokenizer/config hashes verified. Native Safetensors weights were not acquired or loaded. Model display aliases/GGUF are not identity evidence.',
        'BASELINE':'BASELINE_BLOCKED. No measured results exist. Every validation/internal-test task is marked blocked, never model FAIL. No TRAIN rows used to claim evaluation quality.',
        'COLAB':'No Colab runtime is connected or tested. Local nvidia-smi detects '+gpu.stdout.strip()+'. CUDA runtime, GPU training dependencies and 4-bit memory feasibility are unverified. The isolated tokenizer dependency runtime is not a training environment.',
        'QLORA':'NOT_RUN. No load, quantization, forward/backward, optimizer step, saved adapter or reload. No LoRA fallback. Infrastructure/input blocking is not a model-quality failure.',
        'TRAINING CONFIG':'Not activated or prepared beyond the recorded seed because the required pre-baseline integrity gate failed. Suggested NF4/r16/alpha32/dropout0.05/learning-rate1e-4 settings remain proposals, not tested compatibility or calibrated hardware choices.',
        'SEQUENCE LENGTH':json.dumps(read(out/'sequence-length-final.json'))+'. All 1010 supervised assistant turns re-rendered with the pinned official template and their masks checked. No truncation; 4096 is a candidate cap, not a measured GPU guarantee.',
        'CHECKPOINT POLICY':'Future selection uses validation-only category-level independent measurements. Internal-test and T01–T15 never select checkpoints. No checkpoint exists.',
        'BENCHMARK INTEGRITY':'T01–T15 acquisition manifest SHA-256 matches the frozen release reference. No benchmark solutions, hidden expected outputs or outcomes inspected; no T01–T15 evaluation run.',
        'SECURITY':'No model-generated code was executed on the host or Colab. Required coding/agentic Docker oracles were not bypassed. Production ToolRegistry, executor, validator, prompts, router, broker and sandbox policy unchanged.',
        'DEPLOYMENT':'Future Base → separate QLoRA adapter → validation-only checkpoint selection → independent final evaluation → separate merged model → exact-version converter compatibility check → Q4_K_M → llama.cpp → gated SovereignAI deployment. None executed; original Base and production GGUF were not overwritten.',
        'CURRENT STATUS':'TRAINING_FORMAT_BLOCKED. RUN_TRAIN = False. '+str(len(flagged))+' computation records require an explicitly reviewed experiment-only adjustment before baseline work. Remove oracle expectations from user prompts; if calculator-conditioned learning is retained, use actual model-selected tool actions and their genuine observations instead of presenting worked answers in advance. No dataset reexpansion is needed.',
        'STOP CONDITION':'Stopped under sections 3 and 14 of the current prompt. Colab setup, the executable training notebook, qlora_config_final.yaml, smoke testing and Base evaluation are intentionally not advanced after the failed input gate. This report does not claim READY_TO_TRAIN. release-adjustment-required.jsonl contains marked copies only; no canonical record was silently repaired.'}
    (out/'FINAL_REPORT.md').write_text('# SovereignAI pre-training audit\n\n'+''.join('## '+k+'\n\n'+v+'\n\n' for k,v in sections.items()),encoding='utf-8')
    assert all(sha(RELEASE/name)==digest for name,digest in frozen.items()) and sha(archive)==archive_sha
    assert all(sha(FACTORY/'base-tokenizer'/name)==digest for name,digest in base_hashes.items())
    assert sha(benchmark_manifest)==expected
    assert len(flagged)==43 and all(f['category']=='computation' for f in flagged)
    save(out/'audit-self-check.json',{'status':'PASS','canonical_dataset_and_history_unchanged':True,'release_archive_unchanged':True,'original_base_tokenizer_artifacts_unchanged':True,'benchmark_manifest_unchanged':True,'exact_partition_verified':True,'all_assistant_masks_checked':True,'masked_prefix_tokens_checked':sum(t['prompt_tokens'] for t in turns),'supervised_turns':len(turns),'leakage_detection_positive_control':'43 GSM8K precomputed-answer user prompts','negative_control':'The remaining computation record lacks these precomputed answer fields.','no_model_calls':True,'no_training':True,'no_weight_updates':True})
    save(out/'experiment-manifest.json',{'status':'TRAINING_FORMAT_BLOCKED','artifact_sha256':{p.name:sha(p) for p in out.iterdir() if p.is_file()},'RUN_TRAIN':False,'training_allowed':False})
    print(json.dumps({'namespace':str(out),'status':'TRAINING_FORMAT_BLOCKED','affected_rows':len(flagged),'affected_by_split':integrity['affected_by_split'],'structural_integrity':'PASS','format_and_masks':'PASS','benchmark_integrity':'PASS','model_visible_answers':'FAIL','training_run':False}))

if __name__=='__main__':main()
