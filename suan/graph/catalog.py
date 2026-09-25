"""Node catalogs and presets.

* :func:`build_registry` / :func:`default_registry`: the built-in node types
  (``suan.graph.nodes``) plus third-party packages registered under the
  ``stk.nodes`` entry-point group. Entry points load after the built-ins with
  ``replace=True`` (a private package such as ``stk-mupro`` may override a
  built-in type), in entry-point name order; a plugin that fails to load is
  reported in ``registry.load_errors`` and skipped, so one broken plugin cannot
  take down the catalog.
* :func:`compare_catalog`: the live catalog against the frozen spec catalog
  (``docs/specs/catalog/stk-catalog-m1.json``), family by family.
* :func:`list_presets` / :func:`load_preset`: graph templates shipped in
  ``suan/graph/presets/<id>.json`` (either an ``stk.graph/1`` document or
  ``{"id", "name", "description", "graph", "bindings"?}``).

Standard library only; importing node modules must not import NumPy.
"""
from importlib import metadata, resources
import json
from pathlib import Path
import re
import threading

from .nodes import MODULE_FAMILIES, builtin_modules, register_builtin
from .registry import Registry
from .schema import GraphError

__all__ = [
    "ENTRY_POINT_GROUP", "NAMESPACES", "PRESET_ID_RE",
    "build_registry", "catalog_document", "compare_catalog", "default_registry", "list_presets",
    "load_entry_points", "load_preset", "present_families", "spec_catalog", "spec_catalog_path",
]

NAMESPACES = {"stk": 1}
ENTRY_POINT_GROUP = "stk.nodes"
PRESET_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}\Z")

_default = None
_default_lock = threading.Lock()


def load_entry_points(registry, group=ENTRY_POINT_GROUP):
    """Register the node types of every ``group`` entry point; returns ``[(name, error message)]`` failures."""
    try:
        found = metadata.entry_points(group=group)
    except Exception as exc:  # broken distribution metadata
        return [("*", f"{type(exc).__name__}: {exc}")]
    failures = []
    for entry in sorted(found, key=lambda e: (e.name, e.value)):
        try:
            registry.register(entry.load(), replace=True)
        except Exception as exc:
            failures.append((entry.name, f"{type(exc).__name__}: {exc}"))
    return failures


def build_registry(*, builtins=True, entry_points=True):
    """A new :class:`Registry` with the built-in node types and the ``stk.nodes`` plugins."""
    registry = Registry(namespaces=NAMESPACES)
    if builtins:
        register_builtin(registry)
    registry.load_errors = load_entry_points(registry) if entry_points else []
    return registry


def default_registry(*, refresh=False):
    """The process-wide registry (built once; ``refresh=True`` rebuilds it)."""
    global _default
    with _default_lock:
        if _default is None or refresh:
            _default = build_registry()
        return _default


def catalog_document(registry=None, *, include_impl=False):
    """The ``stk.catalog/1`` document (``suan graph catalog --json``, ``GET /api/v1/graphs/catalog``)."""
    return (registry or default_registry()).catalog(include_impl=include_impl)


def present_families():
    """Node families whose built-in module is installed (e.g. ``{"source", "view"}``)."""
    names = {module.__name__.rsplit(".", 1)[-1] for module in builtin_modules()}
    return {MODULE_FAMILIES[name] for name in names}


def spec_catalog_path():
    """``docs/specs/catalog/stk-catalog-m1.json`` of a source checkout, or ``None`` (not shipped in wheels)."""
    path = Path(__file__).resolve().parents[2] / "docs" / "specs" / "catalog" / "stk-catalog-m1.json"
    return path if path.is_file() else None


def spec_catalog():
    path = spec_catalog_path()
    return json.loads(path.read_text(encoding="utf-8")) if path else None


def _family(entry):
    return entry["id"].split(".")[1]


def _strip(entry):
    return {key: value for key, value in entry.items() if key != "impl"}


def compare_catalog(live, spec, *, families=None):
    """Differences between two ``stk.catalog/1`` documents, restricted to ``families`` (default: all).

    Every spec entry of those families must exist in ``live`` with the same
    declaration (``impl`` ignored), except ``stretch`` entries, which may be
    absent; ``live`` must not declare extra ``stk`` types in those families.
    Returns a list of human-readable problems (empty = in sync).
    """
    problems = []
    live_nodes = {entry["id"]: entry for entry in live.get("nodes", ())}
    spec_nodes = {entry["id"]: entry for entry in spec.get("nodes", ())}
    for key in ("port_types", "kinds", "value_types", "client_types"):
        if live.get(key) != spec.get(key):
            problems.append(f"catalog '{key}' differs from the spec")
    for node_id, entry in sorted(spec_nodes.items()):
        if families is not None and _family(entry) not in families:
            continue
        if node_id not in live_nodes:
            if not entry.get("stretch"):
                problems.append(f"{node_id}: missing")
            continue
        if _strip(live_nodes[node_id]) != _strip(entry):
            keys = sorted(k for k in set(_strip(entry)) | set(_strip(live_nodes[node_id]))
                          if _strip(entry).get(k) != _strip(live_nodes[node_id]).get(k))
            problems.append(f"{node_id}: declaration differs from the spec ({', '.join(keys)})")
    for node_id, entry in sorted(live_nodes.items()):
        in_scope = families is None or _family(entry) in families
        if node_id.startswith("stk.") and node_id not in spec_nodes and in_scope:
            problems.append(f"{node_id}: not in the spec catalog")
    return problems


# ---------------------------------------------------------------------------
# Presets


def _presets_root():
    return resources.files("suan.graph").joinpath("presets")


def _read_preset(preset_id):
    if not isinstance(preset_id, str) or not PRESET_ID_RE.match(preset_id):
        raise GraphError("unknown_preset", f"Invalid preset id {preset_id!r}")
    resource = _presets_root().joinpath(preset_id + ".json")
    if not resource.is_file():
        known = ", ".join(entry["id"] for entry in _preset_files()) or "none installed"
        raise GraphError("unknown_preset", f"Unknown preset '{preset_id}'", hint=f"Presets: {known}")
    document = json.loads(resource.read_text(encoding="utf-8"))
    if isinstance(document, dict) and document.get("schema") == "stk.graph/1":
        return {"id": preset_id, "graph": document}
    if isinstance(document, dict) and isinstance(document.get("graph"), dict):
        return {**document, "id": preset_id}
    raise GraphError("unknown_preset", f"Preset '{preset_id}' is neither an stk.graph/1 document nor "
                     "{\"graph\": {...}}")


def _preset_files():
    root = _presets_root()
    try:
        entries = sorted(root.iterdir(), key=lambda entry: entry.name)
    except (FileNotFoundError, NotADirectoryError):
        return []
    return [{"id": entry.name[:-5]} for entry in entries
            if entry.name.endswith(".json") and PRESET_ID_RE.match(entry.name[:-5])]


def load_preset(preset_id):
    """The ``stk.graph/1`` document of a shipped preset (``GraphError('unknown_preset')`` otherwise)."""
    return _read_preset(preset_id)["graph"]


def _bindings(graph, registry):
    found = []
    for node in graph.get("nodes") or ():
        node_type = registry.get(node.get("type")) if registry is not None else None
        for name, value in (node.get("params") or {}).items():
            widget = None
            if node_type is not None and name in node_type.params:
                widget = node_type.params[name].schema.get("x-stk-widget")
            if (widget == "binding" or (node_type is None and name == "binding")) and isinstance(value, str):
                if value not in found:
                    found.append(value)
    return found


def list_presets(registry=None):
    """``[{"id", "name", "description", "graph", "bindings": [{"name", "description"}], "parameters"}]``."""
    registry = registry if registry is not None else default_registry()
    result = []
    for item in _preset_files():
        preset = _read_preset(item["id"])
        graph = preset["graph"]
        described = {b.get("name"): b.get("description", "") for b in preset.get("bindings") or ()
                     if isinstance(b, dict)}
        result.append({
            "id": preset["id"],
            "name": preset.get("name") or graph.get("name") or preset["id"],
            "description": preset.get("description") or graph.get("description") or "",
            "graph": graph,
            "bindings": [{"name": name, "description": described.get(name, "")}
                         for name in _bindings(graph, registry)],
            "parameters": graph.get("parameters") or [],
        })
    return result
