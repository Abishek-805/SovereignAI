"""Preserve before evidence and verify protected receipts without held-out inspection."""
from pathlib import Path
import json,hashlib
from rag.tables import _table,compile_outcome_query,bind_selection_request,execute_query
from backend.contracts import WorkbenchError
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'evidence/rag-value-first/20261009'

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    namespace={'__name__':'value_first_before'}
    exec((OUT/'rollback/tables.py').read_text(),namespace)
    table=_table('Professional Skills',[['Register Number','Result'],['24ALR056','PASS']])
    intent={'operation':'count','scope':'all','result_values':['PASS'],'outcome':'pass',
        'entity_values':['24ALR056'],'entity_column':'Member Id'}
    source={'T1':({'document_id':'synthetic'},table)}
    try:namespace['compile_outcome_query'](intent,source,'Count passes for 24ALR056')
    except WorkbenchError as error:before={'status':'FAIL','error':str(error),'code':error.code}
    else:before={'status':'UNEXPECTED_PASS'}
    fixed=compile_outcome_query(intent,source,'Count passes for 24ALR056')
    after=execute_query(table,fixed)
    (OUT/'before-after.json').write_text(json.dumps({'before':before,'after':after,'passed':before['status']=='FAIL' and after['value']==1},indent=2))
    old=json.loads((ROOT/'evidence/rag-grounding-remediation/20261009/acceptance-release/execution-manifest.json').read_text())
    frozen=old['frozen_comparison_hashes']
    verified={name:digest(ROOT/'evidence/rag-final-comparison/20261009'/name)==expected for name,expected in frozen.items()}
    frozen_result=digest(ROOT/'rag-final-results.json')==old['frozen_results_hash']
    package=ROOT/'evidence/pretraining-readiness/20261008-173531/colab-package'
    manifest=json.loads((package/'package-manifest.json').read_text())
    protected={name:digest(package/name)==expected for name,expected in manifest['files'].items()}
    counts={name:sum(1 for _ in (package/name).open(encoding='utf-8')) for name in ['train.adjusted.jsonl','validation.adjusted.jsonl','internal-test.adjusted.jsonl']}
    (OUT/'integrity.json').write_text(json.dumps({'frozen_comparison':verified,'frozen_result_unchanged':frozen_result,
        'protected_package':protected,'record_counts':counts,'RUN_TRAIN':False,'training_started':False},indent=2))
    assert all(verified.values()) and frozen_result and all(protected.values())
    print('Before failure reproduced; after PASS; frozen comparison and training package unchanged.')

if __name__=='__main__':main()
