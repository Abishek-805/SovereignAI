"""Revalidate the adjusted release and prepare manual-only GPU readiness stages."""
import ast, collections, importlib.util, json, math, re, shutil, sys, urllib.request, zipfile
from datetime import datetime
from pathlib import Path
from experiments.qlora_ready.audit import ROOT, RELEASE, FACTORY, sha, read, rows, save
from experiments.qlora_ready.repair_computation import scan
from experiments.qlora_ready.colab_readiness_runtime import MODEL, REVISION, PINS, training_guard
from experiments.dataset_expansion.release import user_text,norm,shingles

ADJUSTED=ROOT/'evidence/computation-leakage-repair/20261008-171801'

def main():
    out=ROOT/'evidence/pretraining-readiness'/datetime.now().strftime('%Y%m%d-%H%M%S');out.mkdir(parents=True,exist_ok=False)
    prior=read(ADJUSTED/'completion-manifest.json');assert all(sha(ADJUSTED/n)==d for n,d in prior['artifacts_sha256'].items())
    original_hashes=read(ADJUSTED/'release-manifest-adjusted.json')['canonical_artifact_hashes'];assert all(sha(RELEASE/n)==d for n,d in original_hashes.items())
    benchmark=ROOT/'evidence/dataset-expansion/20261008-133347/manifest.json';benchmark_sha=read(RELEASE/'acquisition-manifest.json')['T01_T15_acquisition_manifest_sha256'];assert sha(benchmark)==benchmark_sha
    splits={s:rows(ADJUSTED/(s+'.adjusted.jsonl')) for s in ('train','validation','internal-test')};data=[r for values in splits.values() for r in values]
    assert len(data)==len({r['id'] for r in data})==710
    assert {s:len(v) for s,v in splits.items()}=={'train':579,'validation':65,'internal-test':66}
    originals={r['id']:r for r in rows(RELEASE/'positive-trajectories-final.jsonl')};changed={c['id'] for c in read(ADJUSTED/'computation-leakage-audit.json')['changes']}
    assert sum(r==originals[r['id']] for r in data)==666 and len(changed)==44
    families=read(RELEASE/'split-assignment-final.json')['example_families'];locations={r['id']:s for s,v in splits.items() for r in v};seen=collections.defaultdict(set)
    for r in data:
        assert r['source']==originals[r['id']]['source'] and r['quality']==originals[r['id']]['quality']
        assert r['quality']['verified'] and r['quality']['oracle']['passed']
        assert r['release_checks']['license_status'] in {'LICENSE_CONFIRMED','LICENSE_NOT_REQUIRED'}
        for key in (families[r['id']],'declared:'+r['family'],*['article:'+e['title'] for e in r.get('evidence',[]) if 'title' in e]):seen[key].add(locations[r['id']])
        assert user_text(r)==user_text(originals[r['id']])
        if r['category']=='computation':assert not any(scan(m['content']) for m in r['messages'] if m['role'] in {'system','user'})
    assert all(len(v)==1 for v in seen.values())
    requests=[norm(user_text(r)) for r in data];assert len(requests)==len(set(requests))
    words=[shingles(user_text(r)) for r in data];pair_count=0
    for i,left in enumerate(data):
        for j in range(i+1,len(data)):
            union=words[i]|words[j];similarity=len(words[i]&words[j])/len(union) if union else 0
            if similarity>=.6:assert families[left['id']]==families[data[j]['id']] and locations[left['id']]==locations[data[j]['id']];pair_count+=1
    rag=[];summaries=[]
    for row in data:
        if row['category'] not in {'rag','summarization'}:continue
        objects=[]
        for m in row['messages']:
            if m['role']!='user':continue
            try:value=json.loads(m['content'])
            except ValueError:continue
            if isinstance(value,dict):objects.append(value)
        assert objects
        if row['category']=='rag':
            sources=[v for obj in objects for key in ('retrieved_evidence','sources','tables') if (v:=obj.get(key))]
            assert sources and all(isinstance(v,(dict,list)) for v in sources)
            assert all(not any(key in obj for key in ('oracle','oracle_passed','ground_truth','human_worked_solution')) for obj in objects)
            rag.append({'id':row['id'],'source_context_present':True,'request_and_evidence_unchanged':row['messages']==originals[row['id']]['messages'],'prior_semantic_oracle_unchanged':True,'not_a_new_model_grounding_test':True})
        else:
            assert any(obj.get('sources') or ('before' in obj and 'after' in obj) for obj in objects)
            target=row['messages'][-1]['content'];source_texts=[s['text'] for obj in objects for s in obj.get('sources',[]) if isinstance(s,dict) and 'text' in s]
            assert all(target.strip()!=text.strip() for text in source_texts)
            copied=[sentence for text in source_texts for sentence in re.split(r'(?<=[.!?])\s+',text) if len(sentence.split())>=8 and sentence.strip() in target]
            summaries.append({'id':row['id'],'abstraction_reference_review':'PRESERVED_VERIFIED_SOURCE_BOUND_ORACLE','source_target_unchanged':row['messages']==originals[row['id']]['messages'],'exact_whole_source_copy':False,'long_sentence_copy_triage':copied,'copy_flags_are_triage_not_semantic_verdict':True})
    assert len(rag)==244 and len(summaries)==18
    assert not any(s['long_sentence_copy_triage'] for s in summaries),'Summary copying needs review'
    sys.path.insert(0,str(FACTORY/'format-runtime'));from transformers import AutoTokenizer
    spec=importlib.util.spec_from_file_location('format_helpers',ADJUSTED/'colab_format_helpers.py');helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    tokenizer=AutoTokenizer.from_pretrained(FACTORY/'base-tokenizer',local_files_only=True,trust_remote_code=False)
    encoded,rejected=helper.tokenize_turns(tokenizer,data,4096);assert len(encoded)==1010 and not rejected
    for turn in encoded:assert turn['labels'][:turn['prompt_tokens']]==[-100]*turn['prompt_tokens'] and turn['labels'][turn['prompt_tokens']:]==turn['input_ids'][turn['prompt_tokens']:]
    lengths=sorted(len(t['input_ids']) for t in encoded);pct=lambda p:lengths[min(len(lengths)-1,math.ceil(p*len(lengths))-1)]
    save(out/'dataset-gates.json',{'gates':{n:'PASS' for n in ['record_count','split_count','canonical_hashes','adjusted_manifest_hash','exact_duplicates','source_family_isolation','family_split_isolation','assistant_boundaries_masks','tokenizer','no_truncation','observed_computation_leakage','metadata_oracle_separation','license_provenance','rag_grounding_structure','summary_abstraction_reference_checks','benchmark_manifest_integrity']},'counts':{s:len(v) for s,v in splits.items()},'all_assistant_turns':1010,'observed_leakage':0,'numeric_collisions_previously_reviewed':3,'pair_triage_count':pair_count,'unflagged_latent_similarity_proven_absent':False,'new_semantic_model_evaluation_run':False,'canonical_sha256':original_hashes,'adjusted_manifest_sha256':sha(ADJUSTED/'release-manifest-adjusted.json'),'T01_T15_manifest_sha256':benchmark_sha,'T01_T15_contents_inspected':False})
    save(out/'rag-summary-structure-review.json',{'rag':rag,'summaries':summaries,'scope':'Unchanged verified reference/source checks plus exact-copy triage; not a newly run model-quality evaluation.'})
    save(out/'sequence-length-candidate.json',{'p50':pct(.5),'p90':pct(.9),'p95':pct(.95),'p99':pct(.99),'max':max(lengths),'candidate':4096,'truncated':0,'gpu_fit':'NOT_TESTED','actual_distribution_after_44_repairs':True})
    registry={}
    for name,version in PINS.items():
        requested=version.split('+')[0];url=f'https://pypi.org/pypi/{name}/{requested}/json';info=json.load(urllib.request.urlopen(url))
        registry[name]={'source':url,'version':info['info']['version'],'requires_python':info['info']['requires_python'],'wheels':[{'filename':f['filename'],'sha256':f['digests']['sha256']} for f in info['urls'] if f['packagetype']=='bdist_wheel'],'gpu_compatibility_tested':False}
    save(out/'package-registry-verification.json',registry)
    observed={'status':'NOT_TESTED','earlier_ui_probe_only':{'python':'3.13.15','gpu':'Tesla T4','total_vram_mib':15360,'driver':'580.82.07','torch':'2.11.0+cu130','transformers':'5.18.0','peft':'0.21.1','accelerate':'1.15.0','datasets':'4.8.5','bitsandbytes':None,'trl':None},'probe_did_not_import_torch_or_test_cuda':True,'latest_user_instruction':'Fill cells only; user runs later','new_colab_executions':0}
    save(out/'colab-environment-report.json',observed)
    values={'base_model':MODEL,'base_revision':REVISION,'tokenizer_revision':REVISION,'dataset_manifest_sha256':sha(ADJUSTED/'release-manifest-adjusted.json'),'split_counts':{s:len(v) for s,v in splits.items()},'sequence_length':4096,'quantization':'NF4','double_quant':True,'lora_rank':16,'lora_alpha':32,'lora_dropout':.05,'target_modules':'all-linear excluding visual','learning_rate':1e-4,'microbatch':1,'gradient_accumulation':16,'effective_batch':16,'optimizer':'adamw_torch','scheduler':'linear','warmup_ratio':.03,'epochs':2,'seed':42,'precision':'BF16 if supported, otherwise FP16; actual choice UNKNOWN','gradient_checkpointing':True,'save_strategy':'epoch','eval_strategy':'epoch','assistant_only_loss':True,'checkpoint_selection':'independent validation category scores, never loss-only or internal-test','RUN_TRAIN':False}
    verified={'base_model','base_revision','tokenizer_revision','dataset_manifest_sha256','split_counts','assistant_only_loss','RUN_TRAIN'}
    config={k:{'value':v,'status':'VERIFIED' if k in verified else 'UNKNOWN' if k=='precision' else 'PROPOSED'} for k,v in values.items()}
    save(out/'training-config-candidate.json',config)
    (out/'qlora_config_final.yaml').write_text(json.dumps(config,indent=2)+'\n',encoding='utf-8')
    for name in ('base-model-identity','base-smoke-result','qlora-smoke-result','sequence-fit-result'):
        save(out/(name+'.json'),{'status':'NOT_TESTED','reason':'Prepared manual cells; no execution under fill-only instruction','model':MODEL,'revision':REVISION,'training_run':False})
    save(out/'true-base-baseline.json',{'status':'BASELINE_BLOCKED','reason':'No Base weights loaded or validation/internal-test predictions independently evaluated; prepared capture is first-response only','model':MODEL,'revision':REVISION,'results':[],'attempted':0,'required_tasks':131,'T01_T15_used':False,'model_failures':0,'not_attempted_is_not_model_failure':True})
    save(out/'independent-baseline-receipt-schema.json',{'description':'Required independent reviewed baseline receipt; do not self-certify from raw predictions','model':MODEL,'revision':REVISION,'adapter':None,'prediction_sha256':'SHA256 of base-predictions.json','independently_verified':False,'results':[{'id':'EXACT validation/internal-test row ID','split':'validation or internal-test','category':'original category','status':'PASS/FAIL/UNKNOWN after independent evaluation','independently_verified':False,'dataset_sha256':'SHA256 of matching adjusted split','evidence_file':'relative evidence path within runtime output','evidence_sha256':'SHA256 of independently reviewed evidence','docker_only_execution':'true for coding/agentic','full_stateful_rollout':'true for agentic'}],'number_required':131,'existing_definitions_reference':'sovereignai-finetuning/evaluation/README.md; reference oracles remain evaluator-only'})
    bundle=out/'colab-package';bundle.mkdir()
    for s in splits:shutil.copy2(ADJUSTED/(s+'.adjusted.jsonl'),bundle)
    for name in ('release-manifest-adjusted.json','information-boundary-audit.json','computation-leakage-audit.json','colab_format_helpers.py'):shutil.copy2(ADJUSTED/name,bundle)
    for name in ('training-config-candidate.json','dataset-gates.json','independent-baseline-receipt-schema.json'):shutil.copy2(out/name,bundle)
    shutil.copy2(ROOT/'experiments/qlora_ready/colab_readiness_runtime.py',bundle/'readiness.py')
    shutil.copy2(ROOT/'experiments/qlora_ready/training_loss.py',bundle/'training_loss.py')
    shutil.copytree(FACTORY/'base-tokenizer',bundle/'base-tokenizer')
    shutil.copy2(ROOT/'sovereignai-finetuning/evaluation/select_checkpoint.py',bundle)
    shutil.copy2(ROOT/'sovereignai-finetuning/evaluation/README.md',bundle/'EVALUATION_README.md')
    requirements='\n'.join(f'{p}=={v}' for p,v in PINS.items() if p!='torch')+'\n'
    (bundle/'requirements-readiness.txt').write_text(requirements,encoding='utf-8')
    (bundle/'constraints-readiness.txt').write_text('torch=='+PINS['torch']+'\n',encoding='utf-8')
    save(bundle/'package-manifest.json',{'files':{p.name:sha(p) for p in bundle.iterdir() if p.is_file()},'tokenizer_files':{p.name:sha(p) for p in (bundle/'base-tokenizer').iterdir() if p.is_file()},'model':MODEL,'revision':REVISION,'pins':PINS,'production_untouched':True,'no_T01_T15_content_included':True})
    archive=out/'sovereignai-pretraining-readiness-colab.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for p in bundle.rglob('*'):
            if p.is_file():z.write(p,str(p.relative_to(bundle)).replace('\\','/'))
    with zipfile.ZipFile(archive) as z:assert z.testzip() is None
    prefix='''# SovereignAI post-format readiness. These cells are PREPARED, NOT EXECUTED.
RUN_TRAIN = False
RUN_READINESS = False  # Set True only when you manually choose to run GPU readiness.
RUN_INSTALL = False
OUTPUT_DIR = '/content/sovereignai-readiness-evidence'
'''+f'EXPECTED_READINESS_ZIP_SHA256 = {sha(archive)!r}\n'+'''print('Upload sovereignai-pretraining-readiness-colab.zip in the next cell.')
print('No full training. Raw predictions never count as independent validation.')
'''
    upload='''# Upload only the new readiness ZIP; it replaces neither historical data nor production.
from google.colab import files
from pathlib import Path
import hashlib,json,zipfile,sys,subprocess
uploaded = files.upload()
assert len(uploaded) == 1
archive = Path(next(iter(uploaded)))
assert hashlib.sha256(archive.read_bytes()).hexdigest() == EXPECTED_READINESS_ZIP_SHA256
DATA_DIR = Path('/content/sovereignai-pretraining-readiness')
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None and sum(i.file_size for i in z.infolist()) < 200_000_000
    for info in z.infolist():
        p = Path(info.filename)
        assert not p.is_absolute() and '..' not in p.parts and '\\\\' not in info.filename
        assert (info.external_attr >> 16) & 0o170000 != 0o120000
    if not DATA_DIR.exists():
        z.extractall(DATA_DIR)
package = json.loads((DATA_DIR/'package-manifest.json').read_text())
assert package == json.loads(zipfile.ZipFile(archive).read('package-manifest.json')), 'Existing extraction differs; do not overwrite it'
for name, expected in package['files'].items():
    assert hashlib.sha256((DATA_DIR/name).read_bytes()).hexdigest() == expected, name
sys.path.insert(0,str(DATA_DIR))
import readiness
readiness.integrity(DATA_DIR)
print('Adjusted release hashes and partition PASS. No model loaded.')
'''
    install='''# Exact dependency preparation; CUDA PyTorch is retained, never silently replaced.
import importlib.metadata as md
assert md.version('torch') == '2.11.0+cu130', 'Runtime differs from the observed Colab stack'
if RUN_INSTALL:
    subprocess.run([sys.executable,'-m','pip','install','-r',str(DATA_DIR/'requirements-readiness.txt'),'-c',str(DATA_DIR/'constraints-readiness.txt'),'--report','/content/readiness-pip-install-report.json'],check=True)
    print('Restart the runtime session if any training library was imported before installation.')
else:
    print('Installation disabled. Change RUN_INSTALL only when you run this notebook manually.')
'''
    setup='''# Shared stage runner. Each subprocess exits and releases its GPU model before the next stage.
def run_stage(stage):
    if not RUN_READINESS:
        print(stage + ': NOT_TESTED; RUN_READINESS=False')
        return
    subprocess.run([sys.executable,str(DATA_DIR/'readiness.py'),stage,'--data',str(DATA_DIR),'--output',OUTPUT_DIR],check=True)
run_stage('environment')
# Verifies exact versions, CUDA tensor allocation, NF4 imports and records RAM/VRAM/driver.
'''
    modelcell="""# Exact pinned native Base acquisition + load and neutral runtime smoke.
# Downloads native Safetensors, verifies LFS shard SHA-256 and official tokenizer/config.
run_stage('acquire')
run_stage('base-smoke')
# Four neutral prompts test runtime only, not benchmark quality. No generated code is executed.
"""
    baselinecell="""# Validation + internal-test first-response capture. No TRAIN or T01–T15 evaluation.
run_stage('baseline')
# STOP until independent-base-evaluation.json is supplied under OUTPUT_DIR.
# Captured predictions require source-bound semantic review and existing local Docker oracles.
# Agentic cases require full stateful tool rollouts; first-response capture is insufficient.
# Each of 131 reviewed results must bind prediction/split/evidence hashes and original category.
# Never execute generated coding/agentic outputs on the Colab host.
"""
    smokecell="""# One tiny TRAIN-only LoRA update, Base-frozen/gradient/change checks, save + full unload + fresh reload.
# Refuses to run without independently evaluated Base baseline evidence and runtime smoke PASS.
run_stage('qlora-smoke')
# Separate disposable 4096-token TRAIN-derived fit probe; records forward/backward/optimizer peaks.
# No truncated/dropped canonical records and no automatic smaller-length or LoRA fallback.
run_stage('fit')
"""
    traincell="""# Manual full training is DISABLED. Keep RUN_TRAIN=False throughout readiness.
# Prepared Trainer uses official template + assistant-only labels, 579 TRAIN / 65 validation,
# no packing/truncation, epoch checkpoints, two proposed epochs, fresh Base + fresh adapters.
if RUN_TRAIN:
    assert RUN_READINESS, 'All prerequisite stages must have real passing evidence'
    subprocess.run([sys.executable,str(DATA_DIR/'readiness.py'),'train','--data',str(DATA_DIR),'--output',OUTPUT_DIR,'--run-train'],check=True)
else:
    print('Full training disabled. Trainer/checkpoint code is prepared, not executed.')
# Never select a checkpoint by loss or internal-test. Use independent validation scores
# with select_checkpoint.py; then capture/evaluate the selected adapter separately.
# Merging, GGUF conversion and deployment are outside this readiness notebook.
"""
    download="""# Download only actual evidence later, after you manually run readiness.
import shutil
if Path(OUTPUT_DIR).exists():
    shutil.make_archive('/content/sovereignai-readiness-actual-evidence','zip',OUTPUT_DIR)
    files.download('/content/sovereignai-readiness-actual-evidence.zip')
else:
    print('No executed readiness evidence exists yet.')
"""
    codes=[prefix,upload,install,setup,modelcell,baselinecell,smokecell,traincell,download]
    for code in codes:ast.parse(code)
    nb={'nbformat':4,'nbformat_minor':5,'metadata':{'kernelspec':{'name':'python3','display_name':'Python 3'}},'cells':[{'cell_type':'markdown','metadata':{},'source':['# SovereignAI post-format pretraining readiness\n','Preparation only. You run these cells later. RUN_TRAIN=False. GPU compatibility and baseline quality remain untested.\n']},*[{'cell_type':'code','metadata':{},'source':code.splitlines(keepends=True),'execution_count':None,'outputs':[]} for code in codes]]}
    save(out/'sovereignai_qwen35_pretraining_readiness.ipynb',nb);save(out/'colab-cell-sources.json',codes)
    try:training_guard(bundle,out,False)
    except AssertionError as exc:assert 'RUN_TRAIN=False' in str(exc)
    else:raise AssertionError('Training guard failed')
    save(out/'preparation-self-check.json',{'status':'PASS','all_notebook_cells_syntax_checked':True,'runtime_code_syntax_checked':bool(ast.parse((bundle/'readiness.py').read_text())),'training_false_guard_tested':True,'package_verified':True,'dataset_and_canonical_hashes_checked':True,'new_gpu_executions':0})
    gates=read(out/'dataset-gates.json')['gates']
    lines='\n'.join(f'| {key} | {value} |' for key,value in gates.items())
    report=f'''# SovereignAI training readiness

Status: TRAINING_BLOCKED

The adjusted release is validated and the manual Colab readiness/training code is prepared. No new Colab cells were executed because the user's fill-only instruction remains in effect. This is preparation completion, not GPU readiness or measured model success.

| Dataset gate | Result |
|---|---|
{lines}

710 examples: 579 train / 65 validation / 66 internal-test; all 1010 assistant turns rechecked. Canonical hashes and the adjusted release manifest match. The source question, target, family, source and oracle metadata remain unchanged; 44 repaired prompts and 666 unchanged records are preserved. Zero observed computation leakage; numeric coincidences remain legitimate input quantities. Pair triage and original source-bound semantic reviews are preserved. Unflagged latent similarities are not proven absent. RAG/summary checks cover unchanged references and structure, not a fresh model evaluation.

| Runtime gate | Result |
|---|---|
| Environment/CUDA allocation/NF4 import | NOT_TESTED |
| Native pinned Base weights acquisition | NOT_TESTED |
| Actual Base load/forward/generation | NOT_TESTED |
| Independently validated Base baseline | BLOCKED |
| QLoRA forward/backward/update/reload | NOT_TESTED |
| 4096-token GPU fit | NOT_TESTED |
| Full training | NOT_TESTED / disabled |

Model: {MODEL} @ {REVISION}. Expected Qwen3_5ForConditionalGeneration; native Safetensors only. Exact weights are not downloaded here. Tokenizer/config hashes are pinned. The earlier Colab probe showed Tesla T4, 15360 MiB, Python 3.13.15, torch 2.11.0+cu130; this did not test CUDA or training. Intended dependencies are registry-verified versions, not GPU-verified compatibility. Preserve PyTorch and stop on mismatch; installation records pip archive hashes and environment records installed RECORD hashes.

The existing baseline definition captures first responses. It cannot validate complete stateful agent workflows. The notebook explicitly requires independent source-bound review and existing Docker-only coding/agentic validation, with full tool rollouts for agentic tasks. No keyword acceptance rules or fabricated tool calls are added. Baseline results remain empty and BLOCKED rather than model FAIL. Local Docker evidence must be imported; Colab-generated code must never run on its host.

QLoRA candidate: NF4 double-quant, rank16/alpha32/dropout0.05, learning rate1e-4, microbatch1, accumulation16, two proposed epochs, seed42, actual precision conditional on hardware. AdamW is the existing equivalent optimizer; its memory is measured in smoke and fit, not assumed. Sequence length4096 is proposed; actual revised token statistics are in sequence-length-candidate.json. Smoke saves a disposable adapter, fully releases Base/optimizer/tensors, then reloads a fresh pinned Base and saved adapter. A separate TRAIN-derived padded4096 fit probe records load/forward/backward/optimizer memory; its adapter is discarded. OOM or compatibility failure stops without fallback or dataset truncation.

Configuration statuses are per-parameter VERIFIED/PROPOSED/UNKNOWN. The prepared Trainer preserves assistant-only masks, rejects oversize examples, evaluates validation only and saves epoch checkpoints. Checkpoint selection requires independent validation category evidence, not training loss. No merging, GGUF or deployment code is executed. T01–T15 manifest was hashed only; no contents inspected or exported. Production unchanged.

Exact next manual action: upload sovereignignai-pretraining-readiness-colab.zip (actual filename: sovereignai-pretraining-readiness-colab.zip) in the new readiness upload cell; set RUN_INSTALL=True to install pinned dependencies; restart if libraries were already imported; set RUN_READINESS=True and run environment/acquisition/Base smoke/prediction capture in order. Stop at independent baseline review before QLoRA smoke. Keep RUN_TRAIN=False. Runtime evidence cannot be invented to bypass this stop.

Reproducibility: package SHA-256 {sha(archive)}. Complete package, code, registry metadata, candidate configuration, prior hash bindings and notebook are archived here. The local code/package/guard checks pass; GPU execution is intentionally not checked. T4 compatibility and4096 fit remain material risks.

Primary references: [Qwen3.5 model architecture](https://huggingface.co/docs/transformers/model_doc/qwen3_5), [PEFT quantization](https://huggingface.co/docs/peft/developer_guides/quantization), [bitsandbytes PyPI metadata](https://pypi.org/project/bitsandbytes/0.50.2/). These document interfaces; they are not evidence that this exact Colab run passes.
'''
    (out/'TRAINING_READINESS_REPORT.md').write_text(report.replace('sovereignignai-pretraining-readiness-colab.zip (actual filename: sovereignai-pretraining-readiness-colab.zip)','sovereignai-pretraining-readiness-colab.zip'),encoding='utf-8')
    save(out/'readiness-manifest.json',{'status':'TRAINING_BLOCKED','scope':'MANUAL_CELLS_PREPARED_NO_EXECUTION','RUN_TRAIN':False,'RUN_READINESS':False,'files':{str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file()},'canonical_and_adjusted_releases_unchanged':True})
    assert all(sha(RELEASE/n)==d for n,d in original_hashes.items()) and sha(benchmark)==benchmark_sha
    print(json.dumps({'namespace':str(out),'status':'TRAINING_BLOCKED','dataset_gates':'PASS','colab_cells_prepared':len(codes),'model_calls':0,'training_run':False,'package':str(archive),'package_sha256':sha(archive)}))

if __name__=='__main__':main()
