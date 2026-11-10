"""Configured local observations, without a real MuPRO installation or licence."""

from datetime import datetime
import importlib.metadata
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
from types import SimpleNamespace

from click.testing import CliRunner
import pytest

from suan.mupro import cli, run


CHECK_IDS = ("env_scripts", "sdk_prefix", "program", "shared_libraries", "mpi_launcher", "license_dir", "example_case")
UNVERIFIED = {"program_version": "unobserved", "license_checkout": "not_checked", "solver_execution": "not_run"}
LOCAL_MARKER = "low_entropy_private_fixture_abcdefghijklmnopqrstu"


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch, tmp_path):
    # Do not inspect or forward the user's SDK, credential or scheduler environment.
    environment = {"PATH": os.defpath, "LANG": "C.UTF-8", "STK_TOKEN_PLAN_API_KEY": "",
                   "PYTHONPYCACHEPREFIX": str(tmp_path / "bytecode")}
    monkeypatch.setattr(os, "environ", environment)
    return environment


def assert_observation(report, summary):
    assert set(report) == {"schema", "scope", "producer", "process_id", "started_at", "observed_at",
                           "summary", "checks", "unverified"}
    assert report["schema"] == "stk.mupro-preflight/1"
    assert report["scope"] == "local_process"
    assert report["summary"] == summary
    assert type(report["process_id"]) is int and report["process_id"] > 0
    started, observed = (datetime.fromisoformat(report[name]) for name in ("started_at", "observed_at"))
    assert started.tzinfo is not None and observed.tzinfo is not None and started <= observed
    assert set(report["producer"]) == {"component", "distribution_version"}
    assert report["producer"]["component"] == "suan.mupro"
    assert report["producer"]["distribution_version"] is None or isinstance(report["producer"]["distribution_version"], str)
    assert [item["id"] for item in report["checks"]] == list(CHECK_IDS)
    assert all(set(item) == {"id", "status"} for item in report["checks"])
    assert report["unverified"] == UNVERIFIED


@pytest.mark.parametrize("changes,summary", [
    ({}, "checks_passed"),
    ({"env_scripts": "pass"}, "checks_passed"),
    ({"shared_libraries": "skip"}, "checks_incomplete"),
    ({"example_case": "warn"}, "checks_incomplete"),
    ({"program": "fail", "shared_libraries": "skip", "example_case": "warn"}, "checks_failed"),
])
def test_projection_collects_once_closes_its_shape_and_preserves_status_meaning(monkeypatch, changes, summary):
    statuses = {name: "pass" for name in CHECK_IDS if name != "env_scripts"}
    statuses.update(changes)
    diagnostic = {"ok": "fail" not in statuses.values(), "checks": [
        {"id": name, "status": status, "message": f"/{LOCAL_MARKER}/{name}"}
        for name, status in statuses.items()]
    }
    calls = []
    args = SimpleNamespace()

    def collect(actual):
        assert actual is args
        calls.append(actual)
        assert len(calls) == 1, "Projection must not re-source configured scripts"
        return diagnostic

    monkeypatch.setattr(run, "check_toolchain", collect)
    report = run.preflight_observation(args)
    assert_observation(report, summary)
    assert report["process_id"] == os.getpid()
    assert {item["id"]: item["status"] for item in report["checks"]} == {
        "env_scripts": statuses.get("env_scripts", "not_configured"), **statuses}
    assert len(calls) == 1
    assert LOCAL_MARKER not in json.dumps(report)
    assert all("message" in item for item in diagnostic["checks"]), "Do not mutate legacy diagnostics"


def test_missing_distribution_metadata_is_an_explicit_null(monkeypatch):
    def absent(name):
        assert name == "suan_toolkits"
        raise importlib.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(importlib.metadata, "version", absent)
    monkeypatch.setattr(run, "check_toolchain", lambda _: {
        "ok": True, "checks": [{"id": name, "status": "pass", "message": "local"} for name in CHECK_IDS[1:]]})
    report = run.preflight_observation(SimpleNamespace())
    assert_observation(report, "checks_passed")
    assert report["producer"]["distribution_version"] is None


@pytest.mark.parametrize("as_json", [False, True])
def test_client_cli_forwards_only_local_options_and_collects_once(monkeypatch, as_json):
    def no_client(*args, **kwargs):
        pytest.fail("Local preflight must never construct a Runtime client")

    monkeypatch.setattr(cli, "get_client", no_client)
    captured = []

    def collect(args):
        captured.append(vars(args))
        assert len(captured) == 1
        return {"ok": True, "checks": [{"id": name, "status": "pass", "message": LOCAL_MARKER}
                                       for name in CHECK_IDS]}

    monkeypatch.setattr(run, "check_toolchain", collect)
    arguments = ["check", "--sdk-prefix", LOCAL_MARKER, "--program", "configured-muFerro",
                 "--env-script", "first.sh", "--env-script", "second.sh", "--license-dir", "configured-licence"]
    result = CliRunner().invoke(cli.mupro, arguments + (["--json"] if as_json else []))
    assert result.exit_code == 0, result.output
    assert captured == [{"sdk_prefix": LOCAL_MARKER, "program": "configured-muFerro",
                         "env_scripts": ["first.sh", "second.sh"], "license_dir": "configured-licence"}]
    assert LOCAL_MARKER not in result.output and "configured-licence" not in result.output
    if as_json:
        assert_observation(json.loads(result.output), "checks_passed")
    else:
        assert "local_process" in result.output and "checks_passed" in result.output
        assert "licence checkout not checked; solver not run" in result.output
        assert all(name in result.output for name in CHECK_IDS)


@pytest.fixture
def configured_toolchain(tmp_path, isolated_environment):
    if os.name == "nt":
        pytest.skip("The synthetic executable and sourced environment exercise POSIX node diagnostics")
    sdk = tmp_path / LOCAL_MARKER / "sdk"
    program = sdk / "bin/muFerro"
    example = sdk / run.EXAMPLES
    licence = tmp_path / "empty-licence"
    tools = tmp_path / "configured-bin"
    for folder in (program.parent, example, licence, tools):
        folder.mkdir(parents=True)
    solver_started, mpi_started = tmp_path / "solver-started", tmp_path / "mpi-started"
    for executable, marker in ((program, solver_started), (tools / "mpiexec", mpi_started)):
        executable.write_text(f"#!/bin/sh\nprintf started > {shlex.quote(str(marker))}\nexit 17\n")
        executable.chmod(0o700)
    for name in run.EXAMPLE_FILES:
        (example / name).write_text("")
    isolated_environment["PATH"] = str(tools) + os.pathsep + os.defpath
    args = SimpleNamespace(sdk_prefix=str(sdk), program=str(program), env_scripts=[], license_dir=str(licence), json=True)
    return SimpleNamespace(args=args, sdk=sdk, program=program, example=example, licence=licence,
                           solver_started=solver_started, mpi_started=mpi_started)


@pytest.mark.parametrize("missing_program", [False, True])
def test_legacy_module_json_and_exit_codes_remain_raw_diagnostics(configured_toolchain, capsys, missing_program):
    fixture = configured_toolchain
    if missing_program:
        fixture.program.unlink()
    expected = run.check_toolchain(fixture.args)
    arguments = ["check", "--sdk-prefix", fixture.args.sdk_prefix, "--program", fixture.args.program,
                 "--license-dir", fixture.args.license_dir, "--json"]
    assert run.main(arguments) == (1 if missing_program else 0)
    actual = json.loads(capsys.readouterr().out)
    assert actual == expected
    assert set(actual) == {"ok", "checks"}
    assert all(set(item) == {"id", "status", "message"} for item in actual["checks"])
    assert "env_scripts" not in {item["id"] for item in actual["checks"]}
    assert LOCAL_MARKER in json.dumps(actual)
    assert not fixture.solver_started.exists() and not fixture.mpi_started.exists()


def test_client_cli_failure_retains_the_versioned_observation(configured_toolchain):
    fixture = configured_toolchain
    fixture.program.unlink()
    result = CliRunner().invoke(cli.mupro, ["check", "--json", "--sdk-prefix", fixture.args.sdk_prefix,
        "--program", fixture.args.program, "--license-dir", fixture.args.license_dir])
    assert result.exit_code == 1
    report = json.loads(result.output)
    assert_observation(report, "checks_failed")
    assert next(item for item in report["checks"] if item["id"] == "program")["status"] == "fail"
    assert LOCAL_MARKER not in result.output
    assert not fixture.solver_started.exists() and not fixture.mpi_started.exists()


@pytest.mark.parametrize("condition,summary,changed_check,changed_status", [
    ("configured", "checks_incomplete", "env_scripts", "pass"),
    ("unconfigured", "checks_incomplete", "env_scripts", "not_configured"),
    ("missing_material", "checks_incomplete", "example_case", "warn"),
    ("missing_program", "checks_failed", "program", "fail"),
    ("env_failure", "checks_failed", "env_scripts", "fail"),
])
def test_real_configured_files_produce_observations_without_running_them(
        configured_toolchain, tmp_path, condition, summary, changed_check, changed_status):
    fixture = configured_toolchain
    counter = tmp_path / "sourced-scripts"
    first, second = tmp_path / "first.sh", tmp_path / "second.sh"
    first.write_text(f"printf 'first\\n' >> {shlex.quote(str(counter))}\nexport STK_PREFLIGHT_FIXTURE_STAGE=first\n")
    second.write_text(f"test \"$STK_PREFLIGHT_FIXTURE_STAGE\" = first || return 19\n"
                      f"printf 'second\\n' >> {shlex.quote(str(counter))}\n")
    if condition != "unconfigured":
        fixture.args.env_scripts = [str(first), str(second)]
    if condition == "missing_material":
        (fixture.example / "material.toml").unlink()
    elif condition == "missing_program":
        fixture.program.unlink()
    elif condition == "env_failure":
        second.write_text("return 23\n")
    report = run.preflight_observation(fixture.args)
    assert_observation(report, summary)
    statuses = {item["id"]: item["status"] for item in report["checks"]}
    assert statuses[changed_check] == changed_status
    assert statuses["shared_libraries"] == "skip", "A found script is not a validated native executable"
    assert statuses["license_dir"] == statuses["mpi_launcher"] == "pass"
    assert LOCAL_MARKER not in json.dumps(report) and str(tmp_path) not in json.dumps(report)
    assert not fixture.solver_started.exists() and not fixture.mpi_started.exists()
    expected = [] if condition == "unconfigured" else ["first"] if condition == "env_failure" else ["first", "second"]
    assert (counter.read_text().splitlines() if counter.exists() else []) == expected


@pytest.mark.parametrize("entry", ["module", "client"])
def test_real_cli_subprocess_needs_no_science_import_network_or_licence_contents(
        configured_toolchain, tmp_path, isolated_environment, entry):
    fixture = configured_toolchain
    driver, audit_file = tmp_path / "cli_driver.py", tmp_path / "audit.json"
    repo = Path(__file__).resolve().parents[1]
    driver.write_text(f'''import json,os,runpy,sys
from pathlib import Path
sys.path.insert(0,{str(repo)!r})
entry=sys.argv.pop(1)
licence=Path({str(fixture.licence)!r})
observed={{'subprocesses':[],'network_attempts':0,'licence_reads':0,'client_calls':0,'science_attempts':[]}}
class NoScience:
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[0] in ('numpy','h5py'):
            observed['science_attempts'].append(fullname)
            raise AssertionError('Preflight imported an optional scientific reader')
sys.meta_path.insert(0,NoScience())
def audit(event,args):
    if event.startswith('socket.'):
        observed['network_attempts']+=1
        raise AssertionError('Preflight attempted networking')
    if event=='subprocess.Popen':
        executable=Path(os.fsdecode(args[0])).name
        observed['subprocesses'].append(executable)
        assert executable in ('bash','ldd'), 'Preflight started a solver or MPI executable'
    if event in ('open','os.listdir','os.scandir') and isinstance(args[0],(str,bytes,os.PathLike)):
        target=Path(os.fsdecode(args[0])).absolute()
        if target==licence or licence in target.parents:
            observed['licence_reads']+=1
            raise AssertionError('Preflight read licence contents')
sys.addaudithook(audit)
from suan.mupro import cli
def no_client(*args,**kwargs):
    observed['client_calls']+=1
    raise AssertionError('Preflight constructed a Runtime client')
cli.get_client=no_client
try:
    if entry=='module':runpy.run_module('suan.mupro',run_name='__main__')
    else:
        sys.argv.insert(1,'mupro')
        runpy.run_module('suan.cli.main',run_name='__main__')
finally:
    observed['science_loaded']=[name for name in ('numpy','h5py') if name in sys.modules]
    Path({str(audit_file)!r}).write_text(json.dumps(observed))
''')
    arguments = [sys.executable, "-I", "-B", str(driver), entry, "check", "--json",
                 "--sdk-prefix", fixture.args.sdk_prefix, "--program", fixture.args.program,
                 "--license-dir", fixture.args.license_dir]
    process = subprocess.run(arguments, cwd=tmp_path, env=isolated_environment,
                             capture_output=True, text=True, timeout=20)
    assert process.returncode == 0, process.stderr
    report = json.loads(process.stdout)
    if entry == "client":
        assert_observation(report, "checks_incomplete")
        assert report["process_id"] != os.getpid()
        assert LOCAL_MARKER not in process.stdout
    else:
        assert set(report) == {"ok", "checks"} and report["ok"] is True
        assert LOCAL_MARKER in process.stdout
    audit = json.loads(audit_file.read_text())
    expected_processes = ["ldd"] if shutil.which("ldd", path=isolated_environment["PATH"]) else []
    assert audit == {"subprocesses": expected_processes, "network_attempts": 0, "licence_reads": 0,
                     "client_calls": 0, "science_attempts": [], "science_loaded": []}
    assert not fixture.solver_started.exists() and not fixture.mpi_started.exists()
