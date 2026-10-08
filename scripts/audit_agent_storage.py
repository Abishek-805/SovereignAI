"""Read-only size accounting; persistent user data is never a cleanup target."""
import json
import os
import subprocess
import argparse
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/agent-kernel-rebuild'

def category(path):
    parts=path.parts
    if 'models' in parts:return 'models'
    if 'node_modules' in parts:return 'node_modules'
    if any('venv' in p for p in parts):return 'python_environments'
    if 'workspaces' in parts or any('workspace' in p for p in parts):return 'workspaces_and_staged_drafts'
    if 'checkpoints' in parts or 'snapshots' in parts:return 'snapshots'
    if path.suffix in {'.png','.jpg','.webm'} and 'outputs' in parts:return 'browser_artifacts'
    if 'outputs' in parts or 'benchmarks' in parts:return 'test_outputs_and_evidence'
    if any(p in {'__pycache__','.cache','.pytest_cache'} for p in parts):return 'caches'
    if 'data' in parts:return 'persistent_data'
    if 'runtime' in parts:return 'runtime'
    return 'source_and_other'

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',default='storage-before.json',choices=['storage-before.json','storage-after.json'])
    args=parser.parse_args()
    totals={};top={};files=0
    for directory,dirs,names in os.walk(ROOT,followlinks=False):
        dirs[:]=[d for d in dirs if not (Path(directory)/d).is_symlink() and not (hasattr(Path(directory)/d,'is_junction') and (Path(directory)/d).is_junction())]
        for name in names:
            path=Path(directory)/name
            if path.is_symlink():continue
            try:size=path.stat().st_size
            except OSError:continue
            relative=path.relative_to(ROOT);key=category(relative);totals[key]=totals.get(key,0)+size
            top[relative.parts[0]]=top.get(relative.parts[0],0)+size;files+=1
    docker=subprocess.run(['docker','system','df','--format','{{json .}}'],capture_output=True,text=True,timeout=30)
    result={'root':str(ROOT),'files':files,'total_bytes':sum(totals.values()),'categories_bytes':totals,'top_directories_bytes':top,
            'docker_storage_separate_from_repository':docker.stdout,'docker_error':docker.stderr,
            'cleanup_performed':False,'persistent':['models','source','user workspaces','accepted artifacts','databases','historical evidence'],
            'retention_policy':'Only explicitly application-owned ephemeral caches may expire. No automatic deletion of user workspaces, accepted artifacts, or historical benchmark evidence.'}
    OUT.mkdir(parents=True,exist_ok=True);(OUT/args.output).write_text(json.dumps(result,indent=2))
    print(json.dumps({'GiB':round(result['total_bytes']/2**30,2),'categories_GiB':{k:round(v/2**30,3) for k,v in totals.items()}}))

if __name__=='__main__':main()
