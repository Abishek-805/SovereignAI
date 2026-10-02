"""Explicit, fixed-target desktop integrations; never accept shell commands."""
import os
import subprocess
import threading
import time
from pathlib import Path
import json
import sys

from backend.contracts import WorkbenchError

_lock = threading.Lock()
_last_launch = 0.0


def verify_docker(data_dir, job):
    """Revalidate a fixed installed image; no user-provided commands or images."""
    from backend.settings import ROOT
    from router.sandbox import _docker_cli, LOCAL_ENGINE
    cli = _docker_cli()
    if not cli:
        raise WorkbenchError('sandbox_unavailable', 'Docker CLI is missing')
    job.progress('Checking Docker Linux engine')
    try:
        inspection = subprocess.run([cli, '--host', LOCAL_ENGINE, 'image', 'inspect',
                                     'sovereign-workbench:latest', '--format', '{{.Id}}'],
                                    capture_output=True, text=True, timeout=10, check=True)
        image = inspection.stdout.strip()
        from router.sandbox import IMAGE_ID
        if not IMAGE_ID.fullmatch(image):
            raise WorkbenchError('sandbox_unavailable', 'The installed sandbox image is invalid')
    except (OSError, subprocess.SubprocessError) as exc:
        raise WorkbenchError('sandbox_unavailable', 'Docker engine or local sandbox image is unavailable. Open Docker Desktop and retry.') from exc
    job.progress('Verifying sandbox isolation and cancellation')
    env = dict(os.environ, SOVEREIGN_DATA_DIR=str(data_dir))
    try:
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/verify_docker_sandbox.py'), image],
                                cwd=ROOT, env=env, capture_output=True, text=True, timeout=180)
    except (OSError, subprocess.SubprocessError) as exc:
        raise WorkbenchError('sandbox_verification', 'Sandbox verification could not finish. Code execution remains disabled; retry setup after checking Docker Desktop.') from exc
    if result.returncode:
        raise WorkbenchError('sandbox_verification', 'Sandbox isolation checks failed. Code execution remains disabled.')
    try:
        checks = json.loads(result.stdout)
    except (ValueError, TypeError) as exc:
        raise WorkbenchError('sandbox_verification', 'Sandbox verification returned invalid results') from exc
    if not isinstance(checks, dict) or not checks or not all(value is True for value in checks.values()):
        raise WorkbenchError('sandbox_verification', 'Sandbox isolation checks did not pass')
    return {'status': 'verified', 'checks': checks, 'image_id': image}


def start_docker():
    global _last_launch
    if os.name != 'nt':
        raise WorkbenchError('docker_start', 'Start Docker using your operating system, then refresh.')
    candidates = [Path.home() / 'AppData/Local/Programs/DockerDesktop/Docker Desktop.exe',
                  Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / 'Docker/Docker/Docker Desktop.exe']
    executable = next((path for path in candidates if path.is_file()), None)
    if executable is None:
        raise WorkbenchError('docker_start', 'Docker Desktop is not installed in a supported location.')
    with _lock:
        if _last_launch and time.monotonic() - _last_launch < 90:
            return {'status': 'starting', 'message': 'Docker is starting. Waiting for the Linux engine…'}
        try:
            startup = subprocess.STARTUPINFO()
            startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startup.wShowWindow = 0
            subprocess.Popen([str(executable)], shell=False, startupinfo=startup,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            # Desktop's UI processes can remain present while its engine is
            # stopped. New Desktop CLIs start that engine explicitly; older
            # installations still have the executable launch above as fallback.
            from router.sandbox import _docker_cli
            cli = _docker_cli()
            if cli:
                subprocess.Popen([cli, 'desktop', 'start', '--detach'], shell=False,
                                 startupinfo=startup, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
        except OSError as exc:
            raise WorkbenchError('docker_start', 'Docker could not start. Open Docker Desktop to inspect the issue.') from exc
        _last_launch = time.monotonic()
    return {'status': 'starting', 'message': 'Docker is starting. Waiting for the Linux engine…'}
