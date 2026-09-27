"""Inventory the supported local runtime without copying user documents."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'offline-manifest.json'
CODE_DIRS = ('backend', 'rag', 'router', 'workflows', 'scripts')
ROOT_FILES = ('README.md', 'requirements.txt',
              'start-workbench.ps1', 'stop-workbench.ps1', 'start-sovereign.ps1', 'stop-sovereign.ps1', 'licenses/llama.cpp-LICENSE',
              'docs/model-and-runtime-notices.md', 'offline/Dockerfile.workbench',
              'start-local-model.ps1', 'stop-local-model.ps1', 'Start SovereignAI.bat', 'Stop SovereignAI.bat',
              'docs/WINDOWS_SHORTCUTS.md')


def included_files():
    for name in ROOT_FILES:
        path = ROOT / name
        if not path.is_file():
            raise FileNotFoundError(path)
        yield path
    for directory in CODE_DIRS:
        for path in (ROOT / directory).rglob('*'):
            if path.is_file() and '__pycache__' not in path.parts and path.suffix not in {'.pyc', '.log'}:
                yield path
    # Ship the built llama UI and its attribution, not npm's development tree.
    frontend = ROOT / 'frontend'
    for name in ('llama-ui/LICENSE',):
        path=frontend/name
        if path.is_file(): yield path
    for path in (frontend/'llama-ui'/'dist').rglob('*'):
        if path.is_file(): yield path
    evaluation=ROOT/'benchmarks'
    yield evaluation/'run_heldout_eval.py'
    for path in (evaluation/'heldout-fixtures').glob('*.txt'):
        yield path
    for directory in ('runtime/llama-b11132', 'models/bge-small-en-v1.5'):
        for path in (ROOT / directory).rglob('*'):
            if path.is_file() and '.cache' not in path.parts:
                yield path
    for path in (ROOT / 'models').glob('*.gguf'):
        yield path
    vision = ROOT / 'models' / 'vision-qwen3.5-2b'
    for name in ('Qwen3.5-2B-Q4_K_M.gguf', 'mmproj-F16.gguf'):
        path = vision / name
        if path.is_file():
            yield path


def main():
    entries = []
    for path in sorted(set(included_files())):
        digest = hashlib.sha256()
        with path.open('rb') as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(block)
        entries.append({'path': path.relative_to(ROOT).as_posix(),
                        'size': path.stat().st_size, 'sha256': digest.hexdigest()})
    MANIFEST.write_text(json.dumps({'schema': 1, 'files': entries}, indent=2) + '\n', encoding='utf-8')
    print(f'Wrote {MANIFEST} with {len(entries)} files')


if __name__ == '__main__':
    main()
