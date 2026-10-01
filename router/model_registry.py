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
_RUNTIME_LOCK = Lock()

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
    model_id: str = ''
    display_name: str = ''
    capabilities: tuple[str, ...] = ()
    observed_memory_mib: int | None = None
    resource_context: int | None = None
    kv_configuration: str | None = None
    memory_reserve_mib: int = 256
    gpu_reserve_mib: int = 256
    license_id: str | None = None
    license_reviewed: bool = False
    resource_kv_configuration: str | None = None
    license_source: str | None = None
    license_reviewed_at: str | None = None

    @property
    def identifier(self):
        return self.model_id or self.alias

    @property
    def supported_capabilities(self):
        return self.capabilities or (self.capability,)


def default_specs():
    specs = {
        'text': ModelSpec('text','sovereign-text','Qwen3-4B-Instruct-2507-Q4_K_M.gguf',
                          revision='4edb920b6f14e3b9284d4502a6485103d72cde05',license_reference='docs/model-and-runtime-notices.md',
                          provider_repository='lmstudio-community/Qwen3-4B-Instruct-2507-GGUF',modalities=('text',),
                          display_name='Qwen3 4B Instruct 2507',capabilities=('text','code','calculation'),kv_configuration='q8_0/q8_0',
                          license_id='Apache-2.0',license_reviewed=True,
                          license_source='https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507',license_reviewed_at='2026-09-28'),
        'vision': ModelSpec('vision','sovereign-vision','vision-qwen3.5-2b/Qwen3.5-2B-Q4_K_M.gguf',
                            'vision-qwen3.5-2b/mmproj-F16.gguf',context=16384,revision='f6d5376be1edb4d416d56da11e5397a961aca8ae',
                            license_reference='docs/model-and-runtime-notices.md',
                            provider_repository='unsloth/Qwen3.5-2B-GGUF',modalities=('text','image'),
                            display_name='Qwen3.5 2B Vision',capabilities=('vision',),kv_configuration='f16/f16',
                            license_id='Apache-2.0',license_reviewed=True,
                            license_source='https://huggingface.co/Qwen/Qwen3.5-2B',license_reviewed_at='2026-09-28')
    }
    if (ROOT/'models'/'gemma-4-E2B-it-Q4_K_M.gguf').is_file():
        specs['text']=ModelSpec('text','sovereign-text','gemma-4-E2B-it-Q4_K_M.gguf',context=16384,
            revision='0314792d7f1f7e229411f620751375812bb9faf2',
            provider_repository='unsloth/gemma-4-E2B-it-GGUF',display_name='Gemma 4 E2B',
            capabilities=('text','code','calculation'),kv_configuration='q8_0/q8_0',
            license_reference='docs/model-and-runtime-notices.md',license_id='Apache-2.0',license_reviewed=True,
            license_source='https://ai.google.dev/gemma/docs/core/model_card_4',license_reviewed_at='2026-10-01')
    if (ROOT/'models'/'qwen2.5-coder-3b-instruct-q4_k_m.gguf').is_file():
        from dataclasses import replace
        specs['text']=replace(specs['text'],capabilities=('text','calculation'))
        specs['code']=ModelSpec('code','sovereign-code','qwen2.5-coder-3b-instruct-q4_k_m.gguf',context=16384,
            revision='f74adce6aa16316c625447af059dbebe4983757c',
            provider_repository='Qwen/Qwen2.5-Coder-3B-Instruct-GGUF',display_name='Qwen2.5 Coder 3B',
            capabilities=('code',),kv_configuration='q8_0/q8_0',
            license_reference='docs/model-and-runtime-notices.md',license_id='qwen-research',license_reviewed=True,
            license_source='https://huggingface.co/Qwen/Qwen2.5-Coder-3B-Instruct',license_reviewed_at='2026-10-01')
    if (ROOT/'models'/'Qwen3.5-4B-Q4_K_M.gguf').is_file():
        from dataclasses import replace
        specs['text-light']=replace(specs['text'],alias='sovereign-text-light')
        specs['text']=ModelSpec('text','sovereign-text','Qwen3.5-4B-Q4_K_M.gguf',context=16384,
            revision='e87f176479d0855a907a41277aca2f8ee7a09523',
            provider_repository='unsloth/Qwen3.5-4B-GGUF',display_name='Qwen3.5 4B',
            capabilities=('text','calculation'),kv_configuration='q8_0/q8_0',
            license_reference='docs/model-and-runtime-notices.md',license_id='Apache-2.0',license_reviewed=True,
            license_source='https://huggingface.co/Qwen/Qwen3.5-4B',license_reviewed_at='2026-10-01')
    return specs

class ModelRegistry:
    def __init__(self, port=8087, specs=None):
        self.port = port
        self._lock = _RUNTIME_LOCK
        self.current_alias = "sovereign-text"
        self.runtime_state = None
        self.specs = dict(default_specs() if specs is None else specs)

    def register(self, spec: ModelSpec):
        if any(existing.alias == spec.alias or existing.identifier == spec.identifier for existing in self.specs.values()):
            raise WorkbenchError('model_registry','Model identity or alias already registered')
        self._model_paths(spec)
        if not spec.license_reviewed or not spec.license_id or not spec.license_reference:
            raise WorkbenchError('model_registry','Review and record this model license before production registration')
        key=spec.capability if spec.capability not in self.specs else spec.identifier
        self.specs[key] = spec

    @property
    def models(self):
        """Model-centric identities; legacy registry keys remain launch handles only."""
        return {spec.identifier:spec for spec in self.specs.values()}

    def installed(self, spec):
        return all(path.is_file() for path in self._model_paths(spec))

    def runtime_available(self, spec):
        return spec.runtime_adapter=='llama.cpp' and RUNTIME.is_file()

    def records(self):
        return [{'model_id':spec.identifier,'registry_key':key,'display_name':spec.display_name or spec.alias,
                 'capabilities':list(spec.supported_capabilities),'modalities':list(spec.modalities),
                 'runtime':spec.runtime_adapter,'installed':self.installed(spec),'enabled':spec.enabled,
                 'context_limit':spec.context,'observed_gpu_mib':spec.observed_gpu_mib,
                 'quantization':spec.quantization,'runtime_alias':spec.alias,
                 'observed_memory_mib':spec.observed_memory_mib,'resource_context':spec.resource_context,
                 'kv_configuration':spec.kv_configuration,'resource_kv_configuration':spec.resource_kv_configuration,
                 'benchmark_metrics':dict(spec.measured_metrics),
                 'license_id':spec.license_id,'license_reviewed':spec.license_reviewed,
                 'license_source':spec.license_source,'license_reviewed_at':spec.license_reviewed_at,
                 'license_reference':spec.license_reference,'revision':spec.revision,'provider_repository':spec.provider_repository}
                for key,spec in self.specs.items()]

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
        if not spec.license_reviewed or not spec.license_id or not spec.license_reference:
            raise WorkbenchError('model_registry','Review and record this model license before loading it')
        paths=self._model_paths(spec)
        if not all(path.is_file() for path in paths):
            raise WorkbenchError('model_unavailable',f'{capability.capitalize()} model files missing')
        args=[str(RUNTIME),'-m',str(paths[0])]
        if len(paths)>1: args.extend(['--mmproj',str(paths[1])])
        args.extend(['--alias',spec.alias,'-c',str(spec.context),'-np','1','--n-predict','8192','-b','256','-ub','128','-t','6'])
        if spec.projector_file is None and 'text' in spec.modalities:
            kv=(spec.kv_configuration or 'q8_0/q8_0').split('/')
            if len(kv)!=2 or any(value not in {'f16','q8_0','q4_0'} for value in kv):
                raise WorkbenchError('model_registry','Unsupported bounded KV configuration')
            # Keep the runtime's documented 1 GiB margin for the desktop and
            # transient allocations. A 512 MiB fit can leave a warm model below
            # the admission reserve once the rest of the application is active.
            args.extend(['-fa','on','-ctk',kv[0],'-ctv',kv[1],'--fit','on','--fit-target','1024'])
        else:
            kv=(spec.kv_configuration or 'f16/f16').split('/')
            if len(kv)!=2 or any(value not in {'f16','q8_0','q4_0'} for value in kv):
                raise WorkbenchError('model_registry','Unsupported bounded KV configuration')
            args.extend(['-ctk',kv[0],'-ctv',kv[1],'--fit','on','--fit-target','1024'])
        args.extend(['--host','127.0.0.1','--port',str(self.port),'--cors-origins','localhost',
                     '--offline','--sleep-idle-seconds','600','-lv','4'])
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

    def _runtime_profile_matches(self, args):
        """An alias is not proof of the actual model, context or KV profile."""
        names={'-m':'model','--model':'model','--mmproj':'projector','--alias':'alias',
               '-c':'context','--ctx-size':'context','-np':'slots','--parallel':'slots',
               '-ctk':'key_cache','--cache-type-k':'key_cache',
               '-ctv':'value_cache','--cache-type-v':'value_cache',
               '--fit':'fit','-fit':'fit','--fit-target':'fit_target','-fitt':'fit_target',
               '--sleep-idle-seconds':'sleep_idle'}
        def profile(command):
            values={};index=1
            while index<len(command):
                argument=command[index];flag,separator,inline=argument.partition('=')
                name=names.get(flag)
                if name:
                    if name in values:return None # Repeated aliases/options are ambiguous.
                    if separator:value=inline
                    else:
                        index+=1
                        if index>=len(command):return None
                        value=command[index]
                    values[name]=os.path.normcase(os.path.abspath(value)) if name in {'model','projector'} else value
                index+=1
            if not all(name in values for name in ('key_cache','value_cache')):return None
            return values
        try:
            process=psutil.Process(int(PID_FILE.read_text().strip()))
            expected=profile(args);actual=profile(process.cmdline())
            if expected is None or actual!=expected:return False
            response=httpx.get(f'http://127.0.0.1:{self.port}/props',timeout=2,trust_env=False,follow_redirects=False)
            if response.status_code!=200:return False
            context=response.json().get('default_generation_settings',{}).get('n_ctx')
            return not isinstance(context,bool) and isinstance(context,int) and context==int(expected['context'])
        except (OSError,ValueError,KeyError,TypeError,AttributeError,psutil.Error,httpx.HTTPError):
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
                if self._runtime_profile_matches(args):
                    self.current_alias = target_alias
                    self.runtime_state = 'Ready'
                    return {'model_load_time':None,'switch_required':False,'current_residency':current,'selected_model':target_alias,'state':'Ready','available_context':self.specs[model_type].context}

            if (current is not None or self._is_running()) and not self._owns_server():
                raise WorkbenchError('model_ownership','Model port is occupied by a process this workbench does not own')
            
            # Not running or wrong model running
            logger.info(f"Switching model to {target_alias}")
            self.runtime_state = 'Unloading'
            self.kill_server()
            self.runtime_state = 'Loading'
            load_started=time.perf_counter()
            
            # Start server
            log_dir = ROOT / 'benchmarks'
            try:
                log_dir.mkdir(parents=True,exist_ok=True)
                with open(log_dir / 'server.stdout.log', 'w') as stdout_file, open(log_dir / 'server.stderr.log', 'w') as stderr_file:
                    p = subprocess.Popen(
                        args,
                        cwd=str(RUNTIME.parent),
                        stdout=stdout_file,
                        stderr=stderr_file,
                        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)
                    )
                PID_FILE.write_text(str(p.pid))
            except Exception as e:
                self.runtime_state = 'Error'
                raise WorkbenchError("model_unavailable", f"Failed to start model server: {e}")
                
            # Wait for readiness
            started = time.time()
            ready = False
            while time.time() - started < 30:
                if self._get_current_alias()==target_alias and self._owns_server() and self._runtime_profile_matches(args):
                    ready = True
                    break
                time.sleep(0.5)
                
            if not ready:
                self.runtime_state = 'Error'
                self.kill_server()
                raise WorkbenchError("model_unavailable", f"Server failed to start in 30 seconds")
                
            self.current_alias = target_alias
            self.runtime_state = 'Ready'
            return {'model_load_time':time.perf_counter()-load_started,'switch_required':True,'current_residency':current,'selected_model':target_alias,'state':'Ready','available_context':self.specs[model_type].context}
