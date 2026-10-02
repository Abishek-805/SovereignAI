"""Cheap advisory coding classification; never grants tools or file authority."""
from dataclasses import asdict, dataclass, field
import re
from router.request_normalization import normalize_request, prose_request

@dataclass(frozen=True)
class CodingRequestContext:
    mode: str = 'chat'
    active_file: str | None = None
    workspace_available: bool = False
    repository_scope: str = 'none'
    requested_files: tuple = ()
    estimated_context_size: int | None = None
    visual_input_present: bool = False
    previous_task_type: str | None = None
    previous_worker_role: str | None = None
    previous_validation_failed: bool = False

@dataclass(frozen=True)
class CodingRouteDecision:
    original_request: str
    normalized_request: str
    task_type: str
    complexity: str
    worker_role: str | None
    steps: tuple
    features: dict = field(default_factory=dict)
    reason_codes: tuple = ()
    needs_clarification: bool = False
    mutation_authorized: bool = False

    def to_dict(self):return asdict(self)

def classify_coding_request(request, context=None):
    context=asdict(context) if isinstance(context,CodingRequestContext) else dict(context or {})
    normalized=normalize_request(request if isinstance(request,str) else '')
    text=prose_request(normalized.normalized).lower()
    text=re.sub(r"\b(?:do not|don't|never|without)\b[^.;\n]*",' ',text)
    files=context.get('requested_files') or ()
    visual=bool(context.get('visual_input_present') or context.get('image'))
    followup=bool(re.fullmatch(r'\s*(?:fix that|fix it|make it work|continue|now make the tests pass)[.!?\s]*',text))
    multi=len(files)>1 or bool(re.search(r'\b(?:across|throughout)\b.*\b(?:project|repository|modules|files)\b|\bmulti[- ]file\b',text))
    features={'active_file_present':bool(context.get('active_file')),
        'workspace_available':bool(context.get('workspace_available') or context.get('workspace')),
        'repository_scope':context.get('repository_scope','none'),
        'estimated_context_size':context.get('estimated_context_size'),
        'number_of_files_requested':len(files),'visual_input_present':visual,
        'modality':'image' if visual else 'text','is_follow_up':followup,
        'explicit_error_present':bool(re.search(r'\b(?:error|exception|traceback|failed|failure)\b',text)),
        'language_hints':tuple(re.findall(r'\b(?:python|javascript|typescript|rust|java|html|css|sql|py)\b',text)),
        'execution_requested':bool(re.search(r'\b(?:run|execute)\b',text)),
        'validation_required':bool(re.search(r'\b(?:test|tests|validate|verify)\b',text))}
    task=None
    if followup:
        task=context.get('previous_task_type')
        if task and context.get('previous_validation_failed'):task='REPAIR'
    else:
        families=(('EXPLAIN',r'\b(?:explain|describe|understand|what is|why does|how does)\b'),
            ('AUTOCOMPLETE',r'\b(?:autocomplete|complete)\b.*\b(?:line|code|function)\b'),
            ('TEST',r'\b(?:tests|test cases|unit test)\b'),('REVIEW',r'\b(?:review|audit)\b'),
            ('REFACTOR',r'\brefactor\b'),('DEBUG',r'\b(?:debug|fix|diagnose|troubleshoot)\b'),
            ('REPAIR',r'\brepair\b'),('EDIT',r'\b(?:rename|edit|modify|change|update|replace)\b'),
            ('IMPLEMENT',r'\b(?:implement|add|build)\b'),('CODE_GENERATION',r'\b(?:write|create|generate)\b'))
        task=next((name for name,pattern in families if re.search(pattern,text)),None)
        if task in {'EXPLAIN','REVIEW'}:
            from router.tool_registry import explicit_operation_requested
            # A separate imperative clause changes the requested deliverable;
            # mentioning an edit inside an explanation does not.
            edit_clause=re.search(r'\b(?:and|then)\s+(?:then\s+)?(?:please\s+)?(?:rename|edit|modify|change|update|replace|refactor|debug|fix|diagnose|repair|implement|add|build|write|create|generate)\b',text)
            if edit_clause and explicit_operation_requested(request,'file_edit'):
                task=next((name for name,pattern in families if name not in {'EXPLAIN','REVIEW'} and re.search(pattern,text[edit_clause.start():])),task)
    coding=bool(features['active_file_present'] or features['workspace_available'] or features['language_hints']
        or re.search(r'\b(?:code|function|variable|class|script|program|api|endpoint|syntax|debug|refactor|tests)\b',text)
        or (followup and task))
    if task and task!='EXPLAIN' and not coding and not visual:task=None
    if visual:task='VISION_ASSISTED_CODE' if task and task!='EXPLAIN' else 'VISION_ASSISTED_CODE'
    if multi and not visual and task not in {None,'EXPLAIN','REVIEW'}:task='MULTI_FILE_CHANGE'
    complex_task=bool(multi or re.search(r'\b(?:architecture|architectural|migration|redesign|distributed)\b',text)
        or (context.get('estimated_context_size') or 0)>12000)
    complexity='complex' if complex_task else 'simple'
    if task is None:
        if text.strip() and not followup and not coding and not re.search(r'\b(?:that|this|it|screenshot)\b',text):
            task='CHAT';steps=('lightweight',)
        else:task='CLARIFICATION';steps=()
    elif visual:
        from router.tool_registry import explicit_operation_requested
        steps=('vision','code') if explicit_operation_requested(request,'file_edit') else ('vision',)
    elif task in {'EXPLAIN','CHAT'}:steps=('reasoning',) if complex_task else ('lightweight',)
    else:steps=('reasoning','code') if complex_task else ('code',)
    return CodingRouteDecision(normalized.original,normalized.normalized,task,complexity,
        steps[0] if steps else None,steps,features,('ambiguous_request',) if not steps else ('software_task_features',),not steps)
