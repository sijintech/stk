"""Bounded scalar expressions. ASTs are interpreted explicitly, never compiled/eval'ed.

The first unit policy is deliberately exact: no conversion, inferred UCUM algebra,
or automatic work. Dimensioned values can be scaled and combined with identical
declared units. Unsupported unit operations remain visible cell errors.
"""
import ast
from dataclasses import dataclass
import math
import operator
import re

ENGINE_VERSION = 1
MAX_EXPRESSION = 4096
MAX_BINDINGS = 64
FUNCTIONS = {"abs", "min", "max", "round", "sqrt", "quantity"}


class EvaluationError(ValueError):
    def __init__(self, code, message, source=None):
        super().__init__(message)
        self.code, self.source = code, source

    def document(self):
        result = {"code": self.code, "message": str(self)}
        if self.source is not None:
            result["source"] = {"record_id": self.source[0], "field_id": self.source[1]}
        return result


@dataclass(frozen=True)
class Value:
    value: object
    unit: str | None = None


def _number(value):
    if type(value) not in (int, float):
        raise EvaluationError("type", "Expressions require numeric values (not null, bool or text)")
    try:
        finite = math.isfinite(value)
    except OverflowError:
        finite = False
    if not finite:
        raise EvaluationError("range", "Expression produced a non-finite or oversized number")
    return value


def _same_unit(left, right):
    if left in (None, "unspecified") or right in (None, "unspecified"):
        raise EvaluationError("unit_unknown", "Declare matching units (use '1' for dimensionless values)")
    if left != right:
        raise EvaluationError("unit", f"Units must match exactly: {left!r} and {right!r}; no implicit conversion")
    return left


def check_target(value, kind, unit):
    """Check the value assigned to a field; an absent target unit imposes no unit assertion."""
    if unit is not None and value.unit != unit:
        raise EvaluationError("unit", f"Result unit {value.unit!r} does not match field unit {unit!r}")
    if value.value is None:
        return value
    valid = {"text": isinstance(value.value, str),
             "integer": type(value.value) is int and -(2**63) <= value.value < 2**63,
             "number": type(value.value) in (int, float),
             "boolean": type(value.value) is bool,
             "json": True}.get(kind, False)
    if not valid:
        raise EvaluationError("type", f"Result does not match field type {kind}")
    if kind in {"integer", "number"}:
        _number(value.value)
    return value


class Expression:
    def __init__(self, source, names):
        if not isinstance(source, str) or not source.strip() or len(source) > MAX_EXPRESSION:
            raise EvaluationError("syntax", "Expression must contain 1–4096 characters")
        if len(names) > MAX_BINDINGS or any(not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", name)
                                           or name in FUNCTIONS for name in names):
            raise EvaluationError("binding", "Use up to 64 distinct identifier bindings, excluding function names")
        self.names = set(names)
        self.used = set()
        try:
            self.root = ast.parse(source, mode="eval").body
        except (SyntaxError, ValueError, RecursionError) as exc:
            raise EvaluationError("syntax", f"Invalid expression: {getattr(exc, 'msg', type(exc).__name__)}") from None
        if sum(1 for _ in ast.walk(self.root)) > 256:
            raise EvaluationError("limit", "Expression exceeds the 256-node limit")
        self._validate(self.root, 0)
        if self.used != self.names:
            raise EvaluationError("binding", "Unused bindings: " + ", ".join(sorted(self.names - self.used)))

    def _validate(self, node, depth):
        if depth > 32:
            raise EvaluationError("limit", "Expression exceeds the nesting limit")
        descend = lambda child: self._validate(child, depth + 1)
        if isinstance(node, ast.Constant):
            _number(node.value)
            if type(node.value) is int and not -(2**63) <= node.value < 2**63:
                raise EvaluationError("range", "Integer constants must fit signed 64 bits")
        elif isinstance(node, ast.Name):
            if node.id not in self.names:
                raise EvaluationError("binding", f"Unknown binding {node.id!r}")
            self.used.add(node.id)
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            if isinstance(node.op, ast.USub) and isinstance(node.operand, ast.Constant) and type(node.operand.value) is int and node.operand.value == 2**63:
                return  # The AST stores signed-int64 minimum as unary minus of the positive magnitude.
            descend(node.operand)
        elif isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow)):
            descend(node.left)
            descend(node.right)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in FUNCTIONS:
            name = node.func.id
            minimum, maximum = {"abs": (1, 1), "sqrt": (1, 1), "round": (1, 2),
                                "min": (2, 16), "max": (2, 16), "quantity": (2, 2)}[name]
            if node.keywords or not minimum <= len(node.args) <= maximum:
                raise EvaluationError("syntax", f"Invalid arguments to {name}")
            for index, child in enumerate(node.args):
                if name == "quantity" and index == 1:
                    if not isinstance(child, ast.Constant) or not isinstance(child.value, str) or not child.value.strip() or len(child.value) > 1024:
                        raise EvaluationError("unit", "quantity(value, unit) needs a literal nonempty unit string")
                else:
                    descend(child)
        else:
            raise EvaluationError("unsupported", f"Unsupported expression element: {type(node).__name__}")

    def evaluate(self, resolve):
        try:
            result = self._evaluate(self.root, resolve)
            _number(result.value)
            return result
        except EvaluationError:
            raise
        except ZeroDivisionError:
            raise EvaluationError("division_by_zero", "Division by zero") from None
        except (OverflowError, ValueError, TypeError) as exc:
            raise EvaluationError("range", f"Numeric operation failed: {exc}") from None

    def _evaluate(self, node, resolve):
        if isinstance(node, ast.Constant):
            return Value(node.value, "1")
        if isinstance(node, ast.Name):
            value = resolve(node.id)
            _number(value.value)
            return value
        if isinstance(node, ast.UnaryOp):
            value = self._evaluate(node.operand, resolve)
            return Value(-value.value if isinstance(node.op, ast.USub) else value.value, value.unit)
        if isinstance(node, ast.BinOp):
            left, right = self._evaluate(node.left, resolve), self._evaluate(node.right, resolve)
            if isinstance(node.op, (ast.Add, ast.Sub)):
                unit = _same_unit(left.unit, right.unit)
                function = operator.add if isinstance(node.op, ast.Add) else operator.sub
            elif isinstance(node.op, ast.Mult):
                if left.unit != "1" and right.unit != "1":
                    raise EvaluationError("unit_operation", "Multiplication requires a dimensionless operand")
                unit = right.unit if left.unit == "1" else left.unit
                function = operator.mul
            elif isinstance(node.op, ast.Div):
                unit = left.unit if right.unit == "1" else "1" if _same_unit(left.unit, right.unit) else None
                function = operator.truediv
            else:
                if right.unit != "1" or type(right.value) is not int or not -16 <= right.value <= 16:
                    raise EvaluationError("limit", "Powers need a dimensionless integer exponent from -16 to 16")
                if right.value not in (0, 1) and left.unit != "1":
                    raise EvaluationError("unit_operation", "Powers of dimensioned values are not supported yet")
                unit = "1" if right.value == 0 else left.unit
                function = operator.pow
            return Value(_number(function(left.value, right.value)), unit)
        name = node.func.id
        if name == "quantity":
            value = self._evaluate(node.args[0], resolve)
            if value.unit != "1":
                raise EvaluationError("unit", "quantity() annotates a dimensionless value; it cannot convert units")
            return Value(value.value, node.args[1].value)
        values = [self._evaluate(child, resolve) for child in node.args]
        first = values[0]
        if name == "abs":
            return Value(abs(first.value), first.unit)
        if name == "sqrt":
            if first.unit != "1":
                raise EvaluationError("unit_operation", "sqrt() requires dimensionless values")
            return Value(math.sqrt(first.value), "1")
        if name == "round":
            digits = values[1] if len(values) == 2 else Value(0, "1")
            if digits.unit != "1" or type(digits.value) is not int or not -12 <= digits.value <= 12:
                raise EvaluationError("limit", "round() digits must be a dimensionless integer from -12 to 12")
            return Value(round(first.value, digits.value) if len(values) == 2 else round(first.value), first.unit)
        for value in values[1:]:
            _same_unit(first.unit, value.unit)
        return Value((min if name == "min" else max)(value.value for value in values), first.unit)
