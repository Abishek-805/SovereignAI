"""Prepare audit-only Colab cells and a hash-bound adjusted release, without executing them."""
import ast, json, zipfile
from pathlib import Path
from experiments.qlora_ready.audit import ROOT, FACTORY, sha, save

def main(out):
    manifest=json.loads((out/'release-manifest-adjusted.json').read_text())
    assert manifest['status']=='FORMAT_GATE_RECOVERED'
    for name,digest in manifest['artifact_sha256'].items():assert sha(out/name)==digest
    def function(path,name):
        source=path.read_text(encoding='utf-8');node=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name==name)
        return ast.get_source_segment(source,node)+'\n'
    helper='import copy,json,re\n'+function(ROOT/'sovereignai-finetuning/training.py','tokenize_turns')+function(ROOT/'experiments/qlora_ready/repair_computation.py','scan')
    (out/'colab_format_helpers.py').write_text(helper,encoding='utf-8');ast.parse(helper)
    package=out/'sovereignai-adjusted-release-colab.zip'
    names=['train.adjusted.jsonl','validation.adjusted.jsonl','internal-test.adjusted.jsonl','release-manifest-adjusted.json','computation-leakage-audit.json','information-boundary-audit.json','tokenizer-adjusted-audit.json','dataset-integrity-recheck.json','semantic-contamination-recheck.json','FINAL_REPORT.md','colab_format_helpers.py']
    packaged={n:sha(out/n) for n in names}
    save(out/'colab-package-manifest.json',{'files':packaged,'tokenizer_files':{p.name:sha(p) for p in (FACTORY/'base-tokenizer').iterdir() if p.is_file()},'helper_sha256':sha(out/'colab_format_helpers.py'),'training_code_included':False,'base_weights_included':False})
    with zipfile.ZipFile(package,'w',zipfile.ZIP_DEFLATED) as z:
        for name in names+['colab-package-manifest.json']:z.write(out/name,name)
        for p in (FACTORY/'base-tokenizer').iterdir():
            if p.is_file():z.write(p,'base-tokenizer/'+p.name)
    with zipfile.ZipFile(package) as z:assert z.testzip() is None
    zipsha=sha(package)
    codes=[
        '# 1. SovereignAI adjusted-release verification ONLY. Run these cells yourself.\n# No Base model load, baseline evaluation, smoke, LoRA or QLoRA in this stage.\nRUN_TRAIN = False\nRUN_SMOKE = False\nRUN_BASE_EVALUATION = False\nRUN_INSTALL_TOKENIZER = False\nMODEL_NAME = "Qwen/Qwen3.5-4B-Base"\nMODEL_REVISION = "1001bb4d826a52d1f399e183466143f4da7b741b"\nEXPECTED_ZIP_SHA256 = '+repr(zipsha)+'\nprint("710 records: train 579 / validation 65 / internal-test 66")\nprint("44 corrected computation inputs; 666 unchanged. Canonical data preserved.")\nprint("Training remains disabled. Upload sovereignai-adjusted-release-colab.zip in cell 2.")\n',
        '''# 2. Upload the adjusted release ZIP linked in the completion report.
from google.colab import files
from pathlib import Path
import hashlib, json, zipfile, sys
uploaded = files.upload()
assert len(uploaded) == 1, "Upload exactly the adjusted-release ZIP"
archive = Path(next(iter(uploaded)))
assert hashlib.sha256(archive.read_bytes()).hexdigest() == EXPECTED_ZIP_SHA256, "Wrong or modified release ZIP"
DATASET_PATH = Path('/content/sovereignai-adjusted-release')
assert not DATASET_PATH.exists(), "Do not overwrite an existing extraction; use a fresh runtime or inspect it"
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    assert sum(i.file_size for i in z.infolist()) < 200_000_000
    for info in z.infolist():
        p = Path(info.filename)
        assert not p.is_absolute() and '..' not in p.parts and '\\\\' not in info.filename
        assert (info.external_attr >> 16) & 0o170000 != 0o120000, "Symlink rejected"
    z.extractall(DATASET_PATH)
package = json.loads((DATASET_PATH / 'colab-package-manifest.json').read_text())
for name, digest in package['files'].items():
    assert hashlib.sha256((DATASET_PATH / name).read_bytes()).hexdigest() == digest, name
for name, digest in package['tokenizer_files'].items():
    assert hashlib.sha256((DATASET_PATH / 'base-tokenizer' / name).read_bytes()).hexdigest() == digest, name
print("ZIP, package, dataset and official tokenizer hashes PASS. No model weights loaded.")
''',
        '''# 3. Recheck counts, source/target provenance, answer boundaries and family isolation.
sys.path.insert(0, str(DATASET_PATH))
from colab_format_helpers import scan, tokenize_turns
from collections import defaultdict
split_rows = {s: [json.loads(line) for line in (DATASET_PATH / (s + '.adjusted.jsonl')).read_text().splitlines() if line.strip()] for s in ['train', 'validation', 'internal-test']}
assert {s: len(v) for s,v in split_rows.items()} == {'train':579, 'validation':65, 'internal-test':66}
all_rows = [r for values in split_rows.values() for r in values]
assert len({r['id'] for r in all_rows}) == 710
families = defaultdict(set)
for split, values in split_rows.items():
    for row in values:
        assert row['quality']['verified'] and row['quality']['oracle']['passed']
        assert row['release_checks']['split_assigned'] == split
        assert row['release_checks']['license_status'] in {'LICENSE_CONFIRMED', 'LICENSE_NOT_REQUIRED'}
        families[row['release_checks']['family_assigned']].add(split)
        if row['category'] == 'computation':
            assert not any(scan(m['content']) for m in row['messages'] if m['role'] in {'system','user'}), row['id']
assert all(len(locations) == 1 for locations in families.values())
manifest = json.loads((DATASET_PATH / 'release-manifest-adjusted.json').read_text())
assert manifest['release_gate'] == 'PASS' and manifest['RUN_TRAIN'] is False
print("Partition, family, license annotations, reference oracles and computation boundary PASS.")
print("These are verified references, not measured Base-model successes.")
''',
        '''# 4. Tokenizer dependency only. Optional install; no training stack installation.
import importlib.metadata as md, subprocess
print('Installed transformers:', md.version('transformers'))
if RUN_INSTALL_TOKENIZER:
    subprocess.run([sys.executable, '-m', 'pip', 'install', 'transformers==5.19.0'], check=True)
    print("If transformers was already imported, restart the session before cell 5.")
else:
    print("Leave this disabled to inspect only. Enable RUN_INSTALL_TOKENIZER in cell 1 if version 5.19.0 is missing.")
''',
        '''# 5. Official local tokenizer, every assistant boundary and assistant-only loss mask.
assert md.version('transformers') == '5.19.0', "Use the audited tokenizer version; cell 4 installs it when enabled"
from transformers import AutoTokenizer
tokenizer = AutoTokenizer.from_pretrained(DATASET_PATH / 'base-tokenizer', local_files_only=True, trust_remote_code=False)
encoded, rejected = tokenize_turns(tokenizer, all_rows, 4096)
assert not rejected, "No silent truncation or dropped examples"
assert len(encoded) == 1010
for turn in encoded:
    boundary = turn['prompt_tokens']
    assert turn['labels'][:boundary] == [-100] * boundary
    assert turn['labels'][boundary:] == turn['input_ids'][boundary:]
    assert len(turn['input_ids']) <= 4096 and turn['assistant_tokens'] > 0
FORMAT_GATE_RECOVERED = True
print('FORMAT_GATE_RECOVERED:', len(all_rows), 'examples;', len(encoded), 'assistant turns; max tokens', max(len(t['input_ids']) for t in encoded))
print('No Base weights, training, checkpoint or generated-code execution occurred.')
''',
        '''# 6. Save the actual Colab format result and stop at this stage.
assert FORMAT_GATE_RECOVERED and not any([RUN_TRAIN, RUN_SMOKE, RUN_BASE_EVALUATION])
result = {'status':'FORMAT_GATE_RECOVERED', 'records':710, 'assistant_turns':1010,
          'zip_sha256':EXPECTED_ZIP_SHA256, 'model':MODEL_NAME, 'revision':MODEL_REVISION,
          'base_evaluated':False, 'smoke_run':False, 'training_run':False,
          'gpu_training_compatibility':'NOT_TESTED', 'production_changed':False}
result_path = Path('/content/colab-format-result.json')
result_path.write_text(json.dumps(result, indent=2))
print(json.dumps(result, indent=2))
print('STOP: next phase needs true Base baseline, actual QLoRA smoke and compatible training environment.')
print('Coding/agentic validation stays Docker-only; never execute generated candidates on the Colab host.')
# No executable training cell is included in this release-correction stage.
'''
    ]
    cells=[{'cell_type':'markdown','metadata':{},'source':['# SovereignAI — repaired dataset / preparation only\n','These cells have been filled for you to run later. No cell execution is authorized now.\n','The previous environment probe is separate; it does not establish QLoRA compatibility.\n','This notebook stops after the format gate. Base evaluation, smoke and training remain separate future gates.\n']}]
    for code in codes:cells.append({'cell_type':'code','metadata':{},'source':code.splitlines(keepends=True),'execution_count':None,'outputs':[]})
    nb={'nbformat':4,'nbformat_minor':5,'metadata':{'kernelspec':{'display_name':'Python 3','name':'python3'},'language_info':{'name':'python'}},'cells':cells}
    save(out/'sovereignai_adjusted_release_colab.ipynb',nb)
    save(out/'colab-cell-sources.json',codes)
    ast.parse('\n'.join(codes))
    assert not any('from_pretrained(MODEL_NAME' in c or 'optimizer.step' in c or 'trainer.train' in c for c in codes)
    save(out/'colab-preparation-self-check.json',{'status':'PASS','notebook_cells':len(cells),'new_execution_count':0,'training_code_present':False,'historical_probe_preceded_current_no_execution_instruction':True,'zip_sha256':zipsha,'cell_code_syntax_checked':True,'package_hashes_verified':True})
    print(json.dumps({'package':str(package),'sha256':zipsha,'notebook':str(out/'sovereignai_adjusted_release_colab.ipynb'),'cells':len(cells),'training':False}))

if __name__=='__main__':
    import sys
    main(Path(sys.argv[1]).resolve())
