"""Manifests stk.dataset/1, stk.series/1 and stk.result/1: builders and hand-written validation."""
import json
import math

import pytest

from suan.contracts import load_schema
from suan.data.manifest import (ManifestError, check, dataset_manifest, file_entry, qoi_entry, result_manifest,
                                series_manifest, validate, validate_dataset, validate_result, validate_series)
from suan.data.model import Field, ImageData, Table

IMAGE = {"schema": "stk.dataset/1", "id": "Polar", "kind": "image",
         "geometry": {"frame": "grid", "length_unit": "grid_index", "dimensions": [4, 3, 2], "origin": [0, 0, 0],
                      "spacing": [1, 1, 1], "direction": [1, 0, 0, 0, 1, 0, 0, 0, 1]},
         "fields": [{"name": "Polar", "association": "point", "dtype": "float64", "components": 3, "tensor": "vector",
                     "component_names": ["x", "y", "z"], "quantity": "polarization", "unit": "unspecified"}],
         "time": {"index": "step", "step": 2, "value": None, "physical": {"unit": "unspecified", "known": False}},
         "frames": [{"step": 2, "time": None, "sources": {"Polar": {"path": "Polar.00000002.dat",
                                                                    "reader": "mupro.dat@1", "sha256": None}}}],
         "provenance": {"activity": {"kind": "run", "id": "t1"}, "agent": {"connector": "mupro.muferro@0.1.0"}}}


def test_dataset_descriptors_validate():
    assert validate_dataset(IMAGE) == [] and validate(IMAGE) == []
    image = ImageData((4, 3, 2), id="Polar")
    image.add(Field("Polar", components=3, tensor="vector"))
    assert dataset_manifest(image)["schema"] == "stk.dataset/1" and validate_dataset(dataset_manifest(image)) == []
    table = Table.from_columns({"step": [1, 2]}, index="step", id="energy")
    assert validate(dataset_manifest(table)) == []
    bad = json.loads(json.dumps(IMAGE))
    bad["id"] = "/bad"
    bad["geometry"]["spacing"] = [1, 0, 1]
    bad["fields"][0]["tensor"] = "symmetric_tensor"
    bad["frames"][0]["sources"]["Polar"]["path"] = "../escape.dat"
    bad["frames"][0]["sources"]["Polar"]["reader"] = "Mupro"
    bad["unexpected"] = 1
    problems = validate_dataset(bad)
    for pointer in ("/id", "/geometry/spacing/1", "/fields/0", "/frames/0/sources/Polar/path",
                    "/frames/0/sources/Polar/reader", "/unexpected"):
        assert any(p.startswith(pointer) for p in problems), (pointer, problems)
    assert validate_dataset({"id": "x", "kind": "image"}) == ["/geometry: is required for images"]
    assert any("tables use 'columns'" in p for p in validate_dataset(
        {"id": "t", "kind": "table", "fields": [IMAGE["fields"][0]]}))


def test_series_documents():
    series = series_manifest([{"step": 200, "outputs": {"image": "png/image.00000200.png"}},
                              {"step": 0, "outputs": {"image": {"path": "png/image.00000000.png", "size": 10}}}],
                             dataset="Polar")
    assert [f["step"] for f in series["frames"]] == [0, 200] and validate_series(series) == []
    assert check(series) is series
    series["frames"].append({"step": 0, "path": "/abs.dat"})
    problems = validate(series)
    assert any("unique" in p for p in problems) and any("/frames/2/path" in p for p in problems)
    with pytest.raises(ManifestError) as error:
        check(series)
    assert error.value.problems == problems


def test_result_manifest_builder_and_validation():
    result = result_manifest(
        connector="mupro.muferro", connector_version="0.1.0", app={"id": "mupro.muferro", "name": "muFerro"},
        state="succeeded", complete=True, datasets=[IMAGE],
        files=[file_entry("Polar.00000002.dat", size=10, media_type="text/plain")],
        qoi=[qoi_entry("total_energy", -2.25, "normalized", quantity="energy", step=2,
                       source={"dataset": "energy", "column": "Total Energy"}),
             qoi_entry("broken", math.nan, "normalized")],
        verification={"verifier": "stk-mupro-1", "status": "passed",
                      "checks": [{"id": "completion", "status": "pass", "message": "ok"}]},
        run={"runtime": {"task_id": "abc"}, "layout": {"ranks": 1, "threads_per_rank": 1, "launcher": None}},
        extensions={"mupro": {"case": {"grid": [4, 3, 2]}}},
        native=[{"path": "stk-mupro.json", "schema": "stk-mupro/1"}])
    assert validate_result(result) == [] and result["qoi"][1]["value"] == "NaN"
    assert result["producer"]["generated_at"].endswith("Z") and json.dumps(result, allow_nan=False)
    schema = load_schema("stk.result/1")
    assert set(result) <= set(schema["properties"]) and set(schema["required"]) <= set(result)
    broken = json.loads(json.dumps(result))
    broken["state"] = "done"
    broken["verification"]["status"] = "ok"
    broken["files"][0]["role"] = "data"
    broken["files"][0]["sha256"] = "XYZ"
    broken["run"]["layout"]["ranks"] = 0
    broken["qoi"][0]["value"] = "big"
    broken["datasets"].append(dict(IMAGE))
    problems = validate(broken)
    for pointer in ("/state", "/verification/status", "/files/0/role", "/files/0/sha256", "/run/layout/ranks",
                    "/qoi/0/value", "/datasets/1/id"):
        assert any(p.startswith(pointer) for p in problems), (pointer, problems)
    assert validate({"schema": "nope"})[0].startswith("/schema")


def test_manifests_against_json_schema_when_available():
    jsonschema = pytest.importorskip("jsonschema")
    from suan.contracts import load_all_schemas
    referencing = pytest.importorskip("referencing")
    registry = referencing.Registry().with_resources(
        (uri, referencing.Resource.from_contents(schema)) for uri, schema in load_all_schemas().items())
    result = result_manifest(connector="x", app="x.y", datasets=[IMAGE], state="unknown")
    jsonschema.Draft202012Validator(load_schema("result-1"), registry=registry).validate(result)
