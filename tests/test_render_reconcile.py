"""The reconciled stk.payload/2 rules shared by Python, the web viewer and the desktop decoder.

docs/specs/stk-render-payload-v2.md §2.1 (camera), §5, §6.5-§6.7, §9, §10 and "Changes". The web and C++
implementations are held to the same verdicts by desktop/tests/unit (fixtures/payload/cases.json and
web_vectors.json); these tests pin the Python reference itself.
"""
import copy
import json
import math
from pathlib import Path
import struct

import pytest

np = pytest.importorskip("numpy")

from suan.render import colormaps as cm  # noqa: E402
from suan.render.layers import camera_pose, default_view_up, view_preset  # noqa: E402
from suan.render.payload import (  # noqa: E402
    LABEL_FORMAT, PayloadError, decode, format_label, overlay_problems, read_directory, read_stkp,
)

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "docs" / "specs" / "examples" / "payload-v2"
LAYERS = {"domains": 0, "arrows": 1, "density": 2, "box": 3, "bar": 4, "legend": 5, "sphere": 6, "triad": 7,
          "caption": 8}


@pytest.fixture(scope="module")
def example():
    return read_directory(EXAMPLE)


def _decode(example, mutate):
    manifest = copy.deepcopy(example.manifest)
    mutate(manifest)
    return decode(manifest, example.blobs)


def _layer(manifest, name):
    return manifest["layers"][LAYERS[name]]


# -- §10 rejections the web decoder already had -------------------------------------------------------


@pytest.mark.parametrize("mutate, path", [
    (lambda m: m["colormaps"][1]["entries"][0].update(name=5), "/colormaps/1/entries/0/name"),
    (lambda m: m["colormaps"][1]["entries"][0].pop("name"), "/colormaps/1/entries/0/name"),
    (lambda m: _layer(m, "density")["grid"].update(direction=[1, 0, 0, 0, 1, 0, 0, 0, None]),
     "/layers/2/grid/direction"),
    (lambda m: _layer(m, "density").update(value_range=[0.0]), "/layers/2/value_range"),
    (lambda m: _layer(m, "density")["transfer_function"].update(opacity=[[0.0, 0.5]]),
     "/layers/2/transfer_function/opacity"),
    (lambda m: _layer(m, "arrows")["appearance"]["scale"].update(factor=0), "/layers/1/appearance/scale/factor"),
    (lambda m: _layer(m, "arrows")["appearance"]["scale"].update(factor=-2.0), "/layers/1/appearance/scale/factor"),
    (lambda m: _layer(m, "caption").update(id="__proto__"), "/layers/8/id"),
    (lambda m: _layer(m, "triad").update(id="constructor"), "/layers/7/id"),
    (lambda m: _layer(m, "sphere").update(id="prototype"), "/layers/6/id"),
    (lambda m: _layer(m, "caption").update(id="caption\n"), "/layers/8/id"),
    (lambda m: _layer(m, "bar").update(format=".2f\n"), "/layers/4/format"),
    (lambda m: _layer(m, "domains").update(name=5), "/layers/0/name"),
    (lambda m: _layer(m, "box").pop("type"), "/layers/3/type"),
    (lambda m: _layer(m, "caption").update(kind=5), "/layers/8/kind"),
    (lambda m: m["colormaps"][1]["entries"][0].update(color=[1.5, 0.0, 0.0]), "/colormaps/1/entries/0/color"),
    (lambda m: m["colormaps"][1].update(unknown_color=[2.0, 0.0, 0.0]), "/colormaps/1/unknown_color"),
    (lambda m: m["colormaps"][1].update(categorical=1), "/colormaps/1/categorical"),
    (lambda m: m["accessors"][3].update(normalized="yes"), "/accessors/3/normalized"),
    (lambda m: _layer(m, "arrows")["appearance"]["color"].update(colormap="cm0"),
     "/layers/1/appearance/color/colormap"),
    (lambda m: _layer(m, "domains")["appearance"]["color"].update(range=[0]), "/layers/0/appearance/color/range"),
    (lambda m: _layer(m, "box").update(appearance="red"), "/layers/3/appearance"),
    (lambda m: m["colormaps"][1]["entries"][0].update(value=2 ** 53), "/colormaps/1/entries/0/value"),
])
def test_rejections_shared_with_the_web_decoder(example, mutate, path):
    with pytest.raises(PayloadError) as error:
        _decode(example, mutate)
    assert error.value.path == path


# -- relaxations: defaults, nulls, integral numbers, skipped layers -------------------------------------


@pytest.mark.parametrize("mutate", [
    lambda m: _layer(m, "domains")["appearance"]["color"].pop("by"),        # color.by defaults to solid (§5)
    lambda m: _layer(m, "domains")["appearance"]["color"].update(by=None),
    lambda m: _layer(m, "domains").update(normals=None, origin=None, name=None),   # null counts as absent
    lambda m: m.update(view=None, bounds=None),
    lambda m: m["buffers"][0].update(encoding=None),
    lambda m: _layer(m, "density")["grid"].update(direction=None),
    lambda m: _layer(m, "bar").update(format=None, label_count=None),
    lambda m: _layer(m, "bar").update(label_count=5.0),                       # 5.0 is the integer 5
    lambda m: m["accessors"][0].update(count=float(m["accessors"][0]["count"])),
    lambda m: m["buffers"][0].update(byteLength=float(m["buffers"][0]["byteLength"])),
    lambda m: _layer(m, "arrows")["appearance"]["scale"].pop("factor"),       # factor defaults to 1
    lambda m: _layer(m, "caption").update(id="toString"),
])
def test_relaxed_rules_accept(example, mutate):
    payload = _decode(example, mutate)
    assert payload.warnings == []


def test_unknown_types_kinds_and_malformed_overlays_are_skipped_with_warnings(example):
    def mutate(m):
        _layer(m, "legend")["kind"] = "histogram"            # an unknown overlay kind (spec §1)
        _layer(m, "caption")["title"] = 5                    # a presentation member of a wrong type
        m["layers"].append({"id": "future", "type": "labels", "anything": 1})
    payload = _decode(example, mutate)
    assert [(w["path"], w["layer"]) for w in payload.warnings] == [
        ("/layers/5", "domain_legend"), ("/layers/8", "caption"), ("/layers/9", "future")]
    assert payload.skipped(payload.layer("caption")) and not payload.skipped(payload.layer("domains"))
    assert overlay_problems({"kind": "axes_triad", "labels": ["x"], "size_px": [-1, 2]}) == [
        "size_px must be a positive number or 2 positive numbers", "labels must be 3 strings"]
    assert read_directory(EXAMPLE).warnings == []


def test_polyline_cell_attributes_are_per_segment():
    from suan.render.payload import PayloadBuilder
    # [0, 4]: one polyline of 3 segments; [0, 3, 4]: 2 + 0 segments. One value per polyline is rejected.
    for offsets, cells, ok in (([0, 4], 3, True), ([0, 4], 1, False), ([0, 3, 4], 2, True), ([0, 2, 4], 1, False)):
        builder = PayloadBuilder()
        builder.add_accessor("pos", np.zeros((4, 3), dtype=np.float32))
        builder.add_accessor("idx", np.arange(4, dtype=np.uint32))
        builder.add_accessor("off", np.asarray(offsets, dtype=np.uint32))
        builder.add_accessor("c", np.arange(cells, dtype=np.float32))
        builder.add_layer({"id": "l", "type": "lines", "mode": "polylines", "positions": "pos", "indices": "idx",
                           "offsets": "off", "attributes": {"c": {"accessor": "c", "association": "cell"}}})
        if ok:
            builder.build().validate()
        else:
            with pytest.raises(PayloadError, match="expected"):
                builder.build().validate()


# -- .stkp framing and JSON parsing (§9) -----------------------------------------------------------------


def _stkp(text, chunks):
    body = bytearray()
    for kind, data in [(b"JSON", text)] + [(b"BIN ", c) for c in chunks]:
        body += struct.pack("<Q4sI", len(data), kind, 0) + data
        body += (b" " if kind == b"JSON" else b"\0") * (-len(data) % 8)
    return b"STKP" + struct.pack("<IQ", 2, 16 + len(body)) + bytes(body)


def test_stkp_json_is_strict(example):
    packed = json.loads(json.dumps(example.manifest))
    chunks = []
    for index, buffer in enumerate(packed["buffers"], start=1):
        buffer["uri"] = f"#{index}"
        chunks.append(example.blobs[buffer["sha256"]])
    text = json.dumps(packed, separators=(",", ":")).encode()
    assert read_stkp(_stkp(text, chunks))
    assert read_stkp(_stkp(text[:-1] + b',"x-big":123456789012345678901234567890}', chunks))
    for bad in (b"\xef\xbb\xbf" + text, text[:-1] + b',"x":NaN}', text[:-1] + b',"x":1e400}',
                text[:-1] + b',"x":1' + b"0" * 400 + b"}"):
        with pytest.raises(PayloadError, match="not valid JSON"):
            read_stkp(_stkp(bad, chunks))
    data = (EXAMPLE / "example.stkp").read_bytes()
    with pytest.raises(PayloadError, match="length field"):
        read_stkp(data + b"\0" * 8)          # the length field is exactly the file size


# -- colours (§5, §6.6) -----------------------------------------------------------------------------------


def test_non_integer_labels_are_grey_and_duplicate_opacity_values_keep_the_last_point():
    assert cm.stk_categorical_color(2.5) == (0.5, 0.5, 0.5)
    assert cm.stk_categorical_color(float("nan")) == (0.5, 0.5, 0.5)
    assert cm.stk_categorical_color(7.0) == cm.stk_categorical_color(7)
    points = [[0.0, 0.0], [0.5, 1.0], [0.5, 0.2], [1.0, 0.8]]
    assert cm.opacity_at([0.5, 0.75], points).tolist() == pytest.approx([0.2, 0.5])
    assert cm.opacity_at([0.5], [[0.5, 0.2], [0.5, 1.0], [0.0, 0.0]]).tolist() == [1.0]


def test_volume_colour_points_degenerate_ranges_and_quantized_palettes():
    lut = cm.lut_rgba8("viridis")
    entry = {"categorical": False}
    assert len(cm.volume_color_points(entry, lut, (0.0, 1.0))) == 256
    for degenerate in ((2.0, 2.0), (3.0, 1.0)):
        assert cm.volume_color_points(entry, lut, degenerate) == [[degenerate[0]] + [c / 255 for c in lut[128, :3]]]
    palette = {"categorical": True, "entries": [{"value": 3, "name": "a", "color": [0.3333, 0.6667, 0.001]}]}
    r, g, b = (c / 255 for c in cm.rgba8([0.3333, 0.6667, 0.001])[:3])
    assert cm.volume_color_points(palette, None, (0, 5)) == [[2.501, r, g, b], [3.499, r, g, b]]


# -- scalar-bar labels (§6.7) -----------------------------------------------------------------------------


@pytest.mark.parametrize("value, spec, text", [
    (0.125, ".2f", "0.12"), (0.375, ".2f", "0.38"), (2.5, "d", "2"), (3.5, "d", "4"), (-2.5, "d", "-2"),
    (-0.0, ".3g", "0"), (-0.0001, ".2f", "0.00"), (-0.0001, "08.2f", "00000.00"), (-0.0001, "+.2f", "+0.00"),
    (-0.4, "d", "0"), (-0.001, ".0%", "0%"), (-1e-300, ".3g", "-1e-300"), (-0.0, "", "0.0"),
    (float("inf"), "d", "inf"), (float("-inf"), "+05d", "-0inf"), (float("nan"), ".2f", "nan"),
    (1234.5, ",d", "1,234"), (1.0, "{}", "1"), (1.0, ".2f\n", "1"),
])
def test_label_format_rounds_half_to_even_and_never_prints_minus_zero(value, spec, text):
    assert format_label(value, spec) == text


def test_label_format_is_anchored_at_the_very_end():
    assert LABEL_FORMAT.match(".3g") and not LABEL_FORMAT.match(".3g\n") and not LABEL_FORMAT.fullmatch("999999")


# -- camera (§2.1) ----------------------------------------------------------------------------------------


def test_camera_follows_the_interactive_viewer():
    bounds = [[-1.0, -1.0, -1.0], [1.0, 1.0, 1.0]]
    # z-up unless the view direction is within 1e-6 of z
    assert default_view_up([0, 0.001, 10], [0, 0, 0]) == [0.0, 0.0, 1.0]
    assert default_view_up([0, 1e-7, 10], [0, 0, 0]) == [0.0, 1.0, 0.0]
    # an explicit view_up is honoured together with a preset
    pose = camera_pose({"schema": "stk.view/1", "camera": {"preset": "iso", "view_up": [0, 1, 0]}}, [0, 0, 0], bounds)
    assert pose["view_up"] == [0.0, 1.0, 0.0]
    # view angles >= 180 degrees become 30
    pose = camera_pose({"schema": "stk.view/1", "camera": {"preset": "+x", "view_angle_deg": 200}}, [0, 0, 0], bounds)
    assert pose["view_angle_deg"] == 30.0
    assert pose["position"] == pytest.approx([math.sqrt(3) / math.sin(math.radians(15)), 0, 0])
    # a numeric camera wins over a preset; its zoom narrows the angle only without a preset
    numeric = {"position": [10, 0, 0], "focal_point": [0, 0, 0], "zoom": 2}
    assert camera_pose({"schema": "stk.view/1", "camera": numeric}, [0, 0, 0], bounds)["view_angle_deg"] == 15.0
    assert camera_pose({"schema": "stk.view/1", "camera": {**numeric, "preset": "iso"}}, [0, 0, 0],
                       bounds)["view_angle_deg"] == 30.0
    assert view_preset({"schema": "stk.view/1", "camera": numeric}) is None
    assert view_preset({"schema": "stk.view/1", "camera": {"preset": "bogus"}}) == "bogus"
    assert camera_pose({"schema": "stk.view/1", "camera": {"preset": "bogus"}}, [0, 0, 0], bounds)["position"] == \
        camera_pose(None, [0, 0, 0], bounds)["position"]
