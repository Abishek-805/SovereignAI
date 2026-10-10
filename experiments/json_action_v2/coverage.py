"""Stage 1A: frozen native action coverage, experimental workspace only."""
import hashlib
import json
import sys
import urllib.request
from dataclasses import asdict
from pathlib import Path
from experiments.comparison_extra_tasks import cases
from experiments.fidelity_v1.runners import load_native
from experiments.fidelity_v1.run_status import inspect_status
from experiments.fidelity_v1.tasks import OUT
from experiments.json_action_v2.compatibility import post
from router.sandbox import CodeSandbox
from workflows.coding_workspace import CodingWorkspace

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'evidence/json-action-adapter-v2/stage-1a'
IMAGE='sha256:6f6ac11cda347a185454338dee35d77003e066579a3261b52b7c6ff1048c8573'
TASKS=[('A','list_dir','path','List the files in the existing app directory using list_dir with a nonempty path. Do not modify any file.'),
       ('B','search_code','query','Use search_code to find the VALUE assignment in this project. Use a useful nonempty query. Do not modify files.'),
       ('C','delete_file','path','Delete only disposable.txt, the experiment-owned disposable file already read below. Preserve every other file.'),
       ('D','run_command','command','Run the documented app module entrypoint using run_command in Docker. Preserve every file and report its output.')]
def save(path,value): path.write_text(json.dumps(value,indent=2,ensure_ascii=False),encoding='utf-8')
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def register():
    BASE.mkdir(parents=True,exist_ok=False)
    text='''# Stage 1A preregistration
Four isolated native-tool coverage cells A=list_dir.path, B=search_code.query, C=delete_file.path, D=run_command.command. One model call per cell, no retry or semantic correction. Frozen native snapshot ToolRegistry, SYSTEM, executor, permission policy and ValidationEngine; current registry-owned Qwen3.5-4B Q4_K_M b11132 context16384 KVq8_0/q8_0, temperature0, thinkingfalse, max_tokens4096, seed absent, tools required, parallel false. No alternate runtime/model.
Fixture: immutable copy of existing experiments.comparison_extra_tasks rp07 starting_files with existing app directory and documented python -m app.runner output17. Add only disposable.txt in C; delete only its overlay draft, no canonical publication. Record fixture hashes before execution. Four original requests listed in coverage-tasks.json frozen before calls. Task-specific requests are experimental inputs, no global prompt change. All ten tools exposed unchanged.
Use native WorkspaceManager/PermissionPolicy/ToolExecutor. Native list/search/delete operate on isolated virtual draft, not a Docker shell; do not alter their architecture. Validate their resulting draft and exact returned observations independently in pinned Docker. run_command uses existing ValidationEngine Docker path. Preserve this distinction in reports. Harness prerequisite read_file for C is recorded explicitly and cannot count as model evidence. Oracle code frozen before output, never supplied to model. Oracle compares actual returned data to fixture-derived expected files/matches/deletion and unchanged unrelated hashes; D requires actual sandbox exit0/stdout17 and unchanged files. Negative controls must fail per oracle.
Qualifying requires raw model-emitted registered target action with nonempty string, Registry.check, existing permission execution and independent Docker oracle PASS. No manual action substitution, schema-only success, model assertion or rewriting. Unexpected/invalid/nonqualifying action stops remaining execution; preserve outcome. Bounds = maximum qualifying observed codepoint length + 256, only four missing fields. Original successful baseline bounds unchanged. Every observation retained.
Before calls verify idle expected worker, no evaluator, pinned Docker available and existing 18-check verifier passed; stop if unavailable. Production/held-out/15-task results immutable. Snapshot previous Stage1 evidence hashes before execution. No T10 B/C or Stage2. After coverage stop on missing evidence; otherwise bounded schema, pinned converter audit, actual-tokenizer worst-case size. Stop on grammar semantic loss or 4096-budget incompatibility; no bound shrinking. Passing sample is not universal size proof. Output token budget4096 is fixed; integers retain unbounded original domains, audit their consequence explicitly.
'''
    (BASE/'PREREGISTRATION.md').write_text(text,encoding='utf-8')
    (BASE/'AMENDMENT-TO-BOUND-POLICY.md').write_text('''# Amendment to bound policy
WHY: successful preserved 15-task evidence contains no qualifying values for list_dir.path, search_code.query, delete_file.path, run_command.command.
PURPOSE: obtain legitimate validated observations without guessed bounds. SCOPE: these four parameters only. Qualifying means a raw model-generated native registry action, nonempty string, actual existing permission-path execution, independent Docker oracle success, preserved raw action/execution. Fixture creation or prerequisite harness reads are not model successes.
NON-CHANGES: production, original benchmark, model/artifact/runtime, native kernel, validator architecture, sandbox image/security, context16384, KVq8_0/q8_0, output4096 and temp0 remain unchanged. Margin remains256. Coverage is separately labeled; never merge outcomes into original comparison. Native file tools inspect draft metadata; independent Docker oracle required, not a claim that native metadata dispatch itself runs Docker.
''',encoding='utf-8')
    fixture=next(task for task in cases() if task['id']=='rp07')
    save(BASE/'registered-fixture.json',{'source':'experiments/comparison_extra_tasks.py:cases rp07','source_sha256':sha(ROOT/'experiments/comparison_extra_tasks.py'),'files':fixture['starting_files'],'disposable_addition':{'disposable.txt':'STAGE1A DISPOSABLE\n'}})
    save(BASE/'coverage-tasks.json',TASKS)
    frozen={str(p.relative_to(ROOT)):sha(p) for p in (ROOT/'evidence/json-action-adapter-v2/stage-1').rglob('*') if p.is_file()}
    save(BASE/'evidence-inventory.json',{'previous_stage1_sha256':frozen,'preregistration_sha256':sha(BASE/'PREREGISTRATION.md'),'amendment_sha256':sha(BASE/'AMENDMENT-TO-BOUND-POLICY.md'),'tasks_sha256':sha(BASE/'coverage-tasks.json'),'fixture_sha256':sha(BASE/'registered-fixture.json')})
    print('Registered and hashed Stage1A before execution',flush=True)

ORACLE='''import os,shutil,json,hashlib
from pathlib import Path
root=Path('/output/project')
shutil.copytree('/input',root,ignore=lambda source,names:{'program.py'} if Path(source)==Path('/input') else set())
os.chdir(root)
observation=OBSERVATION
expected=EXPECTED
kind=KIND
actual={str(p.relative_to(root)).replace('\\\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}
assert actual==expected['hashes'], (actual,expected['hashes'])
if kind=='A': assert observation['files']==expected['files']
if kind=='B': assert observation['matches']==expected['matches'] and bool(observation['matches'])
if kind=='C': assert observation['deleted']=='disposable.txt' and not (root/'disposable.txt').exists() and observation['published'] is False
if kind=='D': assert observation['container_executed'] is True and observation['exit_code']==0 and observation['stdout']=='17\\n'
print('INDEPENDENT_COVERAGE_PASS')
'''
def execute(delete_target='disposable.txt', required_search_match=None):
    inventory=json.loads((BASE/'evidence-inventory.json').read_text())
    assert sha(BASE/'PREREGISTRATION.md')==inventory['preregistration_sha256'] and sha(BASE/'AMENDMENT-TO-BOUND-POLICY.md')==inventory['amendment_sha256']
    assert not inspect_status(OUT)['running_verified']
    with urllib.request.urlopen('http://127.0.0.1:8087/slots',timeout=5) as r: assert not any(x['is_processing'] for x in json.load(r))
    with urllib.request.urlopen('http://127.0.0.1:8087/props',timeout=5) as r: save(BASE/'runtime-props.json',json.load(r))
    from scripts.verify_docker_sandbox import verify
    checks=verify(IMAGE); save(BASE/'docker-verifier.json',checks)
    assert len(checks)==18 and all(checks.values())
    native=load_native(); registry=native.ToolRegistry(); allrows=[]
    fixture=json.loads((BASE/'registered-fixture.json').read_text())['files']
    save(BASE/'oracle-source.json',{'source':ORACLE,'sha256':hashlib.sha256(ORACLE.encode()).hexdigest()})
    for identity,name,key,request in TASKS:
        cell=BASE/identity; cell.mkdir()
        coding=CodingWorkspace(cell/'workspace'); wid=coding.create('Stage1A '+identity)['workspace_id']
        for path,content in fixture.items(): coding.write(wid,path,content)
        if identity=='C': coding.write(wid,delete_target,'STAGE1A DISPOSABLE\n')
        workspace=native.WorkspaceManager(coding,wid,request)
        sandbox=CodeSandbox('docker',IMAGE,cell/'sandbox'); session=native.AgentSession(request,wid,'sovereign-text')
        validator=native.ValidationEngine(workspace,sandbox,session); executor=native.ToolExecutor(workspace,validator,registry)
        initial=workspace.files(); save(cell/'fixture.json',{'files':{p:b.decode() for p,b in initial.items()},'revision':workspace.revision})
        messages=[{'role':'system','content':native.SYSTEM},{'role':'user','content':json.dumps({'original_request':request,'workspace_id':wid,'workspace_root':'/output/project','current_files':sorted(initial),'revision':workspace.revision})}]
        if identity=='C':
            read=executor.execute('read_file',{'path':delete_target}); save(cell/'harness-prerequisite-read.json',{'actor':'harness','not_model_evidence':True,'result':read})
            messages[1]['content']+='\nPrerequisite harness read_file observation (not a model action): '+json.dumps(read)
            before=sandbox.execute("from pathlib import Path\np=Path('/input')/"+repr(delete_target)+"\nassert p.is_file() and p.read_text()=='STAGE1A DISPOSABLE\\n'\nprint('DISPOSABLE_PRECONDITION_PASS')",input_files=initial)
            before_result=asdict(before); before_result.pop('output_files',None); save(cell/'disposable-before-docker.json',before_result)
            assert before.executed and before.exit_code==0, 'Disposable precondition failed'
        payload={'model':'sovereign-text','messages':messages,'tools':registry.schemas(),'tool_choice':'required','parallel_tool_calls':False,'temperature':0,'max_tokens':4096,'chat_template_kwargs':{'enable_thinking':False}}
        raw=post(cell/'model',payload); row={'parameter':name+'.'+key,'task_id':identity,'model_generated':True,'qualifies':False,'executed':False,'independent_validation':False,'raw_path':str((cell/'model').relative_to(ROOT))}
        try:
            response=raw['response']; calls=response['choices'][0]['message'].get('tool_calls',[])
            assert len(calls)==1,'Expected one native action'
            fn=calls[0]['function']; args=json.loads(fn['arguments']) if isinstance(fn['arguments'],str) else fn['arguments']
            row.update(action={'name':fn['name'],'arguments':args})
            assert fn['name']==name and isinstance(args.get(key),str) and bool(args[key]),'Wrong target or empty value'
            registry.check(name,args)
            if identity=='A': assert args[key].strip('/')=='app','Must list existing app directory'
            if identity=='C': assert args[key]==delete_target,'Only disposable target authorized'
            if identity=='D': assert args[key]=='python -m app.runner','Only documented read-only command authorized'
            observation=executor.execute(name,args); row.update(executed=True,value=args[key],characters=len(args[key]),bytes=len(args[key].encode()),nonempty=True,execution=observation)
            files=workspace.files(); expected={'hashes':{p:hashlib.sha256(b).hexdigest() for p,b in initial.items() if not(identity=='C' and p==delete_target)}}
            if identity=='A': expected['files']=sorted(p for p in initial if p.startswith('app/'))
            if identity=='B': expected['matches']=[{'path':p,'line':i,'text':line[:300]} for p,b in initial.items() for i,line in enumerate(b.decode().splitlines(),1) if args[key] in line][:100]
            if identity=='B' and required_search_match:
                expected['required_match']=required_search_match
            oracle_source=ORACLE.replace('disposable.txt',delete_target)
            if required_search_match:
                oracle_source += "\nif kind=='B': assert expected['required_match'] in observation['matches']\n"
            script=oracle_source.replace('OBSERVATION',repr(observation)).replace('EXPECTED',repr(expected)).replace('KIND',repr(identity))
            save(cell/'execution.json',row); (cell/'oracle.py').write_text(script)
            result=asdict(sandbox.execute(script,input_files=files)); result.pop('output_files',None); save(cell/'oracle-result.json',result)
            row['independent_validation']=result['executed'] and result['exit_code']==0 and 'INDEPENDENT_COVERAGE_PASS' in result['stdout']
            wrong=dict(observation)
            if identity=='A': wrong['files']=[]
            if identity=='B': wrong['matches']=[]
            if identity=='C': wrong['deleted']='other.txt'
            if identity=='D': wrong['stdout']='wrong\n'
            negative=asdict(sandbox.execute(script.replace(repr(observation),repr(wrong)),input_files=files)); negative.pop('output_files',None); save(cell/'oracle-negative-control.json',negative)
            row['negative_control_rejected']=negative['executed'] and negative['exit_code']!=0
            row['canonical_unchanged']=coding.raw_files(wid)==initial
            row['qualifies']=row['independent_validation'] and row['negative_control_rejected'] and row['canonical_unchanged']
        except Exception as exc: row['error']=str(exc)
        allrows.append(row); save(BASE/'observations.json',allrows)
        print(identity,row['qualifies'],row.get('error',''),flush=True)
        if not row['qualifies']: break
    save(BASE/'nonqualifying-observations.json',[r for r in allrows if not r['qualifies']])
    save(BASE/'bound-derivations.json',[{'parameter':r['parameter'],'observation_count':1,'largest_observed_value':r['value'],'observed_characters':r['characters'],'margin':256,'derived_maxLength':r['characters']+256,'source':r['raw_path']} for r in allrows if r['qualifies']])

if __name__=='__main__':
    if sys.argv[1]=='register': register()
    elif sys.argv[1]=='execute': execute()
