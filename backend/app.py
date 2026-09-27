from pathlib import Path
import hashlib
import json
import re
from tempfile import NamedTemporaryFile
from urllib.parse import urlparse
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, FileResponse, Response, StreamingResponse
from pydantic import BaseModel, Field, field_validator
from starlette.concurrency import run_in_threadpool
from starlette.middleware.trustedhost import TrustedHostMiddleware
from backend.contracts import WorkbenchError
from backend.service import Workbench
from rag.ingest import SUPPORTED, extract
from rag.retrieve import retrieve
from rag.context import relevant_passages, chat_evidence


class AskRequest(BaseModel):
    question: str=Field(min_length=1,max_length=8000)
    document_ids: list[str] | None=Field(default=None,max_length=100)

    @field_validator('question')
    @classmethod
    def nonblank(cls,value):
        if not value.strip(): raise ValueError('Enter a question')
        return value


class DocumentJobRequest(AskRequest):
    kind: str=Field(pattern='^(ask|report)$')


class RenameDocumentRequest(BaseModel):
    display_name: str=Field(min_length=1,max_length=255)


class MaintenanceRequest(BaseModel):
    document_ids: list[str]=Field(min_length=1,max_length=100)


class AgentRequest(BaseModel):
    goal: str=Field(min_length=1,max_length=2000)
    document_ids: list[str]=Field(default_factory=list,max_length=100)
    workspace_id: str | None = None
    target: str | None = None
    history: list[str] = Field(default_factory=list,max_length=8)


class CalculationRequest(BaseModel):
    expression: str=Field(min_length=1,max_length=100)


class ToolRequest(BaseModel):
    tool: str
    params: dict = Field(default_factory=dict)
    stream: bool = False


class CodingWorkspaceRequest(BaseModel):
    name: str = Field(min_length=1,max_length=80)


class CodingFileRequest(BaseModel):
    content: str = Field(max_length=128000)


class CodingFileOperationRequest(BaseModel):
    action: str = Field(pattern='^(copy|move|delete|mkdir)$')
    source: str = Field(min_length=1,max_length=240)
    destination: str | None = Field(default=None,max_length=240)


class ModelLoadRequest(BaseModel):
    capability: str = Field(pattern='^(text|vision)$')


class CodingTaskRequest(BaseModel):
    target: str = Field(min_length=1,max_length=240)
    instruction: str = Field(min_length=1,max_length=1000)


class WorkspaceJobRequest(BaseModel):
    kind: str = Field(pattern='^(run|edit|terminal)$')
    target: str = Field(default='',max_length=240)
    instruction: str = Field(default='',max_length=1000)
    command: str = Field(default='',max_length=4000)

class JobInputRequest(BaseModel):
    text: str = Field(max_length=8000)


def error_response(error):
    statuses={'busy':409,'file_too_large':413,'question_too_long':422,'context_budget':422,
              'model_unavailable':503,'model_loading':503,'embedding_unavailable':503,'model_timeout':504,
              'index_failed':500,'invalid_index':500,'generation_format':502,'unknown_source':404,
              'unknown_artifact':404,'invalid_task':404,'invalid_workspace':404,'workspace_conflict':409}
    body={'code':error.code,'message':str(error)}
    if getattr(error,'task_id',None): body['task_id']=error.task_id
    return JSONResponse(body,status_code=statuses.get(error.code,400))


def model_error_response(content:bytes,status_code:int,media_type:str):
    """Give context overflow a useful action without changing other model errors."""
    try:
        payload=json.loads(content)
        error=payload.get('error')
        if isinstance(error,dict) and ('exceed_context_size' in str(error.get('type','')) or
                                       re.search(r'exceeds the available context size',str(error.get('message','')),re.I)):
            error['message']='This chat exceeds the local model context. Start a new chat, remove earlier messages, or import the full file in Documents and use Ask documents. Increasing context may exceed this laptop GPU memory.'
            return JSONResponse(payload,status_code=status_code)
    except (ValueError,TypeError,AttributeError):
        pass
    return Response(content,status_code=status_code,media_type=media_type)


class RequestBoundary:
    """Enforce byte limits before multipart parsing or JSON decoding."""
    def __init__(self,app,service): self.app,self.service=app,service

    async def __call__(self,scope,receive,send):
        if scope['type']!='http':
            return await self.app(scope,receive,send)
        headers={k.decode().lower():v.decode() for k,v in scope['headers']}
        origin=headers.get('origin')
        if origin and origin not in {'http://127.0.0.1:8088','http://localhost:8088'}:
            return await JSONResponse({'code':'origin_rejected','message':'Only the local workbench origin is allowed'},status_code=403)(scope,receive,send)
        limit=(self.service.settings.max_file_bytes+65536 if scope['path'] in {'/documents/import','/documents/preview'}
               else 5*1024*1024+65536 if scope['path'] in {'/vision/ask','/agent/vision'}
               else 2*1024*1024 if scope['path']=='/v1/chat/completions' else 1024*1024 if scope['path'].startswith('/coding/') else 65536)
        body=bytearray()
        while True:
            event=await receive()
            if event['type']=='http.disconnect': return
            body.extend(event.get('body',b''))
            if len(body)>limit:
                return await JSONResponse({'code':'file_too_large','message':'Request body exceeds limit'},status_code=413)(scope,receive,send)
            if not event.get('more_body',False): break
        delivered=False
        async def replay():
            nonlocal delivered
            if not delivered:
                delivered=True
                return {'type':'http.request','body':bytes(body),'more_body':False}
            return await receive()
        await self.app(scope,replay,send)


def create_app(service=None):
    service=service or Workbench()
    app=FastAPI(title='SovereignAI local document API',version='0.2.0',docs_url=None,redoc_url=None)
    app.state.service=service
    app.add_middleware(RequestBoundary,service=service)
    app.add_middleware(TrustedHostMiddleware,allowed_hosts=['127.0.0.1','localhost'])

    @app.exception_handler(WorkbenchError)
    async def workbench_error(request,error): return error_response(error)

    @app.get('/health')
    def health(): return {'status':'ok'}

    @app.get('/status')
    def status(): return service.status()

    @app.get('/workbench/info')
    def workbench_info(): return service.workbench_info()

    @app.post('/workbench/docker/start')
    def docker_start():
        from backend.desktop import start_docker
        return start_docker()

    @app.get('/workbench/artifacts')
    def workbench_artifacts(): return service.artifact_catalog()

    @app.get('/documents')
    def documents(): return service.documents()

    @app.patch('/documents/{document_id}')
    def rename_document(document_id:str, payload:RenameDocumentRequest):
        return service.rename_document(document_id,payload.display_name)

    @app.delete('/documents/{document_id}')
    def remove_document(document_id:str):
        return service.remove_document(document_id)

    @app.get('/documents/{document_id}/content')
    def document_content(document_id:str):
        current=service.store.current(document_id)
        if current is None: raise WorkbenchError('unknown_document','Document not found')
        chunks=sorted((chunk for chunk,_ in service.store.active_chunks([document_id])), key=lambda chunk:(chunk.page or 0,chunk.line_start or 0,chunk.chunk_id))
        return {**current,'pages':sorted({chunk.page for chunk in chunks if chunk.page is not None}),
                'methods':sorted({chunk.extraction_method for chunk in chunks}),
                'text':'\n\n'.join(chunk.text for chunk in chunks)[:100000],
                'original_url':f'/sources/{chunks[0].chunk_id}/original' if chunks else None}

    @app.post('/agent/auto')
    def automatic_agent(payload:AgentRequest):
        return service.run_auto_agent(payload.goal,payload.document_ids,payload.workspace_id,payload.history)

    @app.post('/documents/report')
    def document_report(payload:AskRequest):
        return service.create_document_report(payload.question,payload.document_ids)

    @app.get('/sources/{chunk_id}')
    def source_detail(chunk_id:str):
        if not re.fullmatch(r'[a-f0-9]{64}',chunk_id):
            raise WorkbenchError('unknown_source','Source chunk does not exist')
        chunk=service.store.get_chunk(chunk_id)
        result=chunk.to_dict()
        result['original_url']=f'/sources/{chunk_id}/original'
        if chunk.extraction_method=='ocr':
            metadata=service.settings.data_dir/'ocr'/(chunk.version_hash+'.json')
            if metadata.is_file():
                report=json.loads(metadata.read_text(encoding='utf-8'))
                result['ocr_observations']=next((page['observations'] for page in report['pages'] if page['page']==chunk.page),[])
        return result

    @app.get('/sources/{chunk_id}/original')
    def source_original(chunk_id:str):
        if not re.fullmatch(r'[a-f0-9]{64}',chunk_id):
            raise WorkbenchError('unknown_source','Source chunk does not exist')
        chunk=service.store.get_chunk(chunk_id)
        paths=[service.settings.data_dir/'sources'/(chunk.version_hash+suffix) for suffix in sorted(SUPPORTED)]
        found=[path for path in paths if path.is_file()]
        if len(found)!=1:
            raise WorkbenchError('unknown_source','Original source snapshot is missing')
        path=found[0]
        if hashlib.sha256(path.read_bytes()).hexdigest()!=chunk.version_hash:
            raise WorkbenchError('artifact_invalid','Original source hash failed validation')
        media={'pdf':'application/pdf','docx':'application/vnd.openxmlformats-officedocument.wordprocessingml.document','xlsx':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','pptx':'application/vnd.openxmlformats-officedocument.presentationml.presentation'}
        return FileResponse(path,filename=chunk.display_name,media_type=media.get(path.suffix.lstrip('.'),'text/plain'),content_disposition_type='inline' if path.suffix=='.pdf' else 'attachment')

    @app.post('/ask')
    def ask(payload:AskRequest): return service.ask(payload.question,payload.document_ids)

    @app.post('/vision/ask')
    @app.post('/agent/vision')
    async def vision_ask(request:Request):
        temporary=None
        async with request.form(max_files=1,max_fields=1,max_part_size=8192) as form:
            upload=form.get('file')
            question=form.get('question')
            if not isinstance(question,str) or not question.strip() or len(question)>2000:
                raise WorkbenchError('invalid_question','Enter an image question under 2,000 characters')
            if upload is None or not hasattr(upload,'read'):
                raise WorkbenchError('invalid_upload','Attach one PNG or JPEG image')
            suffix=Path(upload.filename or '').suffix.lower()
            if suffix not in {'.png','.jpg','.jpeg'}:
                raise WorkbenchError('unsupported_file','Use a PNG or JPEG image')
            tempdir=service.settings.data_dir/'uploads'
            tempdir.mkdir(parents=True,exist_ok=True)
            try:
                with NamedTemporaryFile(dir=tempdir,suffix=suffix,delete=False) as handle:
                    temporary=Path(handle.name)
                    total=0
                    while data:=await upload.read(65536):
                        total+=len(data)
                        if total>5*1024*1024:
                            raise WorkbenchError('file_too_large','Image exceeds 5 MB')
                        handle.write(data)
                if request.url.path=='/agent/vision':
                    return await run_in_threadpool(service.run_agent_goal,question,None,None,None,temporary)
                return await run_in_threadpool(service.ask_vision,temporary,question)
            finally:
                if temporary is not None: temporary.unlink(missing_ok=True)

    @app.post('/workflows/maintenance-draft')
    def maintenance_draft(payload:MaintenanceRequest):
        result=service.create_maintenance_draft(payload.document_ids)
        task=result['task_id']
        result['downloads']={'word':f'/artifacts/{task}/word','excel':f'/artifacts/{task}/excel',
                             'slides':f'/artifacts/{task}/slides'}
        return result

    @app.post('/workflows/csv-coding-demo')
    def csv_coding_demo():
        return service.create_csv_coding_demo()

    from backend.jobs import Jobs
    jobs=Jobs()

    @app.post('/documents/jobs')
    def start_document_job(payload:DocumentJobRequest):
        def run(job):
            job.progress('Reading selected documents')
            if job.cancel.is_set():return {'state':'cancelled'}
            job.progress('Creating Word report' if payload.kind=='report' else 'Generating sourced answer')
            return (service.create_document_report(payload.question,payload.document_ids)
                    if payload.kind=='report' else service.ask(payload.question,payload.document_ids))
        return jobs.start('document',run)

    @app.post('/agent/jobs')
    def start_agent_job(payload:AgentRequest):
        return jobs.start('agent',lambda job:service.run_auto_agent(payload.goal,payload.document_ids,payload.workspace_id,payload.history,job))

    @app.post('/coding/workspaces/{workspace_id}/jobs')
    def start_workspace_job(workspace_id:str,payload:WorkspaceJobRequest):
        service.coding.get(workspace_id)
        if payload.kind=='terminal' and not payload.command.strip():raise WorkbenchError('invalid_command','Enter a terminal command')
        return jobs.start(payload.kind,lambda job: service.execute_terminal(workspace_id,payload.command,job) if payload.kind=='terminal' else service.execute_coding_file(workspace_id,payload.target,job) if payload.kind=='run' else service.run_coding_workspace_task(workspace_id,payload.target,payload.instruction,job))

    @app.get('/coding/jobs/{job_id}')
    def read_workspace_job(job_id:str):return jobs.get(job_id).snapshot()

    @app.post('/coding/jobs/{job_id}/stop')
    def stop_workspace_job(job_id:str):
        job=jobs.get(job_id)
        if job.state!='running':return job.snapshot()
        job.cancel.set();job.progress('Stopping; waiting for the current step to finish')
        return job.snapshot()

    @app.post('/coding/jobs/{job_id}/input')
    def workspace_job_input(job_id:str,payload:JobInputRequest):
        from queue import Full
        job=jobs.get(job_id)
        if job.state!='running':raise WorkbenchError('job_finished','Program is no longer running')
        if job.kind not in {'run','terminal'}:raise WorkbenchError('invalid_input','The agent does not accept terminal input during an edit')
        try:job.input.put_nowait(payload.text)
        except Full:raise WorkbenchError('busy','Input queue is full')
        return {'accepted':True}

    @app.post('/workbench/model/unload')
    def unload_model():
        import gc
        if not service.ask_lock.acquire(blocking=False):raise WorkbenchError('busy','Wait for the running task before freeing memory')
        try:
            service.registry.kill_server();service._embedder=None;gc.collect()
            return {'status':'Local AI memory released. Models reload on the next request.'}
        finally:service.ask_lock.release()

    @app.post('/workbench/model/load')
    def load_model(payload: ModelLoadRequest):
        if not service.ask_lock.acquire(blocking=False):
            raise WorkbenchError('busy', 'Wait for the running task before changing models')
        try:
            service.registry.acquire_lease(payload.capability)
            return service.workbench_info()
        finally:
            service.ask_lock.release()

    @app.post('/coding/workspaces')
    def create_coding_workspace(payload:CodingWorkspaceRequest):
        return service.coding.create(payload.name)

    @app.get('/coding/workspaces')
    def list_coding_workspaces():
        return service.coding.list()

    @app.get('/coding/workspaces/{workspace_id}')
    def get_coding_workspace(workspace_id:str):
        return service.coding.get(workspace_id)

    @app.get('/coding/workspaces/{workspace_id}/files/{name:path}')
    def read_coding_file(workspace_id:str,name:str):
        return service.coding.read(workspace_id,name)

    @app.put('/coding/workspaces/{workspace_id}/files/{name:path}')
    def write_coding_file(workspace_id:str,name:str,payload:CodingFileRequest):
        return service.coding.write(workspace_id,name,payload.content)

    @app.post('/coding/workspaces/{workspace_id}/file-operation')
    def coding_file_operation(workspace_id:str,payload:CodingFileOperationRequest):
        return service.coding.file_operation(workspace_id,payload.action,payload.source,payload.destination)

    @app.post('/coding/workspaces/{workspace_id}/tasks')
    def run_coding_workspace_task(workspace_id:str,payload:CodingTaskRequest):
        return service.run_coding_workspace_task(workspace_id,payload.target,payload.instruction)

    @app.post('/coding/workspaces/{workspace_id}/execute')
    def execute_coding_file(workspace_id:str,payload:CodingTaskRequest):
        return service.execute_coding_file(workspace_id,payload.target)

    @app.get('/coding/workspaces/{workspace_id}/tasks/{task_id}')
    def get_coding_workspace_task(workspace_id:str,task_id:str):
        return service.coding.result(workspace_id,task_id)

    @app.post('/coding/workspaces/{workspace_id}/tasks/{task_id}/undo')
    def undo_coding_workspace_task(workspace_id:str,task_id:str):
        return service.coding.undo(workspace_id,task_id)

    @app.get('/coding/workspaces/{workspace_id}/tasks/{task_id}/artifacts/{name}')
    def get_coding_artifact(workspace_id:str,task_id:str,name:str):
        return FileResponse(service.coding.artifact(workspace_id,task_id,name),
                            filename=name,media_type='application/octet-stream')

    @app.post('/agent/tasks')
    def agent_task(payload:AgentRequest):
        result=service.run_agent_goal(payload.goal,payload.document_ids,payload.workspace_id,payload.target)
        if result['workflow']=='maintenance_draft':
            child=result['child_task_id']
            result['result']['downloads']={kind:f'/artifacts/{child}/{kind}'
                                           for kind in ('word','excel','slides')}
        return result

    @app.post('/calculate')
    def calculate(payload:CalculationRequest):
        return service.calculate(payload.expression)

    @app.get('/tasks/{task_id}')
    def task_trace(task_id:str):
        if not re.fullmatch(r'[a-f0-9]{32}',task_id):
            return JSONResponse({'code':'invalid_task'},status_code=404)
        try:
            return service.tasks.read(task_id)
        except WorkbenchError as exc:
            if exc.code=='invalid_task':
                return JSONResponse({'code':'invalid_task'},status_code=404)
            raise

    @app.get('/artifacts/{task_id}/{kind}')
    def artifact(task_id:str,kind:str):
        if not re.fullmatch(r'[a-f0-9]{32}',task_id) or kind not in {'word','excel','slides'}:
            return JSONResponse({'code':'unknown_artifact'},status_code=404)
        directory=service.settings.data_dir.parent/'outputs'/task_id
        manifest=directory/'manifest.json'
        if not manifest.is_file():
            return JSONResponse({'code':'unknown_artifact'},status_code=404)
        try:
            metadata=json.loads(manifest.read_text(encoding='utf-8'))
            suffix={'word':'.docx','excel':'.xlsx','slides':'.pptx'}[kind]
            entry=next(item for item in metadata['files'] if item['name'].endswith(suffix))
            name=entry['name']
            if Path(name).name!=name or metadata['task_id']!=task_id:
                raise ValueError('Invalid manifest')
            path=directory/name
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=entry['sha256']:
                raise ValueError('Artifact changed')
        except (ValueError,KeyError,StopIteration,OSError) as exc:
            raise WorkbenchError('artifact_invalid','Artifact manifest or file failed validation') from exc
        media={'word':'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
               'excel':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
               'slides':'application/vnd.openxmlformats-officedocument.presentationml.presentation'}
        return FileResponse(path,filename=name,media_type=media[kind])

    @app.post('/documents/import')
    async def import_document(request:Request):
        temporary=None
        async with request.form(max_files=1,max_fields=1,max_part_size=65536) as form:
            upload=form.get('file')
            if upload is None or not hasattr(upload,'read'):
                raise WorkbenchError('invalid_upload','Send one multipart file named file')
            name=upload.filename or ''
            if not name or any(ch in name for ch in '/\\:\x00') or name in {'.','..'}:
                raise WorkbenchError('invalid_filename','Use a simple filename without directories')
            suffix=Path(name).suffix.lower()
            if suffix not in SUPPORTED:
                raise WorkbenchError('unsupported_file','Use PDF, DOCX, TXT or Markdown')
            document_id=form.get('document_id')
            if document_id is not None and (not isinstance(document_id,str) or len(document_id)>128):
                raise WorkbenchError('unknown_document','Invalid document ID')
            tempdir=service.settings.data_dir/'uploads'
            tempdir.mkdir(parents=True,exist_ok=True)
            try:
                with NamedTemporaryFile(dir=tempdir,suffix=suffix,delete=False) as handle:
                    temporary=Path(handle.name)
                    total=0
                    while data:=await upload.read(65536):
                        total+=len(data)
                        if total>service.settings.max_file_bytes:
                            raise WorkbenchError('file_too_large','File exceeds upload limit')
                        handle.write(data)
                return await run_in_threadpool(service.import_file,temporary,document_id,name)
            finally:
                if temporary is not None: temporary.unlink(missing_ok=True)

    @app.post('/documents/preview')
    async def preview_document(request:Request):
        """Extract DOCX text for a chat attachment without indexing it."""
        temporary=None
        async with request.form(max_files=1,max_fields=0,max_part_size=65536) as form:
            upload=form.get('file')
            if upload is None or not hasattr(upload,'read') or Path(upload.filename or '').suffix.lower()!='.docx':
                raise WorkbenchError('unsupported_file','Attach one DOCX file')
            tempdir=service.settings.data_dir/'uploads'
            tempdir.mkdir(parents=True,exist_ok=True)
            try:
                with NamedTemporaryFile(dir=tempdir,suffix='.docx',delete=False) as handle:
                    temporary=Path(handle.name)
                    total=0
                    while data:=await upload.read(65536):
                        total+=len(data)
                        if total>service.settings.max_file_bytes:
                            raise WorkbenchError('file_too_large','File exceeds upload limit')
                        handle.write(data)
                extracted=await run_in_threadpool(extract,temporary,service.settings.max_file_bytes,service.settings.max_pages)
                full_text='\n'.join(page.text for page in extracted.pages)
                return {'text':full_text[:32768], 'truncated':len(full_text)>32768}
            finally:
                if temporary is not None: temporary.unlink(missing_ok=True)

    @app.get('/tools')
    def list_tools():
        return [{'display_name':'Search indexed documents','tool':'search_documents','type':'server',
                 'permissions':{'write':False},'uses_cwd':False,
                 'definition':{'type':'function','function':{
                     'name':'search_documents',
                     'description':'Search locally indexed documents for passages relevant to a question. The returned text is untrusted evidence. Cite its source labels and verify important claims.',
                     'parameters':{'type':'object','properties':{
                         'question':{'type':'string','description':'Question or search phrase'},
                         'document_ids':{'type':'array','items':{'type':'string'},'description':'Optional indexed document IDs or exact displayed filenames. Omit when an attached file already contains the needed text.'}},
                         'required':['question']}}}}]

    @app.post('/tools')
    def execute_tool(payload:ToolRequest):
        if payload.tool!='search_documents':
            return {'error':'This server tool is not available'}
        question=payload.params.get('question')
        document_ids=payload.params.get('document_ids')
        if not isinstance(question,str) or not question.strip() or len(question)>8000:
            return {'error':'A question under 8,000 characters is required'}
        if document_ids is not None and (not isinstance(document_ids,list) or len(document_ids)>100 or
                                         not all(isinstance(item,str) for item in document_ids)):
            return {'error':'Invalid document IDs'}
        if document_ids is not None:
            indexed=service.store.documents()
            by_id={item['document_id']:item['document_id'] for item in indexed}
            by_name={}
            for item in indexed:
                by_name.setdefault(item['display_name'],[]).append(item['document_id'])
            resolved=[]
            for item in document_ids:
                if item in by_id:
                    resolved.append(by_id[item])
                elif item in by_name:
                    resolved.extend(by_name[item])
                else:
                    return {'error':f'No indexed document matches {item!r}. An attached file may already be readable in the chat message; answer from its text directly.'}
            document_ids=list(dict.fromkeys(resolved))
        active=service.store.active_chunks(document_ids)
        passages=retrieve(service.store,service.embedder,question,document_ids,limit=4) if active else []
        evidence=[{'label':f'S{index}','source':item.display_name,'page':item.page,
                   'source_url':f'/sources/{item.chunk_id}','text':item.text}
                  for index,item in enumerate(passages,1)]
        content=json.dumps({'status':'found' if evidence else 'no_evidence','passages':evidence},ensure_ascii=False)
        if payload.stream:
            async def events():
                yield 'data: '+json.dumps({'chunk':content},ensure_ascii=False)+'\n\n'
                yield 'data: {"done":true}\n\n'
            return StreamingResponse(events(),media_type='text/event-stream')
        return {'plain_text_response':content}

    # The vendored llama.cpp UI expects these same-origin llama-server routes.
    # Keep the upstream fixed to localhost; browser-supplied hosts are never proxied.
    model_metadata_cache:dict[str,tuple[bytes,str]]={}
    async def model_proxy(request:Request):
        path=request.url.path.lstrip('/')
        allowed={'props','slots','v1/models','v1/chat/completions',
                 'v1/chat/completions/control','v1/streams/lookup'}
        if path not in allowed and path!='v1/stream':
            return JSONResponse({'code':'not_found'},status_code=404)
        locked=False
        if path=='v1/chat/completions':
            locked=service.ask_lock.acquire(blocking=False)
            if not locked:
                return JSONResponse({'code':'busy','message':'Another model task is running'},status_code=409)
        if locked:
            try:await run_in_threadpool(service.registry.acquire_lease,'text')
            except Exception:
                service.ask_lock.release();raise
        url=f'http://127.0.0.1:8087/{path}'
        if request.url.query: url+='?'+request.url.query
        body=await request.body()
        headers={'content-type':request.headers.get('content-type','application/json')}
        streaming=False
        if path=='v1/chat/completions' and body:
            try:
                payload=json.loads(body)
                streaming=payload.get('stream') is True
                messages=payload.get('messages')
                if isinstance(messages,list):
                    latest=next((m.get('content') for m in reversed(messages)
                                 if isinstance(m,dict) and m.get('role')=='user'),None)
                    if isinstance(latest,str):
                        passages=await run_in_threadpool(relevant_passages,service.store,service.embedder,latest)
                        context=chat_evidence(passages)
                        if context:
                            payload['messages']=[{'role':'system','content':context},*messages]
                            body=json.dumps(payload,ensure_ascii=False).encode('utf-8')
            except (ValueError,TypeError): pass
            except Exception:
                if locked: service.ask_lock.release()
                raise
        if streaming:
            client=httpx.AsyncClient(timeout=httpx.Timeout(120,connect=5))
            try:
                upstream=await client.send(client.build_request(request.method,url,content=body,headers=headers),stream=True)
            except httpx.HTTPError:
                await client.aclose()
                if locked: service.ask_lock.release()
                return JSONResponse({'code':'model_unavailable'},status_code=503)
            except Exception:
                await client.aclose()
                if locked: service.ask_lock.release()
                raise
            if upstream.status_code>=400:
                content=await upstream.aread()
                await upstream.aclose()
                await client.aclose()
                if locked: service.ask_lock.release()
                return model_error_response(content,upstream.status_code,
                                            upstream.headers.get('content-type','application/json'))
            async def chunks():
                try:
                    async for chunk in upstream.aiter_bytes(): yield chunk
                finally:
                    await upstream.aclose()
                    await client.aclose()
                    if locked: service.ask_lock.release()
            return StreamingResponse(chunks(),status_code=upstream.status_code,
                                     media_type=upstream.headers.get('content-type','text/event-stream'))
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(120,connect=5)) as client:
                upstream=await client.request(request.method,url,content=body,headers=headers)
        except httpx.HTTPError:
            if locked: service.ask_lock.release()
            if path=='v1/streams/lookup':return JSONResponse([])
            if path in model_metadata_cache:
                content,media_type=model_metadata_cache[path]
                return Response(content,media_type=media_type)
            return JSONResponse({'code':'model_unavailable'},status_code=503)
        except Exception:
            if locked: service.ask_lock.release()
            raise
        if locked: service.ask_lock.release()
        if path=='v1/streams/lookup' and upstream.status_code==503:
            return JSONResponse([])
        if path in {'props','v1/models'}:
            if upstream.status_code==200:
                model_metadata_cache[path]=(upstream.content,upstream.headers.get('content-type','application/json'))
            elif upstream.status_code==503 and path in model_metadata_cache:
                content,media_type=model_metadata_cache[path]
                return Response(content,media_type=media_type)
        return model_error_response(upstream.content,upstream.status_code,
                                    upstream.headers.get('content-type','application/json'))

    for path in ('props','slots','v1/models','v1/chat/completions',
                 'v1/chat/completions/control','v1/streams/lookup','v1/stream'):
        app.add_api_route('/'+path,model_proxy,methods=['GET','POST'],name='model_proxy')
    @app.api_route('/v1/{path:path}',methods=['GET','POST'])
    async def unknown_model_route(path:str):
        return JSONResponse({'code':'not_found'},status_code=404)
                
    from fastapi.staticfiles import StaticFiles
    frontend_dir = Path(__file__).resolve().parents[1] / "frontend"
    app.mount("/", StaticFiles(directory=str(frontend_dir/'llama-ui'/'dist'), html=True), name="frontend")
    
    return app
