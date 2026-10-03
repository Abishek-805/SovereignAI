"""Derive repair regressions and semantic status from saved offline evidence."""
import hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'benchmarks/phase-d-handoff'
primary=json.loads((OUT/'results.json').read_text());secondary=json.loads((ROOT/'benchmarks/phase-d-repair-feedback/results.json').read_text())
assert primary['state']==secondary['state']=='COMPLETED'
components=json.loads((OUT/'component-review.json').read_text());supplement=json.loads((OUT/'supplemental-semantic-review.json').read_text())
assert len(components['controls'])==20
rows=primary['rows']+secondary['rows'];result=[]
for row in rows:
 case,arm=row['case_id'],row['arm'];attempts=row['fidelity_trace']['candidate_attempts'];replayed=[]
 for i,attempt in enumerate(attempts,1):
  if 'result' not in attempt:continue
  key=f'{case}-{arm}-{i}';entry=components['candidates'].get(key)
  assert entry is not None,key
  checks={c['index']:c['passed'] for c in entry['checks'] or [] if not c.get('setup') and c['index']>=0}
  replayed.append({'attempt':i,'checks':checks,'executed':entry['executed'],'exit_code':entry['exit_code']})
 regressions=[]
 for before,after in zip(replayed,replayed[1:]):
  lost=[index for index,passed in before['checks'].items() if passed and after['checks'].get(index) is False]
  if lost:regressions.append({'from_attempt':before['attempt'],'to_attempt':after['attempt'],'previously_passing_check_ids_now_failing':lost})
 supplement_key=f'{case}-{arm}';extra=supplement.get(supplement_key)
 if row['status']=='PASS':semantic='PASS' if extra and extra['artifact_verified'] else 'PARTIAL' if extra and not extra['artifact_verified'] else 'UNKNOWN'
 elif row['status']=='FAIL':semantic='FAIL'
 else:semantic='NOT VERIFIED'
 result.append({'case_id':case,'arm':arm,'raw_status':row['status'],'semantic_status':semantic,
  'supplemental_check':extra,'component_regressions':regressions,
  'component_replay_attempts':len(replayed),'all_completed_attempts_replayed':sum('result' in a for a in attempts)==len(replayed)})
out={'records':result,'positive_component_controls':len(components['controls']),
 'semantic_pass_counts':{arm:sum(r['semantic_status']=='PASS' for r in result if r['arm']==arm) for arm in 'ABCR'},
 'regression_cases':[r for r in result if r['component_regressions']],
 'supplemental_failures':[r['case_id']+'-'+r['arm'] for r in result if r['raw_status']=='PASS' and r['semantic_status']=='PARTIAL']}
(OUT/'semantic-and-regression-review.json').write_text(json.dumps(out,indent=2),encoding='utf-8')
baseline=json.loads((OUT/'baseline-preservation.json').read_text());changed=[path for path,sha in baseline['files'].items() if not (ROOT/path).is_file() or hashlib.sha256((ROOT/path).read_bytes()).hexdigest()!=sha]
assert not changed,changed[:10]
assert all(r['publication']=='NOT_ACCEPTED' for r in rows)
assert all((r['measurements']['max_llama_server_processes'] or 0)<=1 for r in rows)
print(json.dumps({'semantic_pass_counts':out['semantic_pass_counts'],'regression_cases':len(out['regression_cases']),'supplemental_failures':out['supplemental_failures'],'frozen_changed':changed,'single_server_max':max(r['measurements']['max_llama_server_processes'] for r in rows)},indent=2))
