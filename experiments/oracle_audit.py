"""Intent-bound oracle audit, independent of model outcomes."""
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from experiments.old_workflow_control import private_oracles

def main():
    directory=ROOT/'benchmarks/model-comparison'
    tasks=json.loads((directory/'frozen-40-task-manifest.json').read_text())
    oracles=private_oracles()
    rows=[]
    for task in tasks:
        name=task['task_id'];test=oracles[name]
        gaps=[]
        if name.startswith(('mf','cx')):
            gaps.append('Exercises app.process and health but does not independently call the requested core/rules APIs or prove cross-module delegation. An app-only implementation could pass.')
        if name.startswith('cp'):
            gaps.append('Behavioral tests preserve imported public APIs but do not assert every original project file remains, including package initializer files.')
        if name.startswith('rp'):
            gaps.append('Kernel validator proves README read, exact command/output and unchanged files, but does not assert the final user-facing report states the observed output. Old-control adapter requires separate command-identity audit.')
        rows.append({'task_id':name,'classification':'PARTIAL' if gaps else 'VALID',
            'requirements':task['requirements'],'private_oracle_sha256':hashlib.sha256(test.encode()).hexdigest(),
            'gaps':gaps,'ranking_use':'descriptive execution evidence only; exclude from strong ranking until supplemental verification' if gaps else 'contract-tested evidence',
            'model_outcomes_inspected_for_this_audit':False})
    (directory/'oracle_audit.json').write_text(json.dumps({'version':'v1-intent-audit','tasks':rows,
        'valid':sum(r['classification']=='VALID' for r in rows),'partial':sum(r['classification']=='PARTIAL' for r in rows),
        'invalid':0,'full_decision_gate_complete':False,'repair_required':'Supplemental versioned validation of omitted obligations; preserve frozen v1 results.'},indent=2))

if __name__=='__main__':main()
