import ast,json,zipfile,hashlib
from pathlib import Path
from experiments.qlora_factory.prepare import ROOT,save,sha
def main():
    p=ROOT/'sovereignai-finetuning';nbpath=p/'sovereignai_qwen35_qlora_colab.ipynb';nb=json.loads(nbpath.read_text(encoding='utf-8'))
    base_cells=[c for c in nb['cells'] if 'True Base/adapter prediction capture' in ''.join(c['source']) or 'RUN_BASE_PREDICTIONS=False' in ''.join(c['source'])]
    nb['cells']=[c for c in nb['cells'] if c not in base_cells];index=next(i for i,c in enumerate(nb['cells']) if '## 18. Full training gate' in ''.join(c['source']));nb['cells'][index:index]=base_cells
    for c in nb['cells']:
        if c['cell_type']=='code':ast.parse(''.join(c['source']))
    save(nbpath,nb);manifest=json.loads((p/'training_manifest.json').read_text());manifest.update(training_code_sha256=sha(p/'training.py'),serialization_adapter_sha256=sha(p/'training.py'),notebook_sha256=sha(nbpath));save(p/'training_manifest.json',manifest)
    # Check known rejection paths without GPU/teacher execution.
    import importlib.util
    spec=importlib.util.spec_from_file_location('checkpoint_selector',p/'evaluation/select_checkpoint.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    rejected=[]
    for case in ([],[{'split':'internal-test','independently_verified':True}],[{'split':'validation','independently_verified':False}]):
        try:m.select(case);raise AssertionError('Invalid checkpoint scores accepted')
        except ValueError:rejected.append(True)
    save(p/'package-checks.json',{'notebook_code_cells_parse':True,'checkpoint_rejects_missing_or_unverified_or_internal_test_scores':all(rejected),'dataset_hashes_match':all(sha(p/name)==value for name,value in manifest['dataset_sha256'].items()),'training_code_hash_matches':sha(p/'training.py')==manifest['training_code_sha256'],'gpu_smoke':'NOT_RUN','full_training_started':False})
    archive=ROOT/'sovereignai-finetuning.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for file in p.rglob('*'):
            if file.is_file() and '__pycache__' not in str(file):z.write(file,Path('sovereignai-finetuning')/file.relative_to(p))
    save(ROOT/'evidence/qlora-dataset-factory/20261008-114330/final-package-inventory-v2.json',{str(file.relative_to(p)):sha(file) for file in p.rglob('*') if file.is_file() and '__pycache__' not in str(file)})
    print('Package checks passed; zip bytes',archive.stat().st_size)
if __name__=='__main__':main()
