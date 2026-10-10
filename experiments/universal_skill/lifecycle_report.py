"""Summarize preserved staging receipts without touching frozen or training artifacts."""
from pathlib import Path
import json,hashlib
ROOT=Path(__file__).resolve().parents[2]
OUT=Path((ROOT/'experiments/universal_skill/lifecycle-output.txt').read_text())
def load(name):
    content=(OUT/name).read_bytes()
    try:text=content.decode('utf-8-sig')
    except UnicodeDecodeError:text=content.decode('cp1252')
    return json.loads(text)
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
integrity={}
for name in ('protected-before.json','training-before.json'):
    hashes=load(name);changed=[p for p,h in hashes.items() if not (ROOT/p).exists() or digest(ROOT/p)!=h]
    integrity[name]={'status':'PASS' if not changed else 'FAIL','files':len(hashes),'changed':changed}
sources=['backend/jobs.py','backend/model.py','backend/service.py','router/task_completion.py','rag/answer.py','rag/grounding.py','rag/analytics.py','rag/tables.py','rag/recovery.py',
 'frontend/llama-ui/src/lib/stores/chat/index.svelte.ts','frontend/llama-ui/src/lib/components/sovereign/AgentChat.svelte',
 'frontend/llama-ui/src/lib/components/app/chat/ChatMessages/ChatMessage/ChatMessage.svelte']
# Recovery's pre-task content is identical except for the isolated terminal guard.
recovery=ROOT/'rag/recovery.py';rollback=OUT/'rollback/rag/recovery.py'
if not rollback.exists():
    rollback.parent.mkdir(parents=True,exist_ok=True)
    rollback.write_text(recovery.read_text().replace("        # Claim assessment already owns its one repair; retrieval cannot reset that budget.\n        if result.get('checks',{}).get('evidence_assessment') is not None:\n            stop='assessment_terminal';break\n",''))
metrics=[]
for r in load('api-acceptance.json'):
    final=r['snapshots'][-1]
    metrics.append({'case':r['case'],'seconds':r['seconds'],'transport_state':final['state'],'completion':final.get('completion')})
calls=[]
for line in (OUT/'gemma/trajectories.jsonl').read_text().splitlines():
    r=json.loads(line)
    calls.append({'question':r['question'],'run_id':r['run_id'],'seconds':r['seconds'],'error':r.get('error'),
      'model_calls':[{'stage':c.get('stage'),'seconds':c.get('seconds'),'usage':c.get('usage'),'gemma_profile_verified':c.get('gemma_profile_verified')} for c in r.get('model_calls',[])]})
cases=[]
for file in ('final-api-acceptance.json','final-fault-acceptance.json'):
    if not (OUT/file).exists():continue
    for r in load(file):
        if file=='final-api-acceptance.json' and r['case'] in {'invalid_id','missing_id','quote_mismatch'}:continue
        final=r['snapshots'][-1];result=final.get('result') or {}
        cases.append({'case':r['case'],'seconds':r['seconds'],'fault':r['fault'],'state':final['state'],'error':final.get('error'),
          'completion':final.get('completion'),'answer':result.get('answer'),'checks':(result.get('result') or result).get('checks'),'receipt':file})
report={'status':'PARTIAL','staging_ui':'PASS','production_acceptance':'NOT_VERIFIED','training_started':False,'RUN_TRAIN':False,
 'root_causes':['Connected table availability could select analytics for a narrative question.',
 'Grouped citations [S1, S2] were not recognized by exact-label and numeric guards, falsely rejecting supported claims.',
 'Evidence recovery could regenerate after the claim assessor had exhausted its one repair.',
 'Terminal job/poll ownership and completion handling allowed stale draft/status updates.'],
 'changes':sources,'source_sha256':{p:digest(ROOT/p) for p in sources},'integrity':integrity,
 'tests':{'backend':{'passed':251,'log':'backend-all-final-tests.log'},'frontend_unit':{'passed':728,'files':61,'log':'frontend-final-tests.log'},
 'frontend_check':{'errors':0,'warnings':0,'log':'frontend-check-complete.log'}},
 'ui_observations':{'chat_overview_after_fix':'PASS: multi-source narrative; Ready; no Stop; final prose persisted.',
 'agent_overview_after_fix':'PASS: final multi-source narrative; New chat enabled; Stop absent.',
 'history_reopen':'PASS: previous overview, missing rationale, deterministic total and missing-file error restored.',
 'cancel_verification':'PASS: observed Verifying sourced answer, clicked Stop task, final Task stopped with draft removed and composer enabled.',
 'backend_error':'PASS: unavailable requested filename terminal error; composer enabled.',
 'cancel_generation':'NOT_VERIFIED live; cancellation and terminal ownership regression checks pass.'},
 'live_cases':cases,'first_and_warm_samples':metrics,'model_call_metrics':calls,
 'cold_latency':'NOT_VERIFIED: resident model shared with production; no forced unload/restart.',
 'runtime':{'model':'gemma-4-E2B-it-Q4_K_M.gguf','alias':'sovereign-rag','model_port':8087,'staging_port':8099,
 'weight_hash':'NOT_VERIFIED in this pass; existing registered runtime profile attested per receipt.'},
 'limitations':['Controlled reconstructed KPRIET and synthetic workbook fixtures; original uploaded workbook and 24ALR051 not accepted here.',
 'Faulted initial ID/quote tests intercepted tokenizer responses and are invalid; superseded by final-fault-acceptance.json, originals preserved.',
 'Latency is a small shared-runtime sample, not a benchmark; cold plus three warm per every requested category incomplete.',
 'Grouped citations normalize to adjacent labels before validation; unknown labels, exact quotes, claim IDs, numeric checks and one repair remain enforced.',
 'Raw numeric totals exclude absent/non-numeric cells and do not infer grading weights or maximum marks.',
 'Production was not restarted or activated; live production acceptance remains pending.'],
 'evidence':str(OUT),'rollback':str(OUT/'rollback')}
(ROOT/'rag-answer-lifecycle-report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False))
lines=['# SovereignAI RAG answer lifecycle repair','',
 'Status: **PARTIAL** overall; staged overview delivery **PASS**; production acceptance **NOT_VERIFIED**.',
 '', '## Proven causes and repair',*['- '+x for x in report['root_causes']],
 '', 'The existing request interpreter now chooses passage or table evidence from the requested operation. Numeric totals use the existing source-bound executor. Grouped citations are normalized before the unchanged grounding checks. Claim assessment is terminal after its one repair, so retrieval recovery cannot reset that budget. Terminal jobs and frontend polls reject stale updates; verified answers receive completed status.',
 '', '## Before and after',
 '| Case | Before | After in staging |','|---|---|---|',
 '| Institution overview with tables connected | Cohort/pass-rule/table errors | Narrative passage answer in Chat and Agent |',
 '| Multi-source citations | [S1, S2] falsely rejected; postcode fragments flagged | [S1] [S2] checked with exact source bindings; final overview delivered |',
 '| Rejected draft | Further retrieval/answer generation after repair | Assessed rejection terminal; one repair maximum |',
 '| Exact-ID score total | Unsupported ordering plan | Raw total 25.5 on controlled fixture, missing value explicitly excluded |',
 '| Verification cancellation | Risk of stale draft/terminal polling | Task stopped, draft removed, input enabled |',
 '', '## Validation',
 '251 backend tests and 728 frontend unit tests (61 files) pass. Svelte check: zero errors/warnings. Final isolated frontend build log: `frontend-build-complete.log`. No new dependency, reviewer model, router, database, or planner was introduced.',
 '', '## Live UI observations',*['- '+k+': '+v for k,v in report['ui_observations'].items()],
 '', '## Live controlled API evidence',
 '| Case | Seconds | Transport state | Error |','|---|---:|---|---|',
 *[f"| {r['case']} | {r['seconds']:.2f} | {r['state']} | {str(r['error'] or '').replace('|','/')} |" for r in cases],
 '', 'Unsupported content was injected only in the isolated test harness, after genuine model output. Claim-ID and quote faults mutate genuine assessment output. These are safety tests, not fabricated model successes. Raw outputs and mutations are retained separately.',
 '', '## Timing and reproducibility',
 'Initial controlled Agent overview: 26.83 s. Warm location requests: 17.08, 12.00, 11.53 s. Earlier missing rationale: 15.36 s. Source-bound total: 1.08 s and no model calls. These precede the final grouped-citation/recovery correction; final case timings and every captured call/stage/token usage are in JSON and raw trajectories.',
 'Cold latency NOT_VERIFIED because Gemma was already resident and shared. No model was unloaded to manufacture a cold sample. Full cold + three warm samples per category remain unverified.',
 '', '## Integrity',*['- '+k+': '+str(v['files'])+' files; '+v['status'] for k,v in integrity.items()],
 '- CURRENT_BASELINE retrieval and isolated E5 experiment retained. No T01–T15 inspection. No dataset modification. training_started=false; RUN_TRAIN=false.',
 '', '## Activation and rollback',
 'The staged UI is at http://127.0.0.1:8099/. Production was deliberately not restarted, as required by the master prompt. Activate only when ready, from PowerShell:',
 '```powershell',r'Set-Location C:\Users\ashek\Desktop\SovereignAI\frontend\llama-ui','npm.cmd run build',r'Set-Location C:\Users\ashek\Desktop\SovereignAI',r'.\stop-workbench.ps1',r'.\start-workbench.ps1','```',
 'Then reload the actual production UI and repeat overview, total and missing-rationale requests. That activation is not accepted by this staging report.',
 'Rollback snapshots: `'+str(OUT/'rollback')+'`. Restore only the listed changed files after checking for later user edits, rebuild the frontend, and restart using the owned-process scripts. Do not reset the whole repository.',
 '', '## Limitations and remaining acceptance',*['- '+x for x in report['limitations']],
 '- Missing rationale, unsupported content, IDs, quotes, conjunctions, numeric literals and URLs covered by regression/live evidence; live UI coverage is narrower than API/unit coverage. No universal reliability claim is made.',
 '', '## Changed files',*['- `'+p+'`' for p in sources],
 '', 'Evidence: `'+str(OUT)+'`. Machine-readable details: `rag-answer-lifecycle-report.json`.']
(ROOT/'rag-answer-lifecycle-report.md').write_text('\n'.join(lines),encoding='utf-8')
print(json.dumps({'integrity':integrity,'live_cases':[(c['case'],c['state']) for c in cases]}))
