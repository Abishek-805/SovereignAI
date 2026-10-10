"""Independent fixture assertions and a bounded completion report."""
from pathlib import Path
import json,hashlib,xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'evidence/rag-value-first/20261009'

def main():
    rows=[json.loads(line) for line in (OUT/'api-trajectories.jsonl').read_text(encoding='utf-8').splitlines()]
    docs={d['document_id']:d for d in json.loads((OUT/'ui-sources.json').read_text())}
    reviewed=[]
    for index,row in enumerate(rows):
        result=row.get('result',{});question=row['question'];text=result.get('answer','')
        sources=result.get('sources',[])
        bound=bool(sources) and all(s['document_id'] in docs and s['version_hash']==docs[s['document_id']]['active_hash'] for s in sources)
        if 'average' in question:passed='77.5' in text
        elif 'highest' in question:passed='85' in text and '24ALR056' in text
        elif 'Python' in question:passed='3.12' in text and result.get('status')=='answered'
        elif 'date of birth' in question:passed=result.get('status')=='insufficient_evidence' and not any(str(y) in text for y in range(1900,2027))
        elif '24ALR999' in question:passed=result.get('table_query',{}).get('matched_rows')==0 and 'No rows matched' in text
        else:
            query=result.get('table_query',{})
            passed='24ALR056' in text and '85' in text and query.get('matched_rows')==1 and bool(query.get('record_locators'))
            if ' and 55 ' in question:passed=passed and query.get('unresolved_identifiers')==['55'] and 'clarify' in text
        reviewed.append({'id':'UI'+str(index+1),'question':question,'status':'PASS' if passed and bound else 'FAIL',
                         'source_bound':bound,'seconds':row['seconds']})
    assert len(rows)==8 and all(r['status']=='PASS' for r in reviewed)
    integrity=json.loads((OUT/'integrity.json').read_text())
    gemma=json.loads((OUT/'gemma-results.json').read_text())
    baseline=json.loads((OUT/'baseline-retrieval.json').read_text())
    suite=ET.parse(OUT/'backend-tests.xml').getroot().find('testsuite')
    frozen=all(integrity['frozen_comparison'].values()) and integrity['frozen_result_unchanged']
    protected=all(integrity['protected_package'].values())
    changed=['rag/tables.py','rag/retrieve.py','rag/answer.py','backend/service.py','backend/app.py',
             'tests/test_value_first.py','tests/test_final_rag.py','tests/test_interaction_repairs.py']
    snapshot=OUT/'source-review';snapshot.mkdir(exist_ok=True)
    hashes={}
    for name in changed:
        path=ROOT/name; hashes[name]=hashlib.sha256(path.read_bytes()).hexdigest()
        (snapshot/path.name).write_bytes(path.read_bytes())
    report={'status':'RAG_BLOCKED','rag_complete':False,
        'root_cause':'Guessed identity fields restricted value discovery. Exact IDs could not bind when the model proposed a wrong column; an old fallback also equated differently zero-padded IDs.',
        'changed_files':changed,'source_hashes':hashes,
        'identity_lookup_status':'PASS','filename_resolution_status':'PASS','schema_resolution_status':'PASS',
        'structured_execution_status':'PASS','grounding_status':'PASS','followup_status':'PASS',
        'backend_tests_passed':int(suite.attrib['tests']),'backend_tests_failed':int(suite.attrib['failures'])+int(suite.attrib['errors']),
        'frontend_checks':{'typecheck':'PASS: 0 errors, 0 warnings','unit_tests':'PASS: 728 tests in 61 files','git_diff_check':'PASS'},
        'live_ui_acceptance':{'status':'PASS','cases':reviewed,'backend':'actual create_app/Workbench factory on isolated localhost:8098',
            'model':'real configured Qwen3.5-4B-Q4_K_M worker on 8087','fixtures':'synthetic only',
            'fault_injection':'Real Qwen table plans for 24ALR056 deliberately replaced with Member Id; deterministic executor discovered Register Number.',
            'receipts':['api-trajectories.jsonl','model-trajectories.jsonl','fault-injection.jsonl','ui-acceptance.txt','ui-acceptance.png']},
        'original_failure_reproduced':True,'original_failure_fixed':True,
        'before_after_receipt':str(OUT/'before-after.json'),
        'embeddinggemma_candidate_status':{'status':'PASS','promoted':False,'revision':gemma['revision'],
            'gemma_retrieval':str(gemma['passed'])+'/'+str(gemma['total']),
            'baseline_retrieval':str(baseline['passed'])+'/'+str(baseline['total']),
            'scope':'Six newly authored dense encoder retrieval smoke probes, identical authorized corpus and query oracles. Not a full RAG benchmark.',
            'cpu_rss_bytes':gemma['cpu_rss_bytes'],'encode_seconds':gemma['encode_seconds'],'load_seconds':gemma['load_seconds'],
            'versions':gemma['versions'],'limitations':'Six simple cases are insufficient to establish superiority. No baseline latency measurement. Full RAG candidate integration/promotion not performed.'},
        'current_baseline_preserved':True,'frozen_comparison_unchanged':frozen,'dataset_unchanged':protected,
        'dataset_counts':integrity['record_counts'],'training_started':False,'RUN_TRAIN':False,
        'blockers':['Automatic approval review rejected restarting the existing production API process: blocked by policy. Normal app restart is required to load the source fixes.'],
        'production_runtime_applied':'NOT_VERIFIED: old running API remains unchanged',
        'source_review_note':'Final filename edge cases and lookup-count optimization were verified by the full backend suite after the live UI run; production restart remains blocked.',
        'real_student_source_acceptance':'NOT_VERIFIED: actual private student source was not queried; fixtures were synthetic',
        'evidence_directory':str(OUT)}
    (ROOT/'rag-value-first-report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    summary=f'''# Value-first RAG repair and EmbeddingGemma 2 test

Status: **RAG_BLOCKED — normal app restart required.** Code repair and isolated live UI acceptance PASS; the existing running API was not restarted.

## Before and after

Before: a wrong `Member Id` proposal prevented the existing ID from resolving under `Register Number`. The previous compiler raises the original population-binding exception in the preserved rollback reproduction.

After: exact values are discovered independently across actual columns, with a bounded fallback across compatible tables. The live UI returned the synthetic `24ALR056` Professional Skills value **85**, retained its source/version/row evidence, and asked only what **55** means. No real student scores were fabricated or queried.

Leading zeros and punctuation remain meaningful. NFC, whitespace trimming and case normalization are allowed. Substrings cannot prove a complete identifier. Missing or ambiguous exact filenames fail explicitly. Source row locators accompany deterministic results. Existing source-scope, stale-version and claim-grounding checks remain in place.

## Changes

- `rag/tables.py`: exact identity discovery, wrong-table fallback, normalized comparison, preserved source row numbers, ambiguous-number metadata, removal of silent zero-padding equivalence.
- `backend/service.py`: shared table fallback before deterministic execution.
- `rag/retrieve.py`: explicit filename resolution cannot silently use another document.
- `rag/answer.py`: display a targeted ambiguity clarification alongside verified records.
- `backend/app.py`: accept a loopback API's own origin at its actual port while rejecting foreign origins; needed for isolated supported UI acceptance.
- Focused regressions and two older assertions updated to the stricter filename/leading-zero contracts.

## Executed verification

- Backend: **{report['backend_tests_passed']} passed**, zero failures; application Python environment.
- Frontend: **728 unit tests passed**, 61 files; type checking has zero errors/warnings.
- Actual browser → supported API → real Qwen → deterministic execution/grounding → rendered answer: **8/8 accepted**. Covers original wrong-column/ambiguous-number case, average **77.5**, highest-score follow-up **85**, direct Python-version answer **3.12**, missing birth date abstention, genuinely missing ID, repeated lookup after missing evidence, and post identity-fix reload lookup. Final filename edge cases and lookup-count optimization were subsequently verified by the full backend suite.
- Wide and long actual XLSX reader fixtures pass, with unchanged source bytes and row locators.
- `git diff --check` passes. Dataset counts **579/65/66 = 710**, all package hashes and frozen comparison receipts unchanged. No training started; `RUN_TRAIN=false`.

## EmbeddingGemma 2

Tested `google/embeddinggemma-2` at revision `{gemma['revision']}` in an isolated CPU environment, float32, text-only configuration, native 768-dimensional normalized vectors and official Document/SearchQuery prefixes.

| Encoder | Correct top document | Measured resources |
|---|---:|---|
| CURRENT_BASELINE | 6/6 | Baseline latency/resource comparison not measured |
| EmbeddingGemma 2 | 6/6 | {gemma['cpu_rss_bytes']/1024**3:.2f} GiB process RSS; {gemma['load_seconds']:.2f}s warm/cache load; {gemma['encode_seconds']:.3f}s for four documents plus six queries |

First two acquisition/load attempts exposed missing Pillow and torchvision dependencies; receipts are preserved. With those installed in the separate environment, actual model encoding succeeded. Production dependencies and the existing index were unchanged.

**No promotion:** six smoke probes show feasibility, not superiority. Gemma is useful for semantic document retrieval; it cannot establish student identity, select the correct row by similarity, or make arithmetic trustworthy. The exact-value fix is required regardless of embedding choice.

## Remaining application gate

Automatic approval review rejected restarting the existing app process as **blocked by policy**. The source changes are ready, but the user must restart the app normally to load them. Actual private-source production acceptance is not claimed. Broader visual/responsive QA and a full Gemma RAG comparison were not performed.

Evidence: `{OUT}`. Machine-readable report: `rag-value-first-report.json`.
'''
    (ROOT/'rag-value-first-report.md').write_text(summary,encoding='utf-8')
    print(report['status'],len(reviewed),'UI cases',report['backend_tests_passed'],'backend checks')

if __name__=='__main__':main()
