"""Honest activation-gated report from recorded requests; no production mutation."""
from pathlib import Path
import json,hashlib
ROOT=Path(__file__).resolve().parents[2]
OUT=Path((ROOT/'experiments/universal_skill/lifecycle-followup-output.txt').read_text().strip())
OLD=Path((ROOT/'experiments/universal_skill/lifecycle-output.txt').read_text().strip())
def load(name):return json.loads((OUT/name).read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
requests=load('isolated-live-requests.json')
source_rows=load('24ALR051-independent-source-records.json')
all_row=next(r for r in source_rows if r['sheet']=='All')['record']
marks={field:value for field,value in all_row.items() if field.startswith(('WAT ','CAT '))}
expected=sum(marks.values())
result=requests[0]['snapshots'][-1]['result'];query=result['result']['table_query']
group=query['measurements'][0]
assert group['value']==expected and len(group['included'])==len(marks)
assert all(cell['raw']==marks[cell['measurement']] for cell in group['included'])
assert requests[1]['snapshots'][-1]['error_code']=='needs_input'
assert 'No exact matching record' in requests[1]['snapshots'][-1]['error']
assert all(not r['snapshots'][-1]['partial_answer'] for r in requests)
protected=load('protected-manifest.json')
integrity={'files':len(protected),'changed':[p for p,h in protected.items() if not (ROOT/p).exists() or sha(ROOT/p)!=h]}
integrity['status']='PASS' if not integrity['changed'] else 'FAIL'
changed=['backend/model.py','rag/analytics.py','tests/test_claim_ids.py','tests/test_measurement_analytics.py']
traces=[json.loads(line) for line in (OUT/'gemma/trajectories.jsonl').read_text(encoding='utf-8').splitlines()]
timings=[{'case':r['case'],'seconds':r['seconds'],'state':r['snapshots'][-1]['state'],
 'stage':r['snapshots'][-1]['stage'],'error_code':r['snapshots'][-1]['error_code'],
 'error':r['snapshots'][-1]['error'],'completion':r['snapshots'][-1]['completion']} for r in requests]
activation=[r'Set-Location C:\Users\ashek\Desktop\SovereignAI\frontend\llama-ui','npm.cmd run build',
 r'Set-Location C:\Users\ashek\Desktop\SovereignAI',r'.\stop-workbench.ps1',r'.\start-workbench.ps1',
 'Open http://127.0.0.1:8088/ and reload the application.']
cases=[{'case':name,'production_status':'NOT_VERIFIED','reason':'Awaiting user-controlled activation of the final staged source and frontend build.'}
 for name in ['KPR overview','missing rationale','exact-ID calculation','missing ID/file','cancellation during generation','history reopening']]
report={'status':'PARTIAL','date':'2026-10-09','production_activation':{'status':'NOT_VERIFIED','automatically_restarted':False,
 'observed_backend_pid':3712,'observed_backend_start_local':'2026-10-09 10:43:57 Asia/Calcutta',
 'reason':'Observed backend predates final staging fixes and this follow-up; on-disk files do not attest loaded revisions.',
 'user_activation_steps':activation},'production_acceptance':cases,
 'production_readonly_checks':{'health':'PASS','backend_ready':'PASS','documents_available':7,
 'gemma_runtime_identity':'PASS: observed llama-b11132 process, gemma-4-E2B-it-Q4_K_M.gguf, sovereign-rag, 16384 context, port 8087',
 'production_ui':'NOT_VERIFIED after final activation','receipt':str(OUT/'production-readonly-inspection.json'),'process_receipt':str(OUT/'observed-processes.json')},
 'saved_revision_inspection':load('revision-inspection.json'),
 'changed_files':[{'path':p,'sha256':sha(ROOT/p)} for p in changed],
 'added_experiment_files':['experiments/universal_skill/lifecycle_followup.py','experiments/universal_skill/lifecycle_followup_report.py'],
 'isolated_acceptance':{'actual_uploaded_workbook':{'status':'PASS','identifier':'24ALR051','source_receipts':str(OUT/'authorized-source-receipts.json'),
 'sheet':'All','source_row':group['included'][0]['row'],'marks':marks,'independent_raw_total':expected,'returned_raw_total':group['value'],
 'interpretation':'Raw WAT/CAT sum only; no weighted grade, pass policy, maximum or percentage inferred.'},
 'missing_identifier':'PASS: source-bound absence stops before model table planning; truthful needs_input error, no inferred measurements.',
 'missing_file':'PASS: unavailable authorized filename is reported; no answer fabricated.',
 'invalid_assessment_id':'PASS: genuine model review mutated in isolated harness; generation_format failed terminal; helpful error and draft cleared.',
 'missing_assessment_id':'PASS: genuine model review mutated in isolated harness; generation_format failed terminal; helpful error and draft cleared.',
 'production_equivalence':'NOT_VERIFIED until user activates and repeats UI cases.'},
 'error_handling_change':'Existing claim ID contract and generation_format code retained. Failed assessment now explains withholding, retry action and distinction from source absence. No bypass or extra repair.',
 'missing_record_change':'Observed absent exact identifier previously fell to table planner and failed Ordering requires selection or grouped aggregation after 48.71 s. Existing deterministic measurement compiler now reports verified record absence before fallback.',
 'timing_evidence':timings,'full_request_traces':str(OUT/'isolated-live-requests.json'),
 'raw_model_calls':str(OUT/'gemma/trajectories.jsonl'),
 'model_call_metrics':[{'question':t['question'],'run_id':t['run_id'],'seconds':t['seconds'],
 'calls':[{'stage':c.get('stage'),'seconds':c.get('seconds'),'usage':c.get('usage'),'gemma_profile_verified':c.get('gemma_profile_verified')} for c in t.get('model_calls',[])]} for t in traces],
 'cold_measurements':{'status':'NOT_VERIFIED','reason':'Shared resident Gemma was not unloaded or restarted. Measurements are warm/shared-runtime samples.'},
 'regressions':{'backend':{'passed':252,'log':str(OUT/'backend-regressions-final.log')},
 'frontend':{'passed':728,'files':61,'log':str(OUT/'frontend-regressions.log')},
 'frontend_build':'Existing staged build/source unchanged; production rebuild is user-executed.'},
 'protected_integrity':integrity,'training_started':False,'RUN_TRAIN':False,
 'rollback':{'prior_checkpoint':str(OLD/'rollback'),'followup_checkpoint':str(OUT/'rollback'),
 'old_receipts_unchanged':True,'note':'Do not reset the dirty repository. Restore only matching checkpoint files after checking for later edits.'},
 'limitations':['All six final production UI acceptance cases require activation and remain NOT_VERIFIED.',
 'Actual workbook checked in an isolated Workbench copy fetched read-only from the active authorized source. Production data was not changed.',
 'Fault tests are controlled mutations of real model outputs, not naturally occurring reviewer ID errors.',
 'Cancellation during generation was not repeated in production; previous staging verification cancellation is separate evidence.',
 'Model weight hash was not recomputed; process/registered profile observed. No model weights, dataset, retrieval baseline or frozen scores modified.',
 'The initial TestClient request used a non-localhost host and failed the existing host restriction; the successful rerun used localhost, with the failed receipt preserved.'],
 'evidence_directory':str(OUT)}
(ROOT/'rag-lifecycle-production-readiness-report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
notes=['# SovereignAI RAG lifecycle activation handoff','','Production acceptance: **NOT_VERIFIED**. No production restart or model unload was performed.',
 '', 'The final follow-up fixes retain the existing architecture and evidence gates. Incomplete/invalid assessment IDs now produce a truthful verification error, with the draft withheld and a retry action. An absent exact source identifier now returns record absence before the table-planner fallback.',
 '', 'The actual authorized workbook independently confirms **24ALR051 raw WAT/CAT total = 125** (25 + 6 + 12 + 4 + 26 + 32 + 20), sheet All, source row '+str(group['included'][0]['row'])+'. Isolated executor output matches every cell. This is not a weighted grade or pass result.',
 '', 'Regression checks: **252 backend tests**, **728 frontend tests**. '+str(len(protected))+' protected file hashes unchanged, including training, benchmark receipts and the earlier rollback. RUN_TRAIN=False.',
 '', '## User-controlled activation','```powershell',*activation[:-1],'```',activation[-1],
 '', 'After activation, repeat the six cases in the actual production UI: KPR overview, missing rationale, exact-ID calculation, missing ID/file, cancellation during generation and history reopening. Verify each final answer/error, terminal status and cleared loading/Stop control. Production PID 3712 observed here started before the final staging corrections, so its loaded code is not accepted.',
 '', 'No cold sample was fabricated. Full request snapshots, model call timing/token usage, original-source hash receipts and before/after evidence are preserved in `'+str(OUT)+'`.',
 '', 'Machine-readable report: `rag-lifecycle-production-readiness-report.json`. Earlier report and rollback remain unchanged.']
(ROOT/'RAG_ACTIVATION_HANDOFF.md').write_text('\n'.join(notes),encoding='utf-8')
print(json.dumps({'status':report['status'],'production_activation':'NOT_VERIFIED','workbook_total':expected,'integrity':integrity,'timings':[(t['case'],round(t['seconds'],3)) for t in timings]}))
