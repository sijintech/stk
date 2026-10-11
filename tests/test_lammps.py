"""LAMMPS engine (E1a, docs/design/multiscale-engines.md): input-script checks, the log.lammps reader on a real
LAMMPS log, and the compute-side launcher with a fake LAMMPS (no physics)."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from lammps_fake import SCRIPT, make_fake_lammps, set_mode, write_case
from suan.lammps.log import read_log, verify_log
from suan.lammps.script import ScriptError, check_parameters, check_script, commands
from suan.lammps.spec import lammps_spec

DATA = Path(__file__).parent / "data" / "lammps"
posix_only = pytest.mark.skipif(os.name == "nt", reason="the fake LAMMPS is a script with a shebang line")


def test_a_script_declares_its_parameters_with_index_defaults():
    checked = check_script(SCRIPT, ["in.npt", "system.data"])
    assert checked["units"] == "real" and checked["used"] == ["pressure", "seed", "steps", "temperature"]
    assert checked["parameters"] == {"pressure": None, "seed": 4928459, "steps": 100, "temperature": 300}
    assert check_parameters({"temperature": 350.0, "pressure": 1, "steps": 200, "seed": 7, "timestep": None},
                            checked["used"]) == {"pressure": 1, "seed": 7, "steps": 200, "temperature": 350.0}
    with pytest.raises(ScriptError, match="set it in the row"):
        check_parameters({"temperature": 300, "steps": 1, "seed": 1}, checked["used"])
    with pytest.raises(ScriptError, match="does not use timestep"):
        check_parameters({"temperature": 300, "pressure": 1, "steps": 1, "seed": 1, "timestep": 2.0}, checked["used"])
    with pytest.raises(ScriptError, match="below 2"):
        check_parameters({"temperature": 300, "pressure": 1, "steps": 1, "seed": 2 ** 31}, checked["used"])
    # Continued lines, quotes and comments are read as LAMMPS reads them.
    assert commands('print "a # b" # note\nfix 1 all &\n  nve\n') == [(1, ["print", "a # b"]), (2, ["fix", "1", "all", "nve"])]


def test_property_scripts_take_valid_numeric_row_parameters():
    from suan.lammps.templates import NAMES, template_text
    for name in NAMES:
        checked = check_script(template_text(name), ["in." + name, "model.in", "system.data"],
                               lambda _: "pair_style lj/cut 9\nread_data system.data\n")
        values = checked["parameters"]
        assert checked["units"] == "real"
        assert {"equilibration_steps", "sample_interval", "temperature", "steps", "timestep", "seed", "pressure"} <= set(values)
        assert check_parameters(values, checked["used"]) == values
        if name == "modulus":
            assert values["strain_rate"] == 1e-6
        if name == "diffusion":
            assert values["solute_type"] == 1 and "msd com no average no" in template_text(name)
        invalid = {**values, "sample_interval": values["steps"]}
        with pytest.raises(ScriptError, match="three sample intervals"):
            check_parameters(invalid, checked["used"])
        with pytest.raises(ScriptError):
            check_parameters({**values, "equilibration_steps": True}, checked["used"])
    with pytest.raises(ValueError):
        template_text("../../outside")


@pytest.mark.parametrize("line, message", [
    ("shell rm -rf data", "shell"),
    ("python source here", "python"),
    ("fix 2 all python/invoke 10 end_of_step f", "Python"),
    ("variable home getenv HOME", "environment"),
    ("plugin load ./x.so", "plugin"),
    ("log other.log", "'log'"),
    ("${command} anything", "written out"),
    ("read_data /etc/passwd", "inside the case folder"),
    ("write_data ../outside.data", "inside the case folder"),
    ("include other.in", "name a file of the case"),
    ("variable temperature equal 300", "index"),
    ("variable steps index many", "single integer"),
])
def test_commands_stk_does_not_run_are_refused(line, message):
    with pytest.raises(ScriptError, match=message):
        check_script("units real\n" + line + "\n", ["in.x"])


def test_the_log_of_a_real_lammps_run_is_read():
    """A trimmed log of LAMMPS 22 Jul 2025 (minimization, then NPT of a small PET model)."""
    text = (DATA / "pet-npt.log").read_text()
    log = read_log(text)
    assert log["version"] == "22 Jul 2025 - Update 6" and log["units"] == "real" and log["finished"]
    assert [len(block["rows"]) for block in log["blocks"]] == [2, 21] and log["warning_count"] == 4
    result = verify_log(text)
    assert result["verification"]["status"] == "passed", result
    qoi = result["qoi"]
    assert qoi["step"] == 85000 and qoi["samples"] == 11 and qoi["runs"] == 2
    assert qoi["density"] == pytest.approx(1.2225, abs=1e-4) and qoi["temperature"] == pytest.approx(297.4, abs=0.1)
    assert qoi["columns"] == ["Step", "Temp", "Press", "Density", "PotEng", "KinEng", "TotEng"]
    # A cut-off log, an error, and NaN are not results.
    cut = text[:text.rindex("Loop time of")]
    assert verify_log(cut)["classification"] == "incomplete_result"
    assert verify_log(text + "ERROR: Lost atoms: original 540 current 539\n")["classification"] == "invalid_result"
    assert verify_log(text.replace("1.2052615", "-nan"))["classification"] == "numerical_failure"
    assert verify_log(text, exit_code=1)["verification"]["status"] == "failed"


def test_the_task_spec_keeps_case_text_off_the_command_line():
    spec = lammps_spec("w" * 32, ranks=2, program="lmp_mpi", launcher="mpiexec")
    assert spec["argv"] == ["{python}", "-m", "suan.lammps", "run", "--case-dir", "case", "--ranks", "{ranks}",
                            "--threads-per-rank", "{threads_per_rank}", "--program", "lmp_mpi", "--launcher", "mpiexec"]
    assert spec["outputs"] == ["stk-lammps.json"]
    with pytest.raises(ValueError, match="walltime"):
        lammps_spec("w" * 32, backend="slurm")


def prepared(tmp_path, variables, script=SCRIPT):
    work = tmp_path / "work"
    case = write_case(work / "case", script)
    (case / "stk-lammps-input.json").write_text(json.dumps(
        {"format": "stk.lammps-input/1", "script": "in.npt", "variables": variables}))
    return work


def launch(work, *args, env=None):
    completed = subprocess.run([sys.executable, "-m", "suan.lammps", "run", "--case-dir", "case", *args], cwd=work,
                               capture_output=True, text=True, env={**os.environ, **(env or {})})
    return completed.returncode, json.loads((work / "stk-lammps.json").read_text())


@posix_only
def test_the_launcher_runs_a_prepared_case_and_verifies_its_log(tmp_path):
    program = make_fake_lammps(tmp_path / "bin")
    work = prepared(tmp_path, {"temperature": 350, "pressure": 1.0, "steps": 60, "seed": 11})
    code, record = launch(work, "--program", str(program))
    assert code == 0, record["reason"]
    assert record["state"] == "succeeded" and record["units"] == "real" and record["version"] == "2 Aug 2023 - Update 3"
    argv = json.loads((work / "case" / "fake-lammps.json").read_text())["argv"]
    assert argv[:5] == ["-in", "in.npt", "-log", "log.lammps", "-nocite"]
    assert argv[5:] == ["-var", "pressure", "1.0", "-var", "seed", "11", "-var", "steps", "60", "-var", "temperature", "350"]
    assert record["qoi"]["density"] == pytest.approx(1.38) and record["qoi"]["step"] == 60
    assert {item["path"] for item in record["outputs"]} == {"case/log.lammps", "case/final.data", "case/fake-lammps.json"}
    assert record["environment"]["OMP_NUM_THREADS"] == "1"


@posix_only
@pytest.mark.parametrize("mode, classification, code", [("nan", "numerical_failure", 3), ("error", "solver_failed", 3),
                                                         ("unfinished", "incomplete_result", 3)])
def test_failed_runs_are_reported_with_a_classification(tmp_path, mode, classification, code):
    program = make_fake_lammps(tmp_path / "bin", mode)
    work = prepared(tmp_path, {"temperature": 300, "pressure": 1, "steps": 40, "seed": 1})
    returned, record = launch(work, "--program", str(program))
    assert (returned, record["state"], record["classification"]) == (code, "failed", classification), record
    if mode == "error":
        assert "Lost atoms" in record["reason"]


@posix_only
def test_the_launcher_refuses_before_running(tmp_path):
    program = make_fake_lammps(tmp_path / "bin")
    # A script STK does not run, even when it reached the compute node.
    work = prepared(tmp_path, {}, script="units real\nshell touch owned\nrun 10\n")
    code, record = launch(work, "--program", str(program))
    assert code == 2 and "shell" in record["reason"] and not (work / "case" / "fake-lammps.json").exists()
    # Several ranks with a LAMMPS built without MPI would each run the whole case.
    work = prepared(tmp_path / "2", {"temperature": 300, "pressure": 1, "steps": 20, "seed": 1})
    code, record = launch(work, "--program", str(program), "--ranks", "2", "--launcher", "mpiexec",
                          env={"STK_ALLOW_LOCAL_MPI": "1"})
    assert code == 2 and "without MPI" in record["reason"] and not (work / "case" / "fake-lammps.json").exists()
    set_mode(program, "mpi")
    code, record = launch(work, "--program", str(program), "--ranks", "2", "--launcher", "mpiexec",
                          env={"PATH": str(tmp_path / "empty")})
    assert code == 2 and "0.0.0.0" in record["reason"]  # the local MPI guard, as for MuPRO
    # Outputs of an earlier run in the case folder.
    work = prepared(tmp_path / "3", {"temperature": 300, "pressure": 1, "steps": 20, "seed": 1})
    (work / "case" / "log.lammps").write_text("old")
    code, record = launch(work, "--program", str(program))
    assert code == 2 and "already holds LAMMPS outputs" in record["reason"]


@posix_only
def test_the_node_check_reports_program_packages_and_mpi(tmp_path):
    program = make_fake_lammps(tmp_path / "bin")
    completed = subprocess.run([sys.executable, "-m", "suan.lammps", "check", "--program", str(program), "--json"],
                               capture_output=True, text=True)
    report = {item["id"]: item for item in json.loads(completed.stdout)["checks"]}
    assert report["version"]["message"] == "2 Aug 2023 - Update 3" and report["packages"]["status"] == "pass"
    assert report["mpi_library"]["status"] == "warn"


@pytest.mark.parametrize("script, message", [
    ('if "1 > 0" then "shell touch x"\n', "shell"),
    ('if "1 > 0" then "print ok" elif "2 > 1" "log moved.log" else "print no"\n', "'log'"),
    ('run 10 every 5 "include /etc/x"\n', "inside the case folder"),
    ('variable g string get\nvariable h string env\nvariable x ${g}${h} HOME\n', "variable style must be written out"),
    ("variable temperature index 300 400 500\n", "single number"),
])
def test_quoted_commands_and_variable_tricks_are_checked(script, message):
    with pytest.raises(ScriptError, match=message):
        check_script("units real\n" + script, ["in.x"])


def test_includes_are_checked_to_any_depth_and_give_their_parameters():
    files = {"in.main": "include ./params.in\nunits real\nrun ${steps}\ninclude a.in\n",
             "params.in": "variable temperature index 450\n", "a.in": "include b.in\n", "b.in": "shell touch owned\n"}
    with pytest.raises(ScriptError, match="b.in line 1: STK does not run the 'shell'"):
        check_script(files["in.main"], list(files), files.__getitem__)
    files["b.in"] = "print done\n"
    checked = check_script(files["in.main"], list(files), files.__getitem__)
    assert checked["used"] == ["steps", "temperature"] and checked["parameters"] == {"steps": None, "temperature": 450}
    assert checked["includes"] == ["a.in", "b.in", "params.in"]
    # Ordinary scripts that mention the words or use LAMMPS's own syntax are not refused.
    check_script('region shell sphere 0 0 0 5\ngroup shell region shell\nprint """\nmany\nlines\n"""\n', ["in.x"])


def test_thermo_layouts_stk_does_not_read_are_named():
    text = (DATA / "pet-npt.log").read_text().replace(
        "   Step          Temp          Press         Density         PotEng         KinEng         TotEng    \n     65000",
        "------------ Step              0 ----- CPU =            0 (sec) -------------\n     65000")
    result = verify_log(text)
    assert result["classification"] == "invalid_result" and "thermo_style multi" in result["reason"]


def test_the_final_state_keeps_the_report_and_never_truncates():
    from suan.workflows.lammps import final_state
    names = ["case/in.lammps", "case/log.lammps", "case/traj.lammpstrj", "case/dump.atom.100", "case/restart.5000",
             "stk-lammps.json"] + [f"case/poly.{i}.restart" for i in range(120)]
    chosen = final_state(sorted(names))
    assert chosen[0] == "stk-lammps.json" and len(chosen) == 124
    assert "case/in.lammps" in chosen and "case/restart.5000" in chosen
    assert "case/traj.lammpstrj" not in chosen and "case/dump.atom.100" not in chosen


@posix_only
def test_a_run_that_overwrites_its_input_fails(tmp_path):
    program = make_fake_lammps(tmp_path / "bin", "overwrite")
    work = prepared(tmp_path, {"temperature": 300, "pressure": 1, "steps": 20, "seed": 1})
    code, record = launch(work, "--program", str(program))
    assert (code, record["classification"]) == (3, "invalid_result") and "overwrote its input system.data" in record["reason"]


@posix_only
def test_a_stopped_run_still_writes_its_report_and_verify_reads_a_log(tmp_path):
    import signal
    import time
    program = make_fake_lammps(tmp_path / "bin", "slow")
    work = prepared(tmp_path, {"temperature": 300, "pressure": 1, "steps": 20, "seed": 1})
    process = subprocess.Popen([sys.executable, "-m", "suan.lammps", "run", "--case-dir", "case", "--program", str(program)],
                               cwd=work, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(200):
        if (work / "case" / "fake-lammps.json").exists():  # LAMMPS has started
            break
        time.sleep(0.05)
    process.send_signal(signal.SIGTERM)
    assert process.wait(timeout=30) == 2
    record = json.loads((work / "stk-lammps.json").read_text())
    assert (record["state"], record["classification"]) == ("failed", "cancelled")
    set_mode(program, None)
    work = prepared(tmp_path / "done", {"temperature": 300, "pressure": 1, "steps": 20, "seed": 1})
    assert launch(work, "--program", str(program))[0] == 0
    completed = subprocess.run([sys.executable, "-m", "suan.lammps", "verify", "--work", str(work), "--case-dir", "case", "--json"],
                               capture_output=True, text=True)
    assert completed.returncode == 0 and json.loads(completed.stdout)["qoi"]["step"] == 20
