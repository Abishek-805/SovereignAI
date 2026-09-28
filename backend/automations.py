"""Persisted interval tasks owned by this application, with a single bounded worker."""
import json
import threading
import time
from uuid import uuid4
from backend.contracts import WorkbenchError
from backend.jobs import Job


class Automations:
    def __init__(self, service):
        self.service = service
        self.path = service.settings.data_dir / 'automations.json'
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.thread = None
        self.active_job = None
        self.items = json.loads(self.path.read_text(encoding='utf-8')) if self.path.is_file() else []

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps(self.items, ensure_ascii=False), encoding='utf-8')
        temporary.replace(self.path)

    def list(self):
        with self.lock:return json.loads(json.dumps(self.items))

    def create(self, name, goal, interval_seconds, workspace_id=None, document_ids=None):
        if not isinstance(interval_seconds, int) or not 60 <= interval_seconds <= 31536000 or not name.strip() or not goal.strip() or len(goal) > 2000:
            raise WorkbenchError('tool_input', 'Specify a recurring goal and interval of at least 60 seconds')
        if workspace_id:self.service.coding.get(workspace_id)
        with self.lock:
            if len(self.items) >= 32:raise WorkbenchError('resource_limit', 'At most 32 recurring tasks are supported')
            entry={'id':uuid4().hex, 'name':name[:80], 'goal':goal, 'interval_seconds':interval_seconds,
                   'workspace_id':workspace_id, 'document_ids':list(document_ids or []), 'paused':False,
                   'next_run':time.time()+interval_seconds, 'last_run':None, 'last_result':None, 'last_error':None}
            self.items.append(entry);self._save()
            return dict(entry)

    def change(self, identifier, paused=None, delete=False):
        with self.lock:
            entry=next((item for item in self.items if item['id']==identifier),None)
            if entry is None:raise WorkbenchError('unknown_automation', 'Choose an existing recurring task ID')
            if delete:self.items.remove(entry)
            else:
                entry['paused']=bool(paused)
                entry['next_run']=time.time()+entry['interval_seconds']
            self._save()
            return {'id':identifier, 'deleted':delete, 'paused':entry['paused']}

    def run_due(self, now=None):
        now=time.time() if now is None else now
        with self.lock:
            due=next((dict(item) for item in self.items if not item['paused'] and item['next_run'] <= now),None)
            if due is None:return
            entry=next(item for item in self.items if item['id']==due['id'])
            # Claim before execution. No overdue queue or catch-up flood on restart.
            entry['next_run']=now+entry['interval_seconds'];self._save()
        if self.service.ask_lock.locked():return
        try:
            self.active_job=Job('automation')
            result=self.service.run_auto_agent(due['goal'],document_ids=due['document_ids'],
                                              workspace_id=due['workspace_id'],history=[],job=self.active_job)
            # Summaries retain audit/task IDs without repeatedly storing code/assets.
            summary={key:result.get(key) for key in ('task_id','status','answer','workspace_id')}
            error=None
        except Exception as exc:
            summary=None;error=str(exc)[:1000]
        finally:self.active_job=None
        with self.lock:
            entry=next((item for item in self.items if item['id']==due['id']),None)
            if entry is not None:
                entry.update(last_run=now,last_result=summary,last_error=error);self._save()

    def start(self):
        if self.thread and self.thread.is_alive():return
        self.stop_event.clear()
        def work():
            while not self.stop_event.wait(5):
                try:self.run_due()
                except Exception:pass  # A malformed external file cannot kill the API.
        self.thread=threading.Thread(target=work,daemon=True,name='sovereign-automations');self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.active_job:self.active_job.cancel.set()
