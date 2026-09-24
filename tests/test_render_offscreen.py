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

from render_scenes import domains_scene, glyph_scene, iso_scene, mixed_scene, volume_scene  # noqa: E402
from suan.render import offscreen  # noqa: E402
from suan.render.colormaps import lut_rgba8, rgba8  # noqa: E402
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
