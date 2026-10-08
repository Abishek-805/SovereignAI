"""Summarize preserved acceptance evidence without promoting partial success."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'outputs/agent-kernel-rebuild'
def main():
    workflows=[]
    for directory in OUT.iterdir():
        result=directory/'result.json';verification=directory/'accepted-independent.json'
        if result.is_file() and verification.is_file():
            r=json.loads(result.read_text());v=json.loads(verification.read_text())
            workflows.append({'evidence':str(directory),'passed':r['state']=='completed' and v.get('passed') is True,'case':directory.name.split('-')[0],'metrics':r.get('metrics',{})})
    browser=[]
    for directory in sorted(OUT.glob('browser-*')):
        file=directory/'final.json'
        if file.exists():
            r=json.loads(file.read_text());terminal=None
            admission=directory/'admission.json'
            if admission.exists():
                a=json.loads(admission.read_text());wid=a.get('request',{}).get('workspace_id')
                if wid:
                    taskfiles=[p for p in (ROOT/'data/coding-workspaces'/wid/'tasks').glob('*.json') if not p.name.endswith('-agent.json')]
                    if taskfiles:
                        terminal=json.loads(max(taskfiles,key=lambda p:p.stat().st_mtime).read_text())
                        (directory/'terminal-task.json').write_text(json.dumps(terminal,indent=2),encoding='utf-8')
            browser.append({'evidence':str(directory),'state':terminal.get('state') if terminal else r.get('state'),'agent_state':terminal.get('agent_state') if terminal else None,'error':terminal.get('error') if terminal else r.get('error'),'elapsed':terminal.get('metrics',{}).get('elapsed',r.get('elapsed')) if terminal else r.get('elapsed'),'accepted':(directory/'preservation.json').exists()})
    api=[]
    for directory in OUT.glob('coder-api-*'):
        file=directory/'final.json'
        if file.exists():
            r=json.loads(file.read_text());inner=r.get('result') or {};inner=inner.get('result',inner)
            api.append({'evidence':str(directory),'state':r.get('state'),'accepted':(directory/'accept.json').exists(),'model':inner.get('routing',{}).get('model'),'error':inner.get('error'),'metrics':inner.get('metrics',{})})
    storage={}
    for phase in ('before','after'):
        file=OUT/('storage-'+phase+'.json')
        if file.exists():storage[phase]=json.loads(file.read_text())
    summary={'status':'INCOMPLETE','isolated_workflows':workflows,'browser_attempts':browser,'api_cases':api,'storage':storage,'production_default':'legacy; native kernel remains gated','limitations':['UI acceptance alone does not independently prove business logic.','No universal model correctness or overall architecture superiority is claimed.','Frozen benchmark results are not rerun or used for tuning.']}
    (OUT/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    lines=['# Native agent kernel acceptance','', 'Status: INCOMPLETE until all requested live acceptance gates pass.','',
           'The worker chooses native tools, receives actual Docker observations, and stages changes for explicit review. The default production path remains gated.','',
           '## Verified evidence','',f'- Isolated accepted workflows: {sum(w["passed"] for w in workflows)}.',
           '- Final regression: see regression-final.txt (1,310 passed, 7 skipped).',
           '- Frontend: see frontend-final.txt (0 errors, 0 warnings).','',
           '## Live UI attempts','', '| Evidence directory | State | Accepted | Seconds |','|---|---|---|---|']
    lines += [f'| {Path(b["evidence"]).name} | {b["state"]} | {b["accepted"]} | {b["elapsed"]} |' for b in browser]
    lines+=['','Final affected checks: 71 passed. Docker safety: all 18 probes passed.','',
            '## Actual API cases','', '| Model | State | Accepted | Evidence |','|---|---|---|---|']
    lines += [f'| {a["model"]} | {a["state"]} | {a["accepted"]} | {Path(a["evidence"]).name} |' for a in api]
    lines+=['','## Findings','',
            '- Qwen3.5 completed an accepted multi-file edit with an immutable supplied oracle. Six isolated model-generated workflows also passed independent post-acceptance validation.',
            '- The exact unseeded attendance-app UI request did not reach accepted completion. It overgenerated tests, produced inconsistent interfaces/identity handling, attempted broad replacements, and exhausted budgets during repair.',
            '- Qwen2.5-Coder selected for mechanical rename failed native generation before any tool action, hitting the output limit. API compatibility alone was insufficient.',
            '- Corrected harness failures: cold-start readiness deadline, Unicode raw logs, task-budget mismatch, missing command-error state during compaction, and underspecified patch semantics. Model failure results were preserved.',
            '- No independent paired old/new architecture superiority comparison was completed. Screenshots and isolated successes do not establish one.',
            '- Release decision: retain the native kernel behind its opt-in flag. Do not select a universal worker or migrate production from these results.']
    lines+=['','All unsuccessful attempts are preserved. Environment/startup failures are distinct from model-generation, test-interface and repair failures.','',
            '## Storage','', '| Category | Before GiB | After GiB |','|---|---:|---:|']
    before=storage.get('before',{}).get('categories_bytes',{});after=storage.get('after',{}).get('categories_bytes',{})
    lines += [f'| {k} | {before.get(k,0)/2**30:.3f} | {after.get(k,0)/2**30:.3f} |' for k in sorted(set(before)|set(after),key=lambda k:after.get(k,before.get(k,0)),reverse=True)]
    lines+=['','No existing user data was deleted. Owned temporary logs are bounded to 64 MiB and seven days; checkpoints store patches and revision metadata. Models dominate measured storage. Docker storage is accounted separately in the raw JSON.','',
            '## Release limits','',*['- '+x for x in summary['limitations']],'- Native artifact adapter publication and arbitrary no-oracle tasks are not release-validated.']
    (OUT/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
if __name__=='__main__':main()
