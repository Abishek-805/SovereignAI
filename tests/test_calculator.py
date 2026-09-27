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
