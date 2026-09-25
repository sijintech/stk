"""STK-owned MuPRO (muFerro) task support: client TaskSpec builder, compute-side
launcher and per-run verifier. Stdlib + TOML reader (tomllib, or tomli before
Python 3.11) only; muprosdk is called as a native program, never imported."""

from .spec import muferro_spec

__all__ = ["muferro_spec"]
