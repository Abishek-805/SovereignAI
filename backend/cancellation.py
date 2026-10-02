"""Request-local cancellation checkpoints without cancelling other conversations."""
from contextlib import nullcontext
from functools import wraps
from inspect import signature, getattr_static
from time import perf_counter
from router.telemetry import CURRENT_ROUTE, RoutingDecision


def cancellable_model_job(method):
    contract=signature(method)
    @wraps(method)
    def run(self,*args,**kwargs):
        bound=contract.bind(self,*args,**kwargs)
        bound.apply_defaults()
        arguments=bound.arguments
        job=arguments.get('job')
        scope=getattr(self.model,'cancel_scope',None)
        # Optional instrumentation must not invoke dynamic inference proxies.
        preview_scope=getattr(self.model,'job_scope',None) if getattr_static(self.model,'job_scope',None) is not None else None
        parent=CURRENT_ROUTE.get()
        trace=parent or RoutingDecision()
        token=CURRENT_ROUTE.set(trace)
        if parent is None:
            started=perf_counter()
            ids=arguments.get('document_ids') if 'document_ids' in arguments else []
            trace.knowledge_scope={'connected':ids != [], 'mode':'off' if ids == [] else 'legacy' if ids is None else 'selected', 'permitted_document_count':None if ids is None else len(ids)}
            trace.event('REQUEST_RECEIVED')
            trace.classification={'method':'request_metadata','status':'abstained',
                                  'reason':'Semantic intent requires validated classification or the bounded planner',
                                  'image':bool(arguments.get('image_path') or method.__name__=='ask_vision'),
                                  'connected_documents':len(arguments.get('document_ids') or []),
                                  'workspace_selected':bool(arguments.get('workspace_id'))}
            classifier=getattr(self,'classifier',None)
            if classifier is not None:
                request=arguments.get('goal') or arguments.get('question') or arguments.get('instruction') or ''
                prediction=classifier.predict(request,{'documents':ids != [],'workspace':bool(arguments.get('workspace_id')), 'image':trace.classification['image'], 'mode':'chat' if method.__name__=='ask' else 'agent'})
                trace.classification=prediction.to_dict()
                trace.classifier_time=prediction.classifier_time_ms/1000
            else:
                trace.classifier_time=perf_counter()-started
            trace.event('CLASSIFICATION_COMPLETED')
        try:
            with scope(job.cancel) if job is not None and callable(scope) else nullcontext():
                with preview_scope(job) if job is not None and callable(preview_scope) else nullcontext():
                    result=method(self,*args,**kwargs)
            if parent is None and isinstance(result,dict):
                plan=result.get('plan') or {}
                trace.intent=plan.get('action') or trace.intent
                routing=result.setdefault('routing',{})
                trace.intent=trace.intent or ('answer' if result.get('status')=='conversation' else 'create_report' if result.get('downloads') else 'search_documents' if result.get('sources') else 'analyze_image' if method.__name__=='ask_vision' else 'edit_code' if method.__name__=='run_coding_project_task' and result.get('state')=='completed' else None)
                trace.total_time=perf_counter()-trace._started
                trace.evidence_used=bool(result.get('sources') or (result.get('result') or {}).get('sources'))
                trace.event('REQUEST_FAILED' if result.get('state',result.get('status'))=='failed' else 'REQUEST_COMPLETED')
                routing['decision']=trace.snapshot()
            return result
        except Exception as exc:
            error={'code':getattr(exc,'code','execution_error'),'message':str(exc)}
            if error not in trace.errors:trace.errors.append(error)
            trace.failure_layer=trace.failure_layer or {'cancelled':'cancellation','resource_unavailable':'resource_admission','model_unavailable':'candidate_filter','embedding_mismatch':'retrieval','invalid_calculation':'tool_execution','tool_input':'tool_validation','tool_execution_failed':'tool_execution','missing_evidence':'evidence','context_budget':'context_admission','generation_format':'generation','unsupported_evidence':'validation'}.get(error['code'],'execution')
            if trace.retrieval and trace.retrieval['status']=='started':trace.retrieval['status']='failed'
            trace.event('REQUEST_CANCELLED' if error['code']=='cancelled' else 'REQUEST_FAILED')
            if parent is None:
                trace.total_time=perf_counter()-trace._started
                exc.routing=trace.snapshot()
            raise
        finally:
            if parent is None:
                snapshot=trace.snapshot()
                if hasattr(self,'remember_route'):self.remember_route(snapshot)
                if job is not None:
                    lock=getattr(job,'lock',None)
                    with lock if lock is not None else nullcontext():job.routing={'decision':snapshot}
            CURRENT_ROUTE.reset(token)
    return run
