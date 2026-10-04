from dataclasses import FrozenInstanceError

import pytest

from router.code_agent_state import CodeObservation, CodeTaskContext, CodeTaskView, ObservationKind


def test_context_preserves_exact_requests_and_copies_bounded_reference_data():
    source={'original_request':'Rename A/B.py "HTTP://X"','resolved_request':'Rename A/B.py "HTTP://X"\nfix it',
            'workspace_id':'work','target':'A/B.py','related_files':['A/B.py'],
            'diagnostics':[{'stderr':'x'*5000,'analysis':'secret'}]}
    context=CodeTaskContext.from_mapping(source)
    source['related_files'].append('other.py')
    assert context.original_request=='Rename A/B.py "HTTP://X"'
    assert context.resolved_request.endswith('\nfix it')
    assert context.related_files==('A/B.py',)
    exported=context.to_dict()
    assert len(exported['diagnostics'][0]['stderr'])==2000
    assert 'analysis' not in exported['diagnostics'][0]
    with pytest.raises(FrozenInstanceError):context.target='other.py'
    exported['diagnostics'][0]['stderr']='changed'
    assert context.to_dict()['diagnostics'][0]['stderr']!='changed'


def test_view_observes_supervisor_without_granting_completion_or_mutating_it():
    snapshot={'supervisor_id':'task','goal':'literal','context':{'workspace_id':'w','target':'a.py'},
              'counts':{'model_switches':2},'task_state':{'resolved_original_request':'resolved',
              'current_stage':'READY_FOR_REVIEW','completion_status':'awaiting_review','active_worker':'coder',
              'repair_count':1,'plan':{'operations':[]},'observations':[{'tests_passed':True}],
              'current_candidate':{'path':'a.py','after':'pass'},'candidate_hash':'hash',
              'timestamps':{'received':1.0},'blockers':['Accept required']}}
    view=CodeTaskView.from_snapshot(snapshot)
    assert view.context.workspace=='w' and view.context.target=='a.py'
    assert view.context.original_request=='literal' and view.context.resolved_request=='resolved'
    assert view.completion_status=='awaiting_review' and view.model_switch_count==2
    assert view.repair_count==1 and view.candidate_hash=='hash'
    assert snapshot['task_state']['completion_status']=='awaiting_review'
    snapshot['task_state']['plan']['operations'].append('tampered')
    assert view.to_dict()['plan']['operations']==[]


def test_observation_preserves_actual_exit_and_execution_without_inference():
    result={'exit_code':1,'executed':True,'stdout':'out','stderr':'bad',
            'reasoning_content':'private','nested':{'thoughts':'private','count':2}}
    item=CodeObservation.from_result(ObservationKind.SANDBOX,result,identity='docker',timestamp=3.0)
    assert item.exit_code==1 and item.executed is True and item.identity=='docker'
    assert item.to_dict()['result']['nested']=={'count':2}
    assert 'reasoning_content' not in item.to_dict()['result']
    unknown=CodeObservation.from_result(ObservationKind.TEST,{'checks':{'tests_passed':True}})
    assert unknown.exit_code is None and unknown.executed is None


@pytest.mark.parametrize('result',[{'exit_code':True},{'exit_code':'0'},{'executed':'yes'}])
def test_observation_rejects_ambiguous_actual_evidence(result):
    with pytest.raises(ValueError):CodeObservation.from_result(ObservationKind.VALIDATION,result)


def test_context_rejects_over_budget_controlling_request_instead_of_truncating():
    with pytest.raises(ValueError):CodeTaskContext.from_mapping({'original_request':'x'*32769})


def test_metadata_total_size_is_bounded_and_nonfinite_numbers_removed():
    observation=CodeObservation.from_result(ObservationKind.TOOL,
        {'bulk':['x'*3000 for _ in range(100)],'nan':float('nan')})
    import json
    assert len(json.dumps(observation.to_dict()).encode())<20000
    assert observation.to_dict()['result'].get('nan') is None
