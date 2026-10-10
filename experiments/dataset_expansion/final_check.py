"""Check the final export independently of the curator, then package it without training."""
import ast,collections,json,shutil,sys,zipfile
from pathlib import Path
from experiments.dataset_expansion.prepare import ROOT,rows,save,digest
from experiments.dataset_expansion.release import user_text,shingles,norm
from experiments.dataset_expansion.final_curate import wording

def read(path):return json.loads(path.read_text(encoding='utf-8'))

def check(out):
    data=rows(out/'positive-trajectories-final.jsonl');byid={r['id']:r for r in data}
    splits={s:rows(out/(s+'.jsonl')) for s in ('train','validation','internal-test')}
    identities=[r['id'] for v in splits.values() for r in v]
    assert len(data)==len(byid)==len(identities)==len(set(identities)) and set(identities)==set(byid)
    locations={r['id']:s for s,v in splits.items() for r in v}
    groups=read(out/'split-assignment-final.json')['example_families'];seen=collections.defaultdict(set)
    oracle_paths=[]
    for r in data:
        assert r['quality']['verified'] and r['quality']['oracle']['passed']
        for key in ('format_valid','source_valid','oracle_verified','family_assigned','split_assigned','contamination_checked','duplicate_checked','tokenizer_checked'):assert r['release_checks'][key]
        assert r['release_checks']['license_status'] in {'LICENSE_CONFIRMED','LICENSE_NOT_REQUIRED'}
        assert r['release_checks']['split_assigned']==locations[r['id']]
        for key in [groups[r['id']],'declared:'+r['family']]+['article:'+e['title'] for e in r.get('evidence',[]) if 'title' in e]:seen[key].add(locations[r['id']])
        path=r['quality']['oracle'].get('evidence')
        if path:
            assert (ROOT/path).is_file();oracle_paths.append({'id':r['id'],'path':path,'sha256':digest(ROOT/path)})
        pending={}
        for m in r['messages']:
            assert m['role'] in {'system','user','assistant','tool'}
            for c in m.get('tool_calls',[]):
                assert m['role']=='assistant' and c['id'] not in pending
                assert isinstance(json.loads(c['function']['arguments']),dict)
                pending[c['id']]=c['function']['name']
            if m['role']=='tool':assert m['tool_call_id'] in pending;pending.pop(m['tool_call_id'])
        assert not pending
        if r['id'].startswith('mbpp-'):assert locations[r['id']]=='train'
    assert all(len(v)==1 for v in seen.values())
    assert all(r==byid[r['id']] for v in splits.values() for r in v)
    requests=[norm(user_text(r)) for r in data];assert len(requests)==len(set(requests))
    # Similarity is only triage; source/code identity determines the actual decision.
    words=[shingles(user_text(r)) for r in data];flags=[]
    for i,left in enumerate(data):
        for j in range(i+1,len(data)):
            union=words[i]|words[j]
            similarity=len(words[i]&words[j])/len(union) if union else 0
            if similarity<.6:continue
            right=data[j]
            assert groups[left['id']]==groups[right['id']]
            public=left['id'].startswith('mbpp-') and right['id'].startswith('mbpp-')
            if public:basis='Same pinned MBPP implementation source and reference-code/native action scaffold; task statements may require distinct algorithms.'
            else:
                assert left['family']==right['family'] and left['id'].startswith('rc-') and right['id'].startswith('rc-')
                basis='Question and synthesis use the identical two-note source contract. Expected output behaviors differ; the entire source family stays together.'
            flags.append({'left':left['id'],'right':right['id'],'similarity_triage':similarity,'classification':'SAME_SOURCE_FAMILY','basis':basis,'split':locations[left['id']],'cross_split':False})
    save(out/'final-pair-semantic-review.json',{'threshold':.6,'reviewed_pairs':len(flags),'cross_split_flags':0,'pairs':flags,'unflagged_latent_similarity_not_proven_absent':True})
    original=read(out/'acquisition-manifest.json');previous=Path(original['previous_candidate'])
    assert all(digest(previous/name)==sha for name,sha in original['previous_sha256'].items())
    assert digest(ROOT/'sovereignai-finetuning-release-candidate.zip')==original['previous_zip_sha256']
    expansion=ROOT/'evidence/dataset-expansion/20261008-133347'
    assert digest(expansion/'manifest.json')==original['T01_T15_acquisition_manifest_sha256']
    negative=rows(out/'negative-trajectories-final.jsonl')
    historical=rows(expansion/'negative-trajectories-expanded.jsonl')
    assert negative[:len(historical)]==historical and len(historical)==421 and len(negative)==425
    for name in ('positive-trajectories.jsonl','negative-trajectories.jsonl'):
        assert (expansion/'immutable-seed'/name).read_bytes()==(ROOT/'sovereignai-finetuning'/name).read_bytes()
    audits=read(out/'tokenizer-final-audit.json');audited={r['id'] for r in audits['turns']}
    assert audited==set(byid) and audits['truncated']==0 and not audits['rejected_whole_examples']
    assert audits['assistant_only_loss_mask_verified'] and audits['assistant_boundaries_and_full_BPE_verified']
    assert all(t['tokens']<=4096 and t['assistant_tokens']>0 for t in audits['turns'])
    raw_oracles=[]
    for path in sorted((out/'native-raw').glob('*/oracle.json')):
        result=read(path)
        assert result['passed'] and result['exit_code']==0 and result['actual_staged']==result['independent_expected_staged_state'] and result['raw_original_workspace_unchanged']
        assert 'Ran ' in result['stderr'] and 'OK' in result['stderr']
        raw_oracles.append({'task':path.parent.name,'sha256':digest(path)})
    assert len(raw_oracles)==12
    stats=read(out/'final-dataset-statistics.json')
    assert stats['total_examples']==len(data) and stats['category_counts']==dict(collections.Counter(r['category'] for r in data))
    assert {s:stats[s.replace('-','_')+'_count'] for s in splits}=={s:len(v) for s,v in splits.items()}
    validation=read(out/'validation-quality-final.json')
    assert validation['passed']
    for s in ('validation','internal-test'):
        for category,record in validation['slices'][s].items():
            values=[r for r in splits[s] if r['category']==category]
            assert record['count']==len(values)>=5 and len({wording(r) for r in values})>=2
            assert len({groups[r['id']] for r in values})>=2 and len({r['difficulty'] for r in values})>=2
    stats.update(final_pair_similarity_flags=len(flags),final_pair_cross_split_flags=0,source_unit_count_definition='Distinct declared provenance units; acquisition corpus counts are reported separately.',source_corpus_counts=dict(collections.Counter(r['source'].get('dataset',r['source']['kind']) for r in data)))
    contract_tags={
        'maintenance':['conditional','temporal'], 'refund':['comparison','conditional'],
        'storage':['temporal','conditional'], 'clinic':['conditional','temporal'],
        'access':['conditional','missing evidence'], 'shipment':['numeric','comparison','missing evidence'],
        'version':['comparison','temporal','missing evidence'], 'course':['numeric','conditional'],
        'water':['numeric','conditional'], 'transport':['numeric','comparison','temporal'],
        'research':['numeric','comparison','missing evidence'], 'incident':['numeric','temporal','missing evidence'],
        'employment':['conditional'], 'migration':['temporal','conditional','missing evidence'],
        'garden':['conditional'], 'museum':['numeric','conditional','missing evidence']}
    rag_review=[]
    for r in data:
        if r['category']!='rag':continue
        if r['id'].startswith('rc-rag-'):tags=['multi-source',*contract_tags[r['id'].removeprefix('rc-rag-')]]
        elif r['id'].startswith('table-'):tags=['structured/table','numeric'];
        elif r['id'].startswith('squad-dual-'):tags=['direct retrieval','multi-source']
        elif r['id'].startswith('squad-followup-'):tags=['direct retrieval','follow-up']
        else:tags=['direct retrieval']
        rag_review.append({'id':r['id'],'families':tags,'oracle_verified':r['quality']['oracle']['passed']})
    stats['RAG_reviewed_capability_counts']=dict(collections.Counter(t for r in rag_review for t in r['families']))
    conflict=[r['id'] for r in data if r['category']=='safety' and r['id'].startswith(('uncertainty-port-conflict','uncertainty-retention-conflict','uncertainty-owner-conflict','uncertainty-revision-authority'))]
    save(out/'RAG-family-review.json',{'examples':rag_review,'counts':stats['RAG_reviewed_capability_counts'],'contradiction_resolution_in_safety_category':conflict,'basis':'Source-bound semantic relation review of frozen two-note contracts; inherited exact source annotations and SQLite oracles for other rows. Category boundaries are reported, not silently changed.'})
    save(out/'final-dataset-statistics.json',stats)
    checks={'unique_exact_split_partition':True,'role_and_tool_binding_integrity':True,'oracle_evidence_paths':oracle_paths,'new_native_oracles':raw_oracles,'whole_family_source_isolation':True,'final_pair_cross_split_flags':0,'negative_history_preserved':True,'original_21_positive_14_negative_bytes_unchanged':True,'previous_namespace_and_zip_unchanged':True,'T01_T15_manifest_unchanged':True,'official_tokenizer_coverage':True,'meaningful_category_validation':True,'base_evaluation_run':False,'training_run':False,'production_modified':False}
    for name in ('final_acquire.py','final_summary.py','final_curate.py','final_check.py'):ast.parse((ROOT/'experiments/dataset_expansion'/name).read_text(encoding='utf-8'))
    save(out/'final-candidate-checks.json',checks)
    report=out/'FINAL_REPORT.md'
    report.write_text(report.read_text(encoding='utf-8')+'## FINAL EXPORT CONSISTENCY AUDIT\n\n'+f'All {len(data)} positives form an exact split partition; 425 negatives/quarantines are preserved. All 12 new native acquisitions have real passing Docker evidence; 11 are selected, with the attempted oracle overwrite excluded. A second pair scan reviewed {len(flags)} retained similarity flags: 290 MBPP source/code-family pairs and five question/synthesis pairs using identical notes. All remain within one split. This does not establish that unflagged latent similarities are absent. Original seed bytes, prior namespace/ZIP and T01–T15 acquisition manifest are unchanged. Full checks are in final-candidate-checks.json. Source counts denote provenance units; source_corpus_counts separately describes upstream acquisition corpora.\n\nRAG capability review: '+json.dumps(stats['RAG_reviewed_capability_counts'])+'. Explicit conflicting-source/revision resolution appears in four safety-category references, listed in RAG-family-review.json; it is not falsely counted as RAG-category data. Missing-evidence qualifications occur within multiple positive RAG answers.\n',encoding='utf-8')
    manifest=read(out/'final-release-manifest.json')
    manifest['artifacts_sha256']={p.name:digest(p) for p in out.iterdir() if p.is_file() and p.name!='final-release-manifest.json'}
    manifest['raw_evidence_sha256']={str(p.relative_to(out)):digest(p) for folder in ('native-raw','summary-raw') for p in (out/folder).rglob('*') if p.is_file()}
    save(out/'final-release-manifest.json',manifest)
    archive=ROOT/'sovereignai-finetuning-final-candidate.zip'
    assert not archive.exists(),'Do not overwrite an existing release archive.'
    shutil.make_archive(str(archive.with_suffix('')),'zip',out.parent,out.name)
    with zipfile.ZipFile(archive) as zipped:
        assert zipped.testzip() is None
        for name,sha in manifest['artifacts_sha256'].items():
            import hashlib
            assert hashlib.sha256(zipped.read(out.name+'/'+name)).hexdigest()==sha
    print(json.dumps({'status':manifest['status'],'positives':len(data),'splits':{s:len(v) for s,v in splits.items()},'archive':str(archive),'archive_sha256':digest(archive),'checks_passed':True}))

if __name__=='__main__':check(Path(sys.argv[1]).resolve())
