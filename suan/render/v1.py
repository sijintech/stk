"""Downgrade an ``stk.payload/2`` payload to a scene v1 (docs/specs/stk-render-payload-v2.md §11).

For clients that accept only ``stk.scene/1`` (the web viewer's ``view.build``
path, Synorder; the C++ ``SPACE_STK`` editor is archived under the tag
``archive/blender-workbench-2026-09``): take the first visible ``triangles``
layer, else expand the first ``instances`` layer into glyph triangles, else turn the
first ``slice_image`` into two triangles per texel quad. The mesh is reduced
to the v1 budget (80 000 vertices, 480 000 indices) with
``suan.visualization.scene._poly_mesh`` (VTK decimation; a NumPy vertex
clustering is used when VTK is not importable), coloured by the layer's active
attribute (the magnitude for vectors and directions), and keeps
``render_origin``. The result passes :func:`validate_scene`, the scene v1 wire
check (also used on ``view.build`` scenes).
"""
import math

__all__ = ["MAX_INDICES", "MAX_VERTICES", "glyph_mesh", "to_scene_v1", "validate_scene"]

MAX_VERTICES = 80_000
MAX_INDICES = 480_000


def validate_scene(scene):
    """Check a scene v1 ``{"manifest", "mesh"}`` before handing its untrusted numeric arrays to native code.

    Returns ``scene`` unchanged; raises ``ValueError`` on an unsupported version or association,
    invalid spatial metadata or scalar range, non-finite samples, or a mesh over the v1 budget.
    """
    m, mesh = scene["manifest"], scene["mesh"]
    if m["version"] != 1 or m.get("association", "point") != "point":
        raise ValueError("Unsupported scientific scene version or association")
    for key in ("origin", "render_origin", "spacing", "dimensions"):
        if len(m[key]) != 3 or not all(isinstance(v, (float, int)) and math.isfinite(v) for v in m[key]):
            raise ValueError("Invalid spatial metadata")
    if any(n < 1 or int(n) != n for n in m["dimensions"]) or min(m["spacing"]) <= 0:
        raise ValueError("Invalid grid dimensions/spacing")
    if len(m["value_range"]) != 2 or not all(math.isfinite(v) for v in m["value_range"]) or m["value_range"][1] < m["value_range"][0]:
        raise ValueError("Invalid scalar range")
    if len(mesh["positions"]) > MAX_VERTICES or len(mesh["values"]) != len(mesh["positions"]):
        raise ValueError("Invalid point count")
    if len(mesh["indices"]) % 3 or len(mesh["indices"]) > MAX_INDICES:
        raise ValueError("Invalid triangle count")
    for p in mesh["positions"]:
        if len(p) != 3 or not all(math.isfinite(v) and abs(v) < 1e30 for v in p):
            raise ValueError("Invalid render coordinates")
    if not all(math.isfinite(v) for v in mesh["values"]):
        raise ValueError("Invalid scalar samples")
    if any(isinstance(i, bool) or not isinstance(i, int) or not 0 <= i < len(mesh["positions"]) for i in mesh["indices"]):
        raise ValueError("Triangle index outside point array")
    return scene


def _np():
    import numpy
    return numpy


def glyph_mesh(shape, resolution=8):
    """Canonical glyph triangles (unit length along +x; spec §6.5) -> ``(points (n, 3), triangles (m, 3))``."""
    np = _np()
    res = max(3, int(resolution))
    angles = np.linspace(0.0, 2 * np.pi, res, endpoint=False)
    ring = np.stack([np.zeros(res), np.cos(angles), np.sin(angles)], axis=1)

    def cylinder(r, x0, x1):
        points = np.concatenate([ring * r + [x0, 0, 0], ring * r + [x1, 0, 0]])
        i = np.arange(res)
        j = (i + 1) % res
        tris = np.concatenate([np.stack([i, j, res + j], axis=1), np.stack([i, res + j, res + i], axis=1)])
        return points, tris

    def cone(r, x0, x1):
        points = np.concatenate([ring * r + [x0, 0, 0], [[x1, 0, 0], [x0, 0, 0]]])
        i = np.arange(res)
        j = (i + 1) % res
        tris = np.concatenate([np.stack([i, j, np.full(res, res)], axis=1),
                               np.stack([j, i, np.full(res, res + 1)], axis=1)])
        return points, tris

    def merge(*parts):
        points, tris, offset = [], [], 0
        for p, t in parts:
            points.append(p)
            tris.append(t + offset)
            offset += len(p)
        return np.concatenate(points), np.concatenate(tris)

    if shape == "arrow":
        return merge(cylinder(0.03, 0.0, 0.65), cone(0.1, 0.65, 1.0))
    if shape == "cone":
        return cone(0.25, 0.0, 1.0)
    if shape == "line":
        return cylinder(0.01, 0.0, 1.0)
    if shape == "cube":
        corners = np.array([[x, y, z] for z in (-.5, .5) for y in (-.5, .5) for x in (-.5, .5)])
        tris = np.array([[0, 2, 1], [1, 2, 3], [4, 5, 6], [5, 7, 6], [0, 1, 4], [1, 5, 4],
                         [2, 6, 3], [3, 6, 7], [0, 4, 2], [2, 4, 6], [1, 3, 5], [3, 7, 5]])
        return corners, tris
    if shape == "sphere":
        rings = max(2, res // 2)
        theta = np.linspace(0, np.pi, rings + 1)[1:-1]
        body = np.array([[0.5 * math.cos(t), 0.5 * math.sin(t) * math.cos(a), 0.5 * math.sin(t) * math.sin(a)]
                         for t in theta for a in angles])
        points = np.concatenate([[[0.5, 0, 0]], body, [[-0.5, 0, 0]]])
        tris = []
        for i in range(res):
            j = (i + 1) % res
            tris.append([0, 1 + j, 1 + i])
            last = 1 + (len(theta) - 1) * res
            tris.append([len(points) - 1, last + i, last + j])
            for r in range(len(theta) - 1):
                a, b = 1 + r * res, 1 + (r + 1) * res
                tris += [[a + i, a + j, b + i], [a + j, b + j, b + i]]
        return points, np.array(tris)
    raise ValueError(f"Unknown glyph shape {shape!r}")


def _rotation_to(directions):
    """Rotation matrices taking +x to each unit direction (Rodrigues; antiparallel -> 180° about z)."""
    np = _np()
    d = directions / np.linalg.norm(directions, axis=1, keepdims=True)
    x = np.array([1.0, 0.0, 0.0])
    v = np.cross(np.broadcast_to(x, d.shape), d)
    c = d[:, 0]
    k = np.zeros((len(d), 3, 3))
    k[:, 0, 1], k[:, 0, 2], k[:, 1, 0] = -v[:, 2], v[:, 1], v[:, 2]
    k[:, 1, 2], k[:, 2, 0], k[:, 2, 1] = -v[:, 0], -v[:, 1], v[:, 0]
    with np.errstate(divide="ignore", invalid="ignore"):
        factor = np.where(c > -1 + 1e-12, 1.0 / (1.0 + c), 0.0)
    rot = np.eye(3)[None] + k + np.einsum("nij,njk->nik", k, k) * factor[:, None, None]
    flip = c <= -1 + 1e-12
    rot[flip] = np.diag([-1.0, -1.0, 1.0])
    return rot


def _layer_values(payload, layer, count):
    """Scalar per position/instance/sample for the layer's colour attribute (magnitude for vectors)."""
    np = _np()
    color = (layer.get("appearance") or {}).get("color") or {}
    attributes = layer.get("attributes") or {}
    name = color.get("attribute") if color.get("by") == "attribute" else None
    if color.get("by") == "direction" and name is None and "directions" in layer:
        return np.linalg.norm(payload.array(layer["directions"]).astype(np.float64), axis=1), None, "direction"
    if name is None:
        name = next((key for key, a in attributes.items() if a.get("association", "point") == "point"), None)
    if name is None or attributes[name].get("association", "point") != "point":
        return np.zeros(count), None, name or "solid"
    values = payload.array(attributes[name]["accessor"]).astype(np.float64)
    if values.ndim > 1:
        component = color.get("component")
        values = values[:, int(component)] if isinstance(component, int) else np.linalg.norm(values, axis=1)
    return values, attributes[name], name


def _choose(payload):
    layers = [layer for layer in payload.layers if layer.get("visible", True)]
    for kind in ("triangles", "instances", "slice_image"):
        for layer in layers:
            if layer.get("type") == kind:
                return layer
    return None


def _mesh(payload, layer, budget):
    """``(positions relative to the layer origin, triangles, values, attribute, name, reduced)``."""
    np = _np()
    kind = layer["type"]
    reduced = False
    if kind == "triangles":
        positions = payload.array(layer["positions"]).astype(np.float64)
        triangles = payload.array(layer["indices"]).astype(np.int64).reshape(-1, 3)
        values, attribute, name = _layer_values(payload, layer, len(positions))
        return positions, triangles, values, attribute, name, reduced
    if kind == "instances":
        positions = payload.array(layer["positions"]).astype(np.float64)
        directions = payload.array(layer["directions"]).astype(np.float64)
        values, attribute, name = _layer_values(payload, layer, len(positions))
        glyph = layer.get("glyph") or {}
        points, tris = glyph_mesh(glyph.get("shape", "arrow"), glyph.get("resolution", 8))
        if glyph.get("center", False) and glyph.get("shape", "arrow") in ("arrow", "cone", "line"):
            points = points - [0.5, 0.0, 0.0]
        scales = _instance_scales(payload, layer, directions)
        keep = (np.linalg.norm(directions, axis=1) > 0) & np.isfinite(scales) & (scales > 0)
        limit = max(1, min(budget[0] // len(points), budget[1] // (3 * len(tris))))
        index = np.flatnonzero(keep)
        if len(index) > limit:
            index, reduced = index[:limit], True
        rot = _rotation_to(directions[index]) if len(index) else np.zeros((0, 3, 3))
        local = np.einsum("nij,pj->npi", rot, points) * scales[index, None, None]
        mesh_points = (local + positions[index, None, :]).reshape(-1, 3)
        mesh_tris = (tris[None] + (np.arange(len(index)) * len(points))[:, None, None]).reshape(-1, 3)
        mesh_values = np.repeat(values[index], len(points))
        return mesh_points, mesh_tris, mesh_values, attribute, name, reduced
    w, h = layer["size"]
    plane = {k: np.asarray(layer["plane"][k], dtype=np.float64) for k in ("origin", "u", "v")}
    values, attribute, name = _layer_values(payload, layer, w * h)
    grid = values.reshape(h, w)
    f = 1
    while (-(-w // f)) * (-(-h // f)) > budget[0] or 6 * max(-(-w // f) - 1, 1) * max(-(-h // f) - 1, 1) > budget[1]:
        f += 1
    grid = grid[::f, ::f]
    reduced = f > 1
    nh, nw = grid.shape
    du = plane["u"] / (w - 1) * f if w > 1 else np.zeros(3)
    dv = plane["v"] / (h - 1) * f if h > 1 else np.zeros(3)
    jj, ii = np.meshgrid(np.arange(nh), np.arange(nw), indexing="ij")
    positions = plane["origin"] + ii.reshape(-1, 1) * du + jj.reshape(-1, 1) * dv
    i, j = np.meshgrid(np.arange(nw - 1), np.arange(nh - 1), indexing="xy")
    a = (j * nw + i).reshape(-1)
    triangles = np.concatenate([np.stack([a, a + 1, a + nw + 1], axis=1), np.stack([a, a + nw + 1, a + nw], axis=1)])
    return positions, triangles, grid.reshape(-1), attribute, name, reduced


def _instance_scales(payload, layer, directions):
    np = _np()
    if "scales" in layer:
        return payload.array(layer["scales"]).astype(np.float64)
    scale = (layer.get("appearance") or {}).get("scale") or {"by": "uniform", "factor": 1.0}
    factor = float(scale.get("factor", 1.0))
    if scale.get("by") == "magnitude":
        return factor * np.linalg.norm(directions, axis=1)
    if scale.get("by") == "attribute":
        attribute = layer["attributes"][scale["attribute"]]
        values = payload.array(attribute["accessor"]).astype(np.float64)
        return factor * (np.linalg.norm(values, axis=1) if values.ndim > 1 else values)
    return np.full(len(directions), factor)


def _reduce(positions, triangles, values, max_vertices, max_indices):
    """Decimate with ``scene._poly_mesh`` (VTK) or, without VTK, NumPy vertex clustering.

    Meshes far over the budget are first thinned by fast vertex clustering to
    about three times the final size, so VTK's decimation stays quick.
    """
    from .payload import cluster_decimate
    np = _np()
    target_vertices = min(max_vertices, max_indices // 7)       # closed meshes have ~2 triangles per vertex
    try:
        import vtk  # noqa: F401  (only to choose the path)
        from vtk.util.numpy_support import numpy_to_vtk, numpy_to_vtkIdTypeArray
        from suan.visualization.scene import _poly_mesh
    except ImportError:
        target = min(max_indices // 3, 2 * max_vertices)
        while True:
            points, tris, _, attrs, _ = cluster_decimate(positions, triangles, max(1, target),
                                                         point_attributes={"v": (values, False)})
            if len(points) <= max_vertices and 3 * len(tris) <= max_indices or target <= 1:
                return points, tris, attrs["v"][0]
            target = int(target * 0.7)
    coarse = 6 * target_vertices
    if len(triangles) > 2 * coarse:
        positions, triangles, _, attrs, _ = cluster_decimate(positions, triangles, coarse,
                                                             point_attributes={"v": (values, False)})
        values = attrs["v"][0]
    for _ in range(6):
        poly = vtk.vtkPolyData()
        points = vtk.vtkPoints()
        points.SetData(numpy_to_vtk(np.ascontiguousarray(positions), deep=True))
        poly.SetPoints(points)
        cells = vtk.vtkCellArray()
        offsets = np.arange(0, 3 * len(triangles) + 1, 3, dtype=np.int64)
        cells.SetData(numpy_to_vtkIdTypeArray(offsets, deep=True),
                      numpy_to_vtkIdTypeArray(np.ascontiguousarray(triangles.reshape(-1), dtype=np.int64), deep=True))
        poly.SetPolys(cells)
        scalars = numpy_to_vtk(np.ascontiguousarray(values, dtype=np.float64), deep=True)
        scalars.SetName("value")
        poly.GetPointData().SetScalars(scalars)
        mesh = _poly_mesh(poly, np.zeros(3), target_vertices)
        new_positions = np.asarray(mesh["positions"], dtype=np.float64).reshape(-1, 3)
        new_triangles = np.asarray(mesh["indices"], dtype=np.int64).reshape(-1, 3)
        new_values = np.asarray(mesh["values"], dtype=np.float64)
        if len(new_positions) <= max_vertices and 3 * len(new_triangles) <= max_indices:
            return new_positions, new_triangles, new_values
        target_vertices = max(100, int(target_vertices * 0.7))
    raise ValueError("The mesh cannot be reduced to the scene v1 budget")


def to_scene_v1(payload, *, dataset_id=None, max_vertices=MAX_VERTICES, max_indices=MAX_INDICES):
    """Scene v1 ``{"manifest", "mesh"}`` of a :class:`suan.render.payload.Payload`."""
    np = _np()
    manifest = payload.manifest
    render_origin = [float(v) for v in manifest["render_origin"]]
    layer = _choose(payload)
    reduced = bool((manifest.get("source") or {}).get("reduced", False))
    if layer is None:
        positions, triangles, values = np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64), np.zeros(0)
        attribute, name = None, "none"
    else:
        positions, triangles, values, attribute, name, cut = _mesh(payload, layer, (max_vertices, max_indices))
        reduced = reduced or cut
        shift = np.asarray(layer.get("origin", render_origin), dtype=np.float64) - render_origin
        positions = positions + shift
        values = np.where(np.isfinite(values), values, np.nan)
        finite = values[np.isfinite(values)]
        values = np.where(np.isfinite(values), values, finite.min() if len(finite) else 0.0)
        if len(positions) > max_vertices or 3 * len(triangles) > max_indices:
            positions, triangles, values = _reduce(positions, triangles, values, max_vertices, max_indices)
            reduced = True
    finite = values[np.isfinite(values)]
    value_range = [float(finite.min()), float(finite.max())] if len(finite) else [0.0, 0.0]
    bounds = manifest.get("bounds")
    origin = [render_origin[a] + (bounds[0][a] if bounds else 0.0) for a in range(3)]
    unit = (attribute or {}).get("unit") or "unspecified"
    step = ((manifest.get("source") or {}).get("time") or {}).get("step")
    timestep = int(step) if isinstance(step, int) and not isinstance(step, bool) and step >= 0 else 0
    v1 = {"version": 1, "dataset_id": str(dataset_id or (manifest.get("source") or {}).get("graph") or "payload"),
          "field": str(name), "association": "point", "dimensions": [1, 1, 1], "origin": origin,
          "spacing": [1.0, 1.0, 1.0], "units": unit,
          "coordinate_units": manifest.get("length_unit", "unspecified").replace("grid_index", "grid index"),
          "components": 1, "component": 0, "timestep": timestep, "mode": "payload-v2", "axis": None, "index": None,
          "level": None, "value_range": value_range, "render_origin": render_origin, "display_reduced": reduced,
          "layer": None if layer is None else layer["id"],
          "resources": [{"kind": "triangle_mesh", "key": "mesh"}]}
    mesh = {"positions": positions.tolist(), "indices": [int(i) for i in triangles.reshape(-1)],
            "values": values.astype(float).tolist()}
    return {"manifest": v1, "mesh": mesh}
