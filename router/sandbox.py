"""Fail-closed adapter for a locally verified Docker Linux sandbox."""
from dataclasses import dataclass, field
from pathlib import Path
import base64
import hashlib
import json
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
from router.telemetry import measured_validation

IMAGE_ID = re.compile(r'^sha256:[a-f0-9]{64}$')
FILE_NAME = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$')

def sensitive_project_path(name: str) -> bool:
    """Exclude project-held credentials and VCS internals from model/sandbox snapshots."""
    parts = name.replace('\\', '/').casefold().split('/')
    basename = parts[-1]
    return (any(part in {'.git', '.ssh', '.aws', '.azure', 'gcloud'} for part in parts) or
            basename == '.env' or basename.startswith('.env.') or
            basename in {'id_rsa', 'id_ed25519', 'credentials', 'credentials.json'} or
            basename.startswith('credentials.') or basename.endswith(('.pem', '.key', '.p12', '.pfx')))
def safe_relative_name(name):
    if not isinstance(name, str) or len(name) > 240 or '\\' in name or ':' in name:
        return False
    parts = name.split('/')
    return all(re.fullmatch(r'[\w.][\w .-]{0,79}', part) and not part.endswith(('.', ' ')) and '..' not in part and
               part.split('.')[0].upper() not in {'CON','PRN','AUX','NUL',*[f'COM{i}' for i in range(10)],*[f'LPT{i}' for i in range(10)]}
               for part in parts)
MAX_OUTPUT = 65536
# Project imports and execution snapshots share the same finite byte limits.
# Assets are mounted/copied as bytes; they do not consume the model context.
MAX_INPUT_FILES = 256
MAX_INPUT_FILE_BYTES = 20 * 1024 * 1024
MAX_INPUT_BYTES = 256 * 1024 * 1024
MAX_CONTAINER_FILE_BYTES = 32 * 1024 * 1024
MAX_OUTPUT_VOLUME_BYTES = 384 * 1024 * 1024
COLLECT_OUTPUT_SCRIPT = '''import os,re,json,base64
valid=re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$')
files={}
for index,entry in enumerate(os.scandir('/output')):
    if index>=4096: raise RuntimeError('Too many output entries')
    if not valid.fullmatch(entry.name) or not entry.is_file(follow_symlinks=False): continue
    if entry.stat(follow_symlinks=False).st_size>1000000: continue
    with open(entry.path,'rb') as stream: data=stream.read(1000001)
    if len(data)>1000000: continue
    files[entry.name]=base64.b64encode(data).decode('ascii')
    if len(files)>8: raise RuntimeError('Too many collected output files')
print(json.dumps(files))
'''
_READY_CACHE = {}
_READY_LOCK = threading.Lock()
LOCAL_ENGINE = 'npipe:////./pipe/dockerDesktopLinuxEngine'
SANDBOX_POLICY = {
    'backend': 'Docker Linux', 'network': 'none', 'user': '65534:65534',
    'filesystem': 'read-only root; isolated input/output mounts',
    'cpus': 1, 'memory_mb': 512, 'timeout_seconds': 120,
    'privileged': False, 'docker_socket': False,
}
SANDBOX_VERIFICATION_VERSION = 2
SANDBOX_VERIFICATION_MAX_AGE = 24 * 60 * 60  # Reprobe each day; desktop/daemon updates can change enforcement.

def sandbox_policy_fingerprint() -> str:
    """Bind a verification record to the actual runner, image recipe, and probe code."""
    digest = hashlib.sha256()
    for path in (Path(__file__), ROOT / 'offline' / 'Dockerfile.workbench',
                 ROOT / 'scripts' / 'verify_docker_sandbox.py'):
        digest.update(path.read_bytes())
    return digest.hexdigest()


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

    @measured_validation
    def execute(self, code: str, timeout: int = 30, input_files: dict[str, bytes] | None = None) -> SandboxResult:
        if self.backend_type == 'none':
            return SandboxResult(-1, '[Execution Disabled]',
                'A validated Linux container runner is not available. Code was not executed.', False)
        if self.backend_type != 'docker':
            raise WorkbenchError('sandbox_error', f'Unsupported sandbox backend: {self.backend_type}')
        if not isinstance(code, str) or len(code.encode('utf-8')) > 100_000 or not 1 <= timeout <= 120:
            raise WorkbenchError('sandbox_input', 'Code or time budget is invalid')
        if input_files is None:input_files={}
        if not isinstance(input_files, dict):
            raise WorkbenchError('sandbox_input', 'Execution input files must be a file mapping')
        input_files={name:data for name,data in input_files.items()
                     if not isinstance(name,str) or not sensitive_project_path(name)}
        if len(input_files)>MAX_INPUT_FILES:
            raise WorkbenchError('sandbox_input', 'Execution supports up to 256 project files')
        if any(not safe_relative_name(name) or name=='program.py' for name in input_files):
            raise WorkbenchError('sandbox_input', 'Input names must be safe relative project paths; program.py is reserved')
        if any(not isinstance(data,bytes) for data in input_files.values()):
            raise WorkbenchError('sandbox_input', 'Execution input files must contain bytes')
        if any(len(data)>MAX_INPUT_FILE_BYTES for data in input_files.values()):
            raise WorkbenchError('sandbox_input', 'Execution input files must be at most 20 MiB each')
        if sum(map(len,input_files.values()))>MAX_INPUT_BYTES:
            raise WorkbenchError('sandbox_input', 'Workspace exceeds the 256 MiB execution budget')
        self._ready()
        self.task_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='run-', dir=self.task_root) as directory:
            task = Path(directory)
            inputs = task / 'input'
            inputs.mkdir()
            (inputs / 'program.py').write_text(code, encoding='utf-8')
            for name, data in input_files.items():
                destination = inputs / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(data)
            container = 'sovereign-code-' + uuid4().hex
            args = [*self.docker, 'run', '-d', '--rm', '--pull=never', '--name', container,
                    f"--network={SANDBOX_POLICY['network']}", '--read-only', '--cap-drop=ALL',
                    '--security-opt=no-new-privileges', '--pids-limit=64',
                    f"--memory={SANDBOX_POLICY['memory_mb']}m",
                    f"--memory-swap={SANDBOX_POLICY['memory_mb']}m", f"--cpus={SANDBOX_POLICY['cpus']}",
                    f'--ulimit=fsize={MAX_CONTAINER_FILE_BYTES}:{MAX_CONTAINER_FILE_BYTES}',
                    f"--user={SANDBOX_POLICY['user']}",
                    '--workdir=/output', '--env=PYTHONDONTWRITEBYTECODE=1', '--env=PYTHONUNBUFFERED=1',
                    '--mount', f'type=bind,src={inputs},dst=/input,readonly',
                    '--tmpfs', f'/output:rw,nosuid,nodev,size={MAX_OUTPUT_VOLUME_BYTES},mode=1777',
                    self.image_id, 'sleep', '300']
            try:
                subprocess.run(args, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=20, check=True)
                execution_args = [*self.docker, 'exec', '-i', container, 'python', '-I', '/input/program.py']
                process = subprocess.Popen(execution_args, stdin=subprocess.PIPE if self.stdin_queue is not None else subprocess.DEVNULL,
                                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            except (OSError, subprocess.SubprocessError) as exc:
                try: subprocess.run([*self.docker, 'rm', '-f', container], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=8)
                except (OSError, subprocess.SubprocessError): pass
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
            try:
                if exit_code >= 0:
                    collected = subprocess.run([*self.docker, 'exec', container, 'python', '-I', '-c', COLLECT_OUTPUT_SCRIPT],
                                               capture_output=True, timeout=45, check=True)
                    payload = json.loads(collected.stdout)
                    if not isinstance(payload, dict) or len(payload)>8:
                        raise ValueError('Invalid output manifest')
                    for name, encoded in payload.items():
                        if not FILE_NAME.fullmatch(name): raise ValueError('Invalid output filename')
                        data=base64.b64decode(encoded, validate=True)
                        if len(data)>1_000_000: raise ValueError('Oversized output')
                        produced[name]=data
            except (OSError, subprocess.SubprocessError, ValueError, TypeError) as exc:
                raise WorkbenchError('sandbox_output', 'Could not collect bounded container output') from exc
            finally:
                try:
                    subprocess.run([*self.docker, 'rm', '-f', container],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=8)
                except (OSError, subprocess.SubprocessError):
                    pass
            return SandboxResult(exit_code, out.decode('utf-8', 'replace'),
                                 err.decode('utf-8', 'replace'), True, produced)
