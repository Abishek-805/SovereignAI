"""Immutable, bounded views of existing supervisor state; no execution authority.

Requests are exact controlling text. Other fields are untrusted public reference
metadata. This module never persists, transitions, executes or infers success.
"""
from dataclasses import dataclass, fields
from enum import Enum
import math
from itertools import islice
from types import MappingProxyType
from collections.abc import Mapping

_PRIVATE={'reasoning','chain_of_thought','thoughts','private_reasoning','analysis','reasoning_content'}
_MAX_REQUEST=32768


def _freeze(value, budget=None, depth=0):
    budget=[12000] if budget is None else budget
    if depth>5 or budget[0]<=0:return None
    if isinstance(value,str):
        text=value[:min(2000,budget[0])]
        budget[0]-=len(text)
        return text
    if value is None or isinstance(value,bool):return value
    if isinstance(value,int):return value if value.bit_length()<=256 else None
    if isinstance(value,float):return value if math.isfinite(value) else None
    if isinstance(value,Mapping):
        output={}
        for key,item in islice(value.items(),32):
            if not isinstance(key,str) or key.casefold() in _PRIVATE:continue
            if budget[0]<=0:break
            safe_key=key[:80]
            budget[0]-=len(safe_key)
            output[safe_key]=_freeze(item,budget,depth+1)
        return MappingProxyType(output)
    if isinstance(value,(list,tuple)):
        output=[]
        for item in value[:32]:
            if budget[0]<=0:break
            output.append(_freeze(item,budget,depth+1))
        return tuple(output)
    return None


def _thaw(value):
    if isinstance(value,Mapping):return {key:_thaw(item) for key,item in value.items()}
    if isinstance(value,tuple):return [_thaw(item) for item in value]
    if isinstance(value,Enum):return value.value
    return value


def _request(value,name):
    if not isinstance(value,str) or len(value)>_MAX_REQUEST:
        raise ValueError(name+' must be exact text within the request budget')
    return value


def _label(value):
    if value is None:return None
    if not isinstance(value,str) or len(value)>1024:raise ValueError('Invalid identity or scope label')
    return value


class _Export:
    def to_dict(self):return {field.name:_thaw(getattr(self,field.name)) for field in fields(self)}


@dataclass(frozen=True)
class CodeTaskContext(_Export):
    original_request: str
    resolved_request: str
    workspace: str | None = None
    target: str | None = None
    active_file: str | None = None
    relevant_symbols: tuple = ()
    related_files: tuple = ()
    diagnostics: tuple = ()
    current_changes: tuple = ()
    previous_tool_result: object = None
    current_model: str | None = None
    task_stage: str | None = None
    context_scope: object = None

    def __post_init__(self):
        _request(self.original_request,'original_request')
        _request(self.resolved_request,'resolved_request')
        for name in ('workspace','target','active_file','current_model','task_stage'):_label(getattr(self,name))
        budget=[12000]
        for name in ('relevant_symbols','related_files','diagnostics','current_changes'):
            value=getattr(self,name)
            if not isinstance(value,(list,tuple)):raise ValueError(name+' must be a sequence')
            object.__setattr__(self,name,_freeze(value,budget) or ())
        for name in ('previous_tool_result','context_scope'):
            object.__setattr__(self,name,_freeze(getattr(self,name),budget))

    @classmethod
    def from_mapping(cls,value):
        if not isinstance(value,Mapping):raise ValueError('Task context must be an object')
        original=value.get('original_request','')
        return cls(original,value.get('resolved_request',original),
            workspace=value.get('workspace',value.get('workspace_id')),target=value.get('target'),
            active_file=value.get('active_file',value.get('target')),
            relevant_symbols=value.get('relevant_symbols',()),related_files=value.get('related_files',()),
            diagnostics=value.get('diagnostics',()),current_changes=value.get('current_changes',()),
            previous_tool_result=value.get('previous_tool_result'),current_model=value.get('current_model'),
            task_stage=value.get('task_stage'),context_scope=value.get('context_scope'))


class ObservationKind(str,Enum):
    TOOL='tool'
    SANDBOX='sandbox'
    TEST='test'
    MODEL='model'
    VALIDATION='validation'
    RESOURCE='resource'


@dataclass(frozen=True)
class CodeObservation(_Export):
    kind: ObservationKind
    identity: str | None = None
    timestamp: float | None = None
    executed: bool | None = None
    exit_code: int | None = None
    stdout: str = ''
    stderr: str = ''
    error_category: str | None = None
    result: object = None

    def __post_init__(self):
        object.__setattr__(self,'kind',ObservationKind(self.kind))
        _label(self.identity)
        _label(self.error_category)
        if self.timestamp is not None and (isinstance(self.timestamp,bool) or not isinstance(self.timestamp,(int,float)) or not math.isfinite(self.timestamp)):
            raise ValueError('Invalid observation timestamp')
        if self.executed is not None and not isinstance(self.executed,bool):raise ValueError('Execution evidence must be boolean or unknown')
        if self.exit_code is not None and (isinstance(self.exit_code,bool) or not isinstance(self.exit_code,int)):raise ValueError('Exit evidence must be integer or unknown')
        for name in ('stdout','stderr'):
            value=getattr(self,name)
            if not isinstance(value,str):raise ValueError(name+' must be text')
            object.__setattr__(self,name,value[:3000])
        object.__setattr__(self,'result',_freeze(self.result))

    @classmethod
    def from_result(cls,kind,result,*,identity=None,timestamp=None,error_category=None):
        if not isinstance(result,Mapping):raise ValueError('Observed result must be an object')
        return cls(kind,identity,timestamp,result.get('executed'),result.get('exit_code'),
                   result.get('stdout',''),result.get('stderr',''),error_category,result)


@dataclass(frozen=True)
class CodeTaskView(_Export):
    task_id: str | None
    context: CodeTaskContext
    task_type: str | None
    complexity: str | None
    current_stage: str | None
    active_worker: str | None
    plan: object
    observations: object
    tool_results: object
    current_candidate: object
    candidate_hash: str | None
    repair_count: int
    model_switch_count: int
    completion_status: str | None
    cancellation: bool
    blocker: object
    timestamps: object

    def __post_init__(self):
        if not isinstance(self.context,CodeTaskContext):raise ValueError('Expected immutable task context')
        for name in ('task_id','task_type','complexity','current_stage','active_worker','candidate_hash','completion_status'):_label(getattr(self,name))
        for name in ('repair_count','model_switch_count'):
            value=getattr(self,name)
            if isinstance(value,bool) or not isinstance(value,int) or value<0:raise ValueError('Invalid observed count')
        if not isinstance(self.cancellation,bool):raise ValueError('Invalid observed cancellation')
        budget=[12000]
        for name in ('plan','observations','tool_results','current_candidate','blocker','timestamps'):
            object.__setattr__(self,name,_freeze(getattr(self,name),budget))

    def to_dict(self):
        result=super().to_dict()
        result['context']=self.context.to_dict()
        return result

    @classmethod
    def from_snapshot(cls,snapshot):
        if not isinstance(snapshot,Mapping):raise ValueError('Supervisor snapshot must be an object')
        state=snapshot.get('task_state',{})
        scope=snapshot.get('context',{})
        counts=snapshot.get('counts',{})
        if not all(isinstance(item,Mapping) for item in (state,scope,counts)):raise ValueError('Invalid supervisor snapshot')
        original=state.get('original_request',snapshot.get('goal',''))
        context=CodeTaskContext.from_mapping({**scope,'original_request':original,
            'resolved_request':state.get('resolved_original_request',original),
            'workspace':state.get('workspace',scope.get('workspace_id')),
            'target':state.get('target',scope.get('target')),
            'current_model':state.get('active_worker'),'task_stage':state.get('current_stage'),
            **{name:state[name] for name in ('active_file','relevant_symbols','related_files','diagnostics','current_changes','previous_tool_result') if name in state},
            'context_scope':state.get('context_scope',scope.get('document_ids'))})
        return cls(state.get('task_id',snapshot.get('supervisor_id')),context,
            state.get('task_type'),state.get('complexity'),state.get('current_stage'),state.get('active_worker'),
            state.get('plan'),state.get('observations',()),state.get('tool_results',()),
            state.get('current_candidate'),state.get('candidate_hash'),state.get('repair_count',0),
            state.get('model_switch_count',counts.get('model_switches',0)),state.get('completion_status'),
            state.get('cancellation_state',False),state.get('blockers',()),state.get('timestamps',{}))
