"""Node registration API, port-type lattice and evaluator-facing interfaces (stk.graph/1).

Standard library only: the hub builds registries and validates graphs without
NumPy. Node modules must keep heavy imports inside functions.

Declaring a node (the M1 catalog is ``docs/specs/catalog/m1_nodes.py``)::

    from suan.graph.registry import Port, node, boolean, field_ref, number_list

    @node("stk.filter.contour", version=1, impl_version=1,
          title={"en": "Contour", "zh": "等值面"},
          inputs=[Port("in", "dataset", accepts=["image"])],
          outputs=[Port("out", "dataset", kind="polydata")],
          params={"field": field_ref(of="in"),
                  "values": number_list(min_items=1, max_items=32),
                  "compute_normals": boolean(True)},
          cache="disk")
    def contour(ctx, inputs, params):
        ...
        return {"out": polydata}

``node`` only attaches a :class:`NodeType` to the function
(``fn.stk_node_type``); :meth:`Registry.register` collects node types from
functions, modules, lists or callables (the ``stk.nodes`` entry-point objects).

Implementation contract (evaluated by ``suan.graph.evaluator`` in Phase B2):

* ``impl(ctx, inputs, params) -> {port: value}`` (a bare value is accepted when
  the node has exactly one output). ``inputs`` maps input port names to values;
  multi ports get a list in link order; optional unlinked ports are absent.
  ``params`` are normalized (defaults filled, ``$param`` resolved,
  :meth:`NodeType.normalize_params`).
* Stages ``source``/``data``/``analysis`` have only data-stage params.
  Their results are cached by the *data key*.
* Stage ``representation``: ``impl`` receives only data-stage params; its
  result is cached by the data key (unless an input carries a client type, see
  :data:`CLIENT_TYPES`). ``finalize(ctx, outputs, client_params) -> outputs``
  then attaches appearance (default :func:`attach_appearance`); it is cheap
  and never disk-cached.
* Stages ``view``/``output``/``plot``: ``impl`` receives all params and is
  cached by the *full key* (which includes client-stage params upstream).
* ``fingerprint(ctx, inputs, params) -> JSON`` describes the file content a
  node reads (e.g. ``[{"path", "sha256", "reader", "selector"}]``); it becomes
  ``source_content`` in the data key. Required for stage ``source`` unless
  ``cache == "none"``.
* ``meta(ctx, input_metas, params) -> {port: meta}`` is optional (``graph.meta``).
"""
from dataclasses import dataclass, field, fields as dataclass_fields
import inspect
import threading
import types as _types
from typing import Any, Callable, Mapping, Protocol, Sequence, runtime_checkable

from .schema import (ID_RE, GraphError, GraphIssue, GraphValidationError, check_value, normalize_value,
                     parse_type)

__all__ = [
    "CATEGORIES", "CLIENT_TYPES", "DATA_STAGES", "DATASET_KINDS", "DELIVERABLE_TYPES", "PORT_TYPES", "REQUIRED",
    "STAGES", "VALUE_TYPES",
    "Budget", "BudgetExceeded", "CancelToken", "Cancelled", "Evaluate", "EvaluationResult", "GraphError",
    "GraphIssue", "GraphValidationError", "NodeContext", "NodeExecutionError", "NodeType", "Param", "Port",
    "Registry",
    "array", "attach_appearance", "binding", "boolean", "color", "enum", "field_ref", "int3", "integer",
    "interval", "is_subkind", "is_subtype", "json_param", "kinds_compatible", "node", "number", "number_list",
    "ports_compatible", "rel_path", "step", "string", "string_list", "vector3",
]

# ---------------------------------------------------------------------------
# Port-type lattice. Each entry: name -> (parent, description[, implemented in M1]).

PORT_TYPES = {
    "any": (None, "Any value; only for generic utility ports."),
    "dataset": ("any", "In-memory STK dataset (suan.data.model.Dataset); qualified by kind. Never leaves the evaluator."),
    "table": ("dataset", "Table dataset (kind 'table' or a refinement such as 'frames')."),
    "value": ("any", "Small JSON value; qualified by value_type."),
    "field": ("any", "Field selection {name, component}."),
    "colormap": ("any", "Continuous colormap spec (client stage)."),
    "palette": ("any", "Categorical palette spec (client stage)."),
    "transfer_function": ("any", "Volume colour/opacity transfer function (client stage)."),
    "layer": ("any", "Render layer: geometry reference + appearance (output of render nodes)."),
    "camera": ("any", "Camera of an stk.view/1 document."),
    "scene": ("any", "Ordered layers + stk.view/1 view; delivered as an stk.payload/2 payload."),
    "plot": ("any", "stk.plot/1 spec with bound tables."),
    "image": ("any", "Rendered raster (PNG/SVG/PDF blob reference). Unrelated to the dataset kind 'image'."),
    "payload": ("any", "Encoded stk.payload/2 manifest + buffers."),
    "file": ("any", "Exported file (name, media type, sha256, size)."),
}

DATASET_KINDS = {
    "image": (None, "Uniform grid (dims, origin, spacing, direction).", True),
    "labels": ("image", "Image with at least one categorical label field (tensor 'label').", True),
    "rectilinear": (None, "One coordinate array per axis.", False),
    "structured": (None, "Curvilinear grid.", False),
    "unstructured": (None, "Points + typed VTK cells (FEM).", False),
    "polydata": (None, "Vertices, lines, polygons.", True),
    "points": ("polydata", "Polydata with vertices only (glyph sources, samples).", True),
    "particles": (None, "Atoms/particles with optional bonds and periodic cell.", False),
    "table": (None, "Named typed columns.", True),
    "frames": ("table", "Frame index table: dataset, step, time, path, size, sha256, reader, components.", True),
    "collection": (None, "Named tree of datasets.", False),
}

VALUE_TYPES = {
    "json": (None, "Any JSON value."),
    "number": ("json", "Finite number."),
    "integer": ("number", "Integer."),
    "boolean": ("json", "true/false."),
    "string": ("json", "String."),
    "vector3": ("json", "[x, y, z] numbers."),
    "range": ("json", "[min|null, max|null]."),
}

# Port types whose values depend on client-stage params; a node consuming one is keyed by its full key.
CLIENT_TYPES = frozenset({"layer", "camera", "scene", "plot", "image", "payload", "colormap", "palette",
                          "transfer_function"})
# Port types a graph output may deliver.
DELIVERABLE_TYPES = frozenset({"dataset", "table", "value", "scene", "plot", "image", "payload", "file"})
# Node family (the middle segment of a type id) -> stage.
CATEGORIES = {"source": "source", "filter": "data", "analysis": "analysis", "render": "representation",
              "view": "view", "output": "output", "plot": "plot"}
STAGES = ("source", "data", "analysis", "representation", "view", "output", "plot")
DATA_STAGES = frozenset({"source", "data", "analysis"})
DISK_CACHEABLE_TYPES = frozenset({"dataset", "table", "value"})


def _is_below(child, parent, lattice):
    seen = set()
    while child is not None and child not in seen:
        if child == parent:
            return True
        seen.add(child)
        child = lattice[child][0] if child in lattice else None
    return False


def is_subtype(child, parent):
    """Port-type lattice: ``is_subtype("table", "dataset")`` is True; everything is below ``any``."""
    return _is_below(child, parent, PORT_TYPES)


def is_subkind(child, parent):
    """Dataset-kind lattice: ``is_subkind("labels", "image")`` and ``is_subkind("frames", "table")``."""
    return _is_below(child, parent, DATASET_KINDS)


def kinds_compatible(out_kinds, accepts):
    """Static check: True if at least one possible output kind is a subkind of an accepted kind.

    ``None`` on either side means "unknown / any". The evaluator re-checks the
    actual kind at run time (``Dataset.kinds()``).
    """
    if not out_kinds or not accepts:
        return True
    return any(is_subkind(kind, accepted) for kind in out_kinds for accepted in accepts)


def ports_compatible(out_port, in_port, out_kinds=None):
    """Can ``out_port`` (an output) feed ``in_port`` (an input)?

    ``out_kinds`` overrides ``out_port.kinds`` (resolved ``kind_from``).
    """
    in_types = in_port.types
    if not any(is_subtype(out_port.type, accepted) for accepted in in_types):
        return False
    if out_port.type in ("dataset", "table") and any(t in ("dataset", "table") for t in in_types):
        accepts = in_port.accepts
        if accepts is None and "table" in in_types and "dataset" not in in_types:
            accepts = ("table",)
        kinds = out_kinds if out_kinds is not None else out_port.kinds
        if not kinds_compatible(kinds, accepts):
            return False
    if out_port.value_type and in_port.value_type:
        return _is_below(out_port.value_type, in_port.value_type, VALUE_TYPES)
    return True


# ---------------------------------------------------------------------------
# Ports


def _text(value):
    if value is None:
        return None
    if isinstance(value, str):
        return {"en": value}
    if not isinstance(value, Mapping) or "en" not in value:
        raise ValueError("Text must be a string or {'en': ..., 'zh': ...}")
    return dict(value)


def _tuple(value):
    if value is None:
        return None
    return (value,) if isinstance(value, str) else tuple(value)


@dataclass(frozen=True)
class Port:
    """An input or output port.

    ``type`` is a port type (inputs may give a tuple = union). ``accepts``
    (inputs) lists dataset kinds; ``kind`` (outputs) is a kind or a tuple of
    possible kinds; ``kind_from`` (outputs) copies the kind of whatever is linked
    to that input port. ``multi`` inputs take a list of links (ordered).
    """

    name: str
    type: Any
    accepts: Any = None
    kind: Any = None
    kind_from: str | None = None
    value_type: str | None = None
    required: bool = True
    multi: bool = False
    title: Any = None
    description: Any = None

    def __post_init__(self):
        object.__setattr__(self, "type", self.type if isinstance(self.type, str) else tuple(self.type))
        object.__setattr__(self, "accepts", _tuple(self.accepts))
        if self.kind is not None and not isinstance(self.kind, str):
            object.__setattr__(self, "kind", tuple(self.kind))
        object.__setattr__(self, "title", _text(self.title))
        object.__setattr__(self, "description", _text(self.description))

    @property
    def types(self):
        return (self.type,) if isinstance(self.type, str) else tuple(self.type)

    @property
    def kinds(self):
        """Possible kinds of an output (tuple) or ``None`` when unknown."""
        if self.kind is not None:
            return _tuple(self.kind)
        if self.type == "table":
            return ("table",)
        return None

    def validate(self, *, output):
        if not isinstance(self.name, str) or not ID_RE.match(self.name):
            raise ValueError(f"Port name {self.name!r} must match ^[a-z][a-z0-9_]{{0,63}}$")
        for name in self.types:
            if name not in PORT_TYPES:
                raise ValueError(f"Port {self.name!r}: unknown port type {name!r}")
        if output and not isinstance(self.type, str):
            raise ValueError(f"Output {self.name!r}: outputs have exactly one port type")
        for kind in (self.accepts or ()) + (_tuple(self.kind) or ()):
            if kind not in DATASET_KINDS:
                raise ValueError(f"Port {self.name!r}: unknown dataset kind {kind!r}")
        dataset_like = any(t in ("dataset", "table") for t in self.types)
        if (self.accepts or self.kind or self.kind_from) and not dataset_like:
            raise ValueError(f"Port {self.name!r}: kinds only apply to dataset/table ports")
        if output and (self.accepts or self.multi or not self.required):
            raise ValueError(f"Output {self.name!r}: 'accepts', 'multi' and 'required' are input-only")
        if not output and (self.kind or self.kind_from):
            raise ValueError(f"Input {self.name!r}: 'kind' and 'kind_from' are output-only")
        if self.value_type is not None:
            if self.value_type not in VALUE_TYPES:
                raise ValueError(f"Port {self.name!r}: unknown value_type {self.value_type!r}")
            if "value" not in self.types:
                raise ValueError(f"Port {self.name!r}: value_type needs port type 'value'")

    def to_json(self, *, output):
        result = {"name": self.name, "type": self.type if isinstance(self.type, str) else list(self.type)}
        if output:
            if self.kind is not None:
                result["kind"] = self.kind if isinstance(self.kind, str) else list(self.kind)
            if self.kind_from:
                result["kind_from"] = self.kind_from
        else:
            if self.accepts:
                result["accepts"] = list(self.accepts)
            result["required"] = self.required
            result["multi"] = self.multi
        if self.value_type:
            result["value_type"] = self.value_type
        if self.title:
            result["title"] = dict(self.title)
        if self.description:
            result["description"] = dict(self.description)
        return result

    @classmethod
    def from_json(cls, data, *, output):
        allowed = {"name", "type", "title", "description", "value_type"} | (
            {"kind", "kind_from"} if output else {"accepts", "required", "multi"})
        unknown = set(data) - allowed
        if unknown:
            raise ValueError(f"Unknown port keys: {', '.join(sorted(unknown))}")
        return cls(**{key: data[key] for key in data})


# ---------------------------------------------------------------------------
# Parameters


class _Required:
    def __repr__(self):
        return "REQUIRED"


REQUIRED = _Required()

_ANNOTATIONS = {
    "widget": "x-stk-widget", "field_of": "x-stk-field-of", "unit": "x-stk-unit", "quantity": "x-stk-quantity",
    "group": "x-stk-group", "advanced": "x-stk-advanced", "choices_from": "x-stk-choices-from",
}


@dataclass
class Param:
    """A node parameter: a JSON Schema fragment, a default and a stage.

    ``stage`` is ``"data"`` (changing it re-runs this node and everything
    downstream) or ``"client"`` (appearance only; never re-runs data-stage
    nodes). ``None`` means the node's default: ``client`` for view/output nodes,
    ``data`` otherwise. ``normalize`` maps a valid value to its canonical form.
    """

    schema: dict
    default: Any = REQUIRED
    stage: str | None = None
    normalize: Callable | None = None

    @property
    def required(self):
        return self.default is REQUIRED

    def fragment(self, stage):
        result = dict(self.schema)
        if not self.required:
            result["default"] = self.default
        result["x-stk-stage"] = stage
        return result

    def canonical(self, value):
        value = normalize_value(value, self.schema)
        return self.normalize(value) if self.normalize else value


def _param(schema, default, *, nullable=False, stage=None, title=None, description=None, normalize=None, **ann):
    schema = dict(schema)
    if nullable:
        schema = {"anyOf": [schema, {"type": "null"}]}
    if title is not None:
        text = _text(title)
        schema["title"] = text["en"]
        if "zh" in text:
            schema["x-stk-title-zh"] = text["zh"]
    if description is not None:
        schema["description"] = description
    for key, value in ann.items():
        if key not in _ANNOTATIONS:
            raise TypeError(f"Unknown parameter annotation {key!r}")
        if value is not None:
            schema[_ANNOTATIONS[key]] = value
    if stage not in (None, "data", "client"):
        raise ValueError("Parameter stage must be 'data' or 'client'")
    if isinstance(default, tuple):
        default = list(default)
    return Param(schema, default, stage, normalize)


def number(default=REQUIRED, *, minimum=None, maximum=None, exclusive_minimum=None, exclusive_maximum=None, **kw):
    schema = {"type": "number"}
    for key, value in (("minimum", minimum), ("maximum", maximum), ("exclusiveMinimum", exclusive_minimum),
                       ("exclusiveMaximum", exclusive_maximum)):
        if value is not None:
            schema[key] = value
    return _param(schema, default, **kw)


def integer(default=REQUIRED, *, minimum=None, maximum=None, **kw):
    schema = {"type": "integer"}
    if minimum is not None:
        schema["minimum"] = minimum
    if maximum is not None:
        schema["maximum"] = maximum
    return _param(schema, default, **kw)


def boolean(default=REQUIRED, **kw):
    return _param({"type": "boolean"}, default, **kw)


def string(default=REQUIRED, *, pattern=None, min_length=None, max_length=None, **kw):
    schema = {"type": "string"}
    if pattern is not None:
        schema["pattern"] = pattern
    if min_length is not None:
        schema["minLength"] = min_length
    if max_length is not None:
        schema["maxLength"] = max_length
    return _param(schema, default, **kw)


def enum(choices, default=REQUIRED, **kw):
    return _param({"enum": list(choices)}, default, **kw)


def vector3(default=REQUIRED, **kw):
    return _param({"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3}, default,
                  **{"widget": "vector3", **kw})


def int3(default=REQUIRED, *, minimum=None, maximum=None, **kw):
    items = {"type": "integer"}
    if minimum is not None:
        items["minimum"] = minimum
    if maximum is not None:
        items["maximum"] = maximum
    return _param({"type": "array", "items": items, "minItems": 3, "maxItems": 3}, default,
                  **{"widget": "int3", **kw})


def color(default=REQUIRED, *, alpha=False, **kw):
    return _param({"type": "array", "items": {"type": "number", "minimum": 0, "maximum": 1}, "minItems": 3,
                   "maxItems": 4 if alpha else 3}, default, **{"widget": "color", **kw})


def interval(default=(None, None), **kw):
    """``[lo, hi]`` with ``null`` meaning unbounded / automatic."""
    return _param({"type": "array", "prefixItems": [{"type": ["number", "null"]}, {"type": ["number", "null"]}],
                   "minItems": 2, "maxItems": 2}, default, **{"widget": "range", **kw})


def array(items, default=REQUIRED, *, min_items=None, max_items=None, unique=False, **kw):
    schema = {"type": "array", "items": items}
    if min_items is not None:
        schema["minItems"] = min_items
    if max_items is not None:
        schema["maxItems"] = max_items
    if unique:
        schema["uniqueItems"] = True
    return _param(schema, default, **kw)


def number_list(default=REQUIRED, *, min_items=None, max_items=None, **kw):
    return array({"type": "number"}, default, min_items=min_items, max_items=max_items, **kw)


def string_list(default=REQUIRED, *, min_items=None, max_items=None, **kw):
    return array({"type": "string", "minLength": 1}, default, min_items=min_items, max_items=max_items, **kw)


FIELD_NAME = {"type": "string", "pattern": "^[^/.]{1,128}$"}
COMPONENT = {"anyOf": [{"type": "integer", "minimum": 0}, {"const": "magnitude"}, {"type": "null"}]}


def field_ref(default=REQUIRED, *, of="in", component=True, **kw):
    """A field of the dataset linked to input ``of``: ``"Polar"`` or ``{"name": "Polar", "component": 0|"magnitude"|null}``.

    Normalized to the object form (``component`` filled with ``null``, or
    omitted when ``component=False``).
    """
    obj = {"type": "object", "required": ["name"], "properties": {"name": FIELD_NAME}, "additionalProperties": False}
    if component:
        obj["properties"]["component"] = COMPONENT
    return _param({"anyOf": [FIELD_NAME, obj]}, default, normalize=_field_normalizer(component),
                  **{"widget": "field", "field_of": of, **kw})


def _field_normalizer(component):
    def normalize(value):
        if value is None:
            return None
        value = {"name": value} if isinstance(value, str) else dict(value)
        if component:
            value.setdefault("component", None)
        return value
    return normalize


def _has_component(schema):
    """Does a field_ref schema fragment (possibly nullable) allow a 'component' key?"""
    if isinstance(schema, dict):
        if "component" in (schema.get("properties") or {}):
            return True
        return any(_has_component(sub) for sub in schema.get("anyOf", ()))
    return False


def step(default="latest", **kw):
    """A time step selector: an integer step >= 0, ``"latest"`` or ``"first"``."""
    return _param({"anyOf": [{"type": "integer", "minimum": 0}, {"enum": ["latest", "first"]}]}, default,
                  **{"widget": "step", "choices_from": "evaluator", **kw})


def binding(default=REQUIRED, **kw):
    """Name of a caller-resolved binding (``{task_id}`` or a local directory); never a path."""
    return _param({"type": "string", "pattern": "^[a-z][a-z0-9_]{0,63}$"}, default, **{"widget": "binding", **kw})


REL_PATH_PATTERN = r"^(?![/\\])(?![A-Za-z]:)(?!.*(^|/)\.\.(/|$))[^\\\u0000]+$"


def rel_path(default=REQUIRED, **kw):
    """A relative path inside a binding: no leading '/', no drive letter, no '..' segment, no backslash."""
    return _param({"type": "string", "minLength": 1, "maxLength": 1024, "pattern": REL_PATH_PATTERN}, default,
                  **{"widget": "path", **kw})


def json_param(schema, default=REQUIRED, **kw):
    """A structured parameter validated by an explicit JSON Schema fragment (subset in suan.graph.schema)."""
    return _param(schema, default, **{"widget": "json", **kw})


# ---------------------------------------------------------------------------
# Node types


def attach_appearance(ctx, outputs, client_params):
    """Default ``finalize`` for representation nodes.

    For each ``layer`` output: a dict gets ``{"appearance": {...client params}}``
    merged in; an object with ``with_appearance(dict)`` is asked to return an
    updated copy. Other outputs pass through.
    """
    node_type = getattr(ctx, "node_type", None)
    layer_ports = {p.name for p in node_type.outputs if p.type == "layer"} if node_type else set(outputs)
    result = {}
    for name, value in outputs.items():
        if name in layer_ports and client_params:
            if isinstance(value, dict):
                value = {**value, "appearance": {**value.get("appearance", {}), **client_params}}
            elif hasattr(value, "with_appearance"):
                value = value.with_appearance(dict(client_params))
            else:
                raise TypeError(f"Cannot attach appearance to {type(value).__name__}; give the node a finalize()")
        result[name] = value
    return result


@dataclass
class NodeType:
    """A registered node type. ``id`` is ``"<type>@<version>"``."""

    type: str
    version: int = 1
    impl_version: int = 1
    title: Any = None
    description: Any = None
    inputs: tuple = ()
    outputs: tuple = ()
    params: dict = field(default_factory=dict)
    stage: str | None = None
    time_dependent: bool = False
    deterministic: bool = True
    cache: str = "memory"
    impl: Callable | None = None
    impl_ref: str | None = None
    finalize: Callable | None = None
    fingerprint: Callable | None = None
    meta: Callable | None = None
    tags: tuple = ()
    stretch: bool = False

    def __post_init__(self):
        self.inputs = tuple(self.inputs)
        self.outputs = tuple(self.outputs)
        self.params = dict(self.params or {})
        self.tags = tuple(self.tags)
        self.title = _text(self.title) or {"en": self.type}
        self.description = _text(self.description)
        namespace, family, name = self.type.split(".") if self.type.count(".") == 2 else (None, None, None)
        if family not in CATEGORIES:
            raise ValueError(f"Node type {self.type!r} must be 'namespace.family.name' with family in "
                             f"{', '.join(CATEGORIES)}")
        derived = CATEGORIES[family]
        if self.stage is None:
            self.stage = derived
        elif self.stage != derived:
            raise ValueError(f"Node type {self.type!r}: stage {self.stage!r} contradicts family {family!r}")
        if self.impl is not None and self.impl_ref is None:
            self.impl_ref = f"{self.impl.__module__}:{self.impl.__qualname__}"
        if (self.stage == "representation" and self.finalize is None
                and any(self.param_stage(n) == "client" for n in self.params)):
            self.finalize = attach_appearance
        self.validate()

    @property
    def id(self):
        return f"{self.type}@{self.version}"

    @property
    def category(self):
        return self.type.split(".")[1]

    @property
    def namespace(self):
        return self.type.split(".")[0]

    def input(self, name):
        return next((port for port in self.inputs if port.name == name), None)

    def output(self, name):
        return next((port for port in self.outputs if port.name == name), None)

    def param_stage(self, name):
        param = self.params[name]
        if param.stage is not None:
            return param.stage
        return "client" if self.stage in ("view", "output") else "data"

    @property
    def keyed_by_data(self):
        """True if results are cached by the data key; False if by the full key."""
        if self.stage in ("view", "output", "plot"):
            return False
        return not any(t in CLIENT_TYPES for port in self.inputs for t in port.types)

    def validate(self):
        parse_type(self.id)
        for name in ("version", "impl_version"):
            value = getattr(self, name)
            if type(value) is not int or value < 1:
                raise ValueError(f"{self.type}: {name} must be a positive integer")
        if not self.outputs:
            raise ValueError(f"{self.id}: a node needs at least one output")
        for group, output in ((self.inputs, False), (self.outputs, True)):
            names = [port.name for port in group]
            if len(set(names)) != len(names):
                raise ValueError(f"{self.id}: duplicate port names in {'outputs' if output else 'inputs'}")
            for port in group:
                if not isinstance(port, Port):
                    raise TypeError(f"{self.id}: ports must be Port instances")
                port.validate(output=output)
        for port in self.outputs:
            if port.kind_from:
                source = self.input(port.kind_from)
                if source is None or not any(t in ("dataset", "table") for t in source.types):
                    raise ValueError(f"{self.id}: output {port.name!r} kind_from must name a dataset/table input")
        for name, param in self.params.items():
            if not isinstance(name, str) or not ID_RE.match(name):
                raise ValueError(f"{self.id}: parameter name {name!r} must match ^[a-z][a-z0-9_]{{0,63}}$")
            if not isinstance(param, Param):
                raise TypeError(f"{self.id}: parameter {name!r} must be a Param (use the helper functions)")
            if not param.required:
                problems = check_value(param.default, param.schema)
                if problems:
                    raise ValueError(f"{self.id}: default of {name!r} is invalid: {problems[0][1]}")
            if self.stage in DATA_STAGES and self.param_stage(name) == "client":
                raise ValueError(f"{self.id}: {self.stage}-stage nodes cannot have client-stage params ({name!r})")
        if self.cache not in ("memory", "disk", "none"):
            raise ValueError(f"{self.id}: cache must be 'memory', 'disk' or 'none'")
        if self.cache == "disk":
            if not self.deterministic:
                raise ValueError(f"{self.id}: non-deterministic nodes cannot use the disk cache")
            if any(port.type not in DISK_CACHEABLE_TYPES for port in self.outputs):
                raise ValueError(f"{self.id}: disk cache only for dataset/table/value outputs")
        if self.stage == "source" and self.fingerprint is None and self.cache != "none" and self.impl is not None:
            raise ValueError(f"{self.id}: source nodes need a fingerprint() (or cache='none')")

    # -- parameters ---------------------------------------------------------

    def defaults(self):
        return {name: param.default for name, param in self.params.items() if not param.required}

    def normalize_params(self, params):
        """Fill defaults and normalize values (params must already be valid and ``$param``-free)."""
        result = {}
        for name, param in self.params.items():
            if name in params:
                result[name] = param.canonical(params[name])
            elif not param.required:
                result[name] = param.canonical(param.default)
            else:
                raise GraphError("missing_param", f"{self.id} needs param '{name}'")
        unknown = set(params) - set(self.params)
        if unknown:
            raise GraphError("unknown_param", f"{self.id} has no param(s) {', '.join(sorted(unknown))}")
        return result

    def split_params(self, params):
        """``(data_params, client_params)`` of a normalized params dict."""
        data, client = {}, {}
        for name, value in params.items():
            (client if self.param_stage(name) == "client" else data)[name] = value
        return data, client

    def wrap_outputs(self, result):
        """Normalize an ``impl`` return value to ``{port: value}``."""
        names = [port.name for port in self.outputs]
        if isinstance(result, Mapping) and set(result) == set(names):
            return dict(result)
        if len(names) == 1 and not (isinstance(result, Mapping) and set(result) == set(names)):
            return {names[0]: result}
        got = ", ".join(sorted(result)) if isinstance(result, Mapping) else type(result).__name__
        raise GraphError("bad_outputs", f"{self.id} must return outputs {', '.join(names)}; got {got}")

    # -- JSON ---------------------------------------------------------------

    def params_schema(self):
        return {
            "type": "object",
            "properties": {name: param.fragment(self.param_stage(name)) for name, param in self.params.items()},
            "required": [name for name, param in self.params.items() if param.required],
            "additionalProperties": False,
        }

    def to_json(self, *, include_impl=True):
        result = {
            "id": self.id, "type": self.type, "version": self.version, "impl_version": self.impl_version,
            "stage": self.stage, "category": self.category, "title": dict(self.title),
        }
        if self.description:
            result["description"] = dict(self.description)
        result.update({
            "inputs": [port.to_json(output=False) for port in self.inputs],
            "outputs": [port.to_json(output=True) for port in self.outputs],
            "params": self.params_schema(),
            "time_dependent": self.time_dependent, "deterministic": self.deterministic, "cache": self.cache,
        })
        if include_impl and self.impl_ref:
            result["impl"] = self.impl_ref
        if self.tags:
            result["tags"] = list(self.tags)
        if self.stretch:
            result["stretch"] = True
        return result

    @classmethod
    def from_json(cls, data):
        """Rebuild a declaration-only node type (no impl) from a catalog entry."""
        params = {}
        schema = data.get("params") or {}
        required = set(schema.get("required", ()))
        for name, fragment in (schema.get("properties") or {}).items():
            fragment = dict(fragment)
            stage = fragment.pop("x-stk-stage")
            default = fragment.pop("default", REQUIRED)
            if name in required:
                default = REQUIRED
            normalize = None
            if fragment.get("x-stk-widget") == "field":
                normalize = _field_normalizer(_has_component(fragment))
            params[name] = Param(fragment, default, stage, normalize)
        type_name = data["type"]
        if data.get("id") not in (None, f"{type_name}@{data['version']}"):
            raise ValueError(f"Catalog entry id {data.get('id')!r} does not match type and version")
        return cls(
            type=type_name, version=data["version"], impl_version=data.get("impl_version", 1),
            title=data.get("title"), description=data.get("description"),
            inputs=[Port.from_json(port, output=False) for port in data.get("inputs", ())],
            outputs=[Port.from_json(port, output=True) for port in data.get("outputs", ())],
            params=params, stage=data.get("stage"), time_dependent=data.get("time_dependent", False),
            deterministic=data.get("deterministic", True), cache=data.get("cache", "memory"),
            impl_ref=data.get("impl"), tags=data.get("tags", ()), stretch=data.get("stretch", False),
        )


def node(type, *, version=1, impl_version=1, title=None, description=None, inputs=(), outputs=(), params=None,
         stage=None, time_dependent=False, deterministic=True, cache="memory", finalize=None, fingerprint=None,
         meta=None, tags=(), stretch=False, registry=None):
    """Decorator declaring a node type; attaches ``fn.stk_node_type`` (and registers into ``registry`` if given)."""
    def decorate(fn):
        node_type = NodeType(type=type, version=version, impl_version=impl_version, title=title,
                             description=description, inputs=inputs, outputs=outputs, params=params or {},
                             stage=stage, time_dependent=time_dependent, deterministic=deterministic, cache=cache,
                             impl=fn, finalize=finalize, fingerprint=fingerprint, meta=meta, tags=tags,
                             stretch=stretch)
        fn.stk_node_type = node_type
        if registry is not None:
            registry.register(node_type)
        return fn
    return decorate


class Registry:
    """Node types by id (``"stk.filter.contour@1"``).

    ``namespaces`` maps a namespace to its catalog version (graph documents
    may require a minimum with ``"catalog": {"stk": 1}``).
    """

    def __init__(self, nodes=(), *, namespaces=None):
        self._nodes = {}
        self.namespaces = dict(namespaces or {})
        for item in nodes:
            self.register(item)

    def register(self, obj, *, replace=False):
        """Register a NodeType, a decorated function, a module, an iterable of those, or a callable returning them.

        Returns the registered node types. Duplicate ids raise ``ValueError``
        unless ``replace=True`` (used for higher-priority private packages).
        """
        added = []
        for node_type in _collect(obj):
            if node_type.id in self._nodes and not replace:
                raise ValueError(f"Node type {node_type.id} is already registered")
            self._nodes[node_type.id] = node_type
            self.namespaces.setdefault(node_type.namespace, 1)
            added.append(node_type)
        return added

    def node(self, type, **kw):
        """Decorator: declare and register a node type in this registry."""
        return node(type, registry=self, **kw)

    def get(self, type_ref):
        return self._nodes.get(type_ref)

    def __getitem__(self, type_ref):
        try:
            return self._nodes[type_ref]
        except KeyError:
            raise KeyError(f"Unknown node type {type_ref!r}") from None

    def __contains__(self, type_ref):
        return type_ref in self._nodes

    def __iter__(self):
        return iter(self._nodes[key] for key in sorted(self._nodes))

    def __len__(self):
        return len(self._nodes)

    def types(self):
        return sorted(self._nodes)

    def catalog(self, *, include_impl=False):
        """The ``stk.catalog/1`` document (validates against node-type-1 ``$defs/catalog``)."""
        return {
            "schema": "stk.catalog/1",
            "generated_by": "suan.graph.registry",
            "namespaces": dict(sorted(self.namespaces.items())),
            "port_types": {name: {"parent": parent, "description": text}
                           for name, (parent, text) in PORT_TYPES.items()},
            "kinds": {name: {"parent": parent, "description": text, "implemented": implemented}
                      for name, (parent, text, implemented) in DATASET_KINDS.items()},
            "value_types": {name: {"parent": parent, "description": text}
                            for name, (parent, text) in VALUE_TYPES.items()},
            "client_types": sorted(CLIENT_TYPES),
            "nodes": [node_type.to_json(include_impl=include_impl) for node_type in self],
        }

    @classmethod
    def from_catalog(cls, document):
        """Declaration-only registry from an exported catalog (enough for :func:`validate_graph`)."""
        if document.get("schema") != "stk.catalog/1":
            raise ValueError("Not an stk.catalog/1 document")
        registry = cls(namespaces=document.get("namespaces"))
        for entry in document.get("nodes", ()):
            registry.register(NodeType.from_json(entry))
        return registry


def _collect(obj):
    if isinstance(obj, NodeType):
        return [obj]
    if hasattr(obj, "stk_node_type"):
        return [obj.stk_node_type]
    if isinstance(obj, _types.ModuleType):
        found = [value.stk_node_type for value in vars(obj).values()
                 if hasattr(value, "stk_node_type") and getattr(value, "__module__", None) == obj.__name__]
        return sorted(found, key=lambda t: _source_line(t))
    if isinstance(obj, (list, tuple)):
        return [item for element in obj for item in _collect(element)]
    if callable(obj):
        return _collect(obj())
    raise TypeError(f"Cannot register {type(obj).__name__} as node types")


def _source_line(node_type):
    try:
        return inspect.getsourcelines(node_type.impl)[1]
    except (TypeError, OSError):
        return 0


# ---------------------------------------------------------------------------
# Evaluator-facing interfaces. The implementation is suan.graph.evaluator (Phase B2).


@dataclass(frozen=True)
class Budget:
    """Limits for one evaluation. ``None`` = unlimited. ``profile`` selects payload budgets (phone/web/desktop)."""

    max_seconds: float | None = 300.0
    max_memory_mb: int | None = None
    max_output_bytes: int | None = None
    profile: str = "web"


class Cancelled(GraphError):
    def __init__(self, message="Evaluation cancelled", **kw):
        super().__init__("cancelled", message, **kw)


class BudgetExceeded(GraphError):
    def __init__(self, message="Evaluation budget exceeded", **kw):
        super().__init__("budget_exceeded", message, **kw)


class NodeExecutionError(GraphError):
    """A node failed; ``code`` is the node's own error code (default ``node_failed``)."""

    def __init__(self, message, *, code="node_failed", **kw):
        super().__init__(code, message, **kw)


class CancelToken:
    """Thread-safe cancellation flag shared by the caller and the evaluator."""

    def __init__(self):
        self._event = threading.Event()
        self.reason = ""

    def cancel(self, reason=""):
        self.reason = reason
        self._event.set()

    @property
    def cancelled(self):
        return self._event.is_set()

    def raise_if_cancelled(self):
        if self._event.is_set():
            raise Cancelled(self.reason or "Evaluation cancelled")


@runtime_checkable
class NodeContext(Protocol):
    """What a node implementation may use (provided by the evaluator)."""

    node_id: str
    node_type: NodeType
    budget: Budget
    cancel: CancelToken
    parameters: Mapping[str, Any]      # effective graph parameter values
    cache_dir: Any                     # pathlib.Path for large intermediates, or None

    @property
    def data_key(self) -> str: ...     # this node's data cache key (hex)

    def resolve(self, binding: str) -> Any: ...
        # -> suan.connectors.api.FileSource for a binding name; GraphError("unknown_binding") otherwise

    def check(self) -> None: ...
        # raise Cancelled / BudgetExceeded; call between chunks of long work

    def progress(self, fraction: float | None = None, message: str = "") -> None: ...

    def warn(self, message: str, *, code: str = "node_warning", **details: Any) -> None: ...

    def report_choices(self, param: str, choices: Sequence[Any], *, value: Any = None) -> None: ...
        # e.g. report_choices("step", [0, 100, 200], value=200) -> EvaluationResult.parameters

    def cached(self, name: str, compute: Callable[[], Any], *, disk: bool = False) -> Any: ...
        # memoize an intermediate under (data_key, name)


@dataclass
class EvaluationResult:
    """Result of one evaluation (in-memory values; ``suan.graph.service`` serializes them)."""

    graph_hash: str
    outputs: dict = field(default_factory=dict)        # output name -> value
    output_types: dict = field(default_factory=dict)   # output name -> port type
    parameters: dict = field(default_factory=dict)     # name -> {"value": v, "choices": [...]}
    keys: dict = field(default_factory=dict)           # node id -> {"data": hex, "full": hex}
    evaluated: list = field(default_factory=list)      # node ids whose impl ran (cache misses), in order
    timings: dict = field(default_factory=dict)        # node id -> seconds
    cache: dict = field(default_factory=lambda: {"hits": 0, "misses": 0})
    warnings: list = field(default_factory=list)       # GraphIssue.to_dict() entries (severity "warning")

    def to_json(self):
        return {name.name: getattr(self, name.name) for name in dataclass_fields(self) if name.name != "outputs"}


class Evaluate(Protocol):
    """Signature of ``suan.graph.evaluator.evaluate`` (Phase B2).

    Validates first (raising :class:`GraphValidationError`), evaluates only the
    ancestors of the requested ``outputs`` (default: all graph outputs) in
    topological order, checks ``cancel`` and ``budget`` between nodes, and
    reuses ``cache`` entries by data/full key. ``resolver`` maps binding names
    to :class:`suan.connectors.api.FileSource`. ``on_event`` receives dicts
    ``{"type": "node.started"|"node.finished"|"node.cached"|"progress"|"warning", "node": id, ...}``.
    """

    def __call__(self, graph: Mapping[str, Any], *, registry: Registry, resolver: Any,
                 outputs: Sequence[str] | None = None, parameters: Mapping[str, Any] | None = None,
                 cache: Any = None, budget: Budget | None = None, cancel: CancelToken | None = None,
                 on_event: Callable[[dict], None] | None = None) -> EvaluationResult: ...
