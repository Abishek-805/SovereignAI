"""Evidence-bound interim/final aggregates. No model judging or code execution."""
import ast
import csv
import json
from pathlib import Path
import statistics
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'benchmarks/model-comparison'
MODELS=('coder','granite','mini-coder','qwen3.5')

def symbols(files):
    result=set()
    for name,text in files.items():
        if not name.endswith('.py'):continue
        try:
            tree=ast.parse(text)
            result.update(name+':'+n.name for n in ast.walk(tree) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)))
        except SyntaxError:pass
    return result

def inspect(row):
    result=row['result']
    events=result['events']
    observations=[e['observation'] for e in events if 'observation' in e]
    validations=[e['observation'] for e in events if e.get('action',{}).get('action')=='finish' and 'observation' in e]
    errors=[o['tool_error'] for o in observations if 'tool_error' in o]
    reason=result['reason']
    bodies=[c.get('http_error_body','') for c in row['calls']]
    if result['state']=='READY_FOR_REVIEW':
        status='PASS'; failure=None
        if not validations or validations[-1].get('docker_executed') is not True or validations[-1].get('exit_code')!=0:
            status='BLOCKED'; failure='VALIDATION'
    else:
        status='BLOCKED' if result['state']=='BLOCKED' else 'FAIL'
        if 'deadline' in reason.lower() or 'timeout' in reason.lower():failure='TIMEOUT'
        elif any('context' in b.lower() or 'exceed' in b.lower() for b in bodies):failure='CONTEXT_ASSEMBLY'
        elif 'HTTPStatusError' in reason:failure='ENVIRONMENT'
        elif 'Docker' in reason or 'sandbox' in reason.lower():failure='SANDBOX'
        elif errors and any('JSON' in e or 'schema' in e or 'Patch base' in e for e in errors):failure='ACTION_FORMAT'
        elif result['counts']['repair_attempts']>0:failure='REPAIR'
        elif any(o.get('exit_code',0)!=0 for o in validations):failure='CODE_GENERATION'
        else:failure='OTHER'
    actions=[e['action'] for e in events if 'action' in e]
    repeated=sum(actions[i]==actions[i-1] for i in range(1,len(actions)))
    return {'status':status,'primary_failure':failure,'classification_method':'evidence rules; requires semantic audit',
            'validation':validations[-1] if validations else None,
            'file_reads':[a['path'] for a in actions if a['action']=='read_file'],
            'repeated_adjacent_actions':repeated,'tool_errors':errors,
            'removed_symbols':sorted(symbols(row['starting_files'])-symbols(result['files'])),
            'removed_files':row['removed_files'],
            'repair_recovery':status=='PASS' and result['counts']['repair_attempts']>0}

def main():
    OUT.mkdir(exist_ok=True)
    aggregates=[]
    for model in MODELS:
        rows=[]
        for path in sorted((OUT/'fixed-40'/model).glob('*.json')):
            if path.stem.endswith('-trajectory') or path.name=='progress.json':continue
            row=json.loads(path.read_text())
            if 'result' not in row:continue
            row['audit']=inspect(row)
            rows.append(row)
        (OUT/(model+'-review.json')).write_text(json.dumps({'rows':rows,'independent_semantic_review_complete':False},indent=2))
        statuses={s:sum(r['audit']['status']==s for r in rows) for s in ('PASS','PARTIAL','FAIL','BLOCKED')}
        calls=sum(r['result']['counts']['model_calls'] for r in rows)
        repairs=sum(r['result']['counts']['repair_attempts'] for r in rows)
        rss=[r['resources']['worker_peak_rss_bytes'] for r in rows if r.get('resources',{}).get('worker_peak_rss_bytes')]
        gpu=[r['resources']['gpu_peak_used_mib'] for r in rows if r.get('resources',{}).get('gpu_peak_used_mib')]
        aggregates.append({'model':model,'completed':len(rows),**statuses,
            'completion_rate_percent':round(statuses['PASS']/40*100,2),
            'median_latency_seconds':statistics.median(r['result']['elapsed_seconds'] for r in rows) if rows else None,
            'model_calls':calls,'repairs':repairs,'peak_worker_ram_bytes':max(rss) if rss else None,
            'peak_device_vram_mib':max(gpu) if gpu else None,
            'resource_measured_tasks':len(rss),
            'repair_recoveries':sum(r['audit']['repair_recovery'] for r in rows)})
    execution_complete=all(r['completed']==40 for r in aggregates)
    summary={'status':'INCOMPLETE','execution_complete':execution_complete,'semantic_audit_complete':False,
             'winner':None,'production_changed':False,'models':aggregates}
    (OUT/'summary.json').write_text(json.dumps(summary,indent=2))
    with (OUT/'summary.csv').open('w',newline='') as file:
        writer=csv.DictWriter(file,fieldnames=list(aggregates[0])); writer.writeheader(); writer.writerows(aggregates)
    lines=['# Fixed-kernel model comparison','', 'STATUS: INCOMPLETE','',
           'No winner selected. Raw outcomes are retained; classifications still require answer-bound semantic review.', '',
           '| Model | Coverage | PASS | PARTIAL | FAIL | BLOCKED | Completion / 40 | Median seconds | Calls | Repairs |',
           '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    for r in aggregates:
        lines.append(f"| {r['model']} | {r['completed']}/40 | {r['PASS']} | {r['PARTIAL']} | {r['FAIL']} | {r['BLOCKED']} | {r['completion_rate_percent']}% | {r['median_latency_seconds']} | {r['model_calls']} | {r['repairs']} |")
    lines+=['','Unexecuted tasks are not counted as failures. Completion percentages use the required 40 tasks; interim rates are not rankings.',
            '', 'The first six Coder records lack resource samples and exact HTTP response bodies. Their valid outcomes are retained, with missing observations explicitly reported. They are not silently rerun.',
            '', 'GPU memory is sampled device-wide every two seconds; brief peaks may be missed. Published model benchmark scores are not used.',
            '', 'Kernel versus old-workflow superiority cannot be established by this model-only comparison. A matched old-workflow arm is required.',
            '', 'Next: finish 160 executions, audit every failed/partial trajectory, check oracle adequacy and paired outcomes, then select a candidate only if supported.']
    (OUT/'report.md').write_text('\n'.join(lines)+'\n')

if __name__=='__main__':main()
