"""Check packaged readiness and observed Colab cells without importing a GPU stack."""
import ast
import hashlib
import importlib.util
import json
import sys
import zipfile
from pathlib import Path

root = Path(sys.argv[1]).resolve()
read = lambda p: json.loads(p.read_text(encoding='utf-8'))
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
sources = read(root / 'colab-cell-sources.json')
observed = read(root / 'colab-observed-cell-sources.json')
assert len(sources) == len(observed) == 9
for i, (expected, actual) in enumerate(zip(sources, observed), 7):
    assert ast.dump(ast.parse(expected)) == ast.dump(ast.parse(actual.replace('\u00a0', ' '))), i
dom = (root / 'colab-filled-dom.txt').read_text(encoding='utf-8')
assert dom.count('generic: "[ ]"') == 15
assert dom.count('generic: "[1]"') == 1
assert 'All changes saved' in dom
manifest = read(root / 'readiness-manifest.json')
for name, expected in manifest['files'].items():
    assert sha(root / name) == expected, name
package = root / 'colab-package'
with zipfile.ZipFile(root / 'sovereignai-pretraining-readiness-colab.zip') as archive:
    assert archive.testzip() is None
    for name, expected in read(package / 'package-manifest.json')['files'].items():
        assert hashlib.sha256(archive.read(name)).hexdigest() == expected
spec = importlib.util.spec_from_file_location('readiness', package / 'readiness.py')
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)
splits = runtime.integrity(package)
assert {s: len(rows) for s, rows in splits.items()} == {'train': 579, 'validation': 65, 'internal-test': 66}
checks = root / 'guard-self-checks'
checks.mkdir(exist_ok=True)
def rejects(call, message):
    try:
        call()
    except AssertionError as error:
        assert message in str(error), str(error)
    else:
        raise AssertionError('Guard accepted missing or disabled prerequisites')
rejects(lambda: runtime.training_guard(package, checks, False), 'RUN_TRAIN=False')
rejects(lambda: runtime.require_baseline(package, checks), 'BASELINE_BLOCKED')
(checks / 'base-predictions.json').write_text('[]', encoding='utf-8')
(checks / 'independent-base-evaluation.json').write_text(json.dumps({
    'model': runtime.MODEL, 'revision': runtime.REVISION, 'adapter': None,
    'prediction_sha256': sha(checks / 'base-predictions.json'),
    'independently_verified': True, 'results': []}), encoding='utf-8')
rejects(lambda: runtime.require_baseline(package, checks), '')
assert 'torch' not in sys.modules
result = {'status': 'PASS', 'colab_cells_ast_match': 9, 'unexecuted_cells': 15,
          'prior_environment_probe_executions': 1, 'all_changes_saved': True,
          'package_manifest_hashes': 'PASS', 'dataset_integrity': 'PASS',
          'disabled_training_guard': 'PASS', 'missing_baseline_guard': 'PASS',
          'incomplete_baseline_guard': 'PASS', 'new_gpu_executions': 0,
          'overall_readiness': 'TRAINING_BLOCKED', 'RUN_TRAIN': False}
(root / 'completion-self-check.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
files = {p.name: sha(p) for p in root.iterdir() if p.is_file() and p.name != 'completion-manifest.json'}
(root / 'completion-manifest.json').write_text(json.dumps({'status': 'TRAINING_BLOCKED', 'files': files}, indent=2), encoding='utf-8')
print(json.dumps(result, indent=2))
