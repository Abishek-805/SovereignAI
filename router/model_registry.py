import json
import logging
import subprocess
import time
import os
import psutil
from dataclasses import dataclass
from pathlib import Path
from threading import Lock

import httpx
from backend.contracts import WorkbenchError

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / 'runtime' / 'llama-b11132' / 'llama-server.exe'
PID_FILE = ROOT / 'benchmarks' / 'server.pid'

@dataclass(frozen=True)
class ModelSpec:
    capability: str
    alias: str
    model_file: str
    projector_file: str | None = None
    context: int = 24576
    quantization: str = 'Q4_K_M'
    revision: str = ''
    license_reference: str = ''
    provider_repository: str = ''
    modalities: tuple[str, ...] = ('text',)
    runtime_adapter: str = 'llama.cpp'
    observed_gpu_mib: int | None = None
    measured_metrics: tuple[tuple[str, float], ...] = ()
    enabled: bool = True


def default_specs():
    return {
        'text': ModelSpec('text','sovereign-text','Qwen3-4B-Instruct-2507-Q4_K_M.gguf',
                          revision='4edb920b6f14e3b9284d4502a6485103d72cde05',license_reference='docs/model-and-runtime-notices.md',
                          provider_repository='lmstudio-community/Qwen3-4B-Instruct-2507-GGUF',modalities=('text',)),
        'vision': ModelSpec('vision','sovereign-vision','vision-qwen3.5-2b/Qwen3.5-2B-Q4_K_M.gguf',
                            'vision-qwen3.5-2b/mmproj-F16.gguf',context=16384,revision='f6d5376be1edb4d416d56da11e5397a961aca8ae',
                            license_reference='docs/model-and-runtime-notices.md',
                            provider_repository='unsloth/Qwen3.5-2B-GGUF',modalities=('text','image'))
    }

class ModelRegistry:
    def __init__(self, port=8087, specs=None):
        self.port = port
        self._lock = Lock()
        self.current_alias = "sovereign-text"
        self.specs = dict(specs or default_specs())

    def register(self, spec: ModelSpec):
        if spec.capability in self.specs or any(existing.alias == spec.alias for existing in self.specs.values()):
            raise WorkbenchError('model_registry','Model capability or alias already registered')
        self._model_paths(spec)
        self.specs[spec.capability] = spec

    def _model_paths(self, spec):
        base=(ROOT/'models').resolve()
        paths=[]
        for relative in (spec.model_file,spec.projector_file):
            if relative is None: continue
            path=(base/relative).resolve()
            if not path.is_relative_to(base) or path.suffix.lower()!='.gguf':
                raise WorkbenchError('model_registry','Model assets must be GGUF files inside models')
            paths.append(path)
        return paths

    def launch_args(self, capability):
        spec=self.specs.get(capability)
        if spec is None:
            raise WorkbenchError('routing_error',f'Unknown model capability {capability}')
        if not spec.enabled or spec.runtime_adapter!='llama.cpp':
            raise WorkbenchError('model_unavailable','Model entry is disabled or unsupported')
        paths=self._model_paths(spec)
        if not all(path.is_file() for path in paths):
            raise WorkbenchError('model_unavailable',f'{capability.capitalize()} model files missing')
        args=[str(RUNTIME),'-m',str(paths[0])]
        if len(paths)>1: args.extend(['--mmproj',str(paths[1])])
        args.extend(['--alias',spec.alias,'-c',str(spec.context),'-np','1','--n-predict','4096','-b','256','-ub','128','-t','6'])
        if capability=='text':
            args.extend(['-fa','on','-ctk','q8_0','-ctv','q8_0','--fit','on','--fit-target','512'])
        args.extend(['--host','127.0.0.1','--port',str(self.port),'--cors-origins','localhost',
                     '--offline','--sleep-idle-seconds','60','-lv','4'])
        return args
        
    def _is_running(self):
        try:
            r = httpx.get(f'http://127.0.0.1:{self.port}/props', timeout=2, trust_env=False, follow_redirects=False)
            return r.status_code == 200
        except Exception:
            return False

    def _get_current_alias(self):
        try:
            r = httpx.get(f'http://127.0.0.1:{self.port}/v1/models', timeout=2, trust_env=False, follow_redirects=False)
            if r.status_code == 200:
                models = r.json().get('data', [])
                return models[0].get('id') if len(models) == 1 else None
        except Exception:
            pass
        return None

    def _owns_server(self):
        try:
            pid=int(PID_FILE.read_text().strip())
            process=psutil.Process(pid)
            if os.path.normcase(process.exe())!=os.path.normcase(str(RUNTIME)):
                return False
            command=' '.join(process.cmdline())
            if os.path.normcase(str(ROOT/'models')) not in os.path.normcase(command):
                return False
            return any(connection.status==psutil.CONN_LISTEN and connection.laddr.port==self.port
                       for connection in process.net_connections(kind='tcp'))
        except (OSError,ValueError,psutil.Error):
            return False

    def kill_server(self):
        if PID_FILE.exists():
            try:
                pid = int(PID_FILE.read_text().strip())
                process = psutil.Process(pid)
                if (os.path.normcase(process.exe()) != os.path.normcase(str(RUNTIME)) or
                        os.path.normcase(str(ROOT/'models')) not in os.path.normcase(' '.join(process.cmdline()))):
                    raise WorkbenchError('model_ownership', 'Saved model PID is not owned by this workbench')
                process.terminate()
                process.wait(timeout=10)
                PID_FILE.unlink(missing_ok=True)
            except WorkbenchError:
                raise
            except psutil.NoSuchProcess:
                PID_FILE.unlink(missing_ok=True)
            except Exception as e:
                raise WorkbenchError('model_ownership', f'Could not verify or stop saved model PID: {e}') from e

    def acquire_lease(self, model_type: str):
        """Acquire lease for 'text' or 'vision'."""
        with self._lock:
            args=self.launch_args(model_type)
            target_alias=self.specs[model_type].alias
            
            # Check if what we need is already running
            current = self._get_current_alias()
            if current == target_alias:
                if not self._owns_server():
                    raise WorkbenchError('model_ownership','The active model is not owned by this workbench')
                self.current_alias = target_alias
                return

            if (current is not None or self._is_running()) and not self._owns_server():
                raise WorkbenchError('model_ownership','Model port is occupied by a process this workbench does not own')
            
            # Not running or wrong model running
            logger.info(f"Switching model to {target_alias}")
            self.kill_server()
            
            # Start server
            log_dir = ROOT / 'benchmarks'
            try:
                stdout_file = open(log_dir / 'server.stdout.log', 'w')
                stderr_file = open(log_dir / 'server.stderr.log', 'w')
                p = subprocess.Popen(
                    args,
                    cwd=str(RUNTIME.parent),
                    stdout=stdout_file,
                    stderr=stderr_file,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
                PID_FILE.write_text(str(p.pid))
            except Exception as e:
                raise WorkbenchError("model_unavailable", f"Failed to start model server: {e}")
                
            # Wait for readiness
            started = time.time()
            ready = False
            while time.time() - started < 30:
                if self._get_current_alias()==target_alias:
                    ready = True
                    break
                time.sleep(0.5)
                
            if not ready:
                self.kill_server()
                raise WorkbenchError("model_unavailable", f"Server failed to start in 30 seconds")
                
            self.current_alias = target_alias
