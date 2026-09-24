"""Offscreen VTK rendering of payloads, always in a child process.

Tests marked ``render`` need a working offscreen OpenGL context in the render
interpreter (``$STK_RENDER_PYTHON`` or this interpreter); they skip with the
probe's reason otherwise. Goldens live in ``tests/golden`` and are compared
after 4x4 block averaging (RMS on 0..255) plus exact colours that must appear
(legend swatches, scalar bars and unlit faces). Regenerate them with
``STK_UPDATE_GOLDEN=1``.
"""
import copy
import json
import math
import os
from pathlib import Path
import subprocess
import sys

import pytest

np = pytest.importorskip("numpy")

from render_scenes import (domains_scene, gaussian_volume, glyph_scene, iso_scene, mixed_scene,  # noqa: E402
                           volume_scene)
from suan.render import offscreen  # noqa: E402
from suan.render.colormaps import lut_rgba8, rgba8  # noqa: E402
from suan.render.layers import Layer, Scene  # noqa: E402
from suan.render.payload import Payload, encode_scene, read_directory  # noqa: E402
from suan.render.png import decode_png, png_size  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = Path(__file__).resolve().parent / "golden"
UPDATE = os.environ.get("STK_UPDATE_GOLDEN") == "1"
RMS_LIMIT = 10.0


@pytest.fixture(scope="module")
def renderer():
    info = offscreen.probe()
    if not info["ok"]:
        pytest.skip(f"offscreen rendering unavailable in {info['python']}: {info['error']}. {info['hint']}")
    return info


def _blocks(image, size=4):
    h, w = (image.shape[0] // size) * size, (image.shape[1] // size) * size
    return image[:h, :w].reshape(h // size, size, w // size, size, -1).mean(axis=(1, 3))


def _golden(name, png):
    image = decode_png(png)
    path = GOLDEN / f"{name}.png"
    if UPDATE:
        GOLDEN.mkdir(exist_ok=True)
        path.write_bytes(png)
        return image
    if not path.exists():
        pytest.fail(f"missing golden {path.name}; regenerate with STK_UPDATE_GOLDEN=1")
    golden = decode_png(path.read_bytes())
    assert image.shape == golden.shape, f"{name}: size {image.shape} differs from the golden {golden.shape}"
    rms = math.sqrt(float(((_blocks(image[..., :3].astype(float)) - _blocks(golden[..., :3].astype(float))) ** 2)
                          .mean()))
    assert rms < RMS_LIMIT, f"{name}: RMS {rms:.2f} vs golden (limit {RMS_LIMIT}); STK_UPDATE_GOLDEN=1 regenerates"
    return image


def _count(image, rgb, tolerance=2):
    return int((np.abs(image[..., :3].astype(int) - np.asarray(rgb)[None, None, :]).max(axis=-1) <= tolerance).sum())


def _lut_pixels(image, lut):
    """Pixels whose colour is exactly one of the LUT entries (the 2D scalar bar is unlit)."""
    codes = image[..., 0].astype(np.int64) * 65536 + image[..., 1].astype(np.int64) * 256 + image[..., 2]
    entries = lut[:, 0].astype(np.int64) * 65536 + lut[:, 1].astype(np.int64) * 256 + lut[:, 2]
    return int(np.isin(codes, entries).sum())


# -- no GL needed -------------------------------------------------------------------------------


def test_missing_render_interpreter_gives_an_actionable_error(tmp_path):
    missing = str(tmp_path / "no-python")
    info = offscreen.probe(python=missing)
    assert info["ok"] is False and "cannot start" in info["error"]
    assert "vtk-osmesa" in info["hint"] and "libegl1" in info["hint"] and "STK_RENDER_PYTHON" in info["hint"]
    assert offscreen.probe(python=missing) == info                       # cached
    with pytest.raises(offscreen.OffscreenUnavailable) as error:
        offscreen.render_payload(read_directory(ROOT / "docs/specs/examples/payload-v2"), python=missing)
    assert "vtk-osmesa" in error.value.hint and error.value.probe["ok"] is False


def test_child_reports_invalid_payloads_as_errors(tmp_path):
    bad = tmp_path / "bad.stkp"
    bad.write_bytes(b"STKP" + b"\0" * 12)
    with pytest.raises(offscreen.OffscreenError, match="PayloadError"):
        offscreen.render_payload(bad, check=False, timeout=60)
    with pytest.raises(ValueError, match="magnification"):
        offscreen.render_payload(bad, check=False, magnification=9)


@pytest.mark.parametrize("name", ["domains", "payload-example"])
def test_png_decoder_without_pillow_matches_pillow(monkeypatch, name):
    data = (GOLDEN / f"{name}.png").read_bytes()
    pytest.importorskip("PIL")
    fast = decode_png(data)
    monkeypatch.setitem(sys.modules, "PIL", None)          # force the pure-Python path
    slow = decode_png(data)
    assert fast.shape == slow.shape == (*png_size(data)[::-1], 3) and (fast == slow).all()


def test_transient_probe_failures_are_not_cached(tmp_path):
    # A child killed from outside (here: SIGKILL on the first start) says nothing about the GL stack.
    marker = tmp_path / "first"
    flaky = tmp_path / "flaky-python"
    flaky.write_text(f"#!/bin/sh\nif [ ! -e {marker} ]; then touch {marker}; kill -9 $$; fi\n"
                     f"exec {sys.executable} -c "
                     "'import json; print(json.dumps({\"ok\": False, \"error\": \"no GL\"}))'\n")
    flaky.chmod(0o755)
    if sys.platform.startswith("win"):
        pytest.skip("POSIX shell script")
    first = offscreen.probe(python=str(flaky))
    assert first["ok"] is False and "signal 9" in first["error"]
    second = offscreen.probe(python=str(flaky))  # probed again: the child now answers (a definitive failure)
    assert second["ok"] is False and second["error"] == "no GL"
    marker.unlink()
    assert offscreen.probe(python=str(flaky)) == second  # definitive failures stay cached
    assert "signal 9" in offscreen.probe(python=str(flaky), refresh=True)["error"]


def test_children_run_in_an_empty_directory_and_poll_can_stop_them(tmp_path, monkeypatch):
    # Stray modules in the parent's working directory (vtk.py, json.py, ...) are never imported by the child.
    for name in ("vtk", "json"):
        (tmp_path / f"{name}.py").write_text(f"raise SystemExit('shadowed {name} imported from the cwd')\n")
    monkeypatch.chdir(tmp_path)
    result, error, stderr = offscreen._run(sys.executable, ["--help"], 60)
    assert error is None and "shadowed" not in stderr
    # poll() runs while the child works; what it raises kills the child and propagates at once.
    slow = tmp_path / "slow-python"
    slow.write_text("#!/bin/sh\nexec sleep 30\n")
    slow.chmod(0o755)
    if sys.platform.startswith("win"):
        pytest.skip("POSIX shell script")
    calls = []

    def poll():
        calls.append(1)
        if len(calls) >= 3:
            raise KeyboardInterrupt("cancelled")
    started = __import__("time").monotonic()
    with pytest.raises(KeyboardInterrupt):
        offscreen._run(str(slow), [], 60, poll=poll)
    assert __import__("time").monotonic() - started < 5 and len(calls) == 3
    outcome = offscreen._run(str(slow), [], 0.3)
    assert "timed out" in outcome[1] and outcome.transient


def test_parent_side_never_imports_vtk():
    code = ("import sys; import suan.render.offscreen, suan.render.payload, suan.render.v1, suan.render.layers; "
            "print(json.dumps(sorted(m for m in ('vtk', 'vtkmodules') if m in sys.modules)))")
    output = subprocess.run([sys.executable, "-c", "import json; " + code], capture_output=True, text=True,
                            check=True, env={**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)}).stdout
    assert json.loads(output.strip().splitlines()[-1]) == []


# -- goldens (render marker) ---------------------------------------------------------------------


@pytest.mark.render
def test_domains_golden_with_categorical_legend(renderer):
    scene = domains_scene()
    png = offscreen.render_scene(scene)
    assert png_size(png) == (320, 240)
    image = _golden("domains", png)
    entries = {e["value"]: e for e in scene.layer("domains").attributes["domain"].entries()}
    for value in (1, 7, 19):
        assert _count(image, rgba8(entries[value]["color"])[:3]) >= 100, f"label {value} colour missing"


@pytest.mark.render
def test_glyphs_golden_with_orientation_sphere(renderer):
    image = _golden("glyphs", offscreen.render_scene(glyph_scene()))
    rgb = image[..., :3].astype(float) / 255
    saturated = (rgb.max(axis=-1) - rgb.min(axis=-1)) > 0.5
    hues = set((np.degrees(np.arctan2(np.sqrt(3) * (rgb[..., 1] - rgb[..., 2]),
                                      2 * rgb[..., 0] - rgb[..., 1] - rgb[..., 2]))[saturated] // 60 % 6).astype(int))
    assert len(hues) >= 4, "the orientation colours (arrows and sphere) should span several hue sectors"


@pytest.mark.render
def test_volume_golden_with_scalar_bar(renderer):
    image = _golden("volume", offscreen.render_scene(volume_scene()))
    assert _lut_pixels(image, lut_rgba8("viridis")) >= 1000, "the scalar bar shows exact viridis LUT colours"


@pytest.mark.render
def test_isosurface_golden_with_scalar_bar(renderer):
    image = _golden("isosurface", offscreen.render_scene(iso_scene()))
    assert _lut_pixels(image, lut_rgba8("coolwarm")) >= 1000, "the scalar bar shows exact coolwarm LUT colours"


@pytest.mark.render
def test_spec_example_renders_every_layer_type(renderer):
    payload = read_directory(ROOT / "docs/specs/examples/payload-v2")
    image = _golden("payload-example", offscreen.render_payload(payload, width=480, height=360))
    assert _count(image, (255, 0, 0)) >= 20                              # T[100] legend swatch and cube


@pytest.mark.render
def test_volume_opacity_does_not_depend_on_the_absolute_spacing(renderer):
    # Opacity is per smallest voxel spacing (payload spec §6.6): nm, grid indices or metres look alike.
    images = []
    for spacing in (1.0, 0.01, 50.0):
        data, grid = gaussian_volume(n=24, spacing=spacing, origin=(0.0, 0.0, 0.0))
        layer = Layer("volume", id="v", geometry={"grid": grid, "data": data, "encoding": "f32", "field": "v",
                                                  "unit": "1", "quantity": None, "categorical": False},
                      appearance={"colormap": "viridis", "range": [0.0, 1.0], "opacity": [[0.0, 0.0], [1.0, 0.5]]})
        scene = Scene([layer], view={"schema": "stk.view/1", "camera": {"preset": "iso"},
                                     "viewport": {"width": 96, "height": 72}})
        images.append(decode_png(offscreen.render_scene(scene)).astype(float))
    darkness = [255 - image[..., :3].mean() for image in images]
    assert darkness[0] > 5, "the volume is visible"
    for image in images[1:]:
        assert np.abs(image - images[0]).max() <= 2


@pytest.mark.render
def test_overlay_text_is_drawn_literally(renderer):
    # VTK's MathText detection would draw the title |v| as v (and eat $...$); STK texts are plain text.
    def ink(text):
        scene = Scene([Layer("overlay", id="t", props={"kind": "text", "text": text, "font_size_px": 40,
                                                       "anchor": "top_left", "offset_px": [4, 4]})],
                      view={"schema": "stk.view/1", "viewport": {"width": 200, "height": 80}})
        image = decode_png(offscreen.render_scene(scene)).astype(int)
        return int((image[..., :3].min(axis=-1) < 128).sum())
    bars, plain = ink("|v|"), ink("v")
    assert bars > plain * 1.5, (bars, plain)
    assert ink("$x$") > ink("x") * 1.5
    assert offscreen._label(2.6, "d") == "3" and offscreen._label(0.25, ".0%") == "25%"


@pytest.mark.render
def test_image_node_cancellation_stops_the_render_child(renderer):
    import threading
    import time
    from suan.data.model import ImageData
    from suan.graph.nodes import output, render as render_nodes, view
    from suan.graph.registry import Budget, CancelToken, Cancelled
    from test_nodes_render import FakeContext, run_node
    n = 96
    x = np.linspace(-1, 1, n)
    image = ImageData((n, n, n), (0, 0, 0), (1, 1, 1))
    gaussian = np.exp(-(x[:, None, None] ** 2 + x[None, :, None] ** 2 + x[None, None, :] ** 2) * 4)
    image.add_field("phi", gaussian[..., None])
    layer, _ = run_node(render_nodes.volume, {"in": image}, {})
    scene, _ = run_node(view.scene, {"layers": [layer["layer"]]}, {})
    node_type = output.image_output.stk_node_type
    ctx = FakeContext(node_type, "img")
    ctx.cancel = CancelToken()
    threading.Timer(0.3, lambda: ctx.cancel.cancel("user cancelled")).start()
    started = time.monotonic()
    with pytest.raises(Cancelled):
        output.image_output(ctx, {"source": scene["scene"]}, node_type.normalize_params({"magnification": 4}))
    assert time.monotonic() - started < 5


@pytest.mark.render
def test_magnification_is_the_same_picture_with_more_pixels(renderer):
    payload = encode_scene(domains_scene(), profile="desktop")
    single = decode_png(offscreen.render_payload(payload))
    double = decode_png(offscreen.render_payload(payload, magnification=2))
    assert double.shape[:2] == (480, 640)
    rms = math.sqrt(float(((_blocks(double[..., :3].astype(float), 8)
                            - _blocks(single[..., :3].astype(float), 4)) ** 2).mean()))
    assert rms < 12.0


@pytest.mark.render
def test_transparent_background_and_explicit_size(renderer):
    payload = encode_scene(domains_scene(), profile="desktop")
    image = decode_png(offscreen.render_payload(payload, width=200, height=100, transparent=True))
    assert image.shape == (100, 200, 4)
    assert image[0, 0, 3] == 0 and image[50, 100, 3] == 255


@pytest.mark.render
def test_render_runs_in_a_child_process(renderer, tmp_path):
    out = tmp_path / "scene.png"
    code = ("import sys; from pathlib import Path; sys.path[:0] = [p for p in sys.argv[2:]]; "
            "from render_scenes import iso_scene; from suan.render.offscreen import render_scene; "
            "Path(sys.argv[1]).write_bytes(render_scene(iso_scene())); "
            "print('vtkmodules' in sys.modules)")
    result = subprocess.run([sys.executable, "-c", code, str(out), str(Path(__file__).parent), str(ROOT)],
                            capture_output=True, text=True, check=True)
    assert result.stdout.strip().splitlines()[-1] == "False"
    assert png_size(out.read_bytes()) == (320, 240)


@pytest.mark.render
def test_camera_presets_resolve_like_the_numeric_camera(renderer):
    numeric = encode_scene(iso_scene(), profile="desktop")
    manifest = copy.deepcopy(numeric["manifest"])
    manifest["view"]["camera"] = {"preset": "+x", "view_angle_deg": 30.0}
    first = decode_png(offscreen.render_payload(numeric)).astype(float)
    second = decode_png(offscreen.render_payload(Payload(manifest, numeric["buffers"]))).astype(float)
    assert math.sqrt(float(((first - second) ** 2).mean())) < 1.0


@pytest.mark.render
def test_every_layer_type_renders_far_from_the_origin(renderer):
    image = decode_png(offscreen.render_scene(mixed_scene()))
    assert image.shape == (240, 320, 3)
    drawn = (np.abs(image.astype(int) - 255).max(axis=-1) > 30).mean()
    assert 0.05 < drawn < 0.9
