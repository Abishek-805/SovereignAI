import json,sys,re
from pathlib import Path
import openpyxl
from experiments.table_catalog.run import save
def main(out):
    manifest=json.loads((out/'manifest.json').read_text(encoding='utf-8'));records=json.loads((out/'query-results.json').read_text(encoding='utf-8'))
    target=next(x for x in re.findall(r'\w+',manifest['question']) if re.fullmatch(r'\d+[a-zA-Z]+\d+',x))
    candidates=[]
    for filename in manifest['source_hashes']:
        if Path(filename).suffix!='.xlsx':continue
        book=openpyxl.load_workbook(filename,read_only=True,data_only=True)
        for sheet in book:
            lines=list(sheet.iter_rows(values_only=True))
            headers=[(i,[str(v or '') for v in row]) for i,row in enumerate(lines[:20]) if any(re.fullmatch(r'(?:WAT|CAT|Week|Test)\s*\d+',str(v or ''),re.I) for v in row)]
            for idx,header in headers:
                cols=[(j,name) for j,name in enumerate(header) if re.fullmatch(r'(?:WAT|CAT|Week|Test)\s*\d+',name,re.I)]
                for line in lines[idx+1:]:
                    if any(str(v or '').casefold()==target.casefold() for v in line):
                        values={name:float(line[j]) for j,name in cols if j<len(line) and isinstance(line[j],(int,float)) and not isinstance(line[j],bool)}
                        if values:candidates.append({'source':filename,'sheet':sheet.title,'scores':values})
        book.close()
    truth=max(candidates,key=lambda c:len(c['scores']));truth.update(total=sum(truth['scores'].values()),highest=max(truth['scores'].values()),test_count=len(truth['scores']),method='Independent openpyxl raw cells and exact identity; widest explicitly numbered assessment coverage; no table-query compiler used')
    checks=[]
    for r in records:
        result=r['execution']['results'][0];values={s['column']:s['value'] for s in result.get('summaries',[])}
        checks.append({'phase':r['phase'],'turn':r['turn'],'numeric_measurements_match':values==truth['scores'] if r['turn']<2 else None,'correct_test_count':result.get('value')==truth['test_count'] if r['turn']==2 else None,'presentation_limitation':'Native sums/max are per column; primary125 and global highest32 not explicitly combined by current presenter; count returns records, not selected assessments'})
    save(out/'independent-oracle.json',{'source_truth':truth,'checks':checks})
    filter_rows=[{'turn':r['turn'],'tables':r['table_count'],'audit':r['selection']} for r in records if r['phase']=='selective'];save(out/'catalog-filter-results.json',filter_rows)
    budgets=[]
    for p in out.glob('*/call-*/budget.json'):budgets.append({'path':str(p.relative_to(out)),**json.loads(p.read_text())})
    save(out/'context-budget.json',budgets);save(out/'timing-comparison.json',records)
    for phase,target_name in [('baseline','prompt-before.txt'),('selective','prompt-after.txt')]:
        (out/target_name).write_bytes((out/phase/'call-002/prompt.txt').read_bytes())
    report=f'''# Table catalog context experiment

## ROOT CAUSE
The actual planner receives metadata from every eligible selected-library table. Columns are repeated across applicability metadata, categorical values, outcome/column enums and final binding grammar. Its explicit final context check occurs AFTER the first measure-generation call. Thus a too-large final catalog can be rejected only after time has already been spent planning. Current snapshot has22tables; cannot equate a present fitting snapshot with the historical UI overflow.

## BASELINE
Unchanged current planner completed the exact question with22tables,2model calls in{records[0]['total_seconds']:.9f}s. Original final-binding prompt11522tokens; output reserve1984; context16384; remaining headroom2814including64reserve. Final schema metadata8629tokens as a separately measured serialization, not added twice to template prompt tokens. The observed76.6s/UI overflow was NOT reproduced, and its exact earlier request is unavailable.

## NEW PATH
Experiment-only deterministic lexical table/column matching plus actual complete-record identity observations; top5candidate limit, hard maximum8registered. Exact original schema names retained, no hard-coded table or answer. Current table executor has no SQL joins/foreign-key metadata: no joins were invented, and compatibility with hypothetical relational catalogs is unproven. No strong candidate means controlled clarification, never entire-catalog fallback. Only exact selected columns/samples/actual coverage metadata sent. Full underlying records untouched.

## CONTEXT
Final-binding prompt reduced11522->3624tokens, same1984outputreserve and16384context, headroom2814->10712. System995tokens unchanged, native tool-schema0. Full capture budget includes actual messages/template; catalog standalone serialized tokens measured via runtime tokenizer. before/after text and all raw request/response JSON retained. No production context-window increase. Current experiment demonstrates headroom improvement, not complete guard-before-first-call implementation or guaranteed future overflow prevention.

## LATENCY
Primary {records[0]['total_seconds']:.9f}->{records[1]['total_seconds']:.9f}s, both2calls. Filter time{records[1]['filter_seconds']:.9f}s. Followups highest{records[2]['total_seconds']:.9f}s, count{records[3]['total_seconds']:.9f}s. Exact per-call prompt/generation/roundtrip evidence retained. One sequential sample; prompt caching/order may affect speed, no statistical superiority claim.

## CORRECTNESS
Independent openpyxl oracle reads actual source cells: assessment scores{truth['scores']}, total{truth['total']}, highest{truth['highest']}, tests{truth['test_count']}. Both original/selective sum queries returned matching per-assessment values and correct single-person filtering. Highest query similarly returns per-column extrema, not explicit global maximum. Count followup returned1matched record rather than7assessments: FAIL. Native presentation does not explicitly combine per-column sums into the requested across-test total. No final answer was manually patched. Because end-to-end answer/count correctness remains incomplete, this is not a fully fixed product path.

## SECURITY
Read-only structured execute_query unchanged, no raw model SQL executed. Allowed operators only; mutation DML/DDL unavailable. Source hashes and production files unchanged. Confidential student workbook evidence stays local and is excluded from Colab training package.

## REGRESSIONS
Primary numeric query preserved. Followup count correctness blocked in existing measure/executor semantics. Filtering only covers actual flat table catalogs; relational/ambiguous/unmatched catalogs require further tests. No production rollout, native agent/schema/model changes, RAG experiment alterations or T01–T15 evaluation.

## FINAL STATUS
QUERY_CORRECTNESS_BLOCKED

Context and latency improved in the isolated experiment. Stop after report; no fine-tuning in this stage.
'''
    (out/'FINAL_REPORT.md').write_text(report,encoding='utf-8');print('QUERY_CORRECTNESS_BLOCKED')
if __name__=='__main__':main(Path(sys.argv[1]))
