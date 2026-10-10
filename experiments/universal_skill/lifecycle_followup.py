"""Read-only production inspection, isolated source-bound checks and activation handoff."""
from pathlib import Path
import json,hashlib,time,httpx
from fastapi.testclient import TestClient
ROOT=Path(__file__).resolve().parents[2]
OUT=Path((ROOT/'experiments/universal_skill/lifecycle-followup-output.txt').read_text().strip())
OLD=Path((ROOT/'experiments/universal_skill/lifecycle-output.txt').read_text().strip())
def save(name,value):
    (OUT/name).write_text(json.dumps(value,indent=2,ensure_ascii=False,default=str),encoding='utf-8')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
prior=json.loads((ROOT/'rag-answer-lifecycle-report.json').read_text())
revision={p:{'recorded':h,'current':sha(ROOT/p),'matched_before_followup':h==sha(ROOT/p)} for p,h in prior['source_sha256'].items()}
for name in revision:
    if (OUT/'rollback'/name).exists():revision[name]['matched_before_followup']=revision[name]['recorded']==sha(OUT/'rollback'/name)
save('revision-inspection.json',revision)
protected={}
for name in ('protected-before.json','training-before.json'):
    protected.update(json.loads((OLD/name).read_text()))
for p in (OLD/'rollback').rglob('*'):
    if p.is_file():protected[str(p.relative_to(ROOT))]=sha(p)
for p in (ROOT/'rag-production-config.json',ROOT/'rag/retrieve.py',ROOT/'rag-answer-lifecycle-report.json',ROOT/'rag-answer-lifecycle-report.md'):
    protected[str(p.relative_to(ROOT))]=sha(p)
save('protected-manifest.json',protected)
with httpx.Client(base_url='http://127.0.0.1:8088',timeout=30) as client:
    receipts={}
    for endpoint in ('/health','/status','/documents'):
        start=time.perf_counter();response=client.get(endpoint);response.raise_for_status()
        receipts[endpoint]={'seconds':time.perf_counter()-start,'response':response.json()}
    save('production-readonly-inspection.json',receipts)
    docs=receipts['/documents']['response'];fixtures=OUT/'fixtures';fixtures.mkdir(exist_ok=True)
    selected=[d for d in docs if d['source_extension']=='.xlsx' or d['display_name']=='KPRIET_RAG_Knowledge_Base.md']
    sources=[]
    for doc in selected:
        start=time.perf_counter();response=client.get('/documents/'+doc['document_id']+'/original');response.raise_for_status()
        path=fixtures/doc['display_name'];path.write_bytes(response.content)
        if sha(path)!=doc['active_hash']:raise RuntimeError('Authorized original source hash mismatch')
        sources.append({**doc,'copy':str(path),'verified_sha256':sha(path),'download_seconds':time.perf_counter()-start})
    save('authorized-source-receipts.json',sources)
from experiments.rag_v2 import gemma_rag_acceptance as capture
capture.OUT=OUT
wb,ids=capture.build('gemma')
save('isolated-document-ids.json',ids)
from rag.tables import load_tables
workbook=next((d for d in sources if d['source_extension']=='.xlsx'),None)
observed=[]
if workbook:
    for table in load_tables(Path(workbook['copy'])):
        for row in table['records']:
            if any(str(value).strip().casefold()=='24alr051' for value in row.values()):
                observed.append({'sheet':table['name'],'columns':table['columns'],'record':row})
save('24ALR051-independent-source-records.json',observed)
from backend.app import create_app
app=create_app(wb)
receipts=[]
with TestClient(app,base_url='http://127.0.0.1:8100') as client:
    scope=[ids[d['display_name']] for d in sources]
    goals=[('actual_workbook_total','give me total professional skill test of 24ALR051'),
           ('actual_missing_identifier','give me total professional skill test of 99ZZZ999'),
           ('actual_missing_file','What does unavailable-lifecycle-reference.txt say?')]
    complete=wb.model._request_raw
    for case,goal in goals:
        start=time.perf_counter();job=client.post('/agent/jobs',json={'goal':goal,'document_ids':scope}).json();snapshots=[job]
        while job['state']=='running':
            time.sleep(.1);job=client.get('/coding/jobs/'+job['job_id']).json();snapshots.append(job)
            if time.perf_counter()-start>180:raise RuntimeError('Isolated source test timeout')
        receipts.append({'case':case,'goal':goal,'seconds':time.perf_counter()-start,'snapshots':snapshots})
        save('isolated-live-requests.json',receipts)
        print(case,job['state'],flush=True)
    from rag.model_routing import ACTIVE_RAG
    for mode in ('invalid_id','missing_id'):
        def fault(method,path,**kwargs):
            response=complete(method,path,**kwargs)
            if method=='POST' and path=='/v1/chat/completions' and (ACTIVE_RAG.get() or {}).get('stage')=='assess_evidence':
                response=json.loads(json.dumps(response));review=json.loads(response['choices'][0]['message']['content'])
                if mode=='invalid_id':review['claims'][0]['id']='C999'
                else:review['claims']=[]
                response['choices'][0]['message']['content']=json.dumps(review)
                save(mode+'-controlled-mutation.json',review)
            return response
        wb.model._request_raw=fault
        goal='Where is KPRIET located?';start=time.perf_counter()
        job=client.post('/agent/jobs',json={'goal':goal,'document_ids':scope}).json();snapshots=[job]
        while job['state']=='running':
            time.sleep(.2);job=client.get('/coding/jobs/'+job['job_id']).json();snapshots.append(job)
            if time.perf_counter()-start>180:raise RuntimeError('Fault test timeout')
        assert job['state']=='failed' and job['error_code']=='generation_format' and not job['partial_answer']
        assert 'draft was withheld' in job['error'] and 'same selected documents' in job['error']
        receipts.append({'case':mode,'goal':goal,'seconds':time.perf_counter()-start,'snapshots':snapshots})
        save('isolated-live-requests.json',receipts)
        print(mode,'helpful failed terminal PASS',flush=True)
    wb.model._request_raw=complete
changed=[p for p,h in protected.items() if not (ROOT/p).exists() or sha(ROOT/p)!=h]
save('integrity-after.json',{'status':'PASS' if not changed else 'FAIL','files':len(protected),'changed':changed})
print('integrity',len(protected),'files',changed,flush=True)
