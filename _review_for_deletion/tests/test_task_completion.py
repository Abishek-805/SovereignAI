from router.task_completion import observe_completion


def test_staged_code_is_not_user_goal_completion():
    value=observe_completion({'state':'completed','result':{'publication_state':'staged',
        'checks':{'container_executed':True,'tests_passed':True}}})
    assert value['state']=='awaiting_review' and not value['achieved']


def test_insufficient_evidence_is_not_completed_wrapper():
    value=observe_completion({'state':'completed','result':{'status':'insufficient_evidence','answer':'Missing evidence'}})
    assert value['state']=='needs_input' and not value['achieved'] and value['response_delivered']


def test_nested_operation_failure_prevents_completion():
    value=observe_completion({'state':'completed','operations':[{'result':{'state':'failed'}}]})
    assert value['state']=='failed'


def test_syntax_alone_does_not_prove_runtime_behavior():
    value=observe_completion({'state':'completed','checks':{'syntax_or_format_checked':True}})
    assert value['state']=='unverified' and not value['achieved']


def test_answer_does_not_claim_semantic_proof():
    value=observe_completion({'status':'answered','answer':'Done','checks':{
        'citation_ids_valid':True,'numeric_claims_supported':True,'semantic_support':'not_automatically_proven'}})
    assert not value['achieved'] and 'Semantic support is not automatically proven.' in value['limitations']


def test_failed_numeric_check_overrides_success_status():
    assert observe_completion({'status':'answered','checks':{'numeric_claims_supported':False}})['state']=='failed'


def test_published_revision_contract_and_runtime_execution_observed():
    assert observe_completion({'publication_state':'published','checks':{'target_committed':True}})['achieved']
    assert observe_completion({'exit_code':0})['achieved']
    assert not observe_completion({'exit_code':False})['achieved']
    assert observe_completion({'exit_code':1})['state']=='failed'


def test_computed_table_checks_are_distinct_from_generated_prose():
    value=observe_completion({'status':'answered','checks':{'presentation':'verified_query_result',
        'numeric_claims_supported':True,'semantic_support':'not_automatically_proven'}})
    assert value['achieved']
    assert 'Semantic support is not automatically proven.' in value['limitations']


def test_staged_without_docker_keeps_review_and_validation_boundary():
    value=observe_completion({'state':'completed','publication_state':'staged','checks':{'container_executed':False}})
    assert value['state']=='awaiting_review' and not value['achieved']
    assert any('validation is unavailable' in limit for limit in value['limitations'])
