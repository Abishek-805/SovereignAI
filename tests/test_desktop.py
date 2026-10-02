from unittest.mock import Mock

import pytest

from backend import desktop
from backend.contracts import WorkbenchError


def test_docker_launch_is_fixed_target_and_throttled(monkeypatch):
    from router import sandbox
    monkeypatch.setattr(sandbox, '_docker_cli', lambda: None)
    monkeypatch.setattr(desktop.Path, 'is_file', lambda self: True)
    monkeypatch.setattr(desktop, '_last_launch', 0)
    launch = Mock()
    monkeypatch.setattr(desktop.subprocess, 'Popen', launch)
    assert desktop.start_docker()['status'] == 'starting'
    assert desktop.start_docker()['status'] == 'starting'
    assert launch.call_count == 1
    args, kwargs = launch.call_args
    assert len(args[0]) == 1 and args[0][0].endswith('Docker Desktop.exe')
    assert kwargs['shell'] is False


def test_docker_launch_explicitly_starts_stopped_desktop_engine(monkeypatch):
    from router import sandbox
    monkeypatch.setattr(sandbox, '_docker_cli', lambda: 'docker.exe')
    monkeypatch.setattr(desktop.Path, 'is_file', lambda self: True)
    monkeypatch.setattr(desktop, '_last_launch', 0)
    launch = Mock()
    monkeypatch.setattr(desktop.subprocess, 'Popen', launch)
    assert desktop.start_docker()['status']=='starting'
    args, kwargs=launch.call_args_list[1]
    assert args[0]==['docker.exe','desktop','start','--detach']
    assert kwargs['shell'] is False


def test_missing_docker_has_actionable_error(monkeypatch):
    monkeypatch.setattr(desktop.Path, 'is_file', lambda self: False)
    with pytest.raises(WorkbenchError, match='not installed'):
        desktop.start_docker()


def test_verification_uses_fixed_image_and_real_checks(monkeypatch, tmp_path):
    from backend.jobs import Job
    from router import sandbox
    from types import SimpleNamespace
    monkeypatch.setattr(sandbox, '_docker_cli', lambda: 'docker.exe')
    calls = []
    def run(args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(returncode=0, stdout='sha256:' + 'a'*64 if len(calls)==1 else '{"normal_execution":true}')
    monkeypatch.setattr(desktop.subprocess, 'run', run)
    assert desktop.verify_docker(tmp_path, Job('sandbox_verify'))['status']=='verified'
    assert 'sovereign-workbench:latest' in calls[0][0]
    assert calls[1][1]['env']['SOVEREIGN_DATA_DIR']==str(tmp_path)
    assert calls[1][0][-1]=='sha256:'+'a'*64


def test_verification_failure_stays_disabled(monkeypatch, tmp_path):
    from backend.jobs import Job
    from router import sandbox
    from types import SimpleNamespace
    monkeypatch.setattr(sandbox, '_docker_cli', lambda: 'docker.exe')
    results=iter([SimpleNamespace(returncode=0,stdout='sha256:'+'a'*64),
                  SimpleNamespace(returncode=1,stdout='{}')])
    monkeypatch.setattr(desktop.subprocess,'run',lambda *a,**k:next(results))
    with pytest.raises(WorkbenchError,match='isolation checks failed'):
        desktop.verify_docker(tmp_path, Job('sandbox_verify'))


def test_verification_timeout_is_not_engine_startup_retry(monkeypatch, tmp_path):
    from backend.jobs import Job
    from router import sandbox
    from types import SimpleNamespace
    monkeypatch.setattr(sandbox, '_docker_cli', lambda: 'docker.exe')
    def run(args, **kwargs):
        if 'image' in args:
            return SimpleNamespace(returncode=0, stdout='sha256:'+'a'*64)
        raise desktop.subprocess.TimeoutExpired(args, 180)
    monkeypatch.setattr(desktop.subprocess, 'run', run)
    with pytest.raises(WorkbenchError) as failure:
        desktop.verify_docker(tmp_path, Job('sandbox_verify'))
    assert failure.value.code=='sandbox_verification'
