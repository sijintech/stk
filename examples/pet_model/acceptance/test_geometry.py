"""Manual RDKit fallback and seed replay; initial geometry is not MD equilibrium."""
from collections import Counter

import numpy as np

from suan.lammps.pet_worker import _chain


def test_failed_standard_embedding_has_a_deterministic_random_coordinate_fallback():
    first, audit = _chain(8, 42)
    second, replay = _chain(8, 42)
    assert first.n_particles == second.n_particles == 179
    assert Counter(atom.name for atom in first.particles()) == {"C": 80, "H": 66, "O": 33}
    assert audit["embedding_attempts"][0]["return_code"] == -1
    assert audit["embedding_attempts"][1]["return_code"] == 0
    assert audit["embedding_attempts"][1]["use_random_coordinates"]
    assert np.isfinite(first.xyz).all() and np.array_equal(first.xyz, second.xyz)
    assert audit["coordinate_sha256"] == replay["coordinate_sha256"]
    assert audit["uff_status"] in (0, 1)  # 1 is explicitly not converged.
