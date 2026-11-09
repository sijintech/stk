"""Source nodes stk.source.*@1, called directly with a minimal NodeContext (the evaluator is tested elsewhere)."""
from pathlib import Path
import hashlib
import io
import json
import os

import pytest

np = pytest.importorskip("numpy")

from mupro_fake import write_case, write_outputs  # noqa: E402
from suan.connectors.files import LocalFiles  # noqa: E402
from suan.data.dat import write_dat  # noqa: E402
from suan.graph import registry as graph_registry  # noqa: E402
from suan.graph.nodes import sources  # noqa: E402
from suan.graph.registry import (Budget, CancelToken, GraphError, NodeContext, NodeExecutionError,  # noqa: E402
                                 Registry)

ROOT = Path(__file__).resolve().parents[1]
SOURCE_NODES = {"muferro_run": "stk.source.muferro_run@1", "muferro_frame": "stk.source.muferro_frame@1",
                "file_source": "stk.source.file@1", "table_source": "stk.source.table@1",
                "lammps_log": "stk.source.lammps_log@1", "mupro_hdf5_source": "stk.source.mupro_hdf5@1",
                "mupro_hdf5_fields": "stk.source.mupro_hdf5_fields@1"}


class Context:
    """The subset of NodeContext a source node uses."""

    def __init__(self, bindings, node_type, node_id="node"):
        self.bindings = bindings
        self.node_id = node_id
        self.node_type = node_type
        self.budget = Budget()
        self.cancel = CancelToken()
        self.parameters = {}
        self.cache_dir = None
        self.data_key = "0" * 64
        self.choices = {}
        self.warnings = []
        self.checks = 0
        self.source_fingerprint = None

    def resolve(self, binding):
        if binding not in self.bindings:
            raise GraphError("unknown_binding", f"No binding {binding!r}")
        return LocalFiles(self.bindings[binding])

    def check(self):
        self.checks += 1
        self.cancel.raise_if_cancelled()

    def progress(self, fraction=None, message=""):
        pass

    def warn(self, message, *, code="node_warning", **details):
        self.warnings.append(code)

    def report_choices(self, param, choices, *, value=None):
        self.choices[param] = {"choices": list(choices), "value": value}

    def cached(self, name, compute, *, disk=False):
        return compute()


def call(function, bindings, params, inputs=None):
    node_type = function.stk_node_type
    ctx = Context(bindings, node_type)
    normalized = node_type.normalize_params(params)
    fingerprint = node_type.fingerprint(ctx, inputs or {}, normalized)
    json.dumps(fingerprint)
    ctx.source_fingerprint = json.loads(json.dumps(fingerprint))
    result = node_type.wrap_outputs(function(ctx, inputs or {}, normalized))
    return result, ctx, fingerprint


def test_declarations_match_the_frozen_catalog():
    registry = Registry()
    registry.register(sources)
    assert sorted(registry.types()) == sorted(SOURCE_NODES.values())
    catalog = json.loads((ROOT / "docs/specs/catalog/stk-catalog-m1.json").read_text(encoding="utf-8"))
    frozen = {entry["id"]: entry for entry in catalog["nodes"]}
    for node_type in registry:
        exported = node_type.to_json(include_impl=False)
        assert exported == {k: v for k, v in frozen[node_type.id].items() if k != "impl"}, node_type.id
        assert node_type.fingerprint is not None and node_type.impl.__module__ == "suan.graph.nodes.sources"
    assert isinstance(Context({}, None), NodeContext)
    assert graph_registry.Registry().register(sources)  # importable without a node package __init__


def run_dir(root, **kw):
    write_case(root, grid=(4, 3, 2), steps=4, interval=2)
    write_outputs(root, grid=(4, 3, 2), steps=4, interval=2, **kw)
    return root


def test_muferro_run_and_frame(tmp_path):
    run_dir(tmp_path)
    outputs, ctx, fingerprint = call(sources.muferro_run, {"run": tmp_path}, {"binding": "run"})
    frames = outputs["frames"]
    assert frames.kinds() == {"table", "frames"} and frames.attrs == {"binding": "run", "case_dir": ".",
                                                                      "complete": True}
    assert frames.columns == ["dataset", "step", "time", "path", "size", "sha256", "reader", "components"]
    polar = [i for i in range(frames.n_rows) if frames.column("dataset")[i] == "Polar"]
    assert frames.column("step")[polar].tolist() == [0, 2, 4] and np.isnan(frames.column("time")).all()
    assert frames.column("components")[polar].tolist() == [3, 3, 3] and frames.column("sha256")[0] == ""
    assert outputs["energy"].column("step").tolist() == [1, 2, 3, 4]
    assert outputs["progress"].n_rows == 4 and outputs["result"]["schema"] == "stk.result/1"
    assert [path for path, *_ in fingerprint["frames"]][:1] == ["Charges.00000001.dat"]
    assert all(len(entry) == 3 for entry in fingerprint["frames"])  # path, size, mtime
    assert set(fingerprint["sha256"]) == {"energy_out.dat", "mupro_progress.jsonl", "mupro_completion.json",
                                          "input.toml", "material.toml"}  # the case and its includes
    assert fingerprint["case_dir"] == "."  # "auto" (the default) without a launcher record
    assert ctx.warnings == []
    # Frame reader: latest by default, choices reported, fingerprint = the frame file content.
    image, ctx, fingerprint = call(sources.muferro_frame, {"run": tmp_path}, {}, {"frames": frames})
    image = image["out"]
    assert ctx.choices["step"] == {"choices": [0, 2, 4], "value": 4} and ctx.checks >= 1
    assert image.id == "Polar" and image.time.step == 4 and image.kinds() == {"image"}
    assert fingerprint["path"] == "Polar.00000004.dat" and fingerprint["reader"] == "mupro.dat@1"
    assert fingerprint["sha256"] == LocalFiles(tmp_path).sha256("Polar.00000004.dat")
    field = image.field("Polar")
    assert field.tensor == "vector" and field.quantity == "polarization" and field.unit == "unspecified"
    assert image.array("Polar")[0, 0, 0].tolist() == [1 + 10 + 100 + 1000 * c + 4 for c in (1, 2, 3)]
    assert image.provenance.used[0]["path"] == "Polar.00000004.dat"
    same, _, same_print = call(sources.muferro_frame, {"run": tmp_path}, {"step": 3}, {"frames": frames})
    assert same["out"].time.step == 2 and same_print["path"] == "Polar.00000002.dat"
    strain, _, _ = call(sources.muferro_frame, {"run": tmp_path},
                        {"dataset": "Strain", "step": "first", "precision": "float32", "spacing": [2, 2, 2],
                         "unit": "1", "quantity": "strain", "length_unit": "nm"}, {"frames": frames})
    strain = strain["out"]
    assert strain.field("Strain").components == 6 and strain.field("Strain").tensor == "array"
    assert strain.field("Strain").lossy and strain.spacing == (2.0, 2.0, 2.0) and strain.length_unit == "nm"
    assert strain.field("Strain").unit == "1" and strain.time.step == 1
    with pytest.raises(NodeExecutionError) as error:
        call(sources.muferro_frame, {"run": tmp_path}, {"step": 3, "policy": "exact"}, {"frames": frames})
    assert error.value.code == "frame_not_found"
    with pytest.raises(NodeExecutionError) as error:
        call(sources.muferro_frame, {"run": tmp_path}, {"dataset": "Nope"}, {"frames": frames})
    assert error.value.code == "frame_not_found"
    with pytest.raises(GraphError) as error:
        call(sources.muferro_run, {}, {"binding": "run"})
    assert error.value.code == "unknown_binding"


def test_muferro_run_live_and_in_a_case_directory(tmp_path):
    case = tmp_path / "case16"
    write_case(case, grid=(4, 3, 2), steps=4, interval=2)
    outputs, ctx, _ = call(sources.muferro_run, {"run": tmp_path}, {"binding": "run", "case_dir": "case16"})
    assert outputs["frames"].n_rows == 0 and not outputs["frames"].attrs["complete"]
    assert outputs["energy"].n_rows == 0 and "empty_result" in ctx.warnings
    write_outputs(case, grid=(4, 3, 2), steps=4, interval=2, mode="missing_frame")
    outputs, _, fingerprint = call(sources.muferro_run, {"run": tmp_path}, {"binding": "run", "case_dir": "case16"})
    assert not outputs["frames"].attrs["complete"] and outputs["frames"].column("path")[0].startswith("case16/")
    assert "case16/energy_out.dat" in fingerprint["sha256"]


def test_file_source(tmp_path):
    data = np.arange(4 * 3 * 2 * 3, dtype=float).reshape(4, 3, 2, 3)
    write_dat(tmp_path / "Polar.00000010.dat", data)
    np.save(tmp_path / "scalar.npy", data[..., 0])
    image, _, fingerprint = call(sources.file_source, {"b": tmp_path}, {"binding": "b", "path": "Polar.00000010.dat"})
    image = image["out"]
    assert fingerprint == {"path": "Polar.00000010.dat", "sha256": LocalFiles(tmp_path).sha256("Polar.00000010.dat"),
                           "format": "dat"}
    np.testing.assert_array_equal(image.xyz("Polar"), data)
    assert image.time.step == 10 and image.length_unit == "grid_index"
    assert image.provenance.agent["reader"] == "mupro.dat@1"
    image, _, _ = call(sources.file_source, {"b": tmp_path},
                       {"binding": "b", "path": "scalar.npy", "spacing": [0.5, 0.5, 1], "origin": [1, 2, 3],
                        "length_unit": "nm", "unit": "K", "quantity": "temperature", "step": 7})
    image = image["out"]
    assert image.spacing == (0.5, 0.5, 1.0) and image.origin == (1.0, 2.0, 3.0) and image.length_unit == "nm"
    assert image.field("scalar").unit == "K" and image.field("scalar").quantity == "temperature"
    assert image.time.step == 7
    with pytest.raises(NodeExecutionError) as error:
        call(sources.file_source, {"b": tmp_path}, {"binding": "b", "path": "missing.npy"})
    assert error.value.code == "missing_file"
    with pytest.raises(NodeExecutionError) as error:
        call(sources.file_source, {"b": tmp_path}, {"binding": "b", "path": "Polar.00000010.dat", "fields": ["x"]})
    assert error.value.code == "invalid_param"
    (tmp_path / "bad.dat").write_text("kt: 1 energy: 1\n")
    with pytest.raises(NodeExecutionError) as error:
        call(sources.file_source, {"b": tmp_path}, {"binding": "b", "path": "bad.dat"})
    assert error.value.code == "invalid_data"


def _npy_field(value):
    stream = io.BytesIO()
    np.save(stream, np.full((2, 2, 2), value, dtype=np.int16))
    return stream.getvalue()


def _file_graph(resolver, cache, on_event=None, path="field.npy"):
    from suan.graph.catalog import default_registry
    from suan.graph.evaluator import evaluate

    graph = {"schema": "stk.graph/1", "nodes": [
        {"id": "source", "type": "stk.source.file@1", "params": {"binding": "data", "path": path}},
    ], "outputs": {"out": "source.out"}}
    return evaluate(graph, registry=default_registry(), resolver=resolver, cache=cache, on_event=on_event)


def _rewrite_field(path, data, *, preserve_mtime=True):
    stamp = path.stat()
    path.write_bytes(data)
    mtime = stamp.st_mtime_ns if preserve_mtime else stamp.st_mtime_ns + 1_000_000_000
    os.utime(path, ns=(stamp.st_atime_ns, mtime))
    assert path.stat().st_size == stamp.st_size


def test_file_source_cache_tracks_local_bytes_with_unchanged_metadata(tmp_path):
    from suan.graph.cache import GraphCache
    from suan.graph.resolve import LocalDirResolver

    path = tmp_path / "field.npy"
    path.write_bytes(_npy_field(3))
    cache = GraphCache(tmp_path / "graph-cache")
    first = _file_graph(LocalDirResolver({"data": tmp_path}), cache)
    changed = _npy_field(9)
    _rewrite_field(path, changed)
    second = _file_graph(LocalDirResolver({"data": tmp_path}), cache)
    image = second.outputs["out"]
    assert second.keys != first.keys and second.evaluated == ["source"]
    assert np.all(image.array("field") == 9)
    assert image.provenance.used[0]["sha256"] == hashlib.sha256(changed).hexdigest()


@pytest.mark.parametrize("source_kind", ["local", "local_same_mtime", "runtime"])
def test_file_source_drift_never_publishes_an_old_disk_cache_key(tmp_path, source_kind):
    from test_connectors_files import FakeClient
    from suan.graph.cache import GraphCache
    from suan.graph.evaluator import EvaluationFailed
    from suan.graph.resolve import LocalDirResolver, RuntimeResolver

    original = _npy_field(3)
    path = tmp_path / "field.npy"
    if source_kind == "runtime":
        client = FakeClient({"field.npy": original})
        resolver = RuntimeResolver(client, tmp_path / "downloads").bind({"data": {"task_id": "a" * 32}})
        path = resolver.resolve("data").fetch("field.npy")
    else:
        path.write_bytes(original)
        resolver = LocalDirResolver({"data": tmp_path})
    before = _file_graph(resolver, GraphCache())
    disk = tmp_path / "graph-cache"

    def rewrite(event):
        if event["type"] == "node.started":
            _rewrite_field(path, _npy_field(9), preserve_mtime=source_kind != "local")

    with pytest.raises(EvaluationFailed) as failure:
        _file_graph(resolver, GraphCache(disk), rewrite)
    assert failure.value.errors[0]["code"] == "invalid_data"
    _rewrite_field(path, original)
    restored = _file_graph(resolver, GraphCache(disk, memory_bytes=0))
    assert restored.keys == before.keys and restored.evaluated == ["source"]
    assert np.all(restored.outputs["out"].array("field") == 3)
    assert _file_graph(resolver, GraphCache(disk, memory_bytes=0)).evaluated == []


@pytest.mark.parametrize("storage", ["soft_link", "same_file_virtual"])
def test_file_source_vtkhdf_uses_the_same_logical_id_for_local_and_runtime(tmp_path, storage):
    from test_connectors_files import FakeClient
    from suan.data.model import ImageData
    from suan.data.vtkhdf import write_vtkhdf
    from suan.graph.cache import GraphCache
    from suan.graph.resolve import LocalDirResolver, RuntimeResolver

    h5py = pytest.importorskip("h5py")
    path = tmp_path / "logical.field.vtkhdf"
    image = ImageData((2, 2, 2), id="described")
    image.add_field("field", np.full((2, 2, 2), 3.0))
    write_vtkhdf(path, image)
    with h5py.File(path, "r+") as handle:
        del handle["STK"]
        fields = handle["VTKHDF/PointData"]
        fields.move("field", "/internal")
        if storage == "soft_link":
            fields["field"] = h5py.SoftLink("/internal")
        else:
            target = handle["internal"]
            layout = h5py.VirtualLayout(shape=target.shape, dtype=target.dtype)
            layout[:] = h5py.VirtualSource(".", "/internal", shape=target.shape)
            fields.create_virtual_dataset("field", layout)

    local = LocalDirResolver({"data": tmp_path})
    client = FakeClient({path.name: path.read_bytes()})
    runtime = RuntimeResolver(client, tmp_path / "downloads").bind({"data": {"task_id": "a" * 32}})
    for resolver in (local, runtime):
        result = _file_graph(resolver, GraphCache(), path=path.name).outputs["out"]
        assert result.id == "logical" and np.all(result.array("field") == 3)
        assert result.provenance.used[0]["path"] == path.name


@pytest.mark.parametrize("kind", ["vti", "vtk"])
def test_file_source_preserves_named_vtk_reader_metadata(tmp_path, kind):
    from suan.data.model import ImageData
    from suan.data.vtkconv import image_to_vtk
    from suan.graph.cache import GraphCache
    from suan.graph.resolve import LocalDirResolver

    vtk = pytest.importorskip("vtk")
    name = f"logical.{kind}"
    image = ImageData((2, 2, 2), spacing=(1.0, 2.0, 3.0), length_unit="nm")
    image.add_field("field", np.full((2, 2, 2), 3.0), unit="K")
    vtk_image = image_to_vtk(image)
    for key, value in (("STK_units", "K"), ("STK_coordinate_units", "nm")):
        annotation = vtk.vtkStringArray()
        annotation.SetName(key)
        annotation.InsertNextValue(value)
        vtk_image.GetFieldData().AddArray(annotation)
    writer = vtk.vtkXMLImageDataWriter() if kind == "vti" else vtk.vtkStructuredPointsWriter()
    writer.SetFileName(str(tmp_path / name))
    writer.SetInputData(vtk_image)
    assert writer.Write()

    resolver = LocalDirResolver({"data": tmp_path})
    result = _file_graph(resolver, GraphCache(), path=name).outputs["out"]
    assert result.id == "logical" and result.spacing == image.spacing and result.length_unit == "nm"
    assert result.field("field").unit == "K" and np.all(result.array("field") == 3)


@pytest.mark.parametrize("storage", ["link", "virtual", "raw"])
def test_file_source_rejects_vtkhdf_storage_outside_the_verified_file(tmp_path, storage):
    from suan.connectors.builtin import read_file
    from suan.data.model import ImageData
    from suan.data.vtkhdf import write_vtkhdf
    from suan.graph.cache import GraphCache
    from suan.graph.evaluator import EvaluationFailed
    from suan.graph.resolve import LocalDirResolver

    h5py = pytest.importorskip("h5py")
    path = tmp_path / "field.vtkhdf"
    sidecar = tmp_path / "sidecar"
    values = np.full((2, 2, 2), 3.0)
    image = ImageData((2, 2, 2), id="field")
    image.add_field("field", values)
    write_vtkhdf(path, image)
    if storage != "raw":
        with h5py.File(sidecar, "w") as handle:
            handle["field"] = values
    with h5py.File(path, "r+") as handle:
        fields = handle["VTKHDF/PointData"]
        del fields["field"]
        if storage == "link":
            fields["field"] = h5py.ExternalLink(str(sidecar), "/field")
        elif storage == "virtual":
            layout = h5py.VirtualLayout(shape=values.shape, dtype=values.dtype)
            layout[:] = h5py.VirtualSource(str(sidecar), "/field", shape=values.shape)
            fields.create_virtual_dataset("field", layout)
        else:
            fields.create_dataset("field", data=values, external=[(str(sidecar), 0, values.nbytes)])

    assert np.all(read_file(LocalFiles(tmp_path), path.name).array("field") == 3)
    resolver = LocalDirResolver({"data": tmp_path})
    with pytest.raises(EvaluationFailed) as failure:
        _file_graph(resolver, GraphCache(), path=path.name)
    assert failure.value.errors[0]["code"] == "invalid_data"
    assert not failure.value.partial.outputs


def test_table_source(tmp_path):
    run_dir(tmp_path)
    (tmp_path / "loss.csv").write_text("epoch,loss\n1,0.5\n2,0.25\n")
    table, _, fingerprint = call(sources.table_source, {"r": tmp_path}, {"binding": "r", "path": "energy_out.dat"})
    table = table["out"]
    assert table.id == "energy" and table.columns[0] == "step" and table.field("Total Energy").unit == "normalized"
    assert fingerprint["format"] == "auto" and len(fingerprint["sha256"]) == 64
    assert table.provenance.agent["reader"] == "mupro.energy@1"
    table, _, _ = call(sources.table_source, {"r": tmp_path},
                       {"binding": "r", "path": "energy_out.dat", "columns": ["step", "Total Energy"],
                        "units": {"Total Energy": "eV"}})
    assert table["out"].columns == ["step", "Total Energy"] and table["out"].field("Total Energy").unit == "eV"
    progress, _, _ = call(sources.table_source, {"r": tmp_path}, {"binding": "r", "path": "mupro_progress.jsonl"})
    assert progress["out"].columns == ["step", "completed_steps", "total_steps"]
    csv, _, _ = call(sources.table_source, {"r": tmp_path}, {"binding": "r", "path": "loss.csv",
                                                             "units": {"loss": "1"}})
    assert csv["out"].column("loss").tolist() == [0.5, 0.25] and csv["out"].field("loss").unit == "1"
    (tmp_path / "kt.dat").write_text("# temperature sweep\nT  P\n300 0.5\n310 0.4\n")
    columns, _, _ = call(sources.table_source, {"r": tmp_path}, {"binding": "r", "path": "kt.dat"})
    assert columns["out"].columns == ["T", "P"] and columns["out"].column("T").tolist() == [300, 310]
    with pytest.raises(NodeExecutionError) as error:
        call(sources.table_source, {"r": tmp_path}, {"binding": "r", "path": "Polar.00000000.dat", "format": "columns"})
    assert error.value.code == "invalid_data"
    with pytest.raises(NodeExecutionError) as error:
        call(sources.table_source, {"r": tmp_path}, {"binding": "r", "path": "loss.csv", "columns": ["nope"]})
    assert error.value.code == "invalid_param"
