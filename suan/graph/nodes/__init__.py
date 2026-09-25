"""Built-in STK node types: the Milestone-1 catalog (docs/specs/catalog/m1_nodes.py).

Each module declares the node types of one family and copies its declarations
from ``docs/specs/catalog/m1_nodes.py``:

========== ===========================================
module      node types
========== ===========================================
sources     ``stk.source.*``
filters     ``stk.filter.*``
analysis    ``stk.analysis.*``
render      ``stk.render.*``
view        ``stk.view.*``
output      ``stk.output.*``
plot        ``stk.plot.*``
========== ===========================================

Built-ins are imported directly (a source checkout on ``PYTHONPATH`` works
without installing entry points); third-party node packages register through
the ``stk.nodes`` entry-point group (``suan.graph.catalog``). A built-in module
that does not exist yet is skipped only when importing it raises
``ModuleNotFoundError`` for exactly that module; any other error raised while a
module imports (including a missing dependency) propagates. Node modules must
not import NumPy or VTK at import time.
"""
import importlib

__all__ = ["BUILTIN_MODULES", "MODULE_FAMILIES", "builtin_modules", "catalog", "missing_modules", "register_builtin"]

BUILTIN_MODULES = ("sources", "filters", "analysis", "render", "view", "output", "plot")
# Node family (middle segment of the type id) declared by each module.
MODULE_FAMILIES = {"sources": "source", "filters": "filter", "analysis": "analysis", "render": "render",
                   "view": "view", "output": "output", "plot": "plot"}


def _import(name):
    full = f"{__name__}.{name}"
    try:
        return importlib.import_module(full)
    except ModuleNotFoundError as exc:
        if exc.name != full:
            raise
        return None


def builtin_modules():
    """The built-in node modules that exist, in :data:`BUILTIN_MODULES` order."""
    return [module for module in (_import(name) for name in BUILTIN_MODULES) if module is not None]


def missing_modules():
    """Names of the built-in node modules that are not installed (yet)."""
    return [name for name in BUILTIN_MODULES if _import(name) is None]


def register_builtin(registry, *, replace=False):
    """Register every available built-in node type into ``registry``; returns the registered types."""
    added = []
    for module in builtin_modules():
        added.extend(registry.register(module, replace=replace))
    return added


def catalog(*, include_impl=False):
    """The ``stk.catalog/1`` document of the available built-in node types."""
    from ..registry import Registry
    registry = Registry(namespaces={"stk": 1})
    register_builtin(registry)
    return registry.catalog(include_impl=include_impl)
