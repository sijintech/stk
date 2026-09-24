"""Offscreen VTK rendering of ``stk.payload/2`` payloads, always in a child process.

The renderer draws a *payload* (not a VTK pipeline), so headless PNGs show
exactly what the web viewer and Blender show and serve as golden references.
VTK aborts the whole interpreter when neither EGL nor OSMesa can create a
context, so the parent never imports VTK: it runs this module's ``main`` in
a child interpreter (like ``python -m suan.render.offscreen``, with STK's root
appended to the child's ``sys.path`` so the child's own VTK/NumPy win) and
reads the PNG back. A driver crash kills only the child. Overlay text uses
DejaVu Sans from matplotlib's data when available (VTK's embedded "Arial"
draws square brackets as parentheses), else VTK's Times.

Parent API (standard library only):

* :func:`probe` -- cached capability check (a tiny render in a child); a
  working renderer and definitive failures are cached, transient failures (a
  timeout, a child killed from outside) are probed again next time;
* :func:`render_payload` / :func:`render_scene` -- PNG bytes; ``poll`` (e.g.
  ``NodeContext.check``) is called while the child runs and an exception it
  raises (cancellation, the evaluation's time budget) kills the child;
* :class:`OffscreenUnavailable` (no usable GL; carries an actionable ``hint``)
  and :class:`OffscreenError` (the child failed).

Children run in an empty temporary directory (so a stray ``vtk.py`` in the
parent's working directory is never imported). Text is drawn literally with
FreeType (VTK would otherwise treat ``$…$`` and ``|`` as MathText markup and
turn a title such as ``|v|`` into ``v``).

The render interpreter is ``python=``, else ``$STK_RENDER_PYTHON``, else
``sys.executable`` -- e.g. a separate environment with Kitware's
``vtk-osmesa`` wheel. Magnification renders at ``viewport x magnification``
with every pixel size (fonts, line widths, overlays) scaled, so a magnified
image is the same picture at higher resolution.

Child command line::

    python -m suan.render.offscreen --probe
    python -m suan.render.offscreen --payload scene.stkp --out scene.png [--width W --height H]
                                    [--magnification M] [--transparent]
"""
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import threading
import time

__all__ = [
    "ENV_PYTHON", "HINT", "OffscreenError", "OffscreenUnavailable",
    "available", "main", "probe", "render_payload", "render_scene",
]

ENV_PYTHON = "STK_RENDER_PYTHON"
HINT = ("Offscreen rendering needs an OpenGL context without a display. Install EGL "
        "(apt install libegl1 libegl-mesa0 libgl1-mesa-dri) or OSMesa (apt install libosmesa6) and set "
        "VTK_DEFAULT_OPENGL_WINDOW=vtkEGLRenderWindow or vtkOSOpenGLRenderWindow, or point STK_RENDER_PYTHON at an "
        "interpreter with Kitware's OSMesa build of VTK "
        "(pip install --extra-index-url https://wheels.vtk.org vtk-osmesa).")
_PROBES = {}
_LOCK = threading.Lock()
_POLL_INTERVAL = 0.1  # seconds between poll() calls while a child runs
# A child killed from outside (OOM killer, an operator) says nothing about the GL stack: probe again next time.
_TRANSIENT_SIGNALS = {getattr(signal, name) for name in ("SIGKILL", "SIGTERM", "SIGINT", "SIGHUP")
                      if hasattr(signal, name)}
_PACKAGE_ROOT = str(Path(__file__).resolve().parents[2])
_ANSI = re.compile(r"\x1b\[[0-9;]*m")


class OffscreenUnavailable(RuntimeError):
    """No usable offscreen OpenGL in the render interpreter."""

    def __init__(self, message, *, hint=HINT, probe=None):
        super().__init__(message)
        self.hint = hint
        self.probe = probe or {}


class OffscreenError(RuntimeError):
    """The render child failed (bad payload, crash or timeout)."""


def render_python(python=None):
    return python or os.environ.get(ENV_PYTHON) or sys.executable


# The child finds ``suan`` in its own environment first; this package's root is only *appended* to
# sys.path, so the render interpreter's VTK/NumPy (e.g. vtk-osmesa) are never shadowed by the parent's.
_BOOTSTRAP = ("import sys; sys.path.append({root!r}); from suan.render.offscreen import main; "
              "sys.exit(main(sys.argv[1:]))")


def _child_env():
    env = dict(os.environ)
    env.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    return env


def _tail(text, lines=6):
    cleaned = [_ANSI.sub("", line).strip() for line in (text or "").splitlines() if line.strip()]
    return "\n".join(cleaned[-lines:])


class _Outcome(tuple):
    """``(result, error, stderr)`` of a child run plus ``transient`` (a timeout or an outside kill)."""

    transient = False


def _outcome(result, error, stderr, transient=False):
    outcome = _Outcome((result, error, stderr))
    outcome.transient = transient
    return outcome


def _run(python, args, timeout, *, cwd=None, poll=None):
    """Run the child in ``cwd`` (default: a fresh empty directory); ``poll()`` is called while it runs."""
    if cwd is None:
        with tempfile.TemporaryDirectory(prefix="stk-render-cwd-") as tmp:
            return _run(python, args, timeout, cwd=tmp, poll=poll)
    command = [python, "-c", _BOOTSTRAP.format(root=_PACKAGE_ROOT), *args]
    try:
        child = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                 env=_child_env(), stdin=subprocess.DEVNULL, cwd=str(cwd))
    except OSError as error:
        return _outcome(None, f"cannot start the render interpreter {python!r}: {error}", "")
    deadline = time.monotonic() + timeout
    try:
        while True:
            try:
                stdout, stderr = child.communicate(timeout=_POLL_INTERVAL if poll is not None else
                                                   max(0.0, deadline - time.monotonic()))
                break
            except subprocess.TimeoutExpired:
                if time.monotonic() >= deadline:
                    child.kill()
                    _, stderr = child.communicate()
                    return _outcome(None, f"render child timed out after {timeout:g} s", _tail(stderr), True)
                poll()  # raises Cancelled / BudgetExceeded: the finally clause kills the child
    finally:
        if child.poll() is None:
            child.kill()
            child.communicate()
    result = None
    for line in reversed(stdout.splitlines()):
        if line.startswith("{"):
            try:
                result = json.loads(line)
            except ValueError:
                continue
            break
    if child.returncode < 0:
        return _outcome(result, f"render child killed by signal {-child.returncode}", _tail(stderr),
                        -child.returncode in _TRANSIENT_SIGNALS)
    if child.returncode != 0:
        message = (result or {}).get("error") or f"render child exited with status {child.returncode}"
        return _outcome(result, message, _tail(stderr))
    return _outcome(result, None, _tail(stderr))


def probe(*, python=None, timeout=120.0, refresh=False):
    """Check offscreen rendering in a child process (cached per interpreter and GL settings).

    Returns ``{"ok", "python", "vtk", "window", "renderer", "error", "hint"}``. Success and
    definitive failures (the child reported a failure, crashed, or cannot be started) are cached;
    transient ones (a timeout, a child killed by SIGKILL/SIGTERM) are not, so the next call probes
    again. ``refresh=True`` always probes.
    """
    python = render_python(python)
    key = (python, os.environ.get("VTK_DEFAULT_OPENGL_WINDOW"), os.environ.get("DISPLAY"),
           os.environ.get("WAYLAND_DISPLAY"))
    with _LOCK:
        if not refresh and key in _PROBES:
            return dict(_PROBES[key])
    outcome = _run(python, ["--probe"], timeout)
    result, error, stderr = outcome
    info = {"ok": error is None and bool(result and result.get("ok")), "python": python}
    info.update({k: v for k, v in (result or {}).items() if k in ("vtk", "window", "renderer")})
    if not info["ok"]:
        info["error"] = error or (result or {}).get("error") or "offscreen probe failed"
        if stderr:
            info["stderr"] = stderr
        info["hint"] = HINT
    if info["ok"] or not outcome.transient:
        with _LOCK:
            _PROBES[key] = info
    return dict(info)


def available(**kw):
    return probe(**kw)["ok"]


def render_payload(payload, *, width=None, height=None, magnification=1, transparent=False, python=None,
                   timeout=300.0, check=True, poll=None):
    """PNG bytes of a :class:`suan.render.payload.Payload` (or a path to an ``.stkp`` file).

    ``width``/``height`` default to the payload view's viewport; the image is
    ``width x magnification`` by ``height x magnification`` pixels (RGBA when
    ``transparent``). Raises :class:`OffscreenUnavailable` when the probe fails.
    ``poll`` (optional) is called about every 0.1 s while the child renders; an
    exception it raises (e.g. ``Cancelled``) kills the child and propagates.
    """
    python = render_python(python)
    if check:
        info = probe(python=python)
        if not info["ok"]:
            raise OffscreenUnavailable(f"Offscreen rendering is unavailable in {python}: {info['error']}",
                                       probe=info)
    magnification = int(magnification)
    if not 1 <= magnification <= 8:
        raise ValueError("magnification must be an integer from 1 to 8")
    with tempfile.TemporaryDirectory(prefix="stk-render-") as tmp:
        source = Path(tmp) / "scene.stkp"
        if isinstance(payload, (str, os.PathLike)):
            source = Path(payload)
        else:
            source.write_bytes(payload.to_stkp())
        out = Path(tmp) / "scene.png"
        args = ["--payload", str(source), "--out", str(out), "--magnification", str(magnification)]
        if width:
            args += ["--width", str(int(width))]
        if height:
            args += ["--height", str(int(height))]
        if transparent:
            args.append("--transparent")
        work = Path(tmp) / "cwd"
        work.mkdir()
        result, error, stderr = _run(python, args, timeout, cwd=work, poll=poll)
        if error is not None or not out.is_file():
            detail = f"\n{stderr}" if stderr else ""
            raise OffscreenError(f"Offscreen render failed: {error or 'no image written'}{detail}")
        return out.read_bytes()


def render_scene(scene, *, profile="desktop", budget=None, **kw):
    """Encode a :class:`suan.render.layers.Scene` (desktop profile) and render it to PNG bytes."""
    from .payload import encode_scene
    return render_payload(encode_scene(scene, profile=profile, budget=budget), **kw)


# ---------------------------------------------------------------------------
# Child process: payload -> VTK actors -> PNG


ANCHOR_FRACTIONS = {
    "top_left": (0, 1), "top": (0.5, 1), "top_right": (1, 1), "left": (0, 0.5), "center": (0.5, 0.5),
    "right": (1, 0.5), "bottom_left": (0, 0), "bottom": (0.5, 0), "bottom_right": (1, 0),
}


def _place(anchor, offset, size, window):
    """Bottom-left display position of a ``size`` box at ``anchor`` with ``offset`` inward (pixels)."""
    fx, fy = ANCHOR_FRACTIONS.get(anchor or "top_left", (0, 1))
    (ox, oy), (w, h), (W, H) = offset, size, window
    x = ox if fx == 0 else (W - w - ox if fx == 1 else (W - w) / 2 + ox)
    y = oy if fy == 0 else (H - h - oy if fy == 1 else (H - h) / 2 - oy)
    return x, y


def _literal_text(vtk):
    """Draw every text with FreeType, literally: VTK's detection would render ``$...$`` and ``|`` as MathText."""
    renderer_class = getattr(vtk, "vtkTextRenderer", None)
    instance = renderer_class.GetInstance() if renderer_class is not None and hasattr(renderer_class,
                                                                                         "GetInstance") else None
    if instance is not None and hasattr(instance, "SetDefaultBackend"):
        instance.SetDefaultBackend(renderer_class.FreeType)


class _Renderer:
    def __init__(self, payload, *, width=None, height=None, magnification=1, transparent=False):
        import numpy as np
        import vtk
        from vtk.util import numpy_support
        self.np, self.vtk, self.nps = np, vtk, numpy_support
        _literal_text(vtk)
        self.payload = payload
        self.m = payload.manifest
        self.view = dict(self.m.get("view") or {})
        viewport = self.view.get("viewport") or {}
        self.mag = int(magnification)
        self.size = (int(width or viewport.get("width") or 800), int(height or viewport.get("height") or 600))
        self.W, self.H = self.size[0] * self.mag, self.size[1] * self.mag
        background = self.view.get("background") or {}
        self.transparent = bool(transparent or background.get("type") == "transparent"
                                or (self.view.get("render") or {}).get("transparent"))
        self.background = [float(c) for c in (background.get("color") or (1.0, 1.0, 1.0))[:3]]
        self.lighting = (self.view.get("lighting") or {}).get("preset", "three_point")
        self.ink = (0.0, 0.0, 0.0) if sum(self.background) / 3 > 0.5 else (1.0, 1.0, 1.0)
        self.origin = np.asarray(self.m["render_origin"], dtype=np.float64)
        visibility = self.view.get("visibility") or {}
        self.keep = []              # VTK algorithms whose outputs feed mappers (Python must hold them)
        self.fonts = _font_files()
        self.layers = [layer for layer in self.m["layers"]
                       if layer.get("visible", True) and visibility.get(layer.get("id"), True)]

    # -- helpers --------------------------------------------------------------

    def px(self, value):
        return float(value) * self.mag

    def offset_of(self, layer):
        if "origin" in layer:
            return self.np.asarray(layer["origin"], dtype=self.np.float64) - self.origin
        return self.np.zeros(3)

    def points(self, positions, shift):
        vtk_points = self.vtk.vtkPoints()
        data = self.np.ascontiguousarray(self.np.asarray(positions, dtype=self.np.float64) + shift)
        vtk_points.SetData(self.nps.numpy_to_vtk(data, deep=True))
        return vtk_points

    def cells(self, connectivity, size):
        np = self.np
        connectivity = np.ascontiguousarray(np.asarray(connectivity, dtype=np.int64).reshape(-1))
        offsets = np.arange(0, len(connectivity) + 1, size, dtype=np.int64)
        cells = self.vtk.vtkCellArray()
        cells.SetData(self.nps.numpy_to_vtkIdTypeArray(offsets, deep=True),
                      self.nps.numpy_to_vtkIdTypeArray(connectivity, deep=True))
        return cells

    def rgba_array(self, rgba):
        array = self.nps.numpy_to_vtk(self.np.ascontiguousarray(rgba, dtype=self.np.uint8), deep=True,
                                      array_type=self.vtk.VTK_UNSIGNED_CHAR)
        array.SetName("stk_rgba")
        return array

    def colors(self, layer):
        """``(rgba uint8 (n, 4), association)`` or ``(None, solid rgb)``."""
        from .colormaps import map_categories, map_scalars, orientation_hsl
        np = self.np
        spec = (layer.get("appearance") or {}).get("color") or {"by": "solid", "solid": [0.8, 0.8, 0.8]}
        by = spec.get("by", "solid")
        if by == "solid":
            return None, [float(c) for c in (spec.get("solid") or (0.8, 0.8, 0.8))[:3]]
        attributes = layer.get("attributes") or {}
        if by == "direction":
            name = spec.get("attribute")
            if name is not None:
                vectors, association = self.payload.array(attributes[name]["accessor"]), attributes[name].get(
                    "association", "point")
            else:
                vectors, association = self.payload.array(layer["directions"]), "point"
            rgb = orientation_hsl(vectors, spec.get("max_magnitude"), spec.get("lightness_range") or (0.0, 1.0))
            rgba = np.concatenate([rgb, np.ones((len(rgb), 1))], axis=1)
            return np.floor(np.clip(rgba, 0, 1) * 255 + 0.5).astype(np.uint8), association
        attribute = attributes[spec["attribute"]]
        association = attribute.get("association", "point")
        values = self.payload.array(attribute["accessor"]).astype(np.float64)
        colormap = self.payload.colormap(spec["colormap"])
        if colormap.get("categorical"):
            rgba = map_categories(values if values.ndim == 1 else values[:, 0], colormap["entries"],
                                  unknown_color=colormap.get("unknown_color"))
        else:
            if values.ndim > 1:
                component = spec.get("component")
                values = values[:, component] if isinstance(component, int) else np.linalg.norm(values, axis=1)
            value_range = spec.get("range") or attribute.get("range")
            if value_range is None:
                finite = values[np.isfinite(values)]
                value_range = [finite.min(), finite.max()] if len(finite) else [0.0, 1.0]
            rgba = map_scalars(values, self.payload.array(colormap["lut"]).reshape(256, 4), value_range,
                               nan_color=colormap.get("nan_color"), below_color=colormap.get("below_color"),
                               above_color=colormap.get("above_color"))
        return np.floor(np.clip(rgba, 0, 1) * 255 + 0.5).astype(np.uint8), association

    def apply_colors(self, poly, mapper, actor, layer):
        rgba, association = self.colors(layer)
        if rgba is None:
            actor.GetProperty().SetColor(*association)
            mapper.ScalarVisibilityOff()
            return
        data = poly.GetCellData() if association == "cell" else poly.GetPointData()
        data.SetScalars(self.rgba_array(rgba))
        mapper.SetColorModeToDirectScalars()
        mapper.ScalarVisibilityOn()
        if association == "cell":
            mapper.SetScalarModeToUseCellData()
        else:
            mapper.SetScalarModeToUsePointData()

    def finish_actor(self, actor, appearance, lighting_default=True):
        prop = actor.GetProperty()
        prop.SetOpacity(float(appearance.get("opacity", 1.0)))
        if not appearance.get("lighting", lighting_default) or self.lighting == "none":
            prop.SetAmbient(1.0)
            prop.SetDiffuse(0.0)
            prop.SetSpecular(0.0)
        return actor

    # -- 3D layers ------------------------------------------------------------

    def layer_triangles(self, layer):
        vtk, np = self.vtk, self.np
        poly = vtk.vtkPolyData()
        poly.SetPoints(self.points(self.payload.array(layer["positions"]), self.offset_of(layer)))
        poly.SetPolys(self.cells(self.payload.array(layer["indices"]), 3))
        appearance = layer.get("appearance") or {}
        if "normals" in layer:
            normals = self.nps.numpy_to_vtk(np.ascontiguousarray(self.payload.array(layer["normals"]),
                                                                 dtype=np.float32), deep=True)
            poly.GetPointData().SetNormals(normals)
        elif appearance.get("shading", "smooth") == "smooth":
            filt = vtk.vtkPolyDataNormals()
            filt.SetInputData(poly)
            filt.SplittingOff()
            filt.ConsistencyOn()
            filt.Update()
            poly = filt.GetOutput()
        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputData(poly)
        actor = vtk.vtkActor()
        actor.SetMapper(mapper)
        self.apply_colors(poly, mapper, actor, layer)
        if appearance.get("shading") == "flat":
            actor.GetProperty().SetInterpolationToFlat()
        edges = appearance.get("edges") or {}
        if edges.get("visible"):
            actor.GetProperty().EdgeVisibilityOn()
            actor.GetProperty().SetEdgeColor(*[float(c) for c in edges.get("color", (0, 0, 0))[:3]])
            actor.GetProperty().SetLineWidth(self.px(edges.get("width_px", 1.0)))
        return [self.finish_actor(actor, appearance)]

    def layer_slice_image(self, layer):
        vtk, np = self.vtk, self.np
        w, h = layer["size"]
        shift = self.offset_of(layer)
        o, u, v = (np.asarray(layer["plane"][k], dtype=np.float64) for k in ("origin", "u", "v"))
        o = o + shift
        du = u / (w - 1) if w > 1 else None
        dv = v / (h - 1) if h > 1 else None
        if du is None and dv is None:
            du, dv = np.array([1.0, 0.0, 0.0]), np.array([0.0, 1.0, 0.0])
        elif du is None:
            du = _perpendicular(dv, np) * np.linalg.norm(dv)
        elif dv is None:
            dv = _perpendicular(du, np) * np.linalg.norm(du)
        plane = vtk.vtkPlaneSource()
        plane.SetOrigin(*(o - du / 2 - dv / 2))
        plane.SetPoint1(*(o + du * (w - 1) + du / 2 - dv / 2))
        plane.SetPoint2(*(o - du / 2 + dv * (h - 1) + dv / 2))
        plane.SetResolution(1, 1)
        rgba, association = self.colors(layer)
        if rgba is None:
            rgba = np.tile(np.floor(np.array(list(association) + [1.0]) * 255 + 0.5).astype(np.uint8), (w * h, 1))
        image = vtk.vtkImageData()
        image.SetDimensions(w, h, 1)
        image.GetPointData().SetScalars(self.rgba_array(rgba))
        texture = vtk.vtkTexture()
        texture.SetInputData(image)
        color = (layer.get("appearance") or {}).get("color") or {}
        texture.SetInterpolate(color.get("interpolate", "linear") == "linear")
        texture.SetColorModeToDirectScalars()
        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputConnection(plane.GetOutputPort())
        self.keep.append(plane)
        actor = vtk.vtkActor()
        actor.SetMapper(mapper)
        actor.SetTexture(texture)
        return [self.finish_actor(actor, layer.get("appearance") or {}, lighting_default=False)]

    def layer_lines(self, layer):
        vtk, np = self.vtk, self.np
        poly = vtk.vtkPolyData()
        poly.SetPoints(self.points(self.payload.array(layer["positions"]), self.offset_of(layer)))
        indices = np.asarray(self.payload.array(layer["indices"]), dtype=np.int64)
        if layer.get("mode") == "polylines":
            offsets = np.asarray(self.payload.array(layer["offsets"]), dtype=np.int64)
            pairs = [np.stack([indices[a:b - 1], indices[a + 1:b]], axis=1) for a, b in zip(offsets[:-1], offsets[1:])
                     if b - a > 1]
            indices = np.concatenate(pairs) if pairs else np.zeros((0, 2), dtype=np.int64)
        poly.SetLines(self.cells(indices, 2))
        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputData(poly)
        actor = vtk.vtkActor()
        actor.SetMapper(mapper)
        self.apply_colors(poly, mapper, actor, layer)
        appearance = layer.get("appearance") or {}
        actor.GetProperty().SetLineWidth(self.px(appearance.get("width_px", 1.0)))
        return [self.finish_actor(actor, appearance, lighting_default=False)]

    def layer_points(self, layer):
        vtk, np = self.vtk, self.np
        positions = self.payload.array(layer["positions"])
        appearance = layer.get("appearance") or {}
        poly = vtk.vtkPolyData()
        poly.SetPoints(self.points(positions, self.offset_of(layer)))
        poly.SetVerts(self.cells(np.arange(len(positions)), 1))
        radius = appearance.get("radius")
        if appearance.get("render_as") == "spheres" and ("radii" in layer or radius):
            scales = (np.asarray(self.payload.array(layer["radii"]), dtype=np.float64) if "radii" in layer
                      else np.full(len(positions), float(radius)))
            poly.GetPointData().AddArray(_named(self.nps.numpy_to_vtk(2 * scales, deep=True), "stk_scale"))
            sphere = vtk.vtkSphereSource()
            sphere.SetRadius(0.5)
            sphere.SetThetaResolution(16)
            sphere.SetPhiResolution(12)
            mapper = vtk.vtkGlyph3DMapper()
            mapper.SetSourceConnection(sphere.GetOutputPort())
            self.keep.append(sphere)
            mapper.SetScaleArray("stk_scale")
            mapper.SetScaleModeToScaleByMagnitude()
        else:
            mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputData(poly)
        actor = vtk.vtkActor()
        actor.SetMapper(mapper)
        self.apply_colors(poly, mapper, actor, layer)
        actor.GetProperty().SetPointSize(self.px(appearance.get("size_px", 3.0)))
        if appearance.get("render_as") == "spheres":
            actor.GetProperty().SetRenderPointsAsSpheres(True)
        return [self.finish_actor(actor, appearance)]

    def glyph_source(self, glyph):
        vtk = self.vtk
        shape, res = glyph.get("shape", "arrow"), int(glyph.get("resolution", 8))
        if shape == "arrow":
            source = vtk.vtkArrowSource()
            source.SetTipResolution(res)
            source.SetShaftResolution(res)
        elif shape == "cone":
            source = vtk.vtkConeSource()
            source.SetHeight(1.0)
            source.SetRadius(0.25)
            source.SetResolution(res)
            source.SetCenter(0.5, 0.0, 0.0)
            source.SetDirection(1.0, 0.0, 0.0)
        elif shape == "sphere":
            source = vtk.vtkSphereSource()
            source.SetRadius(0.5)
            source.SetThetaResolution(res)
            source.SetPhiResolution(max(3, res // 2 + 1))
        elif shape == "line":
            source = vtk.vtkLineSource()
            source.SetPoint1(0.0, 0.0, 0.0)
            source.SetPoint2(1.0, 0.0, 0.0)
        else:
            source = vtk.vtkCubeSource()
        if glyph.get("center") and shape in ("arrow", "cone", "line"):
            transform = vtk.vtkTransform()
            transform.Translate(-0.5, 0.0, 0.0)
            shifted = vtk.vtkTransformPolyDataFilter()
            shifted.SetTransform(transform)
            shifted.SetInputConnection(source.GetOutputPort())
            self.keep += [source, shifted]
            return shifted
        self.keep.append(source)
        return source

    def layer_instances(self, layer):
        vtk, np = self.vtk, self.np
        positions = np.asarray(self.payload.array(layer["positions"]), dtype=np.float64)
        directions = np.asarray(self.payload.array(layer["directions"]), dtype=np.float64)
        appearance = layer.get("appearance") or {}
        scale = appearance.get("scale") or {"by": "uniform", "factor": 1.0}
        factor = float(scale.get("factor", 1.0))
        if "scales" in layer:
            scales = np.asarray(self.payload.array(layer["scales"]), dtype=np.float64)
        elif scale.get("by") == "magnitude":
            scales = factor * np.linalg.norm(directions, axis=1)
        elif scale.get("by") == "attribute":
            values = self.payload.array(layer["attributes"][scale["attribute"]]["accessor"]).astype(np.float64)
            scales = factor * (np.linalg.norm(values, axis=1) if values.ndim > 1 else values)
        else:
            scales = np.full(len(positions), factor)
        keep = (np.linalg.norm(directions, axis=1) > 0) & np.isfinite(scales)
        poly = vtk.vtkPolyData()
        poly.SetPoints(self.points(positions[keep], self.offset_of(layer)))
        poly.GetPointData().AddArray(_named(self.nps.numpy_to_vtk(np.ascontiguousarray(directions[keep]), deep=True),
                                            "stk_direction"))
        poly.GetPointData().AddArray(_named(self.nps.numpy_to_vtk(np.ascontiguousarray(np.abs(scales[keep])),
                                                                  deep=True), "stk_scale"))
        rgba, association = self.colors(layer)
        mapper = vtk.vtkGlyph3DMapper()
        mapper.SetInputData(poly)
        source = self.glyph_source(layer.get("glyph") or {})
        mapper.SetSourceConnection(source.GetOutputPort())
        mapper.SetOrientationArray("stk_direction")
        mapper.SetOrientationModeToDirection()
        mapper.SetScaleArray("stk_scale")
        mapper.SetScaleModeToScaleByMagnitude()
        mapper.SetScaleFactor(1.0)
        actor = vtk.vtkActor()
        actor.SetMapper(mapper)
        if rgba is None:
            actor.GetProperty().SetColor(*association)
            mapper.ScalarVisibilityOff()
        else:
            poly.GetPointData().SetScalars(self.rgba_array(rgba[keep]))
            mapper.SetColorModeToDirectScalars()
            mapper.ScalarVisibilityOn()
        return [self.finish_actor(actor, appearance)]

    def layer_volume(self, layer):
        vtk, np = self.vtk, self.np
        grid = layer["grid"]
        nx, ny, nz = grid["dimensions"]
        stored = np.asarray(self.payload.array(layer["data"]), dtype=np.float64)
        values = (stored * float(layer.get("value_scale", 1.0)) + float(layer.get("value_offset", 0.0))).astype(
            np.float32)
        image = vtk.vtkImageData()
        image.SetDimensions(nx, ny, nz)
        image.SetSpacing(*grid["spacing"])
        image.GetPointData().SetScalars(self.nps.numpy_to_vtk(values, deep=True))
        tf = layer["transfer_function"]
        colormap = self.payload.colormap(tf["colormap"])
        color = vtk.vtkColorTransferFunction()
        lo, hi = (float(v) for v in tf["range"])
        if colormap.get("categorical"):
            for entry in colormap["entries"]:
                rgb = [float(c) for c in entry["color"][:3]]
                color.AddRGBPoint(entry["value"] - 0.499, *rgb)
                color.AddRGBPoint(entry["value"] + 0.499, *rgb)
        else:
            lut = np.asarray(self.payload.array(colormap["lut"])).reshape(256, 4) / 255.0
            for k in range(256):
                color.AddRGBPoint(lo + (k + 0.5) / 256 * (hi - lo if hi > lo else 1.0), *lut[k, :3])
        opacity = vtk.vtkPiecewiseFunction()
        for value, alpha in tf["opacity"]:
            opacity.AddPoint(float(value), float(alpha))
        prop = vtk.vtkVolumeProperty()
        prop.SetColor(color)
        prop.SetScalarOpacity(opacity)
        # Opacity is per smallest voxel spacing (payload spec §6.6, as the web viewer does), so the picture
        # does not depend on the absolute spacing (nm vs grid index) of the grid.
        prop.SetScalarOpacityUnitDistance(float(min(grid["spacing"])))
        if layer.get("sampling", "linear") == "nearest":
            prop.SetInterpolationTypeToNearest()
        else:
            prop.SetInterpolationTypeToLinear()
        if layer.get("shade"):
            prop.ShadeOn()
        mapper = vtk.vtkFixedPointVolumeRayCastMapper()
        mapper.SetInputData(image)
        mapper.AutoAdjustSampleDistancesOff()
        mapper.SetSampleDistance(min(grid["spacing"]) / 2)
        mapper.SetImageSampleDistance(1.0)
        volume = vtk.vtkVolume()
        volume.SetMapper(mapper)
        volume.SetProperty(prop)
        direction = np.asarray(grid.get("direction") or (1, 0, 0, 0, 1, 0, 0, 0, 1), dtype=np.float64).reshape(3, 3)
        origin = np.asarray(grid["origin"], dtype=np.float64) + self.offset_of(layer)
        matrix = vtk.vtkMatrix4x4()
        for r in range(3):
            for c in range(3):
                matrix.SetElement(r, c, direction[r, c])
            matrix.SetElement(r, 3, origin[r])
        volume.SetUserMatrix(matrix)
        return [volume]

    # -- overlays ---------------------------------------------------------------

    def font(self, prop, bold=False):
        """DejaVu Sans (matplotlib's font files) when available, else VTK's embedded Times.

        VTK's embedded 'Arial' draws '[' and ']' as parentheses, which would turn
        variant names such as T[100] into T(100).
        """
        if self.fonts:
            prop.SetFontFamily(self.vtk.VTK_FONT_FILE)
            prop.SetFontFile(self.fonts[1 if bold else 0])
        else:
            prop.SetFontFamilyToTimes()
            prop.SetBold(bold)

    def text(self, text, x, y, size_px, color=None, *, halign="left", valign="bottom", bold=False):
        actor = self.vtk.vtkTextActor()
        actor.SetInput(text)
        prop = actor.GetTextProperty()
        prop.SetFontSize(max(1, int(round(self.px(size_px)))))
        prop.SetColor(*(color or self.ink))
        self.font(prop, bold)
        getattr(prop, {"left": "SetJustificationToLeft", "center": "SetJustificationToCentered",
                       "right": "SetJustificationToRight"}[halign])()
        getattr(prop, {"bottom": "SetVerticalJustificationToBottom", "center": "SetVerticalJustificationToCentered",
                       "top": "SetVerticalJustificationToTop"}[valign])()
        actor.SetDisplayPosition(int(round(x)), int(round(y)))
        return actor

    def quads(self, rects, rgba):
        """2D actor of axis-aligned display-space rectangles ``[(x0, y0, x1, y1)]`` with per-rect RGBA8 colours."""
        vtk, np = self.vtk, self.np
        rects = np.asarray(rects, dtype=np.float64).reshape(-1, 4)
        corners = np.stack([rects[:, [0, 1]], rects[:, [2, 1]], rects[:, [2, 3]], rects[:, [0, 3]]], axis=1)
        points = np.concatenate([corners.reshape(-1, 2), np.zeros((4 * len(rects), 1))], axis=1)
        poly = vtk.vtkPolyData()
        poly.SetPoints(self.points(points, np.zeros(3)))
        poly.SetPolys(self.cells(np.arange(4 * len(rects)), 4))
        poly.GetCellData().SetScalars(self.rgba_array(rgba))
        mapper = vtk.vtkPolyDataMapper2D()
        mapper.SetInputData(poly)
        mapper.SetColorModeToDirectScalars()
        mapper.SetScalarModeToUseCellData()
        actor = vtk.vtkActor2D()
        actor.SetMapper(mapper)
        return actor

    def frame(self, x0, y0, x1, y1):
        vtk = self.vtk
        poly = vtk.vtkPolyData()
        poly.SetPoints(self.points([[x0, y0, 0], [x1, y0, 0], [x1, y1, 0], [x0, y1, 0]], self.np.zeros(3)))
        poly.SetLines(self.cells([0, 1, 1, 2, 2, 3, 3, 0], 2))
        mapper = vtk.vtkPolyDataMapper2D()
        mapper.SetInputData(poly)
        actor = vtk.vtkActor2D()
        actor.SetMapper(mapper)
        actor.GetProperty().SetColor(*self.ink)
        actor.GetProperty().SetLineWidth(max(1.0, self.px(1.0)))
        return actor

    def overlay_scalar_bar(self, layer):
        np = self.np
        colormap = self.payload.colormap(layer["colormap"])
        lut = np.asarray(self.payload.array(colormap["lut"])).reshape(256, 4)
        lo, hi = (float(v) for v in layer["range"])
        count = int(layer.get("label_count", 5))
        fmt = layer.get("format", ".3g")
        labels = [_label(lo + (hi - lo) * k / (count - 1), fmt) for k in range(count)]
        font = 12.0
        window = (self.W / self.mag, self.H / self.mag)
        vertical = layer.get("orientation", "vertical") == "vertical"
        thick, length = sorted(float(v) for v in layer.get("size_px") or (28, 320))
        length = min(length, 0.7 * (window[1] if vertical else window[0]))
        bar_w, bar_h = (thick, length) if vertical else (length, thick)
        title = layer.get("title")
        unit = layer.get("unit")
        if unit and unit != "1" and title and f"[{unit}]" not in title:
            title = f"{title} [{unit}]"
        char = font * 0.62
        label_w = max(len(text) for text in labels) * char + 6
        title_w = len(title) * char * 1.1 if title else 0.0
        title_h = font * 1.7 if title else 0.0
        if vertical:
            box = (max(bar_w + label_w, title_w), bar_h + title_h + font / 2)
        else:
            box = (max(bar_w + label_w, title_w), bar_h + font * 1.6 + title_h)
        anchor = layer.get("anchor", "right")
        x, y = _place(anchor, layer.get("offset_px") or (24, 24), box, window)
        fx = ANCHOR_FRACTIONS.get(anchor, (1, 0.5))[0]
        bar_x = x + box[0] - bar_w - (label_w if vertical else 0) if fx == 1 else x
        bar_y = y + font / 2 if vertical else y + font * 1.6
        X, Y, bw, bh = self.px(bar_x), self.px(bar_y), self.px(bar_w), self.px(bar_h)
        steps = np.arange(257) / 256
        if vertical:
            rects = np.stack([np.full(256, X), Y + steps[:-1] * bh, np.full(256, X + bw), Y + steps[1:] * bh], axis=1)
        else:
            rects = np.stack([X + steps[:-1] * bw, np.full(256, Y), X + steps[1:] * bw, np.full(256, Y + bh)], axis=1)
        actors = [self.quads(rects, lut), self.frame(X, Y, X + bw, Y + bh)]
        for k, text in enumerate(labels):
            t = k / (count - 1)
            if vertical:
                actors.append(self.text(text, X + bw + self.px(4), Y + t * bh, font, valign="center"))
            else:
                actors.append(self.text(text, X + t * bw, Y - self.px(2), font, halign="center", valign="top"))
        if title:
            halign = {0: "left", 0.5: "center", 1: "right"}[fx]
            tx = {"left": self.px(x), "center": self.px(x + box[0] / 2), "right": self.px(x + box[0])}[halign]
            actors.append(self.text(title, tx, Y + bh + self.px(6), font, halign=halign, bold=True))
        return actors

    def overlay_legend(self, layer):
        np = self.np
        colormap = self.payload.colormap(layer["colormap"])
        entries = {e["value"]: e for e in colormap["entries"]}
        values = layer.get("values") or sorted(entries)
        rows = [entries.get(v, {"value": v, "name": str(v), "color": colormap.get("unknown_color", (0.5, 0.5, 0.5))})
                for v in values]
        font, columns = 12.0, max(1, int(layer.get("columns", 1)))
        per_column = -(-len(rows) // columns) if rows else 0
        row_h = font * 1.5
        col_w = font * 1.4 + max([len(str(r["name"])) for r in rows] or [4]) * font * 0.62 + font
        title = layer.get("title")
        title_h = font * 1.7 if title else 0.0
        title_w = len(title) * font * 0.68 if title else 0.0
        box = (max(columns * col_w, title_w), per_column * row_h + title_h)
        anchor = layer.get("anchor", "right")
        x, y = _place(anchor, layer.get("offset_px") or (16, 16), box, (self.W / self.mag, self.H / self.mag))
        fx = ANCHOR_FRACTIONS.get(anchor, (1, 0.5))[0]
        title_x = x + box[0] if fx == 1 else x
        if fx == 1:
            x += box[0] - columns * col_w
        actors, rects, colors = [], [], []
        top = y + per_column * row_h
        for index, row in enumerate(rows):
            column, line = divmod(index, per_column)
            cx = x + column * col_w
            cy = top - (line + 1) * row_h
            swatch = cy + 0.15 * row_h
            rects.append([self.px(cx), self.px(swatch), self.px(cx + font), self.px(swatch + font)])
            rgba = [float(c) for c in row["color"]] + ([1.0] if len(row["color"]) == 3 else [])
            colors.append(np.floor(np.clip(rgba, 0, 1) * 255 + 0.5))
            actors.append(self.text(str(row["name"]), self.px(cx + font * 1.4), self.px(swatch + font / 2), font,
                                    valign="center"))
        if rects:
            actors.insert(0, self.quads(rects, np.asarray(colors, dtype=np.uint8)))
        if title:
            actors.append(self.text(title, self.px(title_x), self.px(top + font * 0.4), font,
                                    halign="right" if fx == 1 else "left", bold=True))
        return actors

    def overlay_text(self, layer):
        font = float(layer.get("font_size_px", 14))
        anchor = layer.get("anchor", "top_left")
        fx, fy = ANCHOR_FRACTIONS.get(anchor, (0, 1))
        ox, oy = layer.get("offset_px") or (12, 12)
        x = ox if fx == 0 else (self.W / self.mag - ox if fx == 1 else self.W / self.mag / 2 + ox)
        y = oy if fy == 0 else (self.H / self.mag - oy if fy == 1 else self.H / self.mag / 2 - oy)
        halign = {0: "left", 0.5: "center", 1: "right"}[fx]
        valign = {0: "bottom", 0.5: "center", 1: "top"}[fy]
        color = [float(c) for c in (layer.get("color") or self.ink)[:3]]
        return [self.text(layer["text"], self.px(x), self.px(y), font, color, halign=halign, valign=valign)]

    def corner_renderer(self, layer, default_size, default_anchor):
        size = layer.get("size_px") or (default_size, default_size)
        limit = 0.35 * min(self.W, self.H) / self.mag
        w, h = min(float(size[0]), limit), min(float(size[1]), limit)
        x, y = _place(layer.get("anchor", default_anchor), layer.get("offset_px") or (12, 12), (w, h),
                      (self.W / self.mag, self.H / self.mag))
        window = (self.W / self.mag, self.H / self.mag)
        renderer = self.vtk.vtkRenderer()
        renderer.SetLayer(1)
        renderer.InteractiveOff()
        renderer.SetViewport(x / window[0], y / window[1], (x + w) / window[0], (y + h) / window[1])
        return renderer, (x, y, w, h)

    def sync_corner(self, renderer, centre, radius):
        main = self.renderer.GetActiveCamera()
        direction = self.np.asarray(main.GetDirectionOfProjection())
        camera = renderer.GetActiveCamera()
        camera.SetFocalPoint(*centre)
        camera.SetPosition(*(self.np.asarray(centre) - direction * radius * 4))
        camera.SetViewUp(*main.GetViewUp())
        camera.ParallelProjectionOn()
        camera.SetParallelScale(radius)
        renderer.ResetCameraClippingRange()

    def overlay_orientation_legend(self, layer):
        from .colormaps import orientation_hsl
        vtk, np = self.vtk, self.np
        renderer, (x, y, w, h) = self.corner_renderer(layer, 120, "bottom_right")
        sphere = vtk.vtkSphereSource()
        sphere.SetRadius(1.0)
        sphere.SetThetaResolution(96)
        sphere.SetPhiResolution(64)
        sphere.Update()
        poly = sphere.GetOutput()
        normals = self.nps.vtk_to_numpy(poly.GetPoints().GetData()).astype(np.float64)
        rgb = orientation_hsl(normals, 1.0, layer.get("lightness_range") or (0.0, 1.0))
        rgba = np.concatenate([rgb, np.ones((len(rgb), 1))], axis=1)
        poly.GetPointData().SetScalars(self.rgba_array(np.floor(np.clip(rgba, 0, 1) * 255 + 0.5)))
        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputData(poly)
        mapper.SetColorModeToDirectScalars()
        actor = vtk.vtkActor()
        actor.SetMapper(mapper)
        actor.GetProperty().SetAmbient(0.35)
        actor.GetProperty().SetDiffuse(0.65)
        actor.GetProperty().SetSpecular(0.0)
        renderer.AddActor(actor)
        self.corners.append((renderer, (0.0, 0.0, 0.0), 1.08))
        actors = []
        if layer.get("title"):
            actors.append(self.text(layer["title"], self.px(x + w / 2), self.px(y + h + 2), 12, halign="center"))
        return actors

    def overlay_axes_triad(self, layer):
        vtk = self.vtk
        renderer, _ = self.corner_renderer(layer, 80, "bottom_left")
        axes = vtk.vtkAxesActor()
        axes.SetTotalLength(1.0, 1.0, 1.0)
        axes.SetShaftTypeToCylinder()
        axes.SetCylinderRadius(0.03)
        labels = layer.get("labels") or ["x", "y", "z"]
        for index, (name, rgb) in enumerate(zip("XYZ", ((0.85, 0.1, 0.1), (0.1, 0.65, 0.1), (0.1, 0.25, 0.9)))):
            getattr(axes, f"Get{name}AxisShaftProperty")().SetColor(*rgb)
            getattr(axes, f"Get{name}AxisTipProperty")().SetColor(*rgb)
            getattr(axes, f"Set{name}AxisLabelText")(str(labels[index]))
            caption = getattr(axes, f"Get{name}AxisCaptionActor2D")()
            caption.GetCaptionTextProperty().SetColor(*self.ink)
            caption.GetCaptionTextProperty().ShadowOff()
            caption.GetCaptionTextProperty().ItalicOff()
            caption.GetCaptionTextProperty().SetFontSize(max(1, int(self.px(12))))
            self.font(caption.GetCaptionTextProperty())
            caption.GetTextActor().SetTextScaleModeToNone()
        renderer.AddActor(axes)
        self.corners.append((renderer, (0.45, 0.45, 0.45), 0.95))
        return []

    # -- scene ------------------------------------------------------------------

    def camera(self, bounds):
        from .layers import default_view_up, fit_camera
        np = self.np
        spec = dict(self.view.get("camera") or {})
        preset = spec.get("preset") or self.view.get("preset") or "iso"
        if spec.get("position") is not None and spec.get("focal_point") is not None:
            position = np.asarray(spec["position"], dtype=np.float64) - self.origin
            focal = np.asarray(spec["focal_point"], dtype=np.float64) - self.origin
            up = spec.get("view_up") or default_view_up(position.tolist(), focal.tolist())
            fitted = None
        else:
            fitted = fit_camera(bounds, preset, view_angle_deg=float(spec.get("view_angle_deg", 30.0)),
                                zoom=float(spec.get("zoom", 1.0)))
            position, focal, up = (np.asarray(fitted[k]) for k in ("position", "focal_point", "view_up"))
        camera = self.renderer.GetActiveCamera()
        camera.SetFocalPoint(*focal)
        camera.SetPosition(*position)
        camera.SetViewUp(*up)
        camera.SetViewAngle(float(spec.get("view_angle_deg", 30.0)))
        if spec.get("projection") == "parallel":
            camera.ParallelProjectionOn()
            scale = spec.get("parallel_scale") or (fitted or {}).get("parallel_scale")
            if scale is None:
                radius = 0.5 * float(np.linalg.norm(np.subtract(*bounds[::-1]))) if bounds else 1.0
                scale = radius / float(spec.get("zoom", 1.0))
            camera.SetParallelScale(float(scale))
        elif fitted is None and spec.get("zoom") not in (None, 1, 1.0):
            camera.Zoom(float(spec["zoom"]))
        camera.OrthogonalizeViewUp()

    def render(self, out_path):
        vtk = self.vtk
        window = vtk.vtkRenderWindow()
        window.SetOffScreenRendering(1)
        window.SetMultiSamples(0)
        window.SetSize(self.W, self.H)
        window.SetNumberOfLayers(2)
        if self.transparent:
            window.SetAlphaBitPlanes(1)
        self.renderer = vtk.vtkRenderer()
        self.renderer.SetLayer(0)
        self.renderer.SetBackground(*self.background)
        if self.transparent:
            self.renderer.SetBackgroundAlpha(0.0)
        background = self.view.get("background") or {}
        if background.get("type") == "gradient" and background.get("color2"):
            self.renderer.GradientBackgroundOn()
            self.renderer.SetBackground2(*[float(c) for c in background["color2"][:3]])
        window.AddRenderer(self.renderer)
        self.corners = []
        overlays = []
        translucent = False
        for layer in self.layers:
            kind = layer.get("type")
            if kind == "overlay":
                method = getattr(self, "overlay_" + str(layer.get("kind")), None)
                if method is not None:
                    overlays.append((method, layer))
                continue
            method = getattr(self, "layer_" + str(kind), None)
            if method is None:
                continue            # clients skip unknown layer types
            for prop in method(layer):
                if isinstance(prop, vtk.vtkVolume):
                    self.renderer.AddVolume(prop)
                else:
                    translucent = translucent or prop.GetProperty().GetOpacity() < 1
                    self.renderer.AddActor(prop)
        if translucent:
            self.renderer.SetUseDepthPeeling(1)
            self.renderer.SetMaximumNumberOfPeels(8)
        bounds = self.m.get("bounds")
        if bounds is None:
            b = self.renderer.ComputeVisiblePropBounds()
            bounds = [[b[0], b[2], b[4]], [b[1], b[3], b[5]]] if b[0] <= b[1] else None
        self.camera(bounds)
        if self.lighting == "three_point":
            kit = vtk.vtkLightKit()
            kit.SetKeyLightIntensity(0.75 * float((self.view.get("lighting") or {}).get("intensity", 1.0)))
            kit.AddLightsToRenderer(self.renderer)
        self.renderer.ResetCameraClippingRange()
        for method, layer in overlays:
            for actor in method(layer):
                self.renderer.AddActor2D(actor)
        for renderer, centre, radius in self.corners:
            window.AddRenderer(renderer)
            self.sync_corner(renderer, centre, radius)
        window.Render()
        grab = vtk.vtkWindowToImageFilter()
        grab.SetInput(window)
        grab.SetScale(1)
        grab.ReadFrontBufferOff()
        if self.transparent:
            grab.SetInputBufferTypeToRGBA()
        else:
            grab.SetInputBufferTypeToRGB()
        grab.Update()
        writer = vtk.vtkPNGWriter()
        writer.SetFileName(str(out_path))
        writer.SetInputConnection(grab.GetOutputPort())
        writer.Write()
        return {"width": self.W, "height": self.H}


def _label(value, fmt):
    """A scalar-bar label: Python's format(), with ``d`` (integers, as in d3) applied to the rounded value."""
    return format(int(round(value)), fmt) if fmt.endswith("d") else format(value, fmt)


def _font_files():
    """``(regular, bold)`` DejaVu Sans TTF paths shipped with matplotlib, or ``None``."""
    try:
        import matplotlib
    except ImportError:
        return None
    folder = Path(matplotlib.get_data_path()) / "fonts" / "ttf"
    files = (folder / "DejaVuSans.ttf", folder / "DejaVuSans-Bold.ttf")
    return tuple(str(f) for f in files) if all(f.is_file() for f in files) else None


def _named(array, name):
    array.SetName(name)
    return array


def _perpendicular(vector, np):
    vector = np.asarray(vector, dtype=np.float64)
    trial = np.array([0.0, 0.0, 1.0]) if abs(vector[2]) < 0.9 * (np.linalg.norm(vector) or 1) else np.array([1.0, 0, 0])
    result = np.cross(vector, trial)
    return result / (np.linalg.norm(result) or 1.0)


def _probe_child():
    import vtk
    from vtk.util.numpy_support import vtk_to_numpy
    window = vtk.vtkRenderWindow()
    window.SetOffScreenRendering(1)
    window.SetMultiSamples(0)
    window.SetSize(32, 24)
    renderer = vtk.vtkRenderer()
    renderer.SetBackground(1.0, 1.0, 1.0)
    window.AddRenderer(renderer)
    plane = vtk.vtkPlaneSource()
    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputConnection(plane.GetOutputPort())
    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    actor.GetProperty().SetColor(1.0, 0.0, 0.0)
    actor.GetProperty().SetAmbient(1.0)
    actor.GetProperty().SetDiffuse(0.0)
    renderer.AddActor(actor)
    renderer.ResetCamera()
    renderer.GetActiveCamera().Zoom(0.6)
    window.Render()
    grab = vtk.vtkWindowToImageFilter()
    grab.SetInput(window)
    grab.ReadFrontBufferOff()
    grab.Update()
    image = grab.GetOutput()
    pixels = vtk_to_numpy(image.GetPointData().GetScalars()).reshape(24, 32, -1)
    capabilities = (window.ReportCapabilities() or "").splitlines()
    renderer_line = next((line.split(":", 1)[1].strip() for line in capabilities if "renderer string" in line), "")
    ok = tuple(pixels[12, 16, :3]) == (255, 0, 0) and tuple(pixels[0, 0, :3]) == (255, 255, 255)
    result = {"ok": bool(ok), "vtk": vtk.vtkVersion.GetVTKVersion(), "window": window.GetClassName(),
              "renderer": renderer_line}
    if not ok:
        result["error"] = f"probe image is wrong (centre {tuple(int(v) for v in pixels[12, 16])})"
    return result


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(prog="python -m suan.render.offscreen",
                                     description="Render an stk.payload/2 (.stkp) to PNG with offscreen VTK.")
    parser.add_argument("--probe", action="store_true", help="check offscreen rendering and print JSON")
    parser.add_argument("--payload", help=".stkp file to render")
    parser.add_argument("--out", help="PNG to write")
    parser.add_argument("--width", type=int)
    parser.add_argument("--height", type=int)
    parser.add_argument("--magnification", type=int, default=1)
    parser.add_argument("--transparent", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.probe:
            result = _probe_child()
        else:
            if not args.payload or not args.out:
                parser.error("--payload and --out are required")
            from .payload import read_stkp
            renderer = _Renderer(read_stkp(args.payload), width=args.width, height=args.height,
                                 magnification=args.magnification, transparent=args.transparent)
            result = {"ok": True, **renderer.render(args.out)}
    except Exception as error:  # reported to the parent as JSON
        print(json.dumps({"ok": False, "error": f"{type(error).__name__}: {error}"}), flush=True)
        return 2
    print(json.dumps(result), flush=True)
    return 0 if result.get("ok") else 3


if __name__ == "__main__":
    sys.exit(main())
