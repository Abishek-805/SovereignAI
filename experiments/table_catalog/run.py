"""Read-only selective catalog experiment; original production planner/compiler."""
import hashlib,json,re,sqlite3,sys,time
from pathlib import Path
from datetime import datetime,timezone,timedelta
from backend.model import LocalModel
from backend.contracts import WorkbenchError
from rag.tables import load_tables,literal_entity_coverage,compile_outcome_query,execute_query,numeric_value,TABULAR
from router.model_registry import ModelRegistry
ROOT=Path(__file__).resolve().parents[2]
QUESTION='can u tell me the total marks scored in all the tests of 24alr051'
def save(path,v):path.write_text(json.dumps(v,indent=2,ensure_ascii=False,default=str),encoding='utf-8')
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def words(text):return set(re.findall(r'\w+',text.casefold()))
class Probe(LocalModel):
    def __init__(self,out):super().__init__(verify_semantics=False);self.out=out;self.calls=[]
    def _request_raw(self,method,path,**kw):
        if method!='POST' or path!='/v1/chat/completions':return super()._request_raw(method,path,**kw)
        payload=kw['json'];number=len(self.calls)+1;cell=self.out/f'call-{number:03}';cell.mkdir()
        save(cell/'request.json',payload);(cell/'prompt.txt').write_text(json.dumps(payload['messages'],indent=2,ensure_ascii=False),encoding='utf-8')
        tokens=self.count_messages(payload['messages'],payload)
        meta={'prompt_tokens':tokens,'system_tokens':sum(self.tokens(m['content']) for m in payload['messages'] if m['role']=='system'),'output_reserved':payload['max_tokens'],'context':self.context_capacity(),'remaining_headroom':self.context_capacity()-tokens-payload['max_tokens']-64,'tool_tokens':0,'response_schema_tokens':self.tokens(json.dumps(payload.get('response_format',{})))}
        save(cell/'budget.json',meta);self.calls.append(meta);started=time.perf_counter()
        try:
            response=super()._request_raw(method,path,**kw);save(cell/'response.json',response);meta['usage']=response.get('usage');return response
        except Exception as exc:meta['error']=str(exc);raise
        finally:meta['seconds']=time.perf_counter()-started;save(cell/'result.json',meta)
    def tokens(self,text):return len(self._request('POST','/tokenize',json={'content':text,'add_special':False})['tokens'])
def filter_catalog(catalog,question,history=None,top=5,hard_max=8):
    terms=words(' '.join([question,*[x.split(':',1)[-1] for x in history or []]]))
    ids={x.casefold() for x in re.findall(r'\b(?=\w*[a-zA-Z])(?=\w*\d)\w+\b',' '.join([question,*[x.split(':',1)[-1] for x in history or []]]))}
    candidates=[]
    for table in catalog:
        coverage=[m for field in ('literal_entity_coverage','history_entity_coverage') for m in table.get(field,{}).get('matches',[]) if m['literal'].casefold() in ids]
        overlap=len(terms & words(table['document']+' '+table['sheet']+' '+' '.join(table['columns'])))
        if ids and not coverage:continue
        if not ids and overlap<2:continue
        measures=[c for c in table['columns'] if re.search(r'\b(wat|cat|week|test|marks?|score)\b',c,re.I)]
        candidates.append((len(coverage)*100+overlap+len(measures)*3,table,coverage,measures))
    candidates.sort(key=lambda x:(-x[0],x[1]['id']))
    output=[];audit=[]
    for score,table,coverage,measures in candidates[:top]:
        needed={m['column'] for m in coverage}
        needed.update(c for c in table['columns'] if terms&words(c))
        if terms & {'all','tests','marks','mark','scores','score','total','highest','highestmark'}:
            needed.update(measures)
            # Actual fallback numeric measure labels, never names or identifiers.
            needed.update(c for c in table['columns'] if re.search(r'\btotal\b',c,re.I))
        if not needed:continue
        selected=[c for c in table['columns'] if c in needed]
        reduced={k:v for k,v in table.items() if k in {'id','document','sheet','row_count'}}
        reduced.update(columns=selected,sample=[{c:r.get(c) for c in selected} for r in table['sample']],title_rows=table['title_rows'],literal_entity_coverage={**table['literal_entity_coverage'],'matches':[m for m in table['literal_entity_coverage']['matches'] if m['column'] in needed]},history_entity_coverage={**table['history_entity_coverage'],'matches':[m for m in table['history_entity_coverage']['matches'] if m['column'] in needed]},categorical_values={c:v for c,v in table['categorical_values'].items() if c in needed})
        output.append(reduced);audit.append({'table':table['id'],'score':score,'columns_before':len(table['columns']),'columns_after':len(selected),'reason':'literal complete-record identity coverage plus actual column/table lexical matches; preserve named/all assessment columns','relationships':'source declares none; current query executor has no relational joins'})
    return output,audit
def catalog_data(question,history=None):
    db=sqlite3.connect('file:'+str(ROOT/'data/index.sqlite')+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
    docs=[dict(r) for r in db.execute('select * from documents order by document_id')];db.close();catalog=[];available={};hashes={}
    for doc in docs:
        suffix=Path(doc['source_path']).suffix.lower()
        if suffix not in TABULAR:continue
        source=Path.home()/'Documents/SovereignAI/Knowledge'/(doc['active_hash']+suffix)
        if not source.exists():continue
        assert sha(source)==doc['active_hash'];hashes[str(source)]=sha(source)
        for table in load_tables(source):
            key='T'+str(len(catalog)+1)
            catalog.append({'id':key,'document':doc['display_name'],'sheet':table['name'],'title_rows':table['rows'][:min(3,table['header_row'])],'columns':table['columns'],'row_count':len(table['records']),'sample':table['records'][:2],'literal_entity_coverage':literal_entity_coverage(table,question),'history_entity_coverage':literal_entity_coverage(table,'\n'.join(history or [])),'categorical_values':{c:sorted({str(r.get(c)) for r in table['records'] if isinstance(r.get(c),str)}) for c in table['columns'] if 0<len({str(r.get(c)) for r in table['records'] if isinstance(r.get(c),str)})<=12}})
            available[key]=(doc,table)
    return catalog,available,hashes
def execute_plan(query,available,q,history):
    if query.get('_measure'):doc,query=compile_outcome_query(query,available,q,history)
    else:doc=available[query['table']][0]
    tables=[query,*[{**extra,'operation':query['operation']} for extra in query.get('additional_queries',[])]]
    return {'query':query,'document':doc['display_name'],'results':[execute_query(available[t['table']][1],t) for t in tables]}
def main():
    out=ROOT/'evidence/table-catalog-context-fix'/datetime.now(timezone(timedelta(hours=5,minutes=30))).strftime('%Y%m%d-%H%M%S');out.mkdir(parents=True)
    (out/'PREREGISTRATION.md').write_text('''Read-only actual catalog diagnosis. Exact supplied request unchanged. Baseline original plan_table_query and reduced top5/maximum8 local lexical/complete-literal-identity coverage filter; all declared relationships preserved, none invented. Actual numeric score labels retained for all/highest requests. Current executor non-SQL/no joins; do not claim join support. No data/model/production changes, output budgets original768/1984planner stages plus reserve64, context16384. Original planner can fail after its initial measure call before later context guard; capture stages/prompt/tokenizer/calls and preserve failure. No manual table/query/answer substitution. After selection use original read-only compiler/executor. Independent oracle from source rows measured separately and not supplied to model; any selected schema/unsafe/correctness failure stops experiment. Followups only after primary pass. No QLoRA training/JSON/T10/Stage2. Unknown reason/count semantic limitations reported. Notebook preparation can proceed separately after report.
''')
    registry=ModelRegistry();assert registry.verified_residency()=='Qwen/Qwen3.5-4B'
    import httpx
    assert not httpx.get('http://127.0.0.1:8087/slots',trust_env=False).json()[0]['is_processing']
    catalog,available,hashes=catalog_data(QUESTION);save(out/'catalog-baseline.json',catalog)
    production={str(p.relative_to(ROOT)):sha(p) for folder in ('backend','rag','router','workflows') for p in (ROOT/folder).rglob('*.py')}
    save(out/'manifest.json',{'preregistration_sha256':sha(out/'PREREGISTRATION.md'),'source_hashes':hashes,'production_sha256':production,'question':QUESTION,'table_count':len(catalog),'column_count':sum(len(t['columns']) for t in catalog),'serialized_bytes':len(json.dumps(catalog,ensure_ascii=False).encode())})
    records=[]
    for phase in ('baseline','selective'):
        cell=out/phase;cell.mkdir();model=Probe(cell);history=[];q=QUESTION
        for turn in range(3 if phase=='selective' else 1):
            started=time.perf_counter();filter_started=time.perf_counter();selected,audit=filter_catalog(catalog,q,history) if phase=='selective' else (catalog,[]);filter_seconds=time.perf_counter()-filter_started
            record={'phase':phase,'turn':turn,'question':q,'filter_seconds':filter_seconds,'table_count':len(selected),'catalog_tokens':model.tokens(json.dumps(selected)),'serialized_bytes':len(json.dumps(selected,ensure_ascii=False).encode()),'selection':audit}
            save(cell/f'catalog-{turn}.json',selected)
            try:
                if not selected:raise WorkbenchError('needs_input','No sufficiently relevant table was identified')
                count_before=len(model.calls);query=model.plan_table_query(q,selected,history);record['generated_query']=query;record['execution']=execute_plan(query,available,q,history);record['model_calls']=len(model.calls)-count_before
                record['status']='executed'
            except Exception as e:record.update(status='failed',error=str(e),model_calls=len(model.calls))
            record['total_seconds']=time.perf_counter()-started;records.append(record);save(out/'query-results.json',records);print(phase,turn,record['status'],record.get('error',''),flush=True)
            if record['status']=='failed':break
            if phase=='selective':
                history.append('user: '+q);q=['what was the highest mark?','how many tests were there?',''][turn]
        model.close()
    changes=[p for p,d in production.items() if sha(ROOT/p)!=d];source_changes=[p for p,d in hashes.items() if sha(Path(p))!=d];save(out/'integrity.json',{'production_changes':changes,'source_changes':source_changes});assert not changes and not source_changes
    print('REPORT_DIRECTORY='+str(out),flush=True)
if __name__=='__main__':main()
