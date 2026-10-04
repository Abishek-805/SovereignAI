"""Bounded application-owned skills; never load instructions from user documents."""
from contextvars import ContextVar
from contextlib import contextmanager
from functools import wraps
from pathlib import Path
import hashlib

ROOT=Path(__file__).resolve().parents[1]/'skills'/'runtime'
COMPOSITIONS={
    'task-core':('chat',), 'chat':('chat',), 'rag':('rag',),
    'documents':('documents','artifacts'), 'spreadsheets':('spreadsheets',),
    'coding':('coding','project-runner','workspace'),
    'application-operations':('workspace','project-runner','documents','artifacts'),
    'structured-data':('spreadsheets',), 'project-runner':('project-runner',),
    'artifacts':('artifacts',), 'workspace':('workspace',)}
PROFILES=frozenset(COMPOSITIONS)
ACTIVE=ContextVar('sovereign_task_skill',default=None)
MAX_CHARS=6500

@contextmanager
def skill_scope(profile):
    if profile not in PROFILES:raise ValueError('Unknown application skill')
    token=ACTIVE.set(profile)
    try:yield
    finally:ACTIVE.reset(token)

def task_skill(profile):
    def decorate(function):
        @wraps(function)
        def invoke(self,*args,**kwargs):
            # Keep document creation in its parent profile when it delegates
            # to the generic code-shaped output decoder.
            selected=ACTIVE.get() if function.__name__=='complete_code' and ACTIVE.get() else profile
            with skill_scope(selected):return function(self,*args,**kwargs)
        return invoke
    return decorate

def inject(messages,enabled):
    profile=ACTIVE.get()
    if not enabled or profile is None:return list(messages),[]
    names=['task-core',*COMPOSITIONS[profile]]
    texts=[];metadata=[]
    for name in names:
        path=ROOT/name/'SKILL.md'
        if path.is_symlink() or not path.resolve().is_relative_to(ROOT.resolve()):
            raise ValueError('Application skill path is not trusted')
        text=path.read_text(encoding='utf-8')
        if len(text)>MAX_CHARS:raise ValueError('Application skill exceeds context budget')
        body=text.split('---',2)[-1].strip()
        texts.append(body)
        metadata.append({'name':name,'sha256':hashlib.sha256(text.encode()).hexdigest(),'characters':len(body)})
    content='\n\n'.join(texts)
    if len(content)>MAX_CHARS:raise ValueError('Selected skills exceed context budget')
    marker='APPLICATION TASK SKILLS (trusted runtime instructions):\n'
    result=[dict(message) for message in messages]
    if any(marker in message.get('content','') for message in result if message.get('role')=='system' and isinstance(message.get('content'),str)):
        return result,metadata
    for index,message in enumerate(result):
        if message.get('role')=='system' and isinstance(message.get('content'),str):
            result[index]={**message,'content':message['content']+'\n\n'+marker+content}
            break
    else:result.insert(0,{'role':'system','content':marker+content})
    return result,metadata
