"""Freeze provenance before any model evaluation; no production mutations."""
import hashlib,json,shutil,datetime
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'evidence/code-agent-fidelity-v1'
FILES=['workflows/agent_kernel.py','workflows/coding_workspace.py','workflows/build_contract.py','workflows/agent_runtime_validation.py','backend/model.py','backend/service.py','backend/task_supervisor.py','backend/settings.py','backend/task_skills.py','router/coding_router.py','router/model_broker.py','router/model_registry.py','router/tool_registry.py','router/sandbox.py','skills/runtime/agent-tools/SKILL.md','experiments/kernel_docker.py']
def main():
    for name in ('native','nanobot','hermes','models','router','attendance-diagnostic','reports'):(OUT/name).mkdir(parents=True,exist_ok=True)
    path=OUT/'reports/baseline-manifest.json'
    if path.exists():raise RuntimeError('Baseline already frozen; do not replace it')
    hashes={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in FILES}
    snapshot=OUT/'native/snapshot';snapshot.mkdir()
    shutil.copy2(ROOT/'workflows/agent_kernel.py',snapshot/'agent_kernel.py')
    manifest={'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source_sha256':hashes,'production_native_default':False,'historical_benchmark_use':'none','purpose':'New separate controlled evaluation; baseline snapshot unchanged'}
    path.write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    (OUT/'reports/architecture-map.md').write_text('''# Inspected execution map

Request -> router/coding_router.py classify_coding_request -> backend/service.py _lease -> router/model_broker.py select/acquire -> router/model_registry.py owned single-server lease.

Opt-in implementation: workflows/agent_kernel.py AgentLoop.run -> ModelAdapter.fit/turn -> backend/model.py agent_tool_turn -> native assistant tool call -> ToolExecutor.execute -> existing CodeSandbox -> JSON tool observation -> next call. Current limits: 32 turns, 64 tools, 12 sandbox runs, 4096 output tokens; service allows 840 seconds within the 900-second owning supervisor.

Context compaction: ModelAdapter.fit retains original system/request and a bounded latest validation summary, removing complete old exchanges. Exact transmitted payloads are not currently persisted; experiment instrumentation must capture them.

Repair: actual command/test failures retained, patch-only existing draft repair, aggregate failure/repair metrics. Native baseline lacks per-property regression rollback and can generate oversized replacement spans. Preserve this as a baseline finding; do not quietly fix baseline.

Authority: router/tool_registry.py macro action registration is distinct from native tool schema projection in workflows/agent_kernel.py. Reuse both as they exist. Do not introduce another authoritative registry.

Validation: ValidationEngine uses immutable supplied suites or contract checks; no-oracle framework probes are only runtime/HTTP evidence. Model-authored tests remain supplemental.

Publication: CodingWorkspace._stage_changes stores changed bytes and expected revisions outside canonical files. CodingWorkspace.accept requires completed/staged Docker evidence, rechecks paths, revisions and staged hashes, then journaled publish. discard never publishes. Models never invoke accept.

Supervisor: backend/task_supervisor.py shared ContextVar owner handles aggregate counters, cancellation, deadlines and terminal state. Existing CodingWorkspace storage and checkpoints own task state; experiments add evidence logs only.

Legacy workflow: router/code_agent.py delegates admitted actions through the existing registry, with at most three attempts and repeated-error fingerprints. Existing historical evaluations in experiments/comparison_* are not reused or modified.

Production: native flag defaults to zero. No production file edits, registration changes, migration or default changes are authorized for this experiment.
''',encoding='utf-8')
if __name__=='__main__':main()
