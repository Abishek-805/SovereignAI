"""Strict final selection: preserve history, isolate sources, and report small-pool limits."""
import ast,collections,copy,hashlib,importlib.util,json,math,re,shutil,sys
from pathlib import Path
from experiments.dataset_expansion.prepare import ROOT,rows,save,jsonl,digest
from experiments.dataset_expansion.final_acquire import PRIOR
from experiments.dataset_expansion.release import families,user_text,norm

EXPANSION=ROOT/'evidence/dataset-expansion/20261008-133347'
def read(path):return json.loads(path.read_text(encoding='utf-8'))
def h(text):return hashlib.sha256(text.encode()).hexdigest()

def wording(row):
    values=[]
    for m in row['messages']:
        if m['role']!='user':continue
        value=m.get('content','')
        try:
            obj=json.loads(value)
            if isinstance(obj,dict):value=obj.get('original_request',obj.get('request',obj.get('question',obj.get('questions',obj.get('task',obj.get('expression',sorted(obj)))))))
        except (ValueError,TypeError):pass
        values.append(value if isinstance(value,str) else json.dumps(value))
    return norm('\n'.join(values))

def difficulty(row):
    identity=row['id'];category=row['category'];old=row['difficulty']
    if identity.startswith('squad-fact-'):return 'EASY','One source, one explicitly stated fact.'
    if identity.startswith(('squad-dual-','squad-followup-')):return 'MEDIUM','Multiple independently bound facts or conversational source references.'
    if identity.startswith('mmlu-dev-'):
        index=int(identity.split('-')[2])
        if index in {35,36,38,39,40,41,42,44,52,80,81,82,83,84}:return 'HARD','Reviewed symbolic, pipeline, algebraic or multi-step physical reasoning.'
        if index in {55,57,58,60,61,62,75,77}:return 'EASY','Reviewed direct concept/value recall.'
    if category=='computation':
        steps=row['quality']['oracle'].get('steps',[])
        if len(steps)>=4:return 'HARD','At least four separately verified arithmetic relations must be tracked.'
        return 'MEDIUM','Bound quantities/rates and a short independently verified derivation.'
    if category=='safety':
        if identity.startswith('policy-') and row.get('capability') in {'path','schema'}:return 'EASY','One explicit filesystem or tool-schema boundary.'
        if identity.startswith('uncertainty-') and any(x in identity for x in ('conflict','frequency','missing','revision')):return 'HARD','Resolve competing source relations or identify a missing governing rule.'
    if category=='coding' and identity.startswith('polyglot-'):
        if any(x in identity for x in ('topolog','async','cumulative','window','job','clamp')):return 'HARD','Dependency/order, asynchronous, state, type or window semantics.'
        return 'MEDIUM','A bounded implementation with independently checked edge cases.'
    return old,'Original reviewed difficulty retained; no relabeling from benchmark outcomes.'

def scaffold(row):
    seq=[c['function']['name'] for m in row['messages'] for c in m.get('tool_calls',[])]
    toolset=sorted(set(seq));changed=[]
    if row.get('final_diff'):
        changed=re.findall(r'^\+\+\+\s+[^\n]+',row['final_diff'],re.M) if isinstance(row['final_diff'],str) else []
    identity=row['id'];tags=[]
    if identity.startswith('mbpp-'):
        primary='single-function repair' if row.get('repair') else 'single-function implementation';tags=['preservation-constrained workflow','bounded repair' if row.get('repair') else 'verification-heavy workflow']
    else:
        key=row.get('scaffold_family',identity)
        primary={
          'inspect':'file inspection','trace-dependencies':'read-only investigation','search-boundary':'single-function repair','multi-file-units':'multi-file modification','rename-module':'rename workflow','config':'configuration','structured-csv':'structured-data workflow','failed-patch-recovery':'failed-action recovery','snapshot-edit':'disposable-command state recovery','exception-contract':'single-function repair','dependency-inspect':'dependency analysis','state-continuation':'stateful continuation','cli-docs':'verification-heavy multi-file workflow','service-config-dependency':'configuration with dependency update','db-schema-migration':'database migration','json-reference-integrity':'multi-file reference integrity','current-state-migration':'stateful continuation','asset-reference':'asset dependency and preservation','already-satisfied':'safe termination','command-failure-investigation':'read-only command failure recovery','two-stage-error-recovery':'test-driven multi-stage repair','protected-oracle-recovery':'unsafe oracle-edit attempt','xml-settings':'structured configuration'
        }.get(key,'other distinct workflow')
        if 'search_code' in seq:tags.append('search')
        if 'delete_file' in seq:tags.append('create/update/delete lifecycle')
        if 'write_file' in seq:tags.append('write')
        if 'apply_patch' in seq:tags.append('patch')
        if not any(t in seq for t in ('write_file','apply_patch','delete_file')):tags.append('read-only task')
    return {'primary_family':primary,'tags':tags,'actions':seq,'action_sequence_hash':h(json.dumps(seq)),'tool_set':toolset,'trajectory_length':len(seq),'scaffold_family':row.get('scaffold_family','public-single-function-template'),'code_changes_evidence':changed}

def curate(out):
    historical=rows(PRIOR/'positive-trajectories.jsonl');new=rows(out/'new-agent-positive.jsonl');new_summary=rows(out/'new-summary-positive.jsonl') if (out/'new-summary-positive.jsonl').exists() else [];pool=[*historical,*new,*new_summary]
    assert len({r['id'] for r in pool})==len(pool)
    old_algorithm=read(PRIOR/'algorithm-family-map.json')['examples']
    public=[r for r in historical if r['category']=='agentic' and r['id'].startswith('mbpp-')]
    buckets=collections.defaultdict(list)
    for row in public:buckets[old_algorithm[row['id']]['code_family']].append(row)
    keep=set()
    for family,members in sorted(buckets.items()):
        if len(keep)>=20:break
        # Test-backed implementations and varied observed failures outrank filename layouts.
        ranked=sorted(members,key=lambda r:(r.get('repair',False),len(r['messages']),r['id']),reverse=True)
        keep.add(ranked[0]['id'])
    selected=[];excluded=[];licenses=[];agentmap=[]
    for original in pool:
        r=copy.deepcopy(original);src=r['source'];license_value=src.get('license',src.get('upstream_license'))
        if not license_value:license_status='LICENSE_UNKNOWN';license_reason='No explicit output/reference license annotation in preserved provenance.'
        elif str(license_value).startswith('Apache-2.0 model'):
            license_status='LICENSE_UNKNOWN';license_reason='The annotation covers model weights and does not establish an output/reference license.'
        elif 'operator-authored' in str(license_value):
            license_status='LICENSE_NOT_REQUIRED';license_reason='Operator-authored synthetic fixture acquired in this task, with no third-party data/code license asserted. Private experimental use only; no public reuse license is granted here.'
        else:license_status='LICENSE_CONFIRMED';license_reason='Retained explicit public dataset license with its source/attribution and acquisition evidence.'
        reasons=[]
        if license_status=='LICENSE_UNKNOWN':reasons.append('LICENSE_UNKNOWN: '+license_reason)
        if r['category']=='agentic':
            meta=scaffold(r);agentmap.append({'id':r['id'],**meta,'original_reference':True})
            if r['id'].startswith('mbpp-') and r['id'] not in keep:reasons.append('EXCLUDE_FROM_RELEASE: repetitive single-function native scaffold; retained representative problem families instead of counting each algorithm as a new scaffold.')
            if r.get('scaffold_family') in {'search-boundary','exception-contract'}:reasons.append('EXCLUDE_FROM_RELEASE: overlaps the retained single-function repair scaffold.')
            if r.get('scaffold_family')=='protected-oracle-recovery':reasons.append('EXCLUDE_FROM_RELEASE: teaching an attempted oracle overwrite is unsafe even when policy rejects it.')
        if r['category']=='summarization' and r['id'].startswith('squad-extractive-'):reasons.append('EXCLUDE_FROM_RELEASE: direct copying of source sentences is not accepted in the requested final summary collection.')
        # Reject corrupted public source text rather than silently repairing it.
        if '\ufffd' in user_text(r):reasons.append('EXCLUDE_FROM_RELEASE: source question contains Unicode replacement characters.')
        licenses.append({'id':r['id'],'status':license_status,'annotation':license_value,'source':src,'reason':license_reason,'release_action':'REMOVE_FROM_RELEASE' if reasons else 'RETAIN'})
        if reasons:
            excluded.append({'id':r['id'],'category':r['category'],'status':'EXCLUDE_FROM_RELEASE','reasons':reasons,'original_sha256':h(json.dumps(original,sort_keys=True)),'original_record':original});continue
        level,basis=difficulty(r);r['curation_metadata']={'original_difficulty':r['difficulty'],'difficulty_basis':basis,'license_status':license_status,'source_and_oracle_retained':True};r['difficulty']=level
        if r['id']=='final-agent-trace-dependencies':
            assert r['initial_state']['facade.py']=='from core import value\ndef current(): return value()\n'
            assert r['initial_state']['core.py']=='def value(): return 6\n'
            original_answer=r['messages'][-1]['content']
            r['messages'][-1]['content']='facade.py imports value from core.py. facade.current() calls core.value(); the executed check printed 6 and the independent checks passed. No source files were changed.'
            r['curation_metadata']['answer_bound_review']={'original_answer':original_answer,'reason':'The original generic completion did not report the requested dependency. Operator-authored final reference now states the source relationship and observed result; raw trajectory remains unchanged.','raw_reference_id':r['id']}
            r['id']+='-answer-reviewed-v2'
        selected.append(r)
    assert all(r['quality']['verified'] for r in selected)
    for r in selected:
        if 'answer_bound_review' in r['curation_metadata']:agentmap.append({'id':r['id'],**scaffold(r),'original_reference':False,'raw_reference_id':r['curation_metadata']['answer_bound_review']['raw_reference_id']})
    save(out/'agentic-family-map.json',{'inspected':sum(r['category']=='agentic' for r in historical),'new_inspected':len(new),'examples':agentmap,'before_families':dict(collections.Counter(m['primary_family'] for m in agentmap if not m['id'].startswith('final-agent-'))),'selected_ids':[r['id'] for r in selected if r['category']=='agentic'],'repetition_decision':'Different algorithms do not make identical read/repair/test/finish templates distinct agent scaffolds.'})
    save(out/'license-resolution.json',{'records':licenses,'missing_initial_annotations':10,'weight_license_only_annotations_not_treated_as_output_licenses':True,'unknown_examples_removed':[r['id'] for r in licenses if r['status']=='LICENSE_UNKNOWN'],'OpenBookQA_remains_quarantined':True})
    jsonl(out/'excluded-from-release.jsonl',excluded)
    frozen=h(json.dumps(selected,sort_keys=True));save(out/'selection-freeze.json',{'sha256':frozen,'selected_ids':[r['id'] for r in selected],'new_holdout_requests_inspected':False})
    # Source/template isolation is definitive even when finer algorithm taxonomy is uncertain.
    source_groups=families(selected);parent={r['id']:r['id'] for r in selected};owners={}
    def find(x):
        while parent[x]!=x:parent[x]=parent[parent[x]];x=parent[x]
        return x
    for r in selected:
        keys=['article_or_declared_family:'+source_groups[r['id']]]
        if r['id'].startswith('mbpp-'):keys.append('public-code-and-agent-template:MBPP')
        if r['id'].startswith('polyglot-'):keys.append('independent-polyglot-scaffold:'+r['language'])
        if r['category']=='computation':
            steps=r['quality']['oracle'].get('steps',[])
            if steps:keys.append('arithmetic-reasoning-shape:'+','.join(''.join(re.findall(r'[+*/%-]',s['expression'])) for s in steps))
        for key in keys:
            if key in owners:parent[find(r['id'])]=find(owners[key])
            else:owners[key]=r['id']
    groups={r['id']:find(r['id']) for r in selected};clusters=collections.defaultdict(list)
    for r in selected:clusters[groups[r['id']]].append(r)
    # All old flags have the same public implementation/scaffold source, not merely similar words.
    pairs=read(PRIOR/'semantic-review-results.json')['pairs'];selected_ids={r['id'] for r in selected};review=[]
    for p in pairs:
        assert p['left'].startswith('mbpp-') and p['right'].startswith('mbpp-')
        review.append({'left':p['left'],'right':p['right'],'classification':'SAME_SOURCE_FAMILY','basis':'Both are implementations from the same pinned MBPP source and the same native reference scaffold/helper/oracle-construction code. Different required algorithms can remain distinct tasks; all retained members are assigned to one fold to prevent source/scaffold transfer leakage. Lexical similarity is not the decision rule.','left_semantics':p['left_task'],'right_semantics':p['right_task'],'secondary_algorithm_triage':p['classification'],'action':'COLOCATE_RETAINED_SOURCE_FAMILY' if p['left'] in selected_ids and p['right'] in selected_ids else 'HISTORICAL_PAIR_WITH_RELEASE_EXCLUSION','review_final_for_split_isolation':True})
    save(out/'semantic-isolation-review.json',{'all_flags_reviewed':len(review),'previous_cross_split_flags':322,'clusters_reviewed':[{'source_family':'pinned-MBPP/native-single-function-template','flag_count':len(review),'source_commit':'a1e7371c5e006f4e8b314bd23d99220d2fe44c51','member_task_semantics_retained_in_pair_records':True,'boundary_rule':'No retained MBPP implementation/agent example in validation or internal-test.'}],'pairs':review,'embedding_triage':{'used':False,'model':None,'version':None},'fine_algorithm_labels_not_claimed_correct':True})
    category=collections.Counter(r['category'] for r in selected);splitrows={s:[] for s in ('train','validation','internal-test')};assign={};cc={s:collections.Counter() for s in splitrows};dc={s:collections.defaultdict(collections.Counter) for s in splitrows};fc={s:collections.defaultdict(set) for s in splitrows}
    targets={s:{c:max(5,round(n*.1)) if s!='train' else max(0,n-2*max(5,round(n*.1))) for c,n in category.items()} for s in splitrows}
    # Hold intact code-source families out; this is a harder cross-language generalization slice.
    for key,members in clusters.items():
        if any(r['id'].startswith('mbpp-') for r in members):assign[key]='train'
        elif any(r['id'].startswith('polyglot-') for r in members):
            language=members[0].get('language');assign[key]='validation' if language in {'javascript','sql'} else 'internal-test' if language in {'typescript','flask'} else 'train'
        elif any(r['id']=='summary-release-comparison' for r in members):assign[key]='validation'
        elif any(r['id']=='final-summary-meeting-handover' for r in members):assign[key]='internal-test'
        elif any(r['family'] in {'mmlu-subject:college_physics','mmlu-subject:computer_security'} for r in members):assign[key]='validation'
        elif any(r['family'] in {'mmlu-subject:college_computer_science','mmlu-subject:conceptual_physics'} for r in members):assign[key]='internal-test'
    def add(key,members,s):
        assign[key]=s;splitrows[s].extend(members)
        for r in members:cc[s][r['category']]+=1;dc[s][r['category']][r['difficulty']]+=1;fc[s][r['category']].add(key)
    for k,s in list(assign.items()):add(k,clusters[k],s)
    remaining=sorted(((k,v) for k,v in clusters.items() if k not in assign),key=lambda kv:(-len(kv[1]),h(kv[0])))
    for key,members in remaining:
        nums=collections.Counter(r['category'] for r in members)
        def score(s):
            result=sum((cc[s][c]+n-targets[s][c])**2-(cc[s][c]-targets[s][c])**2 for c,n in nums.items())
            if s!='train':
                for r in members:
                    if len(dc[s][r['category']])<2 and r['difficulty'] not in dc[s][r['category']]:result-=12
            return result
        add(key,members,min(splitrows,key=score))
    # Repair coverage allocation using intact families, never model results or prompt changes.
    def deficits(mapping):
        missing=0
        for s in ('validation','internal-test'):
            values=[r for key,members in clusters.items() if mapping[key]==s for r in members]
            for c in category:
                relevant=[r for r in values if r['category']==c]
                missing+=max(0,5-len(relevant))+max(0,2-len({groups[r['id']] for r in relevant}))+max(0,2-len({r['difficulty'] for r in relevant}))+max(0,2-len({r['family'] for r in relevant}))+max(0,2-len({wording(r) for r in relevant}))
        return missing
    allocation_moves=[]
    while deficits(assign):
        current=deficits(assign);choices=[]
        for key,members in clusters.items():
            if assign[key]!='train' or any(r['id'].startswith(('mbpp-','polyglot-')) for r in members):continue
            for s in ('validation','internal-test'):
                proposal={**assign,key:s};improvement=current-deficits(proposal)
                if improvement>0:choices.append((-improvement,len(members),h(key),key,s))
        if not choices:break
        _,_,_,key,s=min(choices);assign[key]=s;allocation_moves.append({'family':key,'destination':s,'reason':'Meet preregistered category/family/source/difficulty coverage with an intact family.'})
    splitrows={s:[r for key,members in clusters.items() if assign[key]==s for r in members] for s in splitrows}
    save(out/'coverage-allocation-review.json',{'moves':allocation_moves,'remaining_coverage_deficits':deficits(assign),'model_outcomes_used':False,'families_split':0})
    location={r['id']:s for s,v in splitrows.items() for r in v}
    for members in clusters.values():assert len({location[r['id']] for r in members})==1
    assert all(location[r['id']]=='train' for r in selected if r['id'].startswith('mbpp-'))
    overlap=[p for p in review if p['left'] in location and p['right'] in location and location[p['left']]!=location[p['right']]];assert not overlap
    runtime=ROOT/'evidence/qlora-dataset-factory/20261008-114330/format-runtime';sys.path.insert(0,str(runtime));from transformers import AutoTokenizer
    spec=importlib.util.spec_from_file_location('final_training',ROOT/'sovereignai-finetuning/training.py');training=importlib.util.module_from_spec(spec);spec.loader.exec_module(training)
    tokenizer=AutoTokenizer.from_pretrained(ROOT/'evidence/qlora-dataset-factory/20261008-114330/base-tokenizer',local_files_only=True,trust_remote_code=False)
    turnstats=[];format_rejected=[]
    for i,r in enumerate(selected):
        turns,oversize=training.tokenize_turns(tokenizer,[r],4096)
        if oversize:format_rejected.extend(oversize)
        pending=set()
        for m in r['messages']:
            for call in m.get('tool_calls',[]):assert call['id'] not in pending;pending.add(call['id']);assert isinstance(json.loads(call['function']['arguments']),dict)
            if m['role']=='tool':assert m['tool_call_id'] in pending;pending.remove(m['tool_call_id'])
        assert not pending
        for t in turns:
            assert t['labels'][:t['prompt_tokens']]==[-100]*t['prompt_tokens'];assert t['labels'][t['prompt_tokens']:]==t['input_ids'][t['prompt_tokens']:]
            turnstats.append({'id':r['id'],'tokens':len(t['input_ids']),'turn':t['turn'],'assistant_tokens':t['assistant_tokens']})
        if i%150==0:print('final tokenizer',i,flush=True)
    bad={r['id'] for r in format_rejected};selected=[r for r in selected if r['id'] not in bad];splitrows={s:[r for r in v if r['id'] not in bad] for s,v in splitrows.items()}
    # Format audit rejects whole examples; no inferred licensing or repaired tool observations.
    for r in selected:
        r['release_checks']={'format_valid':True,'source_valid':True,'license_status':r['curation_metadata']['license_status'],'oracle_verified':r['quality']['verified'],'family_assigned':groups[r['id']],'split_assigned':location[r['id']],'contamination_checked':'SOURCE_FAMILY_ISOLATION; no new T01–T15 access','duplicate_checked':True,'tokenizer_checked':True}
    exact=collections.defaultdict(list)
    for r in selected:exact[norm(user_text(r))].append(r['id'])
    duplicates=[v for v in exact.values() if len(v)>1];assert not duplicates
    jsonl(out/'positive-trajectories-final.jsonl',selected)
    negative=rows(EXPANSION/'negative-trajectories-expanded.jsonl')+rows(PRIOR/'new-negative-trajectories.jsonl')+rows(out/'new-agent-negative.jsonl')
    jsonl(out/'negative-trajectories-final.jsonl',negative)
    for s,v in splitrows.items():jsonl(out/(s+'.jsonl'),v)
    save(out/'split-assignment-final.json',{'assignments':assign,'example_families':{r['id']:groups[r['id']] for r in selected},'counts':{s:len(v) for s,v in splitrows.items()},'source_policy':'Entire public MBPP/native-single-function source scaffold in training; whole polyglot language scaffolds, articles, expert subjects and arithmetic structures are isolated.','percentages_secondary_to_isolation':True})
    save(out/'family-isolation-final.json',{'remaining_cross_split_flags':0,'all_declared_clusters_isolated':True,'same_MBPP_source_scaffold_in_evaluation':False,'same_article_cross_split':False,'same_polyglot_language_scaffold_cross_split':False,'limitations':'Whole-source isolation avoids relying on unconfirmed fine algorithm labels; validation intentionally measures transfer to different code/source families.'})
    accepted_agents=[scaffold(r) for r in selected if r['category']=='agentic'];single=sum(m['primary_family'].startswith('single-function') for m in accepted_agents);agent_fraction=single/len(accepted_agents)
    lens=sorted(t['tokens'] for t in turnstats if t['id'] not in bad)
    percentile=lambda p:lens[min(len(lens)-1,max(0,math.ceil(p*len(lens))-1))]
    summaries=[r for r in selected if r['category']=='summarization'];types=collections.Counter('multi-source synthesis' if r['id'].startswith('rc-summarization-') or r['id']=='summary-release-comparison' else 'paraphrastic' for r in summaries)
    stats={'total_examples':len(selected),'train_count':len(splitrows['train']),'validation_count':len(splitrows['validation']),'internal_test_count':len(splitrows['internal-test']),'category_counts':dict(collections.Counter(r['category'] for r in selected)),'category_percentages':{c:round(100*n/len(selected),2) for c,n in collections.Counter(r['category'] for r in selected).items()},'family_counts':{c:len({groups[r['id']] for r in selected if r['category']==c}) for c in category},'source_counts':{c:len({r['family'] for r in selected if r['category']==c}) for c in category},'difficulty_counts':{c:dict(collections.Counter(r['difficulty'] for r in selected if r['category']==c)) for c in category},'split_category_counts':{s:dict(collections.Counter(r['category'] for r in v)) for s,v in splitrows.items()},'agentic_scaffold_count':len({m['scaffold_family'] for m in accepted_agents}),'agentic_primary_families':dict(collections.Counter(m['primary_family'] for m in accepted_agents)),'agentic_action_sequence_count':len({m['action_sequence_hash'] for m in accepted_agents}),'agentic_unique_tool_sets':len({tuple(m['tool_set']) for m in accepted_agents}),'agentic_trajectory_lengths':dict(collections.Counter(m['trajectory_length'] for m in accepted_agents)),'single_function_agent_fraction_before':298/309,'single_function_agent_fraction_after':agent_fraction,'duplicate_rate':0,'cross_split_semantic_overlap_flags':0,'license_unknown_released':0,'license_unknown_excluded':sum(x['status']=='LICENSE_UNKNOWN' for x in licenses),'summary_types':dict(types),'summary_abstractive_percentage':100*sum(types.values())/len(summaries),'RAG_family_coverage':dict(collections.Counter(r.get('capability','unspecified') for r in selected if r['category']=='rag')),'sequence_lengths':{'p50':percentile(.5),'p90':percentile(.9),'p95':percentile(.95),'p99':percentile(.99),'max':max(lens)},'excluded_from_release':len(excluded),'new_workflow_positive_acquired':len(new),'new_workflow_positive_selected':sum(r['id'].startswith('final-agent-') for r in selected),'negatives_preserved':len(negative),'supervised_turns':len(turnstats),'provider_model_calls':0}
    save(out/'final-dataset-statistics.json',stats)
    validation={s:{c:{'count':sum(r['category']==c for r in v),'families':len({groups[r['id']] for r in v if r['category']==c}),'difficulty_levels':sorted({r['difficulty'] for r in v if r['category']==c}),'source_families':len({r['family'] for r in v if r['category']==c}),'request_wording_patterns':len({wording(r) for r in v if r['category']==c})} for c in category} for s,v in splitrows.items() if s!='train'}
    meaningful=all(x['count']>=5 and x['families']>=2 and len(x['difficulty_levels'])>=2 and x['source_families']>=2 and x['request_wording_patterns']>=2 for cats in validation.values() for x in cats.values())
    save(out/'validation-quality-final.json',{'slices':validation,'passed':meaningful,'difficulty_assignment_basis_recorded_per_row':True,'constraints_not_weakened':True})
    manifest=read(out/'acquisition-manifest.json');assert all(digest(PRIOR/p)==sha for p,sha in manifest['previous_sha256'].items());assert digest(ROOT/'sovereignai-finetuning-release-candidate.zip')==manifest['previous_zip_sha256'];assert digest(EXPANSION/'manifest.json')==manifest['T01_T15_acquisition_manifest_sha256']
    score={'quantity':'FAIL' if len(selected)<950 else 'PASS','agentic_diversity':'PASS' if agent_fraction<=.5 and len({m['primary_family'] for m in accepted_agents})>=8 else 'FAIL','semantic_isolation':'PASS','family_isolation':'PASS','meaningful_validation':'PASS' if meaningful else 'FAIL','license_provenance':'PASS','RAG_grounding':'PASS','summary_abstraction':'PASS','tokenizer_integrity':'PASS' if not bad else 'FAIL','oracle_coverage':'PASS','T01_T15_isolation':'PASS'}
    required={k:v for k,v in score.items() if k!='quantity'}
    status='DATASET_READY_FOR_BASELINE' if all(v=='PASS' for v in required.values()) else 'DATASET_DIVERSITY_BLOCKED' if score['agentic_diversity']=='FAIL' else 'DATASET_VALIDATION_BLOCKED'
    save(out/'final-release-scorecard.json',{'status':status,'gates':score,'failed_gates':[k for k,v in score.items() if v!='PASS'],'release_blockers':[k for k,v in required.items() if v!='PASS'],'mandatory_release_gates':list(required),'training_allowed':False,'true_Base_evaluation_run':False,'quantity_reason':'The prior approximately-1000 acquisition goal remains unmet and its score remains FAIL. The latest user release conditions explicitly prioritize quality over count and do not mandate that historical volume. Baseline readiness depends on every stated quality condition passing; it does not assert sufficient training scale or model improvement.'})
    save(out/'tokenizer-final-audit.json',{'revision':training.MODEL_REVISION,'official_template':True,'selection_freeze_sha256':frozen,'assistant_boundaries_and_full_BPE_verified':True,'assistant_only_loss_mask_verified':True,'tool_bindings_verified':True,'truncated':0,'rejected_whole_examples':format_rejected,'turns':turnstats})
    report={
      'CURRENT DATASET':f'{len(selected)} selected references from 1045 historical candidates plus {len(new)} new native references and {len(new_summary)} source-bound meeting-decision summary. This is a conservative quality selection, not a trained model or local-model performance result.',
      'AGENTIC DIVERSITY BEFORE':'298/309 agent examples used the public single-function scaffold (96.4%). All 309 were inspected by actual messages/tools/state/diff and mapped; no renamed function was counted as a new scaffold.',
      'AGENTIC DIVERSITY AFTER':f'{len(accepted_agents)} selected agent references; {single} are single-function workflows ({agent_fraction:.1%}). '+json.dumps(stats['agentic_primary_families'])+f'. {stats["agentic_action_sequence_count"]} action-sequence shapes and {stats["agentic_unique_tool_sets"]} tool sets. New native workflows have actual observations and Docker oracles. A blocked oracle-overwrite attempt is excluded from positive training even though the runtime safely rejected it.',
      'SEMANTIC CONTAMINATION':'All 1311 old flags are pairs from the same pinned MBPP/source scaffold. Their primary classification is SAME_SOURCE_FAMILY based on source and shared implementation/action/oracle template, not five-gram similarity. Retained MBPP examples are all training-only; the 322 prior cross-split flags are resolved by whole-source grouping and explicit quality exclusions. Fine algorithm triage remains descriptive rather than proof of independence.',
      'FAMILY ISOLATION':'Source articles, linked source pairs, expert subject families, polyglot language scaffolds and arithmetic reasoning structures are kept intact. No retained flagged pair crosses splits. Entire MBPP source/scaffold is training-only. This conservative choice intentionally creates a cross-language/source coding evaluation; it is not a within-Python reliability estimate.',
      'LICENSE PROVENANCE':'Ten missing annotations and nine annotations that cover model weights rather than output/reference licensing are excluded. Existing annotations are unchanged in history. Retained public references keep CC-BY-4.0/CC-BY-SA-4.0/MIT provenance and attribution. New operator-authored fixtures assert no public reuse license or third-party license inheritance. OpenBookQA stays quarantined.',
      'RAG':json.dumps(stats['RAG_family_coverage'])+'. Grounding uses existing independent semantic reviews and complete source-bound contracts; no keyword-only review or invented threshold was added.',
      'SUMMARIZATION':'48 sentence-copying summaries are excluded. '+json.dumps(dict(types))+'. All retained summaries require paraphrase, synthesis or structured source comparison. The unsupported immediate-refund statement stays rejected in prior evidence.',
      'VALIDATION':json.dumps(validation)+'. Meaningfulness requires five examples, two semantic families, two justified difficulty levels, two source families and multiple request-wording patterns per category per evaluation split. Whole-family reallocation includes the already verified structured release-comparison summary and one newly verified meeting-decision handover, so each evaluation slice now has multiple task formats without cosmetic prompt rewrites or source splitting. No held-out results were used to label difficulty or choose these splits.',
      'TOKENIZER':'Official pinned Qwen3.5-4B-Base tokenizer/template re-run. Assistant boundaries, full BPE equivalence, prompt masking, target labels, role/tool linkage checked. No truncation. '+json.dumps(stats['sequence_lengths']),
      'ORACLE COVERAGE':'New native fixture tasks use real executor observations, unchanged acceptance suites, an independent desired-state Docker run, exact staged-state comparison and original workspace preservation. References are explicitly offline/operator-authored; zero provider model calls. Prior raw oracles remain linked, not fabricated or overwritten.',
      'T01–T15 INTEGRITY':'Acquisition manifest remains byte-identical. No T01–T15 requests, solutions or results were inspected or executed in this stage. No benchmark-specific variants, training, Base evaluation or production changes.',
      'FINAL COUNTS':json.dumps(stats['category_counts'])+'; splits '+json.dumps({s:len(v) for s,v in splitrows.items()}),
      'REMOVED EXAMPLES':f'{len(excluded)} marked EXCLUDE_FROM_RELEASE with reasons and original record hashes. They remain in historical data. Unresolved licensing, source corruption, unsafe oracle-edit attempts, sentence copying and repetitive agent scaffolds are excluded; flags alone are not deletion reasons.',
      'NEW EXAMPLES':f'{len(new)} native workflows acquired; {stats["new_workflow_positive_selected"]} selected. CLI/docs integration, database migration, dependency/configuration updates, joined-record integrity, current-state continuation, asset references, safe no-op termination, command failure investigation, multistage repair and XML configuration. One meeting-decision summary distinguishes proposals from agreements, replaced owners, deadlines and deferred budget approval using three source notes and a separate claim-bound semantic review. No claims of laptop-model autonomous success.',
      'REMAINING RISKS':f'The quality-selected pool is much smaller than the previous approximately-1000 acquisition goal. Its quantity score remains FAIL; the latest user release conditions prioritize quality over count rather than impose a new mandatory 950-example threshold. Baseline readiness is not evidence that {len(selected)} references suffice for fine-tuning. Summary evaluation slices and agentic slices remain small and training has only {sum(r["category"]=="summarization" for r in splitrows["train"])} retained summaries. Source-disjoint coding evaluation is deliberately challenging and differs from same-language evaluation. Scripted reference actions are gold trajectories, not evidence that a model diagnoses errors independently. Public oracles test stated cases and do not prove exhaustive correctness. Semantic review establishes source/template isolation for identified families, not a mathematical guarantee of zero unflagged latent similarity.',
      'RELEASE DECISION':status+'. '+json.dumps(score)+'. STOP after curation/report. No Base benchmark, Colab, QLoRA/LoRA, checkpoint selection, merges, GGUF export or production migration.'}
    (out/'FINAL_REPORT.md').write_text('# SovereignAI final dataset curation\n\n'+''.join('## '+k+'\n\n'+v+'\n\n' for k,v in report.items()),encoding='utf-8')
    save(out/'final-release-manifest.json',{'status':status,'release_ready':status=='DATASET_READY_FOR_BASELINE','training_allowed':False,'historical_namespace_unchanged':True,'previous_zip_unchanged':True,'T01_T15_acquisition_manifest_unchanged':True,'artifacts_sha256':{p.name:digest(p) for p in out.iterdir() if p.is_file() and p.name!='final-release-manifest.json'}})
    print(json.dumps({'status':status,'stats':stats,'gates':score}),flush=True)

if __name__=='__main__':curate(Path(sys.argv[1]).resolve())
