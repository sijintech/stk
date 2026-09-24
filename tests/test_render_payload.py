"""stk.payload/2: the spec example, the builder, the scene encoder, budgets, precision and .stkp I/O."""
import copy
import hashlib
import json
from pathlib import Path
import struct

import pytest

np = pytest.importorskip("numpy")

from render_scenes import domains_scene, glyph_scene, grid_mesh, mixed_scene, volume_scene  # noqa: E402
from suan.render.layers import Attribute, Layer, Scene  # noqa: E402
from suan.render.payload import (  # noqa: E402
    PROFILES, Payload, PayloadBuilder, PayloadError, budget_limits, cluster_decimate, decode, encode_scene,
    pack_stkp, read_directory, read_stkp, unpack_stkp,
)

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "docs" / "specs" / "examples" / "payload-v2"


def test_example_directory_and_stkp_decode_to_the_same_valid_payload():
    directory = read_directory(EXAMPLE)
    single = read_stkp(EXAMPLE / "example.stkp")
    assert directory.manifest == single.manifest == json.loads((EXAMPLE / "manifest.json").read_text("utf-8"))
    assert single.to_stkp() == directory.to_stkp() == (EXAMPLE / "example.stkp").read_bytes()
    assert set(directory.array("mesh_domain").tolist()) == {1, 7, 19}
    assert directory.array("mesh_pos").shape == (72, 3) and directory.array("mesh_idx").shape == (108,)
    assert directory.lut("cm0").shape == (256, 4)
    assert directory.layer("arrows")["type"] == "instances" and directory.colormap("pal0")["categorical"]
    assert decode(directory.manifest, directory.blobs).manifest is directory.manifest
    assert decode(directory.manifest, lambda sha: directory.blobs[sha]).nbytes == directory.nbytes == 5216


def test_builder_reproduces_the_example_exactly(tmp_path):
    example = read_directory(EXAMPLE)
    m = example.manifest
    builder = PayloadBuilder(m["render_origin"], m["length_unit"])
    for buffer in m["buffers"]:
        with builder.buffer(buffer["id"]):
            for accessor in m["accessors"]:
                if accessor["buffer"] == buffer["id"]:
                    builder.add_accessor(accessor["id"], example.array(accessor["id"]), accessor["type"],
                                         accessor["components"])
    for colormap in m["colormaps"]:
        builder.add_colormap(colormap)
    for layer in m["layers"]:
        builder.add_layer(layer)
    rebuilt = builder.build(source=m["source"], bounds=m["bounds"], view=m["view"], stats=dict(m["stats"]))
    assert rebuilt.manifest == m
    assert rebuilt.blobs == {sha: bytes(data) for sha, data in example.blobs.items()}
    assert rebuilt.to_stkp() == (EXAMPLE / "example.stkp").read_bytes()
    rebuilt.write_directory(tmp_path / "copy")
    assert sorted(p.name for p in (tmp_path / "copy").glob("*.bin")) == sorted(p.name for p in EXAMPLE.glob("*.bin"))
    assert read_directory(tmp_path / "copy").manifest == m


def _stkp_chunks(data):
    offset, chunks = 16, []
    while offset < len(data):
        length, kind, _ = struct.unpack_from("<Q4sI", data, offset)
        chunks.append((offset, length, kind))
        offset += 16 + length + (-length % 8)
    return chunks


def test_stkp_layout_and_corruption_is_rejected():
    data = (EXAMPLE / "example.stkp").read_bytes()
    assert data[:4] == b"STKP" and struct.unpack_from("<IQ", data, 4) == (2, len(data))
    chunks = _stkp_chunks(data)
    assert chunks[0][2] == b"JSON" and all(kind == b"BIN " for _, _, kind in chunks[1:])
    assert all((offset + 16) % 8 == 0 for offset, _, _ in chunks)
    corrupt = [
        (b"XXXX" + data[4:], "bad magic"),
        (data[:4] + struct.pack("<I", 3) + data[8:], "version 3"),
        (data[:8] + struct.pack("<Q", len(data) + 1) + data[16:], "length field"),
        (data[:-8], "length field"),
    ]
    offset = chunks[1][0]
    flipped = bytearray(data)
    flipped[offset + 16] ^= 0xFF
    corrupt.append((bytes(flipped), "hash"))
    reserved = bytearray(data)
    reserved[offset + 12] = 1
    corrupt.append((bytes(reserved), "reserved"))
    for bad, message in corrupt:
        with pytest.raises(PayloadError, match=message):
            read_stkp(bad)
    manifest, blobs = unpack_stkp(data)
    assert all(b["uri"] == "sha256:" + b["sha256"] for b in manifest["buffers"])


def _mutated(mutate):
    example = read_directory(EXAMPLE)
    manifest = copy.deepcopy(example.manifest)
    mutate(manifest)
    return manifest, example.blobs


@pytest.mark.parametrize("mutate, message", [
    (lambda m: m.update(schema="stk.payload/1"), "schema"),
    (lambda m: m["accessors"][0].update(byteOffset=4), "multiple of 8"),
    (lambda m: m["accessors"][0].update(count=10_000), "past the end"),
    (lambda m: m["accessors"][2].update(count=107), "multiple of 3"),
    (lambda m: m["layers"][0].update(positions="nope"), "unknown accessor"),
    (lambda m: m["layers"][0]["appearance"]["color"].update(colormap="pal9"), "unknown colormap"),
    (lambda m: m["colormaps"][0].update(lut="mesh_pos"), "u8"),
    (lambda m: m["layers"][0]["attributes"]["height"].update(accessor="gly_mag"), "expected 72"),
    (lambda m: m["layers"][2]["grid"].update(dimensions=[8, 8, 7]), "expected 448"),
    (lambda m: m["layers"].append({"id": "domains", "type": "overlay", "kind": "text", "text": "x"}), "duplicate"),
    (lambda m: m["buffers"][0].update(byteLength=1), "byteLength"),
    (lambda m: m.update(render_origin=[0, 0, float("inf")]), "finite"),
    (lambda m: m["layers"][4].update(colormap="pal0"), "continuous colormap"),
    # Volume transfer functions and scalar-bar labels (review finding RP7/RP4).
    (lambda m: m["layers"][2]["transfer_function"].update(range=[0, float("nan")]), "two finite numbers"),
    (lambda m: m["layers"][2]["transfer_function"].update(range=[0]), "two finite numbers"),
    (lambda m: m["layers"][2]["transfer_function"].update(opacity=[[0.0, 2.0]]), "alpha in"),
    (lambda m: m["layers"][2]["transfer_function"].update(opacity="ramp"), "non-empty list"),
    (lambda m: m["layers"][2].update(transfer_function=["cm0"]), "must be an object"),
    (lambda m: m["layers"][4].update(format="999999"), "unsupported label format"),
    (lambda m: m["layers"][4].update(format="{}"), "unsupported label format"),
    (lambda m: m["layers"][4].update(label_count=1), "label_count"),
    (lambda m: m["layers"][4].update(range=[0, "1"]), "two finite numbers"),
    # Wrong JSON types where objects are expected: PayloadError, never AttributeError/TypeError.
    (lambda m: m["layers"][0]["attributes"].update(height="accessor"), "malformed manifest"),
    (lambda m: m["layers"][1].update(glyph="arrow"), "malformed manifest"),
    (lambda m: m["layers"][0]["appearance"].update(color="red"), "malformed manifest"),
    (lambda m: m["layers"][2].update(lods=[7]), "must be an object"),
    (lambda m: m["layers"][2].update(grid={"dimensions": [8, 8, 8], "origin": None, "spacing": [1, 1, 1]}),
     "3 finite numbers"),
])
def test_decoder_rejects_invalid_manifests(mutate, message):
    manifest, blobs = _mutated(mutate)
    with pytest.raises(PayloadError, match=message):
        decode(manifest, blobs)


def test_decoder_rejects_manifests_that_are_not_objects(tmp_path):
    def stkp(manifest):
        data = json.dumps(manifest).encode()
        body = struct.pack("<Q4sI", len(data), b"JSON", 0) + data + b" " * (-len(data) % 8)
        return b"STKP" + struct.pack("<IQ", 2, 16 + len(body)) + body

    example = read_directory(EXAMPLE)
    for manifest, message in (([], "JSON object"), ("payload", "JSON object"),
                              ({"schema": "stk.payload/2", "buffers": "none"}, "list of objects"),
                              ({"buffers": [1]}, "list of objects")):
        with pytest.raises(PayloadError, match=message):
            decode(manifest, example.blobs.get)
        with pytest.raises(PayloadError, match=message):
            unpack_stkp(stkp(manifest))
        (tmp_path / "manifest.json").write_text(json.dumps(manifest))
        with pytest.raises(PayloadError, match=message):
            read_directory(tmp_path)


def test_scalar_bar_formats_are_validated_when_encoding():
    from suan.render.payload import LABEL_FORMAT
    for good in (".3g", ".2f", "+.1e", ".0%", "08.3f", ",.2f", "", "g"):
        assert LABEL_FORMAT.match(good), good
        format(1234.5678, good)  # every accepted format is also a valid Python format for floats
    for good in ("d", ",d", "+05d"):  # integers (as in d3): the offscreen renderer rounds the value first
        assert LABEL_FORMAT.match(good), good
        format(1234, good)
    for bad in ("999999", ".999f", "{}", "abc", ".3d", "~s", "x" * 3, "999d"):
        assert not LABEL_FORMAT.match(bad), bad
    scene = volume_scene()
    scene.layer("bar").appearance["format"] = "999999"
    with pytest.raises(PayloadError, match="label format") as error:
        encode_scene(scene, profile="web")
    assert error.value.code == "invalid_param"


def test_decoder_rejects_out_of_range_indices_and_non_finite_positions():
    example = read_directory(EXAMPLE)
    builder = PayloadBuilder()
    builder.add_accessor("pos", np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=np.float32))
    builder.add_accessor("idx", np.array([0, 1, 3], dtype=np.uint32))
    builder.add_accessor("bad", np.array([[0, 0, np.nan]] * 3, dtype=np.float32))
    builder.add_layer({"id": "t", "type": "triangles", "positions": "pos", "indices": "idx"})
    with pytest.raises(PayloadError, match="missing position"):
        builder.build().validate()
    builder.layers[0]["indices"] = "pos"
    with pytest.raises(PayloadError, match="u32"):
        builder.build().validate()
    builder.layers[0].update(positions="bad", indices="idx")
    with pytest.raises(PayloadError, match="finite"):
        builder.build().validate()
    unknown = copy.deepcopy(example.manifest)
    unknown["layers"].append({"id": "future", "type": "labels", "anything": 1})     # clients skip unknown types
    assert decode(unknown, example.blobs)


def test_builder_deduplicates_content_and_aligns_groups():
    builder = PayloadBuilder()
    a = builder.add_accessor("a", np.arange(5, dtype=np.float32))
    b = builder.add_accessor("b", np.arange(5, dtype=np.float32))
    with builder.buffer("g"):
        builder.add_accessor("c", np.arange(3, dtype=np.uint8))
        builder.add_accessor("d", np.arange(3, dtype=np.float64))
    payload = builder.build()
    accessors = {x["id"]: x for x in payload.manifest["accessors"]}
    assert accessors[a]["buffer"] == accessors[b]["buffer"] and len(payload.manifest["buffers"]) == 2
    assert accessors["d"]["byteOffset"] == 8 and accessors["c"]["min"] == [0] and accessors["d"]["max"] == [2.0]
    with pytest.raises(PayloadError):
        builder.add_accessor("a", np.zeros(1))
    with pytest.raises(PayloadError):
        builder.add_accessor("e", np.zeros(1, dtype=np.complex64))


def test_scene_round_trip_through_stkp_keeps_geometry_and_precision(tmp_path):
    scene = mixed_scene()
    payload = encode_scene(scene, profile="desktop")
    back = read_stkp(payload.write_stkp(tmp_path / "scene.stkp"))
    assert back.manifest == payload.manifest
    assert read_directory(payload.write_directory(tmp_path / "dir").parent).manifest == payload.manifest
    m = back.manifest
    assert m["render_origin"] == [1.0e6, -3.0, 7.0] and m["length_unit"] == "grid_index"
    assert {layer["type"] for layer in m["layers"]} == {"triangles", "slice_image", "lines", "points", "instances",
                                                         "volume", "overlay"}
    tri = back.layer("tri")
    physical = back.array(tri["positions"]).astype(np.float64) + m["render_origin"]
    assert np.abs(physical - scene.layer("tri").geometry["positions"]).max() < 1e-6
    assert back.array(tri["attributes"]["label"]["accessor"]).tolist() == [1, 2] * 6
    palette = back.colormap(tri["attributes"]["label"]["palette"])
    assert palette["name"] == "stk:categorical" and palette["entries"][0]["color"] == [1.0, 0.0, 0.0]
    assert tri["appearance"]["color"]["range"] == [-1.0, 1.0]        # range_mode symmetric
    image = back.layer("slice")
    assert image["size"] == [5, 4] and image["plane"]["origin"] == [-2.0, -2.0, 0.0]
    assert back.array(image["attributes"]["value"]["accessor"]).tolist() == list(range(20))
    assert image["attributes"]["vec"]["component_names"] == ["x", "y", "z"]
    arrows = back.layer("arrows")
    assert arrows["glyph"]["shape"] == "cone" and arrows["appearance"]["scale"] == {"by": "uniform", "factor": 0.4}
    assert arrows["appearance"]["color"]["colormap"] == "stk:orientation-hsl"
    vol = back.layer("vol")
    assert back.accessor(vol["data"])["type"] == "f32" and vol["transfer_function"]["opacity"][-1][1] == 1.0
    overlays = {layer["id"]: layer for layer in m["layers"] if layer["type"] == "overlay"}
    assert back.colormap(overlays["bar"]["colormap"])["name"] == "turbo"
    assert overlays["bar"]["colormap"] == tri["appearance"]["color"]["colormap"]     # one LUT, shared
    assert overlays["legend"]["colormap"] == tri["attributes"]["label"]["palette"]
    assert m["stats"]["triangles"] == 12 and m["stats"]["instances"] == 20 and m["stats"]["voxels"] == 512
    assert m["stats"]["texels"] == 20 and m["stats"]["line_segments"] == 12 and m["stats"]["points"] == 50
    assert m["stats"]["bytes"] == back.nbytes and m["source"]["reduced"] is False
    assert m["view"]["schema"] == "stk.view/1" and m["source"]["time"] == {"step": 1000, "time": None}


def test_encoding_is_deterministic_and_content_addressed():
    first, second = encode_scene(domains_scene()), encode_scene(domains_scene())
    assert first.manifest == second.manifest and first.blobs == second.blobs
    moved = domains_scene(origin=(100.0, 50.0, 30.0))
    third = encode_scene(moved)
    shared = set(first.blobs) & set(third.blobs)
    assert shared, "buffers that do not change (e.g. labels, LUT) are reused across frames"


def test_far_layers_get_their_own_origin():
    near = Layer("points", id="near", geometry={"positions": np.array([[0.0, 0, 0], [1, 1, 1]])})
    far = Layer("points", id="far", geometry={"positions": np.array([[1e7, 0, 0], [1e7 + 1e-3, 1e-3, 1e-3]])})
    payload = encode_scene(Scene(layers=[near, far], render_origin=(0.0, 0.0, 0.0)), profile="desktop")
    layer = payload.layer("far")
    assert "origin" in layer and "origin" not in payload.layer("near")
    physical = payload.array(layer["positions"]).astype(np.float64) + layer["origin"]
    assert np.abs(physical - far.geometry["positions"]).max() < 1e-9


def test_budget_limits_and_profile_table():
    assert PROFILES["phone"] == {"triangles": 300_000, "instances": 50_000, "points": 200_000, "voxels": 128 ** 3,
                                 "bytes": 32 * 1024 * 1024}
    assert budget_limits("web", {"triangles": 5})["triangles"] == 5
    for bad in ({"faces": 1}, {"triangles": -1}, {"triangles": 1.5}):
        with pytest.raises(PayloadError):
            budget_limits("web", bad)
    with pytest.raises(PayloadError):
        budget_limits("watch")


def test_triangle_budget_decimates_and_records_the_reduction():
    points, triangles = grid_mesh(60)
    labels = (np.arange(len(triangles)) % 3 + 1).astype(np.int16)
    layer = Layer("triangles", id="mesh", geometry={"positions": points, "indices": triangles},
                  attributes={"z": Attribute(points[:, 2].copy()),
                              "label": Attribute(labels, association="cell", categorical=True,
                                                 categories=({"value": 1, "name": "a"}, {"value": 2, "name": "b"},
                                                             {"value": 3, "name": "c"}))})
    payload = encode_scene(Scene(layers=[layer]), profile="phone", budget={"triangles": 1500})
    m = payload.manifest
    assert 0 < m["stats"]["triangles"] <= 1500 and m["source"]["reduced"] is True
    reduction = m["budget"]["reductions"][0]
    assert reduction["layer"] == "mesh" and reduction["from"] == len(triangles) and reduction["to"] <= 1500
    assert m["budget"]["profile"] == "phone" and m["budget"]["limits"]["triangles"] == 1500
    out = payload.layer("mesh")
    assert set(payload.array(out["attributes"]["label"]["accessor"]).tolist()) <= {1, 2, 3}
    assert payload.validate()


def test_cluster_decimate_keeps_labels_exact_and_meets_the_target():
    points, triangles = grid_mesh(40)
    labels = np.repeat(np.array([5, 9]), len(triangles) // 2)
    new_points, new_tris, _, attrs, cells = cluster_decimate(
        points, triangles, 400, point_attributes={"z": (points[:, 2], False)},
        cell_attributes={"label": (labels, True)})
    assert 0 < len(new_tris) <= 400 and new_tris.max() < len(new_points)
    assert set(cells["label"][0].tolist()) <= {5, 9} and len(cells["label"][0]) == len(new_tris)
    assert len(attrs["z"][0]) == len(new_points)
    same = cluster_decimate(points, triangles, 10_000)
    assert same[1] is not None and len(same[1]) == len(triangles)


def test_instance_point_volume_and_slice_budgets():
    glyphs = glyph_scene()
    payload = encode_scene(glyphs, budget={"instances": 10})
    arrows = payload.layer("arrows")
    assert payload.accessor(arrows["positions"])["count"] == 10
    kept = payload.array(arrows["positions"]).astype(np.float64) + payload.manifest["render_origin"]
    assert np.allclose(kept, glyphs.layer("arrows").geometry["positions"][:10], atol=1e-6)   # shuffled prefix
    volume = volume_scene()
    payload = encode_scene(volume, profile="desktop", budget={"voxels": 600})
    layer = payload.layer("density")
    assert layer["grid"]["dimensions"] == [8, 8, 8] and layer["grid"]["spacing"] == [1.0, 1.0, 1.0]
    assert any("stride 2" in r["reason"] for r in payload.manifest["budget"]["reductions"])
    image = Layer("slice_image", id="img", geometry={"plane": {"origin": [0, 0, 0], "u": [9.0, 0, 0],
                                                               "v": [0, 9.0, 0]}, "size": [10, 10]},
                  attributes={"v": Attribute(np.arange(100.0))})
    payload = encode_scene(Scene(layers=[image]), budget={"voxels": 20})
    layer = payload.layer("img")
    assert layer["size"] == [4, 4] and layer["plane"]["u"] == [9.0, 0.0, 0.0]
    assert payload.array(layer["attributes"]["v"]["accessor"]).tolist()[:4] == [0.0, 3.0, 6.0, 9.0]


def test_volume_encoding_follows_the_profile():
    data, _ = volume_scene().layers[0].geometry["data"], None
    for profile, kind in (("phone", "u8"), ("web", "u16"), ("desktop", "f32")):
        payload = encode_scene(volume_scene(), profile=profile)
        layer = payload.layer("density")
        stored = payload.array(layer["data"]).astype(np.float64)
        assert payload.accessor(layer["data"])["type"] == kind
        physical = stored * layer["value_scale"] + layer["value_offset"]
        step = layer["value_scale"] if kind != "f32" else 1e-7
        assert np.abs(physical - data.reshape(-1)).max() <= step
    labels = np.array([[[-1, 0], [7, 19]]], dtype=np.int16)
    grid = {"dimensions": [2, 2, 1], "origin": [0, 0, 0], "spacing": [1, 1, 1]}
    layer = Layer("volume", id="lab", geometry={"grid": grid, "data": labels, "categorical": True,
                                                "categories": [{"value": 7, "name": "O"}],
                                                "palette": "stk:categorical"})
    payload = encode_scene(Scene(layers=[layer]), profile="phone")
    out = payload.layer("lab")
    assert out["sampling"] == "nearest" and payload.accessor(out["data"])["type"] == "u8"
    restored = payload.array(out["data"]) * out["value_scale"] + out["value_offset"]
    assert restored.tolist() == [-1, 0, 7, 19]
    assert payload.colormap(out["transfer_function"]["colormap"])["categorical"]
    assert not any(r["reason"].startswith("volume quantized") for r in payload.manifest["budget"]["reductions"])


def test_byte_budget_shrinks_counts_or_fails_clearly():
    points, triangles = grid_mesh(80)
    layer = Layer("triangles", id="mesh", geometry={"positions": points, "indices": triangles})
    full = encode_scene(Scene(layers=[layer]), profile="desktop")
    limit = full.manifest["stats"]["bytes"] // 3
    small = encode_scene(Scene(layers=[layer]), profile="desktop", budget={"bytes": limit})
    assert small.manifest["stats"]["bytes"] <= limit and small.manifest["source"]["reduced"]
    with pytest.raises(PayloadError) as error:
        encode_scene(Scene(layers=[layer]), profile="desktop", budget={"bytes": 10})
    assert error.value.code == "budget_exceeded"


def test_large_origin_grid_keeps_sub_spacing_precision():
    origin = np.array([1.0e6, -3.0, 7.0])
    points, triangles = grid_mesh(12, origin=origin)
    points[:, :2] = origin[:2] + (points[:, :2] - origin[:2]) * 1e-3            # spacing 1e-3 at x = 1e6
    layer = Layer("triangles", id="fine", geometry={"positions": points, "indices": triangles})
    grid = {"bounds": [points.min(axis=0).tolist(), points.max(axis=0).tolist()]}
    scene = Scene(layers=[layer], render_origin=tuple((np.array(grid["bounds"][0]) + grid["bounds"][1]) / 2))
    payload = encode_scene(scene)
    rel = payload.array(payload.layer("fine")["positions"])
    assert np.abs(rel).max() < 1.0 and rel.dtype == np.float32
    physical = rel.astype(np.float64) + payload.manifest["render_origin"]
    assert np.abs(physical - points).max() < 1e-7
    assert payload.manifest["bounds"][0][0] == pytest.approx(-0.0055, abs=1e-9)


def test_payload_manifest_validates_against_the_json_schema():
    jsonschema = pytest.importorskip("jsonschema")
    referencing = pytest.importorskip("referencing")
    from suan.contracts import URN_PREFIX, load_all_schemas
    schemas = load_all_schemas()
    registry = referencing.Registry().with_resources(
        [(urn, referencing.Resource.from_contents(schema)) for urn, schema in schemas.items()])
    validator = jsonschema.Draft202012Validator(schemas[URN_PREFIX + "payload-2"], registry=registry)
    for scene in (mixed_scene(), domains_scene(), glyph_scene(), volume_scene()):
        manifest = encode_scene(scene, profile="phone").manifest
        assert [e.message for e in validator.iter_errors(manifest)] == []


def test_pack_stkp_matches_payload_method_and_hashes():
    payload = encode_scene(domains_scene())
    data = pack_stkp(payload.manifest, payload.blobs)
    assert data == payload.to_stkp()
    for buffer in payload.manifest["buffers"]:
        assert hashlib.sha256(payload.blobs[buffer["sha256"]]).hexdigest() == buffer["sha256"]
    assert isinstance(read_stkp(data), Payload)
