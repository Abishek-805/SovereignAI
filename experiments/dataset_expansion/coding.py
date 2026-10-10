"""Actual Docker verification and native tool replay of public reference candidates."""
import ast, copy, difflib, hashlib, json, re, sys, time
from collections import Counter
from pathlib import Path
from experiments.dataset_expansion.prepare import ROOT, IMAGE, rows, save, jsonl, digest
from experiments.dataset_expansion.references import sample, source, message
from router.sandbox import CodeSandbox
from workflows.coding_workspace import CodingWorkspace
from workflows import agent_kernel as native

SENTINEL='Existing user content must survive.\n'
HELPER='def preserved_helper():\n    return "unchanged-behavior"\n\n'
ALLOWED={'math','cmath','collections','itertools','functools','operator','re','heapq','bisect','array','string','fractions','decimal','statistics','copy','typing','random'}

def normalized_tree(code):
    tree=ast.parse(code)
    for n in ast.walk(tree):
        if isinstance(n,(ast.Name,ast.arg)):n.id='name' if isinstance(n,ast.Name) else getattr(n,'id',None); n.arg='arg' if isinstance(n,ast.arg) else getattr(n,'arg',None)
        if isinstance(n,ast.FunctionDef):n.name='function'
        if isinstance(n,ast.Constant) and not isinstance(n.value,(bool,type(None))):n.value=0 if isinstance(n.value,(float,int)) else 'literal'
    return ast.dump(tree,include_attributes=False)

def mutation(code,index):
    tree=ast.parse(code);lines=code.splitlines(True)
    if index%4==0:
        node=next((n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef)),None)
        if node and ':' in lines[node.lineno-1]:
            old=lines[node.lineno-1].rstrip('\r\n');new=old.rsplit(':',1)[0]+old.rsplit(':',1)[1]
            return new,old,code.replace(old,new,1),'syntax-missing-colon'
    if index%4==1:
        n=next((n for n in ast.walk(tree) if isinstance(n,ast.Compare) and len(n.ops)==1),None)
        if n:
            old=ast.get_source_segment(code,n);changed=copy.deepcopy(n)
            replacements={ast.Eq:ast.NotEq,ast.NotEq:ast.Eq,ast.Lt:ast.GtE,ast.Gt:ast.LtE,ast.LtE:ast.Gt,ast.GtE:ast.Lt}
            if type(n.ops[0]) in replacements:
                changed.ops[0]=replacements[type(n.ops[0])]();new=ast.unparse(changed)
                if old and code.count(old)==1:return new,old,code.replace(old,new,1),'comparison-boundary'
    n=next((n for n in ast.walk(tree) if isinstance(n,ast.Return) and n.value is not None),None)
    if n:
        old=ast.get_source_segment(code,n);new='return None'
        if old and old!=new and code.count(old)==1:return new,old,code.replace(old,new,1),'incorrect-return-value'
    raise ValueError('No safe unique localized mutation available')

def acceptance(task,path):
    imports=task.get('test_setup_code','')
    tests=task['test_list']+task.get('challenge_test_list',[])
    lines=['import unittest','from pathlib import Path','from '+path[:-3].replace('/','.')+' import *',imports,'class Acceptance(unittest.TestCase):']
    for i,test in enumerate(tests):lines+=[' def test_public_'+str(i)+'(self):',*['  '+line for line in test.splitlines()]]
    lines+=[' def test_preservation(self):','  self.assertEqual(preserved_helper(), "unchanged-behavior")','  self.assertEqual(Path("sentinel.txt").read_text(), '+repr(SENTINEL)+')']
    return '\n'.join(lines)+'\n'

def freeze(out):
    target=out/'coding-candidates.jsonl'
    if target.exists():return rows(target)
    definitions=[];exclusions=[];seen_shapes=set();seen_requests=set()
    tasks=rows(out/'sources/mbpp.jsonl')
    # Use training first; any public dev/test references remain explicitly labeled.
    tasks.sort(key=lambda t:(0 if t['task_id']>=601 else 1 if t['task_id']>=511 else 2, hashlib.sha256(t['text'].encode()).hexdigest()))
    for task in tasks:
        try:
            code=task['code'].replace('\r\n','\n').rstrip()+'\n';tree=ast.parse(code)
            imports={n.module.split('.')[0] for n in ast.walk(tree) if isinstance(n,ast.ImportFrom) and n.module}|{a.name.split('.')[0] for n in ast.walk(tree) if isinstance(n,ast.Import) for a in n.names}
            if imports-ALLOWED or len(code)>9000 or not any(isinstance(n,ast.FunctionDef) for n in ast.walk(tree)):raise ValueError('Unsupported size/import/function coverage')
            if any(isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id in {'eval','exec','open','input','compile','__import__'} for n in ast.walk(tree)):raise ValueError('Unsafe reference primitive')
            shape=normalized_tree(code);request=re.sub(r'\d+','NUMBER',' '.join(task['text'].lower().split()))
            if shape in seen_shapes or request in seen_requests:raise ValueError('Superficial code/request duplicate')
            seen_shapes.add(shape);seen_requests.add(request)
            index=len(definitions);category='agentic' if index<330 else 'coding'
            is_repair=index%3!=2 if category=='agentic' else index%2==0
            broken,repaired,mutant,error_type=mutation(code,index)
            layout=['worker.py','src/worker.py','engine/worker.py'][index%3]
            initial=HELPER+(mutant if is_repair else '')
            desired=HELPER+code
            test=acceptance(task,layout)
            files={layout:initial,'test_acceptance.py':test,'sentinel.txt':SENTINEL}
            if '/' in layout:files[layout.split('/')[0]+'/__init__.py']=''
            if index%5==0:files['docs/usage.md']='Existing documentation; keep this file unchanged.\n'
            actions=[('list_dir',{'path':''}),('read_file',{'path':'test_acceptance.py'})]
            if index%4==0:actions+=[('search_code',{'query':'def '}),('read_file',{'path':layout})]
            else:actions.append(('read_file',{'path':layout}))
            if is_repair:
                actions.append(('run_tests',{}));actions.append(('apply_patch',{'path':layout,'old_text':broken,'new_text':repaired}))
            else:actions.append(('apply_patch',{'path':layout,'old_text':HELPER,'new_text':desired}))
            if index%7==0:actions.append(('run_command',{'command':'python -m compileall -q '+layout.split('/')[0]}))
            actions.extend([('run_tests',{}),('finish',{})])
            request=('Repair' if is_repair else 'Implement')+' the requested behavior in '+layout+': '+task['text']+' Preserve preserved_helper(), sentinel.txt, supplied tests and existing documentation. Inspect state, make only the required change, run the supplied tests in Docker and finish for review.'
            definitions.append({'id':'mbpp-'+category+'-'+str(task['task_id']),'category':category,'family':'mbpp:'+str(task['task_id']),'request':request,'public_task':task,'files':files,'implementation_path':layout,'desired':desired,'mutant':HELPER+mutant,'mutation':{'old_text':broken,'new_text':repaired,'kind':error_type},'repair':is_repair,'actions':actions,'source_split':'train' if task['task_id']>=601 else 'validation' if task['task_id']>=511 else 'public-test (not a SovereignAI holdout)'})
            if len(definitions)==570:break
        except (SyntaxError,ValueError,KeyError) as exc:exclusions.append({'public_id':task['task_id'],'reason':str(exc)})
    jsonl(target,definitions);save(out/'coding-selection.json',{'selected':len(definitions),'categories':dict(Counter(d['category'] for d in definitions)),'exclusions':exclusions,'sha256':digest(target),'frozen_before_execution':True})
    return definitions

def snapshot_runner():
    return "import shutil,os\nfrom pathlib import Path\nshutil.copytree('/input','/output/project',ignore=lambda p,n:{'program.py'} if p=='/input' else set())\nos.chdir('/output/project')\nimport sys;sys.path.insert(0,'/output/project')\nimport unittest\nsuite=unittest.defaultTestLoader.discover('.')\nassert suite.countTestCases()>0\nresult=unittest.TextTestRunner(verbosity=2).run(suite)\nsys.exit(0 if result.wasSuccessful() else 1)\n"

class ReferenceTeacher:
    """Offline reference adapter. No HTTP request or fabricated observation."""
    def __init__(self,definition,directory):self.definition=definition;self.directory=directory;self.records=[];self.index=0
    def agent_tool_turn(self,messages,schemas,alias):
        if self.index>=len(self.definition['actions']):raise ValueError('Reference action program exhausted')
        if messages[-1]['role']=='tool':
            observation=json.loads(messages[-1]['content'])
            if observation.get('error'):raise ValueError('Actual tool failure: '+str(observation))
            if observation.get('passed') is False and self.index>0 and self.definition['actions'][self.index-1][0]=='run_tests' and not (self.definition['repair'] and self.definition['actions'][self.index][0]=='apply_patch'):raise ValueError('Unexpected verification failure')
        name,args=self.definition['actions'][self.index];self.index+=1
        response={'role':'assistant','content':'','tool_calls':[{'id':'offline-reference-'+str(self.index),'type':'function','function':{'name':name,'arguments':json.dumps(args,ensure_ascii=False)}}]}
        record={'teacher':'offline MBPP public-reference adapter','provider_model_calls':0,'request':{'messages':copy.deepcopy(messages),'tools':schemas,'model':alias},'response':{'choices':[{'message':response}]}}
        self.records.append(record);save(self.directory/f'turn-{self.index:03}.json',record)
        return response

def evaluate(out,limit=None):
    definitions=freeze(out);raw=out/'coding-raw';raw.mkdir(exist_ok=True)
    sandbox=CodeSandbox('docker',IMAGE,out/'sandbox');sandbox._ready()
    from scripts.verify_docker_sandbox import verify
    if not (out/'docker-verifier.json').exists():
        checked=verify(IMAGE);save(out/'docker-verifier.json',checked);assert len(checked)==18 and all(checked.values())
    quota={'agentic':298,'coding':198};completed=0
    for definition in definitions:
        directory=raw/definition['id'];directory.mkdir(exist_ok=True);result_path=directory/'outcome.json'
        counts=Counter(json.loads(p.read_text(encoding='utf-8'))['category'] for p in raw.glob('*/outcome.json') if json.loads(p.read_text(encoding='utf-8')).get('passed'))
        if result_path.exists() or counts[definition['category']]>=quota[definition['category']]:continue
        started=time.monotonic();files=definition['files'];outcome={'id':definition['id'],'category':definition['category'],'passed':False,'repair':definition['repair'],'definition_sha256':hashlib.sha256(json.dumps(definition,sort_keys=True).encode()).hexdigest(),'provider_model_calls':0,'teacher':'offline public-reference adapter'}
        try:
            save(directory/'definition.json',definition)
            # Public oracle adequacy: a deliberately wrong candidate must fail.
            negative_files={**files,definition['implementation_path']:definition['mutant']}
            negative=sandbox.execute(snapshot_runner(),input_files={p:c.encode() for p,c in negative_files.items()},timeout=30)
            neg={'executed':negative.executed,'exit_code':negative.exit_code,'stdout':negative.stdout,'stderr':negative.stderr}
            save(directory/'negative-control.json',neg)
            if not negative.executed:raise ValueError('SANDBOX: negative control did not execute')
            if negative.exit_code==0:raise ValueError('VALIDATION: supplied tests did not detect preregistered incorrect implementation')
            correct_files={**files,definition['implementation_path']:definition['desired']}
            correct=sandbox.execute(snapshot_runner(),input_files={p:c.encode() for p,c in correct_files.items()},timeout=30)
            oracle={'executed':correct.executed,'exit_code':correct.exit_code,'stdout':correct.stdout,'stderr':correct.stderr,'image':IMAGE,'candidate_sha256':hashlib.sha256(definition['desired'].encode()).hexdigest(),'negative_control_detected':True}
            save(directory/'oracle.json',oracle)
            if not correct.executed or correct.exit_code!=0:raise ValueError('CODE_GENERATION: public reference failed unchanged supplied tests')
            provenance=source('MBPP',definition['public_task']['task_id'],'CC-BY-4.0',attribution='Austin et al., Google Research, 2021',source_split=definition['source_split'],conversion='public reference with preserved helper and actual Docker verification')
            if definition['category']=='agentic':
                coding=CodingWorkspace(directory/'workspace');wid=coding.create(definition['id'])['workspace_id']
                for path,text in files.items():coding.write(wid,path,text)
                teacher=ReferenceTeacher(definition,directory)
                result=native.AgentLoop().run(coding,wid,definition['request'],teacher,sandbox,'offline-public-reference',timeout_seconds=180)
                save(directory/'native-result.json',result)
                if result['agent_state']!='READY_FOR_REVIEW' or not result['checks']['behavior_verified']:raise ValueError('TOOL: native trajectory did not independently finish '+str(result.get('error')))
                assert coding.raw_files(wid)=={p:c.encode() for p,c in files.items()}
                assert len(result['changes'])==1 and result['changes'][0]['path']==definition['implementation_path']
                messages=copy.deepcopy(teacher.records[-1]['request']['messages'])+[teacher.records[-1]['response']['choices'][0]['message']]
                messages.append({'role':'tool','tool_call_id':messages[-1]['tool_calls'][0]['id'],'content':json.dumps(result['events'][-1]['result'])})
                messages.append(message('assistant','Independent Docker validation passed. The draft is ready for review; existing files and unrelated behavior are preserved.'))
                provenance.update(kind='offline_public_reference_teacher',not_laptop_model_output=True,provider_model_calls=0)
                candidate=sample(definition['id'],'agentic',definition['family'],messages,provenance,{'type':'actual native loop plus immutable public assertions, broken negative control and preservation','passed':True,'evidence':str((directory/'native-result.json').relative_to(ROOT))},tools=native.ToolRegistry().schemas(),language='python',repair=definition['repair'],capability=definition['mutation']['kind'] if definition['repair'] else 'inspect-implement-verify',initial_state=files,final_diff=result['diff'],metrics={'offline_teacher_turns':len(teacher.records),'provider_model_calls':0,'tool_calls':result['metrics']['tool_calls'],'sandbox_runs':result['metrics']['sandbox_runs'],'repairs':result['metrics']['repairs']})
            else:
                prompt={'task':definition['request'],'existing_file':files[definition['implementation_path']],'immutable_tests':files['test_acceptance.py']}
                if definition['repair']:prompt['actual_docker_error']=negative.stderr
                candidate=sample(definition['id'],'coding',definition['family'],[message('system','Return the complete corrected implementation. Preserve existing unrelated functions and satisfy the immutable test contract.'),message('user',prompt),message('assistant','```python\n'+definition['desired']+'```')],provenance,{'type':'unchanged public reference independently executed in pinned Docker; negative control detects defect','passed':True,'evidence':str((directory/'oracle.json').relative_to(ROOT))},language='python',repair=definition['repair'],capability=definition['mutation']['kind'] if definition['repair'] else 'implementation')
            candidate['quality']['verified']=True;save(directory/'candidate.json',candidate);outcome['passed']=True
        except Exception as exc:
            outcome['error']=str(exc);outcome['failure_taxonomy']=str(exc).split(':',1)[0] if ':' in str(exc) else 'TOOL_OR_ENVIRONMENT'
        outcome['latency_seconds']=time.monotonic()-started;save(result_path,outcome);completed+=1
        all_results=[json.loads(p.read_text(encoding='utf-8')) for p in raw.glob('*/outcome.json')]
        save(out/'coding-progress.json',{'executed':len(all_results),'accepted':dict(Counter(r['category'] for r in all_results if r['passed'])),'rejected':sum(not r['passed'] for r in all_results),'remaining_quota':{c:max(0,q-sum(r['passed'] and r['category']==c for r in all_results)) for c,q in quota.items()},'provider_model_calls':0,'training_started':False})
        print(definition['id'],outcome['passed'],outcome.get('error',''),flush=True)
        if limit and completed>=limit:break
    return out

if __name__=='__main__':evaluate(Path(sys.argv[1]).resolve(),int(sys.argv[2]) if len(sys.argv)>2 else None)
