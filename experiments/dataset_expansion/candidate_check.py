"""Final consistency checks for a blocked curation candidate."""
import ast,collections,json,shutil,sys,zipfile
from pathlib import Path
from experiments.dataset_expansion.prepare import ROOT,rows,save,digest

def main(out):
    data=rows(out/'positive-trajectories.jsonl');byid={r['id']:r for r in data};splits={s:rows(out/(s+'.jsonl')) for s in ('train','validation','internal-test')}
    ids=[r['id'] for v in splits.values() for r in v];assert len(ids)==len(set(ids))==len(data) and set(ids)==set(byid)
    for r in data:
        pending=set()
        for m in r['messages']:
            pending.update(c['id'] for c in m.get('tool_calls',[]))
            if m['role']=='tool':assert m['tool_call_id'] in pending;pending.remove(m['tool_call_id'])
        assert not pending
    report=json.loads((out/'split-assignment-final.json').read_text())
    report['counts']={s:len(v) for s,v in splits.items()};report['category_counts']={s:dict(collections.Counter(r['category'] for r in v)) for s,v in splits.items()}
    report['example_clusters']={k:v for k,v in report['example_clusters'].items() if k in byid};save(out/'split-assignment-final.json',report)
    locations={r['id']:s for s,v in splits.items() for r in v};families=collections.defaultdict(set)
    for k,v in report['example_clusters'].items():families[v].add(locations[k])
    assert all(len(v)==1 for v in families.values())
    stats=json.loads((out/'dataset-statistics-final.json').read_text());stats['split_counts']=report['counts'];stats['split_category_counts']=report['category_counts'];save(out/'dataset-statistics-final.json',stats)
    manifests=json.loads((out/'historical-manifest.json').read_text());previous=Path(manifests['previous_namespace']);assert all(digest(previous/p)==sha for p,sha in manifests['sha256'].items())
    assert digest(ROOT/'sovereignai-finetuning-expanded.zip')==manifests['previous_package_sha256']
    checks={'unique_split_partition':True,'exported_tool_bindings':True,'proposed_cluster_isolation':True,'previous_namespace_and_package_unchanged':True,'training_allowed':False,'base_evaluation_run':False,'t01_t15_inspected_or_executed':False,'syntax':True}
    for name in ('candidate_repair.py','curate.py','candidate_check.py'):ast.parse((ROOT/'experiments/dataset_expansion'/name).read_text(encoding='utf-8'))
    save(out/'candidate-checks.json',checks)
    manifest=json.loads((out/'release-manifest.json').read_text());manifest['artifacts_sha256']={p.name:digest(p) for p in out.iterdir() if p.is_file() and p.name!='release-manifest.json'};save(out/'release-manifest.json',manifest)
    archive=shutil.make_archive(str(ROOT/'sovereignai-finetuning-release-candidate'),'zip',out.parent,out.name)
    with zipfile.ZipFile(archive) as zipped:assert zipped.testzip() is None
    print(json.dumps({'checks':checks,'counts':stats['current_counts'],'splits':report['counts'],'archive':archive}),flush=True)

if __name__=='__main__':main(Path(sys.argv[1]).resolve())
