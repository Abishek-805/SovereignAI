"""Audit recorded product trajectories; never execute or modify candidates."""
import hashlib
import json
from pathlib import Path

OUT=Path('outputs/project-error-reliability')
RAW=Path('outputs/build-contract-product/explicit-error-final')
IDS=['discount_cli','temperature_error','flask_error','node_error','age_readme']

def audit(path):
    if not path.exists():return {'status':'NOT_EXECUTED'}
    evidence=json.loads(path.read_text(encoding='utf-8'))
    final=evidence.get('final') or {}
    wrapper=final.get('result') or {}
    result=wrapper.get('result') or {}
    checks=result.get('checks') or {}
    passed=(final.get('state')=='completed' and result.get('state')=='completed'
            and result.get('validation_exit_code')==0 and checks.get('container_executed')
            and result.get('goal_checks_independent') and checks.get('build_contract_passed')
            and evidence['workspace_id']==evidence['request']['workspace_id']==result.get('workspace_id')
            and all(c.get('passed') for c in result.get('contract_results',[])))
    return {'status':'PASS' if passed else ('IN_PROGRESS' if final.get('state')=='running' else 'FAIL'),
            'job_state':final.get('state'),'latency_ms':evidence.get('latency_ms'),
            'validation_exit_code':result.get('validation_exit_code'),'checks':checks,
            'counts':(wrapper.get('supervisor') or {}).get('counts'),
            'repair_count':result.get('repair_count'),
            'error':final.get('error') or wrapper.get('answer'),
            'raw':str(path),'raw_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'failed_obligations':[c for c in result.get('contract_results',[]) if not c.get('passed')],
            'generation_context_count':len(result.get('generation_contexts',[]))}

if __name__=='__main__':
    rows={ident:audit(RAW/(ident+'.json')) for ident in IDS}
    previous=audit(Path('outputs/build-contract-product/behavior-error-contract/discount_cli.json'))
    regression=(OUT/'regression.txt').read_text(encoding='utf-8',errors='replace')
    guard=(OUT/'regression-final-guard.txt').read_text(encoding='utf-8',errors='replace')
    summary={'status':'COMPLETE' if all(r['status']=='PASS' for r in rows.values()) and 'failed' not in regression+guard and 'passed' in regression and 'passed' in guard else 'INCOMPLETE',
             'results':rows,'before_discount':previous,
             'scope':'Existing worker generation, contract, repair and acceptance; no architecture or historical benchmark changes',
             'limits':['Independent fixtures cover finite cases, not universal semantics.',
                       'Unsupported fixture expressions are never evaluated on the host.',
                       'Latency is descriptive; regression tests ran concurrently, so it is not a controlled performance comparison.']}
    (OUT/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    lines=['# Explicit requirement reliability', '', 'STATUS: '+summary['status'], '',
           '| Real browser workflow | Independently audited result | Time (s) | Repair attempts | Model switches |',
           '|---|---|---:|---:|---:|']
    for ident,r in rows.items():
        counts=r.get('counts') or {}
        lines.append(f"| {ident} | {r['status']} | {round(r.get('latency_ms',0)/1000,1)} | {r.get('repair_count','—')} | {counts.get('model_switches','—')} |")
    lines += ['', '## Before and after', '',
              'Before: explicit rejection was present in the request, but the discount worker omitted it. Docker rejected negative prices; the bounded repair did not recover.',
              'After: immutable literal exception cases become structured, file-bound checks. Generation descriptors are saved. Docker records exact input, expected exception and actual result, including the failed candidate’s return value. All supplied tests and passing behavior are rerun after repair. The worker still owns all application source.',
              'A document-only plan for an explicitly named software project now fails before writes instead of claiming completion.',
              'An additional refusal guard stops applications whose explicit error behavior has neither an executable invalid-input check nor supplied independent tests. Its final affected regression tests passed; the five fixture-backed workflows do not enter that guard.',
              'The discount switch count includes initial residency admission from the existing text worker to Coder. Both generation and repair retained Qwen2.5-Coder-3B; no repair escalation is credited.',
              '', '## Failure analysis (A–G)', '',
              'A: The old prose/checklist mentioned the requirement, but lacked an executable file-bound exception obligation. The new contract supplies it.',
              'B/C: New discount source still omits the required negative-element rejection despite the saved file descriptor containing the exact cases. This is an observed generation failure.',
              'D: Both the original unittest assertion and the new trusted Docker exception check execute the failing input.',
              'E: New repair descriptors contain the original request, exact args, expected ValueError, actual numeric return, current diff and existing fixture. Missing these facts no longer explains the observed failure.',
              'F: The same worker’s bounded repair still fails the requirement. This is not a verified recovery.',
              'G: The independent oracle expects a raised exception; a returned value is correctly rejected. A document-only completion in the intermediate age trajectory was false credit and is excluded.',
              '', '## Evidence and limitations', '',
              'Raw trajectories and screenshots: `outputs/build-contract-product/explicit-error-final/`. Intermediate failures remain in `explicit-error-v1/` and `explicit-error-v2/`; historical evidence was not rewritten.',
              'Fixtures: `fixtures.json`. Machine-readable audit: `summary.json`. Regression output: `regression.txt`. Source and historical-file hashes: `final-run-manifest.json`.',
              'The focused tests cover discount, temperature, age, email, and malformed HTTP contracts without application-specific platform implementations.',
              'Docker security verification passed all 18 probes. Generated code remained in the pinned Docker sandbox; no host execution, network, new model, or retry layer was added.',
              'Finite acceptance evidence does not prove arbitrary prompt understanding. Failed generation is retained and refused publication. This change must not be described as complete unless all five real workflows pass.',
              '', 'Full regression run before the last refusal-guard refinement:', '```', *regression.splitlines()[-8:], '```',
              '', 'Final affected regression checks:', '```', *guard.splitlines()[-8:], '```']
    (OUT/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
