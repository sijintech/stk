"""Connector registry: built-ins, entry points, priority and the operator allowlist. Standard library only.

Built-in connectors are imported directly (tests and checkouts run from
``PYTHONPATH`` without installed entry points); installed packages add more
through the entry-point groups ``stk.connectors`` (heavy half) and
``stk.inputs`` (light half). Each entry point names a class (instantiated
without arguments), an instance, or a factory returning one.

When two connectors claim the same id, the higher ``info()["priority"]`` wins
(the private ``stk-mupro`` package uses 10); ties keep the first registered
(built-ins first). Diagnostics list every candidate. The node's
``connectors.allow`` patterns (``fnmatch``, e.g. ``["stk.*", "mupro.*"]``)
limit which connectors run; ``None`` allows all.
"""
from dataclasses import dataclass
from fnmatch import fnmatchcase
from importlib import import_module
from importlib.metadata import entry_points
import threading

from .api import API_VERSION, ENTRY_POINT_GROUPS, ConnectorError

__all__ = [
    "BUILTIN_CONNECTORS", "BUILTIN_INPUTS", "ConnectorRegistry", "Entry", "allowed", "default_registry",
]

BUILTIN_CONNECTORS = (
    "suan.connectors.mupro:MuFerroConnector",
    "suan.connectors.builtin.vtk:VTKConnector",
    "suan.connectors.builtin.numpy:NumpyConnector",
)
BUILTIN_INPUTS = ("suan.connectors.mupro.inputs:MuFerroInputs",)


def allowed(connector_id, patterns):
    """True if ``connector_id`` matches one of the allowlist ``patterns`` (``None`` = everything)."""
    if patterns is None:
        return True
    return any(fnmatchcase(connector_id, pattern) for pattern in patterns)


@dataclass
class Entry:
    """One registered candidate (active or shadowed)."""

    id: str
    version: str | None
    priority: int
    source: str
    object: object = None
    error: str | None = None
    allowed: bool = True
    active: bool = False
    impl: str | None = None

    def to_json(self):
        return {"id": self.id, "version": self.version, "priority": self.priority, "source": self.source,
                "allowed": self.allowed, "active": self.active, "error": self.error, "impl": self.impl}


def _load(reference):
    module, _, name = reference.partition(":")
    target = import_module(module)
    for part in name.split("."):
        target = getattr(target, part)
    return target


def _instance(obj):
    return obj() if isinstance(obj, type) or (callable(obj) and not hasattr(obj, "id")) else obj


def _impl(obj):
    cls = obj if isinstance(obj, type) else type(obj)
    return f"{cls.__module__}:{cls.__qualname__}"


class ConnectorRegistry:
    """Connectors (heavy half) and input connectors (light half) by id."""

    def __init__(self, *, allow=None, builtins=True, entry_points=True):
        self.allow = None if allow is None else tuple(allow)
        self._entries = {"connectors": {}, "inputs": {}}
        self._errors = []
        self._lock = threading.Lock()
        if builtins:
            for reference in BUILTIN_CONNECTORS:
                self._add_reference("connectors", reference, "builtin")
            for reference in BUILTIN_INPUTS:
                self._add_reference("inputs", reference, "builtin")
        if entry_points:
            for half in ("connectors", "inputs"):
                for point in _entry_points(ENTRY_POINT_GROUPS[half]):
                    distribution = getattr(getattr(point, "dist", None), "name", None)
                    self._add_reference(half, point.value, f"entry_point:{distribution or point.name}",
                                        loader=point.load, name=point.name)

    # -- registration ---------------------------------------------------------

    def _add_reference(self, half, reference, source, loader=None, name=None):
        try:
            obj = loader() if loader else _load(reference)
        except Exception as exc:  # a broken plugin must not break the registry
            self._errors.append({"half": half, "reference": reference, "source": source,
                                 "error": f"{type(exc).__name__}: {exc}"})
            return None
        try:
            return self._register(half, obj, source, fallback_id=name)
        except Exception as exc:
            self._errors.append({"half": half, "reference": reference, "source": source,
                                 "error": f"{type(exc).__name__}: {exc}"})
            return None

    def _register(self, half, obj, source, fallback_id=None):
        impl = _impl(obj)
        instance = _instance(obj)
        connector_id = getattr(instance, "id", None) or fallback_id
        if not isinstance(connector_id, str) or not connector_id:
            raise ConnectorError(f"{impl} has no connector id", "invalid_connector")
        api = getattr(instance, "api", API_VERSION)
        if api != API_VERSION:
            raise ConnectorError(f"{connector_id} implements connector API {api}; this STK supports {API_VERSION}",
                                 "unsupported")
        info = instance.info() if half == "connectors" and hasattr(instance, "info") else {}
        priority = int(info.get("priority", getattr(instance, "priority", 0)) or 0)
        version = info.get("version", getattr(instance, "version", None))
        with self._lock:
            candidates = self._entries[half].setdefault(connector_id, [])
            if any(entry.impl == impl for entry in candidates):  # the same class twice (built-in and entry point)
                return next(entry for entry in candidates if entry.impl == impl)
            entry = Entry(connector_id, version, priority, source, instance, allowed=allowed(connector_id, self.allow),
                          impl=impl)
            candidates.append(entry)
            winner = max(candidates, key=lambda e: e.priority)  # max keeps the first of equal priorities
            for candidate in candidates:
                candidate.active = candidate is winner
        return entry

    def register(self, connector, *, source="manual"):
        """Register a connector class or instance (heavy half); returns its :class:`Entry`."""
        return self._register("connectors", connector, source)

    def register_inputs(self, inputs, *, source="manual"):
        """Register an input connector class or instance (light half)."""
        return self._register("inputs", inputs, source)

    # -- lookup -----------------------------------------------------------------

    def _winner(self, half, connector_id):
        entry = next((e for e in self._entries[half].get(connector_id, ()) if e.active), None)
        if entry is None:
            raise ConnectorError(f"No connector {connector_id!r}; known: {', '.join(self.ids(half)) or 'none'}",
                                 "unsupported")
        if not entry.allowed:
            raise ConnectorError(f"Connector {connector_id!r} is not allowed on this node (connectors.allow)",
                                 "not_allowed")
        return entry.object

    def get(self, connector_id):
        """The active, allowed connector with this id (``ConnectorError`` otherwise)."""
        return self._winner("connectors", connector_id)

    def inputs(self, connector_id):
        """The active, allowed input connector (light half) with this id."""
        return self._winner("inputs", connector_id)

    def ids(self, half="connectors"):
        return sorted(self._entries[half])

    def connectors(self):
        """Active allowed connectors, by id."""
        return [e.object for _, candidates in sorted(self._entries["connectors"].items())
                for e in candidates if e.active and e.allowed]

    def enabled(self):
        """``[{"id", "version"}]`` of the active allowed connectors (reported in the agent snapshot)."""
        return [{"id": c.id, "version": getattr(c, "version", None)} for c in self.connectors()]

    def diagnostics(self):
        """Every candidate (active, shadowed or disallowed) and every load error."""
        return {half: [e.to_json() for _, candidates in sorted(entries.items()) for e in candidates]
                for half, entries in self._entries.items()} | {"errors": list(self._errors)}

    def sniff(self, run):
        """``[(connector, Match)]`` of the allowed connectors that recognize ``run``, best first."""
        found = []
        for connector in self.connectors():
            try:
                match = connector.sniff(run)
            except Exception as exc:  # one connector's sniff must not hide the others
                self._errors.append({"half": "connectors", "reference": connector.id, "source": "sniff",
                                     "error": f"{type(exc).__name__}: {exc}"})
                continue
            if match is not None:
                priority = int(connector.info().get("priority", 0) or 0)
                found.append((match.confidence, priority, connector, match))
        found.sort(key=lambda item: (-item[0], -item[1]))
        return [(connector, match) for _, _, connector, match in found]

    def best(self, run):
        """The best ``(connector, Match)`` for ``run``, or ``None``."""
        matches = self.sniff(run)
        return matches[0] if matches else None


def _entry_points(group):
    try:
        return list(entry_points(group=group))
    except Exception:  # pragma: no cover - broken metadata of an unrelated distribution
        return []


_DEFAULT = {}
_DEFAULT_LOCK = threading.Lock()


def default_registry(*, allow=None):
    """A process-wide registry per allowlist (built-ins and installed entry points)."""
    key = None if allow is None else tuple(allow)
    with _DEFAULT_LOCK:
        registry = _DEFAULT.get(key)
        if registry is None:
            registry = _DEFAULT[key] = ConnectorRegistry(allow=allow)
        return registry
