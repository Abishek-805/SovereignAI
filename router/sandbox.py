"""Fail-closed adapter for a locally verified Docker Linux sandbox."""
from dataclasses import dataclass, field
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import threading
import time
from queue import Empty
from uuid import uuid4

from backend.contracts import WorkbenchError
from backend.settings import ROOT

IMAGE_ID = re.compile(r'^sha256:[a-f0-9]{64}$')
FILE_NAME = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$')
def safe_relative_name(name):
    if not isinstance(name, str) or len(name) > 240 or '\\' in name or ':' in name:
        return False
    parts = name.split('/')
    return all(re.fullmatch(r'[\w.][\w .-]{0,79}', part) and not part.endswith(('.', ' ')) and '..' not in part and
               part.split('.')[0].upper() not in {'CON','PRN','AUX','NUL',*[f'COM{i}' for i in range(10)],*[f'LPT{i}' for i in range(10)]}
               for part in parts)
MAX_OUTPUT = 65536
_READY_CACHE = {}
_READY_LOCK = threading.Lock()
LOCAL_ENGINE = 'npipe:////./pipe/dockerDesktopLinuxEngine'
SANDBOX_POLICY = {
    'backend': 'Docker Linux', 'network': 'none', 'user': '65534:65534',
    'filesystem': 'read-only root; isolated input/output mounts',
    'cpus': 1, 'memory_mb': 512, 'timeout_seconds': 120,
    'privileged': False, 'docker_socket': False,
}


@dataclass
class SandboxResult:
    exit_code: int
    stdout: str
    stderr: str
    executed: bool
    output_files: dict[str, bytes] = field(default_factory=dict)


def _docker_cli():
    candidate = shutil.which('docker')
    if candidate:
        return candidate
    local = Path.home() / 'AppData/Local/Programs/DockerDesktop/resources/bin/docker.exe'
    return str(local) if local.is_file() else None


def _bounded_stream(stream, destination, callback=None, channel='stdout'):
    while block := stream.read1(4096):
        remaining = MAX_OUTPUT - len(destination)
        if remaining > 0:
            destination.extend(block[:remaining])
            if callback: callback(channel,block[:remaining].decode('utf-8','replace'))
    stream.close()


class CodeSandbox:
    def __init__(self, backend_type='none', image_id=None, task_root=None, docker_cli=None):
        self.backend_type = backend_type
        self.image_id = image_id
        self.task_root = Path(task_root or ROOT / 'data' / 'code-tasks').resolve()
        self.docker_cli = docker_cli or _docker_cli()
        self.on_output=None;self.cancel_event=None;self.stdin_queue=None

    @property
    def docker(self):
        return [self.docker_cli, '--host', LOCAL_ENGINE]

    def _ready(self):
        if not IMAGE_ID.fullmatch(self.image_id or ''):
            raise WorkbenchError('sandbox_unavailable', 'A pinned local Docker image ID is required')
        if not self.docker_cli:
            raise WorkbenchError('sandbox_unavailable', 'Docker CLI is missing')
        key=(self.docker_cli,self.image_id)
        with _READY_LOCK:
            if time.monotonic()-_READY_CACHE.get(key,0)<5:return
        try:
            engine = subprocess.run([*self.docker, 'info', '--format', '{{.OSType}}'],
                                    capture_output=True, text=True, timeout=8, check=True)
            if engine.stdout.strip() != 'linux':
                raise WorkbenchError('sandbox_unavailable', 'Docker Linux engine is required')
            subprocess.run([*self.docker, 'image', 'inspect', self.image_id],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=8, check=True)
        except (OSError, subprocess.SubprocessError) as exc:
            raise WorkbenchError('sandbox_unavailable', 'Docker Linux engine or pinned image is unavailable') from exc
        with _READY_LOCK:_READY_CACHE[key]=time.monotonic()

    def execute(self, code: str, timeout: int = 30, input_files: dict[str, bytes] | None = None) -> SandboxResult:
        if self.backend_type == 'none':
            return SandboxResult(-1, '[Execution Disabled]',
                'A validated Linux container runner is not available. Code was not executed.', False)
        if self.backend_type != 'docker':
            raise WorkbenchError('sandbox_error', f'Unsupported sandbox backend: {self.backend_type}')
        if not isinstance(code, str) or len(code.encode('utf-8')) > 100_000 or not 1 <= timeout <= 120:
            raise WorkbenchError('sandbox_input', 'Code or time budget is invalid')
        input_files = input_files or {}
        if not isinstance(input_files, dict) or len(input_files) > 256 or any(not safe_relative_name(name)
                                        or not isinstance(data, bytes)
                                        or len(data) > 1_000_000 for name, data in input_files.items()):
            raise WorkbenchError('sandbox_input', 'Input files must be small and have simple names')
        if sum(map(len, input_files.values())) > 8_000_000:
            raise WorkbenchError('sandbox_input', 'Workspace exceeds the 8 MB execution budget')
        self._ready()
        self.task_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='run-', dir=self.task_root) as directory:
            task = Path(directory)
            inputs, outputs = task / 'input', task / 'output'
            inputs.mkdir(); outputs.mkdir()
            (inputs / 'program.py').write_text(code, encoding='utf-8')
            for name, data in input_files.items():
                if name == 'program.py':
                    raise WorkbenchError('sandbox_input', 'program.py is reserved')
                destination = inputs / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(data)
            container = 'sovereign-code-' + uuid4().hex
            args = [*self.docker, 'run', '-i', '--rm', '--pull=never', '--name', container,
                    f"--network={SANDBOX_POLICY['network']}", '--read-only', '--cap-drop=ALL',
                    '--security-opt=no-new-privileges', '--pids-limit=64',
                    f"--memory={SANDBOX_POLICY['memory_mb']}m", f"--cpus={SANDBOX_POLICY['cpus']}", '--ulimit=fsize=16777216:16777216',
                    f"--user={SANDBOX_POLICY['user']}",
                    '--workdir=/output', '--env=PYTHONDONTWRITEBYTECODE=1', '--env=PYTHONUNBUFFERED=1',
                    '--mount', f'type=bind,src={inputs},dst=/input,readonly',
                    '--mount', f'type=bind,src={outputs},dst=/output',
                    self.image_id, 'python', '-I', '/input/program.py']
            try:
                process = subprocess.Popen(args, stdin=subprocess.PIPE if self.stdin_queue is not None else subprocess.DEVNULL,
                                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            except OSError as exc:
                raise WorkbenchError('sandbox_unavailable', 'Could not start Docker CLI') from exc
            out, err = bytearray(), bytearray()
            readers = [threading.Thread(target=_bounded_stream, args=(pipe, buffer, self.on_output, channel), daemon=True)
                       for pipe, buffer, channel in ((process.stdout, out, 'stdout'), (process.stderr, err, 'stderr'))]
            for reader in readers: reader.start()
            try:
                deadline=time.monotonic()+timeout+5
                while True:
                    if self.cancel_event is not None and self.cancel_event.is_set():raise subprocess.TimeoutExpired(args,timeout)
                    if self.stdin_queue is not None:
                        try:
                            data=self.stdin_queue.get_nowait()
                            process.stdin.write(data.encode('utf-8'));process.stdin.flush()
                        except Empty:pass
                        except (BrokenPipeError,OSError):pass
                    try:
                        exit_code=process.wait(timeout=.1);break
                    except subprocess.TimeoutExpired:
                        if time.monotonic()>deadline:raise
            except subprocess.TimeoutExpired:
                try:
                    subprocess.run([*self.docker, 'rm', '-f', container],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
                except (OSError, subprocess.SubprocessError):
                    pass
                process.kill(); process.wait()
                exit_code = -1
                err.extend(b'\nStopped' if self.cancel_event is not None and self.cancel_event.is_set() else b'\nExecution timed out')
            for reader in readers: reader.join(timeout=2)
            if getattr(process,'stdin',None) is not None:process.stdin.close()
            produced = {}
            for path in outputs.iterdir():
                if not path.is_symlink() and path.is_file() and FILE_NAME.fullmatch(path.name) and path.stat().st_size <= 1_000_000:
                    produced[path.name] = path.read_bytes()
            return SandboxResult(exit_code, out.decode('utf-8', 'replace'),
                                 err.decode('utf-8', 'replace'), True, produced)
