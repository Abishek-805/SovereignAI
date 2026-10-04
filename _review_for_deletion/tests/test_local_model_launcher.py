"""Exercise startup arguments without loading or stopping a model."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from router import model_registry


@pytest.mark.parametrize('gemma,reasoner', [(False, False), (True, False), (False, True), (True, True)])
def test_startup_profile_matches_registered_worker(tmp_path, monkeypatch, gemma, reasoner):
    powershell = shutil.which('powershell')
    if not powershell:
        pytest.skip('Windows PowerShell required')
    root = Path(__file__).resolve().parents[1]
    shutil.copyfile(root / 'start-local-model.ps1', tmp_path / 'start-local-model.ps1')
    runtime = tmp_path / 'runtime' / 'llama-b11132' / 'llama-server.exe'
    runtime.parent.mkdir(parents=True)
    runtime.touch()
    models = tmp_path / 'models'
    models.mkdir()
    (models / 'Qwen3-4B-Instruct-2507-Q4_K_M.gguf').touch()
    if gemma:
        (models / 'gemma-4-E2B-it-Q4_K_M.gguf').touch()
    if reasoner:
        (models / 'Qwen3.5-4B-Q4_K_M.gguf').touch()
    (tmp_path / 'benchmarks').mkdir()
    # Shadow process cmdlets: this test can neither start nor stop real workers.
    runner = tmp_path / 'exercise.ps1'
    runner.write_text("""function Get-NetTCPConnection { return $null }
function Start-Process {
    param($FilePath,$ArgumentList,$WorkingDirectory,$WindowStyle,$RedirectStandardOutput,$RedirectStandardError,[switch]$PassThru)
    $ArgumentList | ConvertTo-Json -Compress | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'arguments.json')
    return [pscustomobject]@{Id=123}
}
& (Join-Path $PSScriptRoot 'start-local-model.ps1') -IdleSeconds 45
""", encoding='utf-8')
    subprocess.run([powershell, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(runner)], check=True, capture_output=True)
    args = json.loads((tmp_path / 'arguments.json').read_text(encoding='utf-8-sig'))
    monkeypatch.setattr(model_registry, 'ROOT', tmp_path)
    specs = model_registry.default_specs()
    spec = specs.get('text-light', specs['text'])
    assert args[args.index('--alias') + 1] == spec.alias
    assert args[args.index('-m') + 1].strip('"') == str(models / spec.model_file)
    assert int(args[args.index('-c') + 1]) == spec.context
    assert args[args.index('-np') + 1] == '1'
    assert args[args.index('--sleep-idle-seconds') + 1] == '45'
