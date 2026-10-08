"""Summarize raw model project diagnostics without rewriting their outcomes."""
import json,hashlib
from pathlib import Path
from scripts.model_project_understanding_diagnostic import project_result

root=Path('outputs/model-understanding')
rows=[]
for directory in sorted(root.iterdir()):
 if not directory.is_dir():continue
 for path in sorted(directory.glob('*.json')):
  if path.name=='summary.json':continue
  j=json.loads(path.read_text(encoding='utf-8'))
  if 'case' not in j:continue
  final=j.get('final',{});result=project_result(final.get('result'))
  supervisor=(final.get('result') or {}).get('supervisor',{})
  observations=supervisor.get('task_state',{}).get('observations',[])
  sandbox_observations=[item for item in observations if item.get('kind')=='sandbox']
  error=final.get('error') or result.get('stderr') or ''
  if 'Docker Linux engine or pinned image is unavailable' in error:category='ENVIRONMENT'
  elif "can't open file '/output/main.py'" in error:category='VALIDATION_CWD'
  elif not result.get('changes'):category='MODEL_ACTION_SELECTION' if final.get('state')=='completed' else 'GENERATION_FORMAT'
  elif j.get('oracle',{}).get('exit_code') not in (None,0):category='MODEL_GENERATION'
  elif j.get('oracle',{}).get('exit_code') is None:category='EVIDENCE_GAP'
  else:category=None
  rows.append({'arm':directory.name,'task':j['case']['id'],'original_status':j.get('status'),
   'workflow_state':final.get('state'),'independent_oracle_exit':j.get('oracle',{}).get('exit_code'),
   'latency_seconds':j.get('latency'),'failure_category':category,
   'request_sha256':hashlib.sha256(j['case']['request'].encode()).hexdigest(),
   'oracle_sha256':hashlib.sha256(j['case']['oracle'].encode()).hexdigest(),
   'repair_count':result.get('repair_count'),
   'model_calls':supervisor.get('counts',{}).get('model_calls'),
   'validation_exit_sequence':[o.get('exit_code') for o in sandbox_observations],
   'unchanged_original_files':j.get('preserved_unrelated'),
   'unchanged_supplied_tests':j.get('preserved_acceptance'),
   'evidence':str(path)})

files=['backend/model.py','workflows/coding_workspace.py','workflows/request_contract.py',
       'router/tool_registry.py','skills/runtime/task-core/SKILL.md','skills/runtime/coding/SKILL.md']
summary={'engineering_status':'IMPLEMENTED_AND_REGRESSION_TESTED',
 'universal_prompt_understanding':'NOT_ESTABLISHED',
 'plain_prompt_retained_arm':{'pass':0,'fail':3,'blocked':0},
 'supplied_acceptance_retained_arm':{'pass':2,'fail':0,'blocked':0},
 'regression':{'passed':1230,'skipped':7},
 'source_fingerprints':{name:hashlib.sha256(Path(name).read_bytes()).hexdigest() for name in files},
 'outcomes':rows,
 'limitations':['Small development diagnostic, not a held-out model ranking.',
  'Only the current code worker and existing routing were exercised; not every registered model.',
  'Model-authored contracts are not independent proof of understanding.',
  'Supplied-test tasks are separate from plain-prompt tasks; their completion rates must not be pooled.',
  'Raw interrupted and rejected variant evidence remains unchanged.']}
(root/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
print(json.dumps({'retained_plain':summary['plain_prompt_retained_arm'],'retained_with_tests':summary['supplied_acceptance_retained_arm'],'regression':summary['regression']}))
