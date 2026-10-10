"""Audit and package acquired references; never turn a count into a release claim."""
import ast, collections, copy, hashlib, importlib.util, json, re, shutil, sys
from pathlib import Path
from experiments.dataset_expansion.prepare import ROOT, rows, save, jsonl, digest

STATUS='DATASET_NEEDS_MORE_VERIFIED_DATA'
TARGET={'agentic':300,'rag':250,'coding':200,'general_qa':100,'computation':50,'summarization':50,'safety':50}

def review(out):
    positives=[]; negatives=[]; decisions=[]
    for p in sorted((out/'correction-bounded-raw').glob('*/candidate.json')):
        row=json.loads(p.read_text(encoding='utf-8')); index=int(p.parent.name.split('-')[0])
        accepted=index in {2,172,188}
        reason='Complete supported answer, qualified requested scope and identifiable source labels.' if accepted else 'Independent review rejects incomplete/truncated wording, unsupported relation, contradictory claim or failure to answer every requested part.'
        row['quality']['verified']=accepted;row['quality']['oracle'].update(passed=accepted,independent_semantic_review={'decision':'ACCEPT' if accepted else 'REJECT','reason':reason,'reviewer':'Codex, separate from local producer'})
        if not accepted:row['rejection']=reason
        (positives if accepted else negatives).append(row);decisions.append({'id':row['id'],'raw_sha256':digest(p),'accepted':accepted,'reason':reason})
    # False-premise and typo questions are not automatically good refusal examples.
    accepted_indices={0,2,3,4,8,10,11,12,14}
    for index,original in enumerate(rows(out/'unanswerable-candidates.jsonl')):
        row=copy.deepcopy(original);row['id']+='-reviewed';accepted=index in accepted_indices
        reason='Requested date, identity or relation is absent; response reports source-limited information without inventing the missing fact.' if accepted else 'The source permits a premise correction or likely typo resolution; a generic refusal is not an adequate answer.'
        row['quality']['verified']=accepted;row['quality']['oracle'].update(passed=accepted,independent_semantic_review={'decision':'ACCEPT' if accepted else 'REJECT','reason':reason})
        if not accepted:row['rejection']=reason
        (positives if accepted else negatives).append(row);decisions.append({'id':row['id'],'accepted':accepted,'reason':reason})
    jsonl(out/'final-semantic-verified.jsonl',positives);jsonl(out/'final-semantic-negatives.jsonl',negatives)
    save(out/'final-semantic-review.json',{'decisions':decisions,'targets_not_rewritten':True})

def user_text(row):
    values=[]
    for m in row['messages']:
        if m['role']!='user':continue
        value=m.get('content','')
        try:
            obj=json.loads(value)
            if isinstance(obj,dict):value=obj.get('original_request',obj.get('question',obj.get('task',obj.get('expression',value))))
        except (ValueError,TypeError):pass
        values.append(value if isinstance(value,str) else json.dumps(value))
    return '\n'.join(values)

def norm(text):return ' '.join(re.findall(r'\w+',text.lower()))
def shingles(text):
    w=norm(text).split();return {tuple(w[i:i+5]) for i in range(max(0,len(w)-4))}

def families(data):
    parent={r['id']:r['id'] for r in data};owner={}
    def find(x):
        while parent[x]!=x:parent[x]=parent[parent[x]];x=parent[x]
        return x
    for row in data:
        keys=['family:'+row['family']]
        keys+=['article:'+d['title'] for d in row.get('evidence',[]) if 'title' in d]
        for key in keys:
            if key in owner:parent[find(row['id'])]=find(owner[key])
            else:owner[key]=row['id']
    return {r['id']:find(r['id']) for r in data}

def build(out):
    review(out)
    seed=rows(out/'immutable-seed/positive-trajectories.jsonl');data=list(seed)
    filenames=['reference-verified.jsonl','semantic-verified.jsonl','mmlu-verified.jsonl','structured-verified.jsonl','polyglot-verified.jsonl','uncertainty-verified.jsonl','extra-computation.jsonl','extra-summary.jsonl','final-semantic-verified.jsonl']
    for name in filenames:data.extend(rows(out/name))
    outcomes=[json.loads(p.read_text(encoding='utf-8')) for p in sorted((out/'coding-raw').glob('*/outcome.json'))]
    for result in outcomes:
        if result['passed']:data.append(json.loads((out/'coding-raw'/result['id']/'candidate.json').read_text(encoding='utf-8')))
    assert len({r['id'] for r in data})==len(data) and all(r['quality']['verified'] for r in data)
    save(out/'acquisition-freeze.json',{'ids':[r['id'] for r in data],'sha256':hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest(),'candidate_generation_complete_before_holdout_scan':True})
    # The existing approved rejection-only request scanner; never read solutions/results.
    holdouts=json.loads((ROOT/'evidence/code-agent-fidelity-v1/reports/tasks.json').read_text(encoding='utf-8'))
    contamination=[]; suspicious=set()
    for row in data:
        text=user_text(row);sh=shingles(text);maximum=0;exact=False
        for task in holdouts:
            hs=shingles(task['request']);union=sh|hs;maximum=max(maximum,len(sh&hs)/len(union) if union else 0);exact=exact or norm(text)==norm(task['request'])
        rejected=exact or maximum>.3 or bool(re.search(r'\bT(?:0[1-9]|1[0-5])\b',text))
        if rejected:suspicious.add(row['id'])
        contamination.append({'id':row['id'],'max_request_5gram_jaccard':maximum,'exact':exact,'rejected':rejected})
    save(out/'contamination-report-expanded.json',{'status':'AUTOMATED_SCREEN_CLEAR' if not suspicious else 'CONTAMINATION_DETECTED','results_inspected':False,'solutions_inspected':False,'generation_used_holdouts':False,'scan':contamination,'limitations':'Approved lexical rejection scanner cannot certify semantic/structural disjointness.'})
    if suspicious.intersection(r['id'] for r in seed):raise RuntimeError('Original seed flagged; preserve and halt')
    quarantined=[r for r in data if r['id'] in suspicious];data=[r for r in data if r['id'] not in suspicious]
    runtime=ROOT/'evidence/qlora-dataset-factory/20261008-114330/format-runtime';sys.path.insert(0,str(runtime))
    from transformers import AutoTokenizer
    spec=importlib.util.spec_from_file_location('expanded_training',ROOT/'sovereignai-finetuning/training.py');training=importlib.util.module_from_spec(spec);spec.loader.exec_module(training)
    tokenizer=AutoTokenizer.from_pretrained(ROOT/'evidence/qlora-dataset-factory/20261008-114330/base-tokenizer',local_files_only=True,trust_remote_code=False)
    lengths=[];format_rejected=[];accepted=[]
    for i,row in enumerate(data):
        try:
            turns,oversize=training.tokenize_turns(tokenizer,[row],max_length=4096)
            if oversize:raise ValueError('OVERSIZE_NOT_TRUNCATED '+json.dumps(oversize))
            assert turns and all(any(x>=0 for x in t['labels']) and len(t['labels'])==len(t['input_ids']) for t in turns)
            lengths.extend({'id':row['id'],'turn':t['turn'],'tokens':len(t['input_ids']),'assistant_tokens':t['assistant_tokens'],'prompt_tokens':t['prompt_tokens']} for t in turns);accepted.append(row)
        except Exception as exc:
            if row['id'] in {r['id'] for r in seed}:raise
            rejected=copy.deepcopy(row);rejected['quality']['verified']=False;rejected['rejection']='FORMAT: '+str(exc);format_rejected.append(rejected)
        if i%100==0:print('format',i,'accepted',len(accepted),flush=True)
    jsonl(out/'format-rejected.jsonl',format_rejected);data=accepted
    duplicates=collections.defaultdict(list)
    for row in data:duplicates[norm(user_text(row))].append(row['id'])
    exact_groups=[v for v in duplicates.values() if len(v)>1]
    actions=collections.Counter(tuple(c['function']['name'] for m in r['messages'] for c in m.get('tool_calls',[])) for r in data if r['category']=='agentic')
    save(out/'deduplication-report-expanded.json',{'exact_request_groups':exact_groups,'action_patterns':[{'actions':list(k),'count':v} for k,v in actions.most_common()],'exact_request_audit_passed':not exact_groups,'semantic_algorithm_families_audited':False,'limitation':'Distinct public task IDs/ASTs are not sufficient evidence of distinct algorithm families. Action patterns are diagnostics, not proof of duplication.'})
    groups=families(data);byfamily=collections.defaultdict(list)
    for row in data:byfamily[groups[row['id']]].append(row)
    assignments={};splitrows={n:[] for n in ('train','validation','internal-test')};counts={n:collections.Counter() for n in splitrows}
    totals=collections.Counter(r['category'] for r in data);ratios={'train':.8,'validation':.1,'internal-test':.1}
    for family,members in sorted(byfamily.items(),key=lambda kv:(-len(kv[1]),hashlib.sha256(kv[0].encode()).hexdigest())):
        catcount=collections.Counter(r['category'] for r in members)
        choice=min(splitrows,key=lambda s:sum((counts[s][c]+n-ratios[s]*totals[c])**2-(counts[s][c]-ratios[s]*totals[c])**2 for c,n in catcount.items())/ratios[s])
        assignments[family]=choice;splitrows[choice].extend(members);counts[choice].update(catcount)
    assert all(len({assignments[groups[r['id']]] for r in members})==1 for members in byfamily.values())
    negatives=rows(out/'immutable-seed/negative-trajectories.jsonl')
    for name in ['reference-quarantine.jsonl','semantic-negatives.jsonl','mmlu-negatives.jsonl','structured-negatives.jsonl','polyglot-negatives.jsonl','final-semantic-negatives.jsonl']:negatives.extend(rows(out/name))
    negatives.extend(format_rejected)
    for r in quarantined:
        r=copy.deepcopy(r);r['quality']['verified']=False;r['rejection']='CONTAMINATION_SCREEN';negatives.append(r)
    negatives.extend(r for r in outcomes if not r['passed'])
    for folder in ('correction-raw','correction-bounded-raw'):
        negatives.extend({'id':'failed-'+folder+'-'+p.parent.name,'failure':json.loads(p.read_text(encoding='utf-8')),'raw_evidence':str(p.relative_to(ROOT))} for p in (out/folder).glob('*/failure.json'))
    # Original records remain byte-for-byte at the beginning of expanded collections.
    for name,seedname,values in [('positive-trajectories-expanded.jsonl','positive-trajectories.jsonl',data),('negative-trajectories-expanded.jsonl','negative-trajectories.jsonl',negatives)]:
        original=(out/'immutable-seed'/seedname).read_bytes();old=rows(out/'immutable-seed'/seedname);assert values[:len(old)]==old
        (out/name).write_bytes(original+(b'' if original.endswith(b'\n') else b'\n')+''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in values[len(old):]).encode('utf-8'))
    for split,values in splitrows.items():jsonl(out/(split+'.jsonl'),values)
    mismatch=[]
    for name,sha in json.loads((out/'manifest.json').read_text())['protected_sha256'].items():
        if digest(ROOT/name)!=sha:mismatch.append(name)
    repair=sum(r.get('repair',False) for r in data if r['category']=='coding');coding_count=totals['coding']
    stats={'positive_examples':len(data),'negative_or_quarantined_records':len(negatives),'categories':dict(totals),'target_categories':TARGET,'category_shortfalls':{c:max(0,n-totals[c]) for c,n in TARGET.items()},'splits':{s:{'examples':len(v),'categories':dict(counts[s])} for s,v in splitrows.items()},'source_kinds':dict(collections.Counter(r['source']['kind'] for r in data)),'languages':dict(collections.Counter(r.get('language','not_applicable') for r in data)),'coding_repairs':repair,'coding_repair_fraction':repair/coding_count,'training_started':False}
    save(out/'dataset-statistics-expanded.json',stats)
    save(out/'sequence-length-analysis-expanded.json',{'model':training.MODEL_NAME,'revision':training.MODEL_REVISION,'official_template':True,'max_length':4096,'truncated':0,'rejected_examples':len(format_rejected),'assistant_only_loss':True,'full_bpe_boundary_checks':True,'max_tokens':max(t['tokens'] for t in lengths),'supervised_turns':len(lengths),'turns':lengths})
    save(out/'training-mixture-expanded.json',{'target':TARGET,'actual':dict(totals),'family_isolation':True,'families':len(byfamily),'assignments':assignments,'split_category_counts':{s:dict(c) for s,c in counts.items()}})
    save(out/'trajectory-inventory-expanded.json',{'rows':[{'id':r['id'],'category':r['category'],'family':r['family'],'split_family':groups[r['id']],'source':r['source'],'turns':len(r['messages']),'oracle':r['quality']['oracle']} for r in data]})
    save(out/'oracle-results-expanded.json',{'coding_execution_outcomes':outcomes,'docker_verifier':json.loads((out/'docker-verifier.json').read_text()),'all_exported_rows_verified':all(r['quality']['verified'] for r in data),'independent_semantic_reviews':['independent-semantic-review.json','mmlu-independent-review.json','final-semantic-review.json'],'limitations':['MBPP supplied tests plus negative controls do not prove all edge cases.','Policy examples include static contract checks, not per-example attack execution.','Offline reference adapters are not laptop-model task completions.']})
    gates={'approximately_1000':950<=len(data)<=1050,'category_targets':all(totals[c]>=n for c,n in TARGET.items()),'family_isolation':True,'meaningful_category_validation':all(counts[s][c]>=5 for s in ('validation','internal-test') for c in TARGET),'lexical_contamination_screen':not suspicious,'semantic_contamination_audit':False,'exact_request_dedup':not exact_groups,'algorithm_family_dedup':False,'format':True,'preserved_production_and_seed':not mismatch,'coding_repair_quota':repair/coding_count>=.25,'genuine_diverse_agent_scaffolds':False,'abstractive_summary_coverage':False}
    readiness={'status':STATUS,'gates':gates,'failed_gates':[k for k,v in gates.items() if not v],'production_integrity_mismatches':mismatch,'dataset_release_ready':False,'baseline_completed':False,'colab_gpu_smoke_completed':False,'training_started':False,'reason':'Useful verified acquisition completed, but broader agent workflows, abstractive summaries and semantic family/contamination audits remain insufficient.'}
    save(out/'release-readiness.json',readiness);save(out/'dataset-expansion-report.json',{'status':STATUS,'statistics':stats,'readiness':readiness,'coding_batch_complete':True,'coding_model_performance_claimed':False})
    report='# SovereignAI expanded dataset audit\n\nStatus: '+STATUS+'\n\n'+f"{len(data)} verified references exported; {len(negatives)} negative/quarantine records preserved. No training, Base baseline, GPU smoke or production change.\n\n"
    report+='| Category | Accepted | Target |\n|---|---:|---:|\n'+''.join(f'| {c} | {totals[c]} | {n} |\n' for c,n in TARGET.items())
    report+='\n496 public coding references passed real Docker checks; seven acquisition cases were rejected. Native agent trajectories use an explicitly offline reference adapter: zero provider model calls, no inference about model success. Twenty additional JS/TS/React/Flask/SQL references passed independent Docker oracles and negative controls. React coverage is server rendering, not browser interaction.\n\n'
    report+='Source provenance distinguishes CC-BY-4.0 MBPP, CC-BY-SA-4.0 SQuAD, MIT GSM8K/MMLU and operator-authored fixtures. OpenBookQA remains quarantined because the dataset license is unconfirmed. Preserve attribution and share-alike obligations; code-repository licenses do not establish dataset licenses.\n\n'
    report+='Original 21 positives and 14 negatives are unchanged. Splits join source articles and declared families before assigning 80/10/10 category targets. This does not yet certify broader algorithm-family independence. Official pinned tokenizer audited every accepted assistant boundary and loss mask; oversized examples were rejected whole, never truncated.\n\n'
    report+='Release blockers: '+', '.join(readiness['failed_gates'])+'. Agent data is dominated by single-function Python repairs; most summaries are extractive; a lexical holdout scanner is insufficient for semantic disjointness. Do not pad counts with cosmetic variations or start training from this package.\n\nSee JSON reports and append-only raw directories for decisions and exact execution evidence. True Base baseline is a later gate; the instruction-tuned local teacher is not Base.\n'
    (out/'FINAL_REPORT.md').write_text(report,encoding='utf-8')
    package=ROOT/'sovereignai-finetuning-expanded';package.mkdir(exist_ok=True)
    for name in ('training.py','export_adapter.py','qlora_config.yaml','requirements-colab.txt','training_environment.yaml','training_manifest.json','sovereignai_qwen35_qlora_colab.ipynb'):
        shutil.copyfile(ROOT/'sovereignai-finetuning'/name,package/name)
    for name in ('dataset-expansion-report.json','trajectory-inventory-expanded.json','positive-trajectories-expanded.jsonl','negative-trajectories-expanded.jsonl','train.jsonl','validation.jsonl','internal-test.jsonl','dataset-statistics-expanded.json','training-mixture-expanded.json','sequence-length-analysis-expanded.json','deduplication-report-expanded.json','contamination-report-expanded.json','oracle-results-expanded.json','release-readiness.json','FINAL_REPORT.md'):shutil.copyfile(out/name,package/name)
    save(package/'dataset-statistics.json',{**stats,'release_ready':False});save(package/'baseline-evaluation.json',{'status':'NOT_RUN','model':training.MODEL_NAME,'revision':training.MODEL_REVISION,'training_allowed':False})
    (package/'QLORA_TRAINING_GUIDE.md').write_text('Expanded acquisition is not released for training. Read FINAL_REPORT.md and release-readiness.json first. The preserved Colab notebook is a preparation template, still points to the original package and defaults RUN_SMOKE/RUN_TRAIN=False. Do not enable training; missing diversity and audits must be completed before true Base baseline and Colab GPU smoke. Original NF4/r16/alpha32/dropout0.05/learning-rate1e-4 configuration remains unchanged.\n',encoding='utf-8')
    save(package/'evidence-location.json',{'root':str(out),'raw_results_included_in_zip':False,'reason':'Large raw trajectories remain in the preserved workspace evidence namespace.'})
    finish_package(out)
    print(json.dumps({'status':STATUS,'stats':stats,'failed_gates':readiness['failed_gates']}),flush=True)

def finish_package(out):
    package=ROOT/'sovereignai-finetuning-expanded'
    notebook_path=package/'sovereignai_qwen35_qlora_colab.ipynb'
    notebook=json.loads(notebook_path.read_text(encoding='utf-8'))
    for cell in notebook['cells']:
        text=''.join(cell['source']).replace("DATASET_PATH='/content/sovereignai-finetuning'","DATASET_PATH='/content/sovereignai-finetuning-expanded'")
        text=text.replace('This seed is not release-ready.','This expanded acquisition is not release-ready.').replace('sovereignai-finetuning.zip','sovereignai-finetuning-expanded.zip')
        cell['source']=text.splitlines(True)
    save(notebook_path,notebook)
    manifest=json.loads((package/'training_manifest.json').read_text(encoding='utf-8'))
    manifest.update(dataset_sha256={s+'.jsonl':digest(package/(s+'.jsonl')) for s in ('train','validation','internal-test')},release_ready=False,seed_only=False,notebook_sha256=digest(notebook_path),evidence_namespace=str(out))
    save(package/'training_manifest.json',manifest)
    (package/'QLORA_TRAINING_GUIDE.md').write_text('Expanded acquisition is not released for training. Read FINAL_REPORT.md and release-readiness.json first. Upload the expanded ZIP; notebook path is /content/sovereignai-finetuning-expanded and RUN_SMOKE/RUN_TRAIN default to False. Do not enable training: diversity and semantic audits must pass before true Base baseline and Colab GPU smoke. Existing NF4/r16/alpha32/dropout0.05/learning-rate1e-4 configuration is unchanged.\n',encoding='utf-8')
    counts={s:len(rows(package/(s+'.jsonl'))) for s in ('train','validation','internal-test')}
    ids=[r['id'] for s in counts for r in rows(package/(s+'.jsonl'))]
    assert len(ids)==len(set(ids))==len(rows(package/'positive-trajectories-expanded.jsonl'))
    assert manifest['release_ready'] is False
    for name,sha in manifest['dataset_sha256'].items():assert digest(package/name)==sha
    for name in ('training.py','export_adapter.py'):ast.parse((package/name).read_text(encoding='utf-8'))
    save(package/'package-checks.json',{'split_partition':True,'dataset_manifest_hashes':True,'training_gated':True,'python_syntax':True,'split_counts':counts,'gpu_smoke':'NOT_RUN'})
    shutil.make_archive(str(package),'zip',package.parent,package.name)

if __name__=='__main__':build(Path(sys.argv[1]).resolve())
