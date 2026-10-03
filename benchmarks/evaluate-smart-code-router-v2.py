"""Serial V2 comparison using the existing locked, independently validated harness.

D is the frozen V1 fixed routing/broker policy inside shared current workflows.
History is observation-only during comparisons: each arm starts empty and cannot
learn from oracle feedback. Old datasets and output files are never overwritten.
"""
import importlib.util
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
spec=importlib.util.spec_from_file_location('smart_v1_harness',ROOT/'benchmarks/evaluate-smart-code-router.py')
base=importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
original_configure=base.configure_arm
original_capture=base.capture
original_provenance=base.shared.run_provenance


def configure_arm(workbench,arm):
    original_configure(workbench,arm)
    # Store no cross-case outcome updates. Online learning would confound an
    # ordered, same-policy comparison and cannot see independent test answers.
    workbench._record_model_outcome=lambda *args:None
    if arm=='D':
        path=ROOT/'benchmarks/smart-code-router-v2/prior-model-broker.py'
        spec=importlib.util.spec_from_file_location('router._v1_benchmark_broker',path)
        module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        prior=module.ModelBroker(workbench.registry,sampler=workbench.router.selector.sampler,policy=workbench.router.selector.policy)
        class PreviousBroker:
            selector=prior.selector
            def select(self,*args,**kwargs):
                kwargs.pop('history_context',None);kwargs.pop('use_history',None)
                return prior.select(*args,**kwargs)
            def acquire(self,*args,**kwargs):return prior.acquire(*args,**kwargs)
        workbench.broker=PreviousBroker()


def failure_layer(row):
    result=row.get('operational_result') or {}
    code=(result.get('error') or {}).get('code') if isinstance(result.get('error'),dict) else None
    if code in {'model_unavailable','resource_unavailable'}:return 'ENVIRONMENT_FAILURE'
    if code in {'sandbox_unavailable','docker_unavailable'}:return 'SANDBOX_FAILURE'
    if code in {'generation_format','semantic_uncertainty'}:return 'MODEL_FAILURE'
    if code in {'workspace_conflict','invalid_file','invalid_workspace'}:return 'TOOL_FAILURE'
    if row.get('correctness') is False or result.get('state')=='failed':return 'VALIDATION_FAILURE'
    return 'UNKNOWN' if code else None


def capture(case,workbench,args):
    row=original_capture(case,workbench,args)
    decision=(row.get('operational_result',{}).get('routing') or {}).get('decision') or {}
    if not decision:
        try:
            observed=workbench.routing_decision()
            if observed.get('original_request')==case['request']:decision=observed
        except Exception:pass
    row['routing_observation']=decision
    stages=decision.get('stages') or []
    switches=[]
    for index,stage in enumerate(stages):
        if stage.get('stage')!='runtime_lease' or not stage.get('switch_required'):continue
        selection=next((item for item in reversed(stages[:index]) if item.get('stage')=='model_selection'),{})
        switches.append({'previous_model':selection.get('current_residency'),
            'next_model':stage.get('selected_model_id') or selection.get('selected_model'),
            'reason':selection.get('route_reason'),'task_stage':selection.get('worker_role'),
            'estimated_need':selection.get('selection_evidence'),
            'load_seconds':stage.get('model_load_time'),
            'validated_outcome':row.get('correctness'),'effect':'UNKNOWN',
            'effect_limit':'A paired counterfactual with equivalent validation is required.'})
    row['switch_observations']=switches
    row['failure_layer']=failure_layer(row)
    return row


def provenance(dataset,args,settings,registry):
    data=original_provenance(dataset,args,settings,registry)
    for path in [Path(__file__).resolve(),ROOT/'benchmarks/smart-code-router-v2/prior-model-broker.py']:
        data['production_sha256'][path.relative_to(ROOT).as_posix()]=hashlib.sha256(path.read_bytes()).hexdigest()
    data['comparison_policy']='V2; D frozen9b9a899 fixed role/broker within common current workflows; history frozen empty'
    return data


def main():
    # Reuse the existing CLI and strict lock/provenance/resume checks. Explicit
    # defaults prevent accidental writes over the frozen V1 evidence.
    if '--dataset' not in sys.argv:
        sys.argv+=['--dataset',str(ROOT/'benchmarks/smart-code-router-v2/main.json')]
    if '--output' not in sys.argv:
        sys.argv+=['--output',str(ROOT/'benchmarks/smart-code-router-v2-results.json')]
    output=Path(sys.argv[sys.argv.index('--output')+1]).resolve()
    protected={'smart-code-router-results.json','smart-code-router-heldout-results.json'}
    if output.name in protected:raise ValueError('Frozen V1 evidence cannot be overwritten')
    base.configure_arm=configure_arm
    base.capture=capture
    base.shared.run_provenance=provenance
    base.main()


if __name__=='__main__':main()
