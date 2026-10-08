import json
import os
import time

import psutil

from experiments.fidelity_v1.run_status import EvaluatorHeartbeat, inspect_status, write_atomic


def test_old_checkpoint_is_not_live(tmp_path):
    write_atomic(tmp_path / 'progress.json', {'status': 'EXECUTING'})
    assert inspect_status(tmp_path)['status'] == 'UNKNOWN_NO_HEARTBEAT'


def test_live_then_completed(tmp_path):
    with EvaluatorHeartbeat(tmp_path, 'models'):
        assert inspect_status(tmp_path)['running_verified']
    assert inspect_status(tmp_path)['status'] == 'COMPLETED'
    assert not inspect_status(tmp_path)['running_verified']


def test_pid_reuse_and_stale_heartbeat(tmp_path):
    value = {'pid': os.getpid(), 'process_created_at': psutil.Process().create_time(),
             'updated_at': time.time(), 'state': 'RUNNING'}
    write_atomic(tmp_path / 'evaluator-heartbeat.json', {**value, 'process_created_at': 0})
    assert not inspect_status(tmp_path)['running_verified']
    write_atomic(tmp_path / 'evaluator-heartbeat.json', {**value, 'updated_at': 0})
    assert inspect_status(tmp_path)['status'] == 'INTERRUPTED_OR_STALE'


def test_exception_retains_failure_status(tmp_path):
    try:
        with EvaluatorHeartbeat(tmp_path, 'models'):
            raise RuntimeError('interruption')
    except RuntimeError:
        pass
    assert inspect_status(tmp_path)['status'] == 'STOPPED_WITH_ERROR'


def test_completed_status_survives_process_exit(tmp_path):
    write_atomic(tmp_path / 'evaluator-heartbeat.json', {'pid': -1, 'state': 'COMPLETED'})
    assert inspect_status(tmp_path)['status'] == 'COMPLETED'


def test_corrupt_heartbeat_is_not_live(tmp_path):
    (tmp_path / 'evaluator-heartbeat.json').write_text('{')
    assert not inspect_status(tmp_path)['running_verified']


def test_user_stop_remains_terminal_after_process_exit(tmp_path):
    write_atomic(tmp_path / 'evaluator-heartbeat.json', {'pid': -1, 'state': 'STOPPED_BY_USER'})
    assert inspect_status(tmp_path)['status'] == 'STOPPED_BY_USER'
    assert not inspect_status(tmp_path)['running_verified']
