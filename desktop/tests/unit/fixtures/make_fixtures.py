"""Generate the parity fixtures of the desktop CPU libraries (stk_io, stk_viewer_model) from the Python
reference implementation (suan.render.payload, suan.graph.schema, suan.render.colormaps/layers,
the offscreen label format and VTK glyph sources). Deterministic; small files only.

    PYTHONPATH=. python desktop/tests/unit/fixtures/make_fixtures.py

Writes next to this file:
  payload/scenes/<name>.stkp + <name>.json   encoded test scenes and per-accessor checksums
  payload/cases.json                          spec §10 cases, stkp corruptions and a seeded mutation
                                              corpus, each with the Python verdict (ok / error path)
  schema_cases.json                           check_value(value, schema) -> [(path, message)]
  regex_cases.json                            re.search(pattern, text) and invalid patterns
  graph_cases.json                            graph_hash, canonical_json, parameter_schema,
                                              find_param_refs, node-param issues, normalize_value
  format_cases.json                           offscreen scalar-bar labels (Python format, 'd' rounding)
  colormap_cases.json                         lut_index, hsl/orientation colours, categorical opacity
  camera_cases.json                           fit_camera, default_view_up
  glyph_vtk.json                              VTK glyph source points/polygons (offscreen parameters)
  png/*.png + png/cases.json                  PNGs of every colour type with expected RGBA8 pixels
  fuzz_corpus/                                seeds of the payload decoder fuzzer
"""
from pathlib import Path
import base64
import copy
import hashlib
import json
import math
import random
import re
import struct
import sys
import zlib

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import numpy as np  # noqa: E402

from suan.graph import schema as gschema  # noqa: E402
from suan.graph.catalog import spec_catalog  # noqa: E402
from suan.graph.registry import Registry  # noqa: E402
from suan.render import colormaps, layers  # noqa: E402
from suan.render import payload as P  # noqa: E402

EXAMPLE = ROOT / "docs" / "specs" / "examples" / "payload-v2"


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=None, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"wrote {path.relative_to(ROOT)} ({path.stat().st_size} bytes)")


def b64(data):
    return base64.b64encode(bytes(data)).decode("ascii")


# ---------------------------------------------------------------------------------------------
# Payload decoding


def verdict(fn):
    try:
        fn()
    except P.PayloadError as error:
        return {"ok": False, "path": error.path, "message": str(error)}
    except Exception as error:  # noqa: BLE001 - a crash of the reference is recorded, never hidden
        return {"ok": False, "path": "", "message": f"CRASH {type(error).__name__}: {error}", "crash": True}
    return {"ok": True}


def apply_patch(manifest, patch):
    """Patches are [op, path(list), value?]: set, delete, append (to a list), insert."""
    op, path = patch[0], patch[1]
    target = manifest
    for key in path[:-1]:
        target = target[key]
    last = path[-1] if path else None
    if op == "set":
        if not path:
            return copy.deepcopy(patch[2])
        target[last] = copy.deepcopy(patch[2])
    elif op == "delete":
        del target[last]
    elif op == "append":
        target[last].append(copy.deepcopy(patch[2]))
    elif op == "insert":
        target[last[0]].insert(last[1], copy.deepcopy(patch[2]))
    else:
        raise ValueError(op)
    return manifest


def patched(manifest, patches):
    m = copy.deepcopy(manifest)
    for patch in patches:
        m = apply_patch(m, patch)
    return m


def json_paths(value, prefix=()):
    yield prefix
    if isinstance(value, dict):
        for key, item in value.items():
            yield from json_paths(item, prefix + (key,))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from json_paths(item, prefix + (index,))


REPLACEMENTS = [None, True, False, 0, -1, 1, 7, 2.5, -3.75, 1e300, 256, 65536, 2 ** 40, "", "x", "sha256:" + "0" * 64,
                "#1", "u8", "f32", "point", "cell", "arrow", "segments", "polylines", [], {}, [0, 0, 0], [1, 2],
                [0.0, 1.0], [[0, 0], [1, 1]], {"a": 1}, {"by": "attribute", "attribute": "nope"},
                {"schema": "stk.view/1"}, "stk:orientation-hsl", "pal0", "cm0", "mesh_pos"]


def random_patch(rng, manifest):
    paths = [p for p in json_paths(manifest) if p]
    path = list(rng.choice(paths))
    parent = manifest
    for key in path[:-1]:
        parent = parent[key]
    current = parent[path[-1]]
    choice = rng.random()
    if choice < 0.2 and isinstance(parent, dict):
        return ["delete", path]
    if choice < 0.3 and isinstance(current, (int, float)) and not isinstance(current, bool):
        delta = rng.choice([1, -1, 8, -8, 0.5])
        value = current + delta
        if isinstance(current, int) and not isinstance(delta, float):
            value = int(value)
        return ["set", path, value]
    if choice < 0.4:
        # a copy of another subtree (ids, accessor names, colormaps, ...)
        other = list(rng.choice(paths))
        source = manifest
        for key in other:
            source = source[key]
        return ["set", path, copy.deepcopy(source)]
    return ["set", path, rng.choice(REPLACEMENTS)]


def builder_case(name, build):
    builder = P.PayloadBuilder(render_origin=(1e6, -2.0, 3.0), length_unit="nm")
    build(builder)
    payload = builder.build()
    return {
        "name": name, "kind": "blobs", "manifest": payload.manifest,
        "blobs": {sha: b64(data) for sha, data in payload.blobs.items()},
        "python": verdict(lambda: P.decode(payload.manifest, payload.blobs)),
    }


def payload_cases():
    example = P.read_directory(EXAMPLE)
    manifest = example.manifest
    blobs = example.blobs
    cases = []

    def example_case(name, patches):
        m = patched(manifest, patches)
        cases.append({"name": name, "kind": "example", "patches": patches,
                      "python": verdict(lambda: P.decode(m, blobs))})

    # The cases of tests/test_render_payload.py (spec §10), as JSON patches of the example manifest.
    layers_ = manifest["layers"]
    li = {layer["id"]: i for i, layer in enumerate(layers_)}
    tri, arrows, density, box = li["domains"], li["arrows"], li["density"], li["box"]
    bar = next(i for i, l in enumerate(layers_) if l.get("kind") == "scalar_bar")
    legend = next(i for i, l in enumerate(layers_) if l.get("kind") == "legend")
    text = next(i for i, l in enumerate(layers_) if l.get("kind") == "text")
    acc = {a["id"]: i for i, a in enumerate(manifest["accessors"])}
    tri_idx = layers_[tri]["indices"]
    spec_cases = [
        ("valid example", []),
        ("schema differs", [["set", ["schema"], "stk.payload/1"]]),
        ("schema missing", [["delete", ["schema"]]]),
        ("render_origin missing", [["delete", ["render_origin"]]]),
        ("render_origin not finite (string)", [["set", ["render_origin"], [0, 0, "inf"]]]),
        ("render_origin too short", [["set", ["render_origin"], [0, 0]]]),
        ("render_origin bool", [["set", ["render_origin"], [0, True, 0]]]),
        ("length_unit empty", [["set", ["length_unit"], ""]]),
        ("byteOffset misaligned", [["set", ["accessors", 0, "byteOffset"], 4]]),
        ("accessor past the end", [["set", ["accessors", 0, "count"], 10000]]),
        ("triangle indices not a multiple of 3", [["set", ["accessors", acc[tri_idx], "count"], 107]]),
        ("unknown positions accessor", [["set", ["layers", tri, "positions"], "nope"]]),
        ("positions not x3", [["set", ["accessors", acc[layers_[tri]["positions"]], "components"], 2]]),
        ("positions not f32", [["set", ["accessors", acc[layers_[tri]["positions"]], "type"], "f64"],
                               ["set", ["accessors", acc[layers_[tri]["positions"]], "count"], 36]]),
        ("instance directions count", [["set", ["layers", arrows, "directions"], layers_[arrows]["positions"]],
                                       ["set", ["layers", arrows, "positions"], layers_[tri]["positions"]]]),
        ("triangle indices are floats", [["set", ["layers", tri, "indices"], layers_[tri]["positions"]]]),
        ("unknown colour colormap", [["set", ["layers", tri, "appearance", "color", "colormap"], "pal9"]]),
        ("lut is not u8", [["set", ["colormaps", 0, "lut"], manifest["accessors"][0]["id"]]]),
        ("attribute count mismatch", [["set", ["layers", tri, "attributes", "height", "accessor"],
                                       layers_[arrows]["directions"]]]),
        ("volume count mismatch", [["set", ["layers", density, "grid", "dimensions"], [8, 8, 7]]]),
        ("duplicate layer id", [["append", ["layers"], {"id": "domains", "type": "overlay", "kind": "text",
                                                         "text": "x"}]]),
        ("byteLength differs", [["set", ["buffers", 0, "byteLength"], 1]]),
        ("scalar bar with a categorical colormap", [["set", ["layers", bar, "colormap"], "pal0"]]),
        ("tf range one value", [["set", ["layers", density, "transfer_function", "range"], [0]]]),
        ("tf alpha out of range", [["set", ["layers", density, "transfer_function", "opacity"], [[0.0, 2.0]]]]),
        ("tf opacity string", [["set", ["layers", density, "transfer_function", "opacity"], "ramp"]]),
        ("tf opacity empty", [["set", ["layers", density, "transfer_function", "opacity"], []]]),
        ("tf is a list", [["set", ["layers", density, "transfer_function"], ["cm0"]]]),
        ("scalar bar format too wide", [["set", ["layers", bar, "format"], "999999"]]),
        ("scalar bar format braces", [["set", ["layers", bar, "format"], "{}"]]),
        ("scalar bar format .3d", [["set", ["layers", bar, "format"], ".3d"]]),
        ("scalar bar format ok +.1e", [["set", ["layers", bar, "format"], "+.1e"]]),
        ("scalar bar format ok 08,.2f", [["set", ["layers", bar, "format"], "08,.2f"]]),
        ("scalar bar format ok +05d", [["set", ["layers", bar, "format"], "+05d"]]),
        ("label_count 1", [["set", ["layers", bar, "label_count"], 1]]),
        ("label_count 21", [["set", ["layers", bar, "label_count"], 21]]),
        ("label_count float", [["set", ["layers", bar, "label_count"], 5.0]]),
        ("scalar bar range string", [["set", ["layers", bar, "range"], [0, "1"]]]),
        ("attribute is a string", [["set", ["layers", tri, "attributes", "height"], "accessor"]]),
        ("glyph is a string", [["set", ["layers", arrows, "glyph"], "arrow"]]),
        ("glyph shape unknown", [["set", ["layers", arrows, "glyph", "shape"], "star"]]),
        ("colour spec is a string", [["set", ["layers", tri, "appearance", "color"], "red"]]),
        ("colour mode unknown", [["set", ["layers", tri, "appearance", "color", "by"], "field"]]),
        ("volume lods not objects", [["set", ["layers", density, "lods"], [7]]]),
        ("grid origin null", [["set", ["layers", density, "grid"], {"dimensions": [8, 8, 8], "origin": None,
                                                                     "spacing": [1, 1, 1]}]]),
        ("grid spacing zero", [["set", ["layers", density, "grid", "spacing"], [1, 0, 1]]]),
        ("legend with a continuous colormap", [["set", ["layers", legend, "colormap"], "cm0"]]),
        ("text overlay without text", [["delete", ["layers", text, "text"]]]),
        ("unknown overlay kind", [["set", ["layers", text, "kind"], "sparkline"]]),
        ("unknown layer type is skipped", [["append", ["layers"], {"id": "future", "type": "labels", "anything": 1}]]),
        ("layer origin not finite", [["set", ["layers", tri, "origin"], [0, 0, None]]]),
        ("bounds malformed", [["set", ["bounds"], [[0, 0, 0]]]]),
        ("view without schema", [["set", ["view"], {"camera": {}}]]),
        ("buffers not a list", [["set", ["buffers"], "none"]]),
        ("buffer uri not sha256", [["set", ["buffers", 0, "uri"], "#1"]]),
        ("buffer encoding gzip", [["set", ["buffers", 0, "encoding"], "gzip"]]),
        ("buffer sha256 uppercase", [["set", ["buffers", 0, "sha256"], manifest["buffers"][0]["sha256"].upper()],
                                     ["set", ["buffers", 0, "uri"], "sha256:" + manifest["buffers"][0]["sha256"].upper()]]),
        ("accessor type unknown", [["set", ["accessors", 0, "type"], "f16"]]),
        ("accessor components 17", [["set", ["accessors", 0, "components"], 17]]),
        ("accessor count negative", [["set", ["accessors", 0, "count"], -1]]),
        ("accessor count float", [["set", ["accessors", 0, "count"], 3.0]]),
        ("normalized float accessor", [["set", ["accessors", acc[layers_[tri]["positions"]], "normalized"], True]]),
        ("categorical entry value float", [["set", ["colormaps", 1 if manifest["colormaps"][1].get("categorical")
                                                    else 0, "entries", 0, "value"], 1.5]]),
        ("categorical duplicate values", [["set", ["colormaps", next(i for i, c in enumerate(manifest["colormaps"])
                                                                     if c.get("categorical")), "entries", 1, "value"],
                                           manifest["colormaps"][next(i for i, c in enumerate(manifest["colormaps"])
                                                                      if c.get("categorical"))]["entries"][0]["value"]]]),
        ("lines mode unknown", [["set", ["layers", box, "mode"], "strips"]]),
        ("unknown palette", [["set", ["layers", tri, "attributes", "domain", "palette"], "cm0"]]),
        ("association unknown", [["set", ["layers", tri, "attributes", "height", "association"], "face"]]),
        ("instances scale attribute unknown", [["set", ["layers", arrows, "appearance", "scale"],
                                                {"by": "attribute", "attribute": "nope", "factor": 1}]]),
        ("appearance falsy is ignored", [["set", ["layers", tri, "appearance"], 0]]),
        ("manifest not an object", [["set", [], []]]),
    ]
    for name, patches in spec_cases:
        example_case(name, patches)

    # Data-level cases (small builder payloads with their blobs).
    def triangles(builder, positions, indices, **extra):
        builder.add_accessor("pos", np.asarray(positions, dtype=np.float32))
        builder.add_accessor("idx", np.asarray(indices, dtype=np.uint32))
        builder.add_layer({"id": "t", "type": "triangles", "positions": "pos", "indices": "idx", **extra})

    cases.append(builder_case("index out of range", lambda b: triangles(b, [[0, 0, 0], [1, 0, 0], [0, 1, 0]], [0, 1, 3])))
    cases.append(builder_case("positions not finite",
                              lambda b: triangles(b, [[0, 0, 0], [1, 0, 0], [0, 1, np.nan]], [0, 1, 2])))
    cases.append(builder_case("positions infinite",
                              lambda b: triangles(b, [[0, 0, 0], [np.inf, 0, 0], [0, 1, 0]], [0, 1, 2])))
    cases.append(builder_case("valid far triangle", lambda b: triangles(b, [[0, 0, 0], [1, 0, 0], [0, 1, 0]], [0, 1, 2])))

    def polylines(builder, offsets, cell_count=None):
        builder.add_accessor("pos", np.zeros((4, 3), dtype=np.float32))
        builder.add_accessor("idx", np.array([0, 1, 2, 3], dtype=np.uint32))
        builder.add_accessor("off", np.asarray(offsets, dtype=np.uint32))
        layer = {"id": "l", "type": "lines", "mode": "polylines", "positions": "pos", "indices": "idx", "offsets": "off"}
        if cell_count is not None:
            builder.add_accessor("cells", np.arange(cell_count, dtype=np.float32))
            layer["attributes"] = {"c": {"accessor": "cells", "association": "cell"}}
        builder.add_layer(layer)

    cases.append(builder_case("polylines ok", lambda b: polylines(b, [0, 2, 4])))
    cases.append(builder_case("polylines offsets not from 0", lambda b: polylines(b, [1, 4])))
    cases.append(builder_case("polylines offsets decreasing", lambda b: polylines(b, [0, 3, 2, 4])))
    cases.append(builder_case("polylines offsets short", lambda b: polylines(b, [0, 3])))
    cases.append(builder_case("polylines per-segment cells", lambda b: polylines(b, [0, 2, 4], cell_count=2)))
    cases.append(builder_case("polylines per-line cells", lambda b: polylines(b, [0, 3, 4], cell_count=2)))

    def slice_image(builder, w, h, count):
        builder.add_accessor("v", np.arange(count, dtype=np.float32))
        builder.add_layer({"id": "s", "type": "slice_image", "plane": {"origin": [0, 0, 0], "u": [1, 0, 0],
                                                                       "v": [0, 1, 0]},
                           "size": [w, h], "attributes": {"v": {"accessor": "v"}}})

    cases.append(builder_case("slice image ok", lambda b: slice_image(b, 3, 2, 6)))
    cases.append(builder_case("slice image count mismatch", lambda b: slice_image(b, 3, 2, 5)))

    def u16_indices(builder):
        builder.add_accessor("pos", np.zeros((3, 3), dtype=np.float32))
        builder.add_accessor("idx", np.array([0, 1, 2], dtype=np.uint16))
        builder.add_layer({"id": "t", "type": "triangles", "positions": "pos", "indices": "idx"})

    cases.append(builder_case("u16 indices", u16_indices))

    # .stkp framing: corruptions of example.stkp as byte patches [offset, hex] or a truncation.
    data = (EXAMPLE / "example.stkp").read_bytes()
    offset, chunks = 16, []
    while offset < len(data):
        length, kind, _ = struct.unpack_from("<Q4sI", data, offset)
        chunks.append((offset, length, kind))
        offset += 16 + length + (-length % 8)

    def stkp_case(name, edits=(), truncate=None, append=b""):
        bad = bytearray(data)
        for at, hexbytes in edits:
            raw = bytes.fromhex(hexbytes)
            bad[at:at + len(raw)] = raw
        if truncate is not None:
            bad = bad[:truncate]
        bad += append
        cases.append({"name": name, "kind": "stkp", "edits": [list(e) for e in edits], "truncate": truncate,
                      "append": append.hex(), "python": verdict(lambda: P.read_stkp(bytes(bad)))})

    stkp_case("stkp valid")
    stkp_case("stkp bad magic", [(0, b"XXXX".hex())])
    stkp_case("stkp version 3", [(4, struct.pack("<I", 3).hex())])
    stkp_case("stkp length field", [(8, struct.pack("<Q", len(data) + 1).hex())])
    stkp_case("stkp truncated", truncate=len(data) - 8)
    stkp_case("stkp too short", truncate=10)
    stkp_case("stkp buffer hash", [(chunks[1][0] + 16, "%02x" % (data[chunks[1][0] + 16] ^ 0xFF))])
    stkp_case("stkp reserved", [(chunks[1][0] + 12, "01")])
    stkp_case("stkp chunk type", [(chunks[1][0] + 8, b"BINX".hex())])
    stkp_case("stkp json chunk type", [(chunks[0][0] + 8, b"BIN ".hex())])
    stkp_case("stkp chunk length huge", [(chunks[2][0], struct.pack("<Q", 2 ** 40).hex())])
    stkp_case("stkp manifest not json", [(chunks[0][0] + 16, b"#".hex())])
    stkp_case("stkp trailing bytes", [(8, struct.pack("<Q", len(data) + 8).hex())], append=b"\0" * 8)

    # Seeded mutation corpus of the example manifest: the Python verdict is the expected result.
    rng = random.Random(20260925)
    for k in range(600):
        patches = [random_patch(rng, manifest)]
        if rng.random() < 0.25:
            patches.append(random_patch(rng, patched(manifest, patches)))
        try:
            m = patched(manifest, patches)
            json.dumps(m, allow_nan=False)
        except (KeyError, IndexError, TypeError, ValueError):
            continue
        cases.append({"name": f"mutation {k}", "kind": "example", "patches": patches,
                      "python": verdict(lambda: P.decode(m, blobs))})
    # Byte mutations of the .stkp framing and manifest chunk.
    for k in range(120):
        edits = []
        for _ in range(rng.randint(1, 3)):
            region = rng.random()
            if region < 0.3:
                at = rng.randrange(0, 16)
            elif region < 0.8:
                at = rng.randrange(chunks[0][0], chunks[0][0] + 16 + chunks[0][1])
            else:
                c = rng.choice(chunks)
                at = rng.randrange(c[0], c[0] + 16)
            edits.append((at, "%02x" % rng.randrange(256)))
        stkp_case(f"stkp mutation {k}", edits)
    crashes = [c["name"] for c in cases if c["python"].get("crash")]
    if crashes:
        print("warning: the Python decoder crashed on", crashes)
    return cases


def scene_fixtures(out):
    import render_scenes as scenes
    summary = {}
    for name, build in (("domains", scenes.domains_scene), ("glyphs", scenes.glyph_scene),
                        ("volume", scenes.volume_scene), ("iso", scenes.iso_scene), ("mixed", scenes.mixed_scene)):
        payload = P.encode_scene(build(), profile="desktop")
        payload.validate()
        (out / f"{name}.stkp").parent.mkdir(parents=True, exist_ok=True)
        (out / f"{name}.stkp").write_bytes(payload.to_stkp())
        accessors = {}
        for accessor in payload.manifest["accessors"]:
            values = np.asarray(payload.array(accessor["id"]), dtype=np.float64).ravel()
            accessors[accessor["id"]] = {"count": accessor["count"], "components": accessor["components"],
                                         "type": accessor["type"], "sum": float(values.sum()),
                                         "first": [float(v) for v in values[:6]]}
        summary[name] = {"layers": [[layer["id"], layer["type"]] for layer in payload.layers],
                         "render_origin": payload.manifest["render_origin"], "accessors": accessors,
                         "bytes": payload.nbytes}
        print(f"wrote {(out / f'{name}.stkp').relative_to(ROOT)}")
    write_json(out / "scenes.json", summary)


# ---------------------------------------------------------------------------------------------
# JSON Schema subset


PROBES = [None, True, False, 0, 1, -1, 2.0, 2.5, -3.75, 1e9, 4093, 4094, 1e-7, "", "abc", "Polar", "a/b", "a.b",
          "../x", "x/../y", "/abs", "C:x", "中文字段", "畴" * 129, "x" * 129, "latest", "first", "magnitude", "iso",
          "viridis", "stk:cubic-26-orientation", ".3g", "999999", "abc\n", [], [1, 2, 3], [0.5, None], [None, None],
          [1, 1], [1, 2], [0, 0, 0], [1.5, 2, 3], ["a"], [[0, 0], [1, 1]], {}, {"name": "Polar"},
          {"name": "Polar", "component": "magnitude"}, {"name": "Polar", "component": 0}, {"name": "a/b"},
          {"name": "Polar", "extra": 1}, {"by": "solid"}, {"by": "field", "field": "Polar"},
          {"by": "solid", "rnage": [0, 1]}, {"$param": "x"}]


def schema_cases():
    """{"schemas": [...], "values": [...], "cases": [[value index, schema index, [[path, message], ...] |
    {"raises": name}]]}."""
    schemas, index, value_table, value_index, cases = [], {}, [], {}, []

    def add(value, schema):
        key = json.dumps(schema, sort_keys=True)
        if key not in index:
            index[key] = len(schemas)
            schemas.append(schema)
        vkey = json.dumps(value, sort_keys=False)
        if vkey not in value_index:
            value_index[vkey] = len(value_table)
            value_table.append(value)
        try:
            result = [list(e) for e in gschema.check_value(value, schema)]
        except Exception as error:  # noqa: BLE001
            result = {"raises": type(error).__name__}
        cases.append([value_index[vkey], index[key], result])

    # tests/test_graph_schema.py and tests/test_nodes_render.py
    color = {"type": "object", "required": ["by"], "additionalProperties": False,
             "properties": {"by": {"enum": ["solid", "field"]}, "range": {
                 "type": "array", "prefixItems": [{"type": ["number", "null"]}, {"type": ["number", "null"]}],
                 "minItems": 2, "maxItems": 2}}}
    for value in ({"by": "solid", "range": [None, 2]}, {"by": "solid", "rnage": [0, 1]}, {"range": [0, 1]}):
        add(value, color)
    add(True, {"type": "integer"})
    add(2.0, {"type": "integer"})
    add(-3, {"anyOf": [{"type": "integer", "minimum": 0}, {"enum": ["latest"]}]})
    add([1, 1], {"type": "array", "uniqueItems": True})
    add([1, 1.0], {"type": "array", "uniqueItems": True})
    add([True, 1], {"type": "array", "uniqueItems": True})
    add(5, {"if": {"type": "integer"}, "then": {"maximum": 3}})
    add("x", {"if": {"type": "integer"}, "then": {"maximum": 3}, "else": {"minLength": 2}})
    add("x", {"oneOf": [{"type": "string"}, {"const": "x"}]})
    add(3, {"oneOf": [{"type": "string"}, {"const": "x"}]})
    add(3, {"not": {"type": "integer"}})
    add(3.5, {"not": {"type": "integer"}})
    add({"a": 1, "b": "x", "c/d": [1], "e~f": {}}, {"type": "object", "patternProperties": {"^[ab]$": {"type": "integer"}},
                                                    "additionalProperties": {"type": "array"}})
    add({"ab": 1, "Bad": 2}, {"type": "object", "propertyNames": {"pattern": "^[a-z]+$"}, "maxProperties": 1})
    add({}, {"type": "object", "minProperties": 1, "required": ["x", "y/z"]})
    add([1, "a", None], {"type": "array", "prefixItems": [{"type": "integer"}], "items": {"type": "string"}})
    add(1e20, {"type": "integer", "maximum": 1e19})
    add(0.1, {"type": "number", "exclusiveMinimum": 0.1})
    add(0.1, {"type": "number", "exclusiveMaximum": 0.1})
    add(5, {"const": 5.0})
    add(5, {"enum": [5.0, "5"]})
    add([1, {"a": [2]}], {"const": [1.0, {"a": [2.0]}]})
    add("abcdef", {"type": "string", "maxLength": 5, "minLength": 7})
    add("畴界面", {"type": "string", "maxLength": 3})
    add("畴界面", {"type": "string", "maxLength": 2})
    add({"camera": {"preset": "isometric"}}, {"type": "object", "properties": {"camera": {"type": "object",
         "properties": {"preset": {"enum": ["iso", "+x", "-x", None]}}, "additionalProperties": False}}})
    add({"prset": 1, "zzzz": 2}, {"type": "object", "properties": {"preset": {}, "position": {}},
                                  "additionalProperties": False})
    add({"x": 1}, {"type": "object", "additionalProperties": False})
    add(None, {"type": ["number", "null"]})
    add("a", {"type": ["number", "null"]})
    add("a", {"anyOf": [{"type": "number"}, {"const": "b"}, {"enum": ["c", "d"]}, {"type": ["array", "object"]}, True]})
    add("a", {"anyOf": [{"type": "number"}, {"type": "object"}]})
    add(12, {"anyOf": [{"type": "string"}, {"type": "number", "maximum": 3}]})
    add("x" * 100, {"enum": ["y" * 100]})
    add({"k": "中" * 70}, {"const": 1})
    add(1, {"type": "wat"})
    add(1, False)
    add(1, True)
    add([1, 2, 3], {"type": "array", "minItems": 4, "maxItems": 2})
    # Every param schema of the M1 catalog against default values and probes.
    catalog = spec_catalog()
    seen = set()
    for node in catalog["nodes"]:
        for name, schema in (node.get("params", {}).get("properties") or {}).items():
            key = json.dumps(schema, sort_keys=True)
            if key in seen:
                continue
            seen.add(key)
            values = list(PROBES)
            if "default" in schema:
                values.append(schema["default"])
            for value in values:
                add(value, schema)
    return {"schemas": schemas, "values": value_table, "cases": cases}


def normalize_cases():
    cases = []
    for value, schema in [([4.0, 4, 4], {"type": "array", "items": {"type": "integer"}}), (1, {"type": "number"}),
                          (-0.0, {"type": "number"}), (2.0, {"type": ["integer", "null"]}),
                          ({"a": 1, "b": 2.0}, {"type": "object", "properties": {"a": {"type": "number"}},
                                                "additionalProperties": {"type": "integer"}}),
                          ([1, 2.0, 3], {"prefixItems": [{"type": "number"}], "items": {"type": "integer"}}),
                          (3.0, {"anyOf": [{"type": "string"}, {"type": "integer"}]}),
                          ({"x": -0.0}, True), (-0.0, {})]:
        cases.append({"value": value, "schema": schema, "normalized": gschema.normalize_value(value, schema)})
    return cases


# ---------------------------------------------------------------------------------------------
# Python-compatible regex


def regex_cases():
    texts = ["", "a", "abc", "abc\n", "abc\n\n", "\n", "a/b", "a.b", "../x", "x/../y", "x/..", "..", "/abs", "\\x",
             "C:x", "c:", "Polar", "Polar.00000000.dat", "中文", "畴" * 3, "x" * 128, "x" * 129, "a_b-c", "A9",
             "run:1", "stk:cubic", "12", "١٢٣", "ab cd", "tab\there", "\u0000", "é", "é", "+.3g", ".3g", "999999",
             "08,.2f", "d", ",d", "+05d", "~s", "{}", "aaa", "aaaa", "abab", "xyz", "Ab_9", "_x"]
    patterns = [
        r"^[^/.]{1,128}$", r"^[a-z][a-z0-9_]{0,63}$", r"^([a-z0-9_]+:)?[a-z0-9_]+$", r"^[A-Za-z][A-Za-z0-9_]{0,7}$",
        r"^(?![/\\])(?![A-Za-z]:)(?!.*(^|/)\.\.(/|$))[^\\\u0000]+$",
        r"^[+\- ]?#?0?(?:[1-9][0-9]?)?,?(?:(?:\.[0-9]{1,2})?[eEfFgG%]?|d)$",
        r"abc", r"^abc$", r"^abc\Z", r"\Aabc", r"b", r"^b", r"c$", r"\d+", r"^\d+$", r"\w+", r"^\w+$", r"\s",
        r"\bab\b", r"\Bb", r"a{2}", r"a{2,}", r"a{,2}$", r"^a{1,3}$", r"a{", r"a{}", r"x{1,2", r"(ab)+", r"(?:ab)*c",
        r"(?P<n>a)b", r"(?=a)ab", r"a(?!b)", r"[^a-z]", r"[a\-z]", r"[-a]", r"[a-]", r"[]a]", r"[^]a]", r"[\d.]+$",
        r"[\w]{2}", r"\x41", r"é", r"\U0001F600|a", r"\101", r".", r"^.$", r"a|b|", r"(a|)+b", r"a*?b", r"(?#c)ab",
        r"é", "é", r"[é-ë]", r"^$", r"$", r"^", r"\n$", r"(a*)*b", r"(?:a|ab)(?:c|bcd)", r"\.\.", r"[.]{2}",
    ]
    # results[p][t] = search | match << 1 | fullmatch << 2 (one digit per text)
    results = []
    for pattern in patterns:
        compiled = re.compile(pattern)
        results.append("".join(str(int(compiled.search(t) is not None) | int(compiled.match(t) is not None) << 1
                                   | int(compiled.fullmatch(t) is not None) << 2) for t in texts))
    invalid = []
    for pattern in [r"a**", r"*a", r"a{3,2}", r"(ab", r"ab)", r"[ab", r"\q", r"[z-a]", r"^*", r"a++"]:
        try:
            re.compile(pattern)
            invalid.append({"pattern": pattern, "python_valid": True})
        except re.error:
            invalid.append({"pattern": pattern, "python_valid": False})
    return {"patterns": patterns, "texts": texts, "results": results, "invalid": invalid}


# ---------------------------------------------------------------------------------------------
# Graphs


def graph_cases():
    from suan.graph.catalog import _read_preset, _preset_files
    graphs = {}
    for item in _preset_files():
        graphs[item["id"]] = _read_preset(item["id"])["graph"]
    graphs["example"] = json.loads((ROOT / "docs/specs/examples/graph-v1/muferro-domains.json").read_text())
    variants = {}
    base = graphs["slice"]
    variants["reordered nodes"] = {**base, "nodes": list(reversed(base["nodes"]))}
    variants["ui and x- keys"] = {**base, "ui": {"positions": {}}, "x-note": 1, "name": "renamed",
                                  "nodes": [{**n, "label": "L", "x-y": 2} for n in base["nodes"]]}
    variants["float param"] = copy.deepcopy(base)
    variants["float param"]["parameters"][2]["default"] = 1.5
    variants["negative zero"] = copy.deepcopy(base)
    variants["negative zero"]["parameters"][2]["default"] = -0.0
    variants["unicode"] = {**base, "description": "中文", "parameters": base["parameters"] + [
        {"name": "title", "type": "string", "default": "畴 é \"q\" \\ \n"}]}
    variants["big numbers"] = {**base, "extensions": {"a": 1e16, "b": 1e15, "c": 1e-5, "d": 1e-4, "e": 123456789012,
                                                      "f": 0.1 + 0.2, "g": -1e-300, "h": 2 ** 53 + 1}}
    graphs.update(variants)
    hashes = [{"name": name, "graph": g, "hash": gschema.graph_hash(g),
               "canonical": gschema.canonical_json(g).decode("utf-8")} for name, g in graphs.items()]
    declarations = [{"name": "a", "type": t} for t in gschema.PARAMETER_TYPES if t != "enum"]
    declarations += [{"name": "e", "type": "enum", "choices": ["x", "y"]},
                     {"name": "n", "type": "number", "minimum": 0, "maximum": 1.5},
                     {"name": "i", "type": "integer", "minimum": True, "choices": [1, 2]},
                     {"name": "s", "type": "string", "choices": ["a"]}]
    parameter_schemas = [{"declaration": d, "schema": gschema.parameter_schema(d)} for d in declarations]
    refs = []
    for value in [{"$param": "x"}, {"$param": "x", "y": 1}, {"$param": 5}, {"$param": "Bad"},
                  {"a": [{"$param": "x"}, {"b": {"$param": "y"}}], "$anim": 1, "c/d": {"$param": "z"}}, [1, [{"$x": 2}]]]:
        refs.append({"value": value, "refs": [list(r) for r in gschema.find_param_refs(value, "/p")]})
    # Node-param issues of validate_graph for mutated preset graphs (the codes validate_node_params covers).
    registry = Registry.from_catalog(spec_catalog())
    codes = {"unknown_param", "missing_param", "invalid_param", "param_ref_type", "bad_param_ref", "reserved_key"}
    node_issues = []
    for preset, mutate in [
        ("slice", lambda g: None),
        ("slice", lambda g: g["nodes"][1]["params"].update(axis="w")),
        ("slice", lambda g: g["nodes"][1]["params"].update(axsi="x")),
        ("slice", lambda g: g["nodes"][0]["params"].pop("binding")),
        ("slice", lambda g: g["parameters"][1].update(default="q")),
        ("slice", lambda g: g["nodes"][1]["params"].update(index={"$param": "nope"})),
        ("slice", lambda g: g["nodes"][1]["params"].update(index={"$anim": [1]})),
        ("slice", lambda g: g["nodes"][2]["params"]["color"].update(component={"$param": "axis"})),
        ("iso", lambda g: g["nodes"][1]["params"].update(values={"$param": "path"})),
        ("volume", lambda g: g["nodes"][-1].setdefault("params", {}).update(width=3)),
        ("muferro-domains", lambda g: None),
        ("muferro-domains", lambda g: g["parameters"][1].update(default="x")),
    ]:
        g = copy.deepcopy(graphs[preset])
        mutate(g)
        issues = [i.to_dict() for i in gschema.validate_graph(g, registry) if i.code in codes]
        node_issues.append({"preset": preset, "graph": g,
                            "issues": [{"code": i["code"], "message": i["message"], "path": i["path"]} for i in issues]})
    return {"hashes": hashes, "parameter_schemas": parameter_schemas, "refs": refs, "node_issues": node_issues,
            "normalize": normalize_cases()}


# ---------------------------------------------------------------------------------------------
# Viewer model vectors


FORMATS = [".3g", ".2f", ".1e", ".0%", "d", "", ".3", ".1", ".0f", ".2e", ".4g", ".0g", "g", "e", "f", "%", "G", "E", "F",
           "+.3g", " .2f", "-.1e", "#.3g", "#.0f", "#.0e", "08.3f", "+08.2f", "010.1e", "8.2f", ",.2f", "012,.1f",
           "06,d", "05,d", "04,d", ",d", "+05d", "#d", "+d", "08,d", ",", "+", "10", "#g", ".10g", ".17g", ".20f",
           ".3G", "08,.3g", ",.0%"]
VALUES = [0.0, -0.0, 1.0, -1.0, 0.5, 1.5, 2.5, -2.5, 0.125, 0.375, 1234.5678, -1234.5678, 1e-5, 1.5e-5, 0.0001,
          0.00012345, 123456.0, 1234567.0, 1e16, 1e15, 9.995, 0.995, 99.95, 999.5, 1e21, 1e22, 1e-300, 5e-324,
          1.7976931348623157e308, 0.1, 0.2, 0.3, 1 / 3, 2 / 3, 12345678.9, 100.0, 1e3, 0.05, 0.015, 0.025, 1.005,
          2.675, 1e100, 123.456, -0.0001, 7.0, 10.0, 0.9999, 99999.5, 3.14159265358979]


def offscreen_label(value, fmt):
    from suan.render.offscreen import _label  # the label function of the offscreen renderer
    return _label(value, fmt)


def format_cases():
    cases = []
    for fmt in FORMATS:
        assert P.LABEL_FORMAT.match(fmt), fmt
        for value in VALUES + [math.inf, -math.inf, math.nan]:
            try:
                text = offscreen_label(value, fmt)
            except (ValueError, OverflowError) as error:
                text = None
                if not (fmt.endswith("d") and not math.isfinite(value)):
                    raise error
            cases.append({"format": fmt, "value": value if math.isfinite(value) else str(value), "text": text})
    return cases


def colormap_cases():
    lut = []
    ranges = [(0.0, 1.0), (-1.0, 1.0), (2.0, 2.0), (1.0, 0.0), (0.0, 1e-300), (-1e6, 1e6)]
    values = [-1e300, -1.0, -1e-17, 0.0, 1e-17, 0.00390625, 0.0039062, 0.5, 0.99609375, 0.9999999, 1.0, 1.0000001,
              2.0, math.inf, -math.inf, math.nan, 0.25, 0.75, 1e6, -1e6, 2.0]
    for lo, hi in ranges:
        for v in values:
            index = int(colormaps.lut_index([v], (lo, hi))[0])
            lut.append({"v": v if math.isfinite(v) else str(v), "lo": lo, "hi": hi, "index": index})
    rng = random.Random(5)
    orientation = []
    for _ in range(200):
        p = [rng.uniform(-2, 2) for _ in range(3)]
        if rng.random() < 0.1:
            p[0] = p[1] = 0.0
        if rng.random() < 0.05:
            p = [0.0, 0.0, 0.0]
        M = rng.choice([1.0, 2.0, 3.5, 0.0])
        l = rng.choice([(0.0, 1.0), (0.2, 0.8)])
        orientation.append({"p": p, "M": M, "l": list(l), "rgb": list(colormaps.orientation_rgb(p, M, l))})
    hsl = [{"hsl": [h, s, l], "rgb": list(colormaps.hsl_to_rgb(h, s, l))} for h in (-30.0, 0.0, 59.9, 60.0, 180.0, 359.9, 720.5)
           for s in (0.0, 0.65, 1.0) for l in (0.0, 0.38, 0.5, 1.0)]
    categorical = [{"v": v, "rgb": list(colormaps.stk_categorical_color(v))} for v in range(-3, 40)]
    copacity = [{"range": list(r), "points": colormaps.categorical_opacity(r)} for r in ((-1, 26), (0, 5), (-3, -1), (2, 2))]
    opacity = []
    points = [[0.0, 0.0], [0.5, 1.0], [0.5, 0.2], [1.0, 0.8]]
    for v in (-1.0, 0.0, 0.25, 0.5, 0.75, 1.0, 2.0):
        opacity.append({"points": points, "v": v, "alpha": float(colormaps.opacity_at([v], points)[0])})
    rgba8 = [{"c": c, "rgba": list(colormaps.rgba8(c))} for c in ([0.5, 0.5, 0.5], [0.0, 1.0, 0.999], [0.001961, 0.998039, 0.5, 0.25],
                                                                    [-0.1, 1.1, 0.5019607843137255])]
    return {"lut_index": lut, "orientation": orientation, "hsl": hsl, "categorical": categorical,
            "categorical_opacity": copacity, "opacity": opacity, "rgba8": rgba8}


def camera_cases():
    fits = []
    for bounds in (([-1, -1, -1], [1, 1, 1]), ([0, 0, 0], [10, 2, 1]), ([1e6, -3, 7], [1e6 + 2, -1, 9]), ([0, 0, 0], [0, 0, 0])):
        for preset in layers.PRESETS:
            for angle, zoom in ((30.0, 1.0), (45.0, 2.0), (10.0, 0.5)):
                fit = layers.fit_camera(bounds, preset, view_angle_deg=angle, zoom=zoom)
                fits.append({"bounds": [list(map(float, bounds[0])), list(map(float, bounds[1]))], "preset": preset,
                             "angle": angle, "zoom": zoom, "position": fit["position"], "focal_point": fit["focal_point"],
                             "view_up": fit["view_up"], "parallel_scale": fit["parallel_scale"]})
    ups = [{"position": p, "focal": f, "up": layers.default_view_up(p, f)} for p, f in
           (([0, 0, 10], [0, 0, 0]), ([0.01, 0, 10], [0, 0, 0]), ([1, 0, 10], [0, 0, 0]), ([5, 5, 5], [0, 0, 0]),
            ([0, 0, 0], [0, 0, 0]), ([0, 0, -3], [0, 0, 1]))]
    return {"fit": fits, "default_view_up": ups}


def glyph_cases():
    import vtk
    from vtk.util.numpy_support import vtk_to_numpy

    class Stub:
        def __init__(self):
            self.vtk = vtk
            self.keep = []

    from suan.render.offscreen import _Renderer
    out = []
    for shape in ("arrow", "cone", "sphere", "line", "cube"):
        for resolution in (3, 4, 6, 8, 12):
            for center in (False, True):
                stub = Stub()
                source = _Renderer.glyph_source(stub, {"shape": shape, "resolution": resolution, "center": center})
                source.Update()
                poly = source.GetOutput()
                points = vtk_to_numpy(poly.GetPoints().GetData()).astype(float).tolist()
                cells = []
                polys = poly.GetPolys()
                polys.InitTraversal()
                ids = vtk.vtkIdList()
                while polys.GetNextCell(ids):
                    cells.append([ids.GetId(i) for i in range(ids.GetNumberOfIds())])
                tri = vtk.vtkTriangleFilter()
                tri.SetInputData(poly)
                tri.Update()
                normals = poly.GetPointData().GetNormals()
                out.append({"shape": shape, "resolution": resolution, "center": center, "points": points,
                            "polygons": cells, "lines": poly.GetNumberOfLines(),
                            "triangles": tri.GetOutput().GetNumberOfPolys(),
                            "normals": vtk_to_numpy(normals).astype(float).tolist() if normals is not None else None})
    return {"vtk": vtk.vtkVersion.GetVTKVersion(), "glyphs": out}


# ---------------------------------------------------------------------------------------------
# PNG


def png_bytes(width, height, color_type, bit_depth, rows, palette=None, trns=None):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    raw = b"".join(b"\x00" + row for row in rows)
    out = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, bit_depth, color_type, 0, 0, 0))
    if palette:
        out += chunk(b"PLTE", bytes(v for rgb in palette for v in rgb))
    if trns is not None:
        out += chunk(b"tRNS", trns)
    return out + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


def png_fixtures(out):
    out.mkdir(parents=True, exist_ok=True)
    w, h = 5, 3
    rgba = [[(x * 50, y * 100, (x + y) * 20, 255 - x * 10) for x in range(w)] for y in range(h)]
    cases = []

    def add(name, color_type, bit_depth, rows, expected, palette=None, trns=None):
        data = png_bytes(w, h, color_type, bit_depth, rows, palette, trns)
        (out / f"{name}.png").write_bytes(data)
        cases.append({"name": name, "width": w, "height": h, "rgba": [list(p) for row in expected for p in row]})

    add("rgba8", 6, 8, [bytes(v for p in row for v in p) for row in rgba], rgba)
    add("rgb8", 2, 8, [bytes(v for p in row for v in p[:3]) for row in rgba], [[p[:3] + (255,) for p in row] for row in rgba])
    add("gray8", 0, 8, [bytes(p[0] for p in row) for row in rgba], [[(p[0],) * 3 + (255,) for p in row] for row in rgba])
    add("graya8", 4, 8, [bytes(v for p in row for v in (p[0], p[3])) for row in rgba],
        [[(p[0],) * 3 + (p[3],) for p in row] for row in rgba])
    add("rgba16", 6, 16, [b"".join(struct.pack(">HHHH", *(v * 257 for v in p)) for p in row) for row in rgba], rgba)
    palette = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (10, 20, 30)]
    idx = [[(x + y) % 4 for x in range(w)] for y in range(h)]
    add("palette_trns", 3, 8, [bytes(row) for row in idx],
        [[palette[i] + ((128,) if i == 3 else (255,)) for i in row] for row in idx], palette=palette,
        trns=bytes([255, 255, 255, 128]))
    good = (out / "rgba8.png").read_bytes()
    bad = bytearray(good)
    bad[40] ^= 0xFF  # inside IHDR/IDAT: CRC mismatch
    (out / "corrupt_crc.png").write_bytes(bytes(bad))
    (out / "truncated.png").write_bytes(good[: len(good) - 20])
    write_json(out / "cases.json", {"decode": cases, "invalid": ["corrupt_crc.png", "truncated.png"]})


# ---------------------------------------------------------------------------------------------


def main():
    only = set(sys.argv[1:])
    run = (lambda name: not only or name in only)
    if run("payload"):
        scene_fixtures(HERE / "payload" / "scenes")
        write_json(HERE / "payload" / "cases.json", payload_cases())
    if run("schema"):
        write_json(HERE / "schema_cases.json", schema_cases())
    if run("regex"):
        write_json(HERE / "regex_cases.json", regex_cases())
    if run("graph"):
        write_json(HERE / "graph_cases.json", graph_cases())
    if run("format"):
        write_json(HERE / "format_cases.json", format_cases())
    if run("colormap"):
        write_json(HERE / "colormap_cases.json", colormap_cases())
    if run("camera"):
        write_json(HERE / "camera_cases.json", camera_cases())
    if run("glyph"):
        write_json(HERE / "glyph_vtk.json", glyph_cases())
    if run("png"):
        png_fixtures(HERE / "png")
    if run("fuzz"):
        corpus = HERE / "fuzz_corpus"
        corpus.mkdir(exist_ok=True)
        (corpus / "example.stkp").write_bytes((EXAMPLE / "example.stkp").read_bytes())
        for scene in ("domains", "glyphs", "mixed"):
            (corpus / f"{scene}.stkp").write_bytes((HERE / "payload" / "scenes" / f"{scene}.stkp").read_bytes())
        print(f"wrote {corpus.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
