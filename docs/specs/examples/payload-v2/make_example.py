"""Build the hand-made stk.payload/2 example (standard library + NumPy; deterministic).

Writes next to this file:
  manifest.json      directory form: buffers referenced as "sha256:<hex>", stored as <hex>.bin
  <hex>.bin          one file per buffer
  example.stkp       the same payload as a single .stkp file (buffers referenced as "#<k>")

Layers: a triangles layer (three cubes, categorical 'domain' + continuous 'height'),
an instances layer (arrows coloured by direction), an 8^3 u8 volume, a lines outline
and overlays (scalar bar, legend, orientation legend, axes triad, text).
Colours follow docs/specs/domain-classifiers.md; see docs/specs/stk-render-payload-v2.md.

    python docs/specs/examples/payload-v2/make_example.py
"""
from itertools import product
from pathlib import Path
import hashlib
import json
import math
import re
import struct

import numpy as np

HERE = Path(__file__).resolve().parent
RENDER_ORIGIN = [100.0, 50.0, 25.0]


# -- colours (docs/specs/domain-classifiers.md) ------------------------------

def hsl_to_rgb(h, s, l):
    c = (1 - abs(2 * l - 1)) * s
    hp = (h % 360.0) / 60.0
    x = c * (1 - abs(hp % 2 - 1))
    r1, g1, b1 = [(c, x, 0), (x, c, 0), (0, c, x), (0, x, c), (x, 0, c), (c, 0, x)][int(hp) % 6]
    m = l - c / 2
    return [r1 + m, g1 + m, b1 + m]


def orientation_rgb(p, max_magnitude, lightness_range=(0.0, 1.0)):
    l0, l1 = lightness_range
    px, py, pz = p
    m = math.sqrt(px * px + py * py + pz * pz)
    if max_magnitude <= 0 or m == 0:
        return hsl_to_rgb(0.0, 0.0, l0 + (l1 - l0) * 0.5)
    if math.hypot(px, py) < 1e-5 * max_magnitude:
        t = min(max((pz + max_magnitude) / (2 * max_magnitude), 0.0), 1.0)
        return hsl_to_rgb(0.0, 0.0, l0 + (l1 - l0) * t)
    h = math.degrees(math.atan2(py, px)) % 360.0
    s = min(m / max_magnitude, 1.0)
    return hsl_to_rgb(h, s, l0 + (l1 - l0) * (pz / m + 1) / 2)


def cubic26_stk():
    """STK numbering: families by number of nonzero components, each representative followed by its negation."""
    reps = [v for v in product((1, 0, -1), repeat=3) if any(v) and next(c for c in v if c) == 1]
    reps.sort(key=lambda v: sum(1 for c in v if c))
    return [d for v in reps for d in (v, tuple(-c for c in v))]


def miller(v):
    return "[" + "".join("0" if c == 0 else ("1" if c > 0 else "-1") for c in v) + "]"


def cubic26_palette():
    families = {1: "T", 2: "O", 3: "R"}
    entries = [{"value": -1, "name": "unclassified", "color": [1.0, 1.0, 1.0]},
               {"value": 0, "name": "substrate", "color": [0.75, 0.75, 0.75]}]
    for label, v in enumerate(cubic26_stk(), start=1):
        norm = math.sqrt(sum(c * c for c in v))
        d = [c / norm for c in v]
        family = families[sum(1 for c in v if c)]
        entries.append({"value": label, "name": family + miller(v), "family": family,
                        "direction": [round(c, 12) for c in d],
                        "color": [round(c, 6) for c in orientation_rgb(d, 1.0, (0.2, 0.8))]})
    return entries


VIRIDIS_9 = [(0.267004, 0.004874, 0.329415), (0.282623, 0.140926, 0.457517), (0.229739, 0.322361, 0.545706),
             (0.172719, 0.448791, 0.557885), (0.127568, 0.566949, 0.550556), (0.157851, 0.683765, 0.501686),
             (0.369214, 0.788888, 0.382914), (0.678489, 0.863742, 0.189503), (0.993248, 0.906157, 0.143936)]


def lut_viridis9():
    """256 RGBA8 entries, linear interpolation of 9 viridis stops (an example LUT, not the exact viridis)."""
    stops = np.array(VIRIDIS_9)
    x = np.linspace(0, 1, 256)
    grid = np.linspace(0, 1, len(stops))
    rgb = np.stack([np.interp(x, grid, stops[:, c]) for c in range(3)], axis=1)
    rgba = np.concatenate([rgb, np.ones((256, 1))], axis=1)
    return np.floor(rgba * 255 + 0.5).astype(np.uint8)


# -- geometry ------------------------------------------------------------------

def cube(center, half):
    """24 vertices (4 per face, flat normals) and 12 triangles, counter-clockwise from outside."""
    positions, normals, triangles = [], [], []
    for axis in range(3):
        for sign in (1, -1):
            normal = [0.0, 0.0, 0.0]
            normal[axis] = float(sign)
            u, v = [a for a in range(3) if a != axis]
            corners = []
            for du, dv in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
                p = [0.0, 0.0, 0.0]
                p[axis] = sign * half
                p[u], p[v] = du * half, dv * half
                corners.append([center[i] + p[i] for i in range(3)])
            # Orient so that (c1 - c0) x (c2 - c0) points along the normal.
            e1 = np.subtract(corners[1], corners[0])
            e2 = np.subtract(corners[2], corners[0])
            if np.dot(np.cross(e1, e2), normal) < 0:
                corners = corners[::-1]
            base = len(positions)
            positions.extend(corners)
            normals.extend([normal] * 4)
            triangles.extend([[base, base + 1, base + 2], [base, base + 2, base + 3]])
    return positions, normals, triangles


class Builder:
    def __init__(self):
        self.buffers = []    # (id, bytes)
        self.accessors = []
        self._current = None

    def begin(self, buffer_id):
        self._current = [buffer_id, bytearray()]

    def add(self, accessor_id, array, type_name, components):
        buffer_id, data = self._current
        while len(data) % 8:
            data.append(0)
        array = np.ascontiguousarray(array)
        self.accessors.append({"id": accessor_id, "buffer": buffer_id, "byteOffset": len(data),
                               "count": int(array.shape[0]), "type": type_name, "components": components})
        if array.dtype.kind in "fiu":
            flat = array.reshape(array.shape[0], -1)
            self.accessors[-1]["min"] = [v.item() for v in flat.min(axis=0)]
            self.accessors[-1]["max"] = [v.item() for v in flat.max(axis=0)]
        data.extend(array.astype(array.dtype.newbyteorder("<"), copy=False).tobytes())

    def end(self):
        buffer_id, data = self._current
        self.buffers.append((buffer_id, bytes(data)))
        self._current = None


def build():
    origin = np.array(RENDER_ORIGIN)
    b = Builder()

    # Triangles: three cubes labelled with STK cubic-26 labels 1 (T[100]), 7 (O[110]), 19 (R[111]).
    positions, normals, triangles, domain = [], [], [], []
    for label, center in ((1, (97.0, 50.0, 25.0)), (7, (100.0, 50.0, 25.0)), (19, (103.0, 50.0, 25.0))):
        p, n, t = cube(center, 1.0)
        base = len(positions)
        positions += p
        normals += n
        triangles += [[base + i for i in tri] for tri in t]
        domain += [label] * len(p)
    positions = np.array(positions) - origin
    height = positions[:, 2] + origin[2]
    b.begin("b_mesh")
    b.add("mesh_pos", positions.astype(np.float32), "f32", 3)
    b.add("mesh_nrm", np.array(normals, dtype=np.float32), "f32", 3)
    b.add("mesh_idx", np.array(triangles, dtype=np.uint32).reshape(-1), "u32", 1)
    b.add("mesh_domain", np.array(domain, dtype=np.int16), "i16", 1)
    b.add("mesh_height", height.astype(np.float32), "f32", 1)
    b.end()

    # Instances: a vortex of arrows on a 4x4x2 grid, stored in a seeded random order.
    points = np.array([(96.5 + 2 * i, 46.5 + 2 * j, 22.0 + 6 * k) for k in range(2) for j in range(4)
                       for i in range(4)])
    rel = points - np.array([100.0, 50.0, 25.0])
    vectors = np.stack([-rel[:, 1], rel[:, 0], 0.3 * rel[:, 2]], axis=1) * 0.25
    order = np.random.default_rng(7).permutation(len(points))
    points, vectors = points[order], vectors[order]
    magnitude = np.linalg.norm(vectors, axis=1)
    b.begin("b_glyph")
    b.add("gly_pos", (points - origin).astype(np.float32), "f32", 3)
    b.add("gly_dir", vectors.astype(np.float32), "f32", 3)
    b.add("gly_mag", magnitude.astype(np.float32), "f32", 1)
    b.end()

    # Volume: 8^3 points, a Gaussian blob, u8 with value = stored / 255.
    n = 8
    grid_origin = np.array([96.5, 46.5, 21.5])
    k, j, i = np.meshgrid(np.arange(n), np.arange(n), np.arange(n), indexing="ij")  # (z, y, x)
    xyz = np.stack([i, j, k], axis=-1) - (n - 1) / 2
    blob = np.exp(-(xyz ** 2).sum(axis=-1) / 6.0)
    stored = np.floor(blob * 255 + 0.5).astype(np.uint8)  # (z, y, x) -> x fastest when flattened
    b.begin("b_volume")
    b.add("vol_u8", stored.reshape(-1), "u8", 1)
    b.end()

    # Outline of the volume box (12 segments) and the colormap LUT.
    lo, hi = grid_origin, grid_origin + (n - 1)
    corners = np.array([[(lo, hi)[a][0], (lo, hi)[b_][1], (lo, hi)[c][2]]
                        for c in (0, 1) for b_ in (0, 1) for a in (0, 1)]) - origin
    edges = [(0, 1), (2, 3), (4, 5), (6, 7), (0, 2), (1, 3), (4, 6), (5, 7), (0, 4), (1, 5), (2, 6), (3, 7)]
    b.begin("b_misc")
    b.add("box_pos", corners.astype(np.float32), "f32", 3)
    b.add("box_idx", np.array(edges, dtype=np.uint32).reshape(-1), "u32", 1)
    b.add("lut_viridis9", lut_viridis9(), "u8", 4)
    b.end()

    max_mag = float(magnitude.max())
    palette = cubic26_palette()
    all_points = np.concatenate([positions, points - origin, corners])
    bounds = [[round(float(v), 6) for v in all_points.min(axis=0)], [round(float(v), 6) for v in all_points.max(axis=0)]]
    layers = [
        {"id": "domains", "type": "triangles", "node": "rep", "name": "Domains",
         "positions": "mesh_pos", "normals": "mesh_nrm", "indices": "mesh_idx",
         "attributes": {
             "domain": {"accessor": "mesh_domain", "association": "point", "categorical": True, "palette": "pal0",
                        "unit": "1", "quantity": "domain_variant"},
             "height": {"accessor": "mesh_height", "association": "point", "range": [24.0, 26.0],
                        "unit": "grid_index", "quantity": "length"}},
         "appearance": {"color": {"by": "attribute", "attribute": "domain", "colormap": "pal0",
                                  "interpolate": "nearest"},
                        "opacity": 1.0, "shading": "flat", "lighting": True},
         "pick": {"probe": {"node": "src", "dataset": "Polar"}}},
        {"id": "arrows", "type": "instances", "node": "gly", "name": "Polarization",
         "positions": "gly_pos", "directions": "gly_dir",
         "attributes": {"magnitude": {"accessor": "gly_mag", "range": [0.0, round(max_mag, 6)], "unit": "unspecified",
                                      "quantity": "polarization"}},
         "glyph": {"shape": "arrow", "resolution": 8, "center": True},
         "appearance": {"color": {"by": "direction", "colormap": "stk:orientation-hsl",
                                  "max_magnitude": round(max_mag, 6), "lightness_range": [0.0, 1.0]},
                        "scale": {"by": "magnitude", "factor": round(1.6 / max_mag, 6)}, "opacity": 1.0},
         "progressive": {"shuffled": True, "seed": 7}},
        {"id": "density", "type": "volume", "node": "vol", "name": "Density",
         "grid": {"dimensions": [n, n, n], "origin": [float(v) for v in grid_origin - origin],
                  "spacing": [1.0, 1.0, 1.0], "direction": [1, 0, 0, 0, 1, 0, 0, 0, 1]},
         "data": "vol_u8", "value_scale": 1 / 255, "value_offset": 0.0, "value_range": [0.0, 1.0],
         "unit": "unspecified", "quantity": "electron_density",
         "transfer_function": {"colormap": "cm0", "range": [0.0, 1.0],
                               "opacity": [[0.0, 0.0], [0.2, 0.0], [1.0, 0.6]]},
         "sampling": "linear", "shade": False},
        {"id": "box", "type": "lines", "node": "box", "name": "Outline", "positions": "box_pos",
         "mode": "segments", "indices": "box_idx",
         "appearance": {"color": {"by": "solid", "solid": [0.0, 0.0, 0.0]}, "width_px": 1.0}},
        {"id": "density_bar", "type": "overlay", "kind": "scalar_bar", "node": "bar", "source_layer": "density",
         "colormap": "cm0", "range": [0.0, 1.0], "title": "Density", "unit": "unspecified",
         "orientation": "vertical", "label_count": 5, "format": ".2f", "anchor": "right",
         "offset_px": [24, 24], "size_px": [28, 320]},
        {"id": "domain_legend", "type": "overlay", "kind": "legend", "node": "leg", "source_layer": "domains",
         "colormap": "pal0", "values": [1, 7, 19], "title": "Domain variant", "columns": 1, "anchor": "top_right"},
        {"id": "sphere", "type": "overlay", "kind": "orientation_legend", "node": "ori",
         "colormap": "stk:orientation-hsl", "lightness_range": [0.0, 1.0], "title": "Orientation",
         "anchor": "bottom_right", "size_px": [120, 120]},
        {"id": "triad", "type": "overlay", "kind": "axes_triad", "node": "axes", "labels": ["x", "y", "z"],
         "anchor": "bottom_left", "size_px": [80, 80]},
        {"id": "caption", "type": "overlay", "kind": "text", "text": "stk.payload/2 example (step 1000)",
         "font_size_px": 14, "color": [0.1, 0.1, 0.1], "anchor": "top_left", "offset_px": [12, 12]},
    ]
    graph_hash = "sha256:" + hashlib.sha256(b"docs/specs/examples/payload-v2 example graph").hexdigest()
    manifest = {
        "schema": "stk.payload/2",
        "source": {"graph": "payload-v2-example", "graph_hash": graph_hash, "view": "main",
                   "time": {"step": 1000, "time": None}, "profile": "web", "reduced": False,
                   "generator": "docs/specs/examples/payload-v2/make_example.py"},
        "render_origin": RENDER_ORIGIN,
        "length_unit": "grid_index",
        "bounds": bounds,
        "buffers": [],
        "accessors": b.accessors,
        "colormaps": [
            {"id": "cm0", "name": "viridis-9stop", "categorical": False, "lut": "lut_viridis9", "size": 256,
             "nan_color": [1.0, 0.0, 1.0, 1.0]},
            {"id": "pal0", "name": "stk:cubic-26-orientation", "categorical": True, "entries": palette,
             "unknown_color": [0.5, 0.5, 0.5]},
        ],
        "layers": layers,
        "view": {"schema": "stk.view/1",
                 "camera": {"projection": "perspective", "frame": "grid", "position": [118.0, 32.0, 43.0],
                            "focal_point": [100.0, 50.0, 25.0], "view_up": [0.0, 0.0, 1.0], "view_angle_deg": 30.0,
                            "preset": "iso"},
                 "viewport": {"width": 1600, "height": 1200, "magnification": 1, "lock_aspect": True},
                 "background": {"type": "solid", "color": [1.0, 1.0, 1.0]},
                 "lighting": {"preset": "three_point", "intensity": 1.0},
                 "visibility": {"caption": True}},
        "stats": {"triangles": len(triangles), "instances": len(points), "points": 0, "line_segments": len(edges),
                  "voxels": n ** 3, "texels": 0, "bytes": 0},
    }
    blobs = []
    for buffer_id, data in b.buffers:
        digest = hashlib.sha256(data).hexdigest()
        manifest["buffers"].append({"id": buffer_id, "uri": "sha256:" + digest, "sha256": digest,
                                    "byteLength": len(data), "encoding": "raw"})
        blobs.append((digest, data))
    manifest["stats"]["bytes"] = sum(len(data) for _, data in blobs)
    return manifest, blobs


def pack_stkp(manifest, blobs):
    """.stkp: 'STKP', u32 version 2, u64 total length; chunks [u64 length][4-byte type][u32 0][data, padded to 8]."""
    packed = json.loads(json.dumps(manifest))
    for index, buffer in enumerate(packed["buffers"], start=1):
        buffer["uri"] = f"#{index}"
    chunks = [(b"JSON", json.dumps(packed, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))]
    chunks += [(b"BIN ", data) for _, data in blobs]
    body = bytearray()
    for kind, data in chunks:
        body += struct.pack("<Q4sI", len(data), kind, 0) + data
        body += (b" " if kind == b"JSON" else b"\0") * (-len(data) % 8)
    return b"STKP" + struct.pack("<IQ", 2, 16 + len(body)) + bytes(body)


def dumps(value):
    """Indented JSON with arrays of scalars kept on one line."""
    text = json.dumps(value, indent=1, ensure_ascii=False)
    return re.sub(r"\[\s*([^\[\]{}]*?)\s*\]", lambda m: "[" + ", ".join(p.strip() for p in m.group(1).split(",")) + "]"
                  if m.group(1).strip() else "[]", text) + "\n"


def main():
    manifest, blobs = build()
    for old in HERE.glob("*.bin"):
        old.unlink()
    for digest, data in blobs:
        (HERE / f"{digest}.bin").write_bytes(data)
    (HERE / "manifest.json").write_text(dumps(manifest), encoding="utf-8")
    (HERE / "example.stkp").write_bytes(pack_stkp(manifest, blobs))


if __name__ == "__main__":
    main()
