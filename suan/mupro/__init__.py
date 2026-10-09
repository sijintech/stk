"""STK-owned MuPRO (muFerro) task support: client TaskSpec builder, compute-side
launcher and per-run verifier. Standard library only (tomllib reads TOML);
muprosdk is called as a native program, never imported."""

from .spec import muferro_spec

__all__ = ["muferro_spec"]
