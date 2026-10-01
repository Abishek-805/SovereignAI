"""One bounded observation envelope shared by nested task workflows."""
from contextvars import ContextVar
from dataclasses import asdict, dataclass
from functools import wraps
import inspect
import json
import os
import re
from pathlib import Path
import time
from uuid import uuid4

from backend.contracts import WorkbenchError
from router.task_completion import observe_completion

CURRENT_SUPERVISOR=ContextVar('task_supervisor',default=None)

STAGES={'RECEIVED','NORMALIZING','UNDERSTANDING','PLANNING','ROUTING',
        'WAITING_FOR_RESOURCE','EXECUTING','OBSERVING','VERIFYING','REPAIRING',
        'REPLANNING','WAITING_FOR_USER','READY_FOR_REVIEW','COMPLETED','FAILED','CANCELLED','UNVERIFIED'}
TERMINAL_STAGES={'WAITING_FOR_USER','READY_FOR_REVIEW','COMPLETED','FAILED','CANCELLED','UNVERIFIED'}
# Workflows can alternate planning/routing/execution as tools provide evidence.
# Receiving/normalization cannot restart a running task and terminal stages stop it.
ACTIVE_STAGES=STAGES-TERMINAL_STAGES
STAGE_TRANSITIONS={stage:(ACTIVE_STAGES-{'RECEIVED','NORMALIZING'})|TERMINAL_STAGES
                   for stage in ACTIVE_STAGES}
STAGE_TRANSITIONS['RECEIVED']|={'NORMALIZING'}
STAGE_TRANSITIONS['NORMALIZING']|={'NORMALIZING'}
STAGE_TRANSITIONS.update({stage:set() for stage in TERMINAL_STAGES})
EVENT_STAGES={'REQUEST_NORMALIZED':'NORMALIZING','CAPABILITY_CLASSIFIED':'UNDERSTANDING',
              'PLAN_CREATED':'PLANNING','TOOL_SELECTED':'ROUTING','MODEL_CANDIDATES_FILTERED':'ROUTING',
              'MODEL_SELECTED':'ROUTING','MODEL_LOADING':'WAITING_FOR_RESOURCE',
              'RESOURCE_ADMITTED':'WAITING_FOR_RESOURCE','MODEL_READY':'EXECUTING',
              'GENERATION_STARTED':'EXECUTING','TOOL_STARTED':'EXECUTING',
              'RETRIEVAL_STARTED':'EXECUTING','RETRIEVAL_COMPLETED':'OBSERVING',
              'TOOL_COMPLETED':'OBSERVING','GENERATION_COMPLETED':'OBSERVING',
              'VALIDATION_STARTED':'VERIFYING','VALIDATION_COMPLETED':'VERIFYING',
              'REPAIR_STARTED':'REPAIRING','REPLAN_STARTED':'REPLANNING'}


def _operational_value(value,depth=0):
    """Bound public operational records and omit private reasoning fields."""
    if depth>5:return None
    if isinstance(value,str):return value[:2000]
    if value is None or isinstance(value,(bool,int,float)):return value
    if isinstance(value,(list,tuple)):
        return [_operational_value(item,depth+1) for item in value[:32]]
    if isinstance(value,dict):
        return {str(key)[:80]:_operational_value(item,depth+1) for key,item in list(value.items())[:40]
                if str(key).casefold() not in {'reasoning','chain_of_thought','thoughts','private_reasoning','analysis','reasoning_content'}}
    return str(value)[:2000]


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
        self.worker_role=None
        self.events=[]
        self.on_change=None
        self.event_count=0
        self.task_state={'task_id':self.id,'original_request':goal,'normalized_request':goal,
            'conversation_context':self.context.get('reference_history',[]),
            'follow_up_context':None,'intent':None,'workflow':None,'modality':None,
            'workspace':self.context.get('workspace_id'),'knowledge_scope':self.context.get('document_ids'),
            'requested_deliverables':[],'success_conditions':[],'current_stage':'RECEIVED',
            'current_action':None,'active_worker':None,'plan':None,'observations':[],
            'tool_results':[],'evidence':[],'repair_count':0,'replan_count':0,
            'completion_status':'running','blockers':[],'cancellation_state':False,
            'timestamps':{'received':self.created,'updated':self.created}}

    def record_event(self,name,details=None,**metadata):
        self.checkpoint()
        if not isinstance(name,str) or not re.fullmatch(r'[A-Z][A-Z0-9_]{0,63}',name):
            raise ValueError('Operational event names must be canonical uppercase identifiers')
        if self.task_state['current_stage'] in TERMINAL_STAGES:
            raise WorkbenchError('invalid_state','The supervised task has already stopped')
        if self.event_count>=512:
            raise WorkbenchError('supervisor_budget','Task operational event budget exhausted')
        if details is not None and not isinstance(details,dict):raise ValueError('Operational event details must be an object')
        data=_operational_value({**(details or {}),**metadata})
        if not isinstance(data,dict):raise ValueError('Operational event details must be an object')
        if data.get('tool') is not None and data.get('selected_tool') is None:data['selected_tool']=data['tool']
        stage=EVENT_STAGES.get(name,self.task_state['current_stage'])
        self._transition(stage)
        self.event_count+=1
        self.task_state['timestamps']['updated']=time.time()
        for field in ('normalized_request','intent','workflow','modality','follow_up_context',
                      'requested_deliverables','success_conditions','plan','current_action',
                      'blockers','retrieval_strategy','validation','route_reason','resource_admission'):
            if data.get(field) is not None:self.task_state[field]=data[field]
        if data.get('selected_model') is not None:self.task_state['active_worker']=data['selected_model']
        if data.get('worker_role') is not None:self.worker_role=data['worker_role']
        if data.get('selected_tool') is not None:self.task_state['current_action']=data['selected_tool']
        for field in ('observations','tool_results','evidence'):
            if field in data:
                items=data[field] if isinstance(data[field],list) else [data[field]]
                self.task_state[field]=(self.task_state[field]+items)[-32:]
        if name=='REPAIR_STARTED':self.task_state['repair_count']+=1
        if name=='REPLAN_STARTED':self.task_state['replan_count']+=1
        self.events.append({'event':name,'stage':stage,'at':time.time(),'details':data})
        self.events=self.events[-40:]
        if self.on_change:self.on_change(self)

    def _transition(self,stage):
        current=self.task_state['current_stage']
        if stage not in STAGES or stage!=current and stage not in STAGE_TRANSITIONS[current]:
            raise WorkbenchError('invalid_state','Cannot move supervised task from '+current+' to '+str(stage))
        self.task_state['current_stage']=stage

    def finish(self,completion,error=None):
        outcome=completion['state']
        stage={'completed':'COMPLETED','awaiting_review':'READY_FOR_REVIEW',
               'needs_input':'WAITING_FOR_USER','cancelled':'CANCELLED','failed':'FAILED'}.get(outcome,'UNVERIFIED')
        self._transition(stage)
        self.task_state['completion_status']=outcome
        self.task_state['cancellation_state']=stage=='CANCELLED'
        self.task_state['timestamps'].update(updated=time.time(),finished=time.time())
        self.task_state['observations']=(self.task_state['observations']+[{'completion_checks':completion.get('checks',{})}])[-32:]
        self.task_state['blockers']=completion.get('limitations',[])[:32] if outcome!='completed' else []
        if error:self.task_state['blockers']=[{'code':getattr(error,'code','task_failed'),'message':str(error)[:2000]}]
        event='REQUEST_CANCELLED' if stage=='CANCELLED' else 'REQUEST_FAILED' if stage=='FAILED' else 'REQUEST_COMPLETED'
        self.events.append({'event':event,'stage':stage,'at':time.time(),'completion_status':outcome})
        self.events=self.events[-40:]

    def checkpoint(self):
        cancellation=getattr(self.job,'cancel',None)
        if cancellation is not None and cancellation.is_set():
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
        if key=='model_switches':self.task_state['active_worker']=identity
        self.events.append({'operation':key,'count':self.counts[key],
                            'elapsed_seconds':round(time.monotonic()-self.started,3),
                            **({'model':identity} if key=='model_switches' else {})})
        self.events=self.events[-40:]
        if self.on_change:self.on_change(self)

    def snapshot(self,completion=None,error=None):
        return {'supervisor_id':self.id,'goal':self.goal,'context':self.context,
                'created_at':self.created,'elapsed_seconds':round(time.monotonic()-self.started,3),
                'limits':asdict(self.limits),'counts':dict(self.counts),
                'task_state':{**json.loads(json.dumps(self.task_state)),
                    'worker_role':self.worker_role,
                    'model_switch_count':self.counts['model_switches'],'tool_call_count':self.counts['tool_calls'],
                    'inference_call_count':self.counts['model_calls'],'event_count':self.event_count},
                'events':list(self.events),'completion':completion,'outcome':completion['state'] if completion else 'running',
                **({'error':{'code':getattr(error,'code','task_failed'),'message':str(error)}} if error else {})}


def consume(kind,identity=None):
    supervisor=CURRENT_SUPERVISOR.get()
    if supervisor is not None:supervisor.consume(kind,identity)


def checkpoint():
    supervisor=CURRENT_SUPERVISOR.get()
    if supervisor is not None:supervisor.checkpoint()


def operational_event(name,**details):
    supervisor=CURRENT_SUPERVISOR.get()
    if supervisor is not None:supervisor.record_event(name,details)


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
        from router.request_normalization import normalize_request
        supervisor.task_state['normalized_request']=normalize_request(goal).normalized
        history=context.get('reference_history',[])
        follow_up=bool(re.fullmatch(r'\s*(?:fix that|continue|is (?:it|the task) done\??|make it work|use the other file|now show failures(?: instead)?)[.!?\s]*',goal,re.I))
        if follow_up:
            supervisor.task_state['follow_up_context']={'reference_history':history,'resolution':'conversation_context' if history else 'missing_context',
                                                      'workspace':context.get('workspace_id'),'knowledge_scope':context.get('document_ids')}
            # Link only a unique observed goal with identical supplied scope.
            # No workspace or document selection is inherited from another chat.
            directory=getattr(getattr(owner,'settings',None),'data_dir',None)
            previous_goals={re.sub(r'^user:\s*','',item,flags=re.I).strip() for item in history if re.match(r'user:',item,re.I)}
            matches=[]
            if directory and previous_goals:
                for path in list((Path(directory)/'supervision').glob('*.json'))[-128:]:
                    try:
                        previous=json.loads(path.read_text(encoding='utf-8'))
                        if not isinstance(previous,dict):continue
                        previous_id=previous.get('supervisor_id')
                        if not isinstance(previous_id,str) or not re.fullmatch(r'[a-f0-9]{32}',previous_id) or path.stem!=previous_id:continue
                        prior_context=previous.get('context',{})
                        if not isinstance(prior_context,dict) or not isinstance(previous.get('task_state',{}),dict):continue
                        if previous.get('goal') in previous_goals and all(prior_context.get(key)==context.get(key) for key in ('workspace_id','document_ids')):
                            matches.append(previous)
                    except (OSError,ValueError):continue
                if len(matches)==1:
                    previous=matches[0]
                    supervisor.task_state['follow_up_context'].update(previous_task_id=previous['supervisor_id'],
                        previous_completion=previous.get('completion'),previous_operational_state={key:value for key,value in (previous.get('task_state') or {}).items() if key!='follow_up_context'})
        supervisor.on_change=lambda current:_persist(owner,current.snapshot())
        token=CURRENT_SUPERVISOR.set(supervisor)
        try:
            supervisor.checkpoint()
            _persist(owner,supervisor.snapshot())
            supervisor.record_event('REQUEST_NORMALIZED',normalized_request=supervisor.task_state['normalized_request'])
            if follow_up and not history:
                raise WorkbenchError('needs_input','Tell me which task or result this follow-up refers to')
            result=function(*args,**kwargs)
            supervisor.checkpoint()
            completion=observe_completion(result,function.__name__)
            supervisor.finish(completion)
            snapshot=supervisor.snapshot(completion)
            _persist(owner,snapshot)
            if isinstance(result,dict):
                result={**result,'completion':completion,'supervisor':snapshot}
                decision=(result.get('routing') or {}).get('decision')
                if isinstance(decision,dict):
                    decision.update(current_stage=snapshot['task_state']['current_stage'],completion_status=completion['state'],workflow=supervisor.task_state['workflow'])
                    if callable(getattr(owner,'remember_route',None)):owner.remember_route(decision)
                    if supervisor.job is not None:
                        from contextlib import nullcontext
                        lock=getattr(supervisor.job,'lock',None)
                        with lock if lock is not None else nullcontext():supervisor.job.routing={'decision':decision}
            return result
        except Exception as error:
            completion={'state':'cancelled' if getattr(error,'code',None)=='cancelled' else
                        'needs_input' if getattr(error,'code',None)=='needs_input' else 'failed',
                        'achieved':False,'response_delivered':False,'checks':{},'limitations':[str(error)]}
            # Persistence failure must not conceal the original workflow error.
            if supervisor.task_state['current_stage'] not in TERMINAL_STAGES:
                supervisor.finish(completion,error)
            try:_persist(owner,supervisor.snapshot(completion,error))
            except OSError:pass
            raise
        finally:CURRENT_SUPERVISOR.reset(token)
    return run
