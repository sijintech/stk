"""Small deterministic render scenes shared by the render tests (payload, v1 downgrade, offscreen goldens)."""
from itertools import product
import math

import numpy as np

from suan.render.layers import Attribute, Layer, Scene, fit_camera, union_bounds


def cubic26_categories():
    """STK numbering (docs/specs/domain-classifiers.md §2.1) without colours (the palette fills them)."""
    reps = [v for v in product((1, 0, -1), repeat=3) if any(v) and next(c for c in v if c) == 1]
    reps.sort(key=lambda v: sum(1 for c in v if c))
    families = {1: "T", 2: "O", 3: "R"}
    categories = [{"value": -1, "name": "unclassified"}, {"value": 0, "name": "substrate"}]
    for label, v in enumerate([d for r in reps for d in (r, tuple(-c for c in r))], start=1):
        norm = math.sqrt(sum(c * c for c in v))
        name = families[sum(1 for c in v if c)] + "[" + "".join("0" if c == 0 else ("1" if c > 0 else "-1")
                                                                for c in v) + "]"
        categories.append({"value": label, "name": name, "family": families[sum(1 for c in v if c)],
                           "direction": [c / norm for c in v]})
    return categories


def cube(center, half):
    """24 vertices (4 per face) and 12 counter-clockwise triangles."""
    positions, triangles = [], []
    for axis in range(3):
        for sign in (1, -1):
            u, v = [a for a in range(3) if a != axis]
            corners = []
            for du, dv in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
                p = [0.0, 0.0, 0.0]
                p[axis], p[u], p[v] = sign * half, du * half, dv * half
                corners.append([center[i] + p[i] for i in range(3)])
            normal = np.zeros(3)
            normal[axis] = sign
            if np.dot(np.cross(np.subtract(corners[1], corners[0]), np.subtract(corners[2], corners[0])), normal) < 0:
                corners = corners[::-1]
            base = len(positions)
            positions += corners
            triangles += [[base, base + 1, base + 2], [base, base + 2, base + 3]]
    return np.array(positions, dtype=np.float64), np.array(triangles)


def sphere(center, radius, n_theta=48, n_phi=24):
    """A closed UV sphere: ``(points, triangles)``."""
    phi = np.linspace(0, math.pi, n_phi + 1)[1:-1]
    theta = np.linspace(0, 2 * math.pi, n_theta, endpoint=False)
    body = np.array([[math.sin(p) * math.cos(t), math.sin(p) * math.sin(t), math.cos(p)] for p in phi for t in theta])
    points = np.concatenate([[[0, 0, 1]], body, [[0, 0, -1]]]) * radius + np.asarray(center)
    tris = []
    last = len(points) - 1
    for i in range(n_theta):
        j = (i + 1) % n_theta
        tris.append([0, 1 + i, 1 + j])
        tris.append([last, 1 + (len(phi) - 1) * n_theta + j, 1 + (len(phi) - 1) * n_theta + i])
        for r in range(len(phi) - 1):
            a, b = 1 + r * n_theta, 1 + (r + 1) * n_theta
            tris += [[a + i, b + i, a + j], [a + j, b + i, b + j]]
    return points, np.array(tris)


def box_lines(lo, hi, layer_id="box"):
    corners = np.array([[(lo, hi)[i][0], (lo, hi)[j][1], (lo, hi)[k][2]] for k in (0, 1) for j in (0, 1)
                        for i in (0, 1)], dtype=np.float64)
    edges = np.array([(0, 1), (2, 3), (4, 5), (6, 7), (0, 2), (1, 3), (4, 6), (5, 7), (0, 4), (1, 5), (2, 6), (3, 7)])
    return Layer("lines", id=layer_id, name="Outline", geometry={"positions": corners, "indices": edges},
                 props={"default_color": {"by": "solid", "solid": [0.0, 0.0, 0.0]}},
                 appearance={"color": [0.0, 0.0, 0.0], "width_px": 1.0})


def _scene(layers, *, preset="iso", width=320, height=240, render_origin=None, **view):
    bounds = union_bounds([layer.bounds() for layer in layers if layer.is_3d])
    origin = render_origin if render_origin is not None else [(a + b) / 2 for a, b in zip(*bounds)]
    camera = fit_camera(bounds, preset)
    view = {"schema": "stk.view/1", "camera": camera,
            "viewport": {"width": width, "height": height, "magnification": 1, "lock_aspect": True},
            "background": {"type": "solid", "color": [1.0, 1.0, 1.0]},
            "lighting": {"preset": "three_point", "intensity": 1.0}, **view}
    return Scene(layers=layers, view=view, render_origin=tuple(origin), length_unit="grid_index",
                 time={"step": 1000, "time": None})


def domains_scene(origin=(100.0, 50.0, 25.0)):
    """Three labelled cubes (STK labels 1 T[100], 7 O[110], 19 R[111]) with a legend, outline and axes."""
    positions, triangles, labels = [], [], []
    for label, dx in ((1, -3.0), (7, 0.0), (19, 3.0)):
        p, t = cube((origin[0] + dx, origin[1], origin[2]), 1.0)
        triangles.append(t + sum(len(q) for q in positions))
        positions.append(p)
        labels += [label] * len(p)
    positions = np.concatenate(positions)
    categories = cubic26_categories()
    domain = Attribute(np.array(labels, dtype=np.int16), categorical=True, categories=tuple(categories),
                       palette="stk:cubic-26-orientation", unit="1", quantity="domain_variant")
    height = Attribute(positions[:, 2].copy(), unit="grid_index")
    surface = Layer("triangles", id="domains", name="Domains",
                    geometry={"positions": positions, "indices": np.concatenate(triangles)},
                    attributes={"domain": domain, "height": height},
                    appearance={"color": {"by": "field", "field": "domain"}, "shading": "flat", "lighting": False})
    legend = Layer("overlay", id="legend", props={"kind": "legend", "entries": domain.entries(),
                                                  "palette": "stk:cubic-26-orientation", "values": [1, 7, 19],
                                                  "title": "Domain", "anchor": "top_right"})
    lo, hi = positions.min(axis=0) - 1, positions.max(axis=0) + 1
    axes = Layer("overlay", id="axes", props={"kind": "axes_triad", "anchor": "bottom_left", "size_px": 64})
    return _scene([surface, box_lines(lo, hi), legend, axes])


def glyph_scene():
    """A vortex of 32 arrows coloured by direction, with the orientation sphere."""
    points = np.array([(-3 + 2 * i, -3 + 2 * j, -3.0 + 6 * k) for k in range(2) for j in range(4) for i in range(4)],
                      dtype=np.float64)
    vectors = np.stack([-points[:, 1], points[:, 0], 0.5 * points[:, 2]], axis=1) * 0.25
    order = np.random.default_rng(7).permutation(len(points))
    arrows = Layer("instances", id="arrows", name="P",
                   geometry={"positions": points[order], "directions": vectors[order]},
                   attributes={"magnitude": Attribute(np.linalg.norm(vectors[order], axis=1))},
                   props={"default_color": {"by": "orientation"}, "progressive": {"shuffled": True, "seed": 7},
                          "sample_spacing": 2.0},
                   appearance={"shape": "arrow", "resolution": 12, "center": True})
    sphere_legend = Layer("overlay", id="sphere", props={"kind": "orientation_legend", "anchor": "bottom_right",
                                                         "size_px": 72, "title": "P"})
    return _scene([arrows, box_lines([-4, -4, -4], [4, 4, 4]), sphere_legend])


def gaussian_volume(n=16, spacing=0.5, origin=(-4.0, -4.0, -4.0)):
    k, j, i = np.meshgrid(np.arange(n), np.arange(n), np.arange(n), indexing="ij")
    xyz = np.stack([i, j, k], axis=-1) - (n - 1) / 2
    data = np.exp(-(xyz ** 2).sum(axis=-1) / (n / 3) ** 2)        # (z, y, x)
    grid = {"dimensions": [n, n, n], "origin": list(origin), "spacing": [spacing] * 3,
            "direction": [1, 0, 0, 0, 1, 0, 0, 0, 1]}
    return data, grid


def volume_scene():
    data, grid = gaussian_volume()
    volume = Layer("volume", id="density", name="Density",
                   geometry={"grid": grid, "data": data, "encoding": "auto", "field": "density",
                             "unit": "unspecified", "quantity": None, "categorical": False},
                   appearance={"colormap": "viridis", "range": [0.0, 1.0], "opacity": [[0.0, 0.0], [1.0, 0.9]]})
    bar = Layer("overlay", id="bar", props={"kind": "scalar_bar", "colormap": "viridis", "range": [0.0, 1.0],
                                            "unit": "unspecified", "title": "density", "anchor": "right",
                                            "offset_px": [16, 16], "size_px": [16, 160]})
    lo = np.asarray(grid["origin"])
    hi = lo + (np.asarray(grid["dimensions"]) - 1) * np.asarray(grid["spacing"])
    return _scene([volume, box_lines(lo, hi), bar])


def iso_scene():
    points, tris = sphere((0.0, 0.0, 0.0), 3.0)
    normals = points / np.linalg.norm(points, axis=1, keepdims=True)
    surface = Layer("triangles", id="iso", name="Isosurface",
                    geometry={"positions": points, "indices": tris, "normals": normals},
                    attributes={"height": Attribute(points[:, 2].copy(), unit="nm")},
                    appearance={"color": {"by": "field", "field": "height", "colormap": "coolwarm"}})
    bar = Layer("overlay", id="bar", props={"kind": "scalar_bar", "colormap": "coolwarm", "range": [-3.0, 3.0],
                                            "unit": "nm", "title": "height", "anchor": "right",
                                            "offset_px": [16, 16], "size_px": [16, 160]})
    axes = Layer("overlay", id="axes", props={"kind": "axes_triad", "anchor": "bottom_left", "size_px": 64})
    return _scene([surface, bar, axes], preset="+x")


def mixed_scene(origin=(1.0e6, -3.0, 7.0)):
    """Every M1 layer type, far from zero (render_origin precision)."""
    ox, oy, oz = origin
    positions, triangles = cube((ox, oy, oz), 1.0)
    cell_labels = np.array([1, 2] * 6, dtype=np.int32)
    categories = ({"value": 1, "name": "a", "color": [1.0, 0.0, 0.0]}, {"value": 2, "name": "b"})
    tri = Layer("triangles", id="tri", geometry={"positions": positions, "indices": triangles},
                attributes={"label": Attribute(cell_labels, association="cell", categorical=True,
                                               categories=categories, palette="stk:categorical"),
                            "x": Attribute(positions[:, 0] - ox, unit="m")},
                appearance={"color": {"by": "field", "field": "x", "colormap": "turbo", "range_mode": "symmetric"}})
    w, h = 5, 4
    values = np.arange(w * h, dtype=np.float64).reshape(h, w)
    image = Layer("slice_image", id="slice",
                  geometry={"plane": {"origin": [ox - 2, oy - 2, oz], "u": [4.0, 0.0, 0.0], "v": [0.0, 3.0, 0.0]},
                            "size": [w, h]},
                  attributes={"value": Attribute(values.reshape(-1), unit="Pa"),
                              "vec": Attribute(np.ones((w * h, 3)), component_names=("x", "y", "z"))},
                  appearance={"color": {"by": "field", "field": "value", "colormap": "gray"}})
    lines = box_lines([ox - 2, oy - 2, oz - 2], [ox + 2, oy + 2, oz + 2], "lines")
    rng = np.random.default_rng(1)
    cloud = rng.normal(size=(50, 3)) + origin
    points = Layer("points", id="points", geometry={"positions": cloud, "radii": np.full(50, 0.1)},
                   attributes={"r": Attribute(np.linalg.norm(cloud - origin, axis=1))},
                   props={"progressive": {"shuffled": True, "seed": 1}},
                   appearance={"color": {"by": "field"}, "render_as": "spheres"})
    arrows = Layer("instances", id="arrows", geometry={"positions": cloud[:20], "directions": rng.normal(size=(20, 3))},
                   props={"default_color": {"by": "orientation"}, "sample_spacing": 0.5},
                   appearance={"shape": "cone", "scale": {"by": "uniform", "factor": "auto"}})
    data, grid = gaussian_volume(8, 0.5, (ox - 2, oy - 2, oz - 2))
    volume = Layer("volume", id="vol", geometry={"grid": grid, "data": data, "encoding": "auto", "field": "rho",
                                                 "unit": "unspecified", "categorical": False},
                   appearance={"colormap": "cividis", "range": [None, None], "opacity": [[0, 0], [1, 1]]})
    overlays = [Layer("overlay", id="bar", props={"kind": "scalar_bar", "colormap": "turbo", "range": [-1, 1],
                                                  "unit": "m", "title": "x"}),
                Layer("overlay", id="legend", props={"kind": "legend", "entries": tri.attributes["label"].entries(),
                                                     "palette": "stk:categorical", "values": [1, 2]}),
                Layer("overlay", id="sphere", props={"kind": "orientation_legend"}),
                Layer("overlay", id="text", props={"kind": "text", "text": "mixed"}),
                Layer("overlay", id="triad", props={"kind": "axes_triad"})]
    return _scene([tri, image, lines, points, arrows, volume, *overlays], render_origin=list(origin))


def grid_mesh(n, origin=(0.0, 0.0, 0.0)):
    """An n x n planar triangle grid with a continuous 'z' attribute: ``(points, triangles)``."""
    j, i = np.meshgrid(np.arange(n), np.arange(n), indexing="ij")
    points = np.stack([i.reshape(-1), j.reshape(-1), np.sin(i.reshape(-1) / 5.0)], axis=1).astype(np.float64)
    points += np.asarray(origin)
    a = (j[:-1, :-1] * n + i[:-1, :-1]).reshape(-1)
    triangles = np.concatenate([np.stack([a, a + 1, a + n + 1], axis=1), np.stack([a, a + n + 1, a + n], axis=1)])
    return points, triangles
