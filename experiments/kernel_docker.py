"""Experimental adapter using existing verified Docker isolation unchanged."""
import json
from pathlib import Path
import time
from router.sandbox import (CodeSandbox, SANDBOX_VERIFICATION_VERSION,
                            SANDBOX_VERIFICATION_MAX_AGE, sandbox_policy_fingerprint)


class DockerCommands:
    def __init__(self, root, task_root):
        record = json.loads((Path(root)/'data/sandbox-validation.json').read_text())
        if (record.get('verification_version') != SANDBOX_VERIFICATION_VERSION or
            record.get('policy_fingerprint') != sandbox_policy_fingerprint() or
            not 0 <= time.time()-record['validated_at'] <= SANDBOX_VERIFICATION_MAX_AGE):
            raise RuntimeError('Docker verification missing, stale or mismatched')
        self.sandbox = CodeSandbox('docker',image_id=record['image_id'],task_root=Path(task_root))
        self.image_id = record['image_id']

    def __call__(self, command, files, seconds):
        if seconds < 1:
            raise TimeoutError('Task deadline reached')
        script = '''import os, shutil, subprocess, sys
from pathlib import Path
root = Path('/output/project')
shutil.copytree('/input', root, ignore=lambda source,names: {'program.py'} if Path(source)==Path('/input') else set())
os.chdir(root)
os.environ.update(HOME='/output', TMPDIR='/output', PIP_NO_INDEX='1', npm_config_offline='true')
result = subprocess.run(['bash','-lc',COMMAND], timeout=LIMIT)
sys.exit(result.returncode)
'''.replace('COMMAND',repr(command)).replace('LIMIT',str(max(1,min(110,int(seconds)-1))))
        raw = self.sandbox.execute(script,timeout=max(1,min(120,int(seconds))),
                                   input_files={name:value.encode() for name,value in files.items()})
        return {'command':command,'docker_executed':raw.executed,'exit_code':raw.exit_code,
                'stdout':raw.stdout,'stderr':raw.stderr,'sandbox_image_id':self.image_id}
