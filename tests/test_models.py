"""Client-side TaskSpec contract checks; no runtime server is needed."""

import hashlib
import json

import pytest

from suan.runtime.models import MPI_RESOURCES, TaskSpec, layout

WS = "a" * 32
# Digests computed with the pre-MPI TaskSpec (217bd86).
LEGACY_DIGEST = "17980fc2346444c4bd4ec00326958b2c5dcaeb210609918b6b765ddcec403b7d"
MINIMAL_DIGEST = "9625ff3968a8f09447216257c74b8062468e8765d5fe0c31d2c9a7acacb60d52"


def digest(spec):
    return hashlib.sha256(json.dumps(spec.to_dict(), sort_keys=True).encode()).hexdigest()


def test_legacy_specs_keep_their_idempotency_hash():
    legacy = TaskSpec(WS, ["{python}", "run.py"], backend="slurm", outputs=["out.vtk"],
                      env={"OMP_NUM_THREADS": "4"}, resources={"cpus": 4, "nodes": 2, "walltime_seconds": 60})
    assert legacy.to_dict()["resources"] == {"cpus": 4, "nodes": 2, "walltime_seconds": 60}
    assert not MPI_RESOURCES & set(legacy.to_dict()["resources"])
    assert digest(legacy) == LEGACY_DIGEST
    assert digest(TaskSpec(WS, ["{python}", "-c", "pass"])) == MINIMAL_DIGEST
    # MPI defaults are never written into the spec either.
    assert TaskSpec(WS, ["muFerro"], resources={"ranks": 2}).to_dict()["resources"] == {"ranks": 2}


def test_input_hashes_normalize_paths_and_participate_in_idempotency():
    checked = TaskSpec(WS, ["{python}", "-c", "pass"], inputs=["./input.json"], input_hashes={"./input.json": "a" * 64})
    assert checked.to_dict()["inputs"] == ["input.json"]
    assert checked.to_dict()["input_hashes"] == {"input.json": "a" * 64}
    assert digest(checked) != digest(TaskSpec(WS, checked.argv, inputs=["input.json"]))
    assert "input_hashes" not in TaskSpec(WS, checked.argv, input_hashes=None).to_dict()
    assert TaskSpec(WS, checked.argv, inputs=[], input_hashes={}).to_dict()["input_hashes"] == {}


@pytest.mark.parametrize("inputs,hashes", [
    (None, {}), (["a"], []), (["a"], {}), (["a"], {"a": "a" * 64, "b": "b" * 64}),
    (["a"], {"a": "A" * 64}), (["a"], {"a": "a" * 63}), (["a"], {"a": True}),
    (["a"], {"../a": "a" * 64}), (["a"], {"a": "a" * 64, "./a": "a" * 64}),
])
def test_input_hashes_require_exact_unambiguous_input_coverage(inputs, hashes):
    with pytest.raises(ValueError):
        TaskSpec(WS, ["{python}", "-c", "pass"], inputs=inputs, input_hashes=hashes)


@pytest.mark.parametrize("resources,backend,message", [
    ({"ranks": 4, "cpus": 2}, "local", "not both"),
    ({"threads_per_rank": 2, "cpus": 2}, "local", "not both"),
    ({"ranks": 3, "nodes": 2}, "slurm", "multiple of nodes"),
    ({"threads_per_rank": 2, "nodes": 2}, "slurm", "multiple of nodes"),
    ({"ranks": 0}, "local", "positive integer"),
    ({"threads_per_rank": True}, "local", "positive integer"),
    ({"ranks": "2"}, "local", "positive integer"),
    ({"ranks": 2, "nodes": 2}, "local", "Local tasks"),
    ({"ranks_per_node": 2}, "slurm", "Unknown resource option"),
])
def test_invalid_mpi_layouts(resources, backend, message):
    with pytest.raises(ValueError, match=message):
        TaskSpec(WS, ["mpiexec", "-n", "{ranks}", "muFerro"], backend=backend, resources=resources)


def test_layout_defaults():
    assert layout({}) == {"mpi": False, "nodes": 1, "ranks": 1, "ranks_per_node": 1,
                          "threads_per_rank": 1, "cpus_per_node": 1}
    assert layout({"cpus": 6, "nodes": 2}) == {"mpi": False, "nodes": 2, "ranks": 1, "ranks_per_node": 1,
                                               "threads_per_rank": 6, "cpus_per_node": 6}
    assert layout({"ranks": 4}) == {"mpi": True, "nodes": 1, "ranks": 4, "ranks_per_node": 4,
                                    "threads_per_rank": 1, "cpus_per_node": 4}
    assert layout({"threads_per_rank": 3}) == {"mpi": True, "nodes": 1, "ranks": 1, "ranks_per_node": 1,
                                               "threads_per_rank": 3, "cpus_per_node": 3}
    assert layout({"ranks": 8, "nodes": 2, "threads_per_rank": 2}) == {"mpi": True, "nodes": 2, "ranks": 8, "ranks_per_node": 4,
                                                                       "threads_per_rank": 2, "cpus_per_node": 8}
    TaskSpec(WS, ["muFerro"], backend="slurm", resources={"ranks": 8, "nodes": 2, "threads_per_rank": 2})
