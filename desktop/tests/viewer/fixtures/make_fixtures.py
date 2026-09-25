"""Fixtures of the stk_viewer_gpu tests (desktop/tests/viewer).

Run from the repository root with the repo's Python environment (NumPy, the graph evaluator)::

    PYTHONPATH=. python desktop/tests/viewer/fixtures/make_fixtures.py [--vtk]

Writes next to this file:

* ``muferro_domains/`` (directory form) and ``muferro_domains.stkp``: the ``view`` output of the
  ``muferro-domains`` preset evaluated by the Python graph evaluator on a fake muFerro run
  (``tests/mupro_fake.write_domain_run``, 16 x 12 x 10 grid, 2 steps; the latest step).
* ``layers.stkp``: a coverage payload far from the origin (render_origin ~1e6) with every layer type
  the viewer draws: smooth continuous triangles (u16 indices, below/above/NaN values), flat
  categorical triangles with mixed labels, continuous and categorical slice images, polylines with a
  per-segment attribute, point sprites, sphere impostors with radii, cone/sphere/cube/line glyphs, a u16
  volume, a categorical u8 label volume and overlays (horizontal scalar bar, two-column legend, CJK text).
* ``vtk/muferro_domains.png`` and ``vtk/muferro_domains_nooverlays.png`` (``--vtk``): the offscreen
  VTK reference renders (800 x 600) used by the cross-check test. They need a render interpreter with
  VTK (``STK_RENDER_PYTHON``, e.g. Kitware's vtk-osmesa wheel with ``VTK_DEFAULT_OPENGL_WINDOW=
  vtkOSOpenGLRenderWindow``).
"""
import argparse
import json
import math
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from suan.render.payload import PayloadBuilder, decode  # noqa: E402

VTK_SIZE = (800, 600)


# ---------------------------------------------------------------------------------------------
# muferro-domains


def muferro_domains(out: Path):
    from mupro_fake import write_domain_run
    from suan.graph import catalog
    from suan.graph.resolve import LocalDirResolver
    from suan.graph.service import MemoryBlobSink, evaluate_request

    with tempfile.TemporaryDirectory(prefix="stk-viewer-fixture-") as tmp:
        run = Path(tmp) / "run"
        write_domain_run(run, grid=(16, 12, 10), steps=2, interval=1)
        sink = MemoryBlobSink()
        result = evaluate_request({"preset": "muferro-domains", "outputs": ["view"], "parameters": {}},
                                  resolver=LocalDirResolver({"run": run}), cache_dir=Path(tmp) / "cache",
                                  blob_sink=sink, registry=catalog.build_registry(entry_points=False))
        payload = decode(result["outputs"]["view"]["manifest"], sink.blobs)
    # Drop volatile provenance so regenerating gives the same bytes.
    manifest = json.loads(json.dumps(payload.manifest))
    manifest.get("source", {}).pop("generated_at", None)
    payload = type(payload)(manifest, payload.blobs)
    payload.validate()
    target = out / "muferro_domains"
    shutil.rmtree(target, ignore_errors=True)
    payload.write_directory(target)
    payload.write_stkp(out / "muferro_domains.stkp")
    return payload


# ---------------------------------------------------------------------------------------------
# Coverage payload


def grid_mesh(nx, ny, size, z_of):
    xs = np.linspace(-size / 2, size / 2, nx)
    ys = np.linspace(-size / 2, size / 2, ny)
    X, Y = np.meshgrid(xs, ys, indexing="xy")
    Z = z_of(X, Y)
    positions = np.stack([X.ravel(), Y.ravel(), Z.ravel()], axis=1)
    tris = []
    for j in range(ny - 1):
        for i in range(nx - 1):
            a, b, c, d = j * nx + i, j * nx + i + 1, (j + 1) * nx + i + 1, (j + 1) * nx + i
            tris += [(a, b, c), (a, c, d)]
    return positions, np.asarray(tris, dtype=np.int64)


def layers_payload():
    origin = [1.0e6 + 0.25, -2.0e6 + 0.5, 5.0e5 + 0.125]
    b = PayloadBuilder(render_origin=origin, length_unit="nm")
    viridis = b.add_lut("viridis", below_color=[1.0, 0.0, 1.0, 1.0], above_color=[1.0, 1.0, 1.0, 1.0],
                        nan_color=[0.0, 0.0, 0.0, 1.0])
    coolwarm = b.add_lut("coolwarm")
    palette = b.add_palette("fixture-labels", [
        {"value": 1, "name": "A 甲", "color": [0.85, 0.1, 0.1]},
        {"value": 2, "name": "B 乙", "color": [0.1, 0.6, 0.2]},
        {"value": 3, "name": "C 丙", "color": [0.15, 0.3, 0.9]},
    ], unknown_color=[0.5, 0.5, 0.5])

    # Smooth continuous surface (u16 indices; values below / above the range and NaN).
    pos, tris = grid_mesh(24, 24, 6.0, lambda x, y: 0.6 * np.sin(x) * np.cos(y))
    pos = pos + [-4.0, -4.0, 0.0]
    height = pos[:, 2].copy()
    height[5] = np.nan
    b.add_accessor("surf_pos", pos, "f32", 3)
    b.add_accessor("surf_idx", tris.ravel(), "u16", 1)
    b.add_accessor("surf_h", height, "f32", 1, hints=False)
    b.add_layer({"id": "surf", "type": "triangles", "name": "Surface", "positions": "surf_pos", "indices": "surf_idx",
                 "attributes": {"height": {"accessor": "surf_h", "association": "point", "range": [-0.45, 0.45]}},
                 "appearance": {"color": {"by": "attribute", "attribute": "height", "colormap": viridis},
                                "shading": "smooth", "lighting": True}})

    # Flat categorical triangles with mixed point labels (one exact colour per triangle).
    pos2, tris2 = grid_mesh(6, 6, 3.0, lambda x, y: 0.0 * x)
    pos2 = pos2 + [4.0, -4.0, 0.0]
    labels = (np.arange(len(pos2)) % 4).astype(np.int16)  # 0 has no entry: unknown colour
    b.add_accessor("cat_pos", pos2, "f32", 3)
    b.add_accessor("cat_idx", tris2.ravel(), "u32", 1)
    b.add_accessor("cat_lab", labels, "i16", 1)
    b.add_layer({"id": "cats", "type": "triangles", "name": "Labels", "positions": "cat_pos", "indices": "cat_idx",
                 "attributes": {"label": {"accessor": "cat_lab", "association": "point", "categorical": True,
                                          "palette": palette}},
                 "appearance": {"color": {"by": "attribute", "attribute": "label", "colormap": palette},
                                "shading": "flat", "edges": {"visible": True, "color": [0.1, 0.1, 0.1],
                                                             "width_px": 1.5}}})

    # Slice images: continuous (linear) and categorical (nearest).
    w, h = 16, 12
    ii, jj = np.meshgrid(np.arange(w), np.arange(h), indexing="xy")
    b.add_accessor("slice_v", (np.sin(ii / 3.0) * np.cos(jj / 2.5)).ravel(), "f32", 1)
    b.add_layer({"id": "slice", "type": "slice_image", "name": "Slice", "size": [w, h],
                 "plane": {"origin": [-7.0, 1.0, -1.0], "u": [5.0, 0.0, 0.0], "v": [0.0, 3.75, 0.0]},
                 "attributes": {"v": {"accessor": "slice_v", "association": "point"}},
                 "appearance": {"color": {"by": "attribute", "attribute": "v", "colormap": coolwarm,
                                          "range": [-1.0, 1.0]}}})
    lw, lh = 8, 6
    b.add_accessor("slice_lab", ((np.arange(lw * lh) // 3) % 4).astype(np.int32), "i32", 1)
    b.add_layer({"id": "labels", "type": "slice_image", "name": "Label slice", "size": [lw, lh],
                 "plane": {"origin": [-1.0, 1.5, -1.0], "u": [3.5, 0.0, 0.0], "v": [0.0, 2.5, 0.0]},
                 "attributes": {"label": {"accessor": "slice_lab", "association": "point", "categorical": True,
                                          "palette": palette}},
                 "appearance": {"color": {"by": "attribute", "attribute": "label", "colormap": palette,
                                          "interpolate": "nearest"}}})

    # Polylines with one value per segment (cell attribute), 3 px wide.
    t = np.linspace(0, 2 * math.pi, 40)
    helix1 = np.stack([4.0 + 1.2 * np.cos(t), 2.5 + 1.2 * np.sin(t), -1.0 + t / 3.0], axis=1)
    helix2 = np.stack([4.0 + 0.6 * np.cos(t), 2.5 + 0.6 * np.sin(t), -1.0 + t / 4.0], axis=1)
    b.add_accessor("poly_pos", np.concatenate([helix1, helix2]), "f32", 3)
    b.add_accessor("poly_idx", np.arange(80), "u32", 1)
    b.add_accessor("poly_off", np.array([0, 40, 80]), "u32", 1)
    b.add_accessor("poly_val", np.concatenate([np.linspace(0.0, 0.5, 39), np.linspace(0.6, 1.0, 39)]), "f32", 1)
    b.add_layer({"id": "poly", "type": "lines", "name": "Helices", "positions": "poly_pos", "mode": "polylines",
                 "indices": "poly_idx", "offsets": "poly_off",
                 "attributes": {"v": {"accessor": "poly_val", "association": "cell", "range": [0.0, 1.0]}},
                 "appearance": {"color": {"by": "attribute", "attribute": "v", "colormap": viridis},
                                "width_px": 3.0}})

    # Point sprites and sphere impostors.
    rng = np.random.default_rng(3)
    pts = rng.uniform([-7.5, 5.5, -1.0], [-3.5, 8.5, 1.0], size=(30, 3))
    b.add_accessor("pts_pos", pts, "f32", 3)
    b.add_accessor("pts_val", pts[:, 2], "f32", 1)
    b.add_layer({"id": "pts", "type": "points", "name": "Sprites", "positions": "pts_pos",
                 "attributes": {"z": {"accessor": "pts_val", "association": "point", "range": [-1.0, 1.0]}},
                 "appearance": {"color": {"by": "attribute", "attribute": "z", "colormap": viridis},
                                "render_as": "points", "size_px": 8}})
    balls = np.array([[x, y, 0.0] for x in (-1.5, 0.0, 1.5) for y in (6.0, 7.5)], dtype=float)
    b.add_accessor("ball_pos", balls, "f32", 3)
    b.add_accessor("ball_r", np.array([0.3, 0.4, 0.5, 0.6, 0.35, 0.45]), "f32", 1)
    b.add_layer({"id": "balls", "type": "points", "name": "Spheres", "positions": "ball_pos", "radii": "ball_r",
                 "appearance": {"color": {"by": "solid", "solid": [0.9, 0.55, 0.1]}, "render_as": "spheres"}})

    # Glyphs of every shape.
    for k, shape in enumerate(("cone", "sphere", "cube", "line")):
        n = 6
        gp = np.array([[3.0 + 0.8 * i, 5.5 + 0.9 * k, 0.0] for i in range(n)], dtype=float)
        ang = np.linspace(0, math.pi, n)
        gd = np.stack([np.cos(ang), np.sin(ang), 0.3 * np.ones(n)], axis=1) * (0.5 + 0.1 * np.arange(n))[:, None]
        b.add_accessor(f"g{k}_pos", gp, "f32", 3)
        b.add_accessor(f"g{k}_dir", gd, "f32", 3)
        b.add_layer({"id": f"glyph_{shape}", "type": "instances", "name": shape, "positions": f"g{k}_pos",
                     "directions": f"g{k}_dir", "glyph": {"shape": shape, "resolution": 12, "center": True},
                     "appearance": {"color": {"by": "direction", "colormap": "stk:orientation-hsl",
                                              "max_magnitude": 1.2},
                                    "scale": {"by": "magnitude", "factor": 0.8}}})

    # A u16 volume (Gaussian blob) with a viridis transfer function.
    n = 12
    g = np.linspace(-1, 1, n)
    X, Y, Z = np.meshgrid(g, g, g, indexing="ij")
    blob = np.exp(-3.0 * (X ** 2 + Y ** 2 + Z ** 2))
    stored = np.round(blob * 60000).astype(np.uint16).transpose(2, 1, 0).ravel()  # x fastest
    b.add_accessor("vol", stored, "u16", 1)
    b.add_layer({"id": "vol", "type": "volume", "name": "Blob",
                 "grid": {"dimensions": [n, n, n], "origin": [5.0, -8.5, -1.5], "spacing": [0.25, 0.25, 0.25]},
                 "data": "vol", "value_scale": 1.0 / 60000, "value_offset": 0.0, "value_range": [0.0, 1.0],
                 "transfer_function": {"colormap": viridis, "range": [0.0, 1.0],
                                       "opacity": [[0.0, 0.0], [0.3, 0.05], [1.0, 0.7]]},
                 "sampling": "linear"})

    # A categorical u8 label volume (odd dimensions, nearest sampling, one opacity for every label).
    lab = (np.arange(5 * 4 * 3) % 4).astype(np.uint8)  # x fastest; label 0 has no palette entry
    b.add_accessor("labvol", lab, "u8", 1)
    b.add_layer({"id": "labvol", "type": "volume", "name": "Label volume",
                 "grid": {"dimensions": [5, 4, 3], "origin": [0.0, -8.5, -1.0], "spacing": [0.6, 0.6, 0.6]},
                 "data": "labvol", "value_range": [0.0, 3.0],
                 "transfer_function": {"colormap": palette, "range": [0.0, 3.0],
                                       "opacity": [[0.0, 0.8], [3.0, 0.8]]},
                 "sampling": "nearest"})

    # Overlays.
    b.add_layer({"id": "bar", "type": "overlay", "kind": "scalar_bar", "colormap": viridis, "range": [-0.45, 0.45],
                 "title": "高度 height", "unit": "nm", "orientation": "horizontal", "label_count": 3,
                 "format": "+.2f", "anchor": "bottom", "offset_px": [0, 20], "size_px": [260, 16]})
    b.add_layer({"id": "legend", "type": "overlay", "kind": "legend", "colormap": palette, "values": [1, 2, 3, 0],
                 "title": "Labels 标签", "columns": 2, "anchor": "top_right"})
    b.add_layer({"id": "caption", "type": "overlay", "kind": "text", "text": "覆盖测试 coverage (render_origin ~1e6)",
                 "font_size_px": 16, "color": [0.1, 0.2, 0.5], "anchor": "top_left"})
    b.add_layer({"id": "triad", "type": "overlay", "kind": "axes_triad", "labels": ["x", "y", "z"],
                 "anchor": "bottom_left"})
    view = {"schema": "stk.view/1", "camera": {"preset": "iso", "projection": "perspective", "view_angle_deg": 30.0},
            "viewport": {"width": 800, "height": 600}, "background": {"type": "solid", "color": [0.96, 0.96, 0.96]},
            "lighting": {"preset": "three_point", "intensity": 1.0}}
    payload = b.build(view=view, source={"graph": "stk-viewer-coverage", "generator":
                                         "desktop/tests/viewer/fixtures/make_fixtures.py"})
    payload.validate()
    return payload


# ---------------------------------------------------------------------------------------------
# VTK references


def vtk_references(payload, out: Path):
    from suan.render.offscreen import probe, render_payload
    info = probe()
    if not info["ok"]:
        print(f"offscreen VTK unavailable: {info.get('error')}", file=sys.stderr)
        return False
    out.mkdir(exist_ok=True)
    width, height = VTK_SIZE
    (out / "muferro_domains.png").write_bytes(render_payload(payload, width=width, height=height))
    manifest = json.loads(json.dumps(payload.manifest))
    hidden = {layer["id"]: False for layer in manifest["layers"] if layer.get("type") == "overlay"}
    manifest.setdefault("view", {}).setdefault("visibility", {}).update(hidden)
    quiet = type(payload)(manifest, payload.blobs)
    (out / "muferro_domains_nooverlays.png").write_bytes(render_payload(quiet, width=width, height=height))
    (out / "README.txt").write_text(
        f"Offscreen VTK references ({width}x{height}) of ../muferro_domains.stkp, written by make_fixtures.py --vtk\n"
        f"(VTK {info.get('vtk')}, {info.get('window')}, {info.get('renderer')}).\n"
        "muferro_domains_nooverlays.png hides the overlay layers through view.visibility.\n", encoding="utf-8")
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--vtk", action="store_true", help="also write the offscreen VTK reference PNGs")
    args = parser.parse_args()
    domains = muferro_domains(HERE)
    layers_payload().write_stkp(HERE / "layers.stkp")
    if args.vtk and not vtk_references(domains, HERE / "vtk"):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
