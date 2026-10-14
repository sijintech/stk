"""Independent numerical checks on frozen public PET study artifacts, offline."""
from collections import defaultdict
import csv
import hashlib
import io
import json
import math
from pathlib import Path

from suan.lammps.structure import index_dump, read_data, read_dump_frame


def _raw(project, source, name):
    item = project.snapshots.resolve(source["snapshot_id"], source["files"][name])
    raw = Path(item["path"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == item["sha256"]
    return raw, item


def _blocks(text):
    """Small independent parser of the exact one-line thermo format used here."""
    columns, rows, blocks = None, [], []
    for line in text.splitlines():
        words = line.split()
        if words[:1] == ["Step"] and "Temp" in words and "Density" in words:
            columns, rows = words, []
        elif columns and line.startswith("Loop time of"):
            assert rows
            blocks.append((columns, rows))
            columns = None
        elif columns and len(words) == len(columns):
            try:
                numbers = [float(word) for word in words]
            except ValueError:
                continue
            assert all(math.isfinite(value) for value in numbers)
            rows.append(numbers)
    assert blocks
    return blocks


def _last_block(text):
    return _blocks(text)[-1]


def verify_saved_evidence(project, study, *, lammps):
    """Check all state ancestors, density arithmetic and gas COM MSD identity.

    These checks establish data lineage and numerical/unit implementation. They
    do not assert equilibration, a positive fit, or a material property value.
    """
    assert study["complete"]
    recipe = study["recipe"]
    sources = {key: stage["tasks"][0]["produced"] for key, stage in study["stages"].items()
               if not key.startswith("analysis:")}
    order = ["relax", *(f"property:tg:{i}" for i in range(len(recipe["tg"]["temperatures"])))]
    parents = {key: ("model" if index == 0 else order[index - 1]) for index, key in enumerate(order)}
    for kind in ("modulus", "diffusion"):
        parents["property:" + kind] = "property:tg:" + str(recipe["tg"]["temperatures"].index(recipe[kind]["temperature"]))
    for key, parent in parents.items():
        raw, _ = _raw(project, sources[key], "case/input-state.data")
        previous, _ = _raw(project, sources[parent], "pet.data" if parent == "model" else "case/state.data")
        assert raw == previous, (key, parent)
        receipt_raw, _ = _raw(project, sources[key], "case/pet-stage.json")
        receipt = json.loads(receipt_raw)
        assert receipt["stage"] == key and receipt["study_id"] == study["study_id"]
        assert receipt["source_snapshot_id"] == sources[parent]["snapshot_id"]
        assert receipt["source_files"] == sources[parent]["files"]
        assert receipt["input_state_sha256"] == hashlib.sha256(previous).hexdigest()
    series = study["objects"]["tg_inputs"]
    raw, _ = _raw(project, series, "tg-series.json")
    receipt = json.loads(raw)
    raw, _ = _raw(project, series, "density-temperature.csv")
    csv_rows = list(csv.DictReader(io.StringIO(raw.decode())))
    assert len(csv_rows) == len(receipt["logs"]) == len(recipe["tg"]["temperatures"])
    for index, (row, record) in enumerate(zip(csv_rows, receipt["logs"])):
        source = sources[f"property:tg:{index}"]
        original, _ = _raw(project, source, "case/log.lammps")
        gathered, _ = _raw(project, series, record["path"])
        assert original == gathered
        assert record["simulation_run_id"] == source["simulation_run_id"]
        assert record["snapshot_id"] == source["snapshot_id"]
        assert record["record_id"] == source["files"]["case/log.lammps"]
        assert record["sha256"] == hashlib.sha256(original).hexdigest()
        columns, points = _last_block(original.decode())
        tail = points[len(points) // 2:]
        for name, field in (("Temp", "Temperature"), ("Density", "Density")):
            mean = math.fsum(point[columns.index(name)] for point in tail) / len(tail)
            assert math.isclose(float(row[field]), mean, rel_tol=1e-12, abs_tol=1e-12)
        assert int(row["Samples"]) == len(tail) and row["Source"] == record["path"]
    assert recipe["diffusion"]["group"] == "o2_com"
    source = sources["property:diffusion"]
    gas_raw, _ = _raw(project, source, "case/gas-model.json")
    gas = json.loads(gas_raw)
    parent_log, _ = _raw(project, sources[parents["property:diffusion"]], "case/log.lammps")
    parent_columns, parent_rows = _last_block(parent_log.decode())
    source_temperature = parent_rows[-1][parent_columns.index("Temp")]
    gas_log, _ = _raw(project, source, "case/log.lammps")
    gas_columns, gas_rows = _blocks(gas_log.decode())[0]
    initial_temperature = gas_rows[0][gas_columns.index("Temp")]
    # This public small-tracer acceptance must retain the saved hot PET state.
    # FIRE minimization previously zeroed all PET velocities, leaving only the
    # four newly initialized gas sites hot (3.29 K for the whole 550-atom cell).
    # The new gas contributes <1% of the kinetic degrees of freedom here.
    assert gas["gas_count"] == 2 and len(read_data(_raw(project, source, "case/input-state.data")[1]["path"]).atoms) >= 500
    assert .95 * source_temperature <= initial_temperature <= 1.05 * source_temperature
    _, topology_item = _raw(project, source, "case/state.data")
    topology = read_data(topology_item["path"])
    # Automatic final-state snapshots deliberately exclude dump files. Inspect
    # the bounded trajectory through the existing hash-verified collection.
    viewed = lammps.view(source["simulation_run_id"], project=project)
    path = Path(viewed["directory"]) / "trajectory.dump"
    suffix = f"results/lammps/{source['simulation_run_id']}/case/trajectory.dump"
    entry = next(item for item in viewed["files"] if item["path"] == suffix)
    assert path.stat().st_size <= 128 * 1024 * 1024
    assert hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"]
    indexed = index_dump(path, topology)
    assert indexed.sha256 == entry["sha256"]
    first = read_dump_frame(path, topology, frame="first", index=indexed)
    assert first.step == 0 and first.has_unwrapped
    assert topology.masses[gas["atom_type"]] == 15.9994

    def com(frame):
        groups = defaultdict(list)
        for atom in frame.atoms:
            if atom.type == gas["atom_type"]:
                assert atom.charge == 0 and atom.molecule >= gas["molecule_id_lower_bound"]
                groups[atom.molecule].append(atom.position)
        assert len(groups) == gas["gas_count"] and all(len(points) == 2 for points in groups.values())
        # Both sites have exactly the same O mass; their mean is the molecular COM.
        return {identity: tuple(math.fsum(point[axis] for point in points) / 2 for axis in range(3))
                for identity, points in groups.items()}

    initial = com(first)
    raw, _ = _raw(project, source, "case/msd.dat")
    samples = {}
    for line in raw.decode().splitlines():
        words = line.split()
        if not words or words[0].startswith("#") or words[0] == "Step":
            continue
        assert len(words) == 3
        step, elapsed, msd = map(float, words)
        assert all(math.isfinite(value) for value in (step, elapsed, msd)) and msd >= 0
        assert step.is_integer() and math.isclose(elapsed, step * recipe["diffusion"]["timestep"], rel_tol=1e-12)
        assert int(step) not in samples
        samples[int(step)] = msd
    checked, max_error = 0, 0.
    for entry in indexed.frames[1:]:
        if entry.step not in samples:
            continue
        frame = read_dump_frame(path, topology, frame=entry.step, index=indexed)
        assert frame.has_unwrapped
        current = com(frame)
        expected = math.fsum(math.fsum((current[identity][axis] - origin[axis]) ** 2 for axis in range(3))
                             for identity, origin in initial.items()) / len(initial)
        error = abs(samples[entry.step] - expected)
        # LAMMPS custom dumps and ave/time use rounded textual values. This bound
        # allows that precision while rejecting atom/whole-system MSD or unit mistakes.
        assert error <= max(.002, 2e-4 * abs(expected)), (entry.step, samples[entry.step], expected)
        checked += 1
        max_error = max(max_error, error)
    assert checked >= 3
    return {"frozen_handoffs": len(parents), "density_points": len(csv_rows),
            "gas_com_samples_checked": checked, "max_msd_rounding_error_A2": max_error,
            "gas_source_temperature_K": source_temperature, "gas_initial_temperature_K": initial_temperature,
            "physical_convergence": False}
