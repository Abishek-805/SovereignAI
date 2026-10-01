"""Request-owned routing facts. Unknown measurements remain None."""
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field
from time import perf_counter
from uuid import uuid4
from functools import wraps
from math import isfinite

CURRENT_ROUTE = ContextVar('sovereign_route', default=None)


@dataclass
class RoutingDecision:
    request_id: str = field(default_factory=lambda: uuid4().hex)
    intent: str | None = None
    capability: str | None = None
    modality: str | None = None
    candidate_models: list = field(default_factory=list)
    candidate_rejection_reasons: dict = field(default_factory=dict)
    selected_model: str | None = None
    runtime_alias: str | None = None
    route_reason: str | None = None
    required_context: int | None = None
    available_context: int | None = None
    required_context_scope: dict | None = None
    available_context_scope: dict | None = None
    resource_admission: dict | None = None
    current_residency: str | None = None
    switch_required: bool | None = None
    classifier_time: float | None = None
    routing_time: float | None = None
    model_load_time: float | None = None
    inference_time: float | None = None
    validation_time: float | None = None
    fallback: dict | None = None
    errors: list = field(default_factory=list)
    classification: dict | None = None
    stages: list = field(default_factory=list)
    model_request_time: float | None = None
    lease_time: float | None = None
    total_time: float | None = None
    evidence_required: bool | None = None
    evidence_used: bool | None = None
    knowledge_scope: dict | None = None
    retrieval: dict | None = None
    tool_candidates: list = field(default_factory=list)
    failure_layer: str | None = None
    validation: dict | None = None
    events: list = field(default_factory=list)
    selection_policy: str | None = None
    selection_evidence: dict | None = None
    workflow: str | None = None
    worker_role: str | None = None
    is_warm: bool | None = None
    current_stage: str | None = None
    completion_status: str | None = None
    selected_tool: str | None = None
    candidate_rejection_codes: dict = field(default_factory=dict)
    prefill_time: float | None = None
    generation_time: float | None = None
    retrieval_time: float | None = None
    _started: float = field(default_factory=perf_counter, repr=False)
    _context_admit: object = field(default=None, repr=False)

    def snapshot(self):
        result = asdict(self)
        result.pop('_started')
        result.pop('_context_admit')
        result['timings'] = {name: None if value is None else value * 1000 for name, value in {
            'classification_ms': self.classifier_time, 'routing_ms': self.routing_time,
            'retrieval_ms': self.retrieval_time, 'load_ms': self.model_load_time,
            'switch_ms': None, 'prefill_ms': self.prefill_time,
            'generation_ms': self.generation_time, 'validation_ms': self.validation_time,
            'total_ms': self.total_time}.items()}
        return result

    def event(self, name):
        self.events.append({'event': name, 'elapsed_ms': (perf_counter()-self._started)*1000})
        from backend.task_supervisor import operational_event, CURRENT_SUPERVISOR
        # Error reporting must never re-enter admission and mask cancellation,
        # timeout or budget errors. The outer supervisor records terminal state.
        if name not in {'REQUEST_CANCELLED','REQUEST_FAILED','REQUEST_COMPLETED'}:
            operational_event(name,intent=self.intent,workflow=self.workflow,selected_model=self.selected_model,
                              selected_tool=self.selected_tool)
        supervisor=CURRENT_SUPERVISOR.get()
        if supervisor is not None:
            self.current_stage=supervisor.task_state['current_stage']
            self.workflow=supervisor.task_state['workflow']
            self.worker_role=supervisor.worker_role
            self.selected_tool=supervisor.task_state['current_action']

    def add_time(self, field_name, seconds):
        if not isinstance(seconds, bool) and isinstance(seconds, (float, int)) and isfinite(seconds) and seconds >= 0:
            setattr(self, field_name, (getattr(self, field_name) or 0) + seconds)

    def selection(self, data):
        self.stages.append({'stage': 'model_selection', **data})
        self.event('MODEL_SELECTION_COMPLETED')
        for key in ('capability', 'modality', 'candidate_models', 'candidate_rejection_reasons',
                    'selected_model', 'route_reason', 'required_context', 'available_context',
                    'resource_admission', 'current_residency', 'switch_required', 'fallback',
                    'selection_policy', 'selection_evidence', 'candidate_rejection_codes','worker_role','is_warm'):
            if key in data:
                setattr(self, key, self.switch_required is True or data[key] if key=='switch_required' else data[key])
        self.add_time('routing_time', data.get('routing_time'))


def runtime_inference_seconds(timings):
    if not isinstance(timings, dict):
        return None
    if all(not isinstance(timings.get(key), bool) and isinstance(timings.get(key), (int, float)) and isfinite(timings[key]) and timings[key]>=0 for key in ('prompt_ms', 'predicted_ms')):
        seconds=(timings['prompt_ms']+timings['predicted_ms'])/1000
        return seconds if isfinite(seconds) else None
    return None


def observe_completion(response, wall_seconds):
    trace = CURRENT_ROUTE.get()
    if trace is None:
        return
    trace.add_time('model_request_time', wall_seconds)
    timings = response.get('timings', {}) if isinstance(response, dict) else {}
    trace.add_time('inference_time', runtime_inference_seconds(timings))
    for source, target in (('prompt_ms','prefill_time'),('predicted_ms','generation_time')):
        value=timings.get(source)
        if isinstance(value,(int,float)) and not isinstance(value,bool) and isfinite(value) and value>=0:
            trace.add_time(target,value/1000)
    usage = response.get('usage', {}) if isinstance(response, dict) else {}
    prompt = usage.get('prompt_tokens')
    if isinstance(prompt, int):
        trace.stages.append({'stage': 'inference', 'prompt_tokens': prompt,
                             'completion_tokens': usage.get('completion_tokens'),
                             'model_request_time': wall_seconds, 'runtime_timings': timings or None})


def measured_validation(function):
    @wraps(function)
    def run(*args, **kwargs):
        started=perf_counter()
        succeeded=False
        try:
            result=function(*args, **kwargs)
            succeeded=True
            return result
        finally:
            trace=CURRENT_ROUTE.get()
            if trace:
                elapsed=perf_counter()-started
                trace.add_time('validation_time',elapsed)
                trace.stages.append({'stage':'validation','validator':function.__name__,'wall_seconds':elapsed})
                checks=dict((trace.validation or {}).get('checks',{}))
                checks[function.__name__]=succeeded
                trace.validation={'status':'passed' if all(checks.values()) else 'failed','checks':checks}
                trace.event('VALIDATION_COMPLETED' if succeeded else 'VALIDATION_FAILED')
    return run
