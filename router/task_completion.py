"""Conservative completion observations; model assertions are never proof.

Transport completion and user-goal completion are deliberately independent.
This module observes existing executor results and does not execute or retry work.
"""


def observe_completion(result, workflow=None):
    if not isinstance(result, dict):
        return {'state':'unverified','achieved':False,'response_delivered':False,
                'checks':{},'limitations':['No structured execution result was returned.']}
    observations=[]
    def visit(item):
        if not isinstance(item,dict): return
        observations.append(item)
        visit(item.get('result'))
        for operation in (item.get('operations') or []):
            if isinstance(operation,dict): visit(operation.get('result'))
    visit(result)
    checks={}
    limitations=[]
    states={item.get('state',item.get('status')) for item in observations}
    publications={item.get('publication_state') for item in observations}
    for index,item in enumerate(observations):
        observed=item.get('checks',{})
        if isinstance(observed,dict):
            for name,value in observed.items():
                checks[f'{index}:{name}']=value
            if observed.get('semantic_support')=='not_automatically_proven':
                limitations.append('Semantic support is not automatically proven.')
    delivered=any(bool(item.get('answer')) for item in observations)
    concrete_failures={'tests_passed','runtime_passed','syntax_or_format_checked',
                       'citation_ids_valid','numeric_claims_supported','table_units_readable'}
    failed=any(name.split(':',1)[-1] in concrete_failures and value is False
               for name,value in checks.items())
    failed=failed or any(isinstance(item.get('exit_code'),int) and
                        not isinstance(item.get('exit_code'),bool) and item['exit_code']!=0
                        for item in observations)
    if 'cancelled' in states:
        state='cancelled'
    elif states & {'failed','citation_failure'} or failed:
        state='failed'
    elif publications & {'staged','recovery_required'}:
        state='awaiting_review'
        limitations.append('Project changes have not been published; explicit acceptance is required.')
        if any(item.get('checks',{}).get('container_executed') is False for item in observations
               if isinstance(item.get('checks',{}),dict)):
            limitations.append('Execution validation is unavailable; publication still requires validation.')
    elif states & {'needs_input','insufficient_evidence'}:
        state='needs_input'
    else:
        state='unverified'
        # These are observed execution contracts, not a semantic verdict from
        # an LLM or the mere absence of an exception.
        executed=any(item.get('exit_code')==0 and isinstance(item.get('exit_code'),int)
                     and not isinstance(item.get('exit_code'),bool) for item in observations)
        tested=any(item.get('checks',{}).get('tests_passed') is True or
                   item.get('checks',{}).get('runtime_passed') is True for item in observations
                   if isinstance(item.get('checks',{}),dict))
        published='published' in publications and any(item.get('checks',{}).get('target_committed') is True
                    for item in observations if isinstance(item.get('checks',{}),dict))
        calculation=any('expression' in item and 'rounded' in item and 'steps' in item
                        and item.get('status')=='completed' for item in observations)
        computed_table=any(item.get('checks',{}).get('presentation')=='verified_query_result' and
                           item.get('checks',{}).get('numeric_claims_supported') is True
                           for item in observations if isinstance(item.get('checks',{}),dict))
        simple=delivered and result.get('completion_contract')=='simple_conversation'
        for name,value in {'runtime_exit_success':executed,'runtime_checks_passed':tested,
                           'published_revision_observed':published,'calculation_evaluated':calculation,
                           'verified_table_presentation':computed_table}.items():
            if value:checks[name]=True
        if simple:checks['simple_response_delivered']=True
        if executed or tested or published or calculation or computed_table or simple:
            state='completed'
            limitations.append('Completion establishes the observed executor contract, not universal semantic correctness.')
        elif any(item.get('checks',{}).get('syntax_or_format_checked') is True
                 for item in observations if isinstance(item.get('checks',{}),dict)):
            limitations.append('Syntax or format was checked; requested runtime behavior is unverified.')
        else:
            limitations.append('A returned answer or successful workflow does not prove the entire user goal.')
    return {'state':state,'achieved':state=='completed','response_delivered':delivered,
            'checks':checks,'limitations':list(dict.fromkeys(limitations))}
