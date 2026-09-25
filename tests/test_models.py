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
