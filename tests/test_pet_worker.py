"""Regressions for real Packmol failure modes, without molecular dependencies."""
import os
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import pytest

from suan.lammps.pet_worker import _strict_packmol


@pytest.fixture
def packer(tmp_path, monkeypatch):
    if os.name == "nt":
        pytest.skip("These standalone executable fixtures use POSIX shebangs")
    executable = tmp_path / "registered-alternate-name"
    root, packing = ModuleType("mbuild"), ModuleType("mbuild.packing")
    packing.PACKMOL = str(executable)
    root.packing = packing
    monkeypatch.setitem(sys.modules, "mbuild", root)
    monkeypatch.setitem(sys.modules, "mbuild.packing", packing)
    filled = tmp_path / "filled.xyz"
    filled.write_text("1\npublic test\nH 0 0 0\n")

    def script(source):
        executable.write_text("#!" + sys.executable + "\n" + source, encoding="utf-8")
        executable.chmod(0o700)
        return SimpleNamespace(name=str(filled))
    return script


@pytest.mark.parametrize("output", ["WITHOUT PERFECT PACKING", "ERROR initial packing", "no success marker",
                                   "ERROR earlier failure\nSuccess!"])
def test_packmol_zero_exit_does_not_accept_forced_or_unverified_packing(packer, output):
    filled = packer("print(" + repr(output) + ")\n")
    with pytest.raises(ValueError, match="verified perfect packing"):
        _strict_packmol("", filled)


def test_registered_packmol_exact_executable_and_verified_result_copy(packer, tmp_path):
    filled = packer("import sys\nassert sys.stdin.read() == 'public input'\nprint('Success!')\n")
    output = tmp_path / "copied.xyz"
    _strict_packmol("public input", filled, temp_file=output)
    assert output.read_bytes() == Path(filled.name).read_bytes()


def test_packmol_log_overflow_is_stopped_while_process_is_still_running(packer):
    filled = packer("import sys,time\nsys.stdout.write('x'*(9*1024*1024)); sys.stdout.flush(); time.sleep(30)\n")
    with pytest.raises(ValueError, match="output/time budget"):
        _strict_packmol("", filled)
