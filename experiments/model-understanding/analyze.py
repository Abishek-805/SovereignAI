"""Explicit structured oracles plus manual source-bound answer judgments."""
import collections,hashlib,json,math,statistics
from pathlib import Path
OUT=Path(__file__).resolve().parent
def load(p):return json.loads(p.read_text(encoding='utf-8'))
def save(p,v):p.write_text(json.dumps(v,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
def equal(a,b):
 try:return math.isclose(float(a),float(b),rel_tol=1e-9,abs_tol=1e-9)
 except (TypeError,ValueError):return a==b
def measure(row):
 for event in row['model_events']:
  schema=(event.get('schema') or {}).get('json_schema',{})
  if schema.get('name')=='query_measure':
   return json.loads(event['public_choices'][0]['content'])
 return None
FAILURES={
 'qwen':{
  'long':('UNDERSTANDING_FAILURE','Answers from partial planning preview and wrongly infers P-888 is absent; never retrieves.'),
  'followup-1':('RETRIEVAL_FAILURE','Bare follow-up is not expanded and previous evidence is not reused; retrieved README passages omit the Python requirement.'),
  'followup-2':('FINAL_ANSWER_FAILURE','Asked why the version is required, but discusses absence of the version rather than absence of its rationale.'),
  'indirect-total':('OPERATION_FAILURE','Correct SUM but adds unrelated COUNT and grouping by ID. Correct grand total does not validate this plan.'),
  'arithmetic-2':('FINAL_ANSWER_FAILURE','Calculator returns 90 and both public answer drafts are factually correct. Diagnostic rag.answer literal-number validator rejects 20 from the request because tool text contains 0.2 instead. This is a diagnostic presentation-contract mismatch, not calculator/model arithmetic failure.'),
  'group-count':('OPERATION_FAILURE','Invents nonexistent cohort C and emits three identical IN(A,B,C) criteria. Executor produces three counts of 8; model falsely labels them A/B/C instead of source-bound counts A=4/B=4.'),
  'top-three':('OPERATION_FAILURE','Public intent says select but also requests unrelated COUNT/SUM grouped by ID; compiler returns aggregate. No deterministic ORDER BY/LIMIT contract exists. Model drafts correct top three from full grouped values, but delivered response fails numeric validation of 3.'),
  'qa-missing':('UNDERSTANDING_FAILURE','Chooses answer and uses partial planning metadata rather than requested evidence workflow. Birth-date refusal is factually correct, but positive claims about bays/supervisor/network policy are uncited and no evidence was retrieved.'),
  'conflict':('SCOPE_FAILURE','Software filename narrowing excludes SOP-A; model chooses SOP-B 9.0 and explicitly denies the conflict. Not attributable to a model-selected document scope.')},
 'granite':{
  'direct':('FINAL_ANSWER_FAILURE','Planning/retrieval correct; final-generation HTTP request times out after 120 seconds. No completed final draft. Runtime subsequently serves other cases.'),
  'pdf_page':('FINAL_ANSWER_FAILURE','Correct 30-day fact but omits required citation on initial and repair drafts.'),
  'long':('FINAL_ANSWER_FAILURE','Retrieves correct long-source passage and states 21 days, but omits citation even after repair.'),
  'paraphrase':('FINAL_ANSWER_FAILURE','Correct comparison values but omits required citations on both drafts.'),
  'followup-1':('RETRIEVAL_FAILURE','Same unexpanded follow-up/evidence-reuse gap as Qwen; rejects previously established version.'),
  'indirect-total':('OPERATION_FAILURE','Public measure invents pass outcome, numeric rule 0 and follow-up despite a simple total. Compiler ignores these fields for SUM and gets 238; model omits citations on both answer drafts.'),
  'id-p101':('FINAL_ANSWER_FAILURE','Correct observed 8.2 mm/s but no citation, including repair.'),
  'id-m2':('FINAL_ANSWER_FAILURE','Correct observed 78 C but no citation, including repair.'),
  'id-S03':('OPERATION_FAILURE','Converts score lookup into pass COUNT using an invented threshold 25. Wrong evidence then causes incorrect abstention.'),
  'id-S06':('OPERATION_FAILURE','Converts score lookup into pass COUNT using an invented threshold 25. Wrong evidence then causes incorrect abstention.'),
  'arithmetic-0':('OPERATION_FAILURE','Selects calculate but puts numeric prose in response and omits expression. Safe calculator rejects missing argument.'),
  'arithmetic-1':('OPERATION_FAILURE','Selects calculate but omits expression; prose arithmetic is not deterministic execution evidence.'),
  'arithmetic-2':('OPERATION_FAILURE','Selects calculate but omits expression; executor rejects before calculation.'),
  'arithmetic-3':('OPERATION_FAILURE','Missing expression; unexecuted plan prose also incorrectly computes 85+91+74 as 150 and result 50.'),
  'table-count':('OPERATION_FAILURE','Invents Team-X, pass rule 25 and grouping; source/user-bound compiler rejects population.'),
  'table-sum':('OPERATION_FAILURE','Invents pass rule 0/follow-up in public measure though effective SUM is correct. Initial correct 238 answer lacks citation; repair changes to false insufficiency.'),
  'table-average':('OPERATION_FAILURE','Copies Team-X and pass/count measure from example; compiler rejects before executor.'),
  'table-max':('OPERATION_FAILURE','Copies Team-X and pass/count measure from example; compiler rejects before executor.'),
  'filter-average':('OPERATION_FAILURE','Copies Team-X and invented numeric pass rule rather than literal Status=Pass filter.'),
  'group-count':('OPERATION_FAILURE','Copies Team-X and numeric threshold; compiler rejects instead of grouping actual Cohorts A/B.'),
  'top-three':('OPERATION_FAILURE','Copies Team-X and pass count instead of ordered top-three selection; rejected.'),
  'conflict':('SCOPE_FAILURE','Software scope omits SOP-A. Answer gives only 9.0 and misses requested disagreement.'),
  'compare-documents':('FINAL_ANSWER_FAILURE','Correct 8.2/7.1 comparison but no source labels on initial or repair draft.')}}
DELIVERED_BAD={
 'qwen':{'long','followup-1','followup-2','arithmetic-2','group-count','top-three','conflict','qa-missing'},
 'granite':set(FAILURES['granite'])}
INITIAL_BAD={
 'qwen':{'long','followup-1','followup-2','group-count','conflict'},
 'granite':{'direct','followup-1','id-S03','id-S06','arithmetic-0','arithmetic-1','arithmetic-2','arithmetic-3','table-count','table-average','table-max','filter-average','group-count','top-three','conflict'}}
def score(row,name):
 o=row['oracle'];plan=row.get('task_plan',{});table=row.get('table_plan') or {};public=measure(row);tools=row['tool_observations']
 action_ok=plan.get('action')==o['action'];requested_table='operation' in o;is_calc=row['category']=='arithmetic'
 declared=None
 if requested_table:declared=public.get('operation') if public else None
 elif is_calc:declared='calculate' if plan.get('expression') else None
 op_ok=(declared==o.get('operation')) if requested_table else bool(plan.get('expression')) if is_calc else None
 strict=(row['id'] not in FAILURES[name] or FAILURES[name][row['id']][0]!='OPERATION_FAILURE') if requested_table or is_calc else None
 result_ok=None
 if requested_table or is_calc:
  result_ok=False
  if tools:
   value=tools[0]['result']
   if is_calc:result_ok=equal(value.get('result'),o['value'])
   elif 'value' in o:
    actual=value.get('value')
    if value.get('operation')=='aggregate':actual=next((m['value'] for m in value['metrics'] if m['operation']==o['operation'] and m.get('column')==o.get('column')),None)
    if o['operation']=='select':actual=next((r.get(o['column']) for r in value.get('records',[]) if r.get('ID')==o['entity']),None)
    result_ok=equal(actual,o['value'])
   elif 'groups' in o:
    actual={g['keys'].get('Cohort'):g['metrics'][0]['value'] for g in value.get('groups',[]) if g.get('metrics')}
    result_ok=actual==o['groups']
   elif 'rows' in o:
    actual=[{'ID':r.get('ID'),'Score':float(r.get('Score',0))} for r in value.get('records',[])]
    expected=[{'ID':r['ID'],'Score':r['Score']} for r in o['rows']]
    result_ok=actual==expected and table.get('limit')==3 and bool(table.get('sort'))
 first=FAILURES[name].get(row['id']);final_ok=row['id'] not in DELIVERED_BAD[name]
 abstention=None
 if o.get('abstain'):abstention=row['id'] not in INITIAL_BAD[name]
 evidence_ok=None
 if requested_table or is_calc:evidence_ok=result_ok
 else:
  qrels=load(OUT.parents[1]/'evidence/rag-fast-comparison/20261009/qrels.json')
  relevant=qrels['grades'].get(row['id'])
  evidence=row.get('evidence',[])
  if isinstance(relevant,dict):relevant=list(relevant)
  if relevant:evidence_ok=set(relevant).issubset({p['chunk_id'] for p in evidence})
  elif row['id']=='followup-1':evidence_ok=any('Install **Python 3.12**' in p['text'] for p in evidence)
  elif o.get('abstain'):evidence_ok=bool(evidence)
  elif row['id']=='version-current':evidence_ok=any(p['document_id']=='policy-current' for p in evidence)
  elif o.get('required_documents'):evidence_ok=set(o['required_documents']).issubset({p['document_id'] for p in evidence})
  else:evidence_ok=bool(evidence)
 return {'id':row['id'],'category':row['category'],'workflow_understanding':action_ok,
  'operation_extraction':op_ok,'strict_plan_semantics':strict,
  'tool_selection':action_ok if not requested_table else action_ok and row.get('raw_table_plan',{}).get('operation') not in {None,'none'},
  'retrieval_plan_accuracy':(plan.get('action')=='search_documents')==(o['action']=='search_documents'),
  'model_document_scope_accuracy':None,'scope_note':'Worker contract exposes focused/overview, not document IDs or version constraints. Software-selected scope recorded separately; no model attribution.',
  'deterministic_result_correct':result_ok,'executor_returned':bool(tools) if requested_table or is_calc else None,
  'evidence_coverage':evidence_ok,
  'initial_answer_semantic_correct':row['id'] not in INITIAL_BAD[name],
  'delivered_final_answer_correct':final_ok,'correct_abstention':abstention,
  'abstention_metadata_consistent':row.get('final',{}).get('status')=='insufficient_evidence' if o.get('abstain') else None,
  'first_failure':first[0] if first else None,'review_reason':first[1] if first else 'Manually checked requested fact/value against selected source passages and independent oracle; delivered response satisfies request.',
  'public_interpretation':{'intent':plan.get('action'),'requested_deliverable':None,'entities':public.get('entity_values') if public else None,
   'attributes':public.get('score_columns') if public else None,'document_scope':plan.get('document_scope'),'version_constraint':None,
   'operation':declared,'filter':table.get('filters'),'grouping':public.get('group_by') if public else None,'aggregation':public.get('metrics') if public else None,
   'comparison_requirement':table.get('comparison_requested'),'evidence_requirement':o['action']=='search_documents'},
  'actual_model_calls':row['model_calls']+int(row.get('error',{}).get('code')=='model_timeout'),
  'actual_repair_attempts':row.get('final',{}).get('checks',{}).get('repair',{}).get('attempts',0),
  'original_trajectory_retries_field':row['retries'],'retry_field_note':'Original retries field is zero; actual bounded answer repair count derived from saved checks, original evidence preserved.'}
def rate(items,key):
 values=[r[key] for r in items if r[key] is not None]
 return {'passed':sum(v is True for v in values),'total':len(values),'rate':sum(v is True for v in values)/len(values) if values else None}
def main():
 prereg=load(OUT/'preregistration.json');assert hashlib.sha256((OUT/'suite.json').read_bytes()).hexdigest()==prereg['suite_sha256']
 summaries={};reviews={};latency={};failures={};paired={}
 for name in ['qwen','granite']:
  rows=load(OUT/(name+'-results.json'));assert len(rows)==30 and len({r['id'] for r in rows})==30
  judgments=[score(r,name) for r in rows];reviews[name]=judgments
  keys=['workflow_understanding','model_document_scope_accuracy','retrieval_plan_accuracy','operation_extraction','strict_plan_semantics','tool_selection','evidence_coverage','executor_returned','deterministic_result_correct','initial_answer_semantic_correct','delivered_final_answer_correct','correct_abstention']
  summaries[name]={key:rate(judgments,key) for key in keys}
  summaries[name]['arithmetic']=rate([r for r in judgments if r['category']=='arithmetic'],'deterministic_result_correct')
  summaries[name]['aggregation']=rate([r for r in judgments if r['category']=='aggregation'],'deterministic_result_correct')
  summaries[name]['errors']=sum(r['status']=='ERROR' for r in rows)
  summaries[name]['model_calls_total']=sum(r['actual_model_calls'] for r in judgments)
  summaries[name]['repair_attempts_total']=sum(r['actual_repair_attempts'] for r in judgments)
  summaries[name]['inappropriate_abstentions']=[r['id'] for r,j in zip(rows,judgments) if not r['oracle'].get('abstain') and r.get('final',{}).get('status')=='insufficient_evidence']
  summaries[name]['per_category']={c:rate([r for r in judgments if r['category']==c],'delivered_final_answer_correct') for c in sorted({r['category'] for r in judgments})}
  latency[name]={'median_seconds':{k:statistics.median(v) if (v:=[r['latency'][k] for r in rows if r['latency'][k] is not None]) else None for k in ['pre_retrieval','retrieval','tool_planning','tool_execution','final_generation','total']},
   'median_table_planning_seconds':statistics.median(r['latency']['tool_planning'] for r in rows if 'students' in next(c['scope'] for c in load(OUT/'suite.json')['cases'] if c['id']==r['id']) and r['latency']['tool_planning'] is not None),
   'total_case_seconds':sum(r['latency']['total'] for r in rows),
   'median_model_calls':statistics.median(r['actual_model_calls'] for r in judgments),
   'median_tool_calls':statistics.median(r['tool_calls'] for r in rows),'retrieval_calls_total':sum(r.get('retrieval_calls',0) for r in rows),
   'case_rows':[{'id':r['id'],'timestamps':r['timestamps_seconds'],'latency':r['latency']} for r in rows],
   'representative_peak_rss':max(r['resources_after']['rss'] for r in rows),'sampled_gpu_observations':sorted({r['resources_after']['gpu'] for r in rows if 'gpu' in r['resources_after']})}
  failures[name]={'counts':dict(collections.Counter(r['first_failure'] for r in judgments if r['first_failure'])),'cases':[r for r in judgments if r['first_failure']]}
 for a,b in zip(reviews['qwen'],reviews['granite']):
  assert a['id']==b['id'];paired[a['id']]={'qwen':a['delivered_final_answer_correct'],'granite':b['delivered_final_answer_correct']}
 save(OUT/'independent-review.json',{'method':'Manual source-bound semantic judgments of public drafts/delivered answers plus explicit structural operation/argument comparison and independently authored deterministic numeric oracles. No keyword-only scoring or reviewer model.','arms':reviews})
 save(OUT/'failure-taxonomy.json',failures);save(OUT/'latency-breakdown.json',latency)
 assert summaries['qwen']['arithmetic']['passed']==4 and summaries['granite']['arithmetic']['passed']==0
 assert summaries['qwen']['delivered_final_answer_correct']['passed']==22 and summaries['granite']['delivered_final_answer_correct']['passed']==7
 result={'status':'COMPLETE_WITH_MEASUREMENT_AND_COVERAGE_LIMITATIONS','coverage':{'qwen':30,'granite':30,'paired':30},'best_model':'Qwen3.5-4B','confidence':'Moderate for this exact configuration; insufficient for general model superiority or production readiness.','production_changed':False,'RUN_TRAIN':False,'summary':summaries,'latency':latency,'paired_outcomes':paired,'preregistration':prereg,
  'limitations':['One run per query; no reliable p95 or broad universal accuracy claim.','MIN extraction and cross-document table aggregation not covered by this capped 30-case suite; they remain NOT_TESTED. MAX, SUM, AVG, COUNT, filters, grouping and attempted top-K covered.','Existing worker contracts do not expose document IDs/version constraints or all requested interpretation fields; model scope score is UNKNOWN rather than inferred.','Top-K ordering/limit is not represented by the current table planning contract; unsupported action-space gap, not proven model incapacity.','CPU classification bypassed equally to isolate worker plans; diagnostic is not an unchanged full-production end-to-end test.','Read-only schema inspection follows baseline passage retrieval here; production table branch precedes passage retrieval. Timing labels reflect actual diagnostic order.','Calculator final prose is an explicit diagnostic extension using the fixed evidence prompt; production calculator formatting is deterministic.','Production table formatting bypassed for diagnostic model answer measurement; a source-bound computed result is provided as text and original executor payload retained.','Granite omits expressions required by existing planner grammar and copies example entities; conclusions apply to this exact shared prompt/runtime, not every Granite configuration.','Qwen warm runtime reused, Granite cold loaded; load cost and ordered-run/cache effects are separate.','Memory measurements are sampled process RSS and whole-GPU totals, not precise per-process VRAM peaks.','Original retry-count field corrected only in derived review using actual saved repair checks. Failed HTTP model call added from explicit model_timeout evidence.']}
 save(OUT/'model-understanding-comparison.json',result)
 identity=load(OUT/'model-identities.json')[0]
 save(OUT/'proposed-model-config.json',{'status':'PROPOSED_ONLY_NOT_DEPLOYED','model':identity,'context':16384,'temperature':0,'retrieval':'CURRENT_BASELINE_RAG','latency_evidence':latency['qwen'],'quality_evidence':summaries['qwen'],'known_failure_modes':failures['qwen'],'decision':'Prefer Qwen under the tested existing contracts; fix/isolate scope, evidence reuse and table plan semantics before considering RAG replacement or training.','next_experiment':'Freeze repaired scope/evidence and operation contracts; run matched end-to-end Qwen + CURRENT_BASELINE_RAG versus Qwen + E5 on a small preregistered subset, including group counts, top-K, conflict and follow-ups; do not integrate yet.'})
 lines=['# SovereignAI model understanding and tool planning comparison','',
 '**Status: 60 executions COMPLETE with measurement and coverage limitations — 30/30 Qwen, 30/30 Granite, 30 paired requests.** All raw evidence retained. One Granite final-generation timeout and ten additional rejected invalid argument cases remain results, not rerun successes. Production configuration unchanged; original Qwen process restored. RUN_TRAIN=False.',
 '', '**Preferred worker: Qwen3.5-4B under these exact existing prompts and llama.cpp b11132 runtime.** It provides a substantial advantage in valid executable arguments, deterministic result delivery and cited final answers. This is a configuration-specific worker decision, not universal model understanding or deployment approval.',
 '', '| Dimension | Qwen3.5 | Granite 4.2 |','|---|---:|---:|']
 for label,key in [('Understanding: broad workflow only','workflow_understanding'),('Model document/version scope','model_document_scope_accuracy'),('Retrieval required decision','retrieval_plan_accuracy'),('Declared operation extraction','operation_extraction'),('Strict operation/argument semantics','strict_plan_semantics'),('Tool family selection','tool_selection'),('Evidence coverage','evidence_coverage'),('Deterministic executor returned','executor_returned'),('Deterministic requested result correct','deterministic_result_correct'),('Arithmetic execution','arithmetic'),('Aggregation execution','aggregation'),('Initial answer factual semantics*','initial_answer_semantic_correct'),('Delivered final answer','delivered_final_answer_correct'),('Abstention decisions†','correct_abstention')]:
  values=[summaries[n][key] for n in ['qwen','granite']]
  lines.append('| '+label+' | '+' | '.join(f"{v['passed']}/{v['total']}" if v['total'] else 'UNKNOWN' for v in values)+' |')
 for label,key in [('Median pre-retrieval latency','pre_retrieval'),('Median actual retrieval latency','retrieval'),('Median tool planning latency','tool_planning'),('Median tool execution latency','tool_execution'),('Median final generation latency','final_generation'),('Median total latency','total')]:
  lines.append('| '+label+' | '+' | '.join(f"{latency[n]['median_seconds'][key]:.3f}s" for n in ['qwen','granite'])+' |')
 for label,key in [('Median model calls','median_model_calls'),('Median successful tool calls','median_tool_calls')]:lines.append('| '+label+' | '+' | '.join(str(latency[n][key]) for n in ['qwen','granite'])+' |')
 lines += ['', f"Table-only planning median: Qwen {latency['qwen']['median_table_planning_seconds']:.3f}s, Granite {latency['granite']['median_table_planning_seconds']:.3f}s. Overall tool-planning median is low because twenty requests need no table plan. Faster Granite median includes cases that stopped before final generation; it does not imply faster successful completion."]
 lines += ['', '*Factual semantics separate from missing citations and delivery. A correct unexecuted calculator claim is not credited. †Three expected missing-evidence cases, judged semantically; structured status consistency is recorded separately. Qwen’s birth-date refusal is factually correct but bypasses evidence retrieval and adds uncited positive facts, so delivered grounding fails.',
 '', '## What failed and where','',
 'Qwen: shallow long-document preview caused premature refusal before retrieval. Both models: unexpanded follow-up queries failed to reuse the Python requirement evidence. Both models: the conflict filename scope heuristic omitted SOP-A. This is a software scope failure, not evidence of a model-selected wrong document.',
 'Qwen correctly chose and supplied all four calculator expressions; deterministic results were 45, 90, 90 and 83.33333333333333. Granite chose the calculator family but omitted its expression in all four cases; no calculation completed. Its last unexecuted prose also incorrectly claimed the average was 50. Do not credit arithmetic prose as execution.',
 'Qwen computed COUNT=8, SUM=238, AVG=29.75 and MAX=50 correctly and filtered Pass AVG=36.4 correctly. It nevertheless invented cohort C for grouped counts, made identical combined-population predicates and mislabeled their counts. A separate total used unnecessary grouping. Granite copied Team-X and threshold 25 from an example into unrelated requests; source-bound guards correctly rejected the arguments. Two effective SUM results were correct despite invented pass-rule/follow-up fields in the public measure.',
 'Neither model executed deterministic top-three sorting. The current table contract has no ORDER BY/LIMIT representation. Qwen drafted the correct S06=50, S03=41, S05=35 from grouped observations, but this cannot validate the wrong executable plan.',
 'Granite repeatedly returned correct simple facts without [Sx] citations, including bounded repair; these were blocked. A SUM repair changed a correct uncited draft into false insufficiency. Qwen’s correct 20%-of-450 prose was blocked by the diagnostic literal-number check (20 in request, 0.2 in tool result). That is a diagnostic presentation-contract mismatch; production calculator formatting does not use this path.',
 '', '## Latency interpretation','',
 'Actual baseline vector retrieval is measured independently and is small compared with planning and generation. Table schema planning requires additional model calls after passage retrieval in this diagnostic. The complete per-case T0–T8 values prevent that model time being mislabeled embedding latency. Medians over all requests include no-retrieval arithmetic cases; table-only medians are available in latency-breakdown.json. No private reasoning was captured or used to explain delay. Timing alone does not prove internal reasoning.',
 '', '## Resources and runtime','']
 for n in ['qwen','granite']:
  lines.append(f"- {n}: sampled peak worker RSS {latency[n]['representative_peak_rss']/2**30:.3f} GiB; total case time {latency[n]['total_case_seconds']:.2f}s; {summaries[n]['model_calls_total']} model calls; {summaries[n]['repair_attempts_total']} bounded answer repairs. GPU observations: {', '.join(latency[n]['sampled_gpu_observations'])}.")
 lines += ['', 'Exact repositories, pinned revisions, model/runtime SHA-256, Apache-2.0 profile licenses, quantization Q4_K_M and runtime configuration are in model-identities.json and runtime.json. Model file hashes rechecked against existing installation records. Qwen warm load time is UNKNOWN; Granite cold load/unload timing recorded. Qwen → unload → Granite → unload → original Qwen restored, with a single heavy worker at each stage. No extra downloads or model-specific prompts.',
 '', '## Evidence and controls','',
 'Existing 41-chunk frozen corpus and valid baseline vectors reused. New students.csv (eight explicit source records) and two dated policy text fixtures are ENGINEERING_ONLY. These are isolated from the 710-record training release. Suite has 30 balanced requests and exact source-bound numerical/record oracles. Public plans and raw final drafts, source IDs, version hashes, locators, actual tool inputs/results and resources are retained in qwen-results.json and granite-results.json. No generated code was executed. No T01–T15 content or historical outcomes were inspected.',
 'Harness preparation had two signature errors before any model case executed; corrected by calling existing extract/chunk_pages correctly. Their incident receipt is preserved. Original zero retries fields are known telemetry omissions; derived reviews report actual saved repair counts without replacing raw evidence.',
 '', '## Limitations','']
 lines += ['- '+v for v in result['limitations']]
 lines += ['', '## Decision and next experiment','',
 'Freeze Qwen as the proposed worker candidate, not a deployed winner. Keep baseline RAG for now: model/plan defects and software scope/evidence reuse failures must be isolated before interpreting embedding gains. The proposed exact configuration is saved in proposed-model-config.json. The next experiment is a small preregistered paired Qwen baseline-versus-E5 end-to-end comparison after scope/evidence and operation-contract fixes, with group counts, top-K, conflict and follow-ups. No automatic secondary pass or BGE rerun was performed.',
 '', 'Training: NOT STARTED. RUN_TRAIN: FALSE. Production: UNCHANGED.']
 (OUT/'model-understanding-comparison.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
 print(json.dumps({'summary':summaries,'median_latency':{n:v['median_seconds'] for n,v in latency.items()}},indent=2))
if __name__=='__main__':main()
