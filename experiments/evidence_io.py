"""Benchmark evidence-only Windows replacement retries; no worker changes."""
import json
import os
from pathlib import Path
import time

def install(root, *, replacement=None, sleep=time.sleep):
    """Retry transient sharing/access failures for benchmark JSON checkpoints.

    The task clock continues running. No inference, tool, repair, validation,
    fixture, or budget is changed. Permanent errors still propagate.
    """
    base=(Path(root)/'benchmarks/model-comparison').resolve()
    original=replacement or Path.replace
    if getattr(Path.replace,'_sovereign_evidence_io',False):return
    def replace(source,target):
        destination=Path(target)
        try:
            scoped=source.resolve().is_relative_to(base) and destination.resolve().is_relative_to(base)
        except OSError:scoped=False
        if not scoped or source.suffix!='.tmp' or destination.suffix!='.json':
            return original(source,target)
        started=time.monotonic(); errors=[]
        for attempt in range(41):
            try:
                result=original(source,target)
                if errors:
                    event={'unix_time':time.time(),'source':str(source),'destination':str(destination),
                           'retries':len(errors),'elapsed_seconds':time.monotonic()-started,
                           'errors':errors,'operation':'evidence_replace_only','pid':os.getpid()}
                    with (base/'evidence-io-retries.jsonl').open('a',encoding='utf-8') as handle:
                        handle.write(json.dumps(event)+'\n')
                return result
            except PermissionError as error:
                if getattr(error,'winerror',None) not in (None,5,32,33) or attempt==40:raise
                errors.append(str(error)); sleep(.025)
    replace._sovereign_evidence_io=True
    Path.replace=replace

