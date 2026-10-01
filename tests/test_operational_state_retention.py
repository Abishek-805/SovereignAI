from backend.task_supervisor import CURRENT_SUPERVISOR,TaskSupervisor
from router.telemetry import RoutingDecision
from tests.test_service import service
from router.request_normalization import normalize_request


def test_literal_single_quoted_names_are_not_spelling_corrections():
    literal="creat a folder named 'maintanance' and retain `creat`"
    normalized=normalize_request(literal)
    assert normalized.normalized=="create a folder named 'maintanance' and retain `creat`"
    assert len(normalized.corrections)==1


def test_calculator_keeps_workflow_and_tool_in_final_response(service):
    result=service.run_auto_agent('calcluate 12 * 5',[])
    state=result['supervisor']['task_state']
    assert result['result']['result']==60
    assert state['workflow']=='CALCULATE' and state['current_action']=='calculator'
    assert result['routing']['decision']['workflow']=='CALCULATE'
    assert result['routing']['decision']['selected_tool']=='calculator'
    assert result['supervisor']['counts']['model_calls']==0


def test_unknown_trace_fields_do_not_erase_observed_worker_or_tool():
    supervisor=TaskSupervisor('Read source',{})
    token=CURRENT_SUPERVISOR.set(supervisor)
    try:
        supervisor.record_event('MODEL_READY',selected_model='actual-worker',worker_role='reasoning',workflow='TABLE_QUERY')
        supervisor.record_event('TOOL_STARTED',tool='table_query')
        trace=RoutingDecision()
        trace.event('TOOL_COMPLETED')
        assert supervisor.task_state['active_worker']=='actual-worker'
        assert supervisor.worker_role=='reasoning'
        assert supervisor.task_state['current_action']=='table_query'
        assert trace.workflow=='TABLE_QUERY' and trace.selected_tool=='table_query'
    finally:CURRENT_SUPERVISOR.reset(token)
