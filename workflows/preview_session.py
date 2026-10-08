"""Short-lived Flask preview sessions inside the unchanged Docker sandbox."""
import atexit,json,queue,threading,time
from uuid import uuid4
from backend.contracts import WorkbenchError
from router.sandbox import CodeSandbox

_sessions={};_lock=threading.Lock()

class PreviewSession:
    def __init__(self,sandbox,script,files,database):
        self.queue=queue.Queue();self.responses=queue.Queue();self.buffer=''
        self.database=database;self.last_used=time.monotonic();self.started=self.last_used
        self.calls=0;self.bytes=0;self.closed=False;self.inflight=False;self.request_lock=threading.Lock()
        self.worker=CodeSandbox(sandbox.backend_type,sandbox.image_id,sandbox.task_root,sandbox.docker_cli)
        self.worker.stdin_queue=self.queue;self.worker.on_output=self.output
        self.worker.cancel_event=threading.Event()
        self.thread=threading.Thread(target=self.run,args=(script,files),daemon=True);self.thread.start()
        threading.Thread(target=self.expire,daemon=True).start()
    def output(self,channel,text):
        if channel!='stdout':return
        self.buffer+=text
        while '\n' in self.buffer:
            line,self.buffer=self.buffer.split('\n',1)
            if line.startswith('SOVEREIGN_PREVIEW:'):
                try:self.responses.put(json.loads(line.split(':',1)[1]))
                except ValueError:pass
    def run(self,script,files):
        try:
            result=self.worker.execute(script,timeout=120,input_files=files)
            if result.output_files.get('preview-state.db'):
                self.database.write_bytes(result.output_files['preview-state.db'])
            if result.exit_code!=0:self.responses.put({'error':result.stderr[-4000:] or 'Docker preview stopped'})
        except Exception as error:self.responses.put({'error':str(error)})
        finally:self.closed=True
    def close(self):
        self.queue.put(json.dumps({'stop':True})+'\n')
        self.thread.join(timeout=8)
        if self.thread.is_alive():
            self.worker.cancel_event.set();self.thread.join(timeout=8)
    def expire(self):
        while not self.closed:
            time.sleep(1)
            if (not self.inflight and time.monotonic()-self.last_used>20) or time.monotonic()-self.started>105:
                self.close();return
    def request(self,payload):
        with self.request_lock:
            self.last_used=time.monotonic();self.calls+=1;self.inflight=True
            request_id=uuid4().hex
            self.queue.put(json.dumps({**payload,'request_id':request_id})+'\n')
            try:response=self.responses.get(timeout=35)
            except queue.Empty:
                self.worker.cancel_event.set();self.closed=True
                raise WorkbenchError('preview_failed','Docker preview did not respond within its bounded time')
            finally:self.inflight=False;self.last_used=time.monotonic()
            if response.get('error'):raise WorkbenchError('preview_failed',response['error'])
            if response.pop('request_id',None)!=request_id:
                self.worker.cancel_event.set();self.closed=True
                raise WorkbenchError('preview_failed','Docker preview response did not match this interaction')
            response=json.loads(self.worker.read_active_output('web-response.json'))
            if response.pop('request_id',None)!=request_id:
                raise WorkbenchError('preview_failed','Docker preview body did not match this interaction')
            self.bytes+=len(json.dumps(response).encode());return response

def session_request(key,sandbox,script,files,database,payload):
    with _lock:
        session=_sessions.get(key)
        if session and (session.closed or session.calls>=128):
            session.close();_sessions.pop(key,None);session=None
        if session is None:
            # One preview worker, exact immutable workspace/revision/entrypoint.
            for old in _sessions.values():old.close()
            _sessions.clear()
            if database.exists():files={**files,'__preview_state__.db':database.read_bytes()}
            session=PreviewSession(sandbox,script,files,database);_sessions[key]=session
        # Keep ownership until the response is consumed. A different revision
        # or workspace must not close this worker during an active interaction.
        return session.request(payload)

def close_sessions():
    with _lock:
        for session in _sessions.values():session.close()
        _sessions.clear()
atexit.register(close_sessions)
