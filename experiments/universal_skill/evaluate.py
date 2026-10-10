"""Skill-only paired probes; production source, prompts and stores remain unchanged."""
from pathlib import Path
import hashlib,json,time
from backend.model import LocalModel
from backend.contracts import Chunk
from rag.answer import answer
from rag.tables import _table,compile_outcome_query,bind_selection_request
from workflows.coding_workspace import CodingWorkspace
from router.model_registry import ModelRegistry

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'evidence'/'universal-skill'/str(time.time_ns())
SKILL=Path(__file__).with_name('SKILL.md').read_text(encoding='utf-8').split('---',2)[-1].strip()

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def source_hashes():
    return {str(p.relative_to(ROOT)):digest(p) for directory in ('backend','rag','router','workflows','skills/runtime')
            for p in (ROOT/directory).rglob('*') if p.is_file() and p.suffix in {'.py','.md'}}

def main():
    OUT.mkdir(parents=True)
    before=source_hashes()
    (OUT/'source-hashes-before.json').write_text(json.dumps(before,indent=2))
    (OUT/'SKILL.md').write_bytes(Path(__file__).with_name('SKILL.md').read_bytes())
    registry=ModelRegistry()
    fixtures=[
        ('overview','tell me about kpr','KPR Institute of Engineering and Technology (KPRIET) is an engineering institution in Arasur, Coimbatore, Tamil Nadu, India. It is affiliated to Anna University and approved by AICTE. It focuses on innovation, industry-informed teaching, research and professional careers. Its departments include Computer Science, Civil and Mechanical Engineering.'),
        ('transfer','Give me a general overview of the Northbank Museum.','Northbank Museum is a regional history museum in Seabrook. It preserves local maritime objects and oral histories. Its principal features are permanent harbor exhibits, school workshops and a research archive. Opening hours are not stated.')]
    (OUT/'fixtures.json').write_text(json.dumps(fixtures,indent=2))
    cases=[('overview',fixtures[0]),('transfer',fixtures[1]),('table_applicability',None),('calculator_plan',None),('notes_plan',None)]
    results=[]
    for case,fixture in cases:
        capability='code' if case.endswith('_plan') else 'rag'
        registry.acquire_lease(capability)
        if not registry._runtime_profile_matches(registry.launch_args(capability)):raise RuntimeError('Worker identity mismatch')
        for arm in ('baseline','skill'):
            model=LocalModel(verify_semantics=False)
            calls=[];raw=model._request_raw
            def request(method,path,**kwargs):
                start=time.perf_counter();completion=method=='POST' and path=='/v1/chat/completions'
                receipt={'stage':case,'arm':arm}
                if completion:
                    payload=dict(kwargs['json']);payload['model']=registry.specs[capability].alias
                    messages=[dict(m) for m in payload.get('messages',[])]
                    if arm=='skill':
                        messages[0]['content']+='\n\nEXPERIMENTAL TASK SKILL:\n'+SKILL
                    payload['messages']=messages;kwargs['json']=payload
                    receipt.update(payload=payload,runtime=registry.verified_residency(),
                        profile_verified=registry._runtime_profile_matches(registry.launch_args(capability)))
                    if not receipt['profile_verified']:raise RuntimeError('Worker changed during experiment')
                try:
                    response=raw(method,path,**kwargs)
                    if completion:receipt['response']=response
                    return response
                except Exception as exc:receipt['error']=str(exc);raise
                finally:
                    if completion:
                        receipt['seconds']=time.perf_counter()-start;calls.append(receipt)
                        with (OUT/'calls.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(receipt,ensure_ascii=False)+'\n')
            model._request_raw=request
            result={'case':case,'arm':arm,'model':registry.specs[capability].identifier};start=time.perf_counter()
            try:
                if fixture:
                    _,question,body=fixture
                    chunk=Chunk('c1','d1',hashlib.sha256(body.encode()).hexdigest(),'reference.txt',body,None,1,5)
                    result['result']=answer(question,[chunk],model,context=16384,output_tokens=1024,max_repairs=1)
                    result['status']=result['result']['status']
                elif case=='table_applicability':
                    question='tell me about kpr college'
                    table=_table('All',[['Member Id','Cohort','WAT 1'],['24ALR001','2024-2028-AIDS-A',14],['24ALR002','2024-2028-AIDS-A',20]])
                    catalog=[{'id':'T1','document':'marks.xlsx','sheet':'All','columns':table['columns'],'row_count':2,
                        'sample':table['records'],'alternative_reference_sources':[{'name':'institution.md','reference_excerpt':fixtures[0][2]}]}]
                    plan=model.plan_table_query(question,catalog)
                    result['plan']=plan
                    if plan.get('_measure'):compile_outcome_query(plan['_measure'],{'T1':({'document_id':'d'},table)},question)
                    elif plan.get('operation')!='none':bind_selection_request(plan,table,question)
                    result['status']='PASS' if plan.get('operation')=='none' else 'FAIL_UNRELATED_TABLE'
                else:
                    question='can u generate a simple '+('calculator' if case=='calculator_plan' else 'notes')+' web app'
                    files={'web/index.html':'<h1>Existing unrelated page</h1>','web/style.css':'body {color: blue}',
                        'todo_app/todo_app.py':'print("Existing application")'}
                    folders=['web','todo_app']
                    plan=model.plan_workspace_edit(question,files,folders,'',history=[]);result['plan']=plan
                    work=CodingWorkspace(OUT/arm/case);wid=work.create('Isolated probe')['workspace_id']
                    work._preflight_operation_plan(wid,plan['operations'],files,{},folders,question)
                    contract=plan.get('contract') or {};entry=contract.get('entrypoint')
                    ops=plan['operations']
                    assert contract.get('deliverable')=='application' and entry and any(o['path']==entry and o['action']=='create' for o in ops),'Application entrypoint missing'
                    assert not any(o['action'] in {'edit','delete'} for o in ops),'Standalone creation changes unrelated files'
                    result['status']='PLAN_VALIDATED'
            except Exception as exc:result.update(status='FAIL',error=str(exc),error_code=getattr(exc,'code',None))
            finally:
                result.update(seconds=time.perf_counter()-start,model_calls=len(calls));results.append(result)
                (OUT/'results.json').write_text(json.dumps(results,indent=2,ensure_ascii=False))
                print(json.dumps({k:result[k] for k in ('case','arm','status','seconds','model_calls')}),flush=True)
                model.close()
    after=source_hashes();assert before==after,'Production source changed during experiment'
    (OUT/'integrity.json').write_text(json.dumps({'production_source_unchanged':True,'files':len(before),'skill_sha256':digest(OUT/'SKILL.md'),
        'fixture_basis':'Screenshot-grounded reconstruction plus independent transfer fixture; original user corpus unavailable on 8098',
        'generated_code_executed':False,'production_activated':False},indent=2))
    print(str(OUT),flush=True)

if __name__=='__main__':main()
