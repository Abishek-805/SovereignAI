"""Isolated existing Workbench control. No publication or production data writes.

Runs only after the frozen model-only run exits. Model leases are pinned to
Coder; production planning, generation and repair methods remain unchanged.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time
import httpx
import psutil
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.model import LocalModel
from backend.service import Workbench
from backend.settings import Settings
from backend.contracts import WorkbenchError
from experiments.kernel_model import LocalWorker
from experiments.kernel_docker import DockerCommands
from experiments.benchmark_resources import ResourceSamples
from router.sandbox import SandboxResult

OUT=ROOT/'benchmarks/model-comparison/old-workflow'
MODEL='models/qwen2.5-coder-3b-instruct-q4_k_m.gguf'

def load(filename):
    spec=importlib.util.spec_from_file_location(filename.replace('-','_'),ROOT/'benchmarks/overnight-convergence'/filename)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module

def private_oracles():
    from experiments.comparison_extra_tasks import cases
    small=load('code-fidelity-authoring.py')
    complex_cases=load('complex-project-authoring.py')
    return {**{k:v['tests'] for k,v in small.CASES.items()},
            **{k:v['private_test'] for k,v in complex_cases.TASKS.items()},
            **{c['id']:c['private_test'] for c in cases()}}

class RecordedModel(LocalModel):
    def __init__(self,identity):
        super().__init__(verify_semantics=True)
        self.identity=identity
        self.calls=[]
        self.started=time.monotonic()
        self.tokens=0
    def _request_raw(self,method,path,**kwargs):
        completion=method=='POST' and path=='/v1/chat/completions'
        if not completion:return super()._request_raw(method,path,**kwargs)
        if len(self.calls)>=12 or self.tokens>=12000 or time.monotonic()-self.started>=300:
            raise WorkbenchError('benchmark_budget','Shared task budget exhausted')
        self.identity.check_identity()
        payload=dict(kwargs['json'])
        payload.update(model='sovereign-code',temperature=0,max_tokens=min(payload.get('max_tokens',2048),2048,12000-self.tokens))
        seconds=max(.1,300-(time.monotonic()-self.started))
        record={'payload':payload,'prompt_sha256':hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest(),'ttft_seconds':None}
        self.calls.append(record)
        started=time.monotonic()
        try:
            response=self.client.request(method,path,json=payload,timeout=seconds)
            record.update(http_status=response.status_code,response_body=response.text)
            response.raise_for_status()
            data=response.json()
            record['usage']=data.get('usage')
            self.tokens+=data.get('usage',{}).get('completion_tokens',0)
            return data
        finally:record['elapsed_seconds']=time.monotonic()-started

class FixedWorkbench(Workbench):
    def _lease(self,*args,**kwargs):
        self.fixed_identity.check_identity()
        return 'code'
    def _verified_coding_sandbox(self):
        return self.recorded_sandbox

class RecordedSandbox:
    def __init__(self,docker,oracle=None):
        self.docker=docker;self.base=docker.sandbox;self.image_id=docker.image_id;self.executions=[];self.oracle=oracle
    def _ready(self):return self.base._ready()
    def execute(self,code,**kwargs):
        if len(self.executions)>=12:raise WorkbenchError('benchmark_budget','Shared sandbox budget exhausted')
        seconds=300-(time.monotonic()-self.started)
        if seconds<1:raise WorkbenchError('benchmark_budget','Shared deadline exhausted')
        kwargs['timeout']=min(kwargs.get('timeout',120),int(seconds))
        record={'code':code,'input_hashes':{k:hashlib.sha256(v).hexdigest() for k,v in kwargs.get('input_files',{}).items()}}
        self.executions.append(record)
        if self.oracle is not None:
            files={name:data.decode('utf-8') for name,data in kwargs.get('input_files',{}).items()}
            observation=self.docker('python -m unittest discover -p test_contract.py',
                {**files,'test_contract.py':self.oracle},seconds)
            record['actual_command']='python -m unittest discover -p test_contract.py'
            record['shared_oracle_injected_only_at_validation']=True
            result=SandboxResult(observation['exit_code'],observation['stdout'],observation['stderr'],observation['docker_executed'])
        else:
            result=self.base.execute(code,**kwargs)
        record.update(executed=result.executed,exit_code=result.exit_code,stdout=result.stdout,stderr=result.stderr)
        return result
    def __setattr__(self,name,value):
        if name in ('on_output','cancel_event') and hasattr(self,'base'):setattr(self.base,name,value)
        else:object.__setattr__(self,name,value)

def run_tasks():
    tasks=json.loads((ROOT/'benchmarks/model-comparison/frozen-40-task-manifest.json').read_text())
    oracles=private_oracles()
    from experiments.comparison_extra_tasks import cases
    run_specs={c['id']:c for c in cases() if c['category']=='run_project'}
    OUT.mkdir(parents=True,exist_ok=True)
    for task in tasks:
        task_id=task['task_id'];destination=OUT/(task_id+'.json')
        if destination.exists():continue
        data=OUT/'isolated-data'/task_id
        identity=LocalWorker(ROOT/MODEL)
        model=RecordedModel(identity)
        settings=Settings(data_dir=data,project_dir=data/'projects',context=4096,output_tokens=2048,
                          supervisor_model_calls=12,supervisor_tool_calls=40,supervisor_model_switches=1,supervisor_seconds=300)
        work=FixedWorkbench(settings=settings,model=model)
        work.fixed_identity=identity
        docker=DockerCommands(ROOT,data/'docker-tasks')
        sandbox=RecordedSandbox(docker,None if task_id in run_specs else oracles[task_id])
        work.recorded_sandbox=sandbox
        workspace=work.coding.create(task_id)['workspace_id']
        for path,text in task['starting_files'].items():work.coding.write(workspace,path,text)
        started=time.monotonic();sandbox.started=started;model.started=started
        result=None;error=None
        with ResourceSamples(identity.identity['pid']) as resources:
            try:result=work.run_auto_agent(task['request'],workspace_id=workspace)
            except Exception as exc:error={'type':type(exc).__name__,'message':str(exc)}
            candidate={p:v.decode('utf-8') for p,v in work.coding.raw_files(workspace).items()}
            nested=result.get('result',{}) if isinstance(result,dict) else {}
            for change in nested.get('changes',[]):
                path=change.get('path')
                if change.get('action')=='delete':candidate.pop(path,None)
                elif isinstance(change.get('after'),str):candidate[path]=change['after']
            validation=None
            remaining=300-(time.monotonic()-started)
            if remaining>=1:
                validation=docker('python -m unittest discover -p test_contract.py',
                    {**candidate,'test_contract.py':oracles[task_id]},remaining)
                if task_id in run_specs and validation['exit_code']==0:
                    case=run_specs[task_id]
                    observed=any(e.get('executed') and e.get('exit_code')==0 and e.get('stdout')==case['expected_stdout'] for e in sandbox.executions)
                    if not observed or candidate!=task['starting_files']:
                        validation.update(exit_code=1,stderr='Run contract not established by recorded Docker execution and unchanged snapshot')
        status='PASS' if validation and validation['docker_executed'] and validation['exit_code']==0 and error is None else 'BLOCKED' if error else 'FAIL'
        row={'task_id':task_id,'model':'coder','workflow':'existing Workbench.run_auto_agent',
            'task':task,'workspace_id':workspace,'workspace_revision':hashlib.sha256(json.dumps(task['starting_files'],sort_keys=True).encode()).hexdigest(),
            'result':result,'error':error,'candidate':candidate,'validation':validation,'status':status,
            'calls':model.calls,'sandbox_executions':sandbox.executions,'resources':resources.result(),
            'elapsed_seconds':time.monotonic()-started,'model_switches':0,'publication_performed':False,
            'ttft_seconds':None,'ttft_missing_reason':'Existing nonstreaming workflow transport',
            'control_constraints':'Fixed model leases; common outer model/output/sandbox/deadline limits; unchanged production prompts and workflow'}
        destination.write_text(json.dumps(row,indent=2,default=str))
        model.close()
        print('old-workflow',task_id,status,flush=True)

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    existing=[p for p in psutil.process_iter(['name','cmdline']) if (p.info['name'] or '').lower()=='llama-server.exe']
    if len(existing)>1:raise RuntimeError('Multiple heavy servers')
    original=existing[0].info['cmdline'] if existing else None
    if existing:
        slots=httpx.get('http://127.0.0.1:8087/slots',timeout=5).json()
        if any(s.get('is_processing') for s in slots):raise RuntimeError('Existing runtime busy')
        existing[0].terminate();existing[0].wait(20)
    command=[str(ROOT/'runtime/llama-b11132/llama-server.exe'),'-m',str(ROOT/MODEL),'-c','4096','-ngl','999','-np','1','--host','127.0.0.1','--port','8087']
    with (OUT/'runtime.log').open('a') as log:
        process=subprocess.Popen(command,cwd=ROOT,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW)
        started=time.monotonic()
        try:
            while time.monotonic()-started<90:
                if process.poll() is not None:raise RuntimeError('Coder runtime exited')
                try:
                    if httpx.get('http://127.0.0.1:8087/health',timeout=2).status_code==200:break
                except httpx.HTTPError:pass
                time.sleep(.5)
            else:raise TimeoutError('Coder health deadline')
            run_tasks()
        finally:
            process.terminate();process.wait(20)
            if original:subprocess.Popen(original,cwd=ROOT,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW)

if __name__=='__main__':main()
