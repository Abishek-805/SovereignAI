import ast
import operator
from decimal import Decimal, localcontext
from dataclasses import dataclass
from typing import Any

from backend.contracts import WorkbenchError

# Allowlisted operations
_OP_MAP = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

@dataclass
class CalculationResult:
    expression: str
    result: float
    rounded: float
    steps: list[str]

class SafeCalculator(ast.NodeVisitor):
    def __init__(self):
        self.steps=[]

    def visit_BinOp(self, node):
        left = self.visit(node.left)
        right = self.visit(node.right)
        op = type(node.op)
        if op not in _OP_MAP:
            raise WorkbenchError('invalid_calculation', f"Unsupported operator: {op}")
        if op == ast.Div and right == 0:
            raise WorkbenchError('invalid_calculation', "Division by zero")
        result=_OP_MAP[op](left, right)
        symbol={ast.Add:'+',ast.Sub:'-',ast.Mult:'×',ast.Div:'÷'}[op]
        self.steps.append(f'{left:g} {symbol} {right:g} = {result:g}')
        return result

    def visit_UnaryOp(self, node):
        operand = self.visit(node.operand)
        op = type(node.op)
        if op not in _OP_MAP:
            raise WorkbenchError('invalid_calculation', f"Unsupported operator: {op}")
        return _OP_MAP[op](operand)

    def visit_Constant(self, node):
        if not isinstance(node.value, (int, float)):
            raise WorkbenchError('invalid_calculation', f"Unsupported constant type: {type(node.value)}")
        return Decimal(str(node.value))

    def visit_Expr(self, node):
        return self.visit(node.value)

    def generic_visit(self, node):
        raise WorkbenchError('invalid_calculation', f"Unsupported expression node: {type(node)}")

def evaluate_expression(expr: str, decimals: int = 2) -> CalculationResult:
    """Evaluate a simple arithmetic expression safely."""
    if not expr or not isinstance(expr, str):
        raise WorkbenchError('invalid_calculation', "Expression must be a non-empty string")
    
    try:
        tree = ast.parse(expr, mode='eval')
    except SyntaxError as e:
        raise WorkbenchError('invalid_calculation', f"Syntax error in expression: {e}")
        
    calc = SafeCalculator()
    try:
        with localcontext() as context:
            context.prec=28
            result = calc.visit(tree.body)
    except Exception as e:
        if isinstance(e, WorkbenchError):
            raise
        raise WorkbenchError('invalid_calculation', f"Evaluation failed: {e}")
        
    if not result.is_finite():
        raise WorkbenchError('invalid_calculation', "Result is not finite")
        
    rounded = round(result, decimals)
    return CalculationResult(expression=expr, result=float(result), rounded=float(rounded), steps=calc.steps)
