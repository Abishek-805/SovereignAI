"""Redacted source proof and immutable evidence audit; no held-out contents inspected."""
from pathlib import Path
import json,hashlib,time
from backend.settings import Settings
from rag.store import Store
from rag.tables import load_tables,exact_identity_columns
from rag.identifiers import compile_exact_lookup

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'evidence/agent-rag-critical/20261009'
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    settings=Settings();store=Store(settings.data_dir/'index.sqlite')
    fingerprint='a2671fe3d41e8b6c76fc0aabb2b6bd52db289cfe090102085a2844344d76b9ad'
    start=time.perf_counter();matches=[];observed=[];available={}
    for doc in store.documents():
        if doc.get('source_extension') not in {'.csv','.xlsx','.tsv','.json','.jsonl'}:continue
        path=settings.sources_dir/(doc['active_hash']+doc['source_extension'])
        if not path.is_file():continue
        for table in load_tables(path):
            available['T'+str(len(available)+1)]=(doc,table)
            counts=exact_identity_columns(table,['24ALR056','24ALR055'])
            if counts:matches.append({'document_id':doc['document_id'],'hash':doc['active_hash'],
                'table':table['name'],'actual_identity_counts':counts})
            if fingerprint in {table['name'],doc['active_hash']}:
                observed.append({'document_id':doc['document_id'],'hash':doc['active_hash'],
                    'table':table['name'],'columns':table['columns'],'rows':len(table['records']),
                    'actual_identity_counts':counts,'proposed_field_exists':'Member Id' in table['columns']})
    first='24ALR056 and 24ALR055 professional skill training test results?'
    plans=[]
    for question,history in [(first,[]),('24ALR056 and 55 professional skill training test results?',['User: '+first])]:
        plan=compile_exact_lookup(question,available,history)
        plans.append({'compiled':plan is not None,'table':available[plan['table']][1]['name'] if plan else None,
            'document_id':available[plan['table']][0]['document_id'] if plan else None,
            'columns':plan['columns'] if plan else [],'identity_resolution':plan['identity_resolution'] if plan else None})
    (OUT/'source-proof.json').write_text(json.dumps({'screenshot_source':observed,'authorized_exact_matches':matches,
        'real_source_compilation':plans,'real_scores_executed':False,
        'scan_seconds':time.perf_counter()-start,'scores_recorded':False},indent=2))
    old=json.loads((ROOT/'evidence/rag-grounding-remediation/20261009/acceptance-release/execution-manifest.json').read_text())
    frozen={name:digest(ROOT/'evidence/rag-final-comparison/20261009'/name)==expected for name,expected in old['frozen_comparison_hashes'].items()}
    package=ROOT/'evidence/pretraining-readiness/20261008-173531/colab-package'
    manifest=json.loads((package/'package-manifest.json').read_text())
    protected={name:digest(package/name)==expected for name,expected in manifest['files'].items()}
    result={'frozen_comparison':frozen,'frozen_result_unchanged':digest(ROOT/'rag-final-results.json')==old['frozen_results_hash'],
        'protected_package':protected,'training_started':False,'RUN_TRAIN':False}
    (OUT/'integrity.json').write_text(json.dumps(result,indent=2))
    assert all(frozen.values()) and all(protected.values()) and result['frozen_result_unchanged']
    print(json.dumps({'screenshot_tables':len(observed),'matched_tables':len(matches),'protected':True}))
if __name__=='__main__':main()
