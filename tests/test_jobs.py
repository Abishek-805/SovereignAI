import threading
import time
import pytest
from backend.jobs import Jobs
from backend.contracts import WorkbenchError

def test_job_progress_result_and_admission():
    jobs=Jobs();release=threading.Event();started=threading.Event()
    def work(job):
        job.progress('Testing');job.append('stdout','first line\n');started.set();release.wait(3)
        return {'state':'completed','exit_code':0}
    current=jobs.start('run',work);assert started.wait(2)
    assert jobs.get(current['job_id']).snapshot()['output']=='first line\n'
    with pytest.raises(WorkbenchError):jobs.start('run',work)
    release.set()
    for _ in range(100):
        if jobs.get(current['job_id']).state!='running':break
        time.sleep(.01)
    assert jobs.get(current['job_id']).snapshot()['state']=='completed'

def test_cancelled_job_never_claims_success():
    jobs=Jobs();started=threading.Event()
    def work(job):
        started.set();job.cancel.wait(3);return {'state':'completed'}
    record=jobs.start('run',work);assert started.wait(2)
    job=jobs.get(record['job_id']);job.cancel.set()
    for _ in range(100):
        if job.state!='running':break
        time.sleep(.01)
    assert job.snapshot()['state']=='cancelled'

def test_output_is_bounded():
    from backend.jobs import Job
    job=Job('terminal');job.append('stdout','x'*100000)
    assert len(job.snapshot()['output'])==65536


def test_import_and_workspace_have_independent_bounded_lanes():
    jobs=Jobs(); release=threading.Event()
    def work(job):
        release.wait(3); return {'state':'completed'}
    try:
        imported=jobs.start('import',work)
        agent=jobs.start('agent',work)
        assert imported['state']==agent['state']=='running'
        with pytest.raises(WorkbenchError,match='document import'): jobs.start('import',work)
        with pytest.raises(WorkbenchError,match='workspace job'): jobs.start('terminal',work)
        jobs.get(imported['job_id']).created-=7200
        release.set()
    finally: release.set()
