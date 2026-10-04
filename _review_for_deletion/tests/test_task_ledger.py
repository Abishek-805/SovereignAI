import os

from router.task_ledger import TaskLedger


def test_transient_windows_replace_lock_does_not_fail_task(tmp_path,monkeypatch):
    ledger=TaskLedger(tmp_path)
    task=ledger.create('example',[])
    original=os.replace
    calls=0

    def temporarily_locked(source,destination):
        nonlocal calls
        calls+=1
        if calls<=2:
            raise PermissionError(5,'Access is denied',str(destination))
        return original(source,destination)

    monkeypatch.setattr('router.task_ledger.os.replace',temporarily_locked)
    ledger.step(task,'run',{'count':1})
    assert calls==3
    assert ledger.read(task['task_id'])['steps'][0]['name']=='run'
