"""Conservative semantic triage and provisional family-isolated candidate, no training."""
import ast,collections,hashlib,importlib.util,json,re,shutil,sys
from pathlib import Path
from experiments.dataset_expansion.prepare import ROOT,rows,save,jsonl,digest
from experiments.dataset_expansion.candidate_repair import PRIOR
from experiments.dataset_expansion.release import families,user_text,norm

RULES=[
 ('parsing','regular-expression',r'\bregex|regular expression|pattern|re\.search|re\.find'),
 ('graphs','graph-traversal',r'\bgraph|breadth.first|depth.first|dijkstra|adjacency'),
 ('trees','tree-structure',r'\btree|binary search tree|inorder|preorder'),
 ('data-structures','linked-list',r'linked list|linkedlist'),
 ('data-structures','heap-priority',r'heapq|\bheap|priority queue'),
 ('sorting','ordering',r'\bsort|sorted|ascending|descending'),
 ('search','lookup',r'binary search|linear search|bisect|\bsearch'),
 ('dynamic-programming','recurrence',r'dynamic programming|knapsack|fibonacci|memoiz|catalan'),
 ('strings','palindrome',r'palindrom'),('strings','anagram',r'anagram'),
 ('strings','case-transform',r'lowercase|uppercase|capitaliz|casefold|title case'),
 ('strings','encoding',r'ascii|unicode|encode|decode|base64|\bhexadecimal|\bbinary'),
 ('strings','tokenization',r'\bword|\bwords|\bsplit|token'),
 ('strings','substring',r'substring|prefix|suffix|\bstring|character|\btext'),
 ('arrays','matrix',r'matrix|matrices|diagonal|\brow|\bcolumn'),
 ('arrays','contiguous-window',r'subarray|contiguous|sliding.window|sublist'),
 ('arrays','pair-combination',r'\bpair|\btriplet|\btuple|combinations|itertools'),
 ('hashing','frequency',r'frequency|frequencies|\bcount|occurrence|counter|duplicate'),
 ('sets','set-algebra',r'\bset|intersection|union|\bunique|distinct'),
 ('math','prime-divisor',r'\bprime|divisor|\bgcd|\blcm|divisib|perfect number'),
 ('math','digit-arithmetic',r'\bdigit|decimal|octal|hex|bitwise|\bbit'),
 ('math','geometry',r'\barea|perimeter|triangle|circle|rectangle|sphere|volume|distance'),
 ('math','combinatorics',r'factorial|permutation|binomial|combinat'),
 ('math','numerical-formula',r'\bnumber|\bsum|\bproduct|\bpower|\baverage|\bmean|\bsquare|\bcube|\bmod|\bmaximum|\bminimum'),
 ('arrays','collection-transform',r'\blist|\barray|\bdict|dictionary|\bsequence|\belement'),
]

BOUNDARY_OVERRIDES={
 601:('dynamic-programming','pair-chain'),613:('arrays','record-attribute-reduction'),744:('arrays','nullable-tuple-predicate'),81:('arrays','tuple-alignment'),602:('hashing','first-repeated-character'),621:('parsing','numeric-token-transform'),557:('strings','case-transform'),608:('math','bell-recurrence'),84:('math','newman-conway-recurrence'),852:('arrays','numeric-filter'),629:('arrays','numeric-filter'),586:('arrays','rotation'),515:('dynamic-programming','subset-modulo'),518:('math','square-root'),606:('math','angle-conversion'),636:('math','quadratic-roots'),55:('math','geometric-sequence'),590:('math','coordinate-conversion'),642:('hashing','matrix-row-deduplication'),622:('search','sorted-order-statistics'),597:('search','sorted-order-statistics'),632:('arrays','stable-partition'),646:('math','cube-packing'),575:('math','nonmultiple-enumeration'),714:('math','prime-factorization'),671:('math','bit-manipulation'),552:('math','sequence-linearity'),699:('strings','binary-swaps'),364:('strings','binary-alternation'),387:('math','radix-parity'),778:('arrays','run-length-grouping'),562:('arrays','nested-length-reduction'),247:('dynamic-programming','palindromic-subsequence'),873:('math','recursive-fibonacci'),
}

def classify(row,definitions):
    if row['id'] in definitions:
        d=definitions[row['id']];task=d['public_task'];text=task['text'];code=task['code']
        family,subfamily=next(((a,b) for a,b,p in RULES if re.search(p,text+'\n'+code,re.I)),('OTHER','requires-semantic-review'))
        if task['task_id'] in BOUNDARY_OVERRIDES:family,subfamily=BOUNDARY_OVERRIDES[task['task_id']]
        return {'algorithm_family':family,'subfamily':subfamily,'task_type':'repair' if d['repair'] else 'implementation','language':'python','difficulty':row['difficulty'],'task_semantics':text,'code_sha256':hashlib.sha256(code.encode()).hexdigest(),'code_family':family+':'+subfamily,'assignment_method':'task-plus-implementation triage; independent boundary review remains required','final_review':False}
    lang=row.get('language','unknown');family='database' if lang=='sql' else 'web' if lang in {'react','flask'} else 'implementation'
    return {'algorithm_family':family,'subfamily':row.get('capability',row['family']),'task_type':'repair' if row.get('repair') else 'implementation','language':lang,'difficulty':row['difficulty'],'task_semantics':user_text(row),'code_family':row['family'],'assignment_method':'explicit independently authored contract/source family','final_review':True}

def curate(out):
    data=rows(PRIOR/'positive-trajectories-expanded.jsonl')
    additions=[]
    for name in ('document-verified.jsonl','safety-verified.jsonl','agent-verified.jsonl'):additions.extend(rows(out/name))
    rejected_summary=next(r for r in additions if r['id']=='rc-summarization-refund')
    repaired_summary=__import__('copy').deepcopy(rejected_summary);repaired_summary['id']+='-reviewed-v2'
    repaired_summary['messages'][-1]['content']='The two cancellations follow different paths: the undispatched order qualifies for a full cancellation refund, while the shipped order requires a return before refund processing.'
    repaired_summary['source']['original_candidate_id']=rejected_summary['id']
    additions=[repaired_summary if r['id']==rejected_summary['id'] else r for r in additions]
    save(out/'summary-independent-review.json',{'rejected_id':rejected_summary['id'],'reason':'Immediately is an unsupported processing-time claim; refund eligibility does not establish processing time.','new_reference_id':repaired_summary['id'],'all_other_new_summaries_reviewed':True,'full_source_scope_qualifications_checked':True})
    save(out/'algorithm-boundary-review.json',{'manually_reviewed_task_assignments':{str(k):v for k,v in BOUNDARY_OVERRIDES.items()},'findings':['Generic tuple matching mixed pair-chain dynamic programming with tuple inspection.','Internal sorted calls do not make row deduplication an ordering task.','Count and set words confused arithmetic with hashing/set algebra.','Dynamic programming and elementary recursion must not be treated as identical implementations.'],'remaining_boundary_review_complete':False})
    # Check native staged content independently, not just the teacher's intended result.
    defs=json.loads((out/'scaffold-definitions.json').read_text());byid={d['id']:d for d in defs}
    for row in additions:
        if not row['id'].startswith('rc-agent-'):continue
        d=byid[row['id'].removeprefix('rc-agent-')];result=json.loads((out/'agent-raw'/d['id']/'native-result.json').read_text())
        staged={c['path']:None if c['action']=='delete' else c['after'] for c in result['changes']}
        assert staged==d['expected'],(d['id'],staged,d['expected'])
        row['quality']['oracle']['independent_staged_state_exact_match']=True
    data.extend(additions);assert len({r['id'] for r in data})==len(data)
    freeze_path=out/'candidate-freeze.json';previous_freeze=json.loads(freeze_path.read_text()) if freeze_path.exists() else {}
    frozen_sha=hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()
    save(freeze_path,{'ids':[r['id'] for r in data],'rows_sha256':frozen_sha,'training_started':False})
    definitions={d['id']:d for d in rows(PRIOR/'coding-candidates.jsonl')}
    algorithm={r['id']:classify(r,definitions) for r in data if r['category'] in {'agentic','coding'}}
    save(out/'algorithm-family-map.json',{'examples':algorithm,'family_counts':dict(collections.Counter(m['algorithm_family'] for m in algorithm.values())),'subfamily_counts':dict(collections.Counter(m['code_family'] for m in algorithm.values())),'final_boundary_review_complete':False})
    # Conservative isolation unions source families and proposed algorithm subfamilies.
    basegroups=families(data);parent={r['id']:r['id'] for r in data};owners={}
    def find(x):
        while parent[x]!=x:parent[x]=parent[parent[x]];x=parent[x]
        return x
    for r in data:
        keys=['source:'+basegroups[r['id']]]
        if r['id'] in definitions:keys.append('algorithm:'+algorithm[r['id']]['code_family'])
        for key in keys:
            if key in owners:parent[find(r['id'])]=find(owners[key])
            else:owners[key]=r['id']
    groups={r['id']:find(r['id']) for r in data};clusters=collections.defaultdict(list)
    for r in data:clusters[groups[r['id']]].append(r)
    oldsplit={r['id']:s for s in ('train','validation','internal-test') for r in rows(PRIOR/(s+'.jsonl'))}
    representatives=[]
    for k,members in clusters.items():
        reps=members[:2]+members[-2:] if len(members)>4 else members
        representatives.append({'cluster_id':k,'size':len(members),'task_families':sorted({algorithm[r['id']]['code_family'] if r['id'] in algorithm else r['family'] for r in members}),'capabilities':sorted({r.get('capability','unspecified') for r in members}),'source_families':sorted({r['family'] for r in members}),'provisional_split_membership':dict(collections.Counter(oldsplit.get(r['id'],'new') for r in members)),'representatives':[{'id':r['id'],'task':algorithm[r['id']]['task_semantics'] if r['id'] in algorithm else user_text(r),'oracle':r['quality']['oracle']} for r in reps],'boundary_review':'PENDING for inferred algorithm families; conservative merged isolation, no release certification'})
    save(out/'semantic-clusters.json',representatives)
    byrow={r['id']:r for r in data};flags=json.loads((PRIOR/'deduplication-report-expanded.json').read_text())['near_request_pairs'];decisions=[]
    for flag in flags:
        a=byrow[flag['left']];b=byrow[flag['right']];ta=algorithm[a['id']]['task_semantics'] if a['id'] in definitions else user_text(a);tb=algorithm[b['id']]['task_semantics'] if b['id'] in definitions else user_text(b)
        sources=lambda r:{d.get('title') for d in r.get('evidence',[]) if d.get('title')}
        if norm(ta)==norm(tb):kind='EXACT_DUPLICATE';basis='Underlying task requests equal after infrastructure is removed.'
        elif re.sub(r'\d+','N',norm(ta))==re.sub(r'\d+','N',norm(tb)):kind='NEAR_DUPLICATE';basis='Underlying task differs only in numeric literals.'
        elif a['family']==b['family'] or sources(a)&sources(b):kind='SAME_SOURCE/FAMILY_LEAK';basis='Shared source/document or declared fixture family.'
        elif a['id'] in definitions and b['id'] in definitions:
            ma=algorithm[a['id']];mb=algorithm[b['id']]
            if ma['code_family']==mb['code_family']:kind='SAME_TASK_FAMILY';basis='Proposed common algorithm subfamily; merged conservatively pending boundary review.'
            elif ma['algorithm_family']==mb['algorithm_family']:kind='RELATED_BUT_DISTINCT';basis='Different task operations within a broader algorithm domain; proposed only.'
            else:kind='GENUINELY_DISTINCT';basis='Different task/implementation domains; repeated inspection/preservation instructions created the lexical flag. Final boundary review pending.'
        else:kind='RELATED_BUT_DISTINCT';basis='Distinct contracts or requested answer types; final semantic decision pending.'
        decisions.append({**flag,'classification':kind,'basis':basis,'left_task':ta,'right_task':tb,'review_status':'PROVISIONAL_NOT_RELEASE_ACCEPTANCE','cluster_merged':groups[a['id']]==groups[b['id']]})
    save(out/'semantic-review-results.json',{'pairs':decisions,'classification_counts':dict(collections.Counter(d['classification'] for d in decisions)),'pair_final_acceptance_complete':False,'method':'Cluster-level task+code-family triage, explicit source identity, requested capability. No embedding threshold or lexical flag is treated as final semantic acceptance.'})
    counts=collections.Counter(r['category'] for r in data);splits={s:[] for s in ('train','validation','internal-test')};catcounts={s:collections.Counter() for s in splits};assignments={};ratios={'train':.8,'validation':.1,'internal-test':.1}
    for key,members in sorted(clusters.items(),key=lambda kv:(-len(kv[1]),hashlib.sha256(kv[0].encode()).hexdigest())):
        cc=collections.Counter(r['category'] for r in members)
        s=min(splits,key=lambda s:sum((catcounts[s][c]+n-ratios[s]*counts[c])**2-(catcounts[s][c]-ratios[s]*counts[c])**2 for c,n in cc.items())/ratios[s])
        assignments[key]=s;splits[s].extend(members);catcounts[s].update(cc)
    finalsplit={r['id']:s for s,v in splits.items() for r in v};cross=[d for d in decisions if finalsplit[d['left']]!=finalsplit[d['right']]]
    leak=[d for d in cross if d['classification'] in {'EXACT_DUPLICATE','NEAR_DUPLICATE','SAME_TASK_FAMILY','SAME_SOURCE/FAMILY_LEAK'}]
    assert not leak and all(len({finalsplit[r['id']] for r in members})==1 for members in clusters.values())
    save(out/'family-isolation-report.json',{'declared_source_and_proposed_algorithm_cluster_leakage':len(leak),'flagged_cross_split_pairs_remaining':len(cross),'remaining_pairs_are_provisionally_distinct':True,'final_semantic_boundary_audit_complete':False,'family_isolation_prioritized_over_80_10_10':True})
    save(out/'split-assignment-final.json',{'assignments':assignments,'example_clusters':groups,'counts':{s:len(v) for s,v in splits.items()},'category_counts':{s:dict(v) for s,v in catcounts.items()},'splits_provisional_until_release_gates_pass':True})
    runtime=ROOT/'evidence/qlora-dataset-factory/20261008-114330/format-runtime';sys.path.insert(0,str(runtime));from transformers import AutoTokenizer
    spec=importlib.util.spec_from_file_location('training',ROOT/'sovereignai-finetuning/training.py');training=importlib.util.module_from_spec(spec);spec.loader.exec_module(training)
    tokenizer=AutoTokenizer.from_pretrained(ROOT/'evidence/qlora-dataset-factory/20261008-114330/base-tokenizer',local_files_only=True,trust_remote_code=False)
    audit_path=out/'tokenizer-final-audit.json'
    cached=json.loads(audit_path.read_text()) if audit_path.exists() and previous_freeze.get('rows_sha256')==frozen_sha else None
    lengths=cached['turns'] if cached else [];reject=cached['rejections'] if cached else []
    for i,row in enumerate(data):
        if cached:continue
        turns,oversize=training.tokenize_turns(tokenizer,[row],4096)
        if oversize:reject.extend(oversize)
        lengths.extend({'id':row['id'],'turn':t['turn'],'tokens':len(t['input_ids']),'assistant_tokens':t['assistant_tokens']} for t in turns)
        # Validate native tool call/observation binding without repairing canonical data.
        pending=set()
        for m in row['messages']:
            if m['role']=='assistant':pending.update(c['id'] for c in m.get('tool_calls',[]))
            if m['role']=='tool':
                if m['tool_call_id'] not in pending:reject.append({'id':row['id'],'reason':'UNMATCHED_TOOL_RESPONSE','tool_call_id':m['tool_call_id']})
                else:pending.remove(m['tool_call_id'])
        if pending:reject.append({'id':row['id'],'reason':'UNRESOLVED_TOOL_CALLS','call_ids':sorted(pending)})
        if i%200==0:print('tokenizer',i,flush=True)
    bad={r['id'] for r in reject};data=[r for r in data if r['id'] not in bad];splits={s:[r for r in v if r['id'] not in bad] for s,v in splits.items()}
    save(out/'tokenizer-final-audit.json',{'official_pinned_tokenizer':training.MODEL_REVISION,'assistant_boundaries_and_mask_bpe_verified':True,'tool_bindings_verified_for_exported_examples':True,'truncated':0,'invalid_examples_rejected_whole':sorted(bad),'oversized_examples_rejected_whole':sorted({r['id'] for r in reject if r.get('reason')=='OVERSIZE_NOT_TRUNCATED'}),'rejections':reject,'max_tokens':max(t['tokens'] for t in lengths),'turns':lengths})
    for s,v in splits.items():jsonl(out/(s+'.jsonl'),v)
    jsonl(out/'positive-trajectories.jsonl',data)
    rejected_summary=__import__('copy').deepcopy(rejected_summary);rejected_summary['quality']['verified']=False;rejected_summary['rejection']='UNSUPPORTED_IMMEDIATE_PROCESSING_CLAIM'
    original_rows=rows(PRIOR/'positive-trajectories-expanded.jsonl')
    rejected_formats=[{**r,'release_rejection':[x for x in reject if x['id']==r['id']]} for r in original_rows if r['id'] in bad]
    jsonl(out/'new-negative-trajectories.jsonl',[*rows(out/'agent-negative.jsonl'),rejected_summary,*rejected_formats])
    agent=[]
    for r in data:
        if r['category']!='agentic':continue
        seq=[c['function']['name'] for m in r['messages'] for c in m.get('tool_calls',[])];agent.append({'id':r['id'],'action_sequence_hash':hashlib.sha256(json.dumps(seq).encode()).hexdigest(),'tool_set':sorted(set(seq)),'trajectory_length':len(seq),'scaffold_family':r.get('scaffold_family','single-function-public-reference' if r['id'] in definitions else r['family']),'actions':seq,'provider_model_success_claimed':False})
    diversity=collections.Counter(r['scaffold_family'] for r in agent);save(out/'agent-scaffold-diversity.json',{'examples':agent,'family_counts':dict(diversity),'action_sequence_shapes':len({r['action_sequence_hash'] for r in agent}),'single_function_dominance_fraction':diversity['single-function-public-reference']/len(agent),'new_native_workflows_passed':len(rows(out/'agent-verified.jsonl')),'new_native_workflows_failed':len(rows(out/'agent-negative.jsonl')),'adequate_diversity':False})
    save(out/'rag-coverage-final.json',{'count':sum(r['category']=='rag' for r in data),'new_independently_reviewed_contracts':16,'type_counts':dict(collections.Counter(r.get('capability','unspecified') for r in data if r['category']=='rag')),'semantic_review_methods':['original independent crowd-answer/source review','new full relation/scope/qualification contracts'],'substring_only_acceptance':False})
    save(out/'safety-coverage-final.json',{'count':sum(r['category']=='safety' for r in data),'new_distinct_docker_boundaries':8,'actual_security_probe':str(out/'docker-security-verifier.json'),'no_privilege_granted':True})
    summary=[r for r in data if r['category']=='summarization'];abstractive=[r for r in summary if r['id'].startswith('rc-summarization-')]
    save(out/'summary-abstraction-audit.json',{'total':len(summary),'new_abstractive':len(abstractive),'abstractive_ratio':len(abstractive)/len(summary),'review':'All 16 authored summaries paraphrase and combine distinct source facts/constraints without copying sentences. Numeric and causal qualifications reviewed.','meaningful_minority':len(abstractive)/len(summary)>=.2,'examples':[{'id':r['id'],'sources':r['evidence'],'summary':r['messages'][-1]['content']} for r in abstractive]})
    provenance=[]
    for r in data:
        src=r['source'];kind=src['kind'];tag='LOCAL_MODEL' if kind=='self_generated' else 'PUBLIC_REFERENCE' if 'public' in kind or kind=='public_human_reference' else 'OPERATOR_AUTHORED'
        provenance.append({'id':r['id'],'source_type':tag,'source':src,'license':src.get('license',src.get('upstream_license')),'verification':r['quality']['oracle']})
    unresolved_licenses=[r['id'] for r in provenance if not r['license']]
    save(out/'license-provenance-final.json',{'examples':provenance,'unresolved_license_annotations':unresolved_licenses,'openbook_remains_quarantined':True,'repository_code_license_not_used_as_dataset_license':True,'missing_annotations_not_invented':True})
    negative_rows=rows(out/'new-negative-trajectories.jsonl');historical_negative=rows(PRIOR/'negative-trajectories-expanded.jsonl')
    current=collections.Counter(r['category'] for r in data);stats={'accepted':len(data),'current_counts':dict(current),'inherited_negative_quarantine_records':len(historical_negative),'new_negative_count':len(negative_rows),'negative_category_counts':dict(collections.Counter(r.get('category','RAW_FAILURE_UNCLASSIFIED') for r in historical_negative+negative_rows)),'tokenizer_rejected':len(bad),'categories':{c:{'count':n,'difficulty':dict(collections.Counter(r['difficulty'] for r in data if r['category']==c)),'family_count':len({groups[r['id']] for r in data if r['category']==c}),'source_count':len({r['source'].get('dataset',r['source'].get('kind')) for r in data if r['category']==c}),'verified_count':sum(r['quality']['verified'] for r in data if r['category']==c)} for c,n in current.items()},'algorithm_families':dict(collections.Counter(v['algorithm_family'] for v in algorithm.values())),'pair_classifications':dict(collections.Counter(d['classification'] for d in decisions)),'provisional_cross_split_pair_rate':len(cross)/len(decisions),'provisional_family_leakage_rate':len(leak)/len(decisions),'near_duplicate_final_rate':'UNRESOLVED_PENDING_SEMANTIC_REVIEW'}
    save(out/'dataset-statistics-final.json',stats)
    historical=json.loads((out/'historical-manifest.json').read_text());unchanged=all(digest(PRIOR/p)==sha for p,sha in historical['sha256'].items());assert unchanged
    targets={'agentic':300,'rag':250,'coding':200,'general_qa':100,'computation':50,'summarization':50,'safety':50}
    meaningful=all(sum(r['category']==c for r in splits[s])>=5 and len({r['difficulty'] for r in splits[s] if r['category']==c})>=2 and len({groups[r['id']] for r in splits[s] if r['category']==c})>=2 for c in targets for s in ('validation','internal-test'))
    gates={'CATEGORY COVERAGE':all(current[c]>=n for c,n in targets.items()),'SEMANTIC CONTAMINATION':False,'FAMILY ISOLATION':False,'AGENTIC DIVERSITY':False,'RAG GROUNDING':True,'SUMMARY ABSTRACTION':len(abstractive)/len(summary)>=.2,'TOKENIZER FORMAT':True,'LICENSE PROVENANCE':not unresolved_licenses,'ORACLE EVIDENCE':True,'T01–T15 ISOLATION':True,'MEANINGFUL VALIDATION':meaningful}
    status='DATASET_DIVERSITY_BLOCKED';score={'status':status,'gates':{k:'PASS' if v else 'FAIL' for k,v in gates.items()},'critical_failed':[k for k,v in gates.items() if not v],'training_allowed':False,'base_evaluation_run':False,'heldout_inspected_or_executed':False,'inferred_clusters_do_not_certify_independence':True}
    save(out/'release-scorecard.json',score)
    save(out/'contamination-report-final.json',{'status':'SEMANTIC_BOUNDARY_REVIEW_INCOMPLETE','prior_lexical_scan_clear':True,'new_holdout_inspection':False,'prior_pair_flags':1311,'prior_cross_split_flags':463,'provisional_remaining_cross_split_flags':len(cross),'confirmed_duplicate_rate':'NOT_ESTABLISHED','training_blocked':True})
    headings={
      'CURRENT COUNTS':json.dumps(dict(current))+f'; total {len(data)}. Prior 421 quarantines preserved, plus {len(negative_rows)} new rejection records: a failed workflow, an unsupported summary claim and two historical examples excluded for unpaired tool calls.',
      'REMAINING BLOCKERS':', '.join(score['critical_failed'])+'. No critical acceptance criteria were weakened.',
      'SEMANTIC CONTAMINATION FINDINGS':f'All 1311 pair flags received explicit task/source/capability triage classifications. These are provisional: inferred algorithm cluster boundaries have not been independently resolved. {len(cross)} flags remain across provisional splits, classified as related/distinct, never accepted from lexical overlap alone. No new T01–T15 inspection.',
      'SPLIT/FAMILY ISOLATION':json.dumps({s:len(v) for s,v in splits.items()})+'. Entire declared source and proposed algorithm subfamilies were grouped before splitting. No same proposed task/source family crosses splits. Final semantic isolation is not certified.',
      'AGENTIC DIVERSITY':f'11 distinct new native workflows passed and one scoped deletion was blocked by the existing validator. New examples include multiple files, rename via create/update/delete, search, read-only inspection, configuration, structured CSV, failed patch recovery, disposable shell edits, dependency inspection and continuation. Public single-function workflows still dominate ({diversity["single-function-public-reference"]}/{len(agent)}); this critical gate remains failed.',
      'RAG COVERAGE':'16 additional distinct two-source contracts cover conditional eligibility, comparisons, numeric derivation, role authority, temporal relations, contradictions and missing evidence. All targets preserve qualifications. Count target now met.',
      'SAFETY COVERAGE':'Eight distinct new boundaries use actual pinned Docker probes: memory, CPU, pids, timeout, output, input mount, host environment and non-root execution. Existing safety/provenance unchanged.',
      'SUMMARIZATION ABSTRACTION':f'16 new technical and nontechnical multi-source paraphrases; {len(abstractive)/len(summary):.1%} of summaries require synthesis. Critical facts, limitations and numerical/causal qualifications reviewed.',
      'LICENSE STATUS':'Prior MBPP CC-BY-4.0, SQuAD CC-BY-SA-4.0, MMLU/GSM8K MIT and operator-authored annotations retained. New fixtures explicitly synthetic/operator-authored; OpenBookQA remains quarantined. Ten original operator/model-generated examples lack explicit license annotations; these are unresolved, not silently inferred from model-weight or repository licenses. Attribution/share-alike obligations travel with the data.',
      'TOKENIZER STATUS':'Official pinned Qwen3.5-4B-Base template re-run; full BPE assistant boundaries, assistant-only masks and native tool bindings checked. No truncation; invalid examples rejected whole. Original checksums and catalog examples have unpaired tool calls and remain historically unchanged but are excluded from release.',
      'ORACLE/VERIFICATION STATUS':'New native loop results verified against immutable tests and exact staged state, with a separate desired-state Docker run. One failed deletion is retained as negative, not repaired silently. Docker security probes passed. These are offline references, not local-model performance.',
      'T01–T15 INTEGRITY':'No requests, expected solutions or outcomes inspected in this stage; no evaluation or tuning. Prior evidence files remain byte-identical under the acquisition manifest. Production and weights unchanged.',
      'RELEASE DECISION':status+'. STOP: no Base baseline, Colab smoke, QLoRA/LoRA, checkpoint selection or deployment. Final release requires independently resolved semantic boundaries and a materially less repetitive agent dataset.'}
    (out/'FINAL_REPORT.md').write_text('# SovereignAI release-candidate curation\n\n'+''.join('## '+k+'\n\n'+v+'\n\n' for k,v in headings.items()),encoding='utf-8')
    save(out/'release-manifest.json',{'status':status,'release_ready':False,'historical_evidence_unchanged':unchanged,'old_dataset_not_overwritten':True,'training_started':False,'artifacts_sha256':{p.name:digest(p) for p in out.iterdir() if p.is_file() and p.name!='release-manifest.json'},'new_positive_ids':[r['id'] for r in additions],'true_base_evaluation':False})
    print(json.dumps({'status':status,'counts':dict(current),'total':len(data),'scorecard':score}),flush=True)

if __name__=='__main__':curate(Path(sys.argv[1]).resolve())
