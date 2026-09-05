from __future__ import annotations

import datetime
import ast
import operator
import subprocess
import shutil


def get_datetime() -> str:
    return datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")


def get_battery() -> str:
    executable = shutil.which("termux-battery-status")
    if executable is None:
        return "termux-battery-status is not installed."
    try:
        result = subprocess.run([executable], capture_output=True, text=True, timeout=10)
    except subprocess.TimeoutExpired:
        return "Battery status request timed out."
    except OSError as exc:
        return f"Battery status error: {exc}"
    return result.stdout.strip() or result.stderr.strip() or "Battery status unavailable."


_ALLOWED = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod, ast.Pow: operator.pow, ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _eval(node):
    if isinstance(node, ast.Expression): return _eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)): return node.value
    if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED: return _ALLOWED[type(node.op)](_eval(node.operand))
    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED:
        if isinstance(node.op, ast.Pow) and abs(_eval(node.right)) > 100: raise ValueError("Exponent is too large")
        return _ALLOWED[type(node.op)](_eval(node.left), _eval(node.right))
    raise ValueError("Unsupported expression")


def calculate(expression: str) -> str:
    try:
        if len(expression) > 200: raise ValueError("Expression is too long")
        return str(_eval(ast.parse(expression, mode="eval")))
    except Exception as exc:
        return "Calculation error: " + str(exc)
