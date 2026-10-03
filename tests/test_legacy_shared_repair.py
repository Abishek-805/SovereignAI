import pytest
from router.sandbox import SandboxResult
from router.task_ledger import TaskLedger
from tests.test_coding_workspace import workspace


class Model:
    def __init__(self): self.calls = 0
    def complete_code(self, *args, **kwargs):
        self.calls += 1
        return {'code': 'def add(a, b):\n    return %d\n' % self.calls}


class Validator:
    def __init__(self, executed, feedbacks):
        self.executed, self.feedbacks = executed, iter(feedbacks)
        self.calls = 0
    def _ready(self): pass
    def execute(self, *args, **kwargs):
        self.calls += 1
        return SandboxResult(1, '', next(self.feedbacks), self.executed)


@pytest.mark.parametrize('executed,feedbacks,reason,calls',[
    (True, [''], 'missing_feedback', 1),
    (False, ['Docker not available'], 'validation_unavailable', 1),
    (True, ['ValueError: bad','ValueError: bad'], 'repeated_failure', 2),
    (True, ['ValueError: one','ValueError: two','ValueError: three'], 'attempt_budget', 3),
])
def test_legacy_shared_policy_stops_and_preserves_original(tmp_path,executed,feedbacks,reason,calls):
    work,wid = workspace(tmp_path)
    original = work.raw_files(wid)
    model = Model(); validator = Validator(executed,feedbacks)
    result = work.run(wid,'solution.py','Fix add',model,validator,TaskLedger(tmp_path))
    assert result['state'] == 'failed'
    assert result['repair_stop_reason'] == reason
    assert result['attempts'] == model.calls == validator.calls == calls
    assert result['repair_count'] == calls-1
    assert result['checks']['target_committed'] is False
    assert work.raw_files(wid) == original
    assert work.result(wid,result['task_id'])['repair_stop_reason'] == reason
