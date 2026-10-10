"""Audit actual Agent receipts without treating a planner claim as evidence."""
from pathlib import Path
import json,hashlib,xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'evidence/agent-rag-critical/20261009'
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    rows=[json.loads(line) for line in (OUT/'agent-trajectories.jsonl').read_text().splitlines()]
    run_id=rows[-1]['run_id'];final=[row for row in rows if row.get('run_id')==run_id]
    assert len(final)==3,'Final source-hashed run must contain both screenshot requests and missing-ID case'
    runtime=json.loads((OUT/'runtimes'/run_id/'runtime.json').read_text())
    assert all(digest(ROOT/name)==expected for name,expected in runtime['source_hashes'].items())
    reviewed=[]
    for index,row in enumerate(final):
        result=row['result']['result'];query=result['table_query'];identity=query['identity_resolution']
        expected=['24ALR999'] if index==2 else ['24ALR056','24ALR055']
        assert identity['canonical']==expected
        assert query['matched_rows']==(0 if index==2 else 2)
        assert result['checks']['citation_ids_valid'] and result['checks']['numeric_claims_supported']
        assert result['counters']=={'model_calls':0,'tool_calls':1,'retrieval_calls':0,'repair_attempts':0}
        assert row['observed_model_calls']==0 and row['model_runtime_requests']==[]
        assert row['seconds']<15
        if index==1:assert identity['provenance'][1]['origin']=='immediate_user_antecedent'
        if index!=2:assert [r['Professional Skills'] for r in query['records']]==['85','70']
        else:assert query['missing_entities']==['24ALR999'] and '24ALR999' in result['answer']
        reviewed.append({'question':row['question'],'status':'PASS','seconds':row['seconds'],
            'timings':result['timings'],'counters':result['counters'],'runtime_requests':[],
            'canonical':identity['canonical'],'identity_column':identity['matches'][0]['identity_column'] if identity['matches'] else 'Register Number',
            'matched_rows':query['matched_rows'],'record_locators':query['record_locators'],
            'sources':[{key:source[key] for key in ('document_id','version_hash','chunk_id','display_name')} for source in result['sources']]})
    integrity=json.loads((OUT/'integrity.json').read_text())
    assert all(integrity['frozen_comparison'].values()) and all(integrity['protected_package'].values())
    source=json.loads((OUT/'source-proof.json').read_text())
    assert all(plan['compiled'] and plan['table']=='All' for plan in source['real_source_compilation'])
    suite=ET.parse(OUT/'backend-full.xml').getroot().find('testsuite')
    assert int(suite.attrib['failures'])+int(suite.attrib['errors'])==0
    changed=['backend/service.py','rag/tables.py','rag/identifiers.py','rag/answer.py','tests/test_agent_exact_lookup.py',
        'experiments/rag_v2/agent_exact_app.py','experiments/rag_v2/agent_exact_audit.py','experiments/rag_v2/agent_exact_report.py']
    gates={'exact_ids':'PASS','contextual_shorthand':'PASS','filename_scope':'PASS','source_schema':'PASS',
        'table_execution':'PASS','grounding_regressions':'PASS','live_controlled_agent_ui':'PASS',
        'simple_lookup_latency':'PASS','frozen_comparison':'PASS','training_integrity':'PASS',
        'production_loaded_new_code':'NOT_VERIFIED','private_source_score_ui':'NOT_VERIFIED',
        'original_100_second_stage_attribution':'NOT_VERIFIED','general_agent_stage_timing':'PARTIAL'}
    coverage=[
        ('two full IDs','test_full_ids_and_context_shorthand'),('contextual shorthand','test_full_ids_and_context_shorthand'),
        ('wrong identity proposal','test_wrong_identity_proposal_discovers_values'),('non-leading identity','test_full_ids_and_context_shorthand'),
        ('leading zeros','test_numeric_string_id_in_lookup'),('absent IDs','test_missing_id_and_prefix_are_not_fuzzy_matches'),
        ('duplicate assessment rows','test_long_format_duplicate_identity_assessment_filter'),('wrong/ambiguous filename','test_explicit_file_scope_missing_and_duplicate'),
        ('assessment/score versus identity','test_assessment_code_does_not_enter_canonical_ids'),('unrelated history','test_shorthand_does_not_inherit_unrelated_or_assistant'),
        ('cohort replacement','test_replacement_not_union'),('unsupported planner IDs','test_complete_lookup_uses_executor_citations_and_no_model'),
        ('current-turn authority','test_replacement_not_union'),('wide format','test_source_named_wide_summary_beats_unrelated_table'),
        ('long format','test_long_format_duplicate_identity_assessment_filter'),('correct two-ID results','test_full_ids_and_context_shorthand'),
        ('row references','test_full_ids_and_context_shorthand'),('bounded failure/no model retry','test_configured_deadline_rejects_without_model'),
        ('safe reader cache reuse','test_cached_reader_invalidates_source_change'),('configured timing','test_complete_lookup_uses_executor_citations_and_no_model'),
        ('arithmetic/aggregation/top-k/grounding','full tests directory'),('frontend final rendering','actual Agent UI DOM/screenshots; existing 728 frontend unit tests')]
    report={'status':'RAG_BLOCKED','rag_complete':False,'gates':gates,'changed_files':changed,
        'root_causes':[
            'The exact screenshot fingerprint resolves to an unrelated four-row Name/Group/Score/Result table. Both requested IDs are absent there, while seven sheets of another authorized workbook contain both IDs in Member Id.',
            'compile_outcome_query inferred only current-turn alphanumeric identifiers and rejected the planner expanded shorthand before validating its immediate user-authored antecedent.',
            'Agent planned the workflow before ask(force_documents=True); table planning and identity binding could add further generation/repair calls.',
            'Deterministic table presentation still called model tokenization endpoints. It now validates and renders the executor result without those endpoints.'],
        'before_after_latency':{'before_seconds':None,'before_user_report_seconds':'almost 100','before_instrumented':False,
            'original_slow_stage':'NOT_VERIFIED: no original per-stage runtime receipt',
            'after_agent_seconds':[row['seconds'] for row in reviewed],'measurement':'backend Agent job wall clock; UI rendering independently observed'},
        'live_agent_acceptance':{'status':'PASS','host':'127.0.0.1:8099','source':'controlled synthetic fixture only',
            'path':'AgentChat.svelte -> /agent/jobs -> run_auto_agent -> shared exact lookup -> execute_query -> answer citation/value validation -> /coding/jobs poll -> Agent finish rendering',
            'cases':reviewed,'run_id':run_id,'runtime':runtime},
        'regression_coverage':[{'scenario':i+1,'name':name,'evidence':evidence,'status':'PASS'} for i,(name,evidence) in enumerate(coverage)],
        'backend':{'passed':int(suite.attrib['tests']),'failed':0,'command':'.app-venv/Scripts/python.exe -m pytest tests -q'},
        'frontend':{'unit_tests_passed':728,'test_files':61,'svelte_errors':0,'svelte_warnings':0},
        'rollback':str(OUT/'rollback'),'raw_receipts':str(OUT/'agent-trajectories.jsonl'),
        'source_proof':str(OUT/'source-proof.json'),'protected_integrity':integrity,
        'CURRENT_BASELINE_preserved':True,'embeddinggemma_mandatory':False,
        'dataset_records':710,'dataset_split':{'train':579,'validation':65,'internal_test':66},
        'training_started':False,'RUN_TRAIN':False,
        'blockers':['Existing production API PID 20848 predates the repairs. Prior automatic approval review rejected its restart as blocked by policy; no alternative termination was attempted.',
                    'Original 100-second attempt has no preserved per-stage timing. Its latency cannot honestly be assigned to retrieval or model generation.'],
        'limitations':['Source records are cached in memory (128 version/mtime/size-keyed reader entries), not a new persistent identity database. Large heterogeneous libraries need further memory/latency testing.',
            'Deadline is checked between synchronous read/execution stages; it is not a hard preemption mechanism for an OS-blocked read.',
            'Non-literal/ambiguous tasks retain the existing model planner. Their full per-stage timing and recovery behavior were not exhaustively evaluated here.',
            'Real source schema, exact IDs, counts, and selected summary were inspected read-only; private scores were not executed/rendered in the production UI.',
            'Scenario 22 has observed real UI proof plus existing frontend unit coverage; no new automated browser-runner spec was added.']}
    (ROOT/'agent-rag-critical-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    lines=['# SovereignAI critical Agent RAG repair','',
        '**Status: RAG_BLOCKED.** The two screenshot requests pass through the actual Agent UI on an isolated instance of the application. Production has not loaded the new code.',
        '', '## Proven causes','',*['- '+cause for cause in report['root_causes']],
        '', 'The first error was a wrong-source failure, not proof that either student ID was missing. The matching workbook uses Member Id; that field is valid there. The unrelated fingerprint table has no such field or IDs. The source-proof receipt records schema, source hashes, counts, and row references without student scores.',
        '', '## Changes','',
        'A shared typed resolution retains current-turn IDs, immediate user-antecedent shorthand provenance, canonical IDs, unresolved values, source/version/row references, diagnostics, and timings. The existing reader searches values before field guesses. Exact result lookups bind real wide/long assessment data and use the existing read-only executor. Genuine schema/source ambiguity still requires clarification.',
        '', 'Agent and Chat share this lookup. A resolved simple lookup skips workflow/table generation, identity binding, embeddings, reranking, and repair calls. The remaining model table path is restricted to sources that contain exact requested identities; model cohort proposals cannot replace the authoritative canonical set.',
        '', 'No model, router controller, database, training run, or mandatory embedding dependency was added. Source-version validation and deterministic citation/value checks remain in place. Missing identity and missing assessment responses are distinct; flat-file headings show the display filename rather than an opaque hash.',
        '', 'Changed files:', '',*['- `'+name+'`' for name in changed],
        '', '## Measured Agent acceptance','',
        '| Request | Result | Backend seconds | Generation calls | Runtime requests | Tool/retrieval/repair calls |',
        '|---|---|---:|---:|---:|---|']
    for i,row in enumerate(reviewed):
        lines.append('| '+['Two full IDs','Immediate-context 55 shorthand','Absent 24ALR999'][i]+' | PASS | '+f"{row['seconds']:.4f}"+' | 0 | 0 | 1 / 0 / 0 |')
    lines+=['','Both ordinary requests return Register Number 24ALR056 = 85 and 24ALR055 = 70 for Professional Skills in the **synthetic fixture**. Those scores are not claims about real students. Shorthand provenance verifies the previously explicit 24ALR055 in the same authorized fixture. The missing-ID request names 24ALR999 and cites the checked source.',
        '', 'Warm fixture target: 15 seconds; configured deadline: 25 seconds (`SOVEREIGN_EXACT_LOOKUP_SECONDS`). All three observed jobs pass. The original near-100-second time was user-reported, not newly instrumented. No fabricated before/after speedup ratio is reported. Detailed per-stage monotonic measurements and counters are in the JSON report.',
        '', '![Actual Agent acceptance]('+ (OUT/'ui-acceptance-final.png').as_posix()+')',
        '', '## Gates','', '| Gate | Status |','|---|---|',*['| '+name+' | '+status+' |' for name,status in gates.items()],
        '', '## Regression evidence','',f"Full backend: **{report['backend']['passed']} passed, 0 failed**. Frontend: **728 tests across 61 files passed**, Svelte/TypeScript **0 errors, 0 warnings**. All 22 requested areas have evidence below; the frontend rendering gate uses actual browser observation rather than a new automated browser spec.",
        '', '| Scenario | Evidence |','|---|---|',*['| '+str(i+1)+'. '+name+' | `'+evidence+'` |' for i,(name,evidence) in enumerate(coverage)],
        '', 'The actual matching production workbook compiles to its source-bound All summary for both requests, retaining both IDs and actual WAT/CAT columns. This is read-only schema/identity proof, not a production private-score UI acceptance claim.',
        '', '## Reproducibility and preservation','',
        'Rollback: `'+str(OUT/'rollback')+'`. Final tested runtime: `'+run_id+'`. Exact loaded Python source copies and hashes are preserved under `runtimes/`. All staged Agent receipts are appended in `agent-trajectories.jsonl`; prior successes/failures and frozen comparisons were not overwritten.',
        '', 'Protected package and frozen comparison hashes PASS. The dataset remains 710 records, split 579/65/66. No T01–T15 contents were inspected. `training_started=false`; `RUN_TRAIN=false`. CURRENT_BASELINE remains selected; E5/Gemma were not promoted or made mandatory.',
        '', '## Remaining blockers and limits','',*['- '+item for item in report['blockers']+report['limitations']],
        '', 'A normal SovereignAI restart is required to load the repairs in the existing production app. Do not interpret isolated UI PASS as production acceptance or universal RAG completion.']
    (ROOT/'agent-rag-critical-report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({'status':report['status'],'backend_passed':report['backend']['passed'],'agent_seconds':[r['seconds'] for r in reviewed]}))

if __name__=='__main__':main()
