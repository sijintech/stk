"""Pure numerical comparison of explicitly supplied reproduction evidence.

No I/O, execution, unit conversion or source authentication happens on import or
comparison. This package does not establish that a paper was reproduced.
"""
from .comparison import ComparisonError, compare, verify

__all__ = ["ComparisonError", "compare", "verify"]
