"""One bounded observation envelope shared by nested task workflows."""
from contextvars import ContextVar
from dataclasses import asdict, dataclass
from functools import wraps
import inspect
import json
import os
from pathlib import Path
import time
from uuid import uuid4

from backend.contracts import WorkbenchError
from router.task_completion import observe_completion

CURRENT_SUPERVISOR=ContextVar('task_supervisor',default=None)


@dataclass(frozen=True)
class SupervisorLimits:
    model_calls:int=64
    tool_calls:int=12
    model_switches:int=4
    seconds:float=900

    def __post_init__(self):
        for name in ('model_calls','tool_calls','model_switches'):
            value=getattr(self,name)
            if isinstance(value,bool) or not isinstance(value,int) or not 1<=value<=1000:
                raise ValueError('Supervisor '+name+' must be an integer between 1 and 1000')
        if isinstance(self.seconds,bool) or not isinstance(self.seconds,(int,float)) or not 0<self.seconds<=3600:
            raise ValueError('Supervisor seconds must be between zero and 3600')


class TaskSupervisor:
    def __init__(self,goal,context,limits=None,job=None):
        self.id=uuid4().hex
        self.goal=goal
        # Defensive JSON copy prevents caller mutation changing authority scope.
        self.context=json.loads(json.dumps(context))
        self.limits=limits or SupervisorLimits()
        self.job=job
        self.started=time.monotonic()
        self.created=time.time()
        self.counts={'model_calls':0,'tool_calls':0,'model_switches':0}
        self.model_identity=None
        self.events=[]
        self.on_change=None

    def checkpoint(self):
        if self.job is not None and self.job.cancel.is_set():
            raise WorkbenchError('cancelled','Task stopped by the user')
        if time.monotonic()-self.started>=self.limits.seconds:
            raise WorkbenchError('supervisor_budget','Task supervisor time budget exhausted')

    def consume(self,kind,identity=None):
        self.checkpoint()
        aliases={'model':'model_calls','tool':'tool_calls','switch':'model_switches'}
        key=aliases.get(kind,kind)
        if key not in self.counts: raise ValueError('Unknown supervisor budget kind')
        if key=='model_switches' and identity is not None and identity==self.model_identity:
            return
        if self.counts[key]>=getattr(self.limits,key):
            raise WorkbenchError('supervisor_budget','Task supervisor '+key.replace('_',' ')+' budget exhausted')
        self.counts[key]+=1
        if key=='model_switches':self.model_identity=identity
        self.events.append({'operation':key,'count':self.counts[key],
                            'elapsed_seconds':round(time.monotonic()-self.started,3),
                            **({'model':identity} if key=='model_switches' else {})})
        self.events=self.events[-40:]
        if self.on_change:self.on_change(self)

    def snapshot(self,completion=None,error=None):
        return {'supervisor_id':self.id,'goal':self.goal,'context':self.context,
                'created_at':self.created,'elapsed_seconds':round(time.monotonic()-self.started,3),
                'limits':asdict(self.limits),'counts':dict(self.counts),
                'events':list(self.events),'completion':completion,'outcome':completion['state'] if completion else 'running',
                **({'error':{'code':getattr(error,'code','task_failed'),'message':str(error)}} if error else {})}


def consume(kind,identity=None):
    supervisor=CURRENT_SUPERVISOR.get()
    if supervisor is not None:supervisor.consume(kind,identity)


def checkpoint():
    supervisor=CURRENT_SUPERVISOR.get()
    if supervisor is not None:supervisor.checkpoint()


def _persist(owner,snapshot):
    directory=getattr(getattr(owner,'settings',None),'data_dir',None)
    if directory is None:return
    directory=Path(directory)/'supervision'
    directory.mkdir(parents=True,exist_ok=True)
    target=directory/(snapshot['supervisor_id']+'.json')
    temporary=directory/(uuid4().hex+'.tmp')
    try:
        temporary.write_text(json.dumps(snapshot,ensure_ascii=False,indent=2),encoding='utf-8')
        for attempt in range(5):
            try:os.replace(temporary,target);break
            except PermissionError:
                if attempt==4:raise
                time.sleep(.02*(attempt+1))
    finally:temporary.unlink(missing_ok=True)


def supervised_task(function):
    signature=inspect.signature(function)
    @wraps(function)
    def run(*args,**kwargs):
        if CURRENT_SUPERVISOR.get() is not None:
            checkpoint()
            return function(*args,**kwargs)
        bound=signature.bind(*args,**kwargs)
        bound.apply_defaults()
        arguments=bound.arguments
        owner=arguments.get('self')
        goal=next((arguments[name] for name in ('goal','question','instruction','expression','command')
                   if isinstance(arguments.get(name),str)), '')
        context={name:arguments[name] for name in ('workspace_id','document_ids','target','task_id','document_scope','image_path')
                 if name in arguments}
        if arguments.get('history'):
            context['reference_history']=[item[:1000] for item in arguments['history'][-16:] if isinstance(item,str)]
        context=json.loads(json.dumps(context,default=str))
        limits=getattr(owner,'supervisor_limits',None) or SupervisorLimits()
        if isinstance(limits,dict):limits=SupervisorLimits(**limits)
        if not isinstance(limits,SupervisorLimits):raise ValueError('Invalid supervisor limits')
        supervisor=TaskSupervisor(goal,context,limits,arguments.get('job'))
        supervisor.on_change=lambda current:_persist(owner,current.snapshot())
        token=CURRENT_SUPERVISOR.set(supervisor)
        try:
            supervisor.checkpoint()
            _persist(owner,supervisor.snapshot())
            result=function(*args,**kwargs)
            supervisor.checkpoint()
            completion=observe_completion(result,function.__name__)
            snapshot=supervisor.snapshot(completion)
            _persist(owner,snapshot)
            if isinstance(result,dict):result={**result,'completion':completion,'supervisor':snapshot}
            return result
        except Exception as error:
            completion={'state':'cancelled' if getattr(error,'code',None)=='cancelled' else
                        'needs_input' if getattr(error,'code',None)=='needs_input' else 'failed',
                        'achieved':False,'response_delivered':False,'checks':{},'limitations':[str(error)]}
            # Persistence failure must not conceal the original workflow error.
            try:_persist(owner,supervisor.snapshot(completion,error))
            except OSError:pass
            raise
        finally:CURRENT_SUPERVISOR.reset(token)
    return run
