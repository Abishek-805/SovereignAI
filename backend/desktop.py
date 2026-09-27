"""Explicit, fixed-target desktop integrations; never accept shell commands."""
import os
import subprocess
import threading
import time
from pathlib import Path

from backend.contracts import WorkbenchError

_lock = threading.Lock()
_last_launch = 0.0


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
        except OSError as exc:
            raise WorkbenchError('docker_start', 'Docker could not start. Open Docker Desktop to inspect the issue.') from exc
        _last_launch = time.monotonic()
    return {'status': 'starting', 'message': 'Docker is starting. Waiting for the Linux engine…'}
