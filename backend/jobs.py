"""Bounded in-process jobs for responsive local workspace interactions."""
import threading
import time
from queue import Queue
from uuid import uuid4
from backend.contracts import WorkbenchError

class Job:
    def __init__(self,kind):
        self.id=uuid4().hex;self.kind=kind;self.state='running';self.stage='Starting';self.output=''
        self.result=None;self.error=None;self.created=time.time();self.events=[];self.routing=None
        self.cancel=threading.Event();self.input=Queue(maxsize=32);self.lock=threading.Lock()
    def progress(self,stage):
        with self.lock:
            self.stage=stage;self.events.append({'stage':stage,'at':time.time()});self.events=self.events[-40:]
    def append(self,channel,text):
        with self.lock:
            self.output=(self.output+text)[-65536:]
            if self.kind in {'run','terminal'} and channel=='stdout' and self.output.rstrip().endswith((':','?')):
                self.stage='Waiting for program input'
    def snapshot(self):
        with self.lock:return {'job_id':self.id,'kind':self.kind,'state':self.state,'stage':self.stage,'output':self.output,'result':self.result,'error':self.error,'routing':self.routing,'events':list(self.events),'elapsed':round(time.time()-self.created,1)}

class Jobs:
    def __init__(self):self.jobs={};self.lock=threading.Lock()
    def get(self,id):
        with self.lock:job=self.jobs.get(id)
        if job is None:raise WorkbenchError('unknown_job','This job is no longer available')
        return job
    def start(self,kind,work):
        with self.lock:
            if any(j.state=='running' for j in self.jobs.values()):raise WorkbenchError('busy','Wait for the current workspace job or stop it first')
            self.jobs={k:j for k,j in self.jobs.items() if time.time()-j.created<3600}
            if len(self.jobs)>=20:self.jobs.pop(next(iter(self.jobs)))
            job=Job(kind);self.jobs[job.id]=job
        def run():
            try:
                result=work(job)
                with job.lock:
                    job.result=result;job.state='cancelled' if job.cancel.is_set() else 'failed' if result.get('state',result.get('status'))=='failed' else 'completed'
                    job.stage='Stopped' if job.state=='cancelled' else 'Finished' if job.state=='completed' else 'Check failed'
            except Exception as exc:
                with job.lock:job.state='cancelled' if job.cancel.is_set() else 'failed';job.error=str(exc);job.stage='Stopped' if job.state=='cancelled' else 'Could not finish'
        threading.Thread(target=run,daemon=True).start()
        return job.snapshot()
