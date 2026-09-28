"""Actual Docker terminal synchronization against an isolated mixed-asset fixture."""
import hashlib
import json
import threading
from pathlib import Path
from uuid import uuid4

from backend.jobs import Job
from backend.service import Workbench
from router.sandbox import CodeSandbox
from workflows.coding_workspace import CodingWorkspace


root = Path(__file__).resolve().parents[1]
output = root / 'benchmarks' / 'terminal-project-sync-acceptance' / uuid4().hex
output.mkdir(parents=True)
service = Workbench.__new__(Workbench)
service.ask_lock = threading.Lock()
service.coding = CodingWorkspace(output / 'data', output / 'projects')
image = json.loads((root / 'data' / 'sandbox-validation.json').read_text())['image_id']
service._verified_coding_sandbox = lambda: CodeSandbox('docker', image, output / 'containers')
workspace = service.coding.create('Isolated terminal synchronization')['workspace_id']
service.coding.write(workspace, 'old.txt', 'original')
service.coding.write(workspace, 'nested/program.py', 'print("nested")')
asset = b'\x89PNG\x00' + b'asset' * 260000
service.coding.import_bytes(workspace, 'assets/large.png', asset)
before = service.coding.raw_files(workspace)
success = service.execute_terminal(workspace, "printf 'result' > new.txt; rm old.txt; printf 'updated' > nested/program.py", Job('terminal'))
after = service.coding.raw_files(workspace)
failure = service.execute_terminal(workspace, "printf 'must not persist' > failed.txt; exit 1", Job('terminal'))
checks = {
    'successful_command': success['state'] == 'completed',
    'created_file': after.get('new.txt') == b'result',
    'deleted_file': 'old.txt' not in after,
    'nested_wrapper_preserved_and_edited': after.get('nested/program.py') == b'updated',
    'large_asset_byte_identical': after.get('assets/large.png') == asset,
    'failed_command_not_applied': failure['state'] == 'failed' and service.coding.raw_files(workspace) == after,
    'actual_workspace_returned': success['workspace_id'] == workspace,
}
record = {'checks': checks, 'success': success, 'failure': failure,
          'asset_sha256': hashlib.sha256(asset).hexdigest(), 'workspace': service.coding.get(workspace)['host_path']}
(output / 'results.json').write_text(json.dumps(record, indent=2))
print(json.dumps({'checks': checks, 'results': str(output / 'results.json')}, indent=2))
raise SystemExit(0 if all(checks.values()) else 1)
