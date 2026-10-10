"""Resume unexecuted Stage1A cells in a new namespace; old evidence immutable."""
import hashlib
import json
import shutil
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path
from experiments.json_action_v2 import coverage
from router.model_registry import ModelRegistry

def main():
    parent=coverage.BASE
    out=parent/('execution-'+datetime.now(timezone(timedelta(hours=5,minutes=30))).strftime('%Y%m%d-%H%M%S'))
    out.mkdir()
    original={str(p.relative_to(coverage.ROOT)):coverage.sha(p) for p in parent.rglob('*') if p.is_file()}
    coverage.save(out/'previous-evidence-sha256.json',original)
    for name in ('PREREGISTRATION.md','AMENDMENT-TO-BOUND-POLICY.md','coverage-tasks.json','registered-fixture.json','evidence-inventory.json'):
        shutil.copy2(parent/name,out/name)
    states={}
    for name,command in [('context',['docker','context','show']),('info',['docker','--host','npipe:////./pipe/dockerDesktopLinuxEngine','info','--format','{{.OSType}}']),('image',['docker','--host','npipe:////./pipe/dockerDesktopLinuxEngine','image','inspect',coverage.IMAGE]),('wsl',['wsl','--list','--verbose'])]:
        r=subprocess.run(command,capture_output=True); states[name]={'exit_code':r.returncode,'stdout':r.stdout.decode('utf-8',errors='replace'),'stderr':r.stderr.decode('utf-8',errors='replace')}
    coverage.save(out/'docker-state.json',states)
    assert states['context']['stdout'].strip()=='desktop-linux'
    assert states['info']['exit_code']==0 and states['info']['stdout'].strip()=='linux'
    assert states['image']['exit_code']==0 and json.loads(states['image']['stdout'])[0]['Id']==coverage.IMAGE
    registry=ModelRegistry(); resident=registry.verified_residency()
    assert resident==registry.specs['text'].identifier=='Qwen/Qwen3.5-4B'
    coverage.save(out/'worker-verification.json',{'resident':resident,'args':registry.launch_args('text'),'owned':registry._owns_server()})
    manifest=json.loads((coverage.ROOT/'evidence/json-action-adapter-v2/manifest.json').read_text())
    before={name:coverage.sha(coverage.ROOT/name) for name in manifest['frozen_sha256']}
    coverage.save(out/'before-source-sha256.json',before)
    coverage.BASE=out
    print('EXECUTION_DIRECTORY='+str(out),flush=True)
    coverage.execute()
    changed=[name for name,digest in before.items() if coverage.sha(coverage.ROOT/name)!=digest]
    prior_changed=[name for name,digest in original.items() if coverage.sha(coverage.ROOT/name)!=digest]
    coverage.save(out/'integrity-after.json',{'source_changes_during_resume':changed,'previous_stage1a_changes':prior_changed})

if __name__=='__main__': main()
