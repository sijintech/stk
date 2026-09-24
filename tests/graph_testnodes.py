"""Test-local node types and graphs for the graph evaluator, cache, service and CLI tests.

They use only the public registration API and suan.data.model, so the tests do
not depend on the built-in node modules of other phases. ``registry.runs``
counts impl calls per node id.
"""
from collections import Counter
import copy
import hashlib
import json
import re
import time

import numpy as np

from suan.data.model import ImageData, Table, TimeInfo
from suan.graph.registry import GraphError, Port, Registry, binding, enum, number, rel_path, step, string

FRAME_RE = re.compile(r"^(?P<dataset>[A-Za-z]+)\.(?P<step>\d{8})\.npy$")
STEPS = (0, 100, 200)


def write_run(directory, steps=STEPS, dataset="P"):
    """A fake run directory: ``P.<step:08d>.npy`` frames of shape (z, y, x, 3) = (2, 3, 4, 3)."""
    directory.mkdir(parents=True, exist_ok=True)
    for index, value in enumerate(steps):
        array = np.arange(2 * 3 * 4 * 3, dtype=np.float64).reshape(2, 3, 4, 3) * (index + 1)
        np.save(directory / f"{dataset}.{value:08d}.npy", array)
    (directory / "notes.txt").write_text("not a frame", encoding="utf-8")
    return directory


def _pick(frames, params):
    datasets, steps, paths = frames.column("dataset"), frames.column("step"), frames.column("path")
    rows = sorted((int(s), str(p)) for d, s, p in zip(datasets, steps, paths) if str(d) == params["dataset"])
    if not rows:
        raise GraphError("frame_not_found", f"No frames of {params['dataset']!r}")
    available = [s for s, _ in rows]
    wanted = params["step"]
    if wanted == "latest":
        chosen = available[-1]
    elif wanted == "first":
        chosen = available[0]
    else:
        earlier = [s for s in available if s <= wanted]
        if not earlier:
            raise GraphError("frame_not_found", f"No frame at or before step {wanted}")
        chosen = earlier[-1]
    return chosen, dict(rows)[chosen], available


def make_registry(runs=None):
    """A fresh registry with the ``test.*`` node types."""
    runs = runs if runs is not None else Counter()
    registry = Registry(namespaces={"test": 1})
    registry.runs = runs
    node = registry.node

    def frames_fingerprint(ctx, inputs, params):
        source = ctx.resolve(params["binding"])
        return [[f.path, f.size] for f in source.list() if FRAME_RE.match(f.path)]

    @node("test.source.frames", outputs=[Port("frames", "table", kind="frames")], params={"binding": binding()},
          time_dependent=True, fingerprint=frames_fingerprint)
    def frames(ctx, inputs, params):
        runs[ctx.node_id] += 1
        rows = []
        for info in ctx.resolve(params["binding"]).list():
            match = FRAME_RE.match(info.path)
            if match:
                rows.append((match["dataset"], int(match["step"]), info.path))
        rows.sort()
        table = Table.from_columns({"dataset": np.array([r[0] for r in rows], dtype=str),
                                    "step": np.array([r[1] for r in rows], dtype=np.int64),
                                    "path": np.array([r[2] for r in rows], dtype=str)}, id="frames")
        table.attrs["binding"] = params["binding"]
        return table

    def frame_fingerprint(ctx, inputs, params):
        chosen, path, _ = _pick(inputs["frames"], params)
        source = ctx.resolve(inputs["frames"].attrs["binding"])
        return {"path": path, "sha256": source.sha256(path), "reader": "npy"}

    @node("test.source.frame", inputs=[Port("frames", "table", accepts=["frames"])],
          outputs=[Port("out", "dataset", kind="image")],
          params={"dataset": string("P"), "step": step("latest")}, time_dependent=True,
          fingerprint=frame_fingerprint, cache="disk")
    def frame(ctx, inputs, params):
        runs[ctx.node_id] += 1
        chosen, path, available = _pick(inputs["frames"], params)
        ctx.report_choices("step", available, value=chosen)
        with ctx.resolve(inputs["frames"].attrs["binding"]).open(path) as stream:
            values = np.load(stream, allow_pickle=False)
        image = ImageData((values.shape[2], values.shape[1], values.shape[0]), id=params["dataset"],
                          length_unit="grid_index", time=TimeInfo(step=chosen))
        image.add_field(params["dataset"], values, tensor="vector", unit="unspecified")
        return image

    def file_fingerprint(ctx, inputs, params):
        return {"path": params["path"], "sha256": ctx.resolve(params["binding"]).sha256(params["path"])}

    @node("test.source.file", outputs=[Port("out", "value", value_type="json")],
          params={"binding": binding(), "path": rel_path()}, fingerprint=file_fingerprint)
    def file_source(ctx, inputs, params):
        runs[ctx.node_id] += 1
        with ctx.resolve(params["binding"]).open(params["path"]) as stream:
            data = stream.read()
        return {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()}

    @node("test.filter.scale", inputs=[Port("in", "dataset", accepts=["image"])],
          outputs=[Port("out", "dataset", kind_from="in")],
          params={"field": string("P"), "factor": number(1.0),
                  "mode": enum(["ok", "fail", "missing", "inplace", "cached"], "ok")})
    def scale(ctx, inputs, params):
        runs[ctx.node_id] += 1
        image = inputs["in"]
        values = image.array(params["field"])
        if params["mode"] == "fail":
            raise ValueError("synthetic failure")
        if params["mode"] == "missing":
            ctx.resolve("nowhere")
        if params["mode"] == "inplace":
            values[...] = 0
        if params["mode"] == "cached":
            def compute():
                runs[ctx.node_id + ".norm"] += 1
                return np.abs(values).max(axis=(0, 1, 2))
            ctx.cached("norm", compute, disk=True)
        image.add_field(params["field"] + "_scaled", values * params["factor"], tensor="vector")
        return image

    @node("test.filter.slow", inputs=[Port("in", "dataset", accepts=["image"])],
          outputs=[Port("out", "dataset", kind_from="in")], params={"steps": number(20.0), "delay": number(0.01)})
    def slow(ctx, inputs, params):
        runs[ctx.node_id] += 1
        count = int(params["steps"])
        for index in range(count):
            ctx.check()
            ctx.progress(index / count, f"chunk {index}")
            time.sleep(params["delay"])
        return inputs["in"]

    @node("test.filter.maybe_labels", inputs=[Port("in", "dataset", accepts=["image"])],
          outputs=[Port("out", "dataset", kind=["image", "labels"])], params={"wrong": enum(["no", "yes"], "no")})
    def maybe_labels(ctx, inputs, params):
        runs[ctx.node_id] += 1
        return Table.from_columns({"x": np.arange(3)}) if params["wrong"] == "yes" else inputs["in"]

    @node("test.analysis.count_labels", inputs=[Port("in", "dataset", accepts=["labels"])],
          outputs=[Port("out", "value", value_type="json")])
    def count_labels(ctx, inputs, params):
        runs[ctx.node_id] += 1
        return {"labels": len(inputs["in"].label_fields())}

    @node("test.analysis.stats", inputs=[Port("in", "dataset", accepts=["image"])], outputs=[Port("out", "table")],
          params={"field": string("P")}, cache="disk")
    def stats(ctx, inputs, params):
        runs[ctx.node_id] += 1
        values = inputs["in"].array(params["field"])
        ctx.warn("synthetic statistics warning", code="test_warning", count=int(values.size))
        return Table.from_columns({"stat": np.array(["min", "max", "mean"]),
                                   "value": np.array([values.min(), values.max(), values.mean()])},
                                  units={"value": "unspecified"}, id="stats")

    @node("test.analysis.info", inputs=[Port("in", "dataset", accepts=["image"])],
          outputs=[Port("info", "value", value_type="json")], cache="disk")
    def info(ctx, inputs, params):
        runs[ctx.node_id] += 1
        image = inputs["in"]
        return {"dimensions": list(image.dimensions), "fields": image.field_names, "step": image.time.step}

    @node("test.render.surface", inputs=[Port("in", "dataset", accepts=["image"])], outputs=[Port("layer", "layer")],
          params={"field": string("P_scaled"), "colormap": string("viridis", stage="client"),
                  "opacity": number(1.0, minimum=0, maximum=1, stage="client")})
    def surface(ctx, inputs, params):
        runs[ctx.node_id] += 1
        assert set(params) == {"field"}, params  # representation impls only see data-stage params
        values = inputs["in"].array(params["field"])
        return {"type": "surface", "field": params["field"],
                "values": np.ascontiguousarray(values, dtype=np.float32).ravel()}

    @node("test.render.legend", inputs=[Port("source", "layer")], outputs=[Port("layer", "layer")],
          params={"title": string("Legend", stage="client")})
    def legend(ctx, inputs, params):
        runs[ctx.node_id] += 1
        return {"type": "legend", "colormap": inputs["source"]["appearance"]["colormap"]}

    @node("test.view.camera", outputs=[Port("camera", "camera")],
          params={"preset": enum(["iso", "+x", "-x", "+z"], "iso")})
    def camera(ctx, inputs, params):
        runs[ctx.node_id] += 1
        return {"preset": params["preset"]}

    @node("test.view.scene", inputs=[Port("layers", "layer", multi=True), Port("camera", "camera", required=False)],
          outputs=[Port("scene", "scene")], params={"background": string("white")})
    def scene(ctx, inputs, params):
        runs[ctx.node_id] += 1
        return {"layers": list(inputs["layers"]), "camera": inputs.get("camera"), "background": params["background"]}

    @node("test.output.payload", inputs=[Port("scene", "scene")], outputs=[Port("payload", "payload")])
    def payload(ctx, inputs, params):
        runs[ctx.node_id] += 1
        return encode_scene(inputs["scene"], profile=ctx.budget.profile)

    @node("test.output.image", inputs=[Port("source", ["scene", "plot"])], outputs=[Port("image", "image")],
          params={"width": number(64.0), "height": number(48.0)})
    def image(ctx, inputs, params):
        runs[ctx.node_id] += 1
        data = b"\x89PNG\r\n\x1a\n" + json.dumps(_describe(inputs["source"]), sort_keys=True).encode()
        return {"media_type": "image/png", "sha256": hashlib.sha256(data).hexdigest(),
                "width": int(params["width"]), "height": int(params["height"]), "bytes": data}

    @node("test.plot.line", inputs=[Port("table", "table")], outputs=[Port("plot", "plot")],
          params={"title": string("Stats", stage="client")})
    def line(ctx, inputs, params):
        runs[ctx.node_id] += 1
        return {"schema": "stk.plot/1", "title": params["title"], "tables": {"t": inputs["table"].to_json()}}

    @node("test.output.export", inputs=[Port("in", "dataset")], outputs=[Port("file", "file")],
          params={"name": string("export")})
    def export(ctx, inputs, params):
        runs[ctx.node_id] += 1
        directory = ctx.cache_dir
        target = directory / f"{params['name']}.npy"
        np.save(target, inputs["in"].array("P"))
        data = target.read_bytes()
        return {"name": target.name, "media_type": "application/octet-stream",
                "sha256": hashlib.sha256(data).hexdigest(), "size": len(data), "path": str(target)}

    @node("test.analysis.big", inputs=[Port("in", "dataset", accepts=["image"])], outputs=[Port("out", "table")],
          params={"rows": number(40000.0)})
    def big(ctx, inputs, params):
        runs[ctx.node_id] += 1
        count = int(params["rows"])
        return Table.from_columns({"i": np.arange(count, dtype=np.int64), "v": np.linspace(0, 1, count)})

    return registry


def _describe(value):
    if isinstance(value, dict):
        return {k: _describe(v) for k, v in value.items() if k != "values"}
    if isinstance(value, list):
        return [_describe(v) for v in value]
    return value


def encode_scene(scene, *, profile="web", budget=None):
    """A minimal stk.payload/2 value (manifest + buffers) for the test scene."""
    buffers, entries, layers = {}, [], []
    for index, layer in enumerate(scene["layers"]):
        entry = {"id": f"l{index}", "type": layer["type"], "appearance": layer.get("appearance", {})}
        if "values" in layer:
            data = layer["values"].tobytes()
            digest = hashlib.sha256(data).hexdigest()
            buffers[digest] = data
            entries.append({"id": f"b{len(entries)}", "uri": f"#{len(entries) + 1}", "sha256": digest,
                            "byteLength": len(data), "encoding": "raw"})
            entry["buffer"] = entries[-1]["id"]
        layers.append(entry)
    manifest = {"schema": "stk.payload/2", "render_origin": [0.0, 0.0, 0.0], "length_unit": "grid_index",
                "buffers": entries, "accessors": [], "layers": layers,
                "view": {"camera": scene.get("camera"), "background": scene.get("background")},
                "source": {"profile": profile}}
    return {"manifest": manifest, "buffers": buffers}


def render_plot(plot, *, format="svg"):
    text = json.dumps(plot, sort_keys=True)
    if format == "svg":
        return {"bytes": f"<svg xmlns='http://www.w3.org/2000/svg'><desc>{len(text)}</desc></svg>".encode(),
                "media_type": "image/svg+xml", "data": plot["tables"]}
    return {"bytes": b"\x89PNG\r\n\x1a\n" + text.encode(), "media_type": "image/png", "data": plot["tables"]}


GRAPH = {
    "schema": "stk.graph/1", "name": "test pipeline",
    "parameters": [
        {"name": "step", "type": "step", "default": "latest"},
        {"name": "factor", "type": "number", "default": 2.0},
        {"name": "view", "type": "enum", "choices": ["iso", "+x", "-x", "+z"], "default": "iso"},
    ],
    "nodes": [
        {"id": "frames", "type": "test.source.frames@1", "params": {"binding": "run"}},
        {"id": "frame", "type": "test.source.frame@1", "inputs": {"frames": {"from": "frames.frames"}},
         "params": {"dataset": "P", "step": {"$param": "step"}}},
        {"id": "scale", "type": "test.filter.scale@1", "inputs": {"in": {"from": "frame.out"}},
         "params": {"factor": {"$param": "factor"}}},
        {"id": "stats", "type": "test.analysis.stats@1", "inputs": {"in": {"from": "scale.out"}},
         "params": {"field": "P_scaled"}},
        {"id": "info", "type": "test.analysis.info@1", "inputs": {"in": {"from": "frame.out"}}},
        {"id": "surface", "type": "test.render.surface@1", "inputs": {"in": {"from": "scale.out"}},
         "params": {"colormap": "viridis", "opacity": 0.8}},
        {"id": "legend", "type": "test.render.legend@1", "inputs": {"source": {"from": "surface.layer"}}},
        {"id": "camera", "type": "test.view.camera@1", "params": {"preset": {"$param": "view"}}},
        {"id": "scene", "type": "test.view.scene@1",
         "inputs": {"layers": [{"from": "surface.layer"}, {"from": "legend.layer"}],
                    "camera": {"from": "camera.camera"}}},
        {"id": "payload", "type": "test.output.payload@1", "inputs": {"scene": {"from": "scene.scene"}}},
        {"id": "image", "type": "test.output.image@1", "inputs": {"source": {"from": "scene.scene"}}},
        {"id": "plot", "type": "test.plot.line@1", "inputs": {"table": {"from": "stats.out"}}},
    ],
    "outputs": {"payload": "payload.payload", "image": "image.image", "stats": "stats.out", "plot": "plot.plot",
                "info": "info.info", "scene": "scene.scene"},
    "ui": {"positions": {"frames": [0, 0]}},
}

DATA_NODES = ("frames", "frame", "scale", "stats", "info")


def graph(**changes):
    """A deep copy of :data:`GRAPH`; ``changes`` maps node id -> params to merge."""
    document = copy.deepcopy(GRAPH)
    for node_id, params in changes.items():
        node = next(n for n in document["nodes"] if n["id"] == node_id)
        node.setdefault("params", {}).update(params)
    return document
