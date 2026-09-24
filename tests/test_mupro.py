"""MuPRO (muFerro) support: client builder and CLI, per-run verifier, compute-side launcher.

Launcher tests use the fake SDK in mupro_fake.py. They never start a real MPI launcher
or muFerro; the opt-in real test runs a single rank only.
"""

from pathlib import Path
import json
import os
import shutil
import subprocess
import sys

from click.testing import CliRunner
import pytest

from mupro_fake import make_fake_mpiexec, make_fake_sdk, make_fake_srun, write_case, write_outputs
from suan.mupro import cli as mupro_cli
from suan.mupro import muferro_spec
from suan.mupro.run import FRAME, RUN_OUTPUTS, MuproError, expected_frames, main, read_case, verify_run
from suan.runtime.common import sha256

WORKSPACE = "a" * 32
# Anything that could reach a real SDK, licence or MPI launcher, and the scheduler markers.
NODE_ENV = ("STK_MUPRO_ENV_SCRIPTS", "MUPRO_SDK_PREFIX", "MUPROROOT", "STK_MUPRO_ALLOW_LOCAL_MPI", "SLURM_JOB_ID",
            "PBS_JOBID", "SRUN_CPUS_PER_TASK")


class FakeClient:
    def __init__(self, resources=("ranks", "threads_per_rank"), report=None):
        self.resources, self.report = resources, report
        self.uploads, self.submitted = [], []

    def health(self):
        return {"api_version": 1, **({"resources": list(self.resources)} if self.resources else {})}

    def upload(self, workspace_id, path, remote):
        self.uploads.append(remote)
        return {"path": remote}

    def files(self, workspace_id):
        return [{"path": p} for p in ("case16/input.toml", "case16/material.toml", "other/input.toml")]

    def submit(self, spec, key):
        self.submitted.append((spec, key))
        return {"id": "b" * 32, "state": "queued", "spec": spec}

    def wait(self, task_id, timeout):
        return {"id": task_id, "state": "failed"}

    def download(self, task_id, remote_path, destination):
        Path(destination).write_text(json.dumps(self.report), encoding="utf-8")
        return destination


def invoke(client, monkeypatch, args):
    monkeypatch.setattr(mupro_cli, "get_client", lambda *_: client)
    return CliRunner().invoke(mupro_cli.mupro, args)


def test_spec_builder_uses_rank_tokens_and_mpi_resources():
    spec = muferro_spec(WORKSPACE, case_dir="case16", inputs=["case16/input.toml"], ranks=2, backend="slurm",
                        walltime_seconds=600, program="/opt/mupro/bin/muFerro", launcher="srun",
                        sdk_prefix="/opt/mupro", env_scripts=["/opt/a.sh", "/opt/b.sh"], license_dir="/opt/lic",
                        name="pto")
    assert spec["argv"] == ["{python}", "-m", "suan.mupro", "run", "--ranks", "{ranks}", "--threads-per-rank",
                            "{threads_per_rank}", "--case-dir", "case16", "--program", "/opt/mupro/bin/muFerro",
                            "--launcher", "srun", "--sdk-prefix", "/opt/mupro", "--env-script", "/opt/a.sh",
                            "--env-script", "/opt/b.sh", "--license-dir", "/opt/lic"]
    assert spec["outputs"] == ["stk-mupro.json"] and spec["env"] == {}
    assert spec["resources"] == {"ranks": 2, "threads_per_rank": 1, "walltime_seconds": 600}
    assert (spec["workspace_id"], spec["backend"], spec["name"]) == (WORKSPACE, "slurm", "pto")
    assert spec["inputs"] == ["case16/input.toml"]
    example = muferro_spec(WORKSPACE, example=True)
    assert example["argv"][8:] == ["--example"] and example["inputs"] == []
    assert example["resources"] == {"ranks": 1, "threads_per_rank": 1} and example["backend"] == "local"
    cluster = muferro_spec(WORKSPACE, ranks=8, threads_per_rank=2, nodes=2, backend="pbs", walltime_seconds=3600,
                           memory_mb=4096, queue="batch", account="proj")
    assert cluster["argv"][8:] == [] and cluster["inputs"] is None
    assert cluster["resources"] == {"ranks": 8, "threads_per_rank": 2, "nodes": 2, "walltime_seconds": 3600,
                                    "memory_mb": 4096, "queue": "batch", "account": "proj"}


@pytest.mark.parametrize("kwargs, message", [
    ({"ranks": True}, "ranks"),
    ({"threads_per_rank": 0}, "threads_per_rank"),
    ({"backend": "slurm"}, "Cluster MuPRO jobs require walltime_seconds"),
    ({"example": True, "inputs": ["input.toml"]}, "inputs must be empty"),
    ({"nodes": 2}, "one node"),
    ({"case_dir": "../x"}, "inside the workspace"),
])
def test_spec_builder_rejects_bad_layouts(kwargs, message):
    with pytest.raises(ValueError, match=message):
        muferro_spec(WORKSPACE, **kwargs)


def test_submit_uploads_case_and_submits_dict_spec(tmp_path, monkeypatch):
    write_case(tmp_path / "case16", grid=(16, 16, 16), steps=101, interval=100)
    client = FakeClient()
    result = invoke(client, monkeypatch, ["submit", "--workspace", WORKSPACE, "--input", str(tmp_path / "case16"),
                                          "--ranks", "2", "--key", "retry-1"])
    assert result.exit_code == 0, result.output
    assert client.uploads == ["case16/input.toml", "case16/material.toml"]
    spec, key = client.submitted[0]
    assert type(spec) is dict and key == "retry-1"
    assert "Idempotency key: retry-1" in result.output
    assert spec["argv"][4:10] == ["--ranks", "{ranks}", "--threads-per-rank", "{threads_per_rank}", "--case-dir",
                                  "case16"]
    assert spec["inputs"] == client.uploads and spec["resources"] == {"ranks": 2, "threads_per_rank": 1}

    result = invoke(client, monkeypatch, ["submit", "--workspace", WORKSPACE, "--input", str(tmp_path / "case16"),
                                          "--remote-dir", "runs/a"])
    assert result.exit_code == 0, result.output
    assert client.submitted[-1][0]["inputs"] == ["runs/a/input.toml", "runs/a/material.toml"]
    result = invoke(client, monkeypatch, ["submit", "--workspace", WORKSPACE, "--case-dir", "case16"])
    assert result.exit_code == 0, result.output
    assert client.submitted[-1][0]["inputs"] == ["case16/input.toml", "case16/material.toml"]
    result = invoke(client, monkeypatch, ["submit", "--workspace", WORKSPACE, "--example", "--backend", "slurm",
                                          "--walltime", "600", "--wait"])
    assert result.exit_code == 1
    spec = client.submitted[-1][0]
    assert spec["inputs"] == [] and "--example" in spec["argv"] and spec["resources"]["walltime_seconds"] == 600

    count = len(client.submitted)
    result = invoke(client, monkeypatch, ["submit", "--workspace", WORKSPACE, "--example", "--backend", "slurm"])
    assert result.exit_code == 1 and "walltime_seconds" in result.output
    result = invoke(client, monkeypatch, ["submit", "--workspace", WORKSPACE, "--example", "--case-dir", "case16"])
    assert result.exit_code == 2 and "exactly one" in result.output
    assert len(client.submitted) == count
    # A layout the builder rejects fails before anything is uploaded.
    client = FakeClient()
    for args, message in ((["--backend", "slurm"], "walltime_seconds"), (["--nodes", "2"], "one node"),
                           # The Runtime's TaskSpec rule, and the case checks the node would make after queueing.
                           (["--backend", "slurm", "--walltime", "3600", "--ranks", "3", "--nodes", "2"],
                            "multiple of nodes"),
                           (["--ranks", "17"], "min(nx, ny) = 16")):
        result = invoke(client, monkeypatch, ["submit", "--workspace", WORKSPACE, "--input", str(tmp_path / "case16"),
                                              *args])
        assert result.exit_code == 1 and message in result.output
        assert client.uploads == [] and client.submitted == []
    (tmp_path / "empty").mkdir()
    result = invoke(client, monkeypatch, ["submit", "--workspace", WORKSPACE, "--input", str(tmp_path / "empty")])
    assert result.exit_code == 1 and "Cannot read input.toml" in result.output
    # Outputs of an earlier run in place would be uploaded, and muFerro would append to them.
    write_outputs(tmp_path / "case16", grid=(16, 16, 16), steps=101, interval=100)
    result = invoke(client, monkeypatch, ["submit", "--workspace", WORKSPACE, "--input", str(tmp_path / "case16")])
    assert result.exit_code == 1 and "already holds muFerro outputs" in result.output
    assert "energy_out.dat" in result.output and "clean case directory" in result.output
    assert client.uploads == [] and client.submitted == []


def test_submit_refuses_runtime_without_mpi_resources(tmp_path, monkeypatch):
    write_case(tmp_path / "case16")
    client = FakeClient(resources=())
    result = invoke(client, monkeypatch, ["submit", "--workspace", WORKSPACE, "--input", str(tmp_path / "case16")])
    assert result.exit_code == 1
    assert "This Runtime does not accept MPI rank resources; upgrade the STK server" in result.output
    assert client.uploads == [] and client.submitted == []


def test_mupro_group_help_needs_no_runtime(monkeypatch):
    def no_client(*_):
        raise AssertionError("--help must not connect to a runtime")

    monkeypatch.setattr(mupro_cli, "get_client", no_client)
    result = CliRunner().invoke(mupro_cli.mupro, ["--help"])
    assert result.exit_code == 0 and "MuPRO jobs queued by the STK Runtime" in result.output
    assert all(name in result.output for name in ("submit", "result", "verify"))
    for command in ("submit", "result", "verify"):
        assert CliRunner().invoke(mupro_cli.mupro, [command, "--help"]).exit_code == 0
    for command in ("run", "verify", "check"):
        with pytest.raises(SystemExit) as info:
            main([command, "--help"])
        assert info.value.code == 0


def test_result_exits_by_verification_status(tmp_path, monkeypatch):
    report = {"state": "succeeded", "verification": {"status": "passed"}}
    kept = tmp_path / "kept.json"
    result = invoke(FakeClient(report=report), monkeypatch, ["result", "c" * 32, "--output", str(kept)])
    assert result.exit_code == 0, result.output
    assert json.loads(kept.read_text(encoding="utf-8")) == report
    report = {"state": "failed", "verification": {"status": "not_run"}}
    result = invoke(FakeClient(report=report), monkeypatch, ["result", "c" * 32])
    assert result.exit_code == 3 and '"not_run"' in result.output


def test_verify_classifies_outputs(tmp_path):
    ok = tmp_path / "ok"
    write_case(ok, grid=(16, 16, 16), steps=101, interval=100)
    write_outputs(ok, grid=(16, 16, 16), steps=101, interval=100)
    report = verify_run(ok)
    assert report["verification"]["status"] == "passed" and report["classification"] is None
    assert [check["status"] for check in report["verification"]["checks"]] == ["pass"] * 4
    assert len(report["frames"]) == 30
    assert report["frames"][0] == {"stem": "Charges", "step": 1, "components": 1, "path": "Charges.00000001.dat"}
    assert [(f["stem"], f["step"]) for f in report["frames"] if f["stem"] == "Polar"] == [("Polar", 0), ("Polar", 100)]
    assert report["qoi"] == {"total_energy": -113.625, "step": 101}
    assert CliRunner().invoke(mupro_cli.mupro, ["verify", str(ok)]).exit_code == 0

    for mode, classification in (("nan", "invalid_result"), ("missing_frame", "incomplete_result")):
        case = tmp_path / mode
        write_case(case)
        write_outputs(case, mode=mode)
        report = verify_run(case)
        assert report["verification"]["status"] == "failed"
        assert report["classification"] == classification, report
        assert report["qoi"] is None
    # The NaN stop leaves no completion manifest, which muprosdk reads first (contract.py:50-54).
    assert verify_run(tmp_path / "nan")["reason"].startswith("Cannot read mupro_completion.json")
    assert CliRunner().invoke(mupro_cli.mupro, ["verify", str(tmp_path / "nan")]).exit_code == 3

    case = tmp_path / "grid"
    write_case(case)
    write_outputs(case)
    frame = case / "Polar.00000002.dat"
    frame.write_text("     4     4     2     3\n" + frame.read_text().split("\n", 1)[1])
    report = verify_run(case)
    assert report["classification"] == "invalid_result" and "Polar.00000002.dat" in report["reason"]
    assert report["verification"]["checks"][3]["id"] == "frames"
    frame.write_text("     4     3     2     3\n" + frame.read_text().split("\n", 1)[1])
    strain = case / "Strain.00000001.dat"
    strain.write_text("     4     3     2     3\n" + strain.read_text().split("\n", 1)[1])
    report = verify_run(case)
    assert report["classification"] == "invalid_result" and "component" in report["reason"]


def _replace(name, old, new):
    def edit(case):
        path = case / name
        path.write_text(path.read_text().replace(old, new, 1))
    return edit


def _drop_last_line(name):
    def edit(case):
        path = case / name
        path.write_text("".join(path.read_text().splitlines(keepends=True)[:-1]))
    return edit


@pytest.mark.parametrize("edit, check, classification", [
    (_replace("mupro_completion.json", '"completed_steps":3', '"completed_steps":2'), "completion",
     "incomplete_result"),
    (_replace("mupro_completion.json", '"final_step":3', '"final_step":NaN'), "completion", "invalid_result"),
    (_replace("energy_out.dat", "kt:      2 energy:", "kt: 2 energy"), "energy", "invalid_result"),
    (_replace("energy_out.dat", "-0.2250000000E+01", ""), "energy", "numerical_failure"),
    (_replace("energy_out.dat", "0.2500000000E+00", "0.25x"), "energy", "invalid_result"),
    (_replace("energy_out.dat", "kt:      2 ", "kt:      9 "), "energy", "incomplete_result"),
    (_drop_last_line("energy_out.dat"), "energy", "incomplete_result"),
    (_drop_last_line("mupro_progress.jsonl"), "progress", "incomplete_result"),
    (_replace("mupro_progress.jsonl", "{", "["), "progress", "invalid_result"),
])
def test_verify_mirrors_muprosdk_worker_classification(tmp_path, edit, check, classification):
    """muprosdk tools/mupro/mupro/worker.py:17-39 and contract.py:50-54."""
    write_case(tmp_path)
    write_outputs(tmp_path)
    edit(tmp_path)
    report = verify_run(tmp_path)
    assert report["classification"] == classification, report
    assert [c["id"] for c in report["verification"]["checks"] if c["status"] == "fail"] == [check]


def test_verify_accepts_fortran_d_exponents_and_restarts(tmp_path):
    write_case(tmp_path)
    write_outputs(tmp_path)
    energy = tmp_path / "energy_out.dat"
    energy.write_text(energy.read_text().replace("E+", "D+").replace("E-", "D-"))
    assert verify_run(tmp_path)["verification"]["status"] == "passed"
    restart = tmp_path / "restart"
    write_case(restart, start=10, steps=2, interval=1)
    write_outputs(restart, start=10, steps=2, interval=1)
    report = verify_run(restart)
    assert report["verification"]["status"] == "passed", report
    assert report["qoi"] == {"total_energy": -13.5, "step": 12}


def test_expected_frames_match_muferro_naming():
    frames = expected_frames({"grid": [16, 16, 16], "start_step": 0, "steps": 101, "output_interval": 100})
    assert len(frames) == 30 and all(FRAME.search(name) for name in frames)
    assert frames["Polar.00000000.dat"] == frames["Polar.00000100.dat"] == 3
    assert frames["Strain.00000001.dat"] == frames["Strain.00000101.dat"] == 6
    assert frames["Charges.00000001.dat"] == frames["Elast_En.00000101.dat"] == 1
    assert frames["Eigen_St.00000001.dat"] == 6 and "Polar.00000101.dat" not in frames
    # A restart still writes its initial Polar frame as step 0 (muprosdk worker.py:40, output.f90:24).
    restart = expected_frames({"grid": [4, 3, 2], "start_step": 10, "steps": 2, "output_interval": 1})
    assert "Polar.00000000.dat" in restart and "Polar.00000010.dat" not in restart
    assert {"Polar.00000011.dat", "Polar.00000012.dat", "Strain.00000011.dat", "Strain.00000012.dat"} <= set(restart)


def test_read_case_uses_muferro_defaults(tmp_path):
    write_case(tmp_path)  # Includes the example's mixed int/float array.
    assert read_case(tmp_path) == {"grid": [4, 3, 2], "start_step": 0, "steps": 3, "output_interval": 2}
    path = tmp_path / "input.toml"
    text = path.read_text()
    path.write_text(text.replace("timestep_start = 0\n", "").replace("timestep_total = 3\n", ""))
    assert read_case(tmp_path) == {"grid": [4, 3, 2], "start_step": 0, "steps": 1000, "output_interval": 2}
    path.write_text(text.replace("interval = 2\n", ""))
    with pytest.raises(MuproError, match=r"\[output\].interval") as info:
        read_case(tmp_path)
    assert info.value.classification == "configuration"
    assert verify_run(tmp_path)["classification"] == "configuration"
    path.write_text(text.replace("simulation_grid = [4, 3, 2]", "simulation_grid = [4, 3]"))
    with pytest.raises(MuproError, match="simulation_grid"):
        read_case(tmp_path)
    path.write_text(text.replace("timestep_total = 3", "timestep_total = 1000000"))
    with pytest.raises(MuproError, match="999999"):
        read_case(tmp_path)


def test_read_case_resolves_includes_like_muferro(tmp_path):
    """muprosdk library/L0_Base/toml.f90:125-238: relative to the naming file, the including
    file and earlier includes win, sub-tables merge per key, at most 16 deep."""
    work = tmp_path / "work"
    case = work / "case"
    write_case(case, steps=3, interval=2)
    text = (case / "input.toml").read_text()
    (case / "input.toml").write_text("include = 'common.toml'\n" + text.replace("timestep_total = 3\n", "")
                                      .split("[output]")[0])
    (case / "common.toml").write_text("include = ['lib/steps.toml', 'lib/late.toml']\n"
                                      "[system]\nsimulation_grid = [9, 9, 9]\n[output]\ninterval = 5\n")
    (case / "lib").mkdir()
    (case / "lib" / "steps.toml").write_text("[system]\ntimestep_total = 7\n")
    (case / "lib" / "late.toml").write_text("[system]\ntimestep_total = 8\ntimestep_start = 4\n")
    assert read_case(case) == {"grid": [4, 3, 2], "start_step": 0, "steps": 7, "output_interval": 5}
    # A shared library elsewhere in the task work dir, but never outside it.
    (case / "common.toml").write_text("include = '../shared/output.toml'\n[system]\ntimestep_total = 7\n")
    (work / "shared").mkdir()
    (work / "shared" / "output.toml").write_text("[output]\ninterval = 5\n")
    assert read_case(case, work)["output_interval"] == 5
    with pytest.raises(MuproError, match="must stay inside") as info:
        read_case(case)
    assert info.value.classification == "configuration"
    # Include strings are POSIX paths on every platform, so a Windows client refuses what the node would.
    for include, message in (("'missing.toml'", "Cannot read case/missing.toml"), ("'/etc/x.toml'", "relative POSIX"),
                             ("'lib\\steps.toml'", "relative POSIX"), ("'C:lib/steps.toml'", "relative POSIX"),
                             ("'lib/C:x.toml'", "relative POSIX"), ('"x\\u0000.toml"', "relative POSIX"),
                             ("['input.toml']", "Cyclic"), ("[1]", "path or a list of paths")):
        (case / "common.toml").write_text(f"include = {include}\n")
        with pytest.raises(MuproError, match=message):
            read_case(case, work)
    # input.toml is depth 0 and common.toml depth 1; a file at depth 16 may not include another.
    for n in range(17):
        (case / f"d{n}.toml").write_text(f"include = 'd{n + 1}.toml'\n")
    (case / "d17.toml").write_text("[output]\ninterval = 5\n")
    (case / "common.toml").write_text("include = 'd2.toml'\n")
    with pytest.raises(MuproError, match="16 deep"):
        read_case(case, work)
    (case / "common.toml").write_text("include = 'd3.toml'\n")
    assert read_case(case, work)["output_interval"] == 5


def test_read_case_reports_any_unreadable_case_as_configuration(tmp_path, monkeypatch):
    write_case(tmp_path)
    text = (tmp_path / "input.toml").read_text()
    (tmp_path / "input.toml").write_text("x = " + "[" * 5000 + "]" * 5000 + "\n" + text)
    with pytest.raises(MuproError, match="Cannot read input.toml") as info:
        read_case(tmp_path)
    assert info.value.classification == "configuration"
    assert verify_run(tmp_path)["classification"] == "configuration"
    (tmp_path / "input.toml").write_text("include = 'common.toml'\n" + text)
    (tmp_path / "common.toml").write_text("[system]\ntimestep_total = 7\n")

    def too_deep(*_):
        raise RecursionError("maximum recursion depth exceeded")

    monkeypatch.setattr("suan.mupro.run._merge_under", too_deep)
    with pytest.raises(MuproError, match="Cannot read input.toml: maximum recursion") as info:
        read_case(tmp_path)
    assert info.value.classification == "configuration"


def test_verify_uses_included_layout(tmp_path):
    write_case(tmp_path, steps=3, interval=2)
    text = (tmp_path / "input.toml").read_text()
    (tmp_path / "input.toml").write_text("include = 'common.toml'\n" + text.replace("timestep_total = 3\n", "")
                                         .replace("[output]\ninterval = 2\n", ""))
    (tmp_path / "common.toml").write_text("[system]\ntimestep_total = 3\n[output]\ninterval = 2\n")
    write_outputs(tmp_path, steps=3, interval=2)
    report = verify_run(tmp_path)
    assert report["verification"]["status"] == "passed", report
    assert report["qoi"] == {"total_energy": -3.375, "step": 3}


@pytest.fixture
def node(tmp_path, monkeypatch):
    """A task work dir as CWD with a clean MPI environment and a fake bin dir first on PATH."""
    for key in [*NODE_ENV, *(key for key in os.environ if key.startswith("I_MPI_"))]:
        monkeypatch.delenv(key, raising=False)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    monkeypatch.setenv("PATH", str(bin_dir) + os.pathsep + os.defpath)
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    return work, bin_dir


def launch(sdk, *args):
    code = main(["run", "--sdk-prefix", str(sdk), *args])
    return code, json.loads(Path("stk-mupro.json").read_text(encoding="utf-8"))


def assert_fake_command(record, tmp_path):
    assert Path(record["command"][0]).is_relative_to(tmp_path), record["command"]


def clear_outputs(folder):
    """Remove a finished run's outputs; each Runtime task starts in a fresh work dir."""
    for path in Path(folder).iterdir():
        if path.name in RUN_OUTPUTS or FRAME.search(path.name):
            path.unlink()


@pytest.mark.server
def test_run_example_single_rank_sets_threads_and_verifies(node, tmp_path, monkeypatch):
    work, _ = node
    sdk = make_fake_sdk(tmp_path / "sdk")
    monkeypatch.setenv("OMP_NUM_THREADS", "48")
    result = subprocess.run([sys.executable, "-m", "suan.mupro", "run", "--example", "--sdk-prefix", str(sdk)],
                            cwd=work, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr
    assert "fake muFerro finished" in result.stdout and "verification passed" in result.stdout
    fake = json.loads((work / "fake-muferro.json").read_text())
    assert fake["OMP_NUM_THREADS"] == fake["MKL_NUM_THREADS"] == "1"
    assert fake["cwd"] == str(work)
    record = json.loads((work / "stk-mupro.json").read_text())
    program = sdk / "bin" / "muFerro"
    assert_fake_command(record, tmp_path)
    assert record["command"] == [str(program)]
    assert record["program"] == {"path": str(program), "sha256": sha256(program)}
    assert record["layout"] == {"ranks": 1, "threads_per_rank": 1, "launcher": "none"}
    assert (record["state"], record["classification"], record["exit_code"]) == ("succeeded", None, 0)
    assert record["verification"]["verifier"] == "stk-mupro-1"
    assert record["verification"]["status"] == "passed"
    assert record["environment"] == {"OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1", "MUPROROOT": None,
                                     "SRUN_CPUS_PER_TASK": None}
    assert record["case"] == {"grid": [4, 3, 2], "start_step": 0, "steps": 3, "output_interval": 2}
    assert record["sdk_prefix"] == str(sdk) and record["env_scripts"] == []
    assert record["qoi"] == {"total_energy": -3.375, "step": 3} and len(record["frames"]) == 30
    assert record["schema_version"] == 1 and record["started_at"] and record["finished_at"]


@pytest.mark.server
def test_run_nan_exit_zero_is_failure(node, tmp_path):
    sdk = make_fake_sdk(tmp_path / "sdk", mode="nan")
    code, record = launch(sdk, "--example")
    assert code == 3
    assert_fake_command(record, tmp_path)
    assert (record["state"], record["exit_code"]) == ("failed", 0)
    assert record["classification"] == "invalid_result" and record["verification"]["status"] == "failed"
    failed = {check["id"]: check["status"] for check in record["verification"]["checks"]}
    assert failed == {"completion": "fail", "energy": "fail", "progress": "fail", "frames": "fail"}
    assert record["qoi"] is None


@pytest.mark.server
def test_solver_nonzero_exit_is_solver_failed(node, tmp_path):
    sdk = make_fake_sdk(tmp_path / "sdk", mode="fail")
    code, record = launch(sdk, "--example")
    assert code == 3
    assert_fake_command(record, tmp_path)
    assert (record["state"], record["classification"], record["exit_code"]) == ("failed", "solver_failed", 5)
    assert record["verification"]["status"] == "not_run"


@pytest.mark.server
def test_run_uploaded_case_dir_and_launch_failure(node, tmp_path):
    """The argv `suan mupro submit --input DIR` produces: muFerro runs in work/<case>."""
    work, _ = node
    sdk = make_fake_sdk(tmp_path / "sdk")
    write_case(work / "case16")
    code, record = launch(sdk, "--case-dir", "case16")
    assert code == 0, record["reason"]
    assert_fake_command(record, tmp_path)
    assert json.loads((work / "case16" / "fake-muferro.json").read_text())["cwd"] == str(work / "case16")
    assert (work / "stk-mupro.json").is_file() and not (work / "case16" / "stk-mupro.json").exists()
    assert record["case_dir"] == "case16" and record["verification"]["status"] == "passed"
    assert all(frame["path"].startswith("case16/") for frame in record["frames"])
    assert record["frames"][0]["path"] == "case16/Charges.00000001.dat"

    clear_outputs(work / "case16")
    garbage = tmp_path / "garbage"
    garbage.write_bytes(b"\x00\x01\x02 not an executable\n")
    garbage.chmod(0o755)
    code, record = launch(sdk, "--case-dir", "case16", "--program", str(garbage))
    assert code == 2
    assert_fake_command(record, tmp_path)
    assert (record["state"], record["classification"], record["exit_code"]) == ("failed", "launch_failed", None)
    assert record["verification"]["status"] == "not_run"


@pytest.mark.server
def test_local_multirank_requires_operator_opt_in(node, tmp_path, monkeypatch):
    work, bin_dir = node
    sdk = make_fake_sdk(tmp_path / "sdk")
    mpiexec = make_fake_mpiexec(bin_dir)
    code, record = launch(sdk, "--example", "--ranks", "2")
    assert code == 2
    assert (record["state"], record["classification"]) == ("failed", "configuration")
    assert "0.0.0.0" in record["reason"] and "STK_MUPRO_ALLOW_LOCAL_MPI=1" in record["reason"]
    assert record["command"] == [] and not (work / "fake-muferro.json").exists()
    # An explicit one-rank mpiexec would open the same listener.
    code, record = launch(sdk, "--launcher", "mpiexec")
    assert code == 2 and "0.0.0.0" in record["reason"] and not (work / "fake-muferro.json").exists()
    code, record = launch(sdk, "--launcher", "none", "--ranks", "2")
    assert code == 2 and record["classification"] == "configuration"

    monkeypatch.setenv("STK_MUPRO_ALLOW_LOCAL_MPI", "1")
    assert shutil.which("mpiexec") == str(mpiexec)
    code, record = launch(sdk, "--ranks", "2")
    assert code == 0, record["reason"]
    assert_fake_command(record, tmp_path)
    assert record["command"] == [str(mpiexec), "-n", "2", str(sdk / "bin" / "muFerro")]
    assert record["layout"] == {"ranks": 2, "threads_per_rank": 1, "launcher": "mpiexec"}
    assert json.loads((work / "fake-muferro.json").read_text())["OMP_NUM_THREADS"] == "1"


@pytest.mark.server
def test_slurm_launcher_uses_srun_with_cpus_per_task(node, tmp_path, monkeypatch):
    work, bin_dir = node
    sdk = make_fake_sdk(tmp_path / "sdk")
    srun = make_fake_srun(bin_dir)
    # Outside an allocation srun would queue a separate Slurm job.
    code, record = launch(sdk, "--example", "--ranks", "2", "--launcher", "srun")
    assert code == 2 and record["classification"] == "configuration" and "Slurm allocation" in record["reason"]
    assert record["command"] == [] and not (work / "fake-muferro.json").exists()
    monkeypatch.setenv("SLURM_JOB_ID", "4242")
    code, record = launch(sdk, "--ranks", "2", "--threads-per-rank", "2", "--launcher", "srun")
    assert code == 0, record["reason"]
    assert_fake_command(record, tmp_path)
    assert record["command"] == [str(srun), "--ntasks=2", "--cpus-per-task=2", str(sdk / "bin" / "muFerro")]
    fake = json.loads((work / "fake-muferro.json").read_text())
    assert fake["SRUN_CPUS_PER_TASK"] == "2"
    assert fake["OMP_NUM_THREADS"] == fake["MKL_NUM_THREADS"] == "2"
    assert record["environment"]["SRUN_CPUS_PER_TASK"] == "2"
    # Inside an allocation auto still uses mpiexec; Hydra detects the allocation.
    mpiexec = make_fake_mpiexec(bin_dir)
    assert shutil.which("mpiexec") == str(mpiexec)
    clear_outputs(work)
    code, record = launch(sdk, "--ranks", "2")
    assert code == 0, record["reason"]
    assert_fake_command(record, tmp_path)
    assert record["command"][:3] == [str(mpiexec), "-n", "2"] and record["layout"]["launcher"] == "mpiexec"
    assert record["environment"]["SRUN_CPUS_PER_TASK"] is None


@pytest.mark.server
def test_env_scripts_and_license_path(node, tmp_path, monkeypatch):
    work, _ = node
    sdk = make_fake_sdk(tmp_path / "sdk")
    script = tmp_path / "env.sh"
    script.write_text("export STK_FAKE_MARK=1\n")
    licence = tmp_path / "licence"
    licence.mkdir()
    code, record = launch(sdk, "--example", "--env-script", str(script), "--license-dir", str(licence))
    assert code == 0, record["reason"]
    assert_fake_command(record, tmp_path)
    fake = json.loads((work / "fake-muferro.json").read_text())
    assert fake["STK_FAKE_MARK"] == "1" and fake["MUPROROOT"] == str(licence)
    assert record["environment"]["MUPROROOT"] == str(licence) and record["env_scripts"] == [str(script)]
    assert "STK_FAKE_MARK" not in json.dumps(record)

    failing = tmp_path / "failing.sh"
    failing.write_text("return 3\n")
    monkeypatch.setenv("STK_MUPRO_ENV_SCRIPTS", os.pathsep.join([str(script), str(failing)]))
    code, record = launch(sdk)
    assert code == 2 and record["classification"] == "configuration"
    assert record["reason"] == f"MuPRO environment script {failing} returned 3"
    # `exit 0` in a sourced script would otherwise leave the solver an empty environment.
    exiting = tmp_path / "exiting.sh"
    exiting.write_text("export STK_FAKE_MARK=2\nexit 0\n")
    monkeypatch.setenv("STK_MUPRO_ENV_SCRIPTS", str(exiting))
    code, record = launch(sdk)
    assert code == 2 and record["classification"] == "configuration" and "exiting.sh" in record["reason"]
    assert record["command"] == []
    monkeypatch.delenv("STK_MUPRO_ENV_SCRIPTS")
    code, record = launch(sdk, "--license-dir", str(tmp_path / ("x" * 300)))
    assert code == 2 and "256" in record["reason"] and record["command"] == []


@pytest.mark.server
def test_rank_bound_and_example_conflict(node, tmp_path):
    work, _ = node
    sdk = make_fake_sdk(tmp_path / "sdk", grid=(4, 3, 2))
    code, record = launch(sdk, "--example", "--ranks", "5")
    assert code == 2 and "min(nx, ny) = 3" in record["reason"]
    assert (work / "input.toml").is_file() and not (work / "fake-muferro.json").exists()
    code, record = launch(sdk, "--example")
    assert code == 2 and "overwrite" in record["reason"] and not (work / "fake-muferro.json").exists()
    code, record = launch(sdk, "--case-dir", "../outside")
    assert code == 2 and record["classification"] == "configuration"


@pytest.mark.server
def test_rerun_in_place_is_refused_before_launch(node, tmp_path):
    work, _ = node
    sdk = make_fake_sdk(tmp_path / "sdk")
    case = work / "case"
    write_case(case)
    subprocess.run([str(sdk / "bin" / "muFerro")], cwd=case, check=True, capture_output=True)
    # The fake appends as muFerro does, so a second run in place cannot verify.
    subprocess.run([str(sdk / "bin" / "muFerro")], cwd=case, check=True, capture_output=True)
    report = verify_run(case)
    assert (report["classification"], report["reason"]) == (
        "incomplete_result", "Energy trace steps are incomplete, duplicated or stale")
    (case / "fake-muferro.json").unlink()
    code, record = launch(sdk, "--case-dir", "case")
    assert code == 2 and record["classification"] == "configuration" and record["command"] == []
    assert "already holds muFerro outputs" in record["reason"] and "energy_out.dat" in record["reason"]
    assert not (case / "fake-muferro.json").exists()
    # Polar.in is a restart input, not an output.
    fresh = work / "fresh"
    write_case(fresh)
    (fresh / "Polar.in").write_text("restart field\n")
    code, record = launch(sdk, "--case-dir", "fresh")
    assert code == 0, record["reason"]


@pytest.mark.server
def test_run_resolves_included_case_and_fake_reads_it(node, tmp_path):
    work, _ = node
    sdk = make_fake_sdk(tmp_path / "sdk")
    write_case(work / "case", steps=3, interval=2)
    text = (work / "case" / "input.toml").read_text()
    (work / "case" / "input.toml").write_text("include = '../lib/common.toml'\n" + text.replace(
        "timestep_total = 3\n", "timestep_total = 4\n").replace("[output]\ninterval = 2\n", ""))
    (work / "lib").mkdir()
    (work / "lib" / "common.toml").write_text("[system]\ntimestep_total = 99\n[output]\ninterval = 2\n")
    code, record = launch(sdk, "--case-dir", "case")
    assert code == 0, record["reason"]
    assert record["case"] == {"grid": [4, 3, 2], "start_step": 0, "steps": 4, "output_interval": 2}
    assert record["qoi"] == {"total_energy": -4.5, "step": 4}
    # Like mupro_fatal, a missing material file stops the solver with a non-zero code.
    (work / "bare").mkdir()
    (work / "bare" / "input.toml").write_text(text.replace("material = 'material.toml'", "material = 'absent.toml'"))
    code, record = launch(sdk, "--case-dir", "bare")
    assert (code, record["classification"], record["exit_code"]) == (3, "solver_failed", 1)


@pytest.mark.server
def test_run_always_writes_its_result(node, tmp_path, monkeypatch):
    work, _ = node
    sdk = make_fake_sdk(tmp_path / "sdk")
    write_case(work / "case")
    text = (work / "case" / "input.toml").read_text()
    (work / "case" / "input.toml").write_text('include = "x\\u0000.toml"\n' + text)
    code, record = launch(sdk, "--case-dir", "case")
    assert (code, record["classification"], record["command"]) == (2, "configuration", [])
    assert "relative POSIX path" in record["reason"]
    (work / "case" / "input.toml").write_text(text)

    def broken(*_):
        raise RuntimeError("unexpected")

    monkeypatch.setattr("suan.mupro.run.check_case", broken)
    code, record = launch(sdk, "--case-dir", "case")
    assert (code, record["state"], record["classification"]) == (2, "failed", "configuration")
    assert record["reason"] == "RuntimeError: unexpected" and record["finished_at"]
    assert not (work / "case" / "fake-muferro.json").exists()


@pytest.mark.server
def test_pbs_allocation_allows_multirank_mpiexec(node, tmp_path, monkeypatch):
    work, bin_dir = node
    sdk = make_fake_sdk(tmp_path / "sdk")
    mpiexec = make_fake_mpiexec(bin_dir)
    monkeypatch.setenv("PBS_JOBID", "1234.pbs")
    code, record = launch(sdk, "--example", "--ranks", "2")
    assert code == 0, record["reason"]
    assert_fake_command(record, tmp_path)
    assert record["command"] == [str(mpiexec), "-n", "2", str(sdk / "bin" / "muFerro")]
    assert record["layout"]["launcher"] == "mpiexec"
    clear_outputs(work)
    code, record = launch(sdk, "--launcher", "mpiexec")
    assert code == 0 and record["command"][:3] == [str(mpiexec), "-n", "1"]


@pytest.mark.server
def test_check_reports_node_toolchain(node, tmp_path, capsys):
    _, bin_dir = node
    sdk = make_fake_sdk(tmp_path / "sdk")
    mpiexec = make_fake_mpiexec(bin_dir)
    licence = tmp_path / "licence"
    licence.mkdir()
    (licence / "user.pem").write_text("never read")
    (licence / "user.pem").chmod(0)
    assert main(["check", "--sdk-prefix", str(sdk), "--license-dir", str(licence), "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    checks = {check["id"]: check for check in report["checks"]}
    assert report["ok"] and checks["program"]["message"] == str(sdk / "bin" / "muFerro")
    assert checks["mpi_launcher"] == {"id": "mpi_launcher", "status": "pass", "message": str(mpiexec)}
    assert checks["license_dir"]["status"] == "pass" and checks["example_case"]["status"] == "pass"
    assert checks["shared_libraries"]["status"] in {"pass", "skip"}
    assert main(["check", "--sdk-prefix", str(tmp_path / "absent"), "--json"]) == 1
    report = json.loads(capsys.readouterr().out)
    checks = {check["id"]: check["status"] for check in report["checks"]}
    assert not report["ok"] and checks["sdk_prefix"] == checks["program"] == "fail"
    assert checks["license_dir"] == "warn" and checks["example_case"] == "warn"


@pytest.mark.server
@pytest.mark.skipif(not os.environ.get("STK_TEST_MUPRO_PREFIX"),
                    reason="Set STK_TEST_MUPRO_PREFIX to run the real muFerro example")
def test_real_muferro_example_single_rank(tmp_path):
    """One rank only: an MPI singleton opens no PMI listener. Env scripts come from
    STK_MUPRO_ENV_SCRIPTS and the licence directory from MUPROROOT."""
    env = {key: value for key, value in os.environ.items()
           if key not in {"STK_MUPRO_ALLOW_LOCAL_MPI", "SLURM_JOB_ID", "PBS_JOBID"}}
    subprocess.run(["nice", "-n", "10", sys.executable, "-m", "suan.mupro", "run", "--example", "--ranks", "1",
                    "--launcher", "none", "--sdk-prefix", os.environ["STK_TEST_MUPRO_PREFIX"]],
                   cwd=tmp_path, env=env, stdin=subprocess.DEVNULL, capture_output=True, timeout=600)
    record = json.loads((tmp_path / "stk-mupro.json").read_text(encoding="utf-8"))
    assert record["state"] == "succeeded", record["reason"]
    assert record["verification"]["status"] == "passed" and len(record["frames"]) == 30
    assert record["layout"] == {"ranks": 1, "threads_per_rank": 1, "launcher": "none"}
    assert record["case"] == {"grid": [16, 16, 16], "start_step": 0, "steps": 101, "output_interval": 100}
