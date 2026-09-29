"""Observed resource sampling and conservative admission; never guessed capacity."""
from dataclasses import asdict, dataclass
import shutil
import subprocess
import time
from threading import Lock
import math
import psutil


@dataclass(frozen=True)
class ResourceSnapshot:
    sampled_at: float | None = None
    available_memory_mib: float | None = None
    gpu_free_mib: float | None = None
    gpu_total_mib: float | None = None
    gpu_device: str | None = None
    source: str | None = None
    errors: tuple[str, ...] = ()

    def __post_init__(self):
        errors=list(self.errors)
        for name in ('sampled_at','available_memory_mib','gpu_free_mib','gpu_total_mib'):
            value=getattr(self,name)
            if value is not None and (isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<0):
                object.__setattr__(self,name,None)
                errors.append('Invalid resource observation: '+name)
        if self.gpu_free_mib is not None and self.gpu_total_mib is not None and self.gpu_free_mib>self.gpu_total_mib:
            object.__setattr__(self,'gpu_free_mib',None)
            errors.append('GPU free memory exceeds observed total')
        object.__setattr__(self,'errors',tuple(errors))

    def to_dict(self):
        return asdict(self)


class ResourceSampler:
    """Bounded cached NVML CLI/OS observation, without starting or changing models."""
    def __init__(self, ttl=2.0):
        self.ttl = ttl
        self._lock = Lock()
        self._cached = None
        self._cached_at = 0.0

    def sample(self):
        with self._lock:
            now = time.monotonic()
            if self._cached and now-self._cached_at < self.ttl:
                return self._cached
            errors=[]
            available=None
            try:
                available=psutil.virtual_memory().available / (1024**2)
            except (OSError, psutil.Error) as error:
                errors.append('System memory observation failed: '+type(error).__name__)
            free=total=device=None
            executable=shutil.which('nvidia-smi')
            if executable:
                try:
                    result=subprocess.run([executable,'--query-gpu=index,memory.free,memory.total','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=0.75,check=True)
                    # Runtime's default device is index zero. Do not aggregate independent GPUs.
                    for line in result.stdout.splitlines():
                        values=[item.strip() for item in line.split(',')]
                        if len(values)==3 and values[0]=='0':
                            device='0';free=float(values[1]);total=float(values[2]);break
                except (OSError,ValueError,subprocess.SubprocessError) as error:
                    errors.append('GPU memory observation failed: '+type(error).__name__)
            snapshot=ResourceSnapshot(time.time(),available,free,total,device,'psutil+nvidia-smi' if free is not None else 'psutil',tuple(errors))
            self._cached=snapshot;self._cached_at=now
            return snapshot


def admit_resources(spec, snapshot, *, resident=False, required_context=None):
    """Unknown peak/context/KV requirements explicitly yield conditional admission."""
    reasons=[];unknown=[];reason_codes=[];condition_codes=[]
    def measured(value):
        return value if isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value) and value>=0 else None
    ram=measured(spec.observed_memory_mib)
    gpu=measured(spec.observed_gpu_mib)
    if snapshot.available_memory_mib is not None and snapshot.available_memory_mib < spec.memory_reserve_mib:
        reasons.append('Available system memory is below the configured emergency reserve')
        reason_codes.append('ram_below_emergency_reserve')
    if snapshot.gpu_free_mib is not None and snapshot.gpu_free_mib < spec.gpu_reserve_mib:
        if resident:
            # A healthy resident llama.cpp runtime already owns its weights and
            # configured KV arena. Its own allocation must not block every next
            # request. Additional allocation is still unmeasured and runtime
            # failures remain visible; do not extend this exception to loading.
            unknown.append('Resident runtime has low free GPU headroom; additional allocation is not guaranteed')
            condition_codes.append('resident_gpu_headroom_low')
        else:
            reasons.append('Free GPU memory is below the configured emergency reserve')
            reason_codes.append('gpu_below_emergency_reserve')
    if ram is None:
        unknown.append('Model peak system-memory requirement is not measured')
        condition_codes.append('peak_ram_unmeasured')
    elif snapshot.available_memory_mib is None:
        unknown.append('Available system memory is unknown')
        condition_codes.append('available_ram_unknown')
    elif not resident and ram+spec.memory_reserve_mib > snapshot.available_memory_mib:
        reasons.append('Insufficient available system memory for measured model peak and reserve')
        reason_codes.append('insufficient_ram')
    if gpu is None:
        unknown.append('Model peak GPU-memory requirement is not measured')
        condition_codes.append('peak_gpu_unmeasured')
    elif snapshot.gpu_free_mib is None:
        unknown.append('Available GPU memory is unknown')
        condition_codes.append('available_gpu_unknown')
    elif not resident and gpu+spec.gpu_reserve_mib > snapshot.gpu_free_mib:
        # Memory reclaimed by unloading is unmeasured; reject rather than invent headroom.
        reasons.append('Insufficient free GPU memory for measured model peak and reserve')
        reason_codes.append('insufficient_gpu')
    if resident:
        unknown.append('Incremental context/KV allocation for the resident model is not measured')
        condition_codes.append('resident_incremental_kv_unmeasured')
    if spec.resource_context is None or spec.resource_context < spec.context:
        unknown.append('Peak resource measurements do not cover the configured context/KV settings')
        condition_codes.append('context_profile_unmeasured')
    if spec.resource_kv_configuration is None or spec.resource_kv_configuration!=spec.kv_configuration:
        unknown.append('Peak resource measurements do not cover the configured KV types')
        condition_codes.append('kv_profile_unmeasured')
    return {'status':'rejected' if reasons else 'conditional' if unknown else 'admitted',
            'reasons':reasons,'reason_codes':reason_codes,'conditions':unknown,'condition_codes':condition_codes,'observed':snapshot.to_dict(),
            'requirements':{'system_memory_mib':ram,'gpu_memory_mib':gpu,'measured_context':spec.resource_context,
                            'configured_context':spec.context,'required_context':required_context,'kv_configuration':spec.kv_configuration,
                            'measured_kv_configuration':spec.resource_kv_configuration,
                            'memory_reserve_mib':spec.memory_reserve_mib,'gpu_reserve_mib':spec.gpu_reserve_mib}}
