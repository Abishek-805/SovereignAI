"""Real model/Docker source generation and reviewed publication on disposable data."""
import json
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.model import LocalModel
from router.sandbox import CodeSandbox
from router.task_ledger import TaskLedger
from workflows.coding_workspace import CodingWorkspace
from workflows.source_quality import generated_source_issue

configuration = json.loads((Path(__file__).resolve().parents[1] / 'data/sandbox-validation.json').read_text())
with tempfile.TemporaryDirectory(prefix='sovereign-release-source-') as directory:
    root = Path(directory)
    workspace = CodingWorkspace(root / 'metadata', root / 'projects')
    wid = workspace.create('Disposable real generation')['workspace_id']
    model = LocalModel()
    sandbox = CodeSandbox('docker', image_id=configuration['image_id'], task_root=root / 'jobs')
    task = workspace.run_project(wid, '', 'Create a simple complete HTML web page and CSS stylesheet inside a web folder, with index.html linked to style.css.',
        model, sandbox, TaskLedger(root / 'ledger'), progress=lambda message: print(message, flush=True))
    checks = {'completed':task['state']=='completed', 'staged':task.get('publication_state')=='staged',
        'docker_executed':task['checks'].get('container_executed') is True,
        'canonical_unchanged_before_accept':not workspace.raw_files(wid)}
    for change in task['changes']:
        if change['action'] in {'create', 'edit'}:
            checks['substantive_'+change['path']] = generated_source_issue(change['path'],change['after'],task['instruction'],None,2) is None
    if not all(checks.values()): raise RuntimeError(json.dumps(checks))
    accepted = workspace.accept(wid, task['task_id'])
    checks['published'] = accepted['publication_state']=='published'
    checks['saved_files'] = len(workspace.raw_files(wid))==2
    restarted = CodingWorkspace(root / 'metadata', root / 'projects')
    checks['restart_persistence'] = restarted.raw_files(wid)==workspace.raw_files(wid)
    restarted.undo(wid, task['task_id'])
    checks['undo_restores_empty_project'] = not restarted.raw_files(wid) and not restarted.get(wid)['folders']
    model.close()
    print(json.dumps(checks, indent=2), flush=True)
    if not all(checks.values()): raise RuntimeError('Release source publication check failed')
