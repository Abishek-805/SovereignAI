"""Correct derived labels while preserving the complete Colab export unchanged."""
import hashlib
import json
from pathlib import Path
import zipfile

root = Path('evidence/final-readiness-probes/20261008-162528')
archive = Path('sovereignai-finetuning/oneclick-readiness/sovereignai-final-readiness-probes.zip')
original_hash = hashlib.sha256(archive.read_bytes()).hexdigest()
audit = {
    'status': 'TRAINING_BLOCKED',
    'original_archive_sha256': original_hash,
    'raw_evidence_modified': False,
    'derived_classifications': {
        'sparse': 'NOT_TESTED_HARNESS_API',
        'representative': 'NOT_COMPLETED_ENVIRONMENT_INTERRUPTION',
        'high': 'NOT_TESTED',
        'dense': 'FAIL_CUDA_OOM',
        'long0': 'PASS', 'long1': 'PASS', 'long2': 'NOT_COMPLETED_TIME_BUDGET',
        'accumulation': 'PASS', 'trainer': 'PASS', 'checkpoint_resume': 'PASS',
    },
    'artifact_hashes_verified': 105,
    'reason': 'Queued export used an earlier caption snapshot; correct derived labels without changing raw outcomes.',
}
assert json.loads((root/'recovery-v3/progress.json').read_text())[-1]['exit_code'] == 124
assert 'warmup_ratio' in json.loads((root/'dense-4096-stress-results.json').read_text())['sparse']['error']
report = (root/'final-pretraining-readiness.md').read_text(encoding='utf-8')
for old, new in (
    ('| sparse | FAIL |', '| sparse | NOT_TESTED_HARNESS_API |'),
    ('| representative | RUNNING | varied | — | 0.000 | 0.000 | 0.000 | 61.41 |', '| representative | NOT_COMPLETED_ENVIRONMENT_INTERRUPTION | varied | — | — | — | — | — |'),
    ('| high | NOT_TESTED | varied | — | 0.000 | 0.000 | 0.000 | 0.00 |', '| high | NOT_TESTED | varied | — | — | — | — | — |'),
    ('| long2 | RUNNING |', '| long2 | NOT_COMPLETED_TIME_BUDGET |'),
    ('| 7.034 | 0.00 |', '| 7.034 | — |'),
):
    assert old in report, old
    report = report.replace(old, new)
report += '\n## Export audit correction\n\nOriginal raw outcomes and ZIP are preserved. Sparse failed in the harness before forward execution; representative was interrupted during loading; long2 reached forward but its backward was interrupted at the time budget (exit 124). None is a measured model failure. Missing metrics are unknown. All 105 archived artifact hashes and ZIP CRCs were verified locally.\n\nCompute-only estimate: **2.87 hours per epoch; 5.74 hours for two epochs**, plus unmeasured overhead. This is extrapolated from 64 real microbatches, not a completed epoch. One hour is insufficient for the estimated full run.\n'
Path('final-pretraining-readiness.md').write_text(report, encoding='utf-8')
Path('final-readiness-export-audit.json').write_text(json.dumps(audit, indent=2)+'\n')
audited = archive.with_name('sovereignai-final-readiness-probes-audited.zip')
with zipfile.ZipFile(audited, 'w', zipfile.ZIP_DEFLATED) as z:
    z.write(archive, 'original-colab-export.zip')
    z.write('final-pretraining-readiness.md')
    z.write('final-readiness-export-audit.json')
with zipfile.ZipFile(audited) as z:
    assert z.testzip() is None
assert hashlib.sha256(archive.read_bytes()).hexdigest() == original_hash
print(json.dumps(audit, indent=2))
print('Audited ZIP SHA256:', hashlib.sha256(audited.read_bytes()).hexdigest())
