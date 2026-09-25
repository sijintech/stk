"""Graph methods, the local blob cache, probes and colormaps (spec §9-§10).

Evaluations run in the bridge process (``local`` mode: :func:`suan.graph.service.evaluate_request`
with local directories and/or Runtime task bindings) or on an execution node through the hub
(``hub`` mode: a ``graph.evaluate`` action). Either way every blob the result references ends up
in the bridge's content-addressed cache ``<cache>/blobs/<sha[:2]>/<sha>`` (the layout of the hub
and ``DirectoryBlobSink``), which the app memory-maps.
"""
import base64
from collections import OrderedDict
import hashlib
from pathlib import Path
import re
import threading

from .backends import HubBackend, action_id, summary
from .protocol import BridgeError

__all__ = ["BlobCache", "GraphService"]

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
GRID_CACHE = 2


class BlobCache:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._sink = None

    def path(self, digest):
        if not isinstance(digest, str) or not SHA256_RE.match(digest):
            raise BridgeError("invalid_params", "A blob is named by its sha256: 64 lowercase hexadecimal characters")
        return self.root / digest[:2] / digest

    @property
    def sink(self):
        if self._sink is None:
            from suan.graph.service import DirectoryBlobSink
            self._sink = DirectoryBlobSink(self.root)
        return self._sink

    def describe(self, digest):
        path = self.path(digest)
        try:
            return {"path": str(path), "size": path.stat().st_size}
        except FileNotFoundError:
            return None

    def verify(self, digest):
        """Re-hash a cached blob; a corrupted file is removed (returns False)."""
        path = self.path(digest)
        result = hashlib.sha256()
        with open(path, "rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                result.update(block)
        if result.hexdigest() != digest:
            path.unlink(missing_ok=True)
            return False
        return True


def result_blobs(document):
    """Every sha256 a ``stk.graph-result/1`` document references (buffers, images, plots, files)."""
    found = []

    def add(value):
        if isinstance(value, str) and SHA256_RE.match(value) and value not in found:
            found.append(value)

    for output in (document or {}).get("outputs", {}).values():
        if not isinstance(output, dict):
            continue
        add(output.get("blob"))
        add(output.get("data_blob"))
        manifest = output.get("manifest")
        if isinstance(manifest, dict):
            for buffer in manifest.get("buffers") or ():
                uri = str(buffer.get("uri", ""))
                if uri.startswith("sha256:"):
                    add(uri[7:])
    return found


def _graph_error(exc):
    data = {"graph_code": exc.code}
    issues = getattr(exc, "issues", None)
    if issues:
        data["issues"] = [issue.to_dict() for issue in issues[:50]]
    for key in ("node", "path", "hint"):
        value = getattr(exc, key, None)
        if value:
            data[key] = value
    errors = getattr(exc, "errors", None)
    if errors:
        data["errors"] = errors[:50]
    code = "cancelled" if exc.code == "cancelled" else "graph_error"
    return BridgeError(code, exc.message, data=data)


class GraphService:
    def __init__(self, cache_dir, connections, emit):
        self.cache_dir = Path(cache_dir)
        self.blobs = BlobCache(self.cache_dir / "blobs")
        self.connections = connections
        self.emit = emit
        self.lock = threading.Lock()
        self.running = {}     # eval_id -> {"token": CancelToken | None, "cancelled": Event}
        self.grids = OrderedDict()
        self._registry = None

    # -- catalog ------------------------------------------------------------------------------

    def registry(self):
        if self._registry is None:
            from suan.graph.catalog import default_registry
            self._registry = default_registry()
        return self._registry

    def catalog(self):
        from suan.graph.catalog import catalog_document
        return {"catalog": catalog_document(self.registry())}

    def presets(self):
        from suan.graph.catalog import list_presets
        return {"presets": list_presets(self.registry())}

    def validate(self, graph, parameters=None):
        from suan.graph.schema import validate_graph
        issues = validate_graph(graph, self.registry(), parameters=parameters)
        return {"ok": not any(i.severity == "error" for i in issues), "issues": [i.to_dict() for i in issues]}

    # -- evaluation ---------------------------------------------------------------------------

    def _begin(self, eval_id):
        from suan.graph.registry import CancelToken
        with self.lock:
            if eval_id in self.running:
                raise BridgeError("conflict", f"Evaluation {eval_id!r} is already running")
            entry = {"token": CancelToken(), "cancelled": threading.Event()}
            self.running[eval_id] = entry
        return entry

    def _end(self, eval_id):
        with self.lock:
            self.running.pop(eval_id, None)

    def cancel(self, eval_id):
        with self.lock:
            entry = self.running.get(eval_id)
        if entry is None:
            return {"cancelled": False}
        entry["cancelled"].set()
        entry["token"].cancel("Cancelled by the desktop app")
        return {"cancelled": True}

    def cancel_all(self):
        with self.lock:
            entries = list(self.running.values())
        for entry in entries:
            entry["cancelled"].set()
            entry["token"].cancel("The desktop bridge is shutting down")

    def evaluate(self, params):
        eval_id = params["eval_id"]
        entry = self._begin(eval_id)
        try:
            if params.get("mode", "local") == "hub":
                return self._evaluate_hub(params, entry)
            return self._evaluate_local(params, entry)
        finally:
            self._end(eval_id)

    def _evaluate_local(self, params, entry):
        from suan.graph.registry import GraphError
        from suan.graph.resolve import BindingResolver, LocalDirResolver, RuntimeResolver
        from suan.graph.service import evaluate_request
        request = params["request"]
        local = params.get("local_bindings") or {}
        for name, root in local.items():
            if not Path(root).is_absolute() or not Path(root).is_dir():
                raise BridgeError("invalid_params", f"Local binding '{name}' must name an existing absolute directory")
        resolvers = []
        try:
            if local:
                resolvers.append(LocalDirResolver(local))
            if params.get("connection"):
                backend = self.connections.backend(params["connection"], params.get("node"))
                if backend.kind != "runtime":
                    raise BridgeError("invalid_params", "Local evaluation reads task files from a Runtime "
                                      "connection; use mode 'hub' for hub connections")
                resolvers.append(RuntimeResolver(backend.client, self.cache_dir / "graph" / "downloads"))
            elif request.get("bindings"):
                raise BridgeError("invalid_params", "Task bindings need a Runtime 'connection'")
            resolver = BindingResolver(*resolvers) if resolvers else None
            eval_id = params["eval_id"]

            def progress(event):
                self.emit("graph.progress", {"eval_id": eval_id, "event": _plain_event(event)})

            document = evaluate_request(request, resolver=resolver, cache_dir=self.cache_dir / "graph" / "cache",
                                        blob_sink=self.blobs.sink, registry=self.registry(), cancel=entry["token"],
                                        on_event=progress)
        except GraphError as exc:
            raise _graph_error(exc) from None
        return {"result": document, "blob_dir": str(self.blobs.root)}

    def _evaluate_hub(self, params, entry):
        backend = self.connections.backend(params["connection"], params.get("node"))
        if not isinstance(backend, HubBackend):
            raise BridgeError("invalid_params", "Hub evaluation needs a hub connection and 'node'")
        identity = action_id("graph.evaluate", backend.node_id, params["eval_id"])
        record = backend.run_action("graph.evaluate", params["request"], identity,
                                    wait=float(params.get("wait", 600)), cancel=entry["cancelled"].is_set)
        out = {"action": summary(record), "result": None, "blob_dir": str(self.blobs.root)}
        if record["state"] == "succeeded":
            document = record["result"]
            self.ensure(result_blobs(document), params["connection"], cancel=entry["cancelled"].is_set)
            out["result"] = document
        return out

    # -- blobs --------------------------------------------------------------------------------

    def ensure(self, digests, connection=None, cancel=None):
        hub = None
        blobs, missing = {}, []
        for digest in dict.fromkeys(digests):
            found = self.blobs.describe(digest)
            if found is None and connection:
                if hub is None:
                    if not connection.startswith("hub:"):
                        raise BridgeError("invalid_params", "Blobs are fetched from hub connections only")
                    hub = self.connections.hub_client(connection)

                def check():
                    if cancel is not None and cancel():
                        raise BridgeError("cancelled", "Blob download cancelled")
                try:
                    hub.blob(digest, self.blobs.path(digest), check=check)
                except BridgeError:
                    raise
                except Exception as exc:
                    from .hub import hub_error
                    error = hub_error(exc)
                    if error.code != "not_found":
                        raise error from None
                found = self.blobs.describe(digest)
            if found is None:
                missing.append(digest)
            else:
                blobs[digest] = found
        return {"blobs": blobs, "missing": missing, "blob_dir": str(self.blobs.root)}

    # -- probe --------------------------------------------------------------------------------

    def probe(self, params):
        from suan.graph.probe import FRAME, resolve_probe_target
        graph = params.get("graph")
        if graph is None and params.get("preset"):
            from suan.graph.catalog import load_preset
            from suan.graph.registry import GraphError
            try:
                graph = load_preset(params["preset"])
            except GraphError as exc:
                raise _graph_error(exc) from None
        context = params.get("context") or {}
        local = params.get("local_bindings") or {}
        bindings = {**(context.get("bindings") or {}), **{name: "local" for name in local}}
        artifacts = context.get("artifacts")
        target = resolve_probe_target(graph, params.get("pick"), bindings=bindings, values=context.get("values"),
                                      result=context.get("result"), artifacts=artifacts)
        if "error" in target:
            raise BridgeError("not_found", target["error"], data={"probe_error": True})
        local_root = local.get(target["binding"])
        if local_root is not None:
            target.pop("task_id", None)
            if artifacts is None and FRAME.search(target["path"]):
                target["path"] = _local_frame(Path(local_root), target["path"])
        out = {"target": target}
        position = params.get("position")
        if position is None:
            return out
        metadata = dict(target.get("metadata") or {})
        if local_root is not None:
            from suan.graph.resolve import LocalDirSource
            try:
                path = LocalDirSource(local_root, binding=target["binding"]).local_path(target["path"])
            except Exception as exc:
                raise BridgeError("not_found", f"{type(exc).__name__}: {exc}") from None
            out["sample"] = self._sample(path, target["path"], metadata, position)
            return out
        backend = self.connections.backend(params.get("connection"), params.get("node"))
        if isinstance(backend, HubBackend):
            payload = {"task_id": target["task_id"], "path": target["path"], "position": position}
            if metadata:
                payload["metadata"] = metadata
            identity = action_id("view.probe", backend.node_id, target["task_id"], target["path"], repr(position),
                                 repr(metadata))
            record = backend.run_action("view.probe", payload, identity)
            out["sample"] = record["result"]
            return out
        item = backend.describe("task", target["task_id"], target["path"])
        if item["size"] > 1024 ** 3:
            raise BridgeError("invalid_params", "Probing reads fields of at most 1 GiB")
        path = self.cache_dir / "fields" / (item["sha256"] + Path(target["path"]).suffix)
        backend.call(backend.client.download, target["task_id"], target["path"], path)
        out["sample"] = self._sample(path, target["path"], metadata, position)
        return out

    def _sample(self, path, name, metadata, position):
        from suan.control.agent import frame_metadata
        from suan.visualization.scene import load_grid, probe
        frame = frame_metadata(name)
        if frame:
            metadata.setdefault("field", frame["field"])
            metadata["timestep"] = frame["timestep"]
            if "coordinate_units" not in metadata and "spacing" not in metadata:
                metadata["coordinate_units"] = "grid index"
        stat = Path(path).stat()
        key = (str(path), stat.st_size, stat.st_mtime_ns, repr(sorted(metadata.items())))
        with self.lock:
            grid = self.grids.get(key)
            if grid is not None:
                self.grids.move_to_end(key)
        if grid is None:
            try:
                grid = load_grid(path, **metadata)
            except (ValueError, OSError) as exc:
                raise BridgeError("invalid_params", f"The field cannot be read: {exc}") from None
            with self.lock:
                self.grids[key] = grid
                while len(self.grids) > GRID_CACHE:
                    self.grids.popitem(last=False)
        try:
            sample = probe(grid, position)
        except ValueError as exc:
            raise BridgeError("invalid_params", str(exc)) from None
        from suan.data.model import json_safe
        return json_safe(sample)  # NaN samples become "NaN" (strict JSON)

    # -- colormaps ----------------------------------------------------------------------------

    @staticmethod
    def colormaps():
        from suan.render import colormaps
        return {
            "colormaps": [{"name": name, "lut_rgba8": base64.b64encode(colormaps.lut_rgba8_bytes(name)).decode("ascii")}
                          for name in colormaps.colormap_names()],
            "aliases": dict(colormaps.ALIASES),
            "categorical_palettes": list(colormaps.CATEGORICAL_PALETTES),
            "reserved_colors": {str(k): list(v) for k, v in colormaps.RESERVED_COLORS.items()},
            "nan_color": list(colormaps.DEFAULT_NAN_COLOR),
        }


def _local_frame(root, path):
    """A muFerro frame under a local run directory: ``path`` itself, else the first match one level down."""
    if (root / path).is_file():
        return path
    name = Path(path).name
    for child in sorted(root.iterdir()):
        if child.is_dir() and not child.is_symlink() and (child / name).is_file():
            return f"{child.name}/{name}"
    return path


def _plain_event(event):
    """An evaluator event as plain JSON (finite numbers, string keys)."""
    from suan.data.model import json_safe
    try:
        return json_safe(dict(event))
    except Exception:
        return {"type": str(event.get("type", "event")) if isinstance(event, dict) else "event"}
