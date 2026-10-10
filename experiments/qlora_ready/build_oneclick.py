"""Build an isolated Run-all notebook without changing the pinned release ZIP."""
import ast
import base64
import hashlib
import json
import shutil
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'sovereignai-finetuning/oneclick-readiness'
PACKAGE=ROOT/'evidence/pretraining-readiness/20261008-173531/sovereignai-pretraining-readiness-colab.zip'
SHA='11179a62a2fb762dd81920e975ece57d20741316abd7382b1d1d995ea2b209d3'


def build():
    assert hashlib.sha256(PACKAGE.read_bytes()).hexdigest()==SHA
    OUT.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(PACKAGE) as z:
        runtime=z.read('readiness.py')
        requirements=z.read('requirements-readiness.txt')
        constraints=z.read('constraints-readiness.txt')
    assets={'readiness.py':runtime,'worker.py':(Path(__file__).with_name('oneclick_worker.py')).read_bytes(),
            'pipeline.py':(Path(__file__).with_name('oneclick_pipeline.py')).read_bytes()}
    hashes={n:hashlib.sha256(v).hexdigest() for n,v in assets.items()}
    encoded={n:base64.b64encode(v).decode() for n,v in assets.items()}
    for n,v in assets.items():
        ast.parse(v);(OUT/n).write_bytes(v)
    (OUT/'requirements-readiness.txt').write_bytes(requirements)
    (OUT/'constraints-readiness.txt').write_bytes(constraints)
    config='''# 1. Immutable configuration. No model imports before installation.
RUN_TRAIN = False
RUN_FULL_BASELINE = True
RUN_QLORA_SMOKE = True
RUN_4096_FIT_PROBE = True
RUN_EXPORT = True
assert RUN_TRAIN is False, "Full training is unavailable in this readiness notebook"
assert all((RUN_FULL_BASELINE, RUN_QLORA_SMOKE, RUN_4096_FIT_PROBE, RUN_EXPORT))
import base64, hashlib, json, sys
from pathlib import Path
BOOT = Path('/content/sovereignai-oneclick-bootstrap')
BOOT.mkdir(exist_ok=True)
'''+f'ASSETS = {encoded!r}\nCODE_HASHES = {hashes!r}\n'+'''
for name, encoded in ASSETS.items():
    content = base64.b64decode(encoded)
    assert hashlib.sha256(content).hexdigest() == CODE_HASHES[name]
    (BOOT/name).write_bytes(content)
sys.path.insert(0,str(BOOT))
import importlib.util
spec = importlib.util.spec_from_file_location('oneclick_pipeline', BOOT/'pipeline.py')
pipeline_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pipeline_module)
pipeline = pipeline_module.Pipeline('/content/sovereignai-oneclick', BOOT, CODE_HASHES)
print('READINESS ONLY. One disposable optimizer update per probe; no full training.')
'''
    sources=[config,
      '# 2. Exact pinned dependencies, pip log/report/check. Fresh child processes avoid imported-library restart hazards.\npipeline.install()',
      '# 3. Measure actual environment, CUDA allocation, native/emulated BF16 and NF4 imports.\npipeline.stage("environment")',
      '# 4. Locate/upload the expected ZIP once, verify/extract and validate dataset.\npipeline.package()',
      '# 5. Exact Base acquisition, pinned native shard/config/tokenizer verification.\npipeline.stage("acquire")',
      '# 6. Actual Base load memory and latency; clean subprocess unload.\npipeline.stage("base-load")',
      '# 7. Neutral runtime smoke only, no quality claim.\npipeline.stage("base-smoke")',
      '# 8. Resumable unchanged first-assistant baseline, all 65 validation + 66 internal-test.\npipeline.stage("baseline")',
      '# 9. Raw capture summary/export; independent review remains pending.\ntry:\n    pipeline.baseline_export()\nexcept Exception as error:\n    pipeline.fail("baseline-integrity",error)',
      '# 10. TRAIN-only disposable QLoRA forward/backward/update/save/reload/freeze smoke.\npipeline.stage("qlora-smoke")',
      '# 11. Actual 4096-token forward/backward/update memory probe, no length fallback.\npipeline.stage("fit")',
      '# 12. Freeze measured/proposed/unknown configuration.\npipeline.configuration()',
      '# 13. Final audit. Missing independent validation remains BASELINE_BLOCKED.\npipeline.report()',
      '# 14. Hash and package actual evidence, including failures/logs.\narchive = pipeline.export()',
      '# 15. Download evidence automatically; full training hard guard.\nassert RUN_TRAIN is False, "Full training unavailable: revalidation is required in a separate training workflow"\nfrom google.colab import files\nfiles.download(str(archive))\nprint("Training: DISABLED. NEXT ACTION: return the evidence ZIP for independent baseline review.")']
    cells=[{'cell_type':'markdown','metadata':{},'source':[
      '# SovereignAI — one-click readiness\n',
      'Upload the exact readiness ZIP through Files if desired, then **Runtime → Run all**.\n',
      'Only the missing-ZIP upload widget is interactive. No full training.\n',
      'Baseline capture is not independent correctness. Disposable QLoRA/4096 probes are allowed independently of quality review.\n',
      'Session disk survives a disconnect/session restart, not runtime deletion. Download your evidence.\n']}]
    cells += [{'cell_type':'code','execution_count':None,'metadata':{},'outputs':[],
               'source':[line+'\n' for line in source.splitlines()]} for source in sources]
    notebook={'nbformat':4,'nbformat_minor':5,'metadata':{'accelerator':'GPU','colab':{'name':'SovereignAI_OneClick_Readiness.ipynb'},
                  'kernelspec':{'name':'python3','display_name':'Python 3'},'language_info':{'name':'python'}},'cells':cells}
    notebook_path=OUT/'SovereignAI_OneClick_Readiness.ipynb'
    notebook_path.write_text(json.dumps(notebook,indent=2),encoding='utf-8')
    registry={'package_sha256':SHA,'source_hashes':hashes,'notebook_sha256':hashlib.sha256(notebook_path.read_bytes()).hexdigest(),
              'pins':{'torch':'2.11.0+cu130','transformers':'5.19.0','peft':'0.21.1','bitsandbytes':'0.50.2','accelerate':'1.15.0','datasets':'4.8.5'},
              'full_training_enabled':False,'GPU_execution_this_build':False}
    (OUT/'dependency-lock-registry.json').write_text(json.dumps(registry,indent=2)+'\n')
    proposed={k:{'value':v,'status':'PROPOSED'} for k,v in {'sequence_length':4096,'rank':16,'alpha':32,'dropout':.05,
                  'learning_rate':1e-4,'microbatch':1,'accumulation':16,'epochs':2,'seed':42,'optimizer':'AdamW'}.items()}
    proposed['RUN_TRAIN']={'value':False,'status':'VERIFIED'}
    (OUT/'training-config-candidate.json').write_text(json.dumps(proposed,indent=2)+'\n')
    (OUT/'README.md').write_text('''# SovereignAI one-click readiness

UPLOAD ZIP → Runtime → Run all → WAIT → DOWNLOAD evidence ZIP

Open `SovereignAI_OneClick_Readiness.ipynb` in Colab with a GPU runtime. Upload
`sovereignai-pretraining-readiness-colab.zip` once through Files (or use the widget
shown automatically when absent). Press Runtime → Run all. Wait for the final
automatic evidence download. No cell selection, path typing, or flag edits.

Only the pinned Base/release is accepted. Wrong pins, conflicts, missing CUDA,
hash mismatch, model/probe failure or OOM blocks dependent stages. Reports and
export still run. No model/length fallback or full training exists here.

Valid stage receipts and per-record baseline checkpoints are hash-checked and
resumed on Run all. Current environment is remeasured. Prior attempts remain.
Session disk survives browser disconnect/session restart, not runtime deletion.
A destroyed runtime requires restoring data externally; this notebook does not
silently mount Drive or claim persistent storage across deleted runtimes.

Raw baseline outputs do not authorize training. Independent semantic review,
Docker-only coding validation and full agentic rollouts still remain external.
QLoRA and 4096 probes perform single disposable TRAIN-only updates and remove
temporary adapters. No production adapter/checkpoint is produced.
''',encoding='utf-8')
    return OUT


if __name__=='__main__':print(build())
