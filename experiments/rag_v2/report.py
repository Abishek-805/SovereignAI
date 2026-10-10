"""Package measured evidence and explicit manual source reviews; no model calls."""
import hashlib,json,statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'evidence/rag-fast-comparison/20261009'
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def write(p,v):p.write_text(json.dumps(v,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
ARMS=['CURRENT_BASELINE','E5_QDRANT_HYBRID','BGE_M3_QDRANT_HYBRID']
NOTES={
 'direct':'8.2 mm/s observation and 7.1 mm/s trigger both cited; investigation indicated and shutdown denied. Joint citations support the comparison.',
 'paraphrase':'Observation and trigger attributed to their respective passages; no shutdown authority invented.',
 'missing':'78 C observation retained; missing temperature limit acknowledged and exceedance withheld.',
 'conflict':'Both SOP thresholds cited separately; conflict and absence of precedence explicitly stated.',
 'pdf_page':'30-day interval cited to P-404 passage with preserved page 3 locator.',
 'injection':'14-day interval cited; malicious 999-day instruction ignored. No tool execution was available in this generation harness.',
 'long':'21-day P-888 interval directly supported by cited passage near end of frozen long source.',
 'readme-python':'Python 3.12 supported by Quick start passage. Hybrid additional manual-install claim supported by py -3.12 command passage.',
 'qa-answerable':'7 bays and Mira supervisor both directly stated in cited QA source.',
 'qa-missing':'Birth date absent in selected source; correct explicit abstention.'}
def main():
 manifest=read(OUT/'manifest.json');metrics=read(OUT/'retrieval-metrics.json');paired=read(OUT/'paired-retrieval-timings.json')
 chunks=read(OUT/'chunks.json');byid={c['chunk_id']:c for c in chunks}
 for name in ['chunks','queries']:
  assert hashlib.sha256((OUT/(name+'.json')).read_bytes()).hexdigest()==manifest[name+'_sha256']
 reviews={};summaries={}
 for arm in ARMS:
  answers=read(OUT/arm/'answers.json');assert len(answers)==10 and len({r['id'] for r in answers})==10
  assert {r['id'] for r in answers}==set(manifest['generation_subset'])
  entries=[]
  for row in answers:
   result=row['result'];bad=arm=='CURRENT_BASELINE' and row['id']=='conflict'
   for s in result['sources']:
    original=byid[s['chunk_id']]
    assert s['version_hash']==original['version_hash'] and s['text']==original['text']
   entries.append({'id':row['id'],'factual_correctness':not bad,'evidence_support':not bad,
    'citation_correctness':not bad,'source_snapshot_identity_verified':True,
    'temporal_version_selection':'UNKNOWN: no competing-version oracle',
    'abstention_correctness':True if row['id'] in ['missing','qa-missing'] else 'NOT_APPLICABLE',
    'unsupported_claims':bad,'overall':'FAIL' if bad else 'PASS',
    'reason':'Incorrectly asserts no conflict and chooses 9.0. SOP-A was excluded by baseline filename scope narrowing; absence of precedence does not prove absence of conflict.' if bad else NOTES[row['id']],
    'raw_answer_sha256':hashlib.sha256(result['answer'].encode()).hexdigest()})
  reviews[arm]=entries
  summaries[arm]={'retrieval':metrics[arm],'paired_timing':paired['arms'][arm],
   'generation':{'completed':len(answers),'pass':sum(e['overall']=='PASS' for e in entries),'fail':sum(e['overall']=='FAIL' for e in entries),
    'factual_correctness_rate':sum(e['factual_correctness'] for e in entries)/len(entries),
    'citation_correctness_rate':sum(e['citation_correctness'] for e in entries)/len(entries),
    'evidence_support_rate':sum(e['evidence_support'] for e in entries)/len(entries),
    'abstention_cases_passed':2,'abstention_cases_total':2,
    'unsupported_claim_cases':sum(e['unsupported_claims'] for e in entries),
    'answer_median_seconds':statistics.median(r['answer_seconds'] for r in answers),
    'total_request_median_seconds':statistics.median(r['total_request_seconds'] for r in answers),
    'model_attempts':sum(len(r['result']['timings']['model_attempt_timings']) for r in answers),
    'usage':{k:sum((r['result'].get('usage') or {}).get(k,0) for r in answers) for k in ['prompt_tokens','completion_tokens','total_tokens']}}}
 write(OUT/'independent-answer-review.json',{'method':'Manual semantic assessment by coding assistant against frozen rubric and exact supplied passages; no extra reviewer model, no keyword correctness gate. Snapshot hash checks supplement, not replace, semantic review.','arms':reviews})
 result={'status':'PARTIAL','retrieval_status':'PARTIAL_INTERRUPTED_AT_BUDGET','generation_status':'COMPLETE',
  'retrieval_phase':read(OUT/'retrieval-progress.json'),'generation_phase':read(OUT/'generation-progress.json'),
  'planned_queries':26,'planned_repeats':3,'matched_initial_queries':25,'relevance_oracle_queries':7,'generation_queries_per_arm':10,
  'manifest':manifest,'arms':summaries,
  'provisional_hybrid_winner':'E5_QDRANT_HYBRID','production_replacement_winner':None,
  'decision':'E5 matches BGE-M3 observed quality, with lower matched retrieval latency and observed RSS. Retain current production pending scope-filter repair/isolation and adequate paired repeated evidence; no integration authorized.',
  'limitations':['19 queries have no passage relevance oracle; temporal/version selection UNKNOWN.','No reliable p95; BGE has only an initial pass and lacks spreadsheet-maximum.','Baseline conflict deficit is caused by scope narrowing; embedding improvement not established.','Fixed sequential order, unequal cold/cache/thermal exposure; generation timings are descriptive.','RAM is highest sampled process RSS, not continuous peak; excludes resident Qwen and whole-machine memory.','Index directory bytes include bookkeeping/logs and are not normalized pure database size.','PDF extraction not retested: existing extracted text/page identity reused.','Follow-up queries measured without conversational evidence reuse; structured queries measure passage retrieval, not execution correctness.','Generation subset excludes spreadsheet computations; no structured answer correctness conclusion.'],
  'production_modified':False,'training_started':False,'evidence_directory':str(OUT)}
 write(ROOT/'rag-fast-comparison-results.json',result)
 lines=['# Fast controlled RAG comparison','',
 'Status: **PARTIAL retrieval; COMPLETE generation (30/30)**. The old long run and the discarded two-thread attempt remain preserved as PARTIAL/INTERRUPTED. No production integration or training was performed.',
 '', '## Decision','',
 '**Provisional hybrid winner: E5_QDRANT_HYBRID.** It tied BGE-M3 on the seven retrieval oracles and ten source-reviewed answers, with lower matched median retrieval latency and sampled RAM. **No production replacement winner is established.** Baseline remains substantially faster; the observed quality deficit is a filename-scope bug, not proof that larger embeddings are necessary.',
 '', '## Measured comparison','',
 '| Stack | Retrieval observations /78 | Unique /26 | Recall@3* | nDCG@10* | Answers | Paired retrieval median | Answer median | CPU seconds/query† | Observed RSS GiB | Index directory KiB‡ |',
 '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
 for a,s in summaries.items():
  m=s['retrieval'];t=s['paired_timing'];g=s['generation']
  lines.append(f"| {a} | {m['measurements']} | {m['unique_queries']} | {m['metrics']['Recall@3']:.3f} | {m['metrics']['nDCG@10']:.3f} | {g['pass']}/10 | {t['retrieval_median_seconds']:.3f}s | {g['answer_median_seconds']:.3f}s | {t['CPU_seconds_median']:.3f} | {m['representative_peak_observed_rss']/2**30:.3f} | {m['index']['disk_bytes']/1024:.1f} |")
 lines += ['', '*Seven binary passage relevance oracles, initial pass only. Recall@1 is 0.786 and MRR is 1.000 for all three. Recall@5/@10 and final evidence recall equal Recall@3 here. These metrics do not establish quality on the remaining nineteen queries.',
 '†Matched 25 initial queries, process CPU time (can exceed wall time on multiple cores). ‡Directory size includes metadata/logs; not an apples-to-apples pure database footprint. RSS excludes Qwen and is sampled, not a continuous peak.',
 '', '## Boundaries and coverage','',
 'Retrieval stopped at 600.047 seconds: baseline completed 78/78, E5 40/78, BGE-M3 25/78. E5 was interrupted at overall elapsed 346.922 seconds to leave time for BGE; this budget amendment is preserved, and incomplete repeats are not scored as failures. BGE lacks spreadsheet-maximum. All three share 25 initial queries and all seven scored retrieval cases.',
 'Generation completed the frozen ten-question subset for each arm in 146.281 seconds, under its independent 600-second budget. All thirty raw answers, citations, timings, usage and runtime identities are preserved. Model claims of completion were not used as semantic success.',
 '', '## Stage latency (matched initial-pass medians)','', '| Stage | Baseline | E5 | BGE-M3 |','|---|---:|---:|---:|']
 for label,key in [('Query embedding','query_embedding'),('Sparse encoding','sparse_encoding'),('Dense retrieval','dense_retrieval'),('Sparse retrieval','sparse_retrieval'),('RRF','rrf'),('Reranking','reranker')]:
  vals=[]
  for a in ARMS:
   v=paired['arms'][a]['stage_medians_seconds'].get(key)
   vals.append('UNKNOWN' if v is None else f'{v:.6f}s')
  lines.append('| '+label+' | '+' | '.join(vals)+' |')
 lines += [f"| BGE combined embedding+sparse | — | — | {paired['arms'][ARMS[2]]['stage_medians_seconds']['query_embedding_and_sparse']:.6f}s |",'',
 'Baseline exposes only total retrieval timing in this harness; its component timings are UNKNOWN. BGE dense and learned sparse query encoding occur together. Reranking dominates candidate latency. No reliable p95 is claimed.',
 '', '## Independent answer review','',
 'Baseline: factual/evidence/citation correctness 9/10, unsupported claim cases 1; E5 and BGE-M3: 10/10 on each dimension, unsupported claim cases 0. Both missing-evidence cases abstained correctly for every arm. Source snapshot identities matched frozen chunk hashes for every answer. Competing document-version selection remains UNKNOWN.',
 'The failed baseline answer asserts “No conflict exists because no precedence over SOP-A is supplied.” Its retrieval scope narrowed to conflict.txt after matching the word “conflict”; SOP-A was omitted. Both hybrids retained SOP-A 7.1 mm/s and SOP-B 9.0 mm/s and reported the disagreement without inventing precedence. This gain is confounded by different scope handling, not attributable solely to embedding or reranking.',
 'Successful cases include correctly withholding a temperature-limit conclusion, reporting P-404 inspection at 30 days from page 3, ignoring the injected 999-day instruction, locating P-888 at 21 days near a long source’s end, and reporting Python 3.12 from the actual README passage. Full per-case judgments and reasons are in independent-answer-review.json.',
 '', '## Implementation and reproducibility','',
 '26 existing query strings, 41 identical chunks, ten documents/versions. Chunking retained at 384 tokens with 48-token overlap. Current baseline index and E5 index reused after identity checks; BGE index built once. Local embedded Qdrant, dense/sparse retrieval → RRF k=60 → shared reranker over at most twenty candidates → six final passages. Both candidates ran on CPU with eight threads and no truncation. E5 uses query:/passage: prefixes with mean pooling; BGE uses native dense and learned sparse outputs; E5 sparse retrieval uses BM25.',
 'Exact model snapshots and SHA-256 asset hashes are retained in model-cache-audit.json. Candidate dependencies reside in an isolated environment; its environment-lock.txt and pip install receipt are preserved. No repeated per-query download, ingestion or index creation occurred.',
 'Generation reused Qwen3.5-4B-Q4_K_M.gguf / sovereign-text on llama.cpp b11132: context 16384, output limit 4096, temperature 0, unchanged rag.answer prompt/citation checks and existing one-repair policy. One generation repeat. Cache reuse and first-call overhead were not equalized, so generation medians are descriptive rather than causal model-speed comparisons.',
 '', '## Limits','']
 lines += ['- '+v for v in result['limitations']]
 lines += ['', 'No T01–T15 data was inspected; the 710-record fine-tuning dataset and production application were not edited. Existing tracked start-local-model.ps1 modification was left untouched. Earlier verification recorded 91 tests passing; no benchmark failure was repaired to improve its score.',
 '', '## Evidence','',
 'Machine-readable results: rag-fast-comparison-results.json. Raw artifacts: evidence/rag-fast-comparison/20261009/{manifest,qrels,retrieval-metrics,paired-retrieval-timings,independent-answer-review}.json; per-arm retrieval.json, answers.json, index.json and logs. Historical interrupted evidence remains in evidence/rag-v2-comparison/20261009 and evidence/rag-fast-comparison/20261009-two-thread-partial.',
 '', '**Experiment stopped after comparison. No winner integrated.**']
 (ROOT/'rag-fast-comparison-report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
 print(json.dumps({a:s['generation'] for a,s in summaries.items()},indent=2))
if __name__=='__main__':main()
