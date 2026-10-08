import hashlib
import importlib.util
from pathlib import Path
import pytest


def analyzer():
    path=Path(__file__).resolve().parents[2]/'benchmarks/analyze-hybrid-code-agent.py'
    spec=importlib.util.spec_from_file_location('hybrid_analysis_test',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def passed(arm='F'):
    validation={'container_executed':True,'exit_code':0,'artifact_verified':True,'original_sources_preserved':True}
    return {'arm':arm,'case_id':'case','stage':'READY_FOR_REVIEW','gate':'EXECUTED','correctness':True,
        'validation':validation,'validation_trajectory':[{'phase':'trusted_tests',**validation,'candidate_hashes':{'solution.py':'good'}}]}


def test_final_independent_gate_required_for_f_vs_all_baselines():
    module=analyzer();f=passed();f['correctness']=False
    result=module.analyze({'rows':[passed(arm) for arm in 'ABCDE']+[f]})
    assert set(result['arms'])==set('ABCDEF')
    assert set(result['paired'])=={'F_vs_'+arm for arm in 'ABCDE'}
    assert result['paired']['F_vs_E']['transitions']=={'PASS->FAIL':1}


def test_semantic_review_requires_exact_answer_hash():
    module=analyzer();row={'arm':'F','case_id':'case','stage':'answered','operational_result':{'answer':'actual'}}
    review={'arm':'F','case_id':'case','status':'PASS','answer_sha256':hashlib.sha256(b'other').hexdigest()}
    assert module.analyze({'rows':[row]},[review])['arms']['F']['outcome']['UNKNOWN']==1
    review['answer_sha256']=hashlib.sha256(b'actual').hexdigest()
    assert module.analyze({'rows':[row]},[review])['arms']['F']['outcome']['PASS']==1


def test_recovery_requires_failed_changed_candidate_and_final_pass():
    module=analyzer();row=passed();row['repair_observed']=True
    assert not module.independent_repair(row)
    row['validation_trajectory'].insert(0,{'phase':'trusted_tests','container_executed':True,'exit_code':1,'candidate_hashes':{'solution.py':'bad'}})
    assert module.independent_repair(row)
    row['validation_trajectory'][0]['candidate_hashes']={'solution.py':'good'}
    assert not module.independent_repair(row)


def test_mixed_terminal_proposal_failure_is_not_recovery():
    module=analyzer();row=passed();row.update(gate='FAIL',repair_observed=True,operational_result={'error':{'code':'generation_format'}})
    row['validation_trajectory'].insert(0,{'phase':'trusted_tests','container_executed':True,'exit_code':1,'candidate_hashes':{'solution.py':'bad'}})
    assert module.analyze({'rows':[row]})['arms']['F']['repair_independent_recovery']==0


def test_switch_effect_without_same_state_counterfactual_unknown():
    module=analyzer();row=passed();row['switch_observations']=[{'effect':'HELPFUL','load_seconds':1}]
    assert module.analyze({'rows':[row]})['switch_effects']['F']['UNKNOWN']==1
    row['switch_observations'][0]['hard_constraint_evidence']={'source':'runtime_admission','constraint':'modality','previous_satisfies':False,'next_satisfies':True}
    assert module.analyze({'rows':[row]})['switch_effects']['F']['necessary']==1


def test_heldout_denied_before_read(tmp_path):
    module=analyzer()
    with pytest.raises(ValueError,match='Heldout'):
        module.development_contracts(tmp_path/'heldout.json')


def test_duplicate_trials_not_silently_paired():
    module=analyzer()
    with pytest.raises(ValueError,match='Duplicate'):
        module.analyze({'rows':[passed(),passed()]})
