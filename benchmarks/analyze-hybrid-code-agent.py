"""Offline six-arm hybrid evidence analysis; never invokes models or executes candidates."""
import argparse
from collections import Counter
import importlib.util
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('hybrid_base_analysis',ROOT/'benchmarks/analyze-smart-code-router-v2.py')
v2=importlib.util.module_from_spec(spec)
spec.loader.exec_module(v2)
ARMS=tuple('ABCDEF')
v2.ARMS=ARMS


def independent_repair(row):
    """Require a real failed candidate, a changed candidate and final trusted pass."""
    if row.get('repair_observed') is not True or v2._trusted_verdict(row)!='PASS':
        return False
    failures=[]
    for event in row.get('validation_trajectory') or []:
        if event.get('phase')!='trusted_tests' or event.get('container_executed') is not True:
            continue
        code=event.get('exit_code')
        hashes=event.get('candidate_hashes')
        if not isinstance(hashes,dict) or not hashes:
            continue
        if isinstance(code,int) and not isinstance(code,bool) and code!=0:
            failures.append(hashes)
        elif code==0 and event.get('artifact_verified') is True and any(prior!=hashes for prior in failures):
            return True
    return False


def analyze(report,semantic_reviews=None,*,case_contracts=None):
    result=v2.analyze(report,semantic_reviews,case_contracts=case_contracts)
    reviews=semantic_reviews.get('reviews',[]) if isinstance(semantic_reviews,dict) else semantic_reviews or []
    by_review={(item['arm'],item['case_id']):item for item in reviews}
    by_arm={arm:{} for arm in ARMS}
    grouped={arm:[] for arm in ARMS}
    for row in report.get('rows') or []:
        arm=row.get('arm');case=row.get('case_id')
        if arm in by_arm and isinstance(case,str):
            if case in by_arm[arm]:
                raise ValueError('Duplicate arm/case observations cannot form a paired comparison')
            grouped[arm].append(row)
            by_arm[arm][case]=v2._outcome(row,v2._semantic_verdict(row,by_review.get((arm,case))))
    result['paired']={}
    for baseline in ARMS[:-1]:
        common=sorted(by_arm[baseline].keys() & by_arm['F'].keys())
        transitions=Counter((by_arm[baseline][case],by_arm['F'][case]) for case in common)
        result['paired']['F_vs_'+baseline]={'cases':len(common),
            'transitions':{left+'->'+right:count for (left,right),count in sorted(transitions.items())},
            'both_decisive':sum(count for (left,right),count in transitions.items() if left in ('PASS','FAIL') and right in ('PASS','FAIL')),
            'interpretation':'Descriptive paired task outcomes; fixed-order arms do not establish causal switching benefit'}
    for arm in ARMS:
        result['arms'][arm]['repair_independent_recovery']=sum(independent_repair(row) for row in grouped[arm])
        switches=[event for row in grouped[arm] for event in row.get('switch_observations') or []]
        necessary=sum(isinstance(event.get('hard_constraint_evidence'),dict) and
            event['hard_constraint_evidence'].get('source')=='runtime_admission' and
            event['hard_constraint_evidence'].get('constraint') in ('modality','context_capacity','availability','resource_admission') and
            event['hard_constraint_evidence'].get('previous_satisfies') is False and
            event['hard_constraint_evidence'].get('next_satisfies') is True for event in switches)
        result['switch_effects'][arm]={'observed':len(switches),'necessary':necessary,'UNKNOWN':len(switches)-necessary,
            'HELPFUL':0,'NEUTRAL':0,'HARMFUL':0,
            'reason':'Only explicit hard constraint evidence establishes necessity; no equivalent same-state switch/no-switch experiment is recorded'}
    result['comparison_scope']='F versus A–E; trusted final gates or exact-answer-hash semantic reviews; no model self-agreement'
    return result


def development_contracts(path):
    if 'heldout' in str(path).lower():
        raise ValueError('Heldout datasets are excluded')
    data=json.loads(path.read_text(encoding='utf-8'))
    if 'heldout' in json.dumps(data.get('metadata') or data.get('meta') or {}).lower():
        raise ValueError('Heldout datasets are excluded')
    cases=data.get('cases') or []
    return {case['id']:case['contract_id'] for case in cases if case.get('contract_id')}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report',type=Path)
    parser.add_argument('--semantic-review',type=Path)
    parser.add_argument('--development-dataset',type=Path)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args(argv)
    contracts=development_contracts(args.development_dataset) if args.development_dataset else None
    reviews=json.loads(args.semantic_review.read_text(encoding='utf-8')) if args.semantic_review else None
    result=analyze(json.loads(args.report.read_text(encoding='utf-8')),reviews,case_contracts=contracts)
    text=json.dumps(result,indent=2,sort_keys=True)+'\n'
    if args.output:args.output.write_text(text,encoding='utf-8')
    else:print(text)

if __name__=='__main__':main()
