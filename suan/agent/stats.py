"""Deterministic statistics for the agent's table_statistics tool, in plain Python (numpy is an optional dependency)."""
import math


def _finite(value):
    return value is None or math.isfinite(value)


def summary(values):
    """n, mean, sample standard deviation, minimum and maximum of finite numbers (None when there are none, or with
    ``reason: overflow`` when values are too large to combine)."""
    values = [float(value) for value in values]
    n = len(values)
    if n == 0:
        return {"n": 0, "mean": None, "std": None, "min": None, "max": None}
    try:
        mean = math.fsum(values) / n
        std = math.sqrt(math.fsum((value - mean) * (value - mean) for value in values) / (n - 1)) if n > 1 else None
    except OverflowError:
        mean = std = None
    if mean is None or not (_finite(mean) and _finite(std)):
        return {"n": n, "mean": None, "std": None, "min": min(values), "max": max(values), "reason": "overflow"}
    return {"n": n, "mean": mean, "std": std, "min": min(values), "max": max(values)}


def fit(xs, ys, degree):
    """Least-squares polynomial fit of degree 1 or 2: coefficients from the constant term up, and R²."""
    try:
        result = _fit(xs, ys, degree)
    except (OverflowError, ZeroDivisionError):
        result = None
    if result is None or not all(_finite(value) for value in (result["coefficients"] or []) + [result["r2"]]):
        return {"degree": degree, "n": len(xs), "coefficients": None, "r2": None, "reason": "overflow"}
    return result


def _fit(xs, ys, degree):
    if degree not in (1, 2):
        raise ValueError("degree is 1 or 2")
    xs, ys = [float(x) for x in xs], [float(y) for y in ys]
    n = len(xs)
    if n != len(ys) or n <= degree:
        return {"degree": degree, "n": n, "coefficients": None, "r2": None, "reason": "too_few_points"}
    # Normal equations, solved by Gaussian elimination with partial pivoting (at most 3 x 3).
    size = degree + 1
    matrix = [[math.fsum(x ** (row + column) for x in xs) for column in range(size)] for row in range(size)]
    vector = [math.fsum(y * x ** row for x, y in zip(xs, ys)) for row in range(size)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(matrix[row][column]))
        if abs(matrix[pivot][column]) < 1e-12 * max(1.0, max(abs(value) for value in matrix[pivot])):
            return {"degree": degree, "n": n, "coefficients": None, "r2": None, "reason": "singular"}
        matrix[column], matrix[pivot] = matrix[pivot], matrix[column]
        vector[column], vector[pivot] = vector[pivot], vector[column]
        for row in range(column + 1, size):
            factor = matrix[row][column] / matrix[column][column]
            for k in range(column, size):
                matrix[row][k] -= factor * matrix[column][k]
            vector[row] -= factor * vector[column]
    coefficients = [0.0] * size
    for row in reversed(range(size)):
        coefficients[row] = (vector[row] - math.fsum(matrix[row][k] * coefficients[k] for k in range(row + 1, size))) / matrix[row][row]
    predicted = [math.fsum(coefficient * x ** power for power, coefficient in enumerate(coefficients)) for x in xs]
    mean = math.fsum(ys) / n
    total = math.fsum((y - mean) ** 2 for y in ys)
    residual = math.fsum((y - p) ** 2 for y, p in zip(ys, predicted))
    r2 = 1.0 - residual / total if total > 0 else None
    return {"degree": degree, "n": n, "coefficients": coefficients, "r2": r2}
