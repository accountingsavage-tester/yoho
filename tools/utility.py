import datetime
import ast
import operator
import subprocess


def get_datetime():
    return datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")


def get_battery():
    try:
        result = subprocess.run(["termux-battery-status"], capture_output=True, text=True)
        return result.stdout.strip() or result.stderr.strip()
    except FileNotFoundError:
        return "termux-battery-status is not installed."


_ALLOWED = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _eval(node):
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED:
        return _ALLOWED[type(node.op)](_eval(node.operand))
    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED:
        return _ALLOWED[type(node.op)](_eval(node.left), _eval(node.right))
    raise ValueError("Unsupported expression")


def calculate(expression):
    try:
        tree = ast.parse(expression, mode="eval")
        return str(_eval(tree))
    except Exception as exc:
        return "Calculation error: " + str(exc)
