"""Test-only real bridge for the desktop's module tests: an isolated modules folder and home (no real conda found), a
fake micromamba that "installs" small programs, and a fake LAMMPS already on PATH. Production never imports it."""
import os
from pathlib import Path
import sys

from suan.desktop_bridge.__main__ import main

work = Path(sys.argv.pop(1))
tools, path, home = work / "tools", work / "path", work / "home"
for folder in (tools, path, home):
    folder.mkdir(parents=True, exist_ok=True)
mamba = tools / "micromamba"
mamba.write_text(f"""#!{sys.executable}
import pathlib, sys
args = sys.argv[1:]
prefix = pathlib.Path(args[args.index("--prefix") + 1])
(prefix / "bin").mkdir(parents=True, exist_ok=True)
for package in args[args.index("--channel") + 2:]:
    if package == "packmol":
        (prefix / "bin" / "packmol").write_text("#!/bin/sh\\necho PACKMOL\\n")
        (prefix / "bin" / "packmol").chmod(0o755)
print("Transaction finished", flush=True)
""")
mamba.chmod(0o755)
(path / "lmp").write_text("#!/bin/sh\necho 'LAMMPS (2 Aug 2023 - Update 3)'\n")
(path / "lmp").chmod(0o755)
os.environ.update(STK_MODULES_DIR=str(work / "modules"), STK_MICROMAMBA=str(mamba), HOME=str(home),
                  PATH=str(path) + os.pathsep + "/usr/bin:/bin")
os.environ.pop("CONDA_PREFIX", None)
main()
