"""Contract files: JSON Schemas, quantities, the payload v2 example and the M1 catalog."""
from importlib.resources import files
from pathlib import Path
import hashlib
import json
import runpy
import struct

import pytest

from suan.contracts import (DOCUMENT_SCHEMAS, SCHEMA_IDS, URN_PREFIX, list_schemas, load_all_schemas,
                            load_quantities, load_schema, quantity_info, schema_id)

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "suan" / "contracts" / "schemas"
PAYLOAD = ROOT / "docs" / "specs" / "examples" / "payload-v2"
GRAPH = ROOT / "docs" / "specs" / "examples" / "graph-v1" / "muferro-domains.json"
CATALOG = ROOT / "docs" / "specs" / "catalog" / "stk-catalog-m1.json"
M1_LAYERS = {"triangles", "slice_image", "lines", "points", "instances", "volume", "overlay"}
SIZES = {"i8": 1, "u8": 1, "i16": 2, "u16": 2, "i32": 4, "u32": 4, "f32": 4, "f64": 8}


def strict_load(path):
    def pairs(items):
        keys = [key for key, _ in items]
        assert len(keys) == len(set(keys)), f"duplicate key in {path.name}: {keys}"
        return dict(items)
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=pairs)


def test_schema_files_are_valid_json_with_unique_ids():
    paths = sorted(SCHEMAS.glob("*.schema.json"))
    assert [p.name[:-len(".schema.json")] for p in paths] == list(SCHEMA_IDS) == list(list_schemas())
    ids = []
    for path in paths:
        schema = strict_load(path)
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert schema["$id"] == URN_PREFIX + path.name[:-len(".schema.json")]
        assert schema.get("title") and schema.get("description")
        ids.append(schema["$id"])
    assert len(ids) == len(set(ids)) == 12
    assert set(DOCUMENT_SCHEMAS.values()) <= set(SCHEMA_IDS)
    for path in paths:  # every cross-file reference names a shipped schema
        for ref in _refs(strict_load(path)):
            if ref.startswith(URN_PREFIX):
                assert ref.split("#")[0] in ids, (path.name, ref)


def _refs(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "$ref":
                yield item
            else:
                yield from _refs(item)
    elif isinstance(value, list):
        for item in value:
            yield from _refs(item)


def test_loader_names_copies_and_package_data():
    assert schema_id("stk.graph/1") == schema_id("graph-1.schema.json") == schema_id(URN_PREFIX + "graph-1") == "graph-1"
    graph = load_schema("stk.graph/1")
    graph["title"] = "changed"
    assert load_schema("graph-1")["title"] != "changed"
    assert set(load_all_schemas()) == {URN_PREFIX + key for key in SCHEMA_IDS}
    with pytest.raises(KeyError):
        load_schema("graph-9")
    # Shipped as package data (poetry includes every file under suan/ in the wheel).
    assert files("suan.contracts").joinpath("schemas/payload-2.schema.json").is_file()
    assert files("suan.contracts").joinpath("quantities.json").is_file()


def test_quantities_vocabulary():
    document = load_quantities()
    assert document["schema"] == "stk.quantities/1"
    assert set(document["unit_tokens"]) == {"unspecified", "1", "normalized", "grid_index"}
    colours = set(document["colormaps"]) | set(document["palettes"])
    required = {"polarization", "electric_field", "strain", "stress", "displacement", "energy",
                "electron_density", "temperature", "concentration", "order_parameter", "label"}
    assert required <= set(document["quantities"])
    for name, entry in document["quantities"].items():
        assert set(entry["label"]) == {"en", "zh"}, name
        assert entry["tensor"] in {"scalar", "vector", "symmetric_tensor", "tensor", "quaternion", "array", "label"}
        assert entry["representation"] in document["representations"], name
        assert entry["colormap"] in colours, name
        assert entry["range"] in document["range_modes"], name
        assert isinstance(entry["dimension"], dict) and isinstance(entry["si_unit"], str)
        if entry["tensor"] == "symmetric_tensor":
            assert len(entry["component_names"]) == entry["components"] == 6
    assert quantity_info("stress")["component_names"] == ["xx", "yy", "zz", "yz", "xz", "xy"]
    extension = quantity_info("mupro:landau_force", "vector")
    assert not extension["known"] and extension["default_graph"] == "vectors" and extension["si_unit"] is None
    with pytest.raises(KeyError):
        quantity_info("not_a_quantity")


def _accessor_bytes(manifest, buffers, accessor_id):
    accessor = next(a for a in manifest["accessors"] if a["id"] == accessor_id)
    data = buffers[accessor["buffer"]]
    size = SIZES[accessor["type"]] * accessor["components"] * accessor["count"]
    assert accessor["byteOffset"] % 8 == 0 and accessor["byteOffset"] + size <= len(data)
    return accessor, data[accessor["byteOffset"]:accessor["byteOffset"] + size]


def test_payload_example_is_consistent():
    manifest = strict_load(PAYLOAD / "manifest.json")
    assert manifest["schema"] == "stk.payload/2"
    buffers = {}
    for buffer in manifest["buffers"]:
        data = (PAYLOAD / f"{buffer['sha256']}.bin").read_bytes()
        assert buffer["uri"] == "sha256:" + buffer["sha256"] == "sha256:" + hashlib.sha256(data).hexdigest()
        assert buffer["byteLength"] == len(data)
        buffers[buffer["id"]] = data
    accessors = {a["id"]: a for a in manifest["accessors"]}
    colormaps = {c["id"]: c for c in manifest["colormaps"]}
    for colormap in colormaps.values():
        if colormap["categorical"]:
            values = [entry["value"] for entry in colormap["entries"]]
            assert len(values) == len(set(values))
        else:
            lut, _ = _accessor_bytes(manifest, buffers, colormap["lut"])
            assert (lut["type"], lut["components"], lut["count"]) == ("u8", 4, 256)
    kinds = {layer["type"] for layer in manifest["layers"]}
    assert {"triangles", "instances", "volume", "overlay"} <= kinds <= M1_LAYERS
    by_type = {}
    for layer in manifest["layers"]:
        by_type.setdefault(layer["type"], layer)
        if "positions" in layer:
            count = accessors[layer["positions"]]["count"]
            assert accessors[layer["positions"]]["components"] == 3
            for attribute in layer.get("attributes", {}).values():
                assert accessors[attribute["accessor"]]["count"] == count
                if attribute.get("categorical"):
                    assert attribute["palette"] in colormaps and colormaps[attribute["palette"]]["categorical"]
        if layer["type"] in ("triangles", "lines"):
            accessor, raw = _accessor_bytes(manifest, buffers, layer["indices"])
            indices = struct.unpack(f"<{accessor['count']}I", raw)
            assert max(indices) < accessors[layer["positions"]]["count"]
            assert accessor["count"] % (3 if layer["type"] == "triangles" else 2) == 0
        if layer["type"] == "volume":
            nx, ny, nz = layer["grid"]["dimensions"]
            assert accessors[layer["data"]]["count"] == nx * ny * nz
            assert layer["transfer_function"]["colormap"] in colormaps
        if layer["type"] == "overlay" and "colormap" in layer and layer["colormap"] != "stk:orientation-hsl":
            assert layer["colormap"] in colormaps
    legend = next(layer for layer in manifest["layers"] if layer.get("kind") == "legend")
    domains = by_type["triangles"]["attributes"]["domain"]
    accessor, raw = _accessor_bytes(manifest, buffers, domains["accessor"])
    assert accessor["type"] == "i16" and set(struct.unpack(f"<{accessor['count']}h", raw)) == set(legend["values"])
    entries = {e["value"]: e for e in colormaps[domains["palette"]]["entries"]}
    assert entries[1]["name"] == "T[100]" and entries[1]["color"] == [1.0, 0.0, 0.0]
    assert entries[19]["name"] == "R[111]" and entries[19]["family"] == "R"


def test_stkp_matches_directory_form():
    manifest = strict_load(PAYLOAD / "manifest.json")
    data = (PAYLOAD / "example.stkp").read_bytes()
    magic, version, total = struct.unpack_from("<4sIQ", data, 0)
    assert (magic, version, total) == (b"STKP", 2, len(data))
    chunks, offset = [], 16
    while offset < len(data):
        length, kind, reserved = struct.unpack_from("<Q4sI", data, offset)
        assert reserved == 0
        offset += 16
        assert offset % 8 == 0
        chunks.append((kind, data[offset:offset + length]))
        offset += length + (-length % 8)
    assert offset == len(data)
    assert chunks[0][0] == b"JSON" and all(kind == b"BIN " for kind, _ in chunks[1:])
    packed = json.loads(chunks[0][1].decode("utf-8"))
    assert len(chunks) == 1 + len(packed["buffers"])
    for index, buffer in enumerate(packed["buffers"], start=1):
        assert buffer["uri"] == f"#{index}"
        assert hashlib.sha256(chunks[index][1]).hexdigest() == buffer["sha256"]
        buffer["uri"] = "sha256:" + buffer["sha256"]
    assert packed == manifest


def test_payload_example_is_reproducible():
    pytest.importorskip("numpy")
    module = runpy.run_path(str(PAYLOAD / "make_example.py"), run_name="stk_payload_example")
    manifest, blobs = module["build"]()
    assert module["dumps"](manifest) == (PAYLOAD / "manifest.json").read_text(encoding="utf-8")
    for digest, data in blobs:
        assert (PAYLOAD / f"{digest}.bin").read_bytes() == data
    assert module["pack_stkp"](manifest, blobs) == (PAYLOAD / "example.stkp").read_bytes()
    assert len(list(PAYLOAD.glob("*.bin"))) == len(blobs)


def test_examples_validate_against_schemas():
    jsonschema = pytest.importorskip("jsonschema")
    referencing = pytest.importorskip("referencing")
    schemas = load_all_schemas()
    registry = referencing.Registry().with_resources(
        [(urn, referencing.Resource.from_contents(schema)) for urn, schema in schemas.items()])

    def errors(schema, document):
        validator = jsonschema.Draft202012Validator(schema, registry=registry)
        return [f"{'/'.join(map(str, e.absolute_path))}: {e.message}" for e in validator.iter_errors(document)]

    for schema in schemas.values():
        jsonschema.Draft202012Validator.check_schema(schema)
    assert errors(schemas[URN_PREFIX + "payload-2"], strict_load(PAYLOAD / "manifest.json")) == []
    assert errors(schemas[URN_PREFIX + "graph-1"], strict_load(GRAPH)) == []
    assert errors({"$ref": URN_PREFIX + "node-type-1#/$defs/catalog"}, strict_load(CATALOG)) == []
    event = {"v": 1, "seq": 3, "ts": 1790000000.5, "type": "metrics", "src": "adapter",
             "data": {"step": 10, "values": {"total_energy": -1.5, "elastic_energy": "NaN"}}}
    assert errors(schemas[URN_PREFIX + "event-1"], event) == []
    assert errors(schemas[URN_PREFIX + "event-1"], {**event, "data": {"values": {"e": "nan"}}})
    assert errors(schemas[URN_PREFIX + "ref-1"], {"binding": "run", "path": "Polar.00001000.dat",
                                                   "frame": {"step": 1000}}) == []
    assert errors(schemas[URN_PREFIX + "ref-1"], {"binding": "run", "path": "../etc/passwd"})
    result = {
        "schema": "stk.result/1", "producer": {"connector": "mupro.muferro", "connector_version": "0.1.0"},
        "complete": True, "run": {"app": {"id": "mupro.muferro", "name": "muFerro"}, "exit_code": 0},
        "state": "succeeded", "frames_of_reference": {"grid": {"length_unit": "grid_index"}},
        "qoi": [{"name": "total_energy", "value": -1.125e3, "unit": "normalized", "quantity": "energy", "step": 1000,
                 "source": {"dataset": "energy", "column": "Total Energy"}}],
        "datasets": [{"id": "energy", "kind": "table", "columns": [
            {"name": "step", "association": "row", "dtype": "int64", "components": 1, "tensor": "scalar",
             "unit": "1", "role": "index"}],
            "frames": [{"step": None, "sources": {"*": {"path": "energy_out.dat", "reader": "mupro.energy@1"}}}]}],
        "files": [{"path": "energy_out.dat", "sha256": "0" * 64, "size": 1, "role": "output"}],
    }
    assert errors(schemas[URN_PREFIX + "result-1"], result) == []
