from pathlib import Path
from contextlib import asynccontextmanager, contextmanager
import hashlib
import json
import re
from time import perf_counter
from router.telemetry import CURRENT_ROUTE, RoutingDecision
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
from backend.model import LocalModel
from router.telemetry import observe_completion, runtime_inference_seconds
from rag.ingest import SUPPORTED, extract
from rag.retrieve import retrieve
from rag.pdf_visuals import enrich_pdf_chunks
from workflows.coding_workspace import MAX_IMPORT_BYTES


_PRIVATE_COMPLETION_FIELDS = frozenset({'reasoning_content', 'reasoning', 'reasoningContent', 'thinking', 'thoughts'})

def _public_completion(value):
    """Never transport private model reasoning, including nested deltas."""
    if isinstance(value, dict):
        return {key: _public_completion(item) for key, item in value.items() if key not in _PRIVATE_COMPLETION_FIELDS}
    if isinstance(value, list):
        return [_public_completion(item) for item in value]
    return value

def _public_sse_line(line):
    if not line.startswith(b'data:'):
        return line
    raw = line[5:].strip()
    if raw == b'[DONE]':
        return line
    try:
        event = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        # Malformed private payloads must not bypass sanitization.
        if any(key.encode() in raw for key in _PRIVATE_COMPLETION_FIELDS):
            return b'data: {}' + (b'\r\n' if line.endswith(b'\r\n') else b'\n' if line.endswith(b'\n') else b'')
        return line
    public = _public_completion(event)
    if public == event:
        return line
    ending = b'\r\n' if line.endswith(b'\r\n') else b'\n' if line.endswith(b'\n') else b''
    return b'data: ' + json.dumps(public, ensure_ascii=False).encode('utf-8') + ending


class AskRequest(BaseModel):
    question: str=Field(min_length=1,max_length=8000)
    document_ids: list[str] | None=Field(default=None,max_length=256)
    history: list[str]=Field(default_factory=list,max_length=6)

    @field_validator('question')
    @classmethod
    def nonblank(cls,value):
        if not value.strip(): raise ValueError('Enter a question')
        return value


class DocumentJobRequest(AskRequest):
    kind: str=Field(pattern='^(ask|report)$')


class RenameDocumentRequest(BaseModel):
    display_name: str=Field(min_length=1,max_length=255)
    expected_hash: str | None=Field(default=None,max_length=128)


class MoveDocumentRequest(BaseModel):
    folder: str=Field(max_length=240)
    expected_hash: str | None=Field(default=None,max_length=128)


class CopyDocumentRequest(BaseModel):
    folder: str | None=Field(default=None,max_length=240)
    expected_hash: str | None=Field(default=None,max_length=128)


class MaintenanceRequest(BaseModel):
    document_ids: list[str]=Field(min_length=1,max_length=100)


class AgentRequest(BaseModel):
    goal: str=Field(min_length=1,max_length=8000)
    document_ids: list[str] | None=Field(default=None,max_length=256)
    workspace_id: str | None = None
    target: str | None = None
    history: list[str] = Field(default_factory=list,max_length=16)


class CalculationRequest(BaseModel):
    expression: str=Field(min_length=1,max_length=100)


class AutomationRequest(BaseModel):
    name: str=Field(min_length=1,max_length=80)
    goal: str=Field(min_length=1,max_length=2000)
    interval_seconds: int=Field(ge=60,le=31536000)
    workspace_id: str | None=None
    document_ids: list[str]=Field(default_factory=list,max_length=256)


class AutomationPauseRequest(BaseModel):
    paused: bool


class ToolRequest(BaseModel):
    tool: str
    params: dict = Field(default_factory=dict)
    stream: bool = False


class CodingWorkspaceRequest(BaseModel):
    name: str = Field(min_length=1,max_length=80)


class CodingFileRequest(BaseModel):
    content: str = Field(max_length=2*1024*1024)
    expected_sha256: str | None = Field(default=None,pattern='^([a-f0-9]{64})?$')


class CodingFileOperationRequest(BaseModel):
    action: str = Field(pattern='^(copy|move|delete|mkdir)$')
    source: str = Field(min_length=1,max_length=240)
    destination: str | None = Field(default=None,max_length=240)


class ModelLoadRequest(BaseModel):
    capability: str = Field(pattern='^(text|code|vision)$')


class CodingTaskRequest(BaseModel):
    target: str = Field(min_length=1,max_length=240)
    instruction: str = Field(min_length=1,max_length=1000)


class WorkspaceJobRequest(BaseModel):
    kind: str = Field(pattern='^(run|edit|terminal)$')
    target: str = Field(default='',max_length=240)
    instruction: str = Field(default='',max_length=1000)
    command: str = Field(default='',max_length=4000)
    cwd: str = Field(default='',max_length=240)

class JobInputRequest(BaseModel):
    text: str = Field(max_length=8000)


def error_response(error):
    statuses={'document_conflict':409,'busy':409,'file_too_large':413,'question_too_long':422,'context_budget':422,
              'model_unavailable':503,'model_loading':503,'embedding_unavailable':503,'model_timeout':504,
              'index_failed':500,'invalid_index':500,'generation_format':502,'unknown_source':404,
              'unknown_artifact':404,'invalid_task':404,'invalid_workspace':404,'workspace_conflict':409,'unknown_route':404}
    body={'code':error.code,'message':str(error)}
    if getattr(error,'routing',None):body['routing']={'decision':error.routing}
    if getattr(error,'task_id',None): body['task_id']=error.task_id
    return JSONResponse(body,status_code=statuses.get(error.code,400),
                        headers={'x-sovereign-request-id':error.routing['request_id']} if getattr(error,'routing',None) else {})


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
               else MAX_IMPORT_BYTES if scope['path'].startswith('/coding/workspaces/') and '/import-files/' in scope['path']
               else 5*1024*1024+65536 if scope['path'] in {'/vision/ask','/agent/vision','/agent/vision/jobs'}
               else 2*1024*1024 if scope['path']=='/v1/chat/completions'
               else 12*1024*1024 if scope['path'].startswith('/coding/workspaces/') and '/files/' in scope['path']
               else 1024*1024 if scope['path'].startswith('/coding/') else 65536)
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
    @asynccontextmanager
    async def lifespan(app):
        service.automations.start()
        try:yield
        finally:service.automations.stop()
    app=FastAPI(title='SovereignAI local document API',version='0.2.0',docs_url=None,redoc_url=None,lifespan=lifespan)
    app.state.service=service
    app.add_middleware(RequestBoundary,service=service)
    app.add_middleware(TrustedHostMiddleware,allowed_hosts=['127.0.0.1','localhost'])

    @app.exception_handler(WorkbenchError)
    async def workbench_error(request,error): return error_response(error)

    @app.get('/health')
    def health(): return {'status':'ok'}

    @app.get('/automations')
    def list_automations():return service.automations.list()

    @app.post('/automations')
    def create_automation(payload:AutomationRequest):
        return service.automations.create(**payload.model_dump())

    @app.patch('/automations/{identifier}')
    def pause_automation(identifier:str,payload:AutomationPauseRequest):
        return service.automations.change(identifier,paused=payload.paused)

    @app.delete('/automations/{identifier}')
    def delete_automation(identifier:str):
        return service.automations.change(identifier,delete=True)

    @app.get('/status')
    def status(): return service.status()

    @app.get('/routing/latest')
    def routing_latest():return service.routing_decision()

    @app.get('/routing/decisions/{request_id}')
    def routing_details(request_id:str):return service.routing_decision(request_id)

    @app.get('/workbench/info')
    def workbench_info(): return service.workbench_info()

    @app.post('/workbench/docker/start')
    def docker_start():
        from backend.desktop import start_docker
        return start_docker()

    @app.get('/workbench/artifacts')
    def workbench_artifacts(): return service.artifact_catalog()

    @app.delete('/workbench/artifacts/{task_id}/{name}')
    def delete_workbench_artifact(task_id: str, name: str):
        service.delete_artifact(task_id,name)
        return {'deleted':True}

    @app.get('/documents')
    def documents(): return service.documents()

    @app.patch('/documents/{document_id}')
    def rename_document(document_id:str, payload:RenameDocumentRequest):
        return service.rename_document(document_id,payload.display_name,payload.expected_hash)

    @app.delete('/documents/{document_id}')
    def remove_document(document_id:str,expected_hash:str | None=None):
        return service.remove_document(document_id,expected_hash)

    @app.post('/documents/{document_id}/move')
    def move_document(document_id:str,payload:MoveDocumentRequest):
        return service.move_document(document_id,payload.folder,payload.expected_hash)

    @app.post('/documents/{document_id}/copy')
    def copy_document(document_id:str,payload:CopyDocumentRequest):
        return service.copy_document(document_id,payload.folder,payload.expected_hash)

    @app.get('/documents/{document_id}/content')
    def document_content(document_id:str, offset:int=0, limit:int=100, chunk_id:str|None=None):
        if offset<0 or not 1<=limit<=200:
            raise WorkbenchError('invalid_request','Use a nonnegative passage offset and a limit from 1 to 200')
        current=service.store.current(document_id)
        if current is None: raise WorkbenchError('unknown_document','Document not found')
        chunks=sorted(enrich_pdf_chunks([chunk for chunk,_ in service.store.active_chunks([document_id])],service.sources_dir), key=lambda chunk:(chunk.page or 0,chunk.line_start or 0,chunk.chunk_id))
        if chunk_id is not None:
            index=next((i for i,chunk in enumerate(chunks) if chunk.chunk_id==chunk_id),None)
            if index is None:raise WorkbenchError('unknown_source','Passage is not part of this document')
            offset=(index//limit)*limit
        selected=chunks[offset:offset+limit]
        return {**current,'pages':sorted({chunk.page for chunk in chunks if chunk.page is not None}),
                'methods':sorted({chunk.extraction_method for chunk in chunks}),
                'passage_offset':offset,'passage_limit':limit,'passage_total':len(chunks),
                'passages':[{'chunk_id':chunk.chunk_id,'page':chunk.page,'text':chunk.text} for chunk in selected],
                'text':'\n\n'.join(chunk.text for chunk in selected)[:100000],
                'original_url':f'/documents/{document_id}/original'}

    @app.get('/documents/{document_id}/original')
    def document_original(document_id:str):
        path=service.document_original(document_id)
        return FileResponse(path,filename=service.store.current(document_id)['display_name'],
                            content_disposition_type='inline' if path.suffix=='.pdf' else 'attachment')

    @app.get('/documents/{document_id}/table')
    def document_table(document_id:str,sheet:int=0,offset:int=0,limit:int=100):
        from rag.tables import preview,TABULAR
        path=service.document_original(document_id)
        if path.suffix not in TABULAR: raise WorkbenchError('unsupported_file','This format has no worksheet preview')
        return preview(path,sheet,offset,limit)

    @app.get('/documents/{document_id}/table/find')
    def document_table_find(document_id:str,q:str,sheet:int|None=None,match_case:bool=False,whole_cell:bool=False,offset:int=0,limit:int=200):
        from rag.tables import find_cells,TABULAR
        path=service.document_original(document_id)
        if path.suffix not in TABULAR: raise WorkbenchError('unsupported_file','This format has no worksheet preview')
        return find_cells(path,q,sheet,match_case,whole_cell,offset,limit)

    @app.post('/agent/auto')
    def automatic_agent(payload:AgentRequest):
        return service.run_auto_agent(payload.goal,payload.document_ids,payload.workspace_id,payload.history)

    @app.post('/documents/report')
    def document_report(payload:AskRequest):
        return (service.create_document_report(payload.question,payload.document_ids,payload.history)
                if payload.history else service.create_document_report(payload.question,payload.document_ids))

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
        paths=[service.sources_dir/(chunk.version_hash+suffix) for suffix in sorted(SUPPORTED)]
        found=[path for path in paths if path.is_file()]
        if len(found)!=1:
            raise WorkbenchError('unknown_source','Original source snapshot is missing')
        path=found[0]
        if hashlib.sha256(path.read_bytes()).hexdigest()!=chunk.version_hash:
            raise WorkbenchError('artifact_invalid','Original source hash failed validation')
        media={'pdf':'application/pdf','docx':'application/vnd.openxmlformats-officedocument.wordprocessingml.document','xlsx':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','pptx':'application/vnd.openxmlformats-officedocument.presentationml.presentation'}
        return FileResponse(path,filename=chunk.display_name,media_type=media.get(path.suffix.lstrip('.'),'text/plain'),content_disposition_type='inline' if path.suffix=='.pdf' else 'attachment')

    @app.post('/ask')
    def ask(payload:AskRequest):
        return (service.ask(payload.question,payload.document_ids,payload.history)
                if payload.history else service.ask(payload.question,payload.document_ids))

    @app.post('/vision/ask')
    @app.post('/agent/vision')
    @app.post('/agent/vision/jobs')
    @app.post('/coding/workspaces/{workspace_id}/vision/jobs')
    async def vision_ask(request:Request):
        temporary=None
        job_owns_upload=False
        async with request.form(max_files=1,max_fields=2,max_part_size=8192) as form:
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
                if request.url.path=='/agent/vision/jobs' or 'workspace_id' in request.path_params:
                    image_path=temporary
                    workspace_id=request.path_params.get('workspace_id')
                    target=form.get('target')
                    if workspace_id:
                        service.coding.get(workspace_id)
                        if not isinstance(target,str) or not target.strip():
                            raise WorkbenchError('needs_input','Choose the code target')
                    def run(job):
                        try:
                            if workspace_id:
                                return service.run_coding_project_task(workspace_id,target,question,job=job,image_path=image_path)
                            return service.run_image_agent(question,image_path,job=job)
                        finally:
                            image_path.unlink(missing_ok=True)
                    result=jobs.start('agent',run)
                    job_owns_upload=True
                    return result
                if request.url.path=='/agent/vision':
                    return await run_in_threadpool(service.run_agent_goal,question,None,None,None,temporary)
                return await run_in_threadpool(service.ask_vision,temporary,question)
            finally:
                if temporary is not None and not job_owns_upload: temporary.unlink(missing_ok=True)

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

    @app.post('/workbench/docker/verify')
    def docker_verify():
        from backend.desktop import verify_docker
        return jobs.start('sandbox_verify', lambda job: verify_docker(service.settings.data_dir, job))

    @app.post('/documents/jobs')
    def start_document_job(payload:DocumentJobRequest):
        def run(job):
            job.progress('Preparing request')
            if job.cancel.is_set():return {'state':'cancelled'}
            if payload.kind=='report':
                return service.create_document_report(payload.question,payload.document_ids,payload.history,job=job)
            return service.ask(payload.question,payload.document_ids,payload.history,job=job)
        return jobs.start('document',run)

    @app.post('/agent/jobs')
    def start_agent_job(payload:AgentRequest):
        return jobs.start('agent',lambda job:service.run_auto_agent(payload.goal,payload.document_ids,payload.workspace_id,payload.history,job))

    @app.post('/coding/workspaces/{workspace_id}/jobs')
    def start_workspace_job(workspace_id:str,payload:WorkspaceJobRequest):
        service.coding.get(workspace_id)
        if payload.kind=='terminal' and not payload.command.strip():raise WorkbenchError('invalid_command','Enter a terminal command')
        return jobs.start(payload.kind,lambda job: service.execute_terminal(workspace_id,payload.command,job,cwd=payload.cwd) if payload.kind=='terminal' else service.execute_coding_file(workspace_id,payload.target,job) if payload.kind=='run' else service.run_coding_project_task(workspace_id,payload.target,payload.instruction,job))

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
        job.append('stdin', payload.text)
        job.progress('Input sent; program running')
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
            service._lease(payload.capability)
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

    @app.delete('/coding/workspaces/{workspace_id}')
    def delete_coding_workspace(workspace_id:str):
        return service.coding.delete(workspace_id)

    @app.post('/coding/workspaces/{workspace_id}/reveal')
    def reveal_coding_workspace(workspace_id:str):
        import os
        path=service.coding.files_directory(workspace_id)
        if os.name != 'nt':raise WorkbenchError('unsupported_platform','Open the project path using your system file manager')
        os.startfile(str(path))
        return {'host_path':str(path),'opened':True}

    @app.post('/coding/workspaces/{workspace_id}/open-vscode')
    def open_workspace_vscode(workspace_id:str):
        import os
        import subprocess
        path=service.coding.files_directory(workspace_id)
        if os.name != 'nt':raise WorkbenchError('unsupported_platform','Open this project path in your installed editor')
        candidates=[Path(os.environ.get('LOCALAPPDATA',''))/'Programs/Microsoft VS Code/Code.exe',
                    Path(os.environ.get('ProgramFiles','C:/Program Files'))/'Microsoft VS Code/Code.exe']
        executable=next((candidate for candidate in candidates if candidate.is_file()),None)
        if executable is None:raise WorkbenchError('editor_unavailable','Visual Studio Code is not installed in a supported location')
        subprocess.Popen([str(executable),'--new-window',str(path)],shell=False,
                         stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        return {'host_path':str(path),'opened':True}

    @app.get('/coding/workspaces/{workspace_id}/files/{name:path}')
    def read_coding_file(workspace_id:str,name:str):
        return service.coding.read(workspace_id,name)

    @app.post('/coding/workspaces/{workspace_id}/import-files/{name:path}')
    async def import_coding_file(workspace_id:str,name:str,request:Request):
        return await run_in_threadpool(service.coding.import_bytes,workspace_id,name,await request.body())

    @app.get('/coding/workspaces/{workspace_id}/assets/{name:path}')
    def coding_asset(workspace_id:str,name:str):
        path=service.coding._file(workspace_id,name)
        if not path.is_file():raise WorkbenchError('invalid_file','Workspace file does not exist')
        # Download disposition and nosniff prevent imported HTML/SVG scripts executing on our origin.
        return FileResponse(path,media_type='application/octet-stream',filename=path.name,
                            headers={'X-Content-Type-Options':'nosniff'})

    @app.put('/coding/workspaces/{workspace_id}/files/{name:path}')
    def write_coding_file(workspace_id:str,name:str,payload:CodingFileRequest):
        return (service.coding.write(workspace_id,name,payload.content,expected_sha256=payload.expected_sha256)
                if payload.expected_sha256 is not None else service.coding.write(workspace_id,name,payload.content))

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

    @app.post('/coding/workspaces/{workspace_id}/tasks/{task_id}/accept')
    def accept_coding_workspace_task(workspace_id:str,task_id:str):
        return service.accept_coding_task(workspace_id,task_id)

    @app.post('/coding/workspaces/{workspace_id}/tasks/{task_id}/discard')
    def discard_coding_workspace_task(workspace_id:str,task_id:str):
        return service.coding.discard(workspace_id,task_id)

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
    async def import_document(request:Request, background:bool=False):
        temporary=None
        async with request.form(max_files=1,max_fields=3,max_part_size=65536) as form:
            upload=form.get('file')
            if upload is None or not hasattr(upload,'read'):
                raise WorkbenchError('invalid_upload','Send one multipart file named file')
            name=upload.filename or ''
            if not name or any(ch in name for ch in '/\\:\x00') or name in {'.','..'}:
                raise WorkbenchError('invalid_filename','Use a simple filename without directories')
            suffix=Path(name).suffix.lower()
            if suffix not in SUPPORTED:
                raise WorkbenchError('unsupported_file','Use PDF, DOCX, XLSX, PPTX or a supported text/source file; export legacy binary formats as text or XLSX')
            document_id=form.get('document_id')
            if document_id is not None and (not isinstance(document_id,str) or len(document_id)>128):
                raise WorkbenchError('unknown_document','Invalid document ID')
            expected_hash=form.get('expected_hash')
            if expected_hash is not None and (not isinstance(expected_hash,str) or len(expected_hash)>128):
                raise WorkbenchError('document_conflict','Invalid version reference')
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
                if background:
                    received=await run_in_threadpool(service.receive_import,temporary,document_id,name,expected_hash)
                    identity=received['document_id']
                    worker_path=temporary
                    def run_import(job):
                        try:
                            return service.import_file(worker_path,identity,name,expected_hash,job=job)
                        except Exception as exc:
                            service.store.import_status(identity,'failed',str(exc))
                            raise
                        finally:
                            worker_path.unlink(missing_ok=True)
                    try: started=jobs.start('import',run_import)
                    except Exception as exc:
                        service.store.import_status(identity,'failed',str(exc))
                        raise
                    temporary=None  # The worker owns cleanup after a successful dispatch.
                    return {**started,'document':received}
                return await run_in_threadpool(service.import_file,temporary,document_id,name,expected_hash)
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
        # One explicit conversation identity; never proxy a global slot cancel.
        identity=request.headers.get('x-conversation-id')
        if path=='v1/stream':
            identities=request.query_params.getlist('conv_id')
            if len(identities)!=1:
                return JSONResponse({'code':'invalid_stream','message':'Supply one conversation identity'},status_code=400)
            identity=identities[0]
            offset=request.query_params.get('from')
            if offset is not None and (not offset.isascii() or not offset.isdigit() or len(offset)>19):
                return JSONResponse({'code':'invalid_stream','message':'Stream offset must be a nonnegative byte count'},status_code=400)
        if identity is not None and not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,255}',identity):
            return JSONResponse({'code':'invalid_stream','message':'Invalid conversation identity'},status_code=400)
        locked=False
        trace=None
        supervisor=None
        model_started=None
        body=await request.body()
        payload=None
        if path=='v1/chat/completions' and body:
            try:payload=json.loads(body)
            except (ValueError,TypeError):pass
        @contextmanager
        def proxy_context():
            from backend.task_supervisor import CURRENT_SUPERVISOR
            supervisor_token=CURRENT_SUPERVISOR.set(supervisor)
            route_token=CURRENT_ROUTE.set(trace)
            try:yield
            finally:
                CURRENT_ROUTE.reset(route_token)
                CURRENT_SUPERVISOR.reset(supervisor_token)
        def finish_proxy(result=None,error=None,code=None):
            if supervisor is None:return
            from router.task_completion import observe_completion as check_task_completion
            from backend.task_supervisor import TERMINAL_STAGES,_persist
            if supervisor.task_state['current_stage'] in TERMINAL_STAGES:return
            completion=check_task_completion(result or {})
            if error is not None:
                failure=code or getattr(error,'code','model_unavailable')
                completion={'state':'cancelled' if failure in {'cancelled','stream_cancelled'} else 'failed',
                            'achieved':False,'response_delivered':False,'checks':{},'limitations':[str(error)[:2000]]}
            supervisor.finish(completion,error if isinstance(error,Exception) else None)
            snapshot=supervisor.snapshot(completion)
            # Operational recording must not conceal the upstream/cancel error.
            try:_persist(service,snapshot)
            except OSError:pass
            if trace:
                trace.current_stage=snapshot['task_state']['current_stage']
                trace.completion_status=completion['state']
                trace.workflow=snapshot['task_state'].get('workflow')
                trace.worker_role=snapshot['task_state'].get('worker_role')
                trace.selected_tool=snapshot['task_state'].get('selected_tool')
        def record_error(error,code=None):
            finish_proxy(error=error,code=code)
            if trace:
                trace.errors.append({'code':code or getattr(error,'code','model_unavailable'),'message':str(error)})
                if model_started is not None:trace.model_request_time=perf_counter()-model_started
                trace.total_time=perf_counter()-trace._started
                if hasattr(service,'remember_route'):service.remember_route(trace.snapshot())
        def route_headers(response):
            if trace:response.headers['x-sovereign-request-id']=trace.request_id
            return response
        if path=='v1/chat/completions':
            messages=payload.get('messages',[]) if isinstance(payload,dict) else []
            image=isinstance(messages,list) and any(isinstance(message,dict) and isinstance(message.get('content'),list) and
                 any(isinstance(item,dict) and item.get('type')=='image_url' for item in message['content']) for message in messages)
            capability='vision' if image else 'text'
            trace=RoutingDecision(intent='conversation',modality='image' if image else 'text')
            trace.knowledge_scope={'connected':False,'mode':'off','permitted_document_count':0}
            trace.evidence_required=False
            trace.evidence_used=False
            trace.retrieval={'required':False,'status':'not_required','document_count':0,'passage_count':0,'candidate_count':0}
            trace.event('REQUEST_RECEIVED')
            latest=next((m.get('content','') for m in reversed(messages) if isinstance(m,dict) and m.get('role')=='user'),'')
            if isinstance(latest,list):latest=' '.join(item.get('text','') for item in latest if isinstance(item,dict) and item.get('type')=='text')
            from router.request_normalization import worker_role, normalize_request
            recent=[f"{item['role']}: {item['content']}" for item in messages[:-1]
                    if isinstance(item,dict) and item.get('role') in {'user','assistant'} and isinstance(item.get('content'),str)][-16:]
            trace.worker_role=worker_role(latest,image=image,history=recent)
            from backend.task_supervisor import TaskSupervisor,SupervisorLimits,_persist
            limits=getattr(service,'supervisor_limits',None) or SupervisorLimits()
            if isinstance(limits,dict):limits=SupervisorLimits(**limits)
            supervisor=TaskSupervisor(latest,{'workspace_id':None,'document_ids':[],
                                      'reference_history':[item[:1000] for item in recent]},limits)
            supervisor.worker_role=trace.worker_role
            supervisor.task_state['normalized_request']=normalize_request(latest).normalized
            supervisor.on_change=lambda current:_persist(service,current.snapshot())
            with proxy_context():
                supervisor.record_event('REQUEST_NORMALIZED',normalized_request=normalize_request(latest).normalized)
                supervisor.record_event('CAPABILITY_CLASSIFIED',intent='VISION' if image else 'GENERAL',
                                        workflow='CHAT',modality='image' if image else 'text',worker_role=trace.worker_role)
            trace.stages.append({'stage':'normalization','original_request':latest,'normalized_request':normalize_request(latest).normalized})
            trace.event('REQUEST_NORMALIZED')
            trace.event('CAPABILITY_CLASSIFIED')
            if isinstance(payload,dict):
                template_kwargs=payload.get('chat_template_kwargs')
                template_kwargs=dict(template_kwargs) if isinstance(template_kwargs,dict) else {}
                if not isinstance(template_kwargs.get('enable_thinking'),bool):template_kwargs['enable_thinking']=False
                payload['chat_template_kwargs']=template_kwargs
            classifier=getattr(service,'classifier',None)
            if classifier is not None:
                if isinstance(latest,str):
                    prediction=classifier.predict(latest,{'documents':False,'workspace':False,'image':image,'mode':'chat'})
                    trace.classification=prediction.to_dict()
                    trace.classifier_time=prediction.classifier_time_ms/1000
                    trace.event('CLASSIFICATION_COMPLETED')
            from rag.calculator import literal_expression
            expression=literal_expression(normalize_request(latest).normalized) if not image else None
            if expression is not None and callable(getattr(service,'calculate',None)):
                try:
                    with proxy_context():result=service.calculate(expression)
                except WorkbenchError as error:
                    finish_proxy(error=error)
                    trace.intent='calculate'
                    trace.failure_layer='tool_execution'
                    trace.errors.append({'code':error.code,'message':str(error)})
                    trace.total_time=perf_counter()-trace._started
                    if hasattr(service,'remember_route'):service.remember_route(trace.snapshot())
                    return route_headers(JSONResponse({'code':error.code,'message':str(error)},status_code=400))
                finish_proxy(result)
                trace.intent='calculate'
                trace.capability='calculation'
                trace.tool_candidates=[{'name':'calculator','status':'executed','reason':'Validated arithmetic syntax'}]
                trace.event('TOOL_COMPLETED')
                trace.total_time=perf_counter()-trace._started
                if hasattr(service,'remember_route'):service.remember_route(trace.snapshot())
                content=f"{result['expression']} = {result['result']}"
                if payload.get('stream'):
                    chunks=[{'id':trace.request_id,'object':'chat.completion.chunk','model':'calculator','choices':[{'index':0,'delta':{'role':'assistant','content':content},'finish_reason':None}]},
                            {'id':trace.request_id,'object':'chat.completion.chunk','model':'calculator','choices':[{'index':0,'delta':{},'finish_reason':'stop'}]}]
                    return route_headers(StreamingResponse(iter(['data: '+json.dumps(chunk)+'\n\n' for chunk in chunks]+['data: [DONE]\n\n']),media_type='text/event-stream'))
                return route_headers(JSONResponse({'id':trace.request_id,'object':'chat.completion','model':'calculator','choices':[{'index':0,'message':{'role':'assistant','content':content},'finish_reason':'stop'}]}))
            locked=service.ask_lock.acquire(blocking=False)
            if not locked:
                record_error('Another model task is running','busy')
                return route_headers(JSONResponse({'code':'busy','message':'Another model task is running'},status_code=409))
        if locked:
            def acquire_proxy_model():
                nonlocal capability
                with proxy_context():
                    supervisor.checkpoint()
                    if hasattr(service,'_lease'):selected=service._lease(capability)
                    else:service.registry.acquire_lease(capability)
                    # Native Chat shares the same semantic planner for potential
                    # code requests. This changes the generation model only;
                    # Chat never executes the planned action or edits files.
                    from router.tool_registry import explicit_operation_requested
                    planner=getattr(service.model,'plan_task',None)
                    if not image and callable(planner) and explicit_operation_requested(latest,'file_edit'):
                        recent=[f"{item['role']}: {item['content']}" for item in messages[-7:-1]
                                if isinstance(item,dict) and item.get('role') in {'user','assistant'} and isinstance(item.get('content'),str)]
                        intent=planner(latest,[],[],recent)
                        trace.stages.append({'stage':'intent','action':intent['action'],'source':'native_chat_planner'})
                        if intent['action']=='edit_code':
                            capability='code'
                            trace.intent='edit_code'
                            supervisor.record_event('CAPABILITY_CLASSIFIED',intent='CODE',workflow='CHAT',
                                                    current_action='generate_inline_code',worker_role='code')
                            selected=service._lease(capability)
                    # Use the selected runtime's chat template and tokenizer, not a
                    # character estimate. Image patch-token expansion remains unknown.
                    if isinstance(service.model,LocalModel) and isinstance(payload,dict):
                        budget=payload.get('max_completion_tokens',payload.get('max_tokens',1024))
                        if isinstance(budget,bool) or not isinstance(budget,int) or budget==0 or budget < -1:
                            raise WorkbenchError('invalid_request','Output token budget must be a positive integer or -1')
                        budget=4096 if budget==-1 else min(budget,4096)
                        if image:
                            trace.stages.append({'stage':'context','required_context':None,'output_budget':budget,
                                                 'condition':'Multimodal patch-token expansion is not measured'})
                        else:
                            for attempt in range(3):
                                prompt_tokens=service.model.count_messages(messages,payload)
                                required=prompt_tokens+budget+64
                                trace.required_context=required
                                trace.stages.append({'stage':'context','prompt_tokens':prompt_tokens,'output_budget':budget,'safety_tokens':64,'required_context':required,'source':'runtime_chat_template_tokenizer'})
                                admitted=service._lease(capability,required_context=required) if hasattr(service,'_lease') else None
                                if not hasattr(service,'_lease') or admitted==selected:break
                                selected=admitted
                            else:raise WorkbenchError('context_budget','Selected tokenizer/context did not stabilize; generation was not started')
                        if 'max_completion_tokens' in payload:payload['max_completion_tokens']=budget
                        else:payload['max_tokens']=budget
                        if 'max_tokens' in payload:payload['max_tokens']=budget
                        if trace.runtime_alias:payload['model']=trace.runtime_alias
            try:await run_in_threadpool(acquire_proxy_model)
            except BaseException as error:
                service.ask_lock.release()
                record_error(error,'stream_cancelled' if type(error).__name__=='CancelledError' else None)
                if isinstance(error,WorkbenchError):error.routing=trace.snapshot()
                raise
            if isinstance(payload,dict):body=json.dumps(payload,ensure_ascii=False).encode()
        url=f'http://127.0.0.1:8087/{path}'
        if request.url.query: url+='?'+request.url.query
        headers={'content-type':request.headers.get('content-type','application/json')}
        if path=='v1/chat/completions' and identity:
            headers['x-conversation-id']=identity
        streaming=path=='v1/stream' and request.method=='GET'
        if path=='v1/chat/completions' and body:
            try:
                payload=json.loads(body)
                streaming=payload.get('stream') is True
                # Ordinary Chat forwards only the supplied conversation.
                # Connected Knowledge uses /documents/jobs, whose intent-first
                # workflow owns scoped retrieval and citation validation.
            except (ValueError,TypeError): pass
            except Exception:
                if locked: service.ask_lock.release()
                raise
        if streaming:
            model_started=perf_counter()
            client=httpx.AsyncClient(timeout=httpx.Timeout(120,connect=5))
            try:
                with proxy_context():
                    if supervisor:
                        supervisor.consume('model_calls')
                        supervisor.record_event('GENERATION_STARTED')
                    upstream=await client.send(client.build_request(request.method,url,content=body,headers=headers),stream=True)
            except httpx.HTTPError as error:
                await client.aclose()
                if locked: service.ask_lock.release()
                record_error(error)
                return route_headers(JSONResponse({'code':'model_unavailable'},status_code=503))
            except BaseException as error:
                await client.aclose()
                if locked: service.ask_lock.release()
                record_error(error,'stream_cancelled' if type(error).__name__=='CancelledError' else None)
                raise
            if upstream.status_code>=400:
                content=await upstream.aread()
                try:content=json.dumps(_public_completion(json.loads(content)),ensure_ascii=False).encode('utf-8')
                except (ValueError,TypeError):
                    if any(key.encode() in content for key in _PRIVATE_COMPLETION_FIELDS):content=b'{"error":{"message":"Invalid model response"}}'
                await upstream.aclose()
                await client.aclose()
                if locked: service.ask_lock.release()
                record_error(content.decode(errors='replace'),'upstream_'+str(upstream.status_code))
                return route_headers(model_error_response(content,upstream.status_code,
                                            upstream.headers.get('content-type','application/json')))
            async def chunks():
                pending=''
                transport_pending=b''
                finished=False
                delivered=False
                incomplete=False
                try:
                    with proxy_context():
                        async for chunk in upstream.aiter_bytes():
                            if supervisor:supervisor.checkpoint()
                            if trace:
                                pending+=chunk.decode('utf-8',errors='replace')
                                lines=pending.split('\n');pending=lines.pop()
                                for line in lines:
                                    if line.startswith('data:'):
                                        if line[5:].strip()=='[DONE]':finished=True
                                        try:
                                            event=json.loads(line[5:])
                                            if any(choice.get('finish_reason')=='stop' for choice in event.get('choices',[]) if isinstance(choice,dict)):finished=True
                                            if event.get('error'):incomplete=True
                                            for choice in event.get('choices',[]):
                                                if not isinstance(choice,dict):continue
                                                if choice.get('finish_reason') not in (None,'stop'):incomplete=True
                                                delta=choice.get('delta',{})
                                                if isinstance(delta,dict) and isinstance(delta.get('content'),str) and delta['content']:delivered=True
                                            timings=event.get('timings',{})
                                            inference_seconds=runtime_inference_seconds(timings)
                                            if inference_seconds is not None:trace.inference_time=inference_seconds
                                        except (ValueError,AttributeError):pass
                            transport_pending+=chunk
                            while b'\n' in transport_pending:
                                line,transport_pending=transport_pending.split(b'\n',1)
                                yield _public_sse_line(line+b'\n')
                            if len(transport_pending)>1048576:
                                raise WorkbenchError('generation_format','Model stream event exceeded the supported size')
                        if transport_pending:yield _public_sse_line(transport_pending)
                    if supervisor:
                        finish_proxy({'status':'answered','answer':'Stream response delivered' if delivered else ''}) if finished and not incomplete else record_error('The model stream ended without a complete response','generation_format')
                except BaseException as error:
                    record_error(error,'stream_cancelled' if type(error).__name__=='CancelledError' else 'stream_error')
                    raise
                finally:
                    await upstream.aclose()
                    await client.aclose()
                    if locked: service.ask_lock.release()
                    if trace:
                        trace.model_request_time=perf_counter()-model_started
                        trace.total_time=perf_counter()-trace._started
                        if hasattr(service,'remember_route'):service.remember_route(trace.snapshot())
            return StreamingResponse(chunks(),status_code=upstream.status_code,
                                     media_type=upstream.headers.get('content-type','text/event-stream'),
                                     headers={'x-sovereign-request-id':trace.request_id} if trace else {})
        model_started=perf_counter()
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(120,connect=5)) as client:
                with proxy_context():
                    if supervisor:
                        supervisor.consume('model_calls')
                        supervisor.record_event('GENERATION_STARTED')
                    upstream=await client.request(request.method,url,content=body,headers=headers)
        except httpx.HTTPError as error:
            if locked: service.ask_lock.release()
            record_error(error)
            if path=='v1/streams/lookup':return JSONResponse([])
            if path in model_metadata_cache:
                content,media_type=model_metadata_cache[path]
                return Response(content,media_type=media_type)
            return route_headers(JSONResponse({'code':'model_unavailable'},status_code=503))
        except BaseException as error:
            if locked: service.ask_lock.release()
            record_error(error,'stream_cancelled' if type(error).__name__=='CancelledError' else None)
            raise
        if locked: service.ask_lock.release()
        response_content=upstream.content
        if path=='v1/chat/completions':
            try:
                raw_completion=upstream.json()
                public_completion=_public_completion(raw_completion)
                if public_completion!=raw_completion:response_content=json.dumps(public_completion,ensure_ascii=False).encode('utf-8')
            except (ValueError,TypeError):
                if any(key.encode() in response_content for key in _PRIVATE_COMPLETION_FIELDS):response_content=b'{"error":{"message":"Invalid model response"}}'
        if trace:
            if upstream.status_code>=400:trace.errors.append({'code':'upstream_'+str(upstream.status_code),'message':response_content.decode(errors='replace')[:2000]})
            token=CURRENT_ROUTE.set(trace)
            try:
                try:completion=json.loads(response_content)
                except (ValueError,TypeError):completion={}
                observe_completion(completion,perf_counter()-model_started)
            finally:CURRENT_ROUTE.reset(token)
            trace.total_time=perf_counter()-trace._started
            if upstream.status_code>=400:
                finish_proxy(error=response_content.decode(errors='replace'),code='upstream_'+str(upstream.status_code))
            else:
                choices=completion.get('choices',[]) if isinstance(completion,dict) else []
                text=next((choice.get('message',{}).get('content') for choice in choices if isinstance(choice,dict) and isinstance(choice.get('message'),dict)),'')
                if isinstance(completion,dict) and completion.get('error') or any(
                        choice.get('finish_reason') not in (None,'stop') for choice in choices if isinstance(choice,dict)):
                    finish_proxy(error='The model response was incomplete',code='generation_format')
                else:finish_proxy({'status':'answered','answer':text if isinstance(text,str) else ''})
            if hasattr(service,'remember_route'):service.remember_route(trace.snapshot())
        if path=='v1/streams/lookup' and upstream.status_code==503:
            return JSONResponse([])
        if path in {'props','v1/models'}:
            if upstream.status_code==200:
                model_metadata_cache[path]=(upstream.content,upstream.headers.get('content-type','application/json'))
            elif upstream.status_code==503 and path in model_metadata_cache:
                content,media_type=model_metadata_cache[path]
                return Response(content,media_type=media_type)
        response=model_error_response(response_content,upstream.status_code,
                                    upstream.headers.get('content-type','application/json'))
        if trace:response.headers['x-sovereign-request-id']=trace.request_id
        return response

    for path in ('props','slots','v1/models','v1/chat/completions',
                 'v1/chat/completions/control','v1/streams/lookup','v1/stream'):
        app.add_api_route('/'+path,model_proxy,methods=['GET','DELETE'] if path=='v1/stream' else ['GET','POST'],name='model_proxy')
    @app.api_route('/v1/{path:path}',methods=['GET','POST'])
    async def unknown_model_route(path:str):
        return JSONResponse({'code':'not_found'},status_code=404)
                
    from fastapi.staticfiles import StaticFiles
    frontend_dir = Path(__file__).resolve().parents[1] / "frontend"
    app.mount("/", StaticFiles(directory=str(frontend_dir/'llama-ui'/'dist'), html=True), name="frontend")
    
    return app
