"""Molecule files through registry, frame selection, caches and payload/2 delivery."""
import hashlib
import json
import subprocess
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from suan.graph.cache import GraphCache
from suan.graph.catalog import build_registry, load_preset
from suan.graph.evaluator import EvaluationFailed, evaluate
from suan.graph.nodes import lammps_structure, molecule_render
from suan.graph.registry import CancelToken, Cancelled, NodeExecutionError
from suan.graph.resolve import LocalDirResolver
from suan.graph.service import MemoryBlobSink, evaluate_request
from suan.render.payload import decode
from test_lammps_structure import DATA, dump_frame
from test_desktop_bridge import bridge_env  # noqa: F401
from test_desktop_scripts import scripts, execute  # noqa: F401


@pytest.fixture
def molecule(tmp_path):
    folder = tmp_path / "molecule"
    folder.mkdir()
    (folder / "state.data").write_bytes(DATA.encode())
    # Atom 40 is near 10, but the data file has exactly bonds 10--20 and 20--30.
    first = [(40, 2, 3, .2, 1, 1.05, 1), (30, 1, 2, -.4, 3, 1, 1),
             (10, 1, 1, .1, 1, 1, 1), (20, 1, 1, .1, 2, 1, 1)]
    latest = [(identity, mol, kind, charge, x + 10, y, z) for identity, mol, kind, charge, x, y, z in first]
    (folder / "trajectory.dump").write_bytes((dump_frame(5, rows=first) + dump_frame(20, rows=latest)).encode())
    return folder


def run(folder, *, cache=None, params=None):
    return evaluate(load_preset("lammps-molecule"), registry=build_registry(entry_points=False),
                    resolver=LocalDirResolver({"data": folder}), cache=cache,
                    parameters={"trajectory": "trajectory.dump", **(params or {})})


def test_complete_molecular_view_retains_identity_original_values_and_real_bonds(molecule):
    result = run(molecule)
    assert result.parameters["step"] == {"value": 20, "choices": [5, 20]}
    scene = result.outputs["view"]
    layers = {layer.id: layer for layer in scene.layers}
    atoms, bonds, box = (layers[name] for name in ("atoms", "bonds", "box"))
    assert atoms.type == "points" and atoms.appearance["render_as"] == "spheres"
    assert atoms.appearance["radius"] == .3 and atoms.props["length_unit"] == "angstrom"
    assert "pick" not in atoms.props and atoms.grid is None
    np.testing.assert_array_equal(atoms.attributes["atom_id"].values, [10, 20, 30, 40])
    np.testing.assert_array_equal(atoms.attributes["molecule_id"].values, [1, 1, 1, 2])
    np.testing.assert_array_equal(atoms.attributes["atom_type"].values, [1, 1, 2, 3])
    np.testing.assert_array_equal(atoms.attributes["charge"].values, [.1, .1, -.4, .2])
    np.testing.assert_allclose(atoms.geometry["positions"], [[1, 1, 1], [2, 1, 1], [3, 1, 1], [1, 1.05, 1]])
    np.testing.assert_allclose(atoms.attributes["source_position"].values,
                               [[11, 1, 1], [12, 1, 1], [13, 1, 1], [11, 1.05, 1]])
    assert atoms.attributes["charge"].values.dtype == np.float64
    assert atoms.attributes["source_position"].values.dtype == np.float64
    assert bonds.type == "lines" and len(bonds.geometry["indices"]) == 2
    np.testing.assert_array_equal(bonds.attributes["bond_id"].values, [7, 8])
    np.testing.assert_array_equal(bonds.attributes["atom_a"].values, [10, 20])
    np.testing.assert_array_equal(bonds.attributes["atom_b"].values, [20, 30])
    assert len(box.geometry["indices"]) == 12
    assert box.bounds() == [[0, 0, 0], [10, 10, 10]]
    diagnostics = result.outputs["diagnostics"]
    assert diagnostics["atoms"] == 4 and diagnostics["bonds"] == 2 and not diagnostics["bonds_inferred"]
    assert diagnostics["coordinate_mode"] == "unwrapped"
    assert diagnostics["units"] == "real" and diagnostics["units_source"] == "caller_declared"
    assert diagnostics["source"]["used"] == [
        {"path": name, "sha256": hashlib.sha256((molecule / name).read_bytes()).hexdigest(), "role": "input"}
        for name in ("state.data", "trajectory.dump")]
    assert [category.name for category in atoms.attributes["atom_type"].categories] == ["C", "O", "H"]


def test_payload_delivery_has_sphere_points_real_lines_and_no_volume_probe(molecule, tmp_path):
    sink = MemoryBlobSink()
    result = evaluate_request({"preset": "lammps-molecule", "parameters": {"trajectory": "trajectory.dump"}},
        registry=build_registry(entry_points=False), resolver=LocalDirResolver({"data": molecule}),
        cache_dir=tmp_path / "cache", blob_sink=sink)
    assert not result.get("errors"), result
    assert result["outputs"]["view"]["type"] == "payload"
    payload = decode(result["outputs"]["view"]["manifest"], sink.blobs)
    layers = {layer["id"]: layer for layer in payload.manifest["layers"]}
    assert layers["atoms"]["appearance"]["render_as"] == "spheres"
    assert layers["atoms"]["appearance"]["radius"] == .3
    assert "pick" not in layers["atoms"] and "grid" not in layers["atoms"]
    assert layers["bonds"]["mode"] == "segments" and layers["box"]["mode"] == "segments"
    ids = payload.array(layers["atoms"]["attributes"]["atom_id"]["accessor"])
    np.testing.assert_array_equal(ids.reshape(-1), [10, 20, 30, 40])
    colouring = layers["atoms"]["appearance"]["color"]
    assert colouring["by"] == "attribute" and colouring["attribute"] == "atom_type"
    assert colouring["interpolate"] == "nearest"
    descriptor = layers["atoms"]["attributes"]["atom_type"]
    assert descriptor["categorical"] and descriptor["association"] == "point"
    np.testing.assert_array_equal(payload.array(descriptor["accessor"]).reshape(-1), [1, 1, 2, 3])
    palette = next(entry for entry in payload.manifest["colormaps"] if entry["id"] == descriptor["palette"])
    assert colouring["colormap"] == palette["id"]
    assert [entry["name"] for entry in palette["entries"]] == ["C", "O", "H"]
    assert len({tuple(entry["color"]) for entry in palette["entries"]}) == 3
    assert result["parameters"]["step"] == {"value": 20, "choices": [5, 20]}
    json.dumps(result, allow_nan=False)


def test_revisit_and_appearance_change_reuse_geometry_and_new_bytes_invalidate(molecule):
    cache = GraphCache()
    first = run(molecule, cache=cache)
    earlier = run(molecule, cache=cache, params={"step": 5})
    assert "molecule" in earlier.evaluated
    assert earlier.parameters["step"]["value"] == 5
    alias = run(molecule, cache=cache, params={"step": "first"})
    assert "molecule" not in alias.evaluated
    assert alias.keys["molecule"] == earlier.keys["molecule"]
    latest = run(molecule, cache=cache, params={"radius": .6, "view": "+x"})
    assert "molecule" not in latest.evaluated and "atoms" not in latest.evaluated
    assert latest.keys["molecule"] == first.keys["molecule"]
    assert next(layer for layer in latest.outputs["view"].layers if layer.id == "atoms").appearance["radius"] == .6
    with (molecule / "trajectory.dump").open("ab") as stream:
        stream.write(dump_frame(35).encode())
    changed = run(molecule, cache=cache)
    assert changed.parameters["step"] == {"value": 35, "choices": [5, 20, 35]}
    assert changed.keys["molecule"] != first.keys["molecule"]


def test_static_topology_has_unknown_boundary_and_no_fabricated_time(molecule):
    result = run(molecule, params={"trajectory": ""})
    assert result.outputs["diagnostics"]["step"] is None
    assert result.outputs["diagnostics"]["boundary"] == ["unknown"] * 3
    assert result.parameters["step"].get("choices", []) == []
    assert "data file does not record boundary" in result.outputs["diagnostics"]["boundary_note"]
    with pytest.raises(EvaluationFailed, match="static topology"):
        run(molecule, params={"trajectory": "", "step": 0})


def test_unwrapped_view_is_explicit_and_wrapped_only_dump_has_warning(molecule):
    result = run(molecule, params={"wrapped_display": False})
    atoms = next(layer for layer in result.outputs["view"].layers if layer.id == "atoms")
    np.testing.assert_allclose(atoms.geometry["positions"][:, 0], [11, 12, 13, 11])
    (molecule / "trajectory.dump").write_text(dump_frame(0, coordinates="x y z"))
    result = run(molecule)
    assert result.outputs["diagnostics"]["coordinate_mode"] == "wrapped"
    assert any(warning["code"] == "wrapped_coordinates" for warning in result.warnings)


@pytest.mark.parametrize("mutation", ["truncate", "repeat", "unknown_atom", "nonfinite"])
def test_invalid_later_frame_rejects_even_when_first_is_selected(molecule, mutation):
    valid = dump_frame(5)
    bad = dump_frame(20)
    if mutation == "truncate":
        bad = bad[:bad.rfind("20 1 1")]
    elif mutation == "repeat":
        bad = dump_frame(5)
    elif mutation == "unknown_atom":
        bad = bad.replace("40 2 3", "90 2 3")
    else:
        bad = bad.replace("0.2 4 4 4", "nan 4 4 4")
    (molecule / "trajectory.dump").write_text(valid + bad)
    with pytest.raises(EvaluationFailed):
        run(molecule, params={"step": "first"})


@pytest.mark.parametrize("topology,trajectory", [("../state.data", ""), ("/state.data", ""),
    ("state.data", "../trajectory.dump"), ("state.data", "state.data")])
def test_paths_reject_before_resolving_a_binding(topology, trajectory):
    ctx = SimpleNamespace(resolve=lambda _: pytest.fail("invalid paths must not resolve the binding"))
    with pytest.raises(NodeExecutionError, match="relative files"):
        lammps_structure.fingerprint(ctx, {}, {"binding": "data", "topology": topology, "trajectory": trajectory})


def test_index_scan_cancels_and_render_nodes_reject_wrong_inputs(molecule):
    count = 0

    def check():
        nonlocal count
        count += 1
        if count == 15:
            raise Cancelled("fixture cancellation")

    context = SimpleNamespace(resolve=LocalDirResolver({"data": molecule}).resolve, check=check,
        report_choices=lambda *args, **kwargs: None, node_id="molecule")
    with pytest.raises(Cancelled, match="fixture cancellation"):
        lammps_structure.fingerprint(context, {}, {"binding": "data", "topology": "state.data", "trajectory": "trajectory.dump", "step": "latest"})
    from suan.data.model import CellArray, PolyData
    arbitrary = PolyData(np.zeros((3, 3)), lines=CellArray.uniform(np.array([[0, 1, 2]])))
    with pytest.raises(NodeExecutionError, match="original atom_id"):
        molecule_render.atoms_layer(context, {"in": arbitrary}, {})
    with pytest.raises(NodeExecutionError, match="two-point segments"):
        molecule_render.lines_layer(context, {"in": arbitrary}, {})


def test_new_catalog_modules_keep_heavy_imports_lazy():
    result = subprocess.run([sys.executable, "-c", "import sys; from suan.graph.catalog import build_registry; "
        "r=build_registry(entry_points=False); assert 'stk.source.lammps_structure@1' in r; "
        "assert 'stk.source.lammps_density_series@1' in r; assert 'numpy' not in sys.modules; assert 'vtk' not in sys.modules"],
        capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr


def test_real_console_rejects_molecular_position_as_a_volume_probe(scripts, molecule):
    session = scripts.call("script.open")["session"]
    result = execute(scripts, session, f'''
from suan.scripting import ScriptError
for source in ('atoms', 'molecule'):
    try:
        stk.graph.probe({{'node': source}}, preset='lammps-molecule',
            local_bindings={{'data': {str(molecule)!r}}}, position=[1, 1, 1])
    except ScriptError as error:
        assert error.code == 'not_found' and error.data['probe_error']
    else:
        raise AssertionError('a molecule was treated as a volume grid')
''')
    assert result["run"]["state"] == "succeeded", scripts.call("script.read", {"session": session})["text"]
    assert not scripts.violations


def test_latest_and_first_payload_attributes_follow_the_frame_original_values(molecule, tmp_path):
    sink = MemoryBlobSink()
    cache = GraphCache()
    positions = []
    for step in ("latest", "first", 20):
        result = evaluate_request({"preset": "lammps-molecule", "parameters": {
            "trajectory": "trajectory.dump", "step": step, "wrapped_display": False}},
            registry=build_registry(entry_points=False), resolver=LocalDirResolver({"data": molecule}),
            cache_dir=tmp_path / "cache", cache=cache, blob_sink=sink)
        assert not result.get("errors"), result
        payload = decode(result["outputs"]["view"]["manifest"], sink.blobs)
        atoms = next(layer for layer in payload.manifest["layers"] if layer["id"] == "atoms")
        positions.append(payload.array(atoms["attributes"]["source_position"]["accessor"]))
        assert payload.manifest["view"]["time"]["step"] == (5 if step == "first" else 20)
        np.testing.assert_array_equal(payload.array(atoms["attributes"]["atom_id"]["accessor"]).reshape(-1),
                                     [10, 20, 30, 40])
    np.testing.assert_allclose(positions[0][:, 0], [11, 12, 13, 11])
    np.testing.assert_allclose(positions[1][:, 0], [1, 2, 3, 1])
    np.testing.assert_array_equal(positions[0], positions[2])
