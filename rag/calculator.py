import ast
import operator
import re
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

def literal_expression(request):
    """Recognize the calculator's formal input, not arbitrary semantic intent.

    No history, document text, names, attribute access, or code is evaluated.
    Unsupported natural-language tasks remain with the capability classifier.
    """
    if not isinstance(request,str) or len(request)>256:
        return None
    value=request.strip()
    value=re.sub(r'^(?:calculate|compute|evaluate|what is)\s*:?\s*','',value,flags=re.I).strip()
    value=value.rstrip('?.').strip()
    number=r'[+-]?\d+(?:\.\d+)?'
    percent=re.fullmatch(r'('+number+r')\s+percent\s+of\s+('+number+r')',value,re.I)
    if percent:value='('+percent[1]+'/100)*('+percent[2]+')'
    root=re.fullmatch(r'(?:the\s+)?square\s+root\s+of\s+('+number+r')',value,re.I)
    if root:value='sqrt('+root[1]+')'
    for word,symbol in (('times','*'),('plus','+'),('minus','-'),('divided by','/')):
        value=re.sub(r'\b'+word+r'\b',symbol,value,flags=re.I)
    value=value.replace('×','*').replace('÷','/').replace('−','-')
    try:
        tree=ast.parse(value,mode='eval')
    except (SyntaxError,ValueError):
        return None
    nodes=list(ast.walk(tree))
    allowed=(ast.Expression,ast.BinOp,ast.UnaryOp,ast.Constant,ast.Add,ast.Sub,ast.Mult,ast.Div,ast.UAdd,ast.USub,ast.Call,ast.Name,ast.Load)
    if len(nodes)>64 or any(not isinstance(node,allowed) for node in nodes):
        return None
    if any(isinstance(node,ast.Name) and node.id!='sqrt' for node in nodes):
        return None
    if any(isinstance(node,ast.Constant) and (isinstance(node.value,bool) or not isinstance(node.value,(float,int))) for node in nodes):
        return None
    if any(isinstance(node,ast.Call) and (not isinstance(node.func,ast.Name) or node.func.id!='sqrt' or len(node.args)!=1 or node.keywords) for node in nodes):
        return None
    if not any(isinstance(node,(ast.BinOp,ast.Call)) for node in nodes):
        return None
    return value

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
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise WorkbenchError('invalid_calculation', f"Unsupported constant type: {type(node.value)}")
        return Decimal(str(node.value))

    def visit_Call(self, node):
        if not isinstance(node.func, ast.Name) or node.func.id != 'sqrt' or len(node.args) != 1 or node.keywords:
            raise WorkbenchError('invalid_calculation', 'Only sqrt with one numeric argument is supported')
        value = self.visit(node.args[0])
        if value < 0:
            raise WorkbenchError('invalid_calculation', 'Square root requires a nonnegative value')
        result = value.sqrt()
        self.steps.append(f'sqrt({value:g}) = {result:g}')
        return result

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
