"""Read-only prerequisites for the full-app OS-blocked-outbound release gate.

This check never changes firewall state and is not offline proof.
"""
from __future__ import annotations

import ctypes
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'benchmarks' / 'gate-a-preflight.json'


def check():
    elevated = bool(ctypes.windll.shell32.IsUserAnAdmin()) if os.name == 'nt' else os.geteuid() == 0
    docker = shutil.which('docker')
    docker_engine = False
    docker_detail = 'docker command not installed'
    if docker:
        try:
            run = subprocess.run([docker, 'info', '--format', '{{.OSType}}'],
                                 capture_output=True, text=True, timeout=12, check=False)
            docker_engine = run.returncode == 0 and run.stdout.strip() == 'linux'
            docker_detail = run.stdout.strip() or run.stderr.strip()[:300]
        except (OSError, subprocess.TimeoutExpired) as exc:
            docker_detail = str(exc)[:300]
    assets = {
        'text_model': ROOT / 'models' / 'Qwen3-4B-Instruct-2507-Q4_K_M.gguf',
        'vision_model': ROOT / 'models' / 'vision-qwen3.5-2b' / 'Qwen3.5-2B-Q4_K_M.gguf',
        'vision_projector': ROOT / 'models' / 'vision-qwen3.5-2b' / 'mmproj-F16.gguf',
        'model_runtime': ROOT / 'runtime' / 'llama-b11132' / 'llama-server.exe',
        'built_ui': ROOT / 'frontend' / 'llama-ui' / 'dist' / 'index.html',
    }
    listeners = []
    for connection in psutil.net_connections(kind='tcp'):
        if connection.status == psutil.CONN_LISTEN and connection.laddr.port in (8087, 8088):
            listeners.append({'port': connection.laddr.port, 'pid': connection.pid})
    blockers = []
    if not elevated:
        blockers.append('No elevated token for an OS-enforced, logged outbound block')
    if not docker_engine:
        blockers.append('Docker Linux engine unavailable for the supported coding task')
    for name, path in assets.items():
        if not path.is_file():
            blockers.append(f'Missing {name}: {path}')
    if listeners:
        blockers.append('Required local ports are already occupied; inspect ownership before launch')
    return {
        'gate': 'A', 'checked_at_unix': time.time(), 'state': 'BLOCKED' if blockers else 'READY_FOR_TEST',
        'this_is_not_offline_proof': True, 'elevated': elevated,
        'docker_linux_engine': docker_engine, 'docker_detail': docker_detail,
        'assets_present': {name: path.is_file() for name, path in assets.items()},
        'local_listeners': listeners, 'blockers': blockers,
    }


def main():
    result = check()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(f"Gate A preflight: {result['state']}; {len(result['blockers'])} blocker(s). Evidence: {OUTPUT}")
    for blocker in result['blockers']:
        print(f'- {blocker}')
    return 0 if result['state'] == 'READY_FOR_TEST' else 2


if __name__ == '__main__':
    raise SystemExit(main())
