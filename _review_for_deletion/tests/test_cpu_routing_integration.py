import pytest
from router.telemetry import RoutingDecision, CURRENT_ROUTE
from rag.calculator import literal_expression
from rag.retrieve import document_scope_for_question
from backend.service import Workbench

@pytest.mark.parametrize('text,expected',[('Calculate: 18.5 × 24','18.5 * 24'),('sqrt(81) + 3','sqrt(81) + 3'),('Create a division program',None),('__import__("os").system("dir")',None),('sqrt(x)',None),('True + 1',None),('Update this',None)])
def test_calculator_input_is_a_formal_bounded_language(text,expected):
    assert literal_expression(text)==expected

@pytest.mark.parametrize('text,expected',[('Calculate 15 percent of 860.','(15/100)*(860)'),('Calculate the square root of 196.','sqrt(196)'),('Calculate 17.25 times 32.','17.25 * 32'),('Calculate the cost from receipt.pdf',None)])
def test_explicit_bounded_arithmetic_not_document_or_code_tasks(text,expected):
    assert literal_expression(text)==expected

def test_explicit_off_never_expands_named_document_scope():
    docs=[{'document_id':'d1','display_name':'inspection-report.pdf'}]
    assert document_scope_for_question(docs,'inspection report',[])==[]
    assert document_scope_for_question(docs,'inspection report',None)==['d1']

def test_classifier_is_not_mutation_authority():
    service=object.__new__(Workbench)
    class Model:
        def conversation_answer(self,*args):raise AssertionError('Mutation cannot dispatch through readonly route')
    service.model=Model()
    trace=RoutingDecision(classification={'production_enabled':True,'decision':'edit_code'})
    token=CURRENT_ROUTE.set(trace)
    try:
        assert service._cpu_readonly_plan('Delete this file',mode='agent') is None
    finally:CURRENT_ROUTE.reset(token)

def test_unreleased_classifier_cannot_skip_planner():
    service=object.__new__(Workbench)
    trace=RoutingDecision(classification={'production_enabled':False,'decision':'answer'})
    token=CURRENT_ROUTE.set(trace)
    try:assert service._cpu_readonly_plan('Hello') is None
    finally:CURRENT_ROUTE.reset(token)

def test_canonical_measurements_preserve_unknowns():
    trace=RoutingDecision(classifier_time=.002,knowledge_scope={'connected':False,'mode':'off','permitted_document_count':0})
    value=trace.snapshot()
    assert value['timings']['classification_ms']==2
    assert value['timings']['generation_ms'] is None
    assert value['evidence_used'] is None
