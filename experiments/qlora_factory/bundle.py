"""Package audited seed and Colab scripts. Never mark a sparse seed release-ready."""
import ast,collections,hashlib,json,re,shutil,sys,zipfile
from pathlib import Path
import numpy as np
from experiments.qlora_factory.prepare import ROOT,save,sha
from experiments.qlora_factory.seed import jsonl
def user_text(row):
    text=[]
    for m in row.get('messages',[]):
        if m['role']!='user':continue
        value=m.get('content','')
        try:
            obj=json.loads(value);value=obj.get('original_request',obj.get('question',obj.get('expression',value))) if isinstance(obj,dict) else value
        except ValueError:pass
        text.append(value)
    return '\n'.join(text)
def norm(text):return ' '.join(re.findall(r'\w+',text.lower()))
def shingles(text,n=5):
    words=norm(text).split();return {tuple(words[i:i+n]) for i in range(max(0,len(words)-n+1))}
def build(out):
    out=out.resolve();package=ROOT/'sovereignai-finetuning';package.mkdir(exist_ok=False)
    rows=[json.loads(x) for x in (out/'positive-trajectories-reviewed.jsonl').read_text(encoding='utf-8').splitlines()]
    negatives=[json.loads(x) for x in (out/'negative-trajectories.jsonl').read_text(encoding='utf-8').splitlines()]
    # Generation was already frozen; isolated rejection-only holdout scan, no result inspection.
    holdouts=json.loads((ROOT/'evidence/code-agent-fidelity-v1/reports/tasks.json').read_text(encoding='utf-8'))
    scan=[];accepted=[];rejected=[]
    for row in rows:
        text=user_text(row);sh=shingles(text);scores=[]
        for task in holdouts:
            hs=shingles(task['request']);union=sh|hs;similarity=len(sh&hs)/len(union) if union else 0
            scores.append({'holdout_id':task['task_id'],'request_5gram_jaccard':similarity,'exact_request_match':norm(text)==norm(task['request'])})
        suspicious=any(s['exact_request_match'] or s['request_5gram_jaccard']>.3 for s in scores) or bool(re.search(r'\bT(?:0[1-9]|1[0-5])\b',text))
        scan.append({'id':row['id'],'suspicious':suspicious,'comparisons':scores})
        if suspicious:rejected.append(row)
        else:accepted.append(row)
    report={'status':'AUTOMATED_SCREEN_CLEAR' if not rejected else 'CONTAMINATION_DETECTED','holdout_used_for_generation':False,'holdout_results_inspected':False,'candidate_definitions_frozen_before_scan':True,'scan':scan,'rejected_ids':[r['id'] for r in rejected],'limitations':'Lexical rejection screen does not prove semantic disjointness; structural/semantic manual audit required before release. Generic tool schemas/system prompts/fixture test filename are infrastructure, not benchmark tasks. No benchmark request/solution appears in exported positives.'}
    save(out/'contamination-report.json',report)
    if rejected:raise RuntimeError('CONTAMINATION_DETECTED: dataset preparation stopped')
    duplicate_groups=collections.defaultdict(list);action_groups=collections.defaultdict(list)
    for row in accepted:
        duplicate_groups[hashlib.sha256(norm(user_text(row)).encode()).hexdigest()].append(row['id'])
        actions=[c['function']['name'] for m in row['messages'] for c in m.get('tool_calls',[])];action_groups[tuple(actions)].append(row['id'])
        if row['category']=='computation':row['family']='literal-calculator'
        if row['id'] in ('direct','relation'):row['family']='synthetic-service-ports'
    exact_dupes=[g for g in duplicate_groups.values() if len(g)>1]
    if exact_dupes:raise RuntimeError('Duplicate requests must be audited before export')
    families=sorted({r['family'] for r in accepted},key=lambda x:hashlib.sha256(x.encode()).hexdigest());n=len(families);train_end=int(n*.8);val_end=train_end+max(1,int(n*.1))
    splits={f:'train' if i<train_end else 'validation' if i<val_end else 'internal-test' for i,f in enumerate(families)}
    for split in ('train','validation','internal-test'):jsonl(package/(split+'.jsonl'),[r for r in accepted if splits[r['family']]==split])
    jsonl(package/'positive-trajectories.jsonl',accepted);jsonl(package/'negative-trajectories.jsonl',negatives)
    counts=dict(collections.Counter(r['category'] for r in accepted));stats={'accepted_examples':len(accepted),'quarantined_or_negative_examples':len(negatives),'categories':counts,'percentages':{c:100*v/len(accepted) for c,v in counts.items()},'splits':{s:sum(splits[r['family']]==s for r in accepted) for s in ('train','validation','internal-test')},'families':n,'authorship':dict(collections.Counter(r['source']['kind'] for r in accepted)),'target_examples':1000,'target_mix':{'agentic':30,'rag':25,'coding':20,'general_qa':10,'computation':5,'summarization':5,'safety':5},'release_ready':False,'reason':'Small verified seed, insufficient diverse agentic/coding/repair/conversation/safety families; computation overrepresented. Do not full-train this as the1000example pilot.'}
    save(package/'dataset-statistics.json',stats);save(package/'training-mixture.json',stats)
    save(package/'deduplication-report.json',{'exact_or_normalized_request_duplicates':exact_dupes,'action_sequence_groups':[{'actions':list(a),'ids':ids,'not_removed_only_for_same_strategy':True} for a,ids in action_groups.items() if a],'family_splits':splits,'near_duplicate_policy':'calculator and same-service source family co-located; manual semantic-family review required','semantic_dedup_complete':False})
    for name in ('repository-capability-inventory.json','PREREGISTRATION.md','contamination-report.json','oracle-results.json','trajectory-inventory.json','upstream.json','independent-review.json'):
        shutil.copy2(out/name,package/name)
    save(package/'rag-source-inventory.json',{'sources':[{'sample':r['id'],'class':'synthetic-controlled','source_owner':'experiment-generated fixture','license':'operator-authored synthetic task fixture; no public corpus imported','texts':[e['text'] for e in r.get('evidence',[])]} for r in accepted if r.get('evidence')],'private_student_workbook_exported':False})
    save(package/'baseline-evaluation.json',{'status':'NOT_RUN_TRUE_BASE_UNAVAILABLE_LOCALLY','true_base_evaluated':False,'base_model':'Qwen/Qwen3.5-4B-Base','production_instruct_gguf_is_not_base':True,'holdout_evaluated':False,'next_runtime':'Colab before training; no local second heavy model'})
    save(package/'training-method-decision.json',{'proposed':'QLoRA','gpu_smoke':'NOT_RUN_NO_COLAB_GPU_SESSION','not_claimed_compatible_until_smoke':True,'fallback':'standard LoRA only after NF4 compatibility failure and sufficient GPU memory; independent evidence run','unsloth':'not enabled; compatibility not demonstrated'})
    versions=json.loads((out/'upstream.json').read_text())['pypi_versions']
    (package/'requirements-colab.txt').write_text('\n'.join(p+'=='+v for p,v in versions.items())+'\nPyYAML==6.0.3\njinja2==3.1.6\n',encoding='utf-8')
    config={'base_model':'Qwen/Qwen3.5-4B-Base','base_revision':json.loads((out/'upstream.json').read_text())['revision'],'method':'qlora','quantization':'nf4','double_quantization':True,'lora_r':16,'lora_alpha':32,'lora_dropout':.05,'target_modules':'all-linear','exclude_modules':'.*visual.*','learning_rate':1e-4,'epochs':2,'micro_batch_size':1,'gradient_accumulation':16,'optimizer':'adamw_torch','gradient_checkpointing':True,'thinking':False,'seed':42,'full_training_enabled':False,'sequence_length':'GPU cap1024/2048/4096; complete trajectories only, no truncation','checkpoint_selection':'validation oracle quality; never automatic loss-only or T01-T15 selection'}
    import yaml
    (package/'qlora_config.yaml').write_text(yaml.safe_dump(config,sort_keys=False));(package/'training_environment.yaml').write_text(yaml.safe_dump(versions,sort_keys=False))
    shutil.copy2(ROOT/'experiments/qlora_factory/training.py',package/'training.py')
    save(package/'training_manifest.json',{'base_model':config['base_model'],'base_revision':config['base_revision'],'dataset_sha256':{s+'.jsonl':sha(package/(s+'.jsonl')) for s in ('train','validation','internal-test')},'release_ready':False,'seed_only':True,'training_code_sha256':sha(package/'training.py'),'config_sha256':sha(package/'qlora_config.yaml'),'tokenizer_config_sha256':sha(out/'base-tokenizer/tokenizer_config.json')})
    guide='''# SovereignAI Colab QLoRA preparation

This package contains a small independently screened seed, not the requested1000example training release. Full training is deliberately gated until more verified diverse data, semantic contamination review and a true Base baseline exist. There is no trained adapter here. The production GGUF remains unchanged.

1. Upload sovereignai-finetuning.zip to Colab using the notebook upload cell. Choose a GPU runtime. The notebook prints GPU/VRAM/CUDA and package versions; it does not assume T4/L4/A100.
2. Run the package installation cell before importing torch. Pinned versions are recorded in requirements-colab.txt. If packages were already imported with incompatible versions, restart the Colab session and rerun; do not mix loaded versions.
3. Public Base model downloads need no token by default. If authentication is required, use huggingface_hub.login with Colab's secret store; never put credentials into dataset cells.
4. Run dataset validation and official-tokenizer preview. Exact role/tool structure is retained. Labels use-100 on prompts and tool observations. Assistant completion boundaries must match the official pinned template; no custom control tokens or hidden reasoning targets. Oversize turns are rejected without truncation.
5. Enable RUN_SMOKE at the top only when ready to use your Colab GPU. The smoke loads NF4, attaches LoRA, performs forward/backward/optimizer/validation, saves an isolated smoke adapter, unloads/reloads it and verifies another forward. Any failure stops. It is not a quality-improved product.
6. If NF4 implementation is unsupported, read failure.json. A separate LoRA smoke can be selected with METHOD='lora' on sufficiently large GPU. Do not treat OOM, format errors or missing kernels as proof that only quantization is broken. Do not auto-fallback after a partly executed run.
7. Gather independent data toward300agentic/250RAG/200coding/100general/50computation/50summary/50safety. Do not copy held-out tasks or alter existing negatives. Raw producer generation, immutable independent oracles and family-isolated splits are required. Current sparse data must not be padded with number/filename variations.
8. Evaluate true Qwen3.5-4B-Base before training, not the instruction-tuned laptop GGUF. Coding/agentic evaluation requires the existing pinned local Docker oracle; do not execute generated code on the Colab host. General/RAG evaluation needs independent semantic contracts, not answer substring presence alone. Evaluation skeleton is provided and explicitly stops where independent runtime/oracle evidence is absent.
9. Only after data release and baseline gates pass, explicitly enable RUN_TRAIN. Start with100–300complete samples for a technical pilot, then the approved1000example cohort. Config starts2epochs; check every epoch. The script creates checkpoints and does not automatically select by loss. Upload independently verified validation category scores to the selection script. Never use internal-test or T01–T15 for checkpoint selection.
10. Preserve the original Base weights, model revision, dataset/code/template hashes and environment reports. Export adapter in a new directory. Merge only a selected adapter into a separately loaded nonquantized Base, with enough CPU/GPU memory. Recheck Base/adapter/merged behavior independently.
11. GGUF export is a later gate: build a pinned compatible llama.cpp checkout and use its supported convert_hf_to_gguf.py on the new merged artifact, then llama-quantize to a new Q4_K_M file. Do not assume the existing b11132 converter supports the merged architecture. Conversion and postquantization tool/RAG/general regressions must pass before registry integration. No production replacement happens from this notebook.

The notebook is self-contained for package upload/preflight/smoke/training gating. GPU smoke and full Base quality evaluation have not been performed in this Windows preparation session. Fine-tuning changes behavior; it does not fix catalog sizing, retrieval ranking or followup-context plumbing.
'''
    (package/'QLORA_TRAINING_GUIDE.md').write_text(guide,encoding='utf-8')
    (package/'README.md').write_text('# SovereignAI Qwen3.5-4B fine-tuning seed\n\nStatus: DATASET_NEEDS_MORE_VERIFIED_DATA. No trained adapter or benchmark gain claimed. See QLORA_TRAINING_GUIDE.md and dataset-statistics.json. Base Apache-2.0 model/license pinned; public training corpus and external paid teacher not used. Synthetic references and self-generation provenance explicit. No private student workbook is included. GPU hardware/smoke results unknown until Colab execution.\n')
    notebook(package,config)
    ast.parse((package/'training.py').read_text())
    save(out/'package-preparation.json',{'package':str(package),'accepted':len(accepted),'status':'DATASET_NEEDS_MORE_VERIFIED_DATA'})
    print(package,len(accepted),stats,flush=True)
def notebook(package,config):
    cells=[]
    def md(text):cells.append({'cell_type':'markdown','metadata':{},'source':text.splitlines(True)})
    def code(text):cells.append({'cell_type':'code','metadata':{},'execution_count':None,'outputs':[],'source':text.splitlines(True)})
    md('# SovereignAI Qwen3.5-4B — QLoRA-first, LoRA fallback\nPreparation only. This seed is not release-ready. GPU smoke is separate from full training; neither has run here. No T01–T15 data, no automatic deployment.')
    code("MODEL_NAME='Qwen/Qwen3.5-4B-Base'\nMODEL_REVISION='1001bb4d826a52d1f399e183466143f4da7b741b'\nDATASET_PATH='/content/sovereignai-finetuning'\nOUTPUT_DIR='/content/sovereignai-adapter'\nMAX_SEQ_LENGTH=None  # GPU-adaptive cap; no truncation\nLORA_R=16\nLORA_ALPHA=32\nLORA_DROPOUT=0.05\nLEARNING_RATE=1e-4\nNUM_EPOCHS=2\nBATCH_SIZE=1\nGRAD_ACCUMULATION=16\nMETHOD='qlora'\nRUN_SMOKE=False\nRUN_TRAIN=False\n")
    md('## 1. Inspect environment before imports/installations')
    code("import sys,subprocess,importlib.metadata as metadata\nsubprocess.run(['nvidia-smi'],check=False)\nfor name in ['torch','transformers','peft','trl','bitsandbytes','unsloth']:\n    try: print(name, metadata.version(name))\n    except metadata.PackageNotFoundError: print(name,'not installed')\n")
    md('## 2. Upload the package zip safely')
    code("from google.colab import files\nfrom pathlib import Path\nimport zipfile\nuploaded=files.upload()\narchive=next(name for name in uploaded if name.endswith('.zip'))\nroot=Path('/content').resolve()\nwith zipfile.ZipFile(archive) as z:\n    for member in z.infolist():\n        target=(root/member.filename).resolve()\n        if not target.is_relative_to(root): raise ValueError('Unsafe zip entry')\n        if member.file_size>100_000_000: raise ValueError('Unexpected large file in package')\n    z.extractall(root)\nassert Path(DATASET_PATH,'training_manifest.json').is_file()\n")
    md('## 3. Install pinned versions; restart session if incompatible modules were already loaded')
    code("subprocess.run([sys.executable,'-m','pip','install','-r',str(Path(DATASET_PATH,'requirements-colab.txt'))],check=True)\n")
    md('## 4–8. GPU, dataset hashes, contamination and official-tokenizer/loss-mask preflight')
    code("import torch,json\nprint('CUDA',torch.version.cuda,'PyTorch',torch.__version__)\nif not torch.cuda.is_available(): raise RuntimeError('Choose a Colab GPU runtime')\nprint(torch.cuda.get_device_name(0),torch.cuda.get_device_properties(0).total_memory/2**30,'GiB')\nprint(json.loads(Path(DATASET_PATH,'dataset-statistics.json').read_text()))\nsubprocess.run([sys.executable,str(Path(DATASET_PATH,'training.py')),'preflight','--dataset',DATASET_PATH,'--output',OUTPUT_DIR,'--method',METHOD],check=True)\n")
    md('## 9–17. Explicit smoke gate:4-bit model load, LoRA, one update, validation, save/reload\nRead failure.json on failure. Standard LoRA fallback is a separate smoke on a sufficiently large GPU. No silent method changes.')
    code("if RUN_SMOKE:\n    subprocess.run([sys.executable,str(Path(DATASET_PATH,'training.py')),'smoke','--dataset',DATASET_PATH,'--output',OUTPUT_DIR,'--method',METHOD],check=True)\nelse: print('Smoke not authorized by notebook flags; nothing trained.')\n")
    md('## 18. Full training gate\nThe bundled sparse seed cannot pass release/baseline gates. Acquire and independently audit the full balanced pilot first. Do not manually toggle release_ready to bypass validation.')
    code("if RUN_TRAIN:\n    subprocess.run([sys.executable,str(Path(DATASET_PATH,'training.py')),'train','--dataset',DATASET_PATH,'--output',OUTPUT_DIR,'--method',METHOD,'--approve-full-training'],check=True)\nelse: print('Full training disabled; no checkpoint selected/deployed.')\n")
    md('## 19–20. Validation-only checkpoint review, forgetting and export gates\nUse evaluation/ scripts. Never select solely by loss. Export a newly named adapter; merge on a separately loaded full-precision Base only after validation quality review. GGUF conversion must use a verified compatible pinned converter and a new filename; compare adapter, merged and Q4_K_M behavior before any production change. Generated coding execution belongs in the existing local Docker sandbox, never on the Colab host.')
    md('## 21. Download actual artifacts only')
    code("import shutil\nif Path(OUTPUT_DIR).exists():\n    shutil.make_archive('/content/sovereignai-actual-artifacts','zip',OUTPUT_DIR)\n    files.download('/content/sovereignai-actual-artifacts.zip')\nelse: print('No GPU/training artifacts exist yet.')\n")
    save(package/'sovereignai_qwen35_qlora_colab.ipynb',{'nbformat':4,'nbformat_minor':5,'metadata':{'kernelspec':{'display_name':'Python 3','language':'python','name':'python3'},'colab':{'name':'sovereignai_qwen35_qlora_colab.ipynb','provenance':[]}},'cells':cells})
if __name__=='__main__':build(Path(sys.argv[1]))
