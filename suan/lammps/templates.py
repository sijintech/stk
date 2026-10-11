"""Input-script templates for imported, already parameterized real-units models."""
from importlib.resources import files

NAMES = ("tg", "modulus", "diffusion")


def template_text(name):
    """Return a shipped input script; caller supplies model.in and its data files."""
    if name not in NAMES:
        raise ValueError("LAMMPS property template must be tg, modulus or diffusion")
    return files("suan.lammps").joinpath("templates", name + ".in").read_text(encoding="utf-8")
