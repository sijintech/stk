"""STK's LAMMPS engine support (docs/design/multiscale-engines.md, E1): client TaskSpec builder, input-script
checks, compute-side launcher and ``log.lammps`` verifier. Standard library only; LAMMPS is run as a program."""

from .spec import lammps_spec
from .data import DataError, render_data, write_data

__all__ = ["DataError", "lammps_spec", "render_data", "write_data"]
