import json,time
from pathlib import Path
from scripts.model_project_understanding_diagnostic import project_result
from workflows.coding_workspace import CodingWorkspace
from backend.settings import Settings
from backend.model import LocalModel
from router.model_registry import ModelRegistry
from router.task_ledger import TaskLedger
from router.sandbox import CodeSandbox
saved=json.loads(Path('evidence/product-reliability-v1/live-model/persistent_notes.json').read_text())
failed=json.loads(Path('evidence/product-reliability-v1/notes-repair-after.json').read_text())['result']
registry=ModelRegistry();lease=registry.acquire_lease('code')
work=CodingWorkspace(Settings().data_dir,Settings().project_dir or Path.home()/'Documents/SovereignAI/Projects')
image=json.loads(Path('data/sandbox-validation.json').read_text())['image_id']
model=LocalModel();start=time.monotonic()
try:
 result=work.run_project(saved['workspace_id'],'',saved['case']['request'],model,CodeSandbox('docker',image),
    TaskLedger(Path('evidence/product-reliability-v1/repair-ledger')),reusable_plan=failed['operation_plan'],repair_candidate=failed)
 evidence={'label':'coder_retained_candidate','original_failed_evidence':'live-model/persistent_notes.json',
    'latency':time.monotonic()-start,'lease':lease,'result':result}
 Path('evidence/product-reliability-v1/notes-repair-coder.json').write_text(json.dumps(evidence,indent=2))
 print(result['state'],result.get('stderr','')[-1200:])
finally:model.close()
