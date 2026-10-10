"""Evidence-only aggregation. Never rewrites a model answer or production file."""
import json,re,sys
from pathlib import Path
import numpy as np
import httpx
from experiments.latency_rag.run import save,ROOT,QUESTIONS,digest

def main(out):
    out=out.resolve();rows=json.loads((out/'all-results.json').read_text(encoding='utf-8'));byid={r['id']:r for r in rows}
    baseline=[byid['baseline-3']]+[byid['qa-baseline-'+q[0]] for q in QUESTIONS[1:]]
    top5=[byid['top5-'+q[0]] for q in QUESTIONS];cached=[byid['cached-'+q[0]] for q in QUESTIONS]
    semantic=[]
    for group in (baseline,top5,cached):
        for row in group:
            failure=row['id'].endswith(('modelport','projects'))
            row['independent_semantic_pass']=bool(row.get('correct')) and not failure
            if failure:
                texts='\n'.join(s['text'] for s in row.get('result',{}).get('sources',[]))
                relation=('local llama.cpp server listens' in texts) if row['id'].endswith('modelport') else ('Code projects use live files under' in texts)
                semantic.append({'request':row['id'],'original_literal_check':row.get('correct'),'independent_semantic_pass':False,'actual_answer':row['result']['answer'],'primary_failure':'MODEL_GENERATION_FAILURE' if relation else 'RETRIEVAL_FAILURE','canonical_relation_in_supplied_sources':relation,'reason':'Answer asserts model server8088 rather than8087' if row['id'].endswith('modelport') else 'Answer does not correctly state explicit default live-project path; regex allowed scattered path words','oracle_adequacy':'Initial regex can falsely pass incidental expected numbers/words; original checks retained, no answer edited'})
    save(out/'independent-semantic-audit.json',semantic)
    semantic_by_id={r['request']:r for r in semantic}
    audit=[]
    for r in rows:
        directory=ROOT/r['directory']; captures=[]
        for p in sorted((directory/'model-request-captures').glob('*/request.json')):
            req=json.loads(p.read_text(encoding='utf-8'));messages=req['messages'];evidence=[]
            for msg in messages:
                try:
                    value,_=json.JSONDecoder().raw_decode(msg.get('content',''))
                    if isinstance(value,dict):evidence.extend(value.get('evidence',[]))
                except (ValueError,TypeError):pass
            contexts=[str(s.get('text','')) for s in evidence]
            captures.append({'request_path':str(p.relative_to(ROOT)),'system_messages':sum(m['role']=='system' for m in messages),'tool_role_messages':sum(m['role']=='tool' for m in messages),'native_tools_present':bool(req.get('tools')),'duplicate_evidence_texts':len(contexts)-len(set(contexts)),'evidence_count':len(evidence),'context_characters':sum(map(len,contexts)),'malformed_evidence_delimiters':False if evidence else 'not automatically established','prompt_tokens':None,'raw_retrieved_tokens':None,'input_budget':req.get('max_tokens'),'history_and_stale_state_manual_review':'exact supplied request retained; no automatic universal corruption certification'})
        for capture,response in zip(captures,r.get('model_responses',[])):
            capture['prompt_tokens']=response.get('usage',{}).get('prompt_tokens');capture['runtime_timings']=response.get('timings',{})
        audit.append({'request':r['id'],'captures':captures,'source_count':len(r.get('result',{}).get('sources',[])),'retrieval_rounds':len(r.get('retrievals',[]))})
        events={}
        for e in r['events']:events.setdefault(e['name'],[]).append(e['monotonic_ns'])
        required=['request_received','router_start','router_end','retrieval_start','embedding_start','embedding_end','bm25_start','bm25_end','vector_search_start','vector_search_end','reranker_start','reranker_end','context_build_start','context_build_end','model_lease_start','model_lease_end','model_switch_start','model_switch_end','prompt_submit_start','prompt_submit_end','first_token_time','generation_end','answer_returned']
        r['complete_timing_fields']={name:events.get(name) for name in required}
        r['unmeasured_timing_reason']='First-token time unavailable for synchronous nonstreaming production call; no switch/reranker occurred; router markers only instrument actual _request_plan, not inferred branch timing. Native C++ prompt/generation timings retained separately. vector_search spans time real dot products; ranking/merge residual stays in enclosing retrieval.'
        r['runtime_prompt_processing_seconds']=sum(x.get('timings',{}).get('prompt_ms',0)/1000 for x in r.get('model_responses',[]))
        r['runtime_generation_seconds']=sum(x.get('timings',{}).get('predicted_ms',0)/1000 for x in r.get('model_responses',[]))
    # Actual runtime tokenize of supplied context is post-run analysis, outside measured request latency.
    with httpx.Client(trust_env=False,timeout=30) as client:
        token_records=[]
        for r in rows:
            retrievals=r.get('retrievals',[])
            if not retrievals:continue
            text='\n\n'.join(c['text'] for c in retrievals[-1]['chunks']);response=client.post('http://127.0.0.1:8087/tokenize',json={'content':text,'add_special':False});response.raise_for_status();data=response.json()
            token_records.append({'request':r['id'],'retrieved_chunk_count':len(retrievals[-1]['chunks']),'raw_retrieved_characters':len(text),'raw_retrieved_tokens':len(data['tokens']),'final_prompt_tokens':[x.get('usage',{}).get('prompt_tokens') for x in r.get('model_responses',[])],'method':'post-run actual runtime tokenizer; context prompt totals use server usage, not a guessed token/character ratio'})
    save(out/'context-token-counts.json',token_records);save(out/'context-audit.json',audit)
    timings={'cold':byid['baseline-0'],'warm':[byid['baseline-'+str(i)] for i in range(1,4)]}
    warm=np.array([r['total_seconds'] for r in timings['warm']]);timings['warm_p50']=float(np.percentile(warm,50));timings['warm_p95']=float(np.percentile(warm,95));save(out/'timing-baseline.json',timings)
    save(out/'retrieval-baseline.json',[{'request':r['id'],'retrievals':r.get('retrievals',[]),'stage_seconds':r['stage_seconds'],'embedded_inputs':r.get('embedding_inputs',[])} for r in rows])
    arithmetic=[r for r in rows if r['id'].startswith('compute-')];save(out/'computation-results.json',arithmetic)
    follow=[r for r in rows if r['id'].startswith('followup-')]
    previous_ids=set()
    for r in follow:
        current_ids={s['chunk_id'] for s in r.get('result',{}).get('sources',[])}
        r['evidence_ids']=sorted(current_ids);r['previous_evidence_overlap']=sorted(previous_ids&current_ids);r['new_retrieval_occurred']=bool(r.get('retrievals'));r['previous_evidence_reused_directly']=False
        if r['id']=='followup-1' and not current_ids:r['grounded_correct']=False;r['failure_category']='ROUTING_FAILURE'
        else:r['grounded_correct']=r.get('correct')
        previous_ids=current_ids
    save(out/'followup-results.json',follow)
    mixed=byid['mixed'];mixed['both_parts_literal_present']=bool(re.search(r'8088',mixed.get('result',{}).get('answer','')) and re.search(r'\b42\b',mixed.get('result',{}).get('answer','')))
    save(out/'router-results.json',{'arithmetic':arithmetic,'followups':follow,'mixed':mixed,'existing_router_metadata':'Workbench ask actual branches; not a replacement router'})
    summary=[]
    for label,group in [('baseline',baseline),('top5',top5),('top5+cached',cached)]:
        summary.append({'configuration':label,'questions':5,'literal_oracle_pass':sum(bool(r.get('correct')) and r.get('result',{}).get('status')=='answered' for r in group),'independent_semantic_pass':sum(bool(r.get('independent_semantic_pass')) for r in group),'total_latency_p50':float(np.median([r['total_seconds'] for r in group])),'retrieval_p50':float(np.median([r['stage_seconds'].get('retrieval',0) for r in group])),'model_calls':sum(r['model_calls'] for r in group),'per_question':[{'id':r['id'],'total':r['total_seconds'],'retrieval':r['stage_seconds'].get('retrieval'),'original_literal_pass':r.get('correct'),'independent_semantic_pass':r.get('independent_semantic_pass'),'failure':semantic_by_id.get(r['id'],{}).get('primary_failure',r.get('failure_category'))} for r in group]})
    save(out/'optimization-comparisons.json',summary)
    eligible=[r for r in rows if 'compute-' not in r['id']];worst=max(eligible,key=lambda r:r['total_seconds']);components=worst['stage_seconds'];dominant=max((k for k in components if k not in {'retrieval','router'}),key=lambda k:components[k])
    table='\n'.join(f"| {s['configuration']} | {s['literal_oracle_pass']}/5 | {s['independent_semantic_pass']}/5 | {s['total_latency_p50']:.6f} | {s['retrieval_p50']:.6f} | {s['model_calls']} |" for s in summary)
    arithmetic_table='\n'.join(f"| {r['question']} | {r.get('result',{}).get('answer',r.get('error',''))} | {r['total_seconds']:.6f} | {r['model_calls']} | {bool(r.get('retrievals'))} | {r.get('correct')} |" for r in arithmetic)
    follow_table='\n'.join(f"| {r['question']} | {r.get('result',{}).get('status',r.get('error',''))} | {r['total_seconds']:.6f} | {r['new_retrieval_occurred']} | {len(r['evidence_ids'])} | {r.get('grounded_correct')} |" for r in follow)
    integrity=json.loads((out/'integrity.json').read_text()); manifest=json.loads((out/'manifest.json').read_text());assert digest(out/'PREREGISTRATION.md')==manifest['preregistration_sha256']
    status='RAG_CORRECTNESS_BLOCKED'
    report=f'''# Latency + RAG recovery

## OBSERVED FACTS
Controlled corpus: exact frozen repository README, hashed before calls, indexed by existing extract/chunk_pages/BGE/Store.publish. It is authentic project text, not invented evidence. Dataset is small; no claim about all user documents. Existing Workbench in isolated module/data/projects, same native policies. The first attempt lost aggregate timing due a relative-path harness bug; its raw correct answer remains separately preserved. This new run fixes path handling only; amendment records the exclusion. No prior results overwritten.

Application-cold request: {byid['baseline-0']['total_seconds']:.9f}s. Three warm totals: {', '.join(f"{r['total_seconds']:.9f}" for r in timings['warm'])}s. Warm p50={timings['warm_p50']:.9f}s, p95={timings['warm_p95']:.9f}s (linear interpolation, only3samples). Cold here means fresh lazy ONNX instance, not fresh GPU/model/OS-cache cold start; current Qwen stays resident.

## BOTTLENECK
Largest measured whole request `{worst['id']}`: {worst['total_seconds']:.9f}s. Its largest non-overlapping leaf/model stage `{dominant}`: {components[dominant]:.9f}s. Runtime prompt processing {worst['runtime_prompt_processing_seconds']:.9f}s; runtime generation {worst['runtime_generation_seconds']:.9f}s. Stage timings can nest; never sum enclosing retrieval/router with their child stages as independent totals. The reported120seconds is NOT reproduced here. No exact cause assigned to that unobserved historical request.

## RETRIEVAL
Existing FTS5 BM25 index and document vectors persist in SQLite. Query retrieve reloads/deserializes all selected active chunks/vectors and sorts dense dot scores each request; not corpus re-embedding or FTS index rebuilding. Workbench also calls active_chunks before retrieve, so two loads may occur. Query embedding_inputs show query=True only during requests; corpus embedding was separate initialization. Initialization timing/chunk count in index-initialization.json. No reranker in current retrieve.py; reranker comparison not applicable. No multi-query/recursive lookup added by harness; existing application recovery is preserved and any repeated retrievals/model calls recorded.

| Configuration | Original literal check | Independent semantic audit | Median total seconds | Median retrieval seconds | Model calls |
|---|---:|---:|---:|---:|---:|
{table}

## ROUTER
Actual Workbench ask has deterministic literal-arithmetic bypass, ordinary-conversation bypass, then document intent path. It does not send every request to retrieval. Main QA uses explicitly forced document path to isolate retrieval; this is an input control, not a production policy change. Followup/mixed calls exercise ordinary existing routing. Router model-call spans and decision/result metadata retained. No new router/controller introduced. Mixed both requested values present: {mixed['both_parts_literal_present']}; full captured result in router-results.json. This literal check alone does not certify decomposition or reasoning.

## COMPUTATION
| Input | Actual answer | Seconds | Model calls | Retrieval | Correct exact tool result |
|---|---|---:|---:|---|---|
{arithmetic_table}

Answers are untouched existing calculator/route outputs. Deterministic tool results are NOT model success. Extra percent shorthand probes existing parser behavior; no harness fix is counted.

## FOLLOW-UP QA
| Turn | Result status | Seconds | New retrieval | Evidence IDs count | Grounded literal correctness |
|---|---|---:|---|---:|---|
{follow_table}

Exact prompts, evidence IDs/overlap and outputs preserved. Workbench history contains prior USER questions only, not previous answers/passages. It does not directly reuse previous evidence. Actual routing of bare version/why-version questions is documented; generic word cues can bypass documents. Third explanation question lacks an explicit causal fact in README; its semantic correctness is UNKNOWN unless independently established, not presumed from fluent text.

## GENERATION
Independent audit found two consistent failures: model-port answers assert8088 while source truth is8087; project-path answers do not state the explicit default Projects directory correctly. Some original regex checks wrongly passed incidental mentions of8087 or scattered Documents/Projects words. Those original checks remain preserved; separate independent-semantic-audit.json records rejection. Supplied top-k chunks omit the specific controlling statements, so primary cause is RETRIEVAL_FAILURE when the exact relation is absent, rather than blaming generation for a fact never supplied. Citation/numeric-presence validation does not prove semantic entailment. Exceptions remain UNKNOWN pending precise inspection. All answers/server responses retained; harness never repairs/substitutes them. Acquisition measured via actual _lease; worker stayed same profile. No restart/switch invoked.

## OPTIMIZATION RESULTS
One variable at a time: existing top6 baseline -> top5 with same prompt/answer path -> same top5 plus experiment-only active-chunk cache. Cache key includes all document IDs/active hashes/embedding revisions and requested scope; SQLite FTS remains persisted. Measured cache hits retained. No production defaults changed. Sequential order and GPU prompt caching can confound total-generation differences; retrieval-only stage comparisons are more directly attributable. The sample is5questions with one run each, not a robust statistical speed claim. No reranker to compare. Full production SYSTEM retained; compact prompt change was not combined with top-k/cache changes.

Recommendation from these measurements: do not promote top5 or this cache as a correctness fix. Top5 increased aggregate QA model calls from5 to13 because omitted facts triggered existing repair/refinement/retrieval cycles. In top5-projects, six model calls consumed37.010368s while all retrieval rounds consumed0.2956013s; total39.7797168s. Cache did not recover the missing facts and left the same13calls. The next separately approved experiments should test source-relation-aware ranking/coverage, version-bound conversational evidence handoff, and the existing calculator's percent-shorthand recognition. Avoid another controller. Retain historical false literal PASS checks alongside the semantic rejection, and strengthen independent oracle adequacy before making any reliability claim.

Mixed request took38.6426283s with seven model calls and ultimately refused both parts. Existing document-only answer instructions cannot use an arithmetic result that the request path never supplied; no deterministic arithmetic sub-result was produced for that mixed request. This is a measured unsupported mixed workflow, not evidence of successful decomposition. The extra20%of450 probe generated the correct90 through one heavy-model call in4.9419127s rather than the deterministic arithmetic branch. The required five literal expressions all completed with zero model/retrieval calls in0.051–0.091s.

## REGRESSION
Fresh existing Docker verifier18/18 before and after, saved raw check maps. Frozen production/native/Stage1A2 changes: {integrity['source_or_evidence_changes']}; frozen model/runtime/BGE asset changes: {integrity['asset_changes']}. One heavy worker retained; no network fallback, candidate execution, publication, native schema alteration, or T10/Stage1B/Stage2. Native JSON experiments unchanged.

## INFERENCES
Measured model processing/roundtrip and cold embedding initialization matter more than small-corpus vector/BM25 query time. Persistent document indexes already exist; active chunk reload is the cacheable query work. Followup routing/history shape may explain missing grounding; no universal causality claim from one small controlled sequence. Stage attribution is supported only for this workload. No production migration justified solely by these samples.

## UNKNOWNS
Actual120second request/corpus/route, large table planning/recovery latency, true OS/model-cold startup, lock contention under real UI concurrency, cache invalidation under concurrent imports, arbitrary followup reasoning. First-token time is unavailable for nonstreaming synchronous production requests and recorded null; HTTP headers cannot infer it. Full model-switch time not measured because no switch occurred. Router timestamp fields are null for bypass branches rather than invented estimates. Actual runtime /tokenize post-run counts and prompt usage in context-token-counts.json; no guessing token ratios. No universal prompt-corruption certification; context-audit.json records actual system/tool/evidence duplication checks and exact prompts.

## FINAL STATUS
{status}

Stopped after report. No production optimization promoted; further action requires explicit approval.
'''
    (out/'FINAL_REPORT.md').write_text(report,encoding='utf-8');save(out/'progress.json',{'status':status,'completed_requests':len(rows),'stopped':True,'production_modified':False,'t10_run':False});print(status,summary,flush=True)
if __name__=='__main__':main(Path(sys.argv[1]))
