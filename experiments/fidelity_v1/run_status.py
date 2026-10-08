"""Passive evaluator liveness; never release leases or terminate processes."""
import json
import os
import threading
import time
from pathlib import Path

import psutil


def write_atomic(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(value, indent=2), encoding='utf-8')
    temporary.replace(path)


def inspect_status(directory, now=None):
    """Missing heartbeat is unknown, never assumed to be running."""
    directory = Path(directory)
    now = time.time() if now is None else now
    progress = json.loads((directory / 'progress.json').read_text()) if (directory / 'progress.json').exists() else {}
    path = directory / 'evaluator-heartbeat.json'
    if not path.exists():
        return {'status': 'UNKNOWN_NO_HEARTBEAT', 'checkpoint': progress, 'running_verified': False}
    try:
        heartbeat = json.loads(path.read_text())
        state = heartbeat['state']
        if state in {'COMPLETED', 'STOPPED_WITH_ERROR', 'STOPPED_BY_USER'}:
            return {'status': state, 'running_verified': False, 'checkpoint': progress, 'heartbeat': heartbeat}
        process = psutil.Process(heartbeat['pid'])
        same_process = abs(process.create_time() - heartbeat['process_created_at']) < .01
        age = max(0, now - heartbeat['updated_at'])
        alive = same_process and process.is_running() and age <= 30
        status = 'RUNNING' if alive and state == 'RUNNING' else state if state != 'RUNNING' else 'INTERRUPTED_OR_STALE'
        return {'status': status, 'running_verified': alive and state == 'RUNNING', 'heartbeat_age_seconds': age,
                'checkpoint': progress, 'heartbeat': heartbeat}
    except (OSError, ValueError, KeyError, TypeError, psutil.Error) as exc:
        return {'status': 'INTERRUPTED_OR_STALE', 'running_verified': False, 'checkpoint': progress, 'error': str(exc)}


class EvaluatorHeartbeat:
    def __init__(self, directory, phase):
        self.path = Path(directory) / 'evaluator-heartbeat.json'
        self.phase = phase
        self.stop = threading.Event()
        self.process = psutil.Process(os.getpid())
        self.thread = None

    def publish(self, state):
        write_atomic(self.path, {'pid': self.process.pid, 'process_created_at': self.process.create_time(),
                                 'updated_at': time.time(), 'phase': self.phase, 'state': state})

    def pulse(self):
        while not self.stop.wait(5):
            self.publish('RUNNING')

    def __enter__(self):
        self.publish('RUNNING')
        self.thread = threading.Thread(target=self.pulse, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.stop.set()
        self.thread.join()
        self.publish('STOPPED_WITH_ERROR' if exc_type else 'COMPLETED')


if __name__ == '__main__':
    from experiments.fidelity_v1.tasks import OUT
    print(json.dumps(inspect_status(OUT), indent=2))
