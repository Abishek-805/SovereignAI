from unittest.mock import Mock

import pytest

from backend import desktop
from backend.contracts import WorkbenchError


def test_docker_launch_is_fixed_target_and_throttled(monkeypatch):
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


def test_missing_docker_has_actionable_error(monkeypatch):
    monkeypatch.setattr(desktop.Path, 'is_file', lambda self: False)
    with pytest.raises(WorkbenchError, match='not installed'):
        desktop.start_docker()
