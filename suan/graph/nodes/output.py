"""Output nodes ``stk.output.payload@1``, ``stk.output.image@1`` and ``stk.output.dataset@1``.

* payload: the scene encoded as ``stk.payload/2`` within a profile budget
  (``suan.render.payload.encode_scene``), optionally with a scene v1 downgrade
  (``Payload.scene_v1``).
* image: a scene rendered by offscreen VTK **in a child process** from its
  desktop-profile payload, or a plot rendered by matplotlib (PNG/SVG/PDF).
  The value is ``{media_type, sha256, width, height, bytes, format}``.
* dataset: a dataset written to VTKHDF, VTI, NPY, CSV or JSON; the value is
  ``{name, media_type, sha256, size, path}``.

Declarations are copied from docs/specs/catalog/m1_nodes.py (frozen).
"""
import hashlib
from pathlib import Path

from suan.graph.registry import NodeExecutionError, Port, boolean, enum, integer, json_param, node, string, string_list

MEDIA_TYPES = {"png": "image/png", "svg": "image/svg+xml", "pdf": "application/pdf",
               "vtkhdf": "application/x-hdf5", "vti": "application/xml", "npy": "application/x-npy",
               "csv": "text/csv", "json": "application/json"}
EXTENSIONS = {"vtkhdf": ".vtkhdf", "vti": ".vti", "npy": ".npy", "csv": ".csv", "json": ".json"}


def _nullable_string(**kw):
    return string(None, nullable=True, **kw)


def _fail(message, code="invalid_param", hint=None):
    raise NodeExecutionError(message, code=code, hint=hint)


def _check(ctx):
    check = getattr(ctx, "check", None)
    if check is not None:
        check()


@node("stk.output.payload", title={"en": "Render payload", "zh": "渲染数据包"},
      description={"en": "Encode a scene as stk.payload/2 within the profile budget (optionally with a scene v1 "
                         "downgrade)."},
      inputs=[Port("scene", "scene")],
      outputs=[Port("payload", "payload")],
      params={
          "profile": enum(["phone", "web", "desktop"], "web"),
          "budget": json_param({"anyOf": [{"type": "null"}, {
              "type": "object", "additionalProperties": False,
              "properties": {key: {"type": "integer", "minimum": 0}
                             for key in ("triangles", "instances", "points", "voxels", "bytes")}}]}, None),
          "v1_fallback": boolean(False),
      })
def payload_output(ctx, inputs, params):
    from suan.render.payload import PayloadError, encode_scene
    try:
        payload = encode_scene(inputs["scene"], profile=params["profile"], budget=params.get("budget"))
    except PayloadError as error:
        _fail(str(error), code=error.code)
    for reduction in payload.manifest.get("budget", {}).get("reductions", ()):
        ctx.warn(f"Layer {reduction['layer']!r}: {reduction['reason']}", code="payload_reduced",
                 **{k: v for k, v in reduction.items() if k in ("layer", "from", "to")})
    if params["v1_fallback"]:
        from suan.render.v1 import to_scene_v1
        payload.scene_v1 = to_scene_v1(payload, dataset_id=getattr(ctx, "node_id", None))
    return payload


def _image_value(data, media_type, width, height, fmt):
    return {"media_type": media_type, "sha256": hashlib.sha256(data).hexdigest(), "width": int(width),
            "height": int(height), "bytes": data, "format": fmt}


@node("stk.output.image", title={"en": "Image", "zh": "图片"},
      description={"en": "Render a scene (offscreen VTK in a subprocess) or a plot (matplotlib) to PNG; plots "
                         "also to SVG/PDF."},
      inputs=[Port("source", ["scene", "plot"])],
      outputs=[Port("image", "image")],
      params={
          "width": integer(None, nullable=True, minimum=16, maximum=16384),
          "height": integer(None, nullable=True, minimum=16, maximum=16384),
          "magnification": integer(1, minimum=1, maximum=8),
          "transparent": boolean(False),
          "format": enum(["png", "svg", "pdf"], "png"),
      })
def image_output(ctx, inputs, params):
    from suan.render.layers import Scene
    source = inputs["source"]
    fmt = params["format"]
    mag = params["magnification"]
    if isinstance(source, Scene):
        if fmt != "png":
            _fail(f"Scenes render to PNG only (format {fmt!r} is for plots)", code="unsupported")
        from suan.render.offscreen import OffscreenError, OffscreenUnavailable, render_payload
        from suan.render.payload import PayloadError, encode_scene
        viewport = (source.view or {}).get("viewport") or {}
        width = params.get("width") or viewport.get("width") or 1600
        height = params.get("height") or viewport.get("height") or 1200
        try:
            payload = encode_scene(source, profile="desktop")
        except PayloadError as error:
            _fail(str(error), code=error.code)
        _check(ctx)
        budget = getattr(ctx, "budget", None)
        timeout = min(600.0, float(getattr(budget, "max_seconds", None) or 600.0))
        try:
            data = render_payload(payload, width=width, height=height, magnification=mag,
                                  transparent=params["transparent"], timeout=timeout)
        except OffscreenUnavailable as error:
            _fail(str(error), code="render_unavailable", hint=error.hint)
        except OffscreenError as error:
            _fail(str(error), code="render_failed")
        return _image_value(data, "image/png", width * mag, height * mag, "png")
    if isinstance(source, dict) and source.get("schema") == "stk.plot/1":
        from suan.plot.mpl import render
        from suan.plot.spec import PlotSpecError
        figure = source.get("figure") or {}
        dpi = int(figure.get("dpi", 200))
        width = params.get("width") or round(float((figure.get("size_in") or [6.0, 4.0])[0]) * dpi)
        height = params.get("height") or round(float((figure.get("size_in") or [6.0, 4.0])[1]) * dpi)
        try:
            data = render(source, format=fmt, width_px=width, height_px=height, magnification=mag,
                          transparent=params["transparent"])
        except PlotSpecError as error:
            _fail(str(error), code="node_failed")
        if fmt == "png":
            from suan.render.png import png_size
            width, height = png_size(data)
            mag = 1
        return _image_value(data, MEDIA_TYPES[fmt], width * mag, height * mag, fmt)
    _fail(f"stk.output.image needs a scene or a plot, got {type(source).__name__}", code="kind_mismatch")


def _output_dir(ctx):
    base = getattr(ctx, "cache_dir", None)
    if base is None:
        import tempfile
        base = tempfile.mkdtemp(prefix="stk-export-")
    directory = Path(base) / "exports" / str(getattr(ctx, "data_key", None) or getattr(ctx, "node_id", "node"))
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _subset(dataset, fields, precision):
    """Shallow copy keeping ``fields`` (all when ``None``); float64 -> float32 (marked lossy) on request."""
    from dataclasses import replace
    import numpy as np
    result = dataset.copy()
    if fields is not None:
        missing = [name for name in fields if name not in dataset.fields]
        if missing:
            _fail(f"No field(s) {', '.join(map(repr, missing))}; fields: {', '.join(dataset.fields) or 'none'}")
        result.fields = {name: dataset.fields[name] for name in fields}
    if precision == "float32":
        result.fields = {name: replace(f, dtype="float32", lossy=True,
                                       values=np.ascontiguousarray(f.values, dtype=np.float32))
                         if f.values is not None and f.dtype == "float64" else f
                         for name, f in result.fields.items()}
    return result


def _write_vti(image, path):
    import numpy as np
    import vtk
    from vtk.util.numpy_support import numpy_to_vtk
    grid = vtk.vtkImageData()
    grid.SetDimensions(*image.dimensions)
    grid.SetOrigin(*image.origin)
    grid.SetSpacing(*image.spacing)
    if not image.is_axis_aligned:
        grid.SetDirectionMatrix(*image.direction)
    active = None
    for field in image.fields.values():
        if field.values is None or field.dtype == "string":
            continue
        values = np.ascontiguousarray(np.asarray(field.values).reshape(-1, field.components))
        array = numpy_to_vtk(values, deep=True)
        array.SetName(field.name)
        data = grid.GetCellData() if field.association == "cell" else grid.GetPointData()
        data.AddArray(array)
        if active is None and field.association == "point":      # what scene.load_grid reads back
            active = field
            (data.SetVectors if field.components == 3 else data.SetScalars)(array)
    for name, value in (("STK_coordinate_units", "grid index" if image.length_unit == "grid_index"
                         else image.length_unit), ("STK_units", active.unit if active is not None else None)):
        if value is not None:
            text = vtk.vtkStringArray()
            text.SetName(name)
            text.InsertNextValue(value)
            grid.GetFieldData().AddArray(text)
    writer = vtk.vtkXMLImageDataWriter()
    writer.SetFileName(str(path))
    writer.SetInputData(grid)
    if not writer.Write():
        _fail(f"VTK could not write {path.name}", code="node_failed")


def _write_table_csv(table, path):
    import csv
    import numpy as np
    headers, columns = [], []
    for field in table.fields.values():
        values = np.asarray(field.values)
        if values.ndim == 1:
            headers.append(field.name)
            columns.append(values.tolist())
        else:
            names = field.component_names or [str(k) for k in range(values.shape[1])]
            headers += [f"{field.name}_{n}" for n in names]
            columns += [values[:, k].tolist() for k in range(values.shape[1])]
    with open(path, "w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(headers)
        writer.writerows(zip(*columns))


@node("stk.output.dataset", title={"en": "Dataset export", "zh": "数据导出"},
      description={"en": "Write a dataset to VTKHDF (STK profile), VTI or NPY, or a table to CSV/JSON."},
      inputs=[Port("in", "dataset")],
      outputs=[Port("file", "file")],
      params={
          "format": enum(["vtkhdf", "vti", "npy", "csv", "json"], "vtkhdf", stage="data"),
          "name": _nullable_string(pattern=r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$", stage="data",
                                   title="File stem (null = node id)"),
          "fields": string_list(None, nullable=True, max_items=64, stage="data"),
          "precision": enum(["float64", "float32"], "float64", stage="data"),
      })
def dataset_output(ctx, inputs, params):
    import json
    import numpy as np
    from suan.data.model import ImageData, Table
    dataset = _subset(inputs["in"], params.get("fields"), params["precision"])
    fmt = params["format"]
    name = (params.get("name") or getattr(ctx, "node_id", None) or "export") + EXTENSIONS[fmt]
    path = _output_dir(ctx) / name
    if fmt in ("csv", "json"):
        if not isinstance(dataset, Table):
            _fail(f"Format {fmt!r} is for tables; use vtkhdf, vti or npy for {dataset.kind} datasets",
                  code="unsupported")
        if fmt == "csv":
            _write_table_csv(dataset, path)
        else:
            path.write_text(json.dumps({"id": dataset.id, **dataset.to_json()}, ensure_ascii=False) + "\n",
                            encoding="utf-8")
    elif fmt == "npy":
        if not isinstance(dataset, ImageData):
            _fail("NPY export needs an image dataset", code="unsupported")
        field = next((f for f in dataset.fields.values() if f.association == "point" and f.values is not None), None)
        if field is None:
            _fail("The image has no point field to export")
        values = np.ascontiguousarray(dataset.xyz(field.name))
        np.save(path, values[..., 0] if field.components == 1 else values)
    elif fmt == "vti":
        if not isinstance(dataset, ImageData):
            _fail("VTI export needs an image dataset", code="unsupported")
        _write_vti(dataset, path)
    else:
        try:
            from suan.data import vtkhdf
        except ModuleNotFoundError as error:
            if error.name not in ("suan.data.vtkhdf", "h5py"):
                raise
            _fail(f"VTKHDF export is unavailable ({error.name} is not installed)", code="unsupported",
                  hint="install the 'visualization' extra (h5py) or export vti/npy")
        vtkhdf.write_vtkhdf(path, dataset)
    data = path.read_bytes()
    return {"name": name, "media_type": MEDIA_TYPES[fmt], "sha256": hashlib.sha256(data).hexdigest(),
            "size": len(data), "path": str(path)}
