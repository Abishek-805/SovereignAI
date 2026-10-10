"""Task-local RAG affinity; runtime verification remains at the shared call boundary."""
from contextvars import ContextVar
from functools import wraps
from inspect import signature
import re

ACTIVE_RAG=ContextVar('sovereign_rag_worker',default=None)


def rag_workflow(function):
    parameters=signature(function)
    @wraps(function)
    def call(self,*args,**kwargs):
        values=parameters.bind(self,*args,**kwargs).arguments
        question=values.get('question',values.get('request',''))
        if not isinstance(question,str) or not question.strip():return function(self,*args,**kwargs)
        from router.request_normalization import is_greeting,worker_role
        documents=values.get('documents')
        ids=values.get('document_ids')
        requested=bool(values.get('force_documents') or values.get('report_generation') or documents or ids)
        if function.__name__=='ask' and ids is None:
            from rag.retrieve import document_scope_for_question
            requested=requested or bool(re.search(r'\b(?:documents?|files?|spreadsheet|workbook|uploaded|knowledge|sources?|marks|scores|cohort)\b|\b24[a-z]{3}\d{3}\b',question,re.I)) or document_scope_for_question(self.documents(),question,None) is not None
        if not requested or is_greeting(question) or function.__name__=='_request_plan' and worker_role(question,documents=bool(documents))=='code':
            return function(self,*args,**kwargs)
        if ACTIVE_RAG.get() is not None:return function(self,*args,**kwargs)
        state={'workbench':self,'stage':function.__name__,'loaded':False}
        token=ACTIVE_RAG.set(state)
        try:return function(self,*args,**kwargs)
        finally:ACTIVE_RAG.reset(token)

    return call


def rag_stage(function):
    @wraps(function)
    def call(*args,**kwargs):
        state=ACTIVE_RAG.get()
        if state is None:return function(*args,**kwargs)
        previous=state['stage'];state['stage']=function.__name__
        try:return function(*args,**kwargs)
        finally:state['stage']=previous
    return call
