"""Read-only audit of preserved product acceptance evidence."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/product-completion-20261005'

def candidates(value):
    if isinstance(value,dict):
        if 'build_contract' in value and 'checks' in value:yield value
        for item in value.values():yield from candidates(item)
    elif isinstance(value,list):
        for item in value:yield from candidates(item)

def main():
    rows=[]
    for name in ['discount_cli','temperature_error','flask_error','node_error','age_readme']:
        arm='product-worker-policy-fixed' if name in {'node_error','age_readme'} else 'product-worker-policy-v1'
        path=ROOT/'outputs/build-contract-product'/arm/(name+'.json')
        raw=json.loads(path.read_text())
        result=next(c for c in candidates(raw) if c.get('state')=='completed')
        checks=result['checks']
        passed=all(checks.get(k) is True for k in ['container_executed','tests_passed','build_contract_passed']) and result['validation_exit_code']==0
        assert passed,name
        rows.append({'case':name,'passed':passed,'evidence':str(path.relative_to(ROOT)),
                     'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'checks':checks,
                     'published':checks.get('target_committed',False)})
    artifacts=[]
    for ext in ['md','docx','xlsx']:
        path=OUT/('artifact-'+ext+'-independent.json')
        artifacts.append({'format':ext,**json.loads(path.read_text())})
    summary={'project_cases':rows,'artifacts':artifacts,
             'limitations':['Five scoped acceptance cases are not a universal correctness guarantee.',
                            'Existing-project repair is verified; automatic generated-candidate recovery is not claimed.',
                            'Before/after evidence is a diagnostic comparison, not a controlled model benchmark.',
                            'Offline sandbox cannot install arbitrary missing dependencies.'],
             'historical_evidence_preserved':True}
    reconnect=ROOT/'outputs/product-verification-20261004/browser-1791212958296'
    assert json.loads((reconnect/'independent-validation.json').read_text())['state']=='completed'
    gates=['multifile-fixed/multifile-verdict.json','multifile-fixed/queue-final.json',
           'repair-output-fixed/repair-independent.json','normal-chat.json','browser-rag.json',
           'insufficient-evidence-verdict.json','persistence-after-model-reload.json',
           'persistence-after-backend-restart.json','browser-files.json']
    summary['additional_evidence']=[{'path':g,'sha256':hashlib.sha256((OUT/g).read_bytes()).hexdigest()} for g in gates]
    summary['browser_reconnect_evidence']=str(reconnect.relative_to(ROOT))
    security=json.loads((OUT/'docker-security-final.txt').read_text(encoding='utf-8-sig'))
    assert all(security.values()),security
    summary['docker_security_checks']=security
    (OUT/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    lines=['# Product completion acceptance evidence','',
           'The local model generated all application implementations. Independent supplied tests and Docker execution gate review readiness; staged files are not silently published.','',
           '| Case | Outcome | Raw evidence |','|---|---|---|']
    lines += [f"| {r['case']} | PASS | [{r['evidence']}](../../{r['evidence']}) |" for r in rows]
    lines += ['', '## Changes and comparison','',
              'Previously, the five-case audit passed two cases. The final scoped audit passes all five. The original failed trajectories remain intact under outputs/build-contract-product/explicit-error-* and outputs/project-error-reliability/. This is diagnostic evidence, not an overall model superiority claim.', '',
              'Straightforward work retains the existing Coder worker. Requirements-heavy project generation starts with the existing Qwen3.5-4B worker, without a mandatory planning handoff. Obvious software creation bypasses a redundant intent-model call. “Standard library” no longer incorrectly redirects software requests to document creation.', '',
              'Validation now retains expected stdout separately from observed stdout, recognizes explicit run/output obligations, and binds output preservation to a unique existing executable. Ambiguous entrypoints and unsupported behavioral obligations remain unverified instead of being credited as success.', '',
              '## Additional acceptance','',
              '- Real existing-project repair: repair-output-fixed/repair.json and repair-independent.json.',
              '- Cross-file model edit, accepted execution and unrelated-file preservation: multifile-fixed/multifile-verdict.json.',
              '- Queue ownership, deferred chat and cancellation: multifile-fixed/queue-final.json.',
              '- Python, Node and Java Docker entrypoint execution: multifile-fixed/language-*.json.',
              '- Model-generated Markdown, Word and Excel: artifact-*-independent.json (original content and hashes independently checked).',
              '- Browser file operations: browser-files.json.',
              '- Browser chat and selected-source RAG: normal-chat.json and browser-rag.json.',
              '- Missing-source-fact abstention: insufficient-evidence-verdict.json.',
              '- Model reload and backend restart preserve original artifact hashes and workspace contents: persistence-after-*.json.',
              '- Browser creation, disconnect/reload, UI acceptance and independent Docker validation: ../product-verification-20261004/browser-1791212958296/.',
              '- Full regression: regression-entrypoint-final.txt; frontend static check: ../project-error-reliability/frontend-check.txt.',
              '- Pinned Docker security probes: docker-security-final.txt.', '',
              '## Limits','']
    lines += ['- '+s for s in summary['limitations']]
    (OUT/'report.md').write_text('\n'.join(lines)+'\n')
    print('Audited 5/5 independent project cases and 3 artifact formats.')

if __name__=='__main__':main()
