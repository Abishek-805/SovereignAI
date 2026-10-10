"""Audit saved acceptance evidence without changing sources, data or raw results."""
from pathlib import Path
import hashlib,json,statistics,difflib

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'evidence/universal-report/20261009'


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return json.loads(path.read_text(encoding='utf-8'))
def trajectories(arm):return [json.loads(line) for line in (OUT/arm/'trajectories.jsonl').read_text(encoding='utf-8').splitlines()]


def main():
    checkpoint=read(OUT/'checkpoint.json')
    checks={name:(ROOT/name).is_file() and digest(ROOT/name)==expected for name,expected in checkpoint['protected_hashes'].items()}
    live_log=read(OUT/'live-worker-log-append-audit.json')
    log_name=live_log['file'];prefix_size=live_log['checkpoint_prefix_bytes']
    prefix=(ROOT/log_name).read_bytes()[:prefix_size]
    log_prefix_preserved=hashlib.sha256(prefix).hexdigest()==checkpoint['protected_hashes'][log_name]
    package=ROOT/'evidence/pretraining-readiness/20261008-173531/colab-package'
    manifest=read(package/'package-manifest.json')
    package_checks={name:digest(package/name)==expected for name,expected in manifest['files'].items()}
    frozen=read(ROOT/'evidence/rag-grounding-remediation/20261009/acceptance-release/execution-manifest.json')
    comparison=ROOT/'evidence/rag-final-comparison/20261009'
    frozen_checks={name:digest(comparison/name)==expected for name,expected in frozen['frozen_comparison_hashes'].items()}
    final_results=ROOT/'rag-final-results.json'
    frozen_checks['rag-final-results.json']=digest(final_results)==frozen['frozen_results_hash']
    integrity={'protected_files':checks,'package_files':package_checks,'frozen_results':frozen_checks,
               'live_worker_log_append':{**live_log,'prefix_unchanged':log_prefix_preserved},
               'passed':all(ok or name==log_name and log_prefix_preserved for name,ok in checks.items()) and all(package_checks.values()) and all(frozen_checks.values()),
               'RUN_TRAIN':False,'dataset_records':710,'splits':[579,65,66],'held_out_contents_inspected':False}
    assert integrity['passed'], 'Protected evidence changed; report must not claim integrity.'
    (OUT/'integrity.json').write_text(json.dumps(integrity,indent=2))
    before=[r for r in trajectories('before') if r['run_id']=='1791503692105833500']
    after=[r for r in trajectories('after') if r['run_id']=='1791504174858258600'][:11]
    assert len(before)==2 and len(after)==11
    calls=lambda r:sum(c['path']=='/v1/chat/completions' for c in r['model_requests'])
    average=after[1]['result']['result']['table_query']['measurements'][0]
    assert average['value']==8.5 and average['denominator']==3 and average['sum']==25.5
    assert len(average['excluded'])==1 and average['excluded'][0]['raw']=='AB'
    assert all(calls(r)==0 for r in after)
    assert after[-1]['error_code']=='needs_input'
    visible=read(OUT/'after/accepted-visible-timings.json')
    final_runtime=read(OUT/'final-loaded-source-audit.json')
    current_visible=read(OUT/'after/current-runtime-visible-timings.json')
    metrics={'before_average_backend_seconds':before[1]['seconds'],'before_average_model_calls':calls(before[1]),
             'after_cold_reader_backend_seconds':after[0]['seconds'],
             'after_warm_average_backend_median_seconds':statistics.median(r['seconds'] for r in after[1:4]),
             'after_cold_reader_visible_ms':visible[0]['milliseconds'],
             'after_warm_average_visible_median_ms':statistics.median(r['milliseconds'] for r in visible[1:4]),
             'after_average_model_calls':0,'before_api_rss_endpoint_bytes':[before[1]['rss_before'],before[1]['rss_after']],
             'final_runtime':{**final_runtime,'cold_visible_ms':current_visible[0]['milliseconds'],
                              'warm_visible_median_ms':statistics.median(r['milliseconds'] for r in current_visible[1:])},
             'after_api_rss_endpoint_bytes':[after[1]['rss_before'],after[1]['rss_after']],
             'resources_note':'RSS endpoints are not peaks; later after arm imported document parsers as well. No fair memory improvement claim.',
             'gpu_representative_snapshot':{'identity':'RTX 3050 A Laptop GPU','used_mib':3207,'total_mib':4094,'peak':False},
             'runtime':{'context':16384,'max_output_tokens':1024,'model':'existing Qwen3.5-4B / sovereign-text','model_server_unchanged':True}}
    documents=[r for r in trajectories('after') if r['run_id']!=after[0]['run_id'] and r['question'].startswith(('What calibration','Why is the calibration'))]
    summaries=[{'question':r['question'],'run_id':r['run_id'],'seconds':r['seconds'],'chat_completion_calls':calls(r),
                'answer':r.get('result',{}).get('answer'),'answer_status':r.get('result',{}).get('result',{}).get('status'),
                'evidence_assessment':r.get('result',{}).get('result',{}).get('checks',{}).get('evidence_assessment'),
                'error':r.get('error')} for r in documents]
    formats=read(OUT/'format-evaluation.json');executor=read(OUT/'executor-evaluation.json')
    parsers=read(OUT/'document-format-evaluation.json');valid=read(OUT/'valid-document-format-evaluation.json')['cases']
    format_matrix={}
    for item in parsers+valid:
        row=format_matrix.setdefault(item['format'],{'parser_positive_probe':False,'grounded_agent_ui':'NOT_VERIFIED','structured_executor':'NOT_VERIFIED'})
        row['parser_positive_probe']|=item['passed']
    for item in formats:
        format_matrix.setdefault(item['format'],{'parser_positive_probe':False,'grounded_agent_ui':'NOT_VERIFIED','structured_executor':'NOT_VERIFIED'})['structured_executor']='PASS' if item['passed'] else 'FAIL'
    format_matrix['.csv']['grounded_agent_ui']='PASS: synthetic identity/measurement questions'
    format_matrix['.txt']['grounded_agent_ui']='PASS: supported interval; missing rationale separately audited'
    changes={name:{'before':expected,'after':digest(ROOT/name),'changed':digest(ROOT/name)!=expected} for name,expected in checkpoint['source_hashes'].items()}
    for name,item in changes.items():
        if item['changed']:
            diff=''.join(difflib.unified_diff((OUT/'rollback'/name).read_text().splitlines(True),(ROOT/name).read_text().splitlines(True),fromfile='rollback/'+name,tofile=name))
            target=OUT/'diffs'/(name+'.diff');target.parent.mkdir(parents=True,exist_ok=True);target.write_text(diff,encoding='utf-8')
    report={'status':'PARTIAL_ACCEPTANCE_PRODUCTION_NOT_VERIFIED','metrics':metrics,'structured_ui_cases':11,
        'structured_ui_successes':10,'structured_ui_expected_ambiguity_abstentions':1,'document_trajectories':summaries,
        'format_executor':{'passed':sum(x['passed'] for x in formats),'total':len(formats)},
        'legacy_executor':{'passed':sum(x['passed'] for x in executor),'total':len(executor)},
        'original_parser_probes':{'passed':sum(x['passed'] for x in parsers),'total':len(parsers)},
        'separate_valid_serialization_probes':{'passed':sum(x['passed'] for x in valid),'total':len(valid)},
        'format_capabilities':format_matrix,'source_changes':changes,'new_files':['rag/analytics.py','tests/test_measurement_analytics.py'],
        'tests':{'backend':207,'frontend_unit':728,'frontend_check':'0 errors, 0 warnings','staged_build':'PASS'},
        'integrity':{'passed':True,'checkpoint_files':len(checks),'exactly_unchanged':sum(checks.values()),'live_log_prefix_preserved':log_prefix_preserved,'package_files':len(package_checks),'frozen_results':len(frozen_checks)},
        'production_activation':'NOT_VERIFIED: automatic approval review rejected previous production restart; only isolated 8096 runtime and staged frontend were exercised.',
        'limitations':['No universal-domain or all-format answer acceptance claim.','Weighted/normalized policies not implemented by this compiler.',
            'Time filters, compound ranking/mean, repeated identities, ambiguous numeric roles require source-bound clarification.',
            'Unstructured model-backed questions remain materially slower than deterministic structured operations.',
            'Name-only/numeric-only identities and multi-document policy synthesis not comprehensively tested.',
            'Reader deadline checked between stages, not preemptive within an OS parser call.',
            'Follow-up receipt scan is bounded to latest 100 receipts; cache bounded by entry count, not bytes.',
            'No private workbook score execution, Docker-generated-code run, training or historical benchmark rerun in this acceptance.']}
    (ROOT/'universal-report-intelligence-report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False))
    matrix='\n'.join(f"| {fmt} | {'PASS' if row['parser_positive_probe'] else 'NOT_VERIFIED'} | {row['structured_executor']} | {row['grounded_agent_ui']} |" for fmt,row in sorted(format_matrix.items()))
    md=f'''# SovereignAI report intelligence acceptance — 2026-10-09

Status: **PARTIAL_ACCEPTANCE_PRODUCTION_NOT_VERIFIED**. Concrete ID, follow-up and measurement defects are repaired and tested in the actual Agent UI on an isolated local runtime. This is not a claim that all report tasks or production acceptance are complete.

## Before and after

Matched rollback/current backend arms used the same synthetic source, actual Agent interface, staged frontend, existing Qwen runtime, context 16384 and output budget 1024. Raw trajectories and failed intermediate probes are preserved. The rollback snapshot predates these edits; it is not the protected historical benchmark.

| Probe | Before | After |
|---|---|---|
| Follow-up overall average | Incorrect per-column averages; {metrics['before_average_backend_seconds']:.3f}s backend, 4 model calls | Correct single mean 8.5 = 25.5/3; {metrics['after_warm_average_backend_median_seconds']:.3f}s backend median, 0 model calls |
| Cold structured reader lookup | 0.036s backend; omitted all-AB measurement | {metrics['after_cold_reader_backend_seconds']:.3f}s backend; all measurement fields retained |
| Visible Agent cold lookup | No paired visible timing recorded | {metrics['after_cold_reader_visible_ms']/1000:.3f}s |
| Visible Agent warm average | No paired visible timing recorded | {metrics['after_warm_average_visible_median_ms']/1000:.3f}s median of three runs |
| Supported 90-day document answer | Draft wrongly rejected despite exact supporting quote | Accepted generated answer after citation-position correction |

The three warm structured requests and one cold-reader request met the requested 5s/15s targets and 25s deadline. Cold here means reader cache empty, not cold model process or OS disk. The user's historical 100-second latency was not reproduced or attributed to a stage. Document-backed generation still invokes the existing planner/generator/evidence checks and is not covered by the sub-second structured result. See JSON for actual model-backed timings and calls.

After the final grounding edit, a separate cold-reader plus three-warm UI replay verified the exact final loaded source hashes: cold visible {current_visible[0]['milliseconds']/1000:.3f}s; warm visible median {statistics.median(r['milliseconds'] for r in current_visible[1:])/1000:.3f}s; warm backend median {final_runtime['warm_backend_median_seconds']:.3f}s. All four used zero model calls. These final confirmation receipts supplement rather than replace the earlier eleven-case acceptance.

## Repairs and preserved contracts

* Exact identifiers are checked against authorized complete source values and actual fields. Safe coordinated shorthand resolves only with source verification; assessment-like prefixes do not override a real source ID.
* Follow-ups use the nearest prior user request, a persisted verified operation receipt, and current authorized source/version evidence. Assistant prose cannot establish the entity population. Singular pronouns after two entities produce a useful ambiguity abstention.
* One shared measurement compiler feeds the existing schema/filter/source-bound executor. It records operation, document/version, identity population, fields, filters, missing policy and completion evidence. No new agent, router, model or orchestration layer was added.
* An overall mean uses measurement cells, with contributing sheet/row/column locators. Metadata is excluded; unresolved numeric roles clarify instead of silently dropping values. AB/blank values are excluded and disclosed unless the user explicitly requests AB as zero. No official grading, normalization or weights are invented.
* Best marks sorts all numeric measurement cells before limiting. Best entities sorts one explicitly named metric and does not confuse entities with marks. Stable source order resolves ties; fewer-than-requested results are disclosed. Missing/non-numeric measurements and numeric-result counts are distinguished from official absence/attendance semantics.
* Generated prose keeps exact quote bindings, current document/version/chunk identity, locators, citation placement and complete claim coverage. Citation-token alignment now tolerates the proven reviewer punctuation mismatch without fuzzy fact matching. Seven added regressions reject changed numbers, uncovered claims, absent/out-of-line citations, false quotations and changed identity punctuation.

## Acceptance evidence

**207 backend tests passed**, including the existing regression suite. Frontend check: 0 errors/0 warnings; 728 frontend unit tests passed. The frontend was built only to an isolated staging directory. Production frontend output was not overwritten.

Eleven structured UI cases: ten successful answers and one expected ambiguity abstention. Cases cover cold ID lookup, three warm overall averages, best five marks, missing measurements, chained all-results follow-up, top students, full two-ID lookup, coordinated shorthand, and ambiguous singular pronoun. The source-independent arithmetic oracle is (7+6+12.5)/3=8.5. AB is retained as a source value, not rewritten.

Final Qwen document probes: the supported interval completed in 13.98s with source-bound claim coverage and status answered. The missing-rationale query completed in 24.60s with status insufficient_evidence and exact source quotations. Its reviewer still incorrectly marked sufficiency true while claim coverage failed; the fail-closed gate prevented an invented explanation, but this reviewer inconsistency remains a documented limitation.

Five structured formats × three asset-domain compiler/executor operations: **15/15 PASS**. Independent legacy invoice executor probes: **9/9 PASS** for count/sum/mean/min/max/filter/percentage/grouped totals. These are executor evidence, not proof that every natural-language planning task passes in the UI. Unit tests additionally cover wide/long layouts, assets, invoices, units, duplicate entities, missing values, stale sources and unsupported constraints.

Original parser probes: {sum(x['passed'] for x in parsers)}/{len(parsers)} passed. Original malformed structured-file failures and a DOCX punctuation-oracle mismatch remain recorded. Nine separately authored valid serialization fixtures passed 9/9; old outcomes were not relabeled. PDF text-layer page extraction and DOCX/PPTX extraction are parser-only; OCR, PDF table analytics and grounded answers across every format are not established.

## Format coverage matrix

| Format | Positive parser probe | Structured compiler/executor | Grounded actual Agent UI |
|---|---|---|---|
{matrix}

## Latency and resources

The repaired structured path records source resolution, SHA-bound loading, identity resolution, deterministic execution, validation and rendering separately. Planning/retrieval/repair model calls are zero for these accepted cases. The existing source-version reader cache is reused; correctness is rechecked before return. Model-backed document queries retain their independent evidence check.

RSS values are recorded before/after each request, not sampled peaks. The later after arm also loaded document parsing components: the different approximately 109MB/265MB endpoints cannot establish a memory regression or improvement attributable to one change. A representative GPU snapshot was 3207/4094MiB on RTX 3050 A Laptop GPU; per-task GPU peaks and end-to-end model RAM are NOT_VERIFIED. No model/runtime settings were tuned.

## Preservation and rollback

Integrity audit: {sum(checks.values())}/{len(checks)} checkpoint-protected files match exactly. The existing running model appended to its worker stderr log; its original {prefix_size} bytes still match the checkpoint hash and are separately preserved. No frozen predictions/results were rewritten. All {len(package_checks)} pretraining package files and {len(frozen_checks)} authoritative frozen result artifacts match exactly. The 710-record dataset and 579/65/66 split, readiness receipts and frozen comparisons remain unchanged. RUN_TRAIN is false. No T01–T15 contents were inspected; no training, adapters, deployment, GGUF conversion or generated host execution occurred.

Rollback originals, SHA-256 checkpoint, source-only diffs and raw before/after trajectories are under `evidence/universal-report/20261009/`. Per-runtime source copies let results be tied to the code actually loaded. `experiments/rag_v2/universal_app.py` runs isolated fixtures through the real app. `experiments/rag_v2/universal_report_audit.py` regenerates this report from preserved evidence and refuses to claim integrity if protected hashes differ. Backend reproduction: `.app-venv/Scripts/python.exe -m pytest tests -q`.

## Remaining gates and product status

Production activation remains **NOT_VERIFIED**. Earlier automatic approval review rejected stopping/restarting the production service; no alternative kill mechanism was used. The existing production API and old built frontend remained running. A normal user-controlled application restart/build activation is still required before these source changes can be claimed as production behavior.

Weighted/normalized source policies, trend/difference/ratio operations, complex time filters, repeated-entity aggregation, arbitrary name/numeric identities and multi-document policy synthesis are not comprehensively completed by this change. Unknown policy/field contracts clarify; no fabricated success is substituted. The receipt scan is bounded to 100 entries; the reader cache is bounded by entries rather than bytes. The deadline is checked between stages and does not preempt a blocked OS parser. These limits must be resolved or tested before claiming universal report intelligence.

The evidence supports retaining the existing retrieval stack and using verified structured operations for exact-value arithmetic. It does not support replacing it with Gemma or claiming that embeddings fix identity, aggregation or operation semantics. No new embedding bake-off was run in this pass.
'''
    (ROOT/'universal-report-intelligence-report.md').write_text(md,encoding='utf-8')
    print(json.dumps({'integrity':integrity['passed'],'structured_cases':11,'tests':207,'report':'universal-report-intelligence-report.md','metrics':metrics},indent=2))


if __name__=='__main__':main()
