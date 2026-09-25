"""Evaluate a graph request and serialize the result as ``stk.graph-result/1``.

Shared by the node agent (action ``graph.evaluate``), MCP tools and the CLI::

    evaluate_request({"graph": {...} | "preset": "muferro-domains",
                      "bindings": {"run": {"task_id": "..."}}, "parameters": {"step": 200},
                      "outputs": ["payload", "image", "fractions", "energy_plot"], "profile": "web"},
                     resolver=RuntimeResolver(client, downloads_dir), cache_dir=cache_dir, blob_sink=upload)

returns (the Hub API of the Milestone-1 decisions)::

    {"schema": "stk.graph-result/1", "graph_sha256": "<hex>", "graph_hash": "sha256:<hex>",
     "outputs": {"<name>": {"type": "payload", "manifest": {stk.payload/2, buffers "uri": "sha256:<hex>"}}
                         | {"type": "image", "blob": "<sha256>", "media_type": "image/png", "width", "height", "size"}
                         | {"type": "table", "columns": {...}, "units": {...}, "attrs": {...}}
                         | {"type": "table", "blob": "<sha256>", "media_type": "application/json", "size", "rows"}
                         | {"type": "plot", "blob": "<sha256>", "media_type": "image/svg+xml" | "image/png",
                            "data_blob": "<sha256>", "size"}
                         | {"type": "value", "value": ...} | {"type": "dataset", "descriptor": {...}}
                         | {"type": "file", "name", "media_type", "blob": "<sha256>", "size"}},
     "parameters": {"step": {"value": 200, "choices": [0, 100, 200]}}, "timings": {node: s},
     "cache": {"hits", "misses"}, "warnings": [...], "keys": {...}, "evaluated": [...], "profile": "web",
     "errors": [...]  # only when some requested outputs failed and others were delivered}

Blobs (payload buffers, images, plots, file exports, tables and values over
256 KiB) go through ``blob_sink(data) -> sha256 hex``, where ``data`` is bytes or
a local file path; the result only references them by sha256. ``scene``
outputs are delivered as payloads encoded for the request profile.

``budget.max_output_bytes`` limits the delivered bytes (blobs plus the result
document); it defaults to the request profile's payload budget (phone 32 MiB,
web 128 MiB, desktop 2 GiB; docs/specs/stk-render-payload-v2.md §7). The
evaluation itself runs without an output-byte limit, since in-memory values
(e.g. a full-resolution scene) are reduced when they are encoded.

Request bindings only name Runtime tasks (``{"task_id": ...}``); requests never
carry filesystem paths. ``resolver`` is bound to them with
``resolver.bind(bindings)`` (``RuntimeResolver``) when it supports that.

Delivering scenes and plots needs the render/plot packages (Phase B3). The
defaults call ``suan.render.payload.encode_scene(scene, profile=..., budget=...)``
(returning a payload value) and ``suan.plot.mpl.render_plot(plot, format=...)``
(returning ``{"bytes", "media_type", "data"}``); both can be injected
(``encode_scene=``, ``render_plot=``). A payload value is a mapping or object
with ``manifest`` (stk.payload/2) and ``buffers`` (``{sha256: bytes}`` or a list
in manifest order), optionally ``scene_v1``.
"""
from collections.abc import Mapping, Sequence
import dataclasses
import hashlib
import json
import os
from pathlib import Path
import threading
import uuid

from .cache import GraphCache, plain_json, sub_key
from .evaluator import EvaluationFailed, evaluate
from .registry import Budget, BudgetExceeded, GraphError
from .schema import ID_RE, GraphIssue, parse_port_ref

__all__ = [
    "INLINE_LIMIT", "PROFILE_OUTPUT_BYTES", "PROFILES", "RESULT_SCHEMA",
    "DirectoryBlobSink", "MemoryBlobSink", "evaluate_request", "parse_request", "shared_cache",
]

RESULT_SCHEMA = "stk.graph-result/1"
PROFILES = ("phone", "web", "desktop")
INLINE_LIMIT = 256 * 1024
DEFAULT_MAX_SECONDS = 300.0
DEFAULT_MAX_OUTPUT_BYTES = 128 * 1024**2
# Default delivery limits per request profile (docs/specs/stk-render-payload-v2.md §7, "bytes").
PROFILE_OUTPUT_BYTES = {"phone": 32 * 1024**2, "web": DEFAULT_MAX_OUTPUT_BYTES, "desktop": 2 * 1024**3}
REQUEST_KEYS = frozenset({"graph", "preset", "bindings", "parameters", "outputs", "profile", "budget",
                          "plot_format", "accept"})
PLOT_FORMATS = {"svg": "image/svg+xml", "png": "image/png"}

_caches = {}
_caches_lock = threading.Lock()


def shared_cache(cache_dir=None, **options):
    """One :class:`GraphCache` per cache directory per process, so the memory tier survives across requests."""
    key = str(Path(cache_dir).expanduser().resolve()) if cache_dir is not None else None
    with _caches_lock:
        if key not in _caches:
            _caches[key] = GraphCache(key, **options)
        return _caches[key]


# ---------------------------------------------------------------------------
# Blob sinks


def _digest(data):
    if isinstance(data, (bytes, bytearray, memoryview)):
        return hashlib.sha256(data).hexdigest(), len(memoryview(data).cast("B"))
    result, size = hashlib.sha256(), 0
    with open(data, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
            size += len(block)
    return result.hexdigest(), size


class MemoryBlobSink:
    """Keeps blobs in memory (``blobs[sha] = bytes``); for tests and small tools."""

    def __init__(self):
        self.blobs = {}

    def __call__(self, data):
        if not isinstance(data, (bytes, bytearray, memoryview)):
            data = Path(data).read_bytes()
        data = bytes(data)
        digest = hashlib.sha256(data).hexdigest()
        self.blobs.setdefault(digest, data)
        return digest


class DirectoryBlobSink:
    """Content-addressed files ``<root>/<sha[:2]>/<sha>`` written atomically (idempotent)."""

    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)

    def path(self, digest):
        return self.root / digest[:2] / digest

    def __call__(self, data):
        digest, _ = _digest(data)
        target = self.path(digest)
        if target.is_file():
            return digest
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        tmp = target.with_name(f".{digest}.{uuid.uuid4().hex}.tmp")
        try:
            if isinstance(data, (bytes, bytearray, memoryview)):
                tmp.write_bytes(bytes(data))
            else:
                with open(data, "rb") as source, open(tmp, "wb") as stream:
                    for block in iter(lambda: source.read(1024 * 1024), b""):
                        stream.write(block)
            os.replace(tmp, target)
        finally:
            tmp.unlink(missing_ok=True)
        return digest


# ---------------------------------------------------------------------------
# Requests


def _bad(message, hint=None):
    return GraphError("bad_request", message, hint=hint)


def parse_request(payload):
    """Validate a ``graph.evaluate`` payload; returns a normalized copy (``GraphError('bad_request')``)."""
    if not isinstance(payload, Mapping):
        raise _bad("The request must be a JSON object")
    unknown = sorted(set(payload) - REQUEST_KEYS)
    if unknown:
        raise _bad(f"Unknown request key(s): {', '.join(unknown)}", hint=f"Allowed: {', '.join(sorted(REQUEST_KEYS))}")
    if ("graph" in payload) == ("preset" in payload):
        raise _bad("Give exactly one of 'graph' or 'preset'")
    request = {"graph": payload.get("graph"), "preset": payload.get("preset")}
    if request["graph"] is not None and not isinstance(request["graph"], Mapping):
        raise _bad("'graph' must be an stk.graph/1 object")
    if request["preset"] is not None and not isinstance(request["preset"], str):
        raise _bad("'preset' must be a preset id")
    bindings = payload.get("bindings") or {}
    if not isinstance(bindings, Mapping):
        raise _bad("'bindings' must be an object {name: {\"task_id\": ...}}")
    for name, value in bindings.items():
        if not isinstance(name, str) or not ID_RE.match(name):
            raise _bad(f"Invalid binding name {name!r}")
        if not isinstance(value, Mapping) or set(value) != {"task_id"} or not isinstance(value["task_id"], str):
            raise _bad(f"Binding '{name}' must be {{\"task_id\": \"...\"}}",
                       hint="Requests never carry filesystem paths")
    request["bindings"] = {name: dict(value) for name, value in bindings.items()}
    parameters = payload.get("parameters") or {}
    if not isinstance(parameters, Mapping):
        raise _bad("'parameters' must be an object {name: value}")
    request["parameters"] = dict(parameters)
    outputs = payload.get("outputs")
    if outputs is not None and (isinstance(outputs, (str, bytes)) or not isinstance(outputs, Sequence)
                                or not all(isinstance(o, str) for o in outputs)):
        raise _bad("'outputs' must be a list of graph output names")
    request["outputs"] = list(dict.fromkeys(outputs)) if outputs is not None else None
    profile = payload.get("profile", "web")
    if profile not in PROFILES:
        raise _bad(f"'profile' must be one of {', '.join(PROFILES)}")
    request["profile"] = profile
    plot_format = payload.get("plot_format", "svg")
    if plot_format not in PLOT_FORMATS:
        raise _bad(f"'plot_format' must be one of {', '.join(PLOT_FORMATS)}")
    request["plot_format"] = plot_format
    budget = payload.get("budget") or {}
    if not isinstance(budget, Mapping) or set(budget) - {"max_seconds", "max_memory_mb", "max_output_bytes"}:
        raise _bad("'budget' may only set max_seconds, max_memory_mb and max_output_bytes")
    for key, value in budget.items():
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0):
            raise _bad(f"Budget '{key}' must be a positive number or null")
    request["budget"] = dict(budget)
    return request


def _budget(request):
    """The request's limits; ``max_output_bytes`` (default: per profile) limits the *delivered* bytes."""
    limits = {"max_seconds": DEFAULT_MAX_SECONDS, "max_memory_mb": None,
              "max_output_bytes": PROFILE_OUTPUT_BYTES[request["profile"]]}
    limits.update(request["budget"])
    if limits["max_memory_mb"] is not None:
        limits["max_memory_mb"] = int(limits["max_memory_mb"])
    if limits["max_output_bytes"] is not None:
        limits["max_output_bytes"] = int(limits["max_output_bytes"])
    return Budget(profile=request["profile"], **limits)


def _bind(resolver, bindings):
    if not bindings:
        return resolver
    if resolver is None or not hasattr(resolver, "bind"):
        raise _bad("This service cannot resolve task bindings (no Runtime resolver)")
    return resolver.bind(bindings)


def evaluate_request(payload, *, resolver, cache_dir, blob_sink, registry=None, cache=None, cancel=None,
                     on_event=None, encode_scene=None, render_plot=None):
    """Evaluate one request and return the ``stk.graph-result/1`` document (plain JSON).

    Raises :class:`GraphError` subclasses: ``bad_request``, graph validation
    (``GraphValidationError`` with ``issues``), ``cancelled``,
    ``budget_exceeded``, node errors (when no requested output could be
    delivered), ``unsupported`` (a scene/plot output without the render/plot
    packages).
    """
    request = parse_request(payload)
    if registry is None:
        from .catalog import default_registry
        registry = default_registry()
    graph = request["graph"]
    if graph is None:
        from .catalog import load_preset
        graph = load_preset(request["preset"])
    graph = dict(graph)
    resolver = _bind(resolver, request["bindings"])
    cache = cache if cache is not None else shared_cache(cache_dir)
    budget = _budget(request)
    for attempt in range(2):
        errors, skipped = [], []
        try:
            # The byte limit applies to what is delivered (blobs + the result document, checked below), not to
            # the in-memory outputs: a scene holds full-resolution arrays that encoding reduces to the profile.
            result = evaluate(graph, registry=registry, resolver=resolver, outputs=request["outputs"],
                              parameters=request["parameters"], cache=cache,
                              budget=dataclasses.replace(budget, max_output_bytes=None), cancel=cancel,
                              on_event=on_event)
        except EvaluationFailed as exc:
            if not exc.partial.outputs:
                raise
            result, errors, skipped = exc.partial, exc.errors, exc.skipped
        stale = _stale_files(graph, result)
        if not stale or attempt:
            break
        # An export file of a cached value was pruned from the scratch space: forget it and evaluate again
        # (only the export nodes re-run).
        for key in stale:
            cache.discard(key, disk=False)
    keys, nodes = {}, {}
    for name in result.outputs:
        node_id, port = parse_port_ref(graph["outputs"][name])
        nodes[name] = node_id
        if node_id in result.keys:
            keys[name] = f"{result.keys[node_id]['full']}:{port}"
    delivery = _Delivery(blob_sink, profile=request["profile"], plot_format=request["plot_format"],
                         max_bytes=budget.max_output_bytes, encode_scene=encode_scene, render_plot=render_plot,
                         cache=cache, keys=keys, nodes=nodes)
    outputs = {}
    for name, value in result.outputs.items():
        outputs[name] = delivery.deliver(name, result.output_types[name], value)
    digest = result.graph_hash.split(":", 1)[-1]
    document = {
        "schema": RESULT_SCHEMA, "graph_sha256": digest, "graph_hash": result.graph_hash, "outputs": outputs,
        "parameters": result.parameters,
        "timings": {node: round(seconds, 6) for node, seconds in result.timings.items()},
        "cache": dict(result.cache), "warnings": _merge_warnings(result.warnings, delivery.warnings),
        "keys": result.keys,
        "evaluated": list(result.evaluated), "profile": request["profile"],
    }
    if errors:
        document["errors"] = [{**error, "skipped": skipped} if index == 0 and skipped else error
                              for index, error in enumerate(errors)]
    document = _json_safe(document)
    size = len(json.dumps(document, allow_nan=False, ensure_ascii=False).encode("utf-8"))
    if budget.max_output_bytes is not None and delivery.bytes + size > budget.max_output_bytes:
        raise BudgetExceeded(f"The result needs {delivery.bytes + size} bytes; the budget is "
                             f"{budget.max_output_bytes} bytes")
    return document


def _merge_warnings(*groups):
    merged = []
    for group in groups:
        for issue in group:
            if issue not in merged:
                merged.append(issue)
    return merged


def _stale_files(graph, result):
    """Full keys of the nodes whose ``file`` outputs name a local path that no longer exists."""
    stale = []
    for name, value in result.outputs.items():
        if result.output_types.get(name) != "file" or _get(value, "bytes") is not None:
            continue
        path = _get(value, "path")
        if path is not None and not Path(path).is_file():
            node_id, _ = parse_port_ref(graph["outputs"][name])
            if node_id in result.keys:
                stale.append(result.keys[node_id]["full"])
    return stale


# ---------------------------------------------------------------------------
# Delivery of output values


def _json_safe(value):
    from suan.data.model import json_safe
    return json_safe(value)


def _dumps(value):
    return json.dumps(_json_safe(value), allow_nan=False, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _get(value, key, default=None):
    if isinstance(value, Mapping):
        return value.get(key, default)
    return getattr(value, key, default)


class _Delivery:
    def __init__(self, sink, *, profile, plot_format, max_bytes, encode_scene, render_plot, cache=None, keys=None,
                 nodes=None):
        self.sink = sink
        self.nodes = nodes or {}  # output name -> node id
        self.warnings = []        # issues found while delivering (GraphIssue.to_dict() form)
        self.profile = profile
        self.plot_format = plot_format
        self.max_bytes = max_bytes
        self.encode_scene = encode_scene
        self.render_plot = render_plot
        self.cache = cache
        self.keys = keys or {}   # output name -> "<full key of its node>:<port>"
        self.bytes = 0
        self._name = None

    def blob(self, data, size=None, expected=None):
        is_path = isinstance(data, os.PathLike)
        if size is None:
            size = Path(data).stat().st_size if is_path else len(memoryview(data).cast("B"))
        if self.max_bytes is not None and self.bytes + size > self.max_bytes:
            raise BudgetExceeded(f"Delivering the outputs needs more than {self.max_bytes} bytes")
        digest = self.sink(Path(data) if is_path else data)
        if not isinstance(digest, str) or (expected is not None and digest != expected):
            raise GraphError("bad_outputs", f"The blob sink returned {digest!r}; expected sha256 {expected}")
        self.bytes += size
        return digest

    def deliver(self, name, port_type, value):
        method = getattr(self, "_" + port_type, None)
        if method is None:
            raise GraphError("bad_output", f"Output '{name}' has type '{port_type}', which cannot be delivered")
        self._name = name
        try:
            return method(value)
        except GraphError as exc:
            if not exc.path:
                exc.path = f"/outputs/{name}"
            raise
        except Exception as exc:
            raise GraphError("bad_outputs", f"Output '{name}' ({port_type}) cannot be delivered: "
                             f"{type(exc).__name__}: {exc}", path=f"/outputs/{name}") from exc

    def _payload(self, value):
        manifest = _get(value, "manifest")
        if not isinstance(manifest, Mapping) or manifest.get("schema") != "stk.payload/2":
            raise GraphError("bad_outputs", "A payload value needs an stk.payload/2 'manifest'")
        manifest = json.loads(_dumps(plain_json(manifest)))
        buffers = _get(value, "buffers")
        entries = manifest.get("buffers") or []
        if isinstance(buffers, Mapping):
            lookup = dict(buffers)
        elif isinstance(buffers, Sequence) and not isinstance(buffers, (bytes, bytearray)):
            if len(buffers) != len(entries):
                raise GraphError("bad_outputs", "Payload buffers do not match the manifest")
            lookup = {entry.get("sha256"): data for entry, data in zip(entries, buffers)}
        else:
            lookup = {}
        for entry in entries:
            digest = entry.get("sha256")
            data = lookup.get(digest)
            if data is None:
                if str(entry.get("uri", "")).startswith("sha256:"):
                    continue  # already stored by the producer
                raise GraphError("bad_outputs", f"Payload buffer {digest} has no bytes")
            size = len(memoryview(data).cast("B"))
            if entry.get("byteLength") not in (None, size):
                raise GraphError("bad_outputs", f"Payload buffer {digest} has {size} bytes, manifest says "
                                 f"{entry.get('byteLength')}")
            self.blob(data, size, expected=digest)
            entry["uri"] = "sha256:" + digest
        result = {"type": "payload", "manifest": manifest}
        scene_v1 = _get(value, "scene_v1")
        if scene_v1 is not None:
            result["scene_v1"] = _json_safe(plain_json(scene_v1))
        return result

    def _scene(self, value):
        encode = self.encode_scene or _default_encode_scene
        payload = encode(value, profile=self.profile, budget=None)
        # The profile budget reduced layers: say so, as stk.output.payload@1 does (code payload_reduced).
        manifest = _get(payload, "manifest")
        budget = manifest.get("budget") if isinstance(manifest, Mapping) else None
        for reduction in (budget.get("reductions") if isinstance(budget, Mapping) else None) or ():
            if not isinstance(reduction, Mapping):
                continue
            issue = GraphIssue("payload_reduced", f"Layer {reduction.get('layer')!r}: {reduction.get('reason')}",
                               f"/outputs/{self._name}", self.nodes.get(self._name), None, "warning").to_dict()
            details = {k: reduction[k] for k in ("layer", "from", "to") if k in reduction}
            if details:
                issue["details"] = _json_safe(details)
            if issue not in self.warnings:
                self.warnings.append(issue)
        return self._payload(payload)

    def _image(self, value):
        data = _get(value, "bytes")
        if data is None:
            raise GraphError("bad_outputs", "An image value needs 'bytes'")
        digest = self.blob(data, expected=_get(value, "sha256"))
        result = {"type": "image", "blob": digest, "media_type": _get(value, "media_type", "image/png"),
                  "size": len(memoryview(data).cast("B"))}
        for key in ("width", "height"):
            if _get(value, key) is not None:
                result[key] = int(_get(value, key))
        return result

    def _rendered(self, kind, render):
        """``render()`` memoized in the cache's memory tier by the output's full key, ``kind`` and the renderer."""
        key = self.keys.get(self._name)
        if self.cache is None or key is None:
            return render()
        renderer = self.render_plot or _default_render_plot
        key = sub_key(key, f"delivery:{kind}:{getattr(renderer, '__module__', '')}."
                           f"{getattr(renderer, '__qualname__', type(renderer).__name__)}")
        hit = self.cache.get(key, disk=False)
        if hit is not None:
            return dict(hit.value)
        rendered = render()
        self.cache.put(key, dict(rendered), disk=False)
        return rendered

    def _plot(self, value):
        render = self.render_plot or _default_render_plot

        def run():
            rendered = render(value, format=self.plot_format)
            if isinstance(rendered, (tuple, list)):
                rendered = dict(zip(("bytes", "media_type", "data"), rendered))
            return dict(rendered)
        # A warm request re-delivers the same bytes without rendering the plot again (~0.3 s with matplotlib).
        rendered = self._rendered(f"plot:{self.plot_format}", run)
        data = rendered.get("bytes")
        if data is None:
            raise GraphError("bad_outputs", "The plot renderer returned no bytes")
        result = {"type": "plot", "blob": self.blob(data),
                  "media_type": rendered.get("media_type") or PLOT_FORMATS[self.plot_format],
                  "size": len(memoryview(data).cast("B"))}
        if rendered.get("data") is not None:
            result["data_blob"] = self.blob(_dumps(rendered["data"]))
        return result

    def _table(self, value):
        if not hasattr(value, "to_json"):
            raise GraphError("bad_outputs", f"A table output must be a Table, got {type(value).__name__}")
        document = _json_safe(value.to_json())
        attrs = _json_safe(getattr(value, "attrs", None) or {})
        # The table's column order, explicitly: JSON object order does not survive every store or client.
        names = [str(name) for name in (document.get("columns") or {})]
        encoded = _dumps(document)
        if len(encoded) > INLINE_LIMIT:
            return {"type": "table", "blob": self.blob(encoded), "media_type": "application/json",
                    "size": len(encoded), "rows": int(getattr(value, "n_rows", 0) or 0), "column_names": names}
        result = {"type": "table", "column_names": names, "columns": document["columns"],
                  "units": document.get("units", {})}
        if attrs:
            result["attrs"] = attrs
        return result

    def _value(self, value):
        encoded = _dumps(plain_json(value))
        if len(encoded) > INLINE_LIMIT:
            return {"type": "value", "blob": self.blob(encoded), "media_type": "application/json",
                    "size": len(encoded)}
        return {"type": "value", "value": json.loads(encoded)}

    def _dataset(self, value):
        if not hasattr(value, "descriptor"):
            raise GraphError("bad_outputs", f"A dataset output must be a Dataset, got {type(value).__name__}")
        return {"type": "dataset", "descriptor": _json_safe(value.descriptor())}

    def _file(self, value):
        data, path = _get(value, "bytes"), _get(value, "path")
        if data is None and path is None:
            raise GraphError("bad_outputs", "A file value needs 'bytes' or a local 'path'")
        source = data if data is not None else Path(path)
        digest = self.blob(source, expected=_get(value, "sha256"))
        size = len(memoryview(data).cast("B")) if data is not None else Path(path).stat().st_size
        name = _get(value, "name") or (Path(path).name if path else "export")
        return {"type": "file", "name": str(name),
                "media_type": _get(value, "media_type") or "application/octet-stream", "blob": digest, "size": size}


def _default_encode_scene(scene, *, profile, budget=None):
    try:
        from suan.render.payload import encode_scene
    except ImportError as exc:
        raise GraphError("unsupported", f"Delivering a scene output needs suan.render.payload.encode_scene ({exc})",
                         hint="Deliver a payload output (stk.output.payload@1) or install the render package") from None
    return encode_scene(scene, profile=profile, budget=budget)


def _default_render_plot(plot, *, format="svg"):
    try:
        from suan.plot.mpl import render_plot
    except ImportError as exc:
        raise GraphError("unsupported", f"Delivering a plot output needs suan.plot.mpl.render_plot ({exc})",
                         hint="Render the plot with stk.output.image@1, or install the plot package") from None
    return render_plot(plot, format=format)
