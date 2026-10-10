"""Local self-check; does not import models or access dataset contents."""
import ast
from pathlib import Path
from experiments.qlora_ready.colab_readiness_runtime import training_guard

try:
    training_guard(Path('unused'), Path('unused'), False)
except AssertionError as error:
    assert 'Full training disabled' in str(error)
else:
    raise AssertionError('RUN_TRAIN=False did not block training')

root = Path(__file__).parent
for name in ('training_loss.py', 'final_probes.py', 'export_final_probes.py'):
    ast.parse((root / name).read_text())
print('Bounded-probe syntax and full-training guard PASS')
