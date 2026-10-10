"""Optional software modules (E0b, docs/design/multiscale-engines.md): detect what is already installed and use it;
install what is missing with micromamba from conda-forge (a fake micromamba here: nothing is downloaded)."""
import json
import os
from pathlib import Path
import stat
import sys
import threading

import pytest

from suan.modules import Modules, load_catalog, platform_key
from suan.project.store import ProjectError
from test_desktop_bridge import bridge_env, inproc  # noqa: F401

pytestmark = pytest.mark.skipif(os.name == "nt", reason="the fake programs are shell scripts")

FAKE_MICROMAMBA = """#!{python}
import json, os, pathlib, sys, time
args = sys.argv[1:]
prefix = pathlib.Path(args[args.index("--prefix") + 1])
packages = args[args.index("--channel") + 2:]
config = json.loads(pathlib.Path(sys.argv[0]).with_suffix(".json").read_text())  # the installer's environment is reduced
pathlib.Path(config["log"]).write_text(json.dumps({{"args": args, "root": os.environ.get("MAMBA_ROOT_PREFIX"),
                                                    "env": sorted(os.environ)}}))
if config.get("mode") == "fail":
    print("error    libmamba Could not solve for environment specs", flush=True)
    sys.exit(1)
if config.get("mode") == "slow":
    print("Transaction starting", flush=True)
    time.sleep(30)
bin = prefix / "bin"
bin.mkdir(parents=True, exist_ok=True)
programs = {{"lammps": ("lmp", "LAMMPS (2 Aug 2023 - Update 3)"), "abacus": ("abacus", "ABACUS v3.10.1"),
             "packmol": ("packmol", "PACKMOL Version 20.15.1")}}
for package in packages:
    name = package.split("=")[0]
    if name in programs:
        program, banner = programs[name]
        (bin / program).write_text("#!/bin/sh\\necho '" + banner + "'\\n")
        (bin / program).chmod(0o755)
print("Transaction finished", flush=True)
"""


def write_program(folder, name, text):
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_text("#!/bin/sh\n" + text + "\n")
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return path


@pytest.fixture
def fake(tmp_path, monkeypatch):
    """An empty PATH (only a folder of our own), no conda, and a fake micromamba."""
    tools = tmp_path / "tools"
    tools.mkdir()
    mamba = tools / "micromamba"
    mamba.write_text(FAKE_MICROMAMBA.format(python=sys.executable))
    mamba.chmod(0o755)
    monkeypatch.setenv("STK_MICROMAMBA", str(mamba))
    (tools / "micromamba.json").write_text(json.dumps({"log": str(tmp_path / "mamba.json")}))
    monkeypatch.setenv("STK_TEST_SECRET_TOKEN", "abcdefghijklmnopqrstu")  # never shown to the installer
    monkeypatch.setenv("PATH", str(tmp_path / "path"))
    monkeypatch.delenv("CONDA_PREFIX", raising=False)
    monkeypatch.setattr("suan.modules._conda_bins", lambda home=None: [])

    class Allow:
        def __init__(self):
            self.network = "internet"

        def allows(self, location):
            return self.network == "internet" or location != "external"
    policy = Allow()
    return {"root": tmp_path / "modules", "path": tmp_path / "path", "log": tmp_path / "mamba.json", "policy": policy,
            "config": tools / "micromamba.json"}


def set_mode(fake, mode):
    config = json.loads(fake["config"].read_text())
    fake["config"].write_text(json.dumps({**config, "mode": mode}))


def state(listing, module_id):
    return next(item for item in listing["modules"] if item["id"] == module_id)


def test_the_catalog_lists_engines_and_tools_with_pinned_micromamba():
    catalog = load_catalog()
    assert [entry["id"] for entry in catalog["modules"]] == ["lammps", "abacus", "packmol", "molecular-modeling"]
    assert all(len(item["sha256"]) == 64 and item["size_bytes"] > 1e6 for item in catalog["micromamba"]["files"].values())
    assert platform_key("Linux", "x86_64") == "linux-64" and platform_key("Darwin", "arm64") == "osx-arm64"


def test_an_installed_program_is_detected_and_used_as_it_is(fake):
    write_program(fake["path"], "lmp", "echo 'LAMMPS (29 Aug 2024)'")
    modules = Modules(fake["root"], fake["policy"])
    listing = modules.detect()
    lammps = state(listing, "lammps")
    assert lammps["state"] == "detected" and lammps["version"] == "29 Aug 2024"
    assert lammps["programs"] == {"lmp": str(fake["path"] / "lmp")}
    assert modules.find_program("lammps") == str(fake["path"] / "lmp")
    assert state(listing, "abacus")["state"] == "missing" and modules.find_program("abacus") is None
    with pytest.raises(ProjectError, match="already on this computer"):
        modules.install("lammps")
    with pytest.raises(ProjectError, match="not installed by STK"):
        modules.remove("lammps")  # STK never removes what it did not install
    assert not fake["log"].exists()


def test_a_missing_module_is_installed_from_conda_forge_and_can_be_removed(fake):
    events = []
    modules = Modules(fake["root"], fake["policy"], emit=lambda name, data: events.append((name, data)))
    job = modules.install("abacus", wait=True)
    assert job["state"] == "done", job
    called = json.loads(fake["log"].read_text())
    assert called["args"][:4] == ["create", "--yes", "--prefix", str(fake["root"] / "envs" / "abacus")]
    assert called["args"][-4:] == ["--channel", "conda-forge", "abacus", "mpich"] and "--override-channels" in called["args"]
    assert called["root"] == str(fake["root"] / "mamba")
    assert "STK_TEST_SECRET_TOKEN" not in called["env"] and "PATH" in called["env"]  # a reduced environment
    abacus = state(modules.list(), "abacus")
    assert abacus["state"] == "installed" and abacus["version"] == "v3.10.1"
    assert modules.find_program("abacus") == str(fake["root"] / "envs" / "abacus" / "bin" / "abacus")
    assert events[-1] == ("modules.progress", {"id": "abacus", "state": "done", "stage": "done", "line": "Transaction finished"})
    # A fresh service (or a Runtime launcher on this computer) finds it in the same folder.
    assert Modules(fake["root"]).find_program("abacus") == modules.find_program("abacus")
    assert set(abacus["job"]) == {"id", "state", "stage", "log", "error", "started_at", "finished_at"}  # nothing private
    assert state(modules.remove("abacus"), "abacus")["state"] == "missing"
    assert not (fake["root"] / "envs" / "abacus").exists()


def test_installing_needs_the_internet_and_failures_and_cancels_leave_nothing(fake, monkeypatch):
    modules = Modules(fake["root"], fake["policy"])
    fake["policy"].network = "offline"
    with pytest.raises(ProjectError, match="network setting"):
        modules.install("packmol")
    fake["policy"].network = "internet"
    set_mode(fake, "fail")
    job = modules.install("packmol", wait=True)
    assert job["state"] == "failed" and "exited with 1" in job["error"] and "Could not solve" in job["log"][-1]
    assert not (fake["root"] / "envs" / "packmol").exists() and state(modules.list(), "packmol")["state"] == "missing"
    set_mode(fake, "slow")
    job = modules.install("packmol")
    assert job["state"] == "running" and state(modules.list(), "packmol")["state"] == "installing"
    assert modules.install("packmol")["state"] == "running"  # the same job
    for _ in range(200):
        if modules.job("packmol")["log"]:
            break
        threading.Event().wait(0.02)
    modules.cancel("packmol")
    for _ in range(500):
        if modules.job("packmol")["state"] != "running":
            break
        threading.Event().wait(0.02)
    assert modules.job("packmol")["state"] == "cancelled" and not (fake["root"] / "envs" / "packmol").exists()


def test_a_python_toolkit_is_detected_by_importing_it(fake):
    write_program(fake["path"], "python3", """case "$*" in *mbuild*) echo '{"version": "0.17.0"}';; esac""")
    listing = Modules(fake["root"], fake["policy"]).detect("molecular-modeling")
    toolkit = state(listing, "molecular-modeling")
    assert toolkit["state"] == "detected" and toolkit["version"] == "0.17.0"
    assert toolkit["programs"] == {"python": str(fake["path"] / "python3")}


def test_the_service_lists_and_detects_for_scripts_and_installs_only_for_the_desktop(inproc, fake, monkeypatch):
    monkeypatch.setenv("STK_MODULES_DIR", str(fake["root"]))
    write_program(fake["path"], "packmol", "echo 'PACKMOL'")
    h = inproc()
    listing = h.call("modules.detect", {})
    assert state(listing, "packmol")["state"] == "detected" and listing["root"] == str(fake["root"])
    assert state(h.call("modules.list", {}), "lammps")["state"] == "missing"
    catalog = set(h.call("script.catalog")["operations"])
    assert {"modules.list", "modules.detect"} <= catalog and not {"modules.install", "modules.cancel", "modules.remove"} & catalog
    assert h.error("modules.install", {"id": "no-such"})["code"] == "invalid_params"
    assert not h.violations


def wait_until(condition, seconds=10):
    for _ in range(int(seconds / 0.02)):
        if condition():
            return True
        threading.Event().wait(0.02)
    return False


def test_a_half_made_environment_is_never_taken_for_an_installed_module(fake):
    modules = Modules(fake["root"], fake["policy"])
    prefix = fake["root"] / "envs" / "packmol"
    write_program(prefix / "bin", "packmol", "exit 127")  # left by an installation that was interrupted
    (fake["root"] / "envs" / "packmol.incomplete").write_text("then")
    assert state(modules.detect(), "packmol")["state"] == "missing" and modules.find_program("packmol") is None
    job = modules.install("packmol", wait=True)  # starts over and checks the result
    assert job["state"] == "done" and not (fake["root"] / "envs" / "packmol.incomplete").exists()
    assert state(modules.list(), "packmol")["state"] == "installed"


def test_installations_and_detections_do_not_trip_over_each_other(fake, monkeypatch):
    modules = Modules(fake["root"], fake["policy"])
    set_mode(fake, "slow")
    first = modules.install("packmol")
    again = modules.install("packmol")  # the same job, nothing private, no second installer
    assert again["state"] == "running" and json.dumps(again) and set(again) == set(first)
    assert wait_until(lambda: modules.job("packmol")["log"])
    listing = modules.detect()  # a full detection leaves the running installation alone
    assert state(listing, "packmol")["state"] == "installing" and listing["detected_at"]
    modules.cancel_all()  # the network setting stopped allowing the internet
    assert wait_until(lambda: modules.job("packmol")["state"] != "running")
    assert modules.job("packmol")["state"] == "cancelled" and not (fake["root"] / "envs" / "packmol").exists()


def test_a_damaged_or_foreign_registry_is_read_safely(fake):
    modules = Modules(fake["root"], fake["policy"])
    fake["root"].mkdir(parents=True)
    (fake["root"] / "registry.json").write_text(json.dumps({"format": "stk.module-registry/1", "modules": {
        "lammps": {"programs": {"lmp": "/x"}}, "abacus": {"source": "detected", "programs": {"abacus": "/y"}, "version": "v" * 500}}}))
    listing = modules.list()
    assert state(listing, "lammps")["state"] == "missing" and len(state(listing, "abacus")["version"]) == 100
    (fake["root"] / "registry.json").write_text("{")
    assert state(modules.list(), "abacus")["state"] == "missing" and modules.list()["detected_at"] is None
