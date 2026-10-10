"""Independent numeric/contract audit; factual entailment requires saved human review."""
import json,math,statistics,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'evidence/rag-final-comparison/20261009'
def load(path):return json.loads(path.read_text(encoding='utf-8'))
def save(path,value):path.write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
def same(a,b):
    try:return math.isclose(float(a),float(b),rel_tol=1e-9,abs_tol=1e-9)
    except (TypeError,ValueError):return a==b
def check(row,oracle):
    result=row.get('tool_result',{});plan=row.get('effective_operation',{});correct=False;contract=False
    if oracle.get('action')=='calculate':return same(result.get('result'),oracle['value']),row.get('understanding',{}).get('action')=='calculate'
    operation=oracle.get('operation')
    if not operation:return None,None
    metric=oracle.get('metric',operation);column=oracle.get('column')
    if oracle.get('groups'):
        observed={str(next(iter(group['keys'].values()))):group['metrics'][0]['value'] for group in result.get('groups',[])}
        correct=set(observed)==set(oracle['groups']) and all(same(observed[k],v) for k,v in oracle['groups'].items())
        contract=plan.get('group_by')==oracle['group_by'] and plan.get('metrics')==[{'operation':metric,'column':column}] and not plan.get('filters')
    elif operation=='select' and oracle.get('limit'):
        records=result.get('records',[])
        if result.get('operation')=='aggregate':
            records=[{**group['keys'],'Score':group['metrics'][0]['value']} for group in result.get('groups',[])]
        wanted=oracle.get('records',oracle.get('rows'))
        correct=len(records)==len(wanted) and all(all(same(record.get(k),v) for k,v in target.items() if k in {'ID','Score'}) for record,target in zip(records,wanted))
        contract=plan.get('operation')=='select' and plan.get('order_by')==oracle.get('order_by',[oracle.get('sort')]) and plan.get('limit')==oracle['limit'] and not plan.get('filters')
    elif operation=='select':
        records=result.get('records',[])
        correct=len(records)==1 and records[0].get('ID')==oracle['entity'] and same(records[0].get(column),oracle['value'])
        contract=plan.get('operation')=='select' and plan.get('filters')==[{'column':'ID','operator':'in','value':[oracle['entity']]}]
    else:
        actual=result.get('value')
        metrics=result.get('metrics',[])
        if len(metrics)==1:actual=metrics[0]['value']
        correct=same(actual,oracle['value'])
        contract=(plan.get('operation')==operation or plan.get('operation')=='aggregate' and plan.get('metrics')==[{'operation':operation,'column':column}]) and not plan.get('group_by')
        requested=oracle.get('filters',[oracle['filter']] if oracle.get('filter') else [])
        filters=plan.get('filters',[])+plan.get('criteria',[])
        if requested:
            contract=contract and len(filters)==1 and filters[0]['column']==requested[0]['column'] and filters[0]['operator'] in {'eq','in'} and filters[0]['value'] in ['Pass',['Pass']]
        else:contract=contract and not filters
    contract=bool(contract and plan.get('table')=='T1')
    return bool(correct),contract


def main():
    cases=load(OUT/'suite.json');review=load(OUT/'semantic-review.json');arms={};audit=[]
    for arm in ['CURRENT_BASELINE','E5_QDRANT_HYBRID']:
        raw=load(OUT/(arm+'.json'))
        if arm=='E5_QDRANT_HYBRID':raw=[r for r in raw if r['status']=='COMPLETED']+load(OUT/(arm+'-recovery.json'))
        byid={r['id']:r for r in raw};assert len(raw)==len(byid)==len(cases) and set(byid)=={c['id'] for c in cases}
        rows=[]
        for case in cases:
            row=byid[case['id']];numeric,operation=check(row,case['oracle'])
            judgment=review[arm].get(case['id'])
            if numeric is None:
                assert judgment is not None,'Missing independent semantic review'
                verdict=judgment['status']
            else:verdict='PASS' if numeric and row.get('final',{}).get('status')=='answered' else 'FAIL'
            source_ids={s['chunk_id'] for s in row.get('evidence',[])}
            bound=all(s['chunk_id'] in source_ids for s in row.get('final',{}).get('sources',[]))
            phase={'UNDERSTANDING':row.get('understanding',{}).get('action')==case['oracle'].get('action','search_documents'),
                'SCOPE':all(p['document_id'] in case['scope'] for p in row.get('evidence',[])) if case['scope'] else True,
                'RETRIEVAL':'UNKNOWN_FULL_RELEVANCE_ORACLE', 'OPERATION':operation if operation is not None else 'NOT_APPLICABLE',
                'TOOL':bool(row.get('tool_calls') or row.get('effective_operation') and 'execution_start' in row['timestamps']) if numeric is not None else 'NOT_APPLICABLE',
                'EXECUTION':numeric if numeric is not None else 'NOT_APPLICABLE',
                'EVIDENCE':judgment.get('evidence_supported','UNKNOWN') if judgment else numeric,
                'FINAL_ANSWER':verdict,'CITATION_BINDING':bound}
            rows.append({'id':case['id'],'verdict':verdict,'stages':phase,'numeric_correct':numeric,'operation_contract_correct':operation,'semantic_review':judgment})
        def latency(a,b):return statistics.median(r['timestamps'][b]-r['timestamps'][a] for r in raw if a in r['timestamps'] and b in r['timestamps'])
        summary={'cases':len(rows),'PASS':sum(r['verdict']=='PASS' for r in rows),'PARTIAL':sum(r['verdict']=='PARTIAL' for r in rows),'FAIL':sum(r['verdict']=='FAIL' for r in rows),
            'operation_pass':sum(r['operation_contract_correct'] is True for r in rows),'operation_cases':sum(r['operation_contract_correct'] is not None for r in rows),
            'numeric_result_pass':sum(r['numeric_correct'] is True for r in rows),'numeric_cases':sum(r['numeric_correct'] is not None for r in rows),
            'median_seconds':{'pre_retrieval':latency('understanding_complete','retrieval_start')+statistics.median(r['timestamps']['understanding_complete'] for r in raw if 'understanding_complete' in r['timestamps']),
                'retrieval':latency('retrieval_start','retrieval_complete'),'operation_planning':latency('retrieval_complete','execution_start'),
                'execution':latency('execution_start','execution_complete'),'generation':latency('generation_start','generation_complete'),'total':statistics.median(r['total_seconds'] for r in raw)},
            'model_calls':sum(r['model_calls'] for r in raw),'tool_calls':sum(max(r['tool_calls'],int(bool(r.get('effective_operation')) and 'execution_start' in r['timestamps'])) for r in raw),'retrieval_calls':sum(r['retrieval_calls'] for r in raw),
            'repairs':sum(r.get('final',{}).get('checks',{}).get('repair',{}).get('attempts',0) for r in raw),
            'max_sampled_rss_bytes':max(r['rss'] for r in raw),'full_chunk_recall':'UNKNOWN','cpu_utilization':'NOT_MEASURED','rows':rows}
        arms[arm]=summary
        table_rows=[r for r in raw if r.get('effective_operation')]
        factual_rows=[r for r in raw if not r.get('effective_operation') and r.get('understanding',{}).get('action')=='search_documents']
        summary['median_seconds']['pre_retrieval']=statistics.median(r['timestamps']['retrieval_start'] for r in raw if 'retrieval_start' in r['timestamps'])
        summary['median_seconds']['table_operation_planning']=statistics.median(r['timestamps']['execution_start']-r['timestamps']['retrieval_complete'] for r in table_rows)
        summary['median_seconds']['factual_generation']=statistics.median(r['timestamps']['generation_complete']-r['timestamps']['generation_start'] for r in factual_rows if 'generation_start' in r['timestamps'])
    result={'status':'RAG_BLOCKED','decision':'KEEP_CURRENT_BASELINE','selected':'CURRENT_BASELINE','arms':arms,'paired_cases':len(cases),
        'environment_incident':load(OUT/'environment-incident.json'),'RUN_TRAIN':False,'full_training':'NOT_STARTED',
        'limitations':['One run per request; recovered runtime changes cache state; no causal speed/superiority claim.',
            'No complete graded chunk-relevance oracle; retrieval recall UNKNOWN.',
            'Controlled existing-model-method diagnostic, not full Workbench/Chat end-to-end acceptance.',
            'Follow-up antecedent evidence replayed through each retrieval arm; no fabricated facts.',
            'RSS samples are not transient peaks; no measured CPU utilization.',
            'Raw repairs field was zero; derived report uses actual checks.repair.attempts without rewriting raw.',
            'Raw tool_calls omitted rejected table execution; derived report counts that actual invocation without rewriting raw.']}
    probe_path=OUT/'contract-repair-final-probes.json'
    if probe_path.exists():
        probes=load(probe_path);cases_by_id={c['id']:c for c in cases}
        result['post_comparison_probes']=[{'id':r['id'],'numeric_correct':check(r,cases_by_id[r['id']]['oracle'])[0],
            'operation_contract_correct':check(r,cases_by_id[r['id']]['oracle'])[1],'status':r['status']} for r in probes]
        result['post_comparison_source']=load(OUT/'contract-repair-final-manifest.json')
    save(ROOT/'rag-final-results.json',result)
    save(ROOT/'rag-production-config.json',{'decision':'KEEP_CURRENT_BASELINE','retrieval':'CURRENT_BASELINE','embedding':'bge-small-en-v1.5','index':'existing SQLite/vector/FTS5','fusion':'RRF',
        'worker':'Qwen3.5-4B','E5_integrated':False,'deployment':'HOLD_RAG_BLOCKED','RUN_TRAIN':False,'rollback':'evidence/rag-final-comparison/20261009/rollback'})
    lines=['# Final RAG correction and controlled comparison','', '**RAG_BLOCKED — KEEP_CURRENT_BASELINE. Full training not started; RUN_TRAIN=False.**','',
        'All 33 requests per arm have a valid captured attempt. Environment-interrupted attempts are preserved separately and excluded from model failure counts. No completed valid case was retried.',
        '', '| Stack | PASS | PARTIAL | FAIL | Numeric result | Strict operation | Median total seconds | Sampled RSS GiB |', '|---|---:|---:|---:|---:|---:|---:|---:|']
    for name,v in arms.items():lines.append(f"| {name} | {v['PASS']} | {v['PARTIAL']} | {v['FAIL']} | {v['numeric_result_pass']}/{v['numeric_cases']} | {v['operation_pass']}/{v['operation_cases']} | {v['median_seconds']['total']:.3f} | {v['max_sampled_rss_bytes']/2**30:.3f} |")
    lines+=['','## Decision and remaining gates','',
        'E5 without a reranker does not resolve operation-contract or unsupported causal explanation failures. The final evidence does not justify replacing the current retrieval stack. The corrected current stack remains the candidate; deployment is held until all gates pass.',
        '','The scope regression passes. Version-bound handoff rejects stale/out-of-scope IDs and successfully reuses the version evidence. The rationale follow-up still invents justification absent from the source. During the frozen comparison, filtered COUNT lost its predicate and declared selections were incorrectly compiled as aggregates. These compiler defects were repaired after comparison, retaining the independent population and threshold validation paths. The original comparison scores remain unchanged.',
        '','## Post-comparison targeted compiler acceptance','',json.dumps(result.get('post_comparison_probes',[]),indent=2),
        '', 'These are separate acceptance probes, not a second retrieval comparison or a revised score. They do not resolve the factual rationale or preview-without-evidence failures. No full product/browser acceptance is inferred.',
        '','## Measurement','',json.dumps({k:{x:y for x,y in v.items() if x not in {'rows'}} for k,v in arms.items()},indent=2),
        '','## Independent semantic review','',json.dumps(review,indent=2),
        '','## Limitations','',*['- '+x for x in result['limitations']],
        '','## Training handoff','', 'Not advanced: RAG_COMPLETE prerequisite failed. Existing measured 4096 dataset-envelope readiness is preserved. Independently reviewed Base baseline remains a separate required gate. No training package is represented as ready and no training, adapter, merge or GGUF operation was performed.']
    (ROOT/'rag-final-report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    (ROOT/'training-handoff-report.md').write_text('# Training handoff\n\n**BLOCKED — RUN_TRAIN=False.**\n\nRAG_COMPLETE has not been achieved. Per the conditional handoff instruction, final training configuration verification and final package release are deferred. The existing 710-record dataset and split 579/65/66 remain untouched. Existing measured TRAINING_READY_REAL_DATA_4096 receipts remain valid for their tested workload envelope; they are not a full-training authorization. Preserve 131 Base predictions and complete source-bound independent semantic/Docker/stateful baseline review before enabling training.\n\nNo full training, production adapter, merge, GGUF or deployment.\n',encoding='utf-8')
    print({k:(v['PASS'],v['PARTIAL'],v['FAIL']) for k,v in arms.items()})


if __name__=='__main__':main()
