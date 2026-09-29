from backend.cancellation import cancellable_model_job
from pathlib import Path
from uuid import uuid4
from dataclasses import asdict
import hashlib
import json
import os
import re
import threading
import shutil
import time
from collections import OrderedDict
from router.telemetry import CURRENT_ROUTE
from router.capability_classifier import ConservativeCapabilityClassifier
from backend.contracts import WorkbenchError
from backend.settings import Settings
from backend.model import LocalModel
from rag.embedding import Embedder
from rag.ingest import extract, chunk_pages, SUPPORTED
from rag.store import Store
from rag.retrieve import retrieve, document_scope_for_question
from rag.answer import answer
from rag.overview import overview_passages, overview_documents
from rag.pdf_visuals import enrich_pdf_chunks
from rag.vision import ask_vision
from router.model_registry import ModelRegistry
from router.router import CapabilityRouter
from router.task_ledger import TaskLedger
from router.orchestrator import Orchestrator, TaskState
from router.tool_registry import ToolRegistry, ToolContract
from router.sandbox import CodeSandbox, SANDBOX_POLICY
from workflows.coding_workspace import CodingWorkspace


class Workbench:
    def __init__(self, settings=None, store=None, embedder=None, model=None, registry=None):
        self.settings=settings or Settings()
        self.sources_dir = self.settings.sources_dir
        if self.sources_dir.is_symlink() or (hasattr(self.sources_dir, 'is_junction') and self.sources_dir.is_junction()):
            raise WorkbenchError('source_conflict', 'Knowledge folder links are not supported')
        self.sources_dir.mkdir(parents=True, exist_ok=True)
        legacy_sources = self.settings.data_dir / 'sources'
        if legacy_sources != self.sources_dir and legacy_sources.is_dir():
            for source in legacy_sources.iterdir():
                if source.is_symlink() or (hasattr(source, 'is_junction') and source.is_junction()):
                    raise WorkbenchError('source_conflict', 'Knowledge source links are not supported')
                if not source.is_file() or source.suffix.lower() not in SUPPORTED:
                    continue
                destination = self.sources_dir / source.name
                if destination.is_symlink() or (hasattr(destination, 'is_junction') and destination.is_junction()):
                    raise WorkbenchError('source_conflict', 'Knowledge source links are not supported')
                if destination.exists():
                    if hashlib.sha256(destination.read_bytes()).digest() != hashlib.sha256(source.read_bytes()).digest():
                        raise WorkbenchError('source_conflict', 'Knowledge source already exists with different content')
                else:
                    shutil.copy2(source, destination)
        self.store=store or Store(self.settings.data_dir/'index.sqlite',self.settings.max_chunks)
        self._embedder=embedder
        self.model=model or LocalModel(self.settings.model_url)
        self.registry=registry or ModelRegistry(8087)
        self.router=CapabilityRouter(self.registry)
        self.classifier=ConservativeCapabilityClassifier()
        self.tasks=TaskLedger(self.settings.data_dir)
        project_root = self.settings.project_dir or (Path.home() / 'Documents' / 'SovereignAI' / 'Projects'
                       if self.settings.data_dir == self.settings.root / 'data' else self.settings.data_dir / 'projects')
        self.coding=CodingWorkspace(self.settings.data_dir, project_root)
        self.ask_lock=threading.Lock()
        self.import_lock=threading.Lock()
        self.embedding_lock=threading.Lock()
        self.routing_decisions=OrderedDict()
        self.routing_lock=threading.Lock()
        from backend.automations import Automations
        self.automations=Automations(self)

    def remember_route(self,decision):
        with self.routing_lock:
            self.routing_decisions[decision['request_id']]=decision
            while len(self.routing_decisions)>128:self.routing_decisions.popitem(last=False)

    def routing_decision(self,request_id=None):
        with self.routing_lock:
            result=(self.routing_decisions.get(request_id) if request_id else
                    next(reversed(self.routing_decisions.values()),None))
        if result is None:raise WorkbenchError('unknown_route','Routing decision is no longer available')
        return result

    def _cpu_readonly_plan(self,request,history=None,mode='chat'):
        """Use only an explicitly released classifier; never authorize writes."""
        trace=CURRENT_ROUTE.get()
        prediction=trace.classification if trace else None
        if not isinstance(prediction,dict) or not prediction.get('production_enabled'):
            return None
        action=prediction.get('decision')
        if action not in {'answer','search_documents','edit_code'} or (action=='edit_code' and mode!='chat'):
            return None
        if trace:
            trace.stages.append({'stage':'intent','action':action,'source':'released_cpu_classifier'})
            trace.intent=action
        response=self.model.conversation_answer(request,history) if action=='answer' else ''
        return {'action':action,'response':response,'target':'','document_scope':'focused'}

    def _lease(self,capability,required_context=None):
        trace=CURRENT_ROUTE.get()
        select=getattr(self.router,'select_model',None)
        if callable(select) and callable(getattr(self.registry,'installed',None)):
            route_start=time.perf_counter()
            current=self.registry._get_current_alias()
            selection=select(capability,modality='image' if capability=='vision' else 'text',required_context=required_context,current_residency=current)
            data=selection.to_dict()
            data['routing_time']=time.perf_counter()-route_start
            if trace:trace.selection(data)
            route=selection.registry_key
            if route is None:
                if trace:trace.failure_layer='resource_admission' if data.get('failure_category')=='RESOURCE_FAILURE' else 'candidate_filter'
                raise WorkbenchError('model_unavailable',data['route_reason'])
        else:
            route=self.router.route_request(capability)
        if trace:
            trace.runtime_alias=getattr(getattr(self.registry,'specs',{}).get(route),'alias',None)
            trace._context_admit=lambda required:self._lease(capability,required)
        started=time.perf_counter()
        lease=self.registry.acquire_lease(route)
        if trace:
            trace.event('MODEL_READY')
            trace.add_time('lease_time',time.perf_counter()-started)
            if isinstance(lease,dict):
                trace.add_time('model_load_time',lease.get('model_load_time'))
                if isinstance(lease.get('switch_required'),bool):
                    trace.switch_required=trace.switch_required is True or lease['switch_required']
                if isinstance(lease.get('available_context'),int):trace.available_context=lease['available_context']
                trace.stages.append({'stage':'runtime_lease',**lease})
            if trace.selected_model is None:
                trace.capability=capability
                trace.selected_model=getattr(getattr(self.registry,'specs',{}).get(route),'alias',None)
        return route

    @property
    def embedder(self):
        with self.embedding_lock:
            if self._embedder is None:
                self._embedder=Embedder(self.settings.model_dir)
            return self._embedder

    def documents(self):
        return self.store.documents()

    def rename_document(self, document_id, display_name, expected_hash=None):
        with self.import_lock:
            return self.store.rename_document(document_id, display_name, expected_hash)

    def remove_document(self, document_id, expected_hash=None):
        with self.import_lock:
            return self.store.remove_document(document_id, expected_hash)

    def move_document(self,document_id,folder,expected_hash=None):
        with self.import_lock:
            return self.store.move_document(document_id,folder,expected_hash)

    def copy_document(self,document_id,folder=None,expected_hash=None):
        with self.import_lock:
            return self.store.copy_document(document_id,folder,expected_hash)

    def import_file(self,path,document_id=None,display_name=None,expected_hash=None):
        path=Path(path).resolve()
        name=display_name or path.name
        if path.suffix.lower() not in SUPPORTED:
            raise WorkbenchError('unsupported_file','Use PDF, DOCX, XLSX, PPTX, CSV, JSON, LOG, TXT or Markdown')
        if not self.import_lock.acquire(blocking=False):
            raise WorkbenchError('busy','Another document is being indexed')
        try:
            if document_id is not None and self.store.current(document_id) is None:
                raise WorkbenchError('unknown_document','Update requires an existing document ID')
            try:
                with path.open('rb') as source:
                    data=source.read(self.settings.max_file_bytes+1)
            except OSError as exc:
                raise WorkbenchError('parse_failed','Could not read selected file') from exc
            if len(data)>self.settings.max_file_bytes:
                raise WorkbenchError('file_too_large','File exceeds upload limit')
            digest=hashlib.sha256(data).hexdigest()
            identity=('upload:'+name+':'+digest) if display_name is not None else os.path.normcase(str(path))
            document_id=document_id or hashlib.sha256(identity.encode()).hexdigest()
            current=self.store.current(document_id)
            if expected_hash is not None and (not current or current['active_hash']!=expected_hash):
                raise WorkbenchError('document_conflict','Document changed. Refresh before replacing the file.')
            if current:
                name=current['display_name']
            if current and current['active_hash']==digest:
                return {'status':'unchanged',**current}
            sources=self.sources_dir
            sources.mkdir(parents=True,exist_ok=True)
            snapshot=sources/(digest+path.suffix.lower())
            if not snapshot.exists():
                temporary=sources/(uuid4().hex+'.tmp')
                try:
                    temporary.write_bytes(data)
                    temporary.replace(snapshot)
                finally:
                    temporary.unlink(missing_ok=True)
            extraction=extract(snapshot,self.settings.max_file_bytes,self.settings.max_pages)
            ocr_pages=[{'page':page.page,'method':page.method,'confidence':page.confidence,
                        'page_image_hash':page.image_hash,'observations':page.observations}
                       for page in extraction.pages if page.method=='ocr']
            if ocr_pages:
                ocr_dir=self.settings.data_dir/'ocr'
                ocr_dir.mkdir(parents=True,exist_ok=True)
                metadata=ocr_dir/(digest+'.json')
                if not metadata.exists():
                    temporary=ocr_dir/(uuid4().hex+'.tmp')
                    try:
                        temporary.write_text(json.dumps({'source_hash':digest,'pages':ocr_pages},ensure_ascii=False),encoding='utf-8')
                        temporary.replace(metadata)
                    finally:
                        temporary.unlink(missing_ok=True)
            chunks=chunk_pages(extraction,self.embedder.tokenizer,document_id,name,self.settings.chunk_tokens,self.settings.overlap_tokens)
            vectors=self.embedder.encode([c.text for c in chunks])
            result=self.store.publish(document_id,name,str(path),digest,chunks,vectors,self.embedder.revision,extraction.warnings)
            result['usable_pages']=len(extraction.pages)
            return result
        finally:
            self.import_lock.release()

    @cancellable_model_job
    def ask(self,question,document_ids=None,history=None,job=None,force_documents=False,document_scope='focused',report_generation=False):
        if not isinstance(question,str) or not question.strip():
            raise WorkbenchError('invalid_question','Enter a question')
        if len(question)>8000:
            raise WorkbenchError('question_too_long','Question exceeds 8000 characters')
        from rag.calculator import literal_expression
        expression=literal_expression(question) if not force_documents else None
        if expression is not None:
            if job and job.cancel.is_set():raise WorkbenchError('cancelled','Task stopped')
            if job:job.progress('Calculating locally')
            result=self.calculate(expression)
            trace=CURRENT_ROUTE.get()
            if trace:
                trace.intent='calculate'
                trace.capability='calculation'
                trace.evidence_required=False
                trace.evidence_used=False
                trace.retrieval={'required':False,'status':'not_required','document_count':0,'passage_count':0,'candidate_count':0}
                trace.tool_candidates=[{'name':'calculator','status':'executed','reason':'Validated arithmetic syntax'}]
                trace.event('TOOL_COMPLETED')
            return {'status':'conversation','answer':f"{result['expression']} = {result['result']}", 'sources':[], 'task_id':result['task_id'], 'result':result,
                    'routing':{'capability':'calculation','model':'No model used'}}
        history=[item[:500] for item in (history or [])[-6:] if isinstance(item,str)]
        if not self.ask_lock.acquire(blocking=False):
            raise WorkbenchError('busy','Another answer is being generated')
        try:
            started=time.perf_counter()
            if job and job.cancel.is_set():
                raise WorkbenchError('cancelled', 'Task stopped')
            lease_start=time.perf_counter()
            route=self._lease('text')
            lease_seconds=time.perf_counter()-lease_start
            if job:job.progress('Preparing document answer' if force_documents else 'Understanding the request')
            report_requested=False
            if not force_documents:
                selected_metadata=[{'document_id':doc['document_id'],'name':doc['display_name']} for doc in self.documents() if doc['document_id'] in document_ids] if document_ids else []
                intent=self._cpu_readonly_plan(question,history) or self.model.plan_task(question,selected_metadata,[],[*history,f'{len(document_ids or [])} indexed documents selected; search them only if the request needs their contents'])
                trace=CURRENT_ROUTE.get()
                if trace is not None:
                    trace.intent=intent['action']
                    trace.evidence_required=intent['action'] in {'search_documents','create_report'}
                    trace.retrieval={'required':trace.evidence_required,'status':'not_required' if not trace.evidence_required else 'started','document_count':0,'passage_count':0,'candidate_count':0}
                    trace.required_context_scope={'documents':intent['action'] in {'search_documents','create_report'},'project':False}
                    trace.available_context_scope={'document_ids':list(document_ids or [])}
                if job and job.cancel.is_set():
                    raise WorkbenchError('cancelled', 'Task stopped during request interpretation')
                if intent['action']=='answer':
                    return {'status':'conversation','answer':intent['response'],'sources':[],
                            'task_id':uuid4().hex,'timings':{'total_seconds':time.perf_counter()-started},
                            'routing':{'capability':route,'model':getattr(getattr(self.registry,'specs',{}).get(route),'alias','sovereign-text')}}
                if intent['action'] in {'application_tools','inspect_code','analyze_image'}:
                    # Chat supplies content inline; planning cannot grant mutation or change mode.
                    response=self.model.conversation_answer(question,history)
                    return {'status':'conversation','answer':response,'sources':[],
                            'task_id':uuid4().hex,'timings':{'total_seconds':time.perf_counter()-started},
                            'routing':{'capability':route,'model':'sovereign-text'}}
                if intent['action']=='edit_code':
                    if job:job.progress('Writing code')
                    generated=self.model.inline_code_answer(question,history,intent.get('target',''))
                    if job and job.cancel.is_set():raise WorkbenchError('cancelled','Task stopped during code generation')
                    return {'status':'conversation','answer':generated['answer'],'sources':[],
                            'usage':generated.get('usage',{}),'task_id':uuid4().hex,
                            'timings':{'total_seconds':time.perf_counter()-started},
                            'routing':{'capability':route,'model':getattr(getattr(self.registry,'specs',{}).get(route),'alias','sovereign-text')}}
                if intent['action'] not in {'search_documents','create_report'}:
                    raise WorkbenchError('needs_input','This request needs a different tool. Use Agent for code changes or calculations.')
                document_scope=intent.get('document_scope','focused')
                report_requested=intent['action']=='create_report'
            if document_ids == []:
                raise WorkbenchError('needs_input','Connect Knowledge to answer questions about your documents')
            # Validate filters even for an empty collection, without loading embeddings.
            retrieval_start=time.perf_counter()
            if job:job.progress('Retrieving selected document passages')
            active=self.store.active_chunks(document_ids)
            retrieval_query=question
            overview=overview_documents(active) if document_scope=='overview' else None
            passages=(overview_passages(active) if overview is not None else
                      retrieve(self.store,self.embedder,retrieval_query,document_ids) if active else [])
            passages=enrich_pdf_chunks(passages,self.sources_dir)
            retrieval_seconds=time.perf_counter()-retrieval_start
            trace=CURRENT_ROUTE.get()
            if trace is not None:
                trace.evidence_required=True
                trace.add_time('retrieval_time',retrieval_seconds)
                trace.retrieval={'required':True,'status':'completed','document_count':len({p.document_id for p in passages}),'passage_count':len(passages),'candidate_count':len(active)}
                trace.event('RETRIEVAL_COMPLETED')
            
            if job:job.progress('Generating sourced answer')
            result=answer(question,passages,self.model,self.settings.context,self.settings.output_tokens,self.settings.safety_tokens,
                          history=history,**({'overview_documents':overview} if overview is not None else {}),
                          **({'report_generation':True} if report_generation or report_requested else {}))
            if job and job.cancel.is_set():
                raise WorkbenchError('cancelled', 'Task stopped')
            result['task_id']=uuid4().hex
            result['routing']={'capability':route,'model':self.registry.specs[route].alias if hasattr(self.registry,'specs') else 'sovereign-text'}
            result['timings'].update(
                retrieval_seconds=retrieval_seconds,
                switch_latency=None,
                lease_seconds=lease_seconds,
                total_seconds=time.perf_counter()-started
            )
            if report_requested:
                from workflows.document_report import publish_report
                task=self.tasks.create('document_report',document_ids or [])
                try:
                    if job:job.progress('Exporting Word report')
                    self.tasks.step(task,'export_word',{'sources':len(result.get('sources',[]))})
                    result['downloads']=publish_report(self.settings,task['task_id'],question,result)
                    result['task_id']=task['task_id']
                    self.tasks.complete(task,{'grounded_answer':True,'word_readback':True})
                except Exception:
                    self.tasks.fail(task,'report_failed')
                    raise
            answers=self.settings.data_dir/'answers'
            answers.mkdir(parents=True,exist_ok=True)
            (answers/(result['task_id']+'.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
            return result
        finally:
            self.ask_lock.release()

    @cancellable_model_job
    def ask_vision(self, image_path, question, job=None):
        if not isinstance(question,str) or not question.strip():
            raise WorkbenchError('invalid_question','Enter a question')
        if not self.ask_lock.acquire(blocking=False):
            raise WorkbenchError('busy','Another answer is being generated')
        try:
            if job and job.cancel.is_set():raise WorkbenchError('cancelled','Image request stopped')
            if job:job.progress('Reading attached image')
            started=time.perf_counter()
            from PIL import Image, UnidentifiedImageError
            try:
                with Image.open(image_path) as source:
                    if source.width * source.height > 12_000_000:
                        raise WorkbenchError('file_too_large','Image exceeds the pixel limit')
                    img=source.convert('RGB')
            except (UnidentifiedImageError,OSError) as exc:
                raise WorkbenchError('invalid_upload','Image could not be decoded') from exc
            
            if job and job.cancel.is_set():raise WorkbenchError('cancelled','Image request stopped before loading the model')
            switch_start = time.perf_counter()
            route=self._lease('vision')
            switch_latency = time.perf_counter() - switch_start
            
            if job and job.cancel.is_set():raise WorkbenchError('cancelled','Image request stopped before inference')
            if job:job.progress('Analyzing attached image')
            result = ask_vision(img, question, request=self.model._request) if isinstance(self.model,LocalModel) else ask_vision(img, question)
            if job and job.cancel.is_set():raise WorkbenchError('cancelled','Image request stopped after inference')
            result['task_id']=uuid4().hex
            result['routing']={'capability':route,'model':self.registry.specs[route].alias if hasattr(self.registry,'specs') else 'sovereign-vision'}
            if 'timings' not in result:
                result['timings'] = {}
            result['timings'].update(
                switch_latency=switch_latency,
                total_seconds=time.perf_counter()-started
            )
            return result
        finally:
            self.ask_lock.release()

    @cancellable_model_job
    def run_image_agent(self, goal, image_path, job=None):
        """An attachment permits visual context; intent decides whether to read it."""
        if not isinstance(goal,str) or not goal.strip() or len(goal)>2000:
            raise WorkbenchError('invalid_goal','Describe an image request under 2,000 characters')
        task=self.tasks.create('image_agent',[])
        try:
            if job and job.cancel.is_set():raise WorkbenchError('cancelled','Image task stopped')
            if not self.ask_lock.acquire(blocking=False):raise WorkbenchError('busy','Another model task is running')
            try:
                if job:job.progress('Understanding the image request')
                if job and job.cancel.is_set():raise WorkbenchError('cancelled','Image task stopped before loading the model')
                self._lease('text')
                plan=self.model.plan_task(goal,[],[],[],images=[{'name':'Attached image'}])
            finally:self.ask_lock.release()
            if job and job.cancel.is_set():raise WorkbenchError('cancelled','Image task stopped after planning')
            self.tasks.step(task,'plan',{'action':plan['action']})
            if plan['action']=='answer':
                spec=getattr(self.registry,'specs',{}).get('text')
                result={'status':'answered','answer':plan['response'],
                        'routing':{'capability':'text','model':spec.alias if spec else 'sovereign-text',
                                   'reason':'Answered without inspecting the attached image'}}
            elif plan['action']=='analyze_image':
                self.tasks.step(task,'analyze_image',{})
                result=self.ask_vision(image_path,goal,job=job)
            else:
                raise WorkbenchError('needs_input','This attachment supports image questions; use document or project context for that task')
            if job and job.cancel.is_set():raise WorkbenchError('cancelled','Image task stopped before completing')
            self.tasks.complete(task,{'workflow_returned':True,'workflow_succeeded':True})
            return {'task_id':task['task_id'],'status':'completed','answer':result['answer'],'plan':plan,
                    'result':result,'downloads':{},'workspace_id':None,'steps':task['steps'],
                    'routing':result['routing']}
        except Exception as exc:
            self.tasks.fail(task,getattr(exc,'code','image_task_failed'))
            if isinstance(exc,WorkbenchError):exc.task_id=task['task_id']
            raise

    def create_maintenance_draft(self,document_ids):
        from workflows.maintenance import create_maintenance_draft
        if not self.ask_lock.acquire(blocking=False):
            raise WorkbenchError('busy','Another task is running')
        try:
            if not document_ids or len(document_ids)>100:
                raise WorkbenchError('invalid_selection','Select report and requirement documents')
            task=self.tasks.create('maintenance_draft',document_ids)
            try:
                self.tasks.step(task,'select_evidence',{'document_count':len(document_ids)})
                result=create_maintenance_draft(self.store,self.settings,document_ids,task_id=task['task_id'])
                self.tasks.step(task,'compare_measurements',{'finding_count':len(result['findings']),
                    'calculation_count':len(result['calculations'])})
                self.tasks.step(task,'write_deliverables',{'artifact_count':3})
                checks={'findings_present':bool(result['findings']),
                        'sources_recorded':bool(result['source_versions']),
                        'word_written':Path(result.get('word_path','')).is_file(),
                        'excel_written':Path(result.get('excel_path','')).is_file(),
                        'slides_written':Path(result.get('slide_path','')).is_file()}
                self.tasks.complete(task,checks)
                return result
            except Exception as exc:
                self.tasks.fail(task,exc.code if isinstance(exc,WorkbenchError) else 'workflow_failed')
                raise
        finally:
            self.ask_lock.release()

    def _verified_coding_sandbox(self):
        validation=self.settings.data_dir/'sandbox-validation.json'
        if not validation.is_file():
            raise WorkbenchError('sandbox_unavailable','Run the Docker isolation verifier first')
        try:
            config=json.loads(validation.read_text(encoding='utf-8'))
        except (OSError,ValueError) as exc:
            raise WorkbenchError('sandbox_unavailable','Docker isolation record is invalid') from exc
        required={'normal_execution','network_blocked','root_read_only','input_read_only','non_root'}
        checks=config.get('checks')
        if not isinstance(checks,dict) or not all(checks.get(name) is True for name in required):
            raise WorkbenchError('sandbox_unavailable','Docker isolation verification did not pass')
        return CodeSandbox('docker',image_id=config.get('image_id'),task_root=self.settings.data_dir/'code-tasks')

    def create_csv_coding_demo(self):
        from workflows.coding import run_csv_demo
        if not self.ask_lock.acquire(blocking=False):
            raise WorkbenchError('busy','Another task is running')
        try:
            sandbox=self._verified_coding_sandbox()
            self._lease('code')
            return run_csv_demo(self.model,sandbox,self.tasks,self.settings)
        finally:
            self.ask_lock.release()

    def run_coding_workspace_task(self, workspace_id, target, instruction, job=None):
        if not self.ask_lock.acquire(blocking=False):
            raise WorkbenchError('busy','Another task is running')
        try:
            sandbox=self._verified_coding_sandbox()
            if job:job.progress('Loading local model');sandbox.on_output=job.append;sandbox.cancel_event=job.cancel
            capability=self._lease('code')
            specs=getattr(self.registry,'specs',{})
            alias=specs[capability].alias if capability in specs else 'sovereign-text'
            return self.coding.run(workspace_id,target,instruction,self.model,sandbox,self.tasks,
                                   model_alias=alias,progress=job.progress if job else None,cancel=job.cancel if job else None)
        finally:
            self.ask_lock.release()

    @cancellable_model_job
    def run_coding_project_task(self, workspace_id, target, instruction, job=None, routed=False):
        if not self.ask_lock.acquire(blocking=False):
            raise WorkbenchError('busy','Another task is running')
        try:
            if job:job.progress('Understanding the request')
            capability=self._lease('code')
            specs=getattr(self.registry,'specs',{})
            alias=specs[capability].alias if capability in specs else 'sovereign-text'
            if not routed:
                intent=self.model.plan_task(instruction,[],[],[])
                if job and job.cancel.is_set():
                    raise WorkbenchError('cancelled', 'Task stopped during request interpretation')
                if intent['action']=='answer':
                    return {'state':'answered','answer':intent['response'],
                            'routing':{'capability':capability,'model':alias,'reason':'Answered before reading project files'}}
                if intent['action']=='inspect_code':
                    if not workspace_id:raise WorkbenchError('needs_input','Choose a project to inspect')
                    files=self.coding.get(workspace_id)['files']
                    excerpts=[]
                    remaining=10000
                    for item in files:
                        source=self.coding.read(workspace_id,item['name'])
                        if not source['editable']:continue
                        snippet=source['content'][:min(5000,remaining)]
                        excerpts.append({'name':item['name'],'source_excerpt':snippet,'excerpt_complete':len(snippet)==len(source['content'])})
                        remaining-=len(snippet)
                        if len(excerpts)>=8 or remaining<=0:break
                    generator=getattr(self.model,'conversation_answer',None)
                    response=generator(instruction,files=excerpts) if callable(generator) else self.model.plan_task(instruction,[],excerpts,[])['response']
                    return {'state':'answered','answer':response,
                            'routing':{'capability':capability,'model':alias,'reason':'Read project excerpts for the requested explanation'}}
                if intent['action']!='edit_code':raise WorkbenchError('needs_input','Use Agent for document questions and calculations')
            from router.tool_registry import explicit_operation_requested
            if not explicit_operation_requested(instruction,'file_edit'):
                raise WorkbenchError('needs_input','Specify the requested code change; classification alone cannot authorize an edit')
            sandbox=self._verified_coding_sandbox()
            if job:job.progress('Reading project structure');sandbox.on_output=job.append;sandbox.cancel_event=job.cancel
            return self.coding.run_project(workspace_id,target,instruction,self.model,sandbox,self.tasks,
                                           model_alias=alias,progress=job.progress if job else None,cancel=job.cancel if job else None)
        finally:
            self.ask_lock.release()

    def execute_coding_file(self, workspace_id, target, job=None):
        from workflows.code_runtime import runner
        if not self.ask_lock.acquire(blocking=False):
            raise WorkbenchError('busy','Another task is running')
        task = None
        try:
            sandbox = self._verified_coding_sandbox()
            self.coding.read(workspace_id, target)
            files = self.coding.raw_files(workspace_id)
            if job:
                job.progress('Starting isolated program');sandbox.on_output=job.append;sandbox.cancel_event=job.cancel;sandbox.stdin_queue=job.input
            script = runner(target, mode='run')
            task = self.tasks.create('workspace_execution', [])
            self.tasks.step(task, 'docker_run', {'target':target})
            execution = sandbox.execute(script,timeout=120,input_files=files)
            checks = {'container_executed':execution.executed, 'exit_success':execution.exit_code == 0}
            if all(checks.values()): self.tasks.complete(task,checks)
            else: self.tasks.fail(task,'execution_failed')
            return {'task_id':task['task_id'],'state':task['state'],'exit_code':execution.exit_code,
                    'stdout':execution.stdout,'stderr':execution.stderr,'checks':checks}
        except Exception:
            if task: self.tasks.fail(task,'execution_failed')
            raise
        finally:
            self.ask_lock.release()

    def execute_terminal(self, workspace_id, command, job, cwd=''):
        if not self.ask_lock.acquire(blocking=False):raise WorkbenchError('busy','Another task is running')
        try:
            if cwd:
                folder=self.coding._file(workspace_id,cwd)
                if not folder.is_dir():raise WorkbenchError('invalid_file','Terminal working directory does not exist')
            job.append('stdin','$ /project'+('/'+cwd if cwd else '')+'> '+command+'\n')
            sandbox=self._verified_coding_sandbox()
            files=self.coding.raw_files(workspace_id)
            sandbox.on_output=job.append;sandbox.cancel_event=job.cancel;sandbox.stdin_queue=job.input
            job.progress('Terminal running in Docker')
            script="""import os,shutil,subprocess,sys,json,base64
from pathlib import Path
source=Path('/input'); project=Path('/output/project')
shutil.copytree(source,project,ignore=lambda directory,names: ['program.py'] if Path(directory)==source and 'program.py' in names else [])
os.chdir("""+repr('/output/project'+('/'+cwd if cwd else ''))+""")
code=subprocess.call(['bash','--noprofile','--norc','-c',"""+repr(command)+"""])
if code: sys.exit(code)
before={p.relative_to(source).as_posix():p.read_bytes() for p in source.rglob('*') if p.is_file() and p != source/'program.py'}
after={}
for path in project.rglob('*'):
    if path.is_symlink(): raise RuntimeError('Terminal outputs cannot contain symbolic links')
    if path.is_file(): after[path.relative_to(project).as_posix()]=path.read_bytes()
delta={'changed':{name:base64.b64encode(data).decode('ascii') for name,data in after.items() if before.get(name)!=data},'deleted':sorted(set(before)-set(after))}
payload=json.dumps(delta).encode('utf-8')
if len(payload)>999000: raise RuntimeError('Terminal changes exceed the 999 KB transfer budget; no project changes were saved')
Path('/output/project-sync.json').write_bytes(payload)
"""
            result=sandbox.execute(script,timeout=120,input_files=files)
            changes={}
            if result.exit_code==0:
                payload=result.output_files.get('project-sync.json')
                if not payload:raise WorkbenchError('sandbox_output','Terminal did not return its project changes; no changes were saved')
                try:manifest=json.loads(payload)
                except (ValueError,TypeError):raise WorkbenchError('sandbox_output','Invalid terminal project changes')
                changes=self.coding.apply_terminal_changes(workspace_id,files,manifest)
            return {'state':'completed' if result.exit_code==0 else 'failed','exit_code':result.exit_code,'stdout':result.stdout,'stderr':result.stderr,'cwd':cwd,'workspace_id':workspace_id,**changes}
        finally:self.ask_lock.release()

    def calculate(self,expression):
        from rag.calculator import evaluate_expression
        if not isinstance(expression,str) or len(expression)>100:
            raise WorkbenchError('invalid_calculation','Use an arithmetic expression under 100 characters')
        if not self.ask_lock.acquire(blocking=False):
            raise WorkbenchError('busy','Another task is running')
        task=None
        try:
            task=self.tasks.create('calculation',[])
            self.tasks.step(task,'evaluate_expression',{'expression':expression})
            value=evaluate_expression(expression)
            checks={'finite_result':True,'steps_recorded':bool(value.steps)}
            self.tasks.complete(task,checks)
            return {'status':'completed','task_id':task['task_id'],'expression':value.expression,
                    'result':value.result,'rounded':value.rounded,'steps':value.steps}
        except Exception as exc:
            if task is not None:
                self.tasks.fail(task,exc.code if isinstance(exc,WorkbenchError) else 'calculation_failed')
            raise
        finally:
            self.ask_lock.release()

    @cancellable_model_job
    def create_document_report(self, question, document_ids, history=None,job=None,document_scope=None):
        from workflows.document_report import is_overview_request, publish_report, selected_document_overview
        task=self.tasks.create('document_report',document_ids or [])
        try:
            self.tasks.step(task,'read_documents',{})
            if job and job.cancel.is_set():
                raise WorkbenchError('cancelled', 'Task stopped')
            if job:job.progress('Reading selected documents')
            result=(selected_document_overview(self.store.active_chunks(document_ids),question)
                    if document_scope is None and is_overview_request(question) else
                    self.ask(question,document_ids,history,job=job,force_documents=True,report_generation=True,
                             **({'document_scope':document_scope} if document_scope is not None else {})))
            if job and job.cancel.is_set():
                raise WorkbenchError('cancelled', 'Task stopped')
            self.tasks.step(task,'export_word',{'sources':len(result.get('sources',[]))})
            if job:job.progress('Exporting Word report')
            downloads=publish_report(self.settings,task['task_id'],question,result)
            self.tasks.complete(task,{'grounded_answer':True,'word_readback':True})
            return {**result,'task_id':task['task_id'],'downloads':downloads}
        except Exception:
            self.tasks.fail(task,'report_failed')
            raise

    @cancellable_model_job
    def run_auto_agent(self, goal, document_ids=None, workspace_id=None, history=None, job=None):
        """Infer the workflow and source target; callers need only a request and optional context."""
        from rag.calculator import literal_expression
        expression=literal_expression(goal)
        if expression is not None:
            if job and job.cancel.is_set():raise WorkbenchError('cancelled','Task stopped')
            if job:job.progress('Calculating locally')
            result=self.calculate(expression)
            trace=CURRENT_ROUTE.get()
            if trace:
                trace.intent='calculate'
                trace.capability='calculation'
                trace.evidence_required=False
                trace.evidence_used=False
                trace.retrieval={'required':False,'status':'not_required','document_count':0,'passage_count':0,'candidate_count':0}
                trace.tool_candidates=[{'name':'calculator','status':'executed','reason':'Validated arithmetic syntax'}]
                trace.event('TOOL_COMPLETED')
            return {'task_id':result['task_id'],'status':'completed',
                    'answer':f"{result['expression']} = {result['result']}",
                    'plan':{'action':'calculate','target':'','response':'Arithmetic evaluated locally'},
                    'result':result,'downloads':{},'workspace_id':None,'steps':result['steps'],
                    'routing':{'capability':'calculation','model':'No model used',
                               'reason':'Arithmetic expression evaluated without loading a model'}}
        if job:job.progress('Understanding the request')
        task=self.tasks.create('automatic_task',document_ids or [])
        try:
            if not self.ask_lock.acquire(blocking=False): raise WorkbenchError('busy','Another model task is running')
            try:
                self._lease('text')
                selected_metadata=[{'document_id':doc['document_id'],'name':doc['display_name']} for doc in self.documents() if doc['document_id'] in document_ids] if document_ids else []
                try:
                    workspace_metadata=[{'name':item['name']} for item in self.coding.get(workspace_id)['files']] if workspace_id else []
                except WorkbenchError as error:
                    if error.code!='invalid_workspace':raise
                    workspace_metadata=[]
                plan=self._cpu_readonly_plan(goal,history,mode='agent') or self.model.plan_task(goal,selected_metadata,workspace_metadata,[item[:1000] for item in (history or [])[-8:] if isinstance(item,str)]+
                                          [f'{len(document_ids or [])} indexed documents selected; workspace selected: {bool(workspace_id)}'])
            finally:self.ask_lock.release()
            if job and job.cancel.is_set():raise WorkbenchError('cancelled','Task stopped after request planning')
            trace=CURRENT_ROUTE.get()
            if trace is not None:
                trace.intent=plan['action']
                trace.evidence_required=plan['action'] in {'search_documents','create_report'}
                trace.retrieval={'required':trace.evidence_required,'status':'not_required' if not trace.evidence_required else 'started','document_count':0,'passage_count':0,'candidate_count':0}
                trace.required_context_scope={'documents':plan['action'] in {'search_documents','create_report'},'project':plan['action'] in {'inspect_code','edit_code'}}
                trace.available_context_scope={'document_ids':list(document_ids or []),'workspace_id':workspace_id,'workspace_file_count':len(workspace_metadata)}
                trace.stages.append({'stage':'intent','action':plan['action'],'source':'bounded_model_planner'})
            self.tasks.step(task,'plan',{'workspace':workspace_id,'action':plan['action']})
            if plan['action']=='application_tools':
                from backend.application_tools import ApplicationTools
                if job:job.progress('Planning application operations')
                if not self.ask_lock.acquire(blocking=False):raise WorkbenchError('busy','Another model task is running')
                try:
                    self._lease('text')
                    # Explicit management commands resolve library names separately
                    # from the optional read/reference selection. No contents are read.
                    catalog=[{'name':doc['display_name'],'document_id':doc['document_id']} for doc in self.documents()]
                    schedules=[{'id':item['id'],'name':item['name'],'paused':item['paused']} for item in self.automations.list()]
                    operations=self.model.plan_application_tools(goal,catalog,workspace_metadata,history,automations=schedules)
                finally:self.ask_lock.release()
                result=ApplicationTools(self,workspace_id,job,document_ids,goal=goal).execute(operations,task)
                checks={'workflow_returned':True,'workflow_succeeded':result['state']=='completed'}
                if checks['workflow_succeeded']:self.tasks.complete(task,checks)
                else:self.tasks.fail(task,'workflow_failed')
                return {'task_id':task['task_id'],'status':task['state'],'answer':result['answer'],
                        'plan':plan,'result':result,'downloads':{},'workspace_id':workspace_id,'steps':task['steps']}
            if plan['action']=='answer':
                result={'answer':plan['response'],'status':'answered'}
                if job and job.cancel.is_set():raise WorkbenchError('cancelled','Task stopped before completing the answer')
                self.tasks.complete(task,{'workflow_returned':True,'workflow_succeeded':True})
                spec=getattr(self.registry,'specs',{}).get('text')
                return {'task_id':task['task_id'],'status':'completed','answer':plan['response'],'plan':plan,
                        'result':result,'downloads':{},'workspace_id':workspace_id,'steps':task['steps'],
                        'routing':{'capability':'text','model':spec.alias if spec else 'sovereign-text',
                                   'reason':'The text model answered without opening project or document files'}}
            if plan['action']=='analyze_image':raise WorkbenchError('needs_input','Attach an image to analyze')
            project_context=plan['action'] in {'edit_code','inspect_code'}
            if plan['action']=='edit_code':
                from router.tool_registry import explicit_operation_requested
                if not explicit_operation_requested(goal,'file_edit'):
                    raise WorkbenchError('needs_input','Specify the code change and its target; classification alone cannot authorize an edit')
            document_context=plan['action'] in {'search_documents','create_report'}
            if document_context and document_ids == []:
                raise WorkbenchError('needs_input','Connect Knowledge to answer questions about your documents')
            docs=self.documents() if document_context else []
            if document_ids is not None and document_context:
                docs=[doc for doc in docs if doc['document_id'] in document_ids]
            # The selected document workflow validates IDs and retrieves once.
            # Do not prefetch evidence that would be discarded before that workflow.
            files=self.coding.get(workspace_id)['files'] if project_context and workspace_id else []
            planning_files=[]
            if plan['action']=='inspect_code':
                if not workspace_id:raise WorkbenchError('needs_input','Choose a project to inspect')
                remaining=10000
                for file in files:
                    if file.get('editable') is False:continue
                    content=self.coding.read(workspace_id,file['name'])['content'] if remaining else ''
                    snippet=content[:remaining]
                    planning_files.append({'name':file['name'],'source_excerpt':snippet,'excerpt_complete':len(snippet)==len(content) if remaining else False})
                    remaining-=len(snippet)
                if not self.ask_lock.acquire(blocking=False):raise WorkbenchError('busy','Another model task is running')
                try:
                    self._lease('text')
                    explanation={'response':self.model.conversation_answer(goal,history,files=planning_files)}
                finally:self.ask_lock.release()
                result={'answer':explanation['response'],'status':'answered'}
                self.tasks.step(task,'inspect_code',{'files':len(planning_files)})
                if job and job.cancel.is_set():raise WorkbenchError('cancelled','Task stopped before completing the answer')
                self.tasks.complete(task,{'workflow_returned':True,'workflow_succeeded':True})
                spec=getattr(self.registry,'specs',{}).get('text')
                return {'task_id':task['task_id'],'status':'completed','answer':explanation['response'],'plan':plan,
                        'result':result,'downloads':{},'workspace_id':workspace_id,'steps':task['steps'],
                        'routing':{'capability':'text','model':spec.alias if spec else 'sovereign-text',
                                   'reason':'The text model inspected requested project excerpts without editing'}}
            # A planner proposes the workflow; current-request permission and
            # target/scope guards remain independent of classification.
            if plan['action']=='edit_code' and workspace_id:
                available={entry['name'] for entry in files}
                if not plan['target'].strip():
                    mentioned=[name for name in available if name.casefold() in goal.casefold()]
                    if len(mentioned)==1: plan['target']=mentioned[0]
                    else:
                        source=[name for name in available if name.endswith(('.py','.js','.ts','.java','.cpp','.go','.rs'))]
                        if len(source)==1: plan['target']=source[0]
                        else: raise WorkbenchError('needs_input','Name the source file to repair; this project has several candidates')
            if plan['action']!='answer':
                plan['response']={'calculate':'Evaluate the expression with the local calculator.','edit_code':'Edit the selected source and validate it in Docker.','search_documents':'Retrieve evidence from the indexed documents.','create_report':'Retrieve evidence and export a cited Word report.'}[plan['action']]
            self.tasks.step(task,plan['action'],{'target':plan['target'],'plan':plan['response'][:500]})
            scope=document_ids if document_ids is not None else [doc['document_id'] for doc in docs]
            if job:
                if job.cancel.is_set():raise WorkbenchError('cancelled','Task stopped before tool execution')
                job.progress(plan['response'] if plan['action']!='answer' else 'Writing answer')
            action=plan['action']
            if action=='answer': result={'answer':plan['response'],'status':'answered'}
            elif action=='calculate': result=self.calculate(plan['expression'])
            elif action=='search_documents': result=self.ask(goal,scope,history=history,job=job,force_documents=True,**({'document_scope':plan['document_scope']} if 'document_scope' in plan else {}))
            elif action=='create_report': result=self.create_document_report(goal,scope,history=history,job=job,**({'document_scope':plan['document_scope']} if 'document_scope' in plan else {}))
            elif action=='edit_code':
                self._verified_coding_sandbox()
                target=plan['target']
                if not workspace_id:
                    workspace_id=self.coding.create(goal[:80])['workspace_id']
                result=self.run_coding_project_task(workspace_id,target,goal[:1000],job=job,routed=True)
            if job and job.cancel.is_set():raise WorkbenchError('cancelled','Task stopped')
            checks={'workflow_returned':True,'workflow_succeeded':result.get('state')!='failed' and result.get('status')!='citation_failure'}
            if all(checks.values()): self.tasks.complete(task,checks)
            else: self.tasks.fail(task,'workflow_failed')
            answer_text=(result.get('answer') or (f"{result.get('expression')} = {result.get('rounded')}" if 'rounded' in result else
                f"{result.get('target','File')}: {result.get('state','finished')}. Validation: {result.get('validation','see checks')}."))
            plan_model=getattr(self.registry,'specs',{}).get('text')
            return {'task_id':task['task_id'],'status':task['state'],'answer':answer_text,'plan':plan,
                    'routing':{'capability':'text','model':plan_model.alias if plan_model else 'sovereign-text',
                               'reason':'Text model planned the task; the selected action used its registered tool or workflow'},
                    'result':result,'downloads':result.get('downloads',{}),'workspace_id':workspace_id,'steps':task['steps']}
        except Exception as exc:
            self.tasks.fail(task,getattr(exc,'code','task_failed'))
            if isinstance(exc,WorkbenchError): exc.task_id=task['task_id']
            raise

    def run_agent_goal(self,goal,document_ids=None,workspace_id=None,target=None,image_path=None):
        """Route one explicit agent request through the existing bounded orchestrator."""
        if not isinstance(goal,str) or not goal.strip() or len(goal)>2000:
            raise WorkbenchError('invalid_goal','Describe a goal under 2,000 characters')
        document_ids=document_ids or []
        if not isinstance(document_ids,list) or len(document_ids)>100 or not all(isinstance(item,str) for item in document_ids):
            raise WorkbenchError('invalid_selection','Select at most 100 indexed documents')
        if sum(bool(value) for value in (document_ids,workspace_id,image_path))>1:
            raise WorkbenchError('invalid_selection','Choose only one of documents, coding workspace, or image')
        started=time.perf_counter()
        task=self.tasks.create('agent_goal',document_ids)
        tools=ToolRegistry()
        tools.register('ask_documents',self.ask,ToolContract(('question','document_ids'),('question',)))
        tools.register('maintenance_draft',self.create_maintenance_draft,ToolContract(('document_ids',),('document_ids',)))
        tools.register('calculate',self.calculate,ToolContract(('expression',),('expression',)))
        tools.register('coding_workspace',self.run_coding_workspace_task,
                       ToolContract(('workspace_id','target','instruction'),('workspace_id','target','instruction')))
        tools.register('csv_coding_demo',self.create_csv_coding_demo,ToolContract((),()))
        tools.register('ask_vision',self.ask_vision,ToolContract(('image_path','question'),('image_path','question')))
        orchestrator=Orchestrator(tools,self.registry)
        agent=orchestrator.create_task(task['task_id'],goal,
                                       on_change=lambda current:self.tasks.record_agent(task,current))
        try:
            agent.transition(TaskState.PLANNING,'Classifying bounded request')
            capability=self.router.classify_agent_goal(goal,document_ids=document_ids,
                                                       workspace_id=workspace_id,image=image_path is not None)
            if capability=='ARTIFACT' and len(document_ids)<2:
                raise WorkbenchError('needs_input','Select an inspection report and its SOP')
            if capability=='CODING' and not target:
                candidates=[item['name'] for item in self.coding.get(workspace_id)['files']
                            if not Path(item['name']).name.startswith('test_')]
                if len(candidates)==1: target=candidates[0]
                else: raise WorkbenchError('needs_input','Open a source file in Code, or describe its filename in a new task')
            workflow={'ARTIFACT':'maintenance_draft','DOCUMENT_QA':'ask_documents',
                      'CALCULATION':'calculate','CODING':'coding_workspace',
                      'CODING_DEMO':'csv_coding_demo','VISION':'ask_vision'}[capability]
            model_capability=('vision' if capability=='VISION' else 'text')
            if capability not in {'CALCULATION','ARTIFACT'}:
                self.router.route_request('vision' if capability=='VISION' else 'code' if capability.startswith('CODING') else 'text')
            specs=getattr(self.registry,'specs',{})
            selected_model=(None if capability in {'CALCULATION','ARTIFACT'} else
                            specs[model_capability].alias if model_capability in specs else
                            ('sovereign-vision' if capability=='VISION' else 'sovereign-text'))
            kwargs=({'question':goal,'document_ids':document_ids} if capability=='DOCUMENT_QA' else
                    {'document_ids':document_ids} if capability=='ARTIFACT' else
                    {'expression':re.split(r'^\s*calculate\s*:\s*',goal,maxsplit=1,flags=re.I)[1]} if capability=='CALCULATION' else
                    {'workspace_id':workspace_id,'target':target,'instruction':goal} if capability=='CODING' else
                    {'image_path':image_path,'question':goal} if capability=='VISION' else {})
            self.tasks.step(task,'plan',{'capability':capability,'workflow':workflow})
            # The orchestrator owns the tool call, state, step and repair limits.
            result=orchestrator.run_step(task['task_id'],workflow,kwargs,retryable=False)
            self.tasks.step(task,'dispatch',{'workflow':workflow,'child_task_id':result.get('task_id')})
            if capability in {'DOCUMENT_QA','VISION'}:
                checks={'answer_available':bool(result.get('answer'))}
                if capability == 'DOCUMENT_QA':
                    checks['grounded'] = result.get('status') == 'answered'
            else:
                child=self.tasks.read(result['task_id'])
                checks={'child_completed':child['state']=='completed',
                        'child_checks_passed':bool(child['checks']) and all(child['checks'].values())}
            if not all(checks.values()):
                raise WorkbenchError('verification_failed','Workflow checks did not pass')
            orchestrator.complete_task(task['task_id'],checks)
            self.tasks.complete(task,checks)
            usage=result.get('usage') if isinstance(result.get('usage'),dict) else {}
            prompt_tokens=usage.get('prompt_tokens') if isinstance(usage.get('prompt_tokens'),int) else None
            resource={'max_steps':agent.max_steps,'max_repairs':agent.max_repairs,
                      'max_model_switches':1,'max_context_tokens':self.settings.context if selected_model else None,
                      'output_budget_tokens':self.settings.output_tokens if selected_model else None,
                      'prompt_tokens':prompt_tokens,
                      'remaining_context_tokens':(max(0,self.settings.context-prompt_tokens-self.settings.output_tokens-self.settings.safety_tokens)
                                                  if prompt_tokens is not None and selected_model else None),
                      'retrieved_evidence':len(result.get('sources',[])),
                      'tool_output_bytes':len(json.dumps(result,default=str).encode('utf-8')),
                      'max_task_seconds':300}
            response={'status':'completed','task_id':task['task_id'],'user_intent':goal,
                      'capability':capability,'selected_model':selected_model,
                      'route':{'capability':capability,'model':selected_model,
                               'reason':('Deterministic workflow; no model loaded' if capability in {'CALCULATION','ARTIFACT'}
                                         else 'Explicit agent request and bounded inputs')},
                      'workflow':workflow,'child_task_id':result.get('task_id'),'result':result,
                      'executed_steps':agent.step_count,'tool_results':agent.history,
                      'artifacts':({kind:f"/artifacts/{result['task_id']}/{kind}" for kind in ('word','excel','slides')}
                                   if capability=='ARTIFACT' else result.get('output_files',[])),
                      'checks':checks,'unresolved_issues':[],
                      'timings':{'total_seconds':round(time.perf_counter()-started,3)},
                      'resource':resource}
            task['agent_result']={key:value for key,value in response.items() if key!='result'}
            self.tasks.record_agent(task,agent)
            return response
        except Exception as exc:
            code=exc.code if isinstance(exc,WorkbenchError) else 'workflow_failed'
            if code=='needs_input':
                agent.transition(TaskState.NEEDS_INPUT,code)
                self.tasks.needs_input(task,code)
            else:
                if agent.state not in (TaskState.FAILED,TaskState.COMPLETED):
                    agent.transition(TaskState.FAILED,code)
                self.tasks.fail(task,code)
            self.tasks.record_agent(task,agent)
            if isinstance(exc,WorkbenchError):
                exc.task_id=task['task_id']
            raise

    def status(self):
        try:
            generator=self.model.status()
            if hasattr(self.registry,'_get_current_alias'):
                generator['alias']=self.registry._get_current_alias()
        except WorkbenchError as exc:
            generator={'available':False,'code':exc.code,'message':str(exc)}
        state=getattr(self.registry,'runtime_state',None)
        if state not in {'Loading','Switching','Unloading','Error'}:
            state='Loading' if generator.get('code')=='model_loading' else 'Offline' if not generator.get('available') else 'Idle' if generator.get('is_sleeping') else 'Ready'
            if state=='Ready' and isinstance(self.model,LocalModel):
                try:
                    slots=self.model._request('GET','/slots')
                    if isinstance(slots,list) and any(slot.get('is_processing') for slot in slots if isinstance(slot,dict)):state='Generating'
                except WorkbenchError:pass
        generator['state']=state
        docs=self.documents()
        return {'documents':len(docs),'chunks':sum(d['chunk_count'] for d in docs),
                'embedding':{'loaded':self._embedder is not None,'files_present':all((self.settings.model_dir/p).is_file() for p in ['tokenizer.json','onnx/model.onnx']),'device':'CPU'},
                'generator':generator,'busy':self.ask_lock.locked()}

    def workbench_info(self):
        """Read-only presentation facts from the configured runtime and verified sandbox."""
        runtime=self.status()
        sandbox={'ready':False,'reason':'Docker isolation has not been verified',
                 'policy':SANDBOX_POLICY,'image_id':None}
        try:
            runner=self._verified_coding_sandbox()
            runner._ready()
            sandbox.update(ready=True,reason=None,image_id=runner.image_id)
        except WorkbenchError as exc:
            sandbox['reason']=str(exc)
        specs=getattr(self.registry,'specs',{})
        models=[{'capability':key,'alias':spec.alias,'model_id':Path(spec.model_file).stem,
                 'quantization':spec.quantization,'context':spec.context,
                 'runtime':spec.runtime_adapter,'observed_gpu_mib':spec.observed_gpu_mib,
                 'enabled':spec.enabled,
                 'assets_present':all(path.is_file() for path in self.registry._model_paths(spec))
                    if hasattr(self.registry,'_model_paths') else False}
                for key,spec in specs.items()]
        routes={}
        for task_type in ('text','code','vision'):
            try:
                if callable(getattr(self.registry,'installed',None)):
                    choice=self.router.select_model(task_type,modality='image' if task_type=='vision' else 'text',current_residency=runtime['generator'].get('alias'))
                    routes[task_type]={'capability':task_type,'model':choice.selected_model,'decision':choice.to_dict()}
                else:
                    capability=self.router.route_request(task_type)
                    routes[task_type]={'capability':capability,'model':specs[capability].alias}
            except (WorkbenchError,KeyError):
                routes[task_type]={'capability':None,'model':None}
        vision_spec=specs.get('vision')
        vision_assets_ready=(bool(vision_spec and vision_spec.enabled) and
                             all(path.is_file() for path in self.registry._model_paths(vision_spec))) if hasattr(self.registry,'_model_paths') else False
        tools=[{'name':'Document search','available':True},
               {'name':'Calculator','available':True},
               {'name':'Maintenance artifacts','available':True},
               {'name':'Coding workspace / Docker','available':sandbox['ready']},
               {'name':'Vision','available':vision_assets_ready}]
        return {'runtime':runtime,'models':models,'routing':{'mode':'automatic','routes':routes},'sandbox':sandbox,'tools':tools,
                'host':'127.0.0.1','network_proof':'not assessed by this status endpoint',
                'model_registry':self.registry.records() if hasattr(self.registry,'records') else [],
                'classification':{'production_enabled':False,'method':'disabled_evaluated_cpu','release_report':'docs/capability-classifier-evaluation-v2.md'}}

    def artifact_catalog(self):
        """List only manifest-backed outputs, validating each file before offering a link."""
        items=[]
        output_root=self.settings.data_dir.parent/'outputs'
        if output_root.is_dir() and not output_root.is_symlink():
            for directory in output_root.iterdir():
                if not directory.is_dir() or directory.is_symlink() or not re.fullmatch(r'[a-f0-9]{32}',directory.name):
                    continue
                manifest=directory/'manifest.json'
                try:
                    data=json.loads(manifest.read_text(encoding='utf-8'))
                    if data.get('task_id')!=directory.name: continue
                    for entry in data.get('files',[]):
                        name=entry['name']
                        if Path(name).name!=name: continue
                        kind={'.docx':'word','.xlsx':'excel','.pptx':'slides'}.get(Path(name).suffix.lower())
                        if not kind: continue
                        file=directory/name
                        valid=file.is_file() and not file.is_symlink() and hashlib.sha256(file.read_bytes()).hexdigest()==entry['sha256']
                        items.append({'name':name,'task_id':directory.name,'created_at':data.get('created_at'),
                                      'kind':kind,'validated':valid,'url':f'/artifacts/{directory.name}/{kind}' if valid else None})
                except (OSError,ValueError,KeyError,TypeError):
                    continue
        for workspace in self.coding.list():
            task_dir=self.coding._directory(workspace['workspace_id'])/'tasks'
            if task_dir.is_symlink() or not task_dir.is_dir():
                continue
            for record in task_dir.glob('*.json'):
                try:
                    if record.is_symlink(): continue
                    data=json.loads(record.read_text(encoding='utf-8'))
                    for entry in data.get('output_files',[]):
                        try:
                            self.coding.artifact(workspace['workspace_id'],data['task_id'],entry['name'])
                            valid=True
                        except WorkbenchError:
                            valid=False
                        items.append({'name':entry['name'],'task_id':data['task_id'],
                                      'created_at':self.tasks.read(data['task_id']).get('created_at'),
                                      'kind':'code_result','validated':valid,
                                      'url':entry['url'] if valid else None})
                except (OSError,ValueError,KeyError,TypeError,WorkbenchError):
                    continue
        return sorted(items,key=lambda item:str(item.get('created_at') or ''),reverse=True)[:50]

    def delete_artifact(self, task_id, name):
        """Delete one catalogued output and remove only its catalog entry."""
        if not re.fullmatch(r'[a-f0-9]{32}',task_id) or Path(name).name!=name:
            raise WorkbenchError('unknown_artifact','Artifact does not exist')
        entry=next((item for item in self.artifact_catalog()
                    if item['task_id']==task_id and item['name']==name),None)
        if entry is None or not entry['validated']:
            raise WorkbenchError('unknown_artifact','Artifact does not exist or failed validation')
        if entry['kind']=='code_result':
            for workspace in self.coding.list():
                try:
                    result=self.coding.result(workspace['workspace_id'],task_id)
                    path=self.coding.artifact(workspace['workspace_id'],task_id,name)
                except WorkbenchError:
                    continue
                path.unlink()
                result['output_files']=[item for item in result['output_files'] if item['name']!=name]
                self.coding._save_result(workspace['workspace_id'],result)
                return
        else:
            directory=self.settings.data_dir.parent/'outputs'/task_id
            manifest=directory/'manifest.json'
            if directory.is_symlink() or manifest.is_symlink():
                raise WorkbenchError('artifact_invalid','Artifact path failed validation')
            metadata=json.loads(manifest.read_text(encoding='utf-8'))
            files=metadata.get('files',[])
            match=next((item for item in files if item.get('name')==name),None)
            path=directory/name
            if metadata.get('task_id')!=task_id or match is None or path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=match.get('sha256'):
                raise WorkbenchError('artifact_invalid','Artifact failed validation')
            path.unlink()
            metadata['files']=[item for item in files if item.get('name')!=name]
            temporary=directory/(uuid4().hex+'.tmp')
            try:
                temporary.write_text(json.dumps(metadata,indent=2),encoding='utf-8')
                temporary.replace(manifest)
            finally:
                temporary.unlink(missing_ok=True)
            return
        raise WorkbenchError('unknown_artifact','Artifact does not exist')
