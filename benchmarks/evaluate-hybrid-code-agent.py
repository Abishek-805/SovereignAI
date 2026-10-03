"""Six-arm isolated comparison; E uses frozen pre-hybrid coding entry points.

All arms share runtime settings, tools, Docker and independent oracle harness.
Only F uses the new runner; E restores exact V2 service/workflow source methods.
This isolates orchestration, not a historical full-binary deployment comparison.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import types

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

v2 = load('hybrid_v2_harness', ROOT/'benchmarks/evaluate-smart-code-router-v2.py')
base = v2.base
base.ARMS['F'] = None
original_provenance = v2.provenance
DIRECTORY = ROOT/'benchmarks/hybrid-code-agent'

def configure_arm(workbench, arm):
    v2.configure_arm(workbench, arm)
    if arm == 'F':
        return
    manifest = json.loads((DIRECTORY/'baseline-source.json').read_text())
    for name, expected in manifest['sha256'].items():
        if hashlib.sha256((DIRECTORY/name).read_bytes()).hexdigest() != expected:
            raise ValueError('Frozen baseline source mismatch')
    service = load('hybrid_frozen_service', DIRECTORY/'baseline-service.py')
    workflow = load('hybrid_frozen_workflow', DIRECTORY/'baseline-coding-workspace.py')
    workbench.run_coding_project_task = types.MethodType(service.Workbench.run_coding_project_task, workbench)
    workbench.coding.run_project = types.MethodType(workflow.CodingWorkspace.run_project, workbench.coding)
    workbench.coding.run = types.MethodType(workflow.CodingWorkspace.run, workbench.coding)

def provenance(dataset, args, settings, registry):
    result = original_provenance(dataset, args, settings, registry)
    for path in [Path(__file__).resolve(), *DIRECTORY.glob('baseline-*')]:
        result['production_sha256'][path.relative_to(ROOT).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    result['comparison_policy'] = 'A/B/C pinned, D prior broker, E frozen V2 coding entrypoints, F hybrid; common current runtime/oracles; history disabled'
    return result

def main():
    if '--dataset' not in sys.argv:
        sys.argv += ['--dataset', str(DIRECTORY/'main.json')]
    if '--output' not in sys.argv:
        sys.argv += ['--output', str(ROOT/'benchmarks/hybrid-code-agent-results.json')]
    output = Path(sys.argv[sys.argv.index('--output')+1]).resolve()
    if output.name.startswith('smart-code-router'):
        raise ValueError('Historical router evidence cannot be overwritten')
    base.configure_arm = configure_arm
    base.capture = v2.capture
    base.shared.run_provenance = provenance
    base.main()

if __name__ == '__main__':
    main()
