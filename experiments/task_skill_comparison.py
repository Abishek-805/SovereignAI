"""New diagnostic: paired skills OFF/ON, no historical benchmark changes."""
import hashlib,json,statistics,time,sys,os
from pathlib import Path
import httpx
from backend.model import LocalModel
from rag.tables import compile_outcome_query,execute_query,literal_entity_coverage
from rag.answer import _messages
from backend.contracts import WorkbenchError

OUT=Path(os.environ.get('SOVEREIGN_SKILL_EVAL_DIR','outputs/task-skill-comparison'))
TABLE={'name':'Inspections','columns':['ID','Status','Score'],'records':[
 {'ID':'NORTH01','Status':'PASS','Score':21},
 {'ID':'NORTH02','Status':'FAIL','Score':10},
 {'ID':'SOUTH01','Status':'PASS','Score':25},
 {'ID':'SOUTH02','Status':'PASS','Score':18}]}
TASKS=[
 {'id':'single_count_after_comparison','kind':'data','question':'How many NORTH inspections passed?',
  'history':['user: Compare NORTH and SOUTH pass percentages','assistant: NORTH 50%, SOUTH 100%.'], 'expected':1},
 {'id':'single_count_no_threshold','kind':'data','question':'How many NORTH inspections passed?','expected':1},
 {'id':'two_group_rates','kind':'data','question':'Compare NORTH and SOUTH pass percentages.','expected':[50.0,100.0]},
 {'id':'failed_outcomes','kind':'data','question':'How many SOUTH inspections failed?','expected':0},
 {'id':'numeric_rule_complement','kind':'data','question':'Scores below 18 are failed. Count passing NORTH inspections using scores.','expected':1},
 {'id':'missing_rule_is_unknown','kind':'data','question':'How many NORTH inspections passed?', 'numeric_only':True,'expected':'needs_input'},
 {'id':'run_program','kind':'operations','question':'Run the existing web application and tell me how to run it.','expected':'run'},
 {'id':'create_functional_folder','kind':'operations','question':'Create an array_tools folder containing a working Python binary search implementation.','expected':'file_edit'},
 {'id':'rename_document','kind':'operations','question':'Rename Knowledge notes.txt to guide.txt.','expected':'document_rename'},
 {'id':'exception_semantics','kind':'code','question':'Implement get_invoice(invoices, key) returning invoices[key] and raising KeyError when the key is missing. Include invoice_total(items) returning sum of quantities times prices. Return complete Python source only.',
  'oracle':"assert get_invoice({'x': 7},'x') == 7\ntry:\n get_invoice({},'missing')\nexcept KeyError:\n pass\nelse:\n raise AssertionError('must raise KeyError')\nassert invoice_total([(2,3),(1,4)]) == 10\nprint('ORACLE_PASS')"},
 {'id':'repair_preserves_symbols','kind':'code','question':"Repair this module. Original requirements: parse_amount returns float(amount); invoice_total(items) returns sum(quantity*price); get_invoice(data,key) returns data[key] and raises KeyError if absent. Actual Docker error: AssertionError: get_invoice must raise KeyError, not return it. Preserve all required functions. Current module:\ndef parse_amount(amount): return float(amount)\ndef invoice_total(items): return sum(q*p for q,p in items)\ndef get_invoice(data,key): return data.get(key, KeyError(key))\nReturn complete repaired source only.",
  'oracle':"assert parse_amount('12.5') == 12.5\nassert invoice_total([(2,3)]) == 6\nassert get_invoice({'a':4},'a')==4\ntry:\n get_invoice({},'missing')\nexcept KeyError:\n pass\nelse:\n raise AssertionError('must raise KeyError')\nprint('ORACLE_PASS')"},
 {'id':'synthesize_supported_parts','kind':'answer','question':'What equipment and operating schedule are available, and what is the inspection pass threshold?',
  'source':'The laboratory has two repair bays and opens Monday through Friday from 09:00 to 17:00. No inspection score criteria are recorded.'}
]

def save(path,data):
    path.write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding='utf-8')

def code_oracle(api,source,oracle):
    workspace=api.post('/coding/workspaces',json={'name':'Skill comparison isolated validation'});workspace.raise_for_status()
    wid=workspace.json()['workspace_id']
    written=api.put(f'/coding/workspaces/{wid}/files/check.py',json={'content':source+'\n\n'+oracle+'\n'});written.raise_for_status()
    job=api.post(f'/coding/workspaces/{wid}/jobs',json={'kind':'run','target':'check.py'});job.raise_for_status()
    jid=job.json()['job_id']
    for _ in range(150):
        response=api.get('/coding/jobs/'+jid);response.raise_for_status();result=response.json()
        if result['state']!='running':
            passed=result['state']=='completed' and result.get('result',{}).get('exit_code')==0 and 'ORACLE_PASS' in result.get('result',{}).get('stdout','')
            return passed,{'workspace_id':wid,'job':result}
        time.sleep(1)
    return False,{'workspace_id':wid,'error':'oracle execution timeout'}

def evaluate(model,task,api):
    kind=task['kind'];q=task['question']
    if kind=='data':
        table=json.loads(json.dumps(TABLE))
        if task.get('numeric_only'):
            table['columns']=['ID','Score']
            table['records']=[{k:v for k,v in row.items() if k!='Status'} for row in table['records']]
        catalog=[{'id':'T1','document':'inspections.csv','sheet':table['name'],'title_rows':[],
            'columns':table['columns'],'row_count':len(table['records']),'sample':table['records'][:2],
            'literal_entity_coverage':literal_entity_coverage(table,q),
            'categorical_values':{'Status':['PASS','FAIL']} if not task.get('numeric_only') else {}}]
        query=model.plan_table_query(q,catalog,task.get('history',[]))
        try:
            plan=compile_outcome_query(query['_measure'],{'T1':({'document_id':'fixture'},table)},q,task.get('history',[])) if '_measure' in query else query
            result=execute_query(table,plan)
            extras=plan.get('additional_queries',[])
            if isinstance(task['expected'],list):
                values=[execute_query(table,{**p,'operation':plan['operation']})['summaries'][0]['percentage'] for p in [plan,*extras]]
                passed=sorted(values)==sorted(task['expected']) and len(values)==2
            else:passed=result.get('value')==task['expected']
            return passed,{'query':query,'compiled':plan,'result':result}
        except WorkbenchError as error:
            return task['expected']=='needs_input' and error.code=='needs_input',{'query':query,'error':str(error),'error_code':error.code}
    if kind=='operations':
        operations=model.plan_application_tools(q,[{'name':'notes.txt','document_id':'notes'}],
            [{'name':'server/app.py'},{'name':'server/templates/index.html'}],folders=['server','server/templates'],
            project={'name':'Demo','workspace_id':'fixture'})
        if task['expected']=='run':
            passed=any(op['tool']=='file_run' and op['target']=='server/app.py' or
                op['tool']=='terminal' and op['target'] in {'','server','Demo'} and op['value'] in {'python server/app.py','python3 server/app.py','python app.py','python3 app.py'} for op in operations)
        else:passed=any(op['tool']==task['expected'] for op in operations)
        if task['expected']=='document_rename':passed=passed and len(operations)==1 and operations[0]['target']=='notes.txt' and operations[0]['value']=='guide.txt'
        return passed,{'operations':operations,'validation_kind':'operation_contract_only'}
    if kind=='code':
        candidate=model.complete_code([{'role':'system','content':'Implement the request. Return complete Python in the required code field.'},{'role':'user','content':q}],max_tokens=1536)
        passed,validation=code_oracle(api,candidate['code'],task['oracle'])
        return passed,{'candidate':candidate,'validation':validation}
    answer=model.complete(_messages(q,[{'label':'S1','display_name':'laboratory.txt','page':1,'line_start':1,'line_end':1,'text':task['source']}]),max_tokens=512)['result']
    text=answer.get('answer','').lower()
    passed=any(value in text for value in ['two','2']) and all(value in text for value in ['09:00','17:00','[s1]']) and any(value in text for value in ['no','not','unknown','missing'])
    return passed,{'answer':answer,'validation_kind':'required_supported_facts_and_missing_rule'}

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    fixtures=json.dumps(TASKS,sort_keys=True).encode();fixture_hash=hashlib.sha256(fixtures).hexdigest()
    save(OUT/'tasks.json',TASKS)
    api=httpx.Client(base_url='http://127.0.0.1:8088',timeout=150)
    status=api.get('/status').json()
    if status.get('busy'):raise RuntimeError('Do not overlap an active task')
    save(OUT/'manifest.json',{'diagnostic':'Task skills OFF/ON','fixtures_sha256':fixture_hash,'baseline_commit':'6108b51',
        'fixed_model':'currently resident Qwen3.5-4B; no model switches','temperature':0,'verify_semantics':False,
        'order':'counterbalanced by task index','retries':0,'status':status,'limitations':'12 component cases, not an all-model benchmark or full end-to-end task completion study. Coding candidates independently executed in existing Docker sandbox.'})
    for index,task in enumerate(TASKS):
        for enabled in ([False,True] if index%2==0 else [True,False]):
            arm='after' if enabled else 'before';path=OUT/(task['id']+'-'+arm+'.json')
            if path.exists():continue
            model=LocalModel(skills_enabled=enabled,verify_semantics=False)
            raw=[];original=model._request_raw
            def record(method,path,**kwargs):
                result=original(method,path,**kwargs)
                if path=='/v1/chat/completions':raw.append({'request':kwargs.get('json'),'response':result})
                return result
            model._request_raw=record
            start=time.perf_counter()
            try:
                passed,result=evaluate(model,task,api);state='PASS' if passed else 'FAIL'
            except Exception as error:state='BLOCKED' if isinstance(error,httpx.HTTPError) else 'FAIL';result={'error':str(error),'type':type(error).__name__}
            elapsed=time.perf_counter()-start
            save(path,{'task_id':task['id'],'category':task['kind'],'arm':arm,'status':state,'latency_seconds':elapsed,'model_calls':len(raw),
                'prompt_tokens':sum(r['response'].get('usage',{}).get('prompt_tokens',0) for r in raw),'result':result,'raw':raw})
            model.close();save(OUT/'progress.json',{'last_task':task['id'],'arm':arm,'completed':len(list(OUT.glob('*-before.json')))+len(list(OUT.glob('*-after.json'))),'total':24})
            print(task['id'],arm,state,round(elapsed,2),flush=True)
    rows=[json.loads(path.read_text(encoding='utf-8')) for path in OUT.glob('*-*.json') if path.name.endswith(('-before.json','-after.json'))]
    summary={}
    for arm in ['before','after']:
        selected=[row for row in rows if row['arm']==arm]
        summary[arm]={'coverage':len(selected),'PASS':sum(row['status']=='PASS' for row in selected),'FAIL':sum(row['status']=='FAIL' for row in selected),'BLOCKED':sum(row['status']=='BLOCKED' for row in selected),
            'median_latency_seconds':statistics.median(row['latency_seconds'] for row in selected),'model_calls':sum(row['model_calls'] for row in selected),'prompt_tokens':sum(row['prompt_tokens'] for row in selected)}
    paired=[]
    for task in TASKS:
        pair={row['arm']:row for row in rows if row['task_id']==task['id']}
        paired.append({'task_id':task['id'],'before':pair['before']['status'],'after':pair['after']['status']})
    save(OUT/'summary.json',{'arms':summary,'paired':paired,'complete':len(rows)==24})
    print(json.dumps(summary),flush=True)

if __name__=='__main__':main()
