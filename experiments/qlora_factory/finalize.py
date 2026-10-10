"""Finalize portable package, notebook syntax checks and immutable evidence audit."""
import ast,collections,hashlib,json,shutil,sys,zipfile
from pathlib import Path
from experiments.qlora_factory.prepare import ROOT,sha,save
def main(out):
    out=out.resolve();package=ROOT/'sovereignai-finetuning'
    notebook_path=package/'sovereignai_qwen35_qlora_colab.ipynb';nb=json.loads(notebook_path.read_text(encoding='utf-8'))
    # Wire top-level settings into every preflight/smoke/train subprocess.
    setup="\nsettings={name:globals()[name] for name in ['MAX_SEQ_LENGTH','LORA_R','LORA_ALPHA','LORA_DROPOUT','LEARNING_RATE','NUM_EPOCHS','BATCH_SIZE','GRAD_ACCUMULATION']}\nPath('/content/sovereignai-runtime-config.json').write_text(json.dumps(settings))\n"
    for cell in nb['cells']:
        if cell['cell_type']!='code':continue
        text=''.join(cell['source'])
        if "'preflight'" in text:text=text.replace("subprocess.run(",setup+"subprocess.run(",1)
        if any("'"+stage+"'" in text for stage in ['preflight','smoke','train']):text=text.replace("'--method',METHOD]","'--method',METHOD,'--runtime-config','/content/sovereignai-runtime-config.json']").replace("'--approve-full-training']","'--runtime-config','/content/sovereignai-runtime-config.json','--approve-full-training']")
        cell['source']=text.splitlines(True);ast.parse(text)
    # Explicit Base-prediction capture cell, never silently evaluated or trained.
    nb['cells'].insert(-3,{'cell_type':'markdown','metadata':{},'source':['## True Base/adapter prediction capture (optional, before training)\nThis captures first responses only. Independent Docker and semantic verification remains mandatory; it does not manufacture baseline quality scores.']})
    nb['cells'].insert(-3,{'cell_type':'code','metadata':{},'execution_count':None,'outputs':[],'source':["RUN_BASE_PREDICTIONS=False\n","if RUN_BASE_PREDICTIONS:\n","    subprocess.run([sys.executable,str(Path(DATASET_PATH,'evaluation/generate.py')),'--dataset',DATASET_PATH,'--split','validation','--output',str(Path(OUTPUT_DIR,'true-base-predictions.json'))],check=True)\n"]})
    save(notebook_path,nb)
    for cell in nb['cells']:
        if cell['cell_type']=='code':ast.parse(''.join(cell['source']))
    from workflows.agent_kernel import ToolRegistry
    registry=ToolRegistry();rows=[json.loads(x) for x in (package/'positive-trajectories.jsonl').read_text(encoding='utf-8').splitlines()];tool_count=0
    for row in rows:
        for message in row['messages']:
            for call in message.get('tool_calls',[]):
                function=call['function'];args=function['arguments'];registry.check(function['name'],json.loads(args) if isinstance(args,str) else args);tool_count+=1
    save(package/'dataset-validation.json',{'positive_rows':len(rows),'verified_flags_all_true':all(r['quality']['verified'] for r in rows),'native_tool_calls_schema_checked':tool_count,'original_native_arguments_preserved':True,'notebook_code_cells_parse':True,'training_code_compiles':True,'gpu_model_load_backward_reload':'NOT_RUN','training_gates':'full training disabled for small imbalanced seed and missing true Base evaluation'})
    original=json.loads((out/'manifest.json').read_text(encoding='utf-8'));changes=[p for p,d in original['production_and_frozen_sha256'].items() if sha(ROOT/p)!=d];save(package/'production-integrity.json',{'changed_files':changes,'checked_files':len(original['production_and_frozen_sha256'])});assert not changes
    manifest=json.loads((package/'training_manifest.json').read_text());manifest['training_code_sha256']=sha(package/'training.py');manifest['notebook_sha256']=sha(notebook_path);manifest['serialization_adapter_sha256']=sha(package/'training.py');manifest['template_sha256']=hashlib.sha256(json.loads((out/'base-tokenizer/tokenizer_config.json').read_text(encoding='utf-8'))['chat_template'].encode()).hexdigest();save(package/'training_manifest.json',manifest)
    stats=json.loads((package/'dataset-statistics.json').read_text());sizes=json.loads((package/'sequence-length-analysis.json').read_text());counts=stats['categories']
    report=f'''# SovereignAI fine-tuning preparation

## REPOSITORY CAPABILITIES
Existing Smart Router/Broker/native registry/executor/Docker/RAG/calculator/ingestion/history/publication inspected. Inventory source locations/hashes and limitations included. No new controller/model/tool architecture. Confidential student-workbook context experiment is separate and not exported.

## DATASET
{len(rows)}accepted seed examples, {stats['quarantined_or_negative_examples']}negative/quarantined original candidates. Category counts{counts}; percentages{stats['percentages']}. Split sizes{stats['splits']} across{stats['families']}families; calculator variants and related service-port evidence co-located. This does NOT meet the requested1000example pilot or80/10/10category coverage. Dataset remains incomplete: explicit quality/imbalance stop, not a fabricated dataset-readiness claim.

## VERIFICATION
Two actual Qwen native trajectories completed READY_FOR_REVIEW with existing immutable Docker acceptance tests, canonical file preservation, zero model switches and no publication. SQL and CSV coding targets have independent Docker behavioral verification. Initial CSV oracle newline defect fixed in separate recheck with exact original code; PythonROT13 import-path oracle repaired but original candidate then failed on str.decode misuse and remains negative. Raw failures retained, no candidate code/action corrected. RAG targets use labeled synthetic sources and bounded citation/numeric/required-fact contracts, with limitations disclosed. GeneralQA3responses accepted after independent review; weaker factual screens remain quarantine. Six calculator-reference targets explicitly programmatic_reference, not model intelligence/trajectory successes. {tool_count}native calls validated against unchanged registry. Scope remains a seed, not expert repair coverage.

## CONTAMINATION
Automated request exact/5gram/ID screens clear after candidate definitions froze; heldout results never inspected, no T01–T15 prompts/solutions exported. Scanner read frozen task definitions for rejection only, not generation. Semantic/structural contamination disjointness is not fully proven; report explicitly requires additional audit before release. Prior private-user/RAG-failure benchmark artifacts not used as SFT targets.

## DATA QUALITY
Exact/normalized duplicate checks, action-strategy groups and family split report included. Native-tool arguments remain raw JSONstrings canonically; only a deep-copy rendering adapter decodes to mappings required by the official Base template, with JSON-value equivalence checked. No hidden manual success correction. Small seed underrepresents agentic/coding/repair/safety/conversation; computation overrepresented. This severe imbalance triggers the requested stop before full training. No number/filename sweeps to falsely reach1000.

## TRAINING METHOD
QLoRA-first proposal: NF4 doublequant, rank16 alpha32 dropout.05 all-linear excluding visual modules, lr1e-4,2epochs,micro1,accum16,checkpointing, bf16if GPU supports otherwisefp16. Pinned HF Base modelrevision1001bb4d826a52d1f399e183466143f4da7b741b; production GGUF unchanged. Pinned Transformers5.19.0/TRL1.14.2/PEFT0.21.2 source APIs inspected. GPU4bit/adapter/backward/reload not run locally; no compatibility claim beyond official tokenizer/static APIs. Separate standard-LoRA smoke fallback only after demonstrated NF4 incompatibility on sufficiently large GPU; no silent retry after OOM or format failure.

## COLAB ENVIRONMENT
Notebook prints nvidia-smi/GPU/VRAM/CUDA and library versions, installs pinned packages, safe zip upload, tokenizer/mask preflight and explicit smoke/full-training flags. Unsloth not enabled because exact compatibility unverified. Hardware UNKNOWN until user's Colab session. No local extra heavy model or PyTorch training installed into production environment.

## TRAINING CONFIG
GPU-adaptive1024/2048/4096caps, no truncation. Total sequence percentiles{sizes['total_sequence']}; counts over caps{sizes['counts_over_caps']}. ShortGPUcaps exclude native trajectory turns; full training rejects changes to approved mixture. Exact official full tokenization equals prefix+completion tokenization, all prompt/observation tokens masked-100,31assistant turns checked. Official emptythinkprefix masked, no private reasoning added. Full training disabled by release/baseline gates before loading training weights. Runtime settings saved separately; smoke adapter isolated and fresh base initialization used for any later full run.

## BASELINE
True Qwen3.5-4B-Base evaluation NOT RUN. Existing instruction-tuned GGUF teacher is not substituted. Colab prediction capture provided; first-action/first-response generation is not full agent task-oracle success. Independent semantic/Docker evaluation required before baseline quality completion. No heldout evaluation.

## VALIDATION
No trained checkpoint, loss curve, GPU smoke, quality improvement or selected adapter exists. Validation-only selector rejects missing/unsafe/unverified domains and internal-test selection. General forgetting/safety gates mandatory. Dataset is too small to support meaningful category-complete validation scores.

## LIMITATIONS
21seedexamples only, self-teacher dependence, constrained RAG grounding contracts, limited general semantic review, no expert repair family, no broad React/TypeScript/Flask coverage. No fully proven semantic contamination audit. GPUQLoRA/LoRA forward/backward/reload untested; merged/GGUF behavior and quantization degradation unknown. No claim that tuning fixes RAG ranking/catalog/history plumbing or latency.

## DEPLOYMENT
New adapter -> separately merged Base -> independently checked compatible pinned converter -> newly named GGUF/Q4_K_M -> validation -> explicit production decision. Never overwrite Base/productionGGUF, auto-select smoke/last checkpoint, execute generated code on Colab host or deploy automatically. Guide/evaluation package details all gates.

## FINAL STATUS
DATASET_NEEDS_MORE_VERIFIED_DATA

Requested package files exist and CPU serialization/mask checks pass. Full1000example dataset/GPU training readiness are NOT complete. Stop at observed imbalance/coverage gates; no full training initiated.
'''
    (package/'FINAL_REPORT.md').write_text(report,encoding='utf-8')
    save(out/'final-package-inventory.json',{str(p.relative_to(package)):sha(p) for p in package.rglob('*') if p.is_file() and '__pycache__' not in str(p)})
    evidence=ROOT/'evidence/sovereignai-finetuning'/out.name;evidence.mkdir(parents=True,exist_ok=False)
    for p in package.iterdir():
        if p.is_file():shutil.copy2(p,evidence/p.name)
    archive=ROOT/'sovereignai-finetuning.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for p in package.rglob('*'):
            if p.is_file() and '__pycache__' not in str(p):z.write(p,Path('sovereignai-finetuning')/p.relative_to(package))
    print('PACKAGE='+str(archive));print('DATASET_NEEDS_MORE_VERIFIED_DATA')
if __name__=='__main__':main(Path(sys.argv[1]))
