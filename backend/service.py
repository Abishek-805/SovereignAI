from pathlib import Path
from uuid import uuid4
from dataclasses import asdict
import hashlib
import json
import os
import re
import threading
import time
from backend.contracts import WorkbenchError
from backend.settings import Settings
from backend.model import LocalModel
from rag.embedding import Embedder
from rag.ingest import extract, chunk_pages, SUPPORTED
from rag.store import Store
from rag.retrieve import retrieve
from rag.context import relevant_passages, chat_evidence
from rag.answer import answer
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
        self.store=store or Store(self.settings.data_dir/'index.sqlite',self.settings.max_chunks)
        self._embedder=embedder
        self.model=model or LocalModel(self.settings.model_url)
        self.registry=registry or ModelRegistry(8087)
        self.router=CapabilityRouter(self.registry)
        self.tasks=TaskLedger(self.settings.data_dir)
        self.coding=CodingWorkspace(self.settings.data_dir)
        self.ask_lock=threading.Lock()
        self.import_lock=threading.Lock()
        self.embedding_lock=threading.Lock()

    @property
    def embedder(self):
        with self.embedding_lock:
            if self._embedder is None:
                self._embedder=Embedder(self.settings.model_dir)
            return self._embedder

    def documents(self):
        return self.store.documents()

    def rename_document(self, document_id, display_name):
        with self.import_lock:
            return self.store.rename_document(document_id, display_name)

    def remove_document(self, document_id):
        with self.import_lock:
            return self.store.remove_document(document_id)

    def import_file(self,path,document_id=None,display_name=None):
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
            if current and current['active_hash']==digest:
                return {'status':'unchanged',**current}
            sources=self.settings.data_dir/'sources'
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

    def ask(self,question,document_ids=None):
        if not isinstance(question,str) or not question.strip():
            raise WorkbenchError('invalid_question','Enter a question')
        if len(question)>8000:
            raise WorkbenchError('question_too_long','Question exceeds 8000 characters')
        if not self.ask_lock.acquire(blocking=False):
            raise WorkbenchError('busy','Another answer is being generated')
        try:
            started=time.perf_counter()
            # Validate filters even for an empty collection, without loading embeddings.
            active=self.store.active_chunks(document_ids)
            passages=retrieve(self.store,self.embedder,question,document_ids) if active else []
            retrieval_seconds=time.perf_counter()-started
            
            # Switch to text model if needed
            switch_start = time.perf_counter()
            route=self.router.route_request('text')
            self.registry.acquire_lease(route)
            switch_latency = time.perf_counter() - switch_start
            
            result=answer(question,passages,self.model,self.settings.context,self.settings.output_tokens,self.settings.safety_tokens)
            result['task_id']=uuid4().hex
            result['routing']={'capability':route,'model':self.registry.specs[route].alias if hasattr(self.registry,'specs') else 'sovereign-text'}
            result['timings'].update(
                retrieval_seconds=retrieval_seconds,
                switch_latency=switch_latency,
                total_seconds=time.perf_counter()-started
            )
            answers=self.settings.data_dir/'answers'
            answers.mkdir(parents=True,exist_ok=True)
            (answers/(result['task_id']+'.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
            return result
        finally:
            self.ask_lock.release()

    def ask_vision(self, image_path, question):
        if not isinstance(question,str) or not question.strip():
            raise WorkbenchError('invalid_question','Enter a question')
        if not self.ask_lock.acquire(blocking=False):
            raise WorkbenchError('busy','Another answer is being generated')
        try:
            started=time.perf_counter()
            from PIL import Image, UnidentifiedImageError
            try:
                with Image.open(image_path) as source:
                    if source.width * source.height > 12_000_000:
                        raise WorkbenchError('file_too_large','Image exceeds the pixel limit')
                    img=source.convert('RGB')
            except (UnidentifiedImageError,OSError) as exc:
                raise WorkbenchError('invalid_upload','Image could not be decoded') from exc
            
            switch_start = time.perf_counter()
            route=self.router.route_request('vision')
            self.registry.acquire_lease(route)
            switch_latency = time.perf_counter() - switch_start
            
            result = ask_vision(img, question)
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
            self.registry.acquire_lease(self.router.route_request('code'))
            return run_csv_demo(self.model,sandbox,self.tasks,self.settings)
        finally:
            self.ask_lock.release()

    def run_coding_workspace_task(self, workspace_id, target, instruction, job=None):
        if not self.ask_lock.acquire(blocking=False):
            raise WorkbenchError('busy','Another task is running')
        try:
            sandbox=self._verified_coding_sandbox()
            capability=self.router.route_request('code')
            if job:job.progress('Loading local model');sandbox.on_output=job.append;sandbox.cancel_event=job.cancel
            self.registry.acquire_lease(capability)
            specs=getattr(self.registry,'specs',{})
            alias=specs[capability].alias if capability in specs else 'sovereign-text'
            return self.coding.run(workspace_id,target,instruction,self.model,sandbox,self.tasks,
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
            files = {item['name']: self.coding.read(workspace_id,item['name'])['content'].encode('utf-8')
                     for item in self.coding.get(workspace_id)['files']}
            if job:
                job.progress('Starting isolated program');sandbox.on_output=job.append;sandbox.cancel_event=job.cancel;sandbox.stdin_queue=job.input
            script = runner(target, mode='run')
            task = self.tasks.create('workspace_execution', [])
            self.tasks.step(task, 'docker_run', {'target':target})
            execution = sandbox.execute(script,input_files=files)
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

    def execute_terminal(self, workspace_id, command, job):
        if not self.ask_lock.acquire(blocking=False):raise WorkbenchError('busy','Another task is running')
        try:
            sandbox=self._verified_coding_sandbox()
            files={item['name']:self.coding.read(workspace_id,item['name'])['content'].encode('utf-8') for item in self.coding.get(workspace_id)['files']}
            sandbox.on_output=job.append;sandbox.cancel_event=job.cancel;sandbox.stdin_queue=job.input
            job.progress('Terminal running in Docker')
            script="import os,shutil,subprocess,sys\nshutil.copytree('/input','/output/project',ignore=shutil.ignore_patterns('program.py'))\nos.chdir('/output/project')\nsys.exit(subprocess.call(['bash','--noprofile','--norc','-c',"+repr(command)+"]))"
            result=sandbox.execute(script,input_files=files)
            return {'state':'completed' if result.exit_code==0 else 'failed','exit_code':result.exit_code,'stdout':result.stdout,'stderr':result.stderr}
        finally:self.ask_lock.release()

    def calculate(self,expression):
        from rag.calculator import evaluate_expression
        if not isinstance(expression,str) or len(expression)>100 or not re.fullmatch(r'[0-9.\s()+\-*/]+',expression):
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

    def create_document_report(self, question, document_ids):
        from workflows.document_report import publish_report
        task=self.tasks.create('document_report',document_ids or [])
        try:
            self.tasks.step(task,'read_documents',{})
            result=self.ask(question,document_ids)
            self.tasks.step(task,'export_word',{'sources':len(result.get('sources',[]))})
            downloads=publish_report(self.settings,task['task_id'],question,result)
            self.tasks.complete(task,{'grounded_answer':True,'word_readback':True})
            return {**result,'task_id':task['task_id'],'downloads':downloads}
        except Exception:
            self.tasks.fail(task,'report_failed')
            raise

    def run_auto_agent(self, goal, document_ids=None, workspace_id=None, history=None, job=None):
        """Infer the workflow and source target; callers need only a request and optional context."""
        if job:job.progress('Reading task context')
        task=self.tasks.create('automatic_task',document_ids or [])
        try:
            docs=self.documents()
            if document_ids:
                self.store.active_chunks(document_ids)  # validate IDs before model planning
                docs=[doc for doc in docs if doc['document_id'] in document_ids]
            rag_passages = relevant_passages(self.store,self.embedder,goal,document_ids,limit=2) if docs else []
            rag_notes = chat_evidence(rag_passages)
            files=self.coding.get(workspace_id)['files'] if workspace_id else []
            planning_files=[]
            remaining=10000
            for file in files:
                content=self.coding.read(workspace_id,file['name'])['content'] if remaining else ''
                snippet=content[:remaining]
                planning_files.append({'name':file['name'],'source_excerpt':snippet,'excerpt_complete':len(snippet)==len(content) if remaining else False})
                remaining-=len(snippet)
            self.tasks.step(task,'plan',{'workspace':workspace_id,'documents':len(docs)})
            if not self.ask_lock.acquire(blocking=False): raise WorkbenchError('busy','Another model task is running')
            try:
                self.registry.acquire_lease(self.router.route_request('code' if workspace_id else 'text'))
                if job:job.progress('Choosing the next action')
                planning_history=[str(item)[:1000] for item in (history or [])[-7:]]
                if rag_notes: planning_history.append(rag_notes[:1000])
                plan=self.model.plan_task(goal,[doc['display_name'] for doc in docs[:50]], planning_files,
                                          planning_history)
            finally:
                self.ask_lock.release()
            if plan['action']=='answer' and (document_ids or rag_passages):
                plan['action']='search_documents'
            if plan['action']!='answer':
                plan['response']={'calculate':'Evaluate the expression with the local calculator.','edit_code':'Edit the selected source and validate it in Docker.','search_documents':'Retrieve evidence from the indexed documents.','create_report':'Retrieve evidence and export a cited Word report.'}[plan['action']]
            self.tasks.step(task,plan['action'],{'target':plan['target'],'plan':plan['response'][:500]})
            scope=document_ids or [doc['document_id'] for doc in docs]
            if job:
                if job.cancel.is_set():raise WorkbenchError('cancelled','Task stopped before tool execution')
                job.progress(plan['response'] if plan['action']!='answer' else 'Writing answer')
            action=plan['action']
            if action=='answer': result={'answer':plan['response'],'status':'answered'}
            elif action=='calculate': result=self.calculate(plan['expression'])
            elif action=='search_documents': result=self.ask(goal,scope)
            elif action=='create_report': result=self.create_document_report(goal,scope)
            elif action=='edit_code':
                self._verified_coding_sandbox()
                target=self.coding._name(plan['target'])
                if not workspace_id:
                    workspace_id=self.coding.create(goal[:80])['workspace_id']
                current=self.coding.get(workspace_id)
                if target not in {file['name'] for file in current['files']}:
                    self.coding.write(workspace_id,target,'')
                instruction=(goal+'\n\nRelevant indexed knowledge (untrusted reference; verify before using):\n'+rag_notes[:700]) if rag_notes else goal
                result=self.run_coding_workspace_task(workspace_id,target,instruction[:1000],job=job)
            checks={'workflow_returned':True,'workflow_succeeded':result.get('state')!='failed'}
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
                'host':'127.0.0.1','network_proof':'not assessed by this status endpoint'}

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
