import pytest
from backend.contracts import WorkbenchError
from rag.calculator import evaluate_expression

def test_calculator_valid():
    res = evaluate_expression("5 * 3.2 - (10 / 2)")
    assert res.result == 11.0
    assert res.rounded == 11.0
    assert res.expression == "5 * 3.2 - (10 / 2)"

def test_calculator_zero_division():
    with pytest.raises(WorkbenchError) as exc:
        evaluate_expression("10 / 0")
    assert "Division by zero" in str(exc.value)

def test_calculator_invalid_operation():
    # Power is not allowlisted
    with pytest.raises(WorkbenchError) as exc:
        evaluate_expression("2 ** 3")
    assert "Unsupported operator" in str(exc.value)

def test_calculator_malicious():
    with pytest.raises(WorkbenchError):
        evaluate_expression("__import__('os').system('ls')")

def test_square_root_uses_decimal_and_records_validation_steps():
    result = evaluate_expression('sqrt(196) + 1')
    assert result.result == 15
    assert result.steps[0] == 'sqrt(196) = 14'

@pytest.mark.parametrize('expression', ['sqrt(-1)', 'sqrt(1, 2)', 'sqrt(x=4)', 'abs(-4)', 'True', "__import__('os')"])
def test_extended_calculator_keeps_calls_and_constants_bounded(expression):
    with pytest.raises(WorkbenchError):
        evaluate_expression(expression)
