"""Explicit disposable live proof, never uses a user's selected workspace."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
spec=importlib.util.spec_from_file_location('smart_eval',ROOT/'benchmarks/evaluate-smart-code-router.py')
evaluation=importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluation)

def main():
    from backend.settings import Settings
    from backend.service import Workbench
    from router.model_registry import ModelRegistry
    report_path=ROOT/'benchmarks/smart-code-repair-publication-proof.json'
    case=next(c for c in json.loads((ROOT/'benchmarks/smart-code-router/main.json').read_text())['cases'] if c['id']=='main-021')
    case['context']['initial_files']={'solution.py':'def clamp(value, low, high):\n    return value\n'}
    case['oracle']['trusted_files']['test_contract.py']+='\ntry:\n    clamp(1,5,0)\nexcept ValueError:\n    pass\nelse:\n    raise AssertionError("invalid bounds accepted")\n'
    original=case['context']['initial_files']['solution.py']
    directory=ROOT/'benchmarks/disposable-code-proof'/str(time.time_ns())
    settings=Settings(data_dir=directory/'data',project_dir=directory/'projects',supervisor_seconds=900)
    settings.data_dir.mkdir(parents=True)
    shutil.copyfile(Settings().data_dir/'sandbox-validation.json',settings.data_dir/'sandbox-validation.json')
    workbench=Workbench(settings=settings,registry=ModelRegistry(8087))
    with evaluation.LiveSuiteLock(ROOT/'data/smart-code-router-live.lock'):
        sandbox=workbench._verified_coding_sandbox()
        baseline=evaluation.validate_candidate(case,{'solution.py':original.encode()},sandbox,120)
        report={'baseline':baseline,'scope':'disposable fixture only','published':False,'candidate_repair_loop_succeeded':None}
        evaluation.shared.atomic_report(report_path,report)
        if baseline['artifact_verified'] or not baseline['container_executed']:
            raise RuntimeError('Expected actual failing baseline was not observed')
        workspace=workbench.coding.create('Disposable code repair and publication proof')
        wid=workspace['workspace_id']
        workbench.coding.write(wid,'solution.py',original)
        instruction='Fix solution.py: clamp value inclusively to low/high and raise ValueError when low exceeds high. Keep clamp(value, low, high). The existing function failed actual Docker validation with exit 1. Return complete corrected source.'
        result=workbench.run_coding_project_task(wid,'solution.py',instruction)
        report.update(workspace_id=wid,workspace=workspace,result=result)
        evaluation.shared.atomic_report(report_path,report)
        if result.get('state')!='completed':return
        files=evaluation.candidate_files(case,result)
        validation=evaluation.validate_candidate(case,{name:text.encode() for name,text in files.items()},sandbox,120)
        report.update(validation=validation,original_preserved_before_accept=workbench.coding.read(wid,'solution.py')['content']==original)
        if validation['artifact_verified']:
            accepted=workbench.accept_coding_task(wid,result['task_id'])
            saved=workbench.coding.read(wid,'solution.py')['content']
            report.update(accepted=accepted,published=saved==files['solution.py'],published_sha256=hashlib.sha256(saved.encode()).hexdigest(),baseline_failure_to_coder_correction_pass=True)
        evaluation.shared.atomic_report(report_path,report)
        print(json.dumps({'published':report['published'],'baseline_failed':not baseline['artifact_verified'],'validated':validation['artifact_verified']}))

if __name__=='__main__':main()
