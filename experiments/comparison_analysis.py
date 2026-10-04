"""Paired descriptive analysis; never substitutes for semantic signoff."""
import csv
import itertools
import json
from pathlib import Path
import statistics
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from experiments.comparison_report import inspect
OUT=ROOT/'benchmarks/model-comparison'
MODELS=('coder','granite','mini-coder','qwen3.5','old-workflow')

def main():
    tasks=json.loads((OUT/'frozen-40-task-manifest.json').read_text())
    data={}; summaries=[]
    for model in MODELS:
        folder=OUT/'old-workflow' if model=='old-workflow' else OUT/'fixed-40'/model
        data[model]={}
        review_path=OUT/(model+'-answer-bound-review.json')
        reviewed={r['task_id']:r for r in json.loads(review_path.read_text())['rows']} if review_path.exists() else {}
        for task in tasks:
            path=folder/(task['task_id']+'.json')
            if not path.exists():continue
            raw=json.loads(path.read_text())
            old=model=='old-workflow'
            status=raw['status'] if old else inspect(raw)['status']
            counts={} if old else raw['result']['counts']
            replay=OUT/'oracle-v2-replay'/model/path.name
            v2=json.loads(replay.read_text()) if replay.exists() else None
            calls=raw['calls']; resources=raw.get('resources') or {}
            usages=[c.get('usage') for c in calls if c.get('usage')]
            data[model][task['task_id']]={
                'task_id':task['task_id'],'category':task['category'],'model':model,
                'status':status,'supplemental_status':v2['status'] if v2 else None,
                'answer_bound_status':reviewed.get(task['task_id'],{}).get('answer_bound_status'),
                'completion_with_supplemental_evidence':status=='PASS' and v2 is not None and v2['status']=='PASS',
                'latency':raw['elapsed_seconds'] if old else raw['result']['elapsed_seconds'],
                'model_calls':len(calls) if old else counts['model_calls'],
                'repair_attempt_counter':None if old else counts['repair_attempts'],
                'tool_calls':None if old else counts['tool_calls'],
                'sandbox_runs':len(raw['sandbox_executions']) if old else counts['sandbox_runs'],
                'model_switches':raw.get('model_switches',0) if old else raw['switches'],
                'output_tokens':sum(u.get('completion_tokens',0) for u in usages) if usages else None,
                'usage_measured_calls':len(usages),
                'ram_bytes':resources.get('worker_peak_rss_bytes'),
                'device_vram_mib':resources.get('gpu_peak_used_mib'),
                'raw_path':str(path.relative_to(ROOT)),
                'semantic_audit_complete':task['task_id'] in reviewed}
        rows=list(data[model].values())
        summaries.append({'model':model,'coverage':len(rows),
            **{s:sum(r['status']==s for r in rows) for s in ('PASS','PARTIAL','FAIL','BLOCKED')},
            'validated_completion_rate_percent':sum(r['status']=='PASS' for r in rows)/40*100,
            'supplemental_confirmed_completion':sum(r['completion_with_supplemental_evidence'] for r in rows),
            'supplemental_coverage':sum(r['supplemental_status'] is not None for r in rows),
            'answer_bound_review_coverage':sum(r['semantic_audit_complete'] for r in rows),
            'answer_bound_pass':sum(r['answer_bound_status']=='PASS' for r in rows),
            'answer_bound_partial':sum(r['answer_bound_status']=='PARTIAL' for r in rows),
            'median_latency_seconds':statistics.median(r['latency'] for r in rows) if rows else None,
            'model_calls':sum(r['model_calls'] for r in rows),
            'model_switches':sum(r['model_switches'] for r in rows),
            'peak_ram_bytes':max((r['ram_bytes'] for r in rows if r['ram_bytes'] is not None),default=None),
            'peak_device_vram_mib':max((r['device_vram_mib'] for r in rows if r['device_vram_mib'] is not None),default=None),
            'missing_resource_tasks':sum(r['ram_bytes'] is None for r in rows)})
    pairs=[]
    for a,b in itertools.combinations(MODELS,2):
        common=sorted(set(data[a]) & set(data[b]))
        for category in (None,*sorted({t['category'] for t in tasks})):
            ids=[i for i in common if category is None or data[a][i]['category']==category]
            eligible=[i for i in ids if data[a][i]['status']!='BLOCKED' and data[b][i]['status']!='BLOCKED']
            wins=sum(data[a][i]['status']=='PASS' and data[b][i]['status']!='PASS' for i in eligible)
            losses=sum(data[b][i]['status']=='PASS' and data[a][i]['status']!='PASS' for i in eligible)
            pairs.append({'a':a,'b':b,'category':category or 'all','paired_tasks':len(ids),
                          'pairs_without_blocks':len(eligible),'pairs_with_block':len(ids)-len(eligible),
                          'a_only_pass':wins,'b_only_pass':losses,'ties_without_blocks':len(eligible)-wins-losses,
                          'a_blocked':sum(data[a][i]['status']=='BLOCKED' for i in ids),
                          'b_blocked':sum(data[b][i]['status']=='BLOCKED' for i in ids),
                          'median_paired_latency_difference_a_minus_b':statistics.median(data[a][i]['latency']-data[b][i]['latency'] for i in ids) if ids else None})
    complete=all(s['coverage']==40 and s['supplemental_coverage']==40 for s in summaries)
    result={'status':'INCOMPLETE','executions_and_candidate_replays_complete':complete,
            'independent_semantic_review_complete':False,'winner':None,'production_modified':False,
            'summaries':summaries,'pairs':pairs,'tasks':[r for m in MODELS for r in data[m].values()],
            'limitations':['Candidate replay cannot measure repair with v2 feedback.',
                          'Repair attempt counters include malformed patch attempts; do not interpret as applied repairs.',
                          'GPU measurements are device-wide, not process allocations.',
                          'Old nonstreaming TTFT and old tool/repair counts are unavailable.',
                          'No population superiority inference from this development set.']}
    (OUT/'paired-analysis.json').write_text(json.dumps(result,indent=2))
    with (OUT/'paired-analysis.csv').open('w',newline='') as handle:
        writer=csv.DictWriter(handle,fieldnames=list(pairs[0]));writer.writeheader();writer.writerows(pairs)
    print('Paired analysis saved; semantic decision gate remains pending',flush=True)

if __name__=='__main__':main()
