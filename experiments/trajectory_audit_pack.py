"""Assemble lossless evidence pointers for answer-bound trajectory review."""
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from experiments.comparison_report import inspect, symbols

def main():
    out=ROOT/'benchmarks/model-comparison'
    rows=[]
    for model in ('coder','granite','mini-coder','qwen3.5'):
        for path in sorted((out/'fixed-40'/model).glob('*.json')):
            row=json.loads(path.read_text())
            if 'result' not in row:continue
            automatic=inspect(row)
            replay_path=out/'oracle-v2-replay'/model/path.name
            replay=json.loads(replay_path.read_text()) if replay_path.exists() else None
            if automatic['status']=='PASS' and (replay is None or replay['status']=='PASS'):continue
            events=row['result']['events']
            calls=row['calls']
            actions=[e['action'] for e in events if 'action' in e]
            docker=[e['observation'] for e in events if e.get('observation',{}).get('docker_executed')]
            hashes=[hashlib.sha256(json.dumps(c['messages'],sort_keys=True).encode()).hexdigest() for c in calls]
            workspace_ok=all(row['result']['workspace_revision'] in c['messages'][-1]['content'] for c in calls)
            errors=[e['observation']['tool_error'] for e in events if 'tool_error' in e.get('observation',{})]
            primary=automatic['primary_failure']
            if errors and any('not list' in e or 'schema' in e or 'Patch base mismatch' in e for e in errors):
                primary='ACTION_FORMAT'
            record={'model':model,'task_id':row['task_id'],'raw_path':str(path.relative_to(ROOT)),
                'raw_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'request':row['request'],
                'requirements':row['requirements'],'status':automatic['status'],'primary_failure_proposal':primary,
                'supplemental_replay':replay,
                'prompt_hashes':hashes,'action_sequence':actions,'tool_errors':errors,
                'actual_docker_observations':docker,'candidate_diff':row['candidate_diff'],
                'removed_symbols':automatic['removed_symbols'],'removed_files':row['removed_files'],
                'http_errors':[{'status':c.get('http_status'),'body':c.get('http_error_body')} for c in calls if c.get('http_status')],
                'review_questions':{
                    'task_understood':'UNKNOWN; inspect raw outputs and diff, not private reasoning',
                    'requirements_preserved':'UNKNOWN; inspect assertions and public symbols',
                    'correct_workspace_in_prompts':workspace_ok,
                    'project_map_used':'UNKNOWN; observed file reads and exec commands retained',
                    'files_inspected':automatic['file_reads'],
                    'valid_action_selected':len(actions)>0,
                    'actions_executed':len(actions),'docker_observed':len(docker)>0,
                    'returned_error_understood':'UNKNOWN; compare subsequent outputs/actions',
                    'repair_targeted':'UNKNOWN; candidate diff and observations retained',
                    'removed_existing_functions':automatic['removed_symbols'],
                    'repeated_strategy':automatic['repeated_adjacent_actions']>0,
                    'premature_finish_count':sum(e.get('action',{}).get('action')=='finish' and e.get('observation',{}).get('exit_code') not in (None,0) for e in events),
                    'oracle_adequacy':'See separately authored oracle_audit.json',
                    'environment_responsible':'UNKNOWN unless transport/Docker evidence establishes it'},
                'human_semantic_signoff':False}
            rows.append(record)
    for path in sorted((out/'old-workflow').glob('*.json')):
        row=json.loads(path.read_text())
        if 'status' not in row:continue
        replay_path=out/'oracle-v2-replay/old-workflow'/path.name
        replay=json.loads(replay_path.read_text()) if replay_path.exists() else None
        if row['status']=='PASS' and (replay is None or replay['status']=='PASS'):continue
        original=row['task']['starting_files'];candidate=row['candidate']
        rows.append({'model':'old-workflow','task_id':row['task_id'],
            'raw_path':str(path.relative_to(ROOT)),'raw_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'request':row['task']['request'],'requirements':row['task']['requirements'],
            'status':row['status'],'primary_failure_proposal':None,
            'prompt_hashes':[c['prompt_sha256'] for c in row['calls']],
            'actual_docker_observations':row['sandbox_executions'],'final_validation':row['validation'],
            'exact_error':row['error'],'removed_files':sorted(set(original)-set(candidate)),
            'removed_symbols':sorted(symbols(original)-symbols(candidate)),
            'supplemental_replay':replay,'human_semantic_signoff':False,
            'review_questions':'Compare every saved request, actual HTTP response, generated/staged files, Docker errors and final answer. Do not infer success from workflow status.'})
    (out/'failure_analysis_evidence_pack.json').write_text(json.dumps({'full_audit_complete':False,'rows':rows},indent=2))
    print('Evidence packs',len(rows))

if __name__=='__main__':main()
