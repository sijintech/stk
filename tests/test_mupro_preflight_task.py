"""Compute-side preflight task: spec, artifact writer and parser, without a real MuPRO or licence."""

import copy
from datetime import datetime
import inspect
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
from types import SimpleNamespace

import pytest

from suan.mupro import preflight, run, spec
from suan.runtime.models import TaskSpec

REPO = Path(__file__).resolve().parents[1]
WORKSPACE = "a" * 32
MARKER = "low_entropy_private_fixture_abcdefghijklmnopqrstu"
CHECK_IDS = ("env_scripts", "sdk_prefix", "program", "shared_libraries", "mpi_launcher", "license_dir", "example_case")
UNVERIFIED = {"program_version": "unobserved", "license_checkout": "not_checked", "solver_execution": "not_run"}
VALID = {
    "schema": "stk.mupro-preflight/1", "scope": "local_process",
    "producer": {"component": "suan.mupro", "distribution_version": "0.0.0"},
    "process_id": 4242, "started_at": "2026-11-09T01:02:03.000004+00:00", "observed_at": "2026-11-09T01:02:04+00:00",
    "summary": "checks_incomplete",
    "checks": [{"id": "env_scripts", "status": "not_configured"}, {"id": "sdk_prefix", "status": "pass"},
               {"id": "program", "status": "pass"}, {"id": "shared_libraries", "status": "skip"},
               {"id": "mpi_launcher", "status": "pass"}, {"id": "license_dir", "status": "pass"},
               {"id": "example_case", "status": "pass"}],
    "unverified": dict(UNVERIFIED),
}
POSIX_ONLY = pytest.mark.skipif(os.name == "nt", reason=(
    "Real collector fixtures use a POSIX shebang program, sourced bash scripts and the Runtime's POSIX exec gate"))


def encode(value):
    return json.dumps(value).encode("utf-8")


def variant(change):
    value = copy.deepcopy(VALID)
    change(value)
    return value


def statuses(observation):
    return {item["id"]: item["status"] for item in observation["checks"]}


@pytest.fixture(autouse=True)
def parent_environment(monkeypatch, tmp_path):
    # The test process must not inspect or forward the user's SDK, credential or model settings.
    environment = {"PATH": os.defpath, "LANG": "C.UTF-8", "STK_TOKEN_PLAN_API_KEY": "",
                   "PYTHONPYCACHEPREFIX": str(tmp_path / "parent-bytecode")}
    monkeypatch.setattr(os, "environ", environment)
    return environment


# ---------------------------------------------------------------- spec

def test_preflight_spec_is_a_fixed_task_without_client_configuration():
    assert list(inspect.signature(spec.preflight_spec).parameters) == [
        "workspace_id", "backend", "walltime_seconds", "memory_mb", "queue", "account", "name"]
    task = spec.preflight_spec(WORKSPACE)
    assert task == {"workspace_id": WORKSPACE, "argv": ["{python}", "-m", "suan.mupro.preflight"],
                    "backend": "local", "name": "", "inputs": [], "outputs": [preflight.OBSERVATION_NAME],
                    "env": {}, "resources": {"cpus": 1}}
    # inputs=[] stages nothing; None would copy every workspace input into the task.
    assert TaskSpec(**task).to_dict() == task
    for option in ("ranks", "nodes", "launcher", "sdk_prefix", "program", "env_scripts", "license_dir", "env", "inputs"):
        with pytest.raises(TypeError):
            spec.preflight_spec(WORKSPACE, **{option: "x"})


def test_preflight_spec_forwards_only_supplied_scheduler_resources():
    task = spec.preflight_spec(WORKSPACE, backend="slurm", walltime_seconds=300, memory_mb=512,
                               queue="debug", account="group-a", name="node preflight")
    assert task["resources"] == {"cpus": 1, "walltime_seconds": 300, "memory_mb": 512,
                                 "queue": "debug", "account": "group-a"}
    assert task["backend"] == "slurm" and task["name"] == "node preflight" and task["env"] == {}
    assert spec.preflight_spec(WORKSPACE, backend="pbs", walltime_seconds=60)["resources"] == {
        "cpus": 1, "walltime_seconds": 60}
    assert spec.preflight_spec(WORKSPACE, walltime_seconds=30, memory_mb=64)["resources"] == {
        "cpus": 1, "walltime_seconds": 30, "memory_mb": 64}


@pytest.mark.parametrize("arguments,message", [
    ({"backend": "ssh"}, "backend must be local, pbs or slurm"),
    ({"backend": "slurm"}, "require walltime_seconds"),
    ({"backend": "pbs", "memory_mb": 64}, "require walltime_seconds"),
    ({"queue": "debug"}, "Local tasks do not allocate"),
    ({"account": "group-a"}, "Local tasks do not allocate"),
    ({"walltime_seconds": 0}, "walltime_seconds must be a positive integer"),
    ({"walltime_seconds": True}, "walltime_seconds must be a positive integer"),
    ({"walltime_seconds": "60"}, "walltime_seconds must be a positive integer"),
    ({"memory_mb": -1}, "memory_mb must be a positive integer"),
    ({"memory_mb": 1.5}, "memory_mb must be a positive integer"),
    ({"backend": "slurm", "walltime_seconds": 60, "queue": "bad queue"}, "Invalid queue"),
    ({"backend": "slurm", "walltime_seconds": 60, "account": ""}, "Invalid account"),
    ({"name": "x" * 201}, "Task name"),
])
def test_preflight_spec_rejects_invalid_requests_before_submission(arguments, message):
    with pytest.raises(ValueError, match=message):
        spec.preflight_spec(WORKSPACE, **arguments)


def test_preflight_spec_validates_the_workspace_while_muferro_spec_is_unchanged():
    with pytest.raises(ValueError, match="Invalid workspace ID"):
        spec.preflight_spec("not-a-workspace")
    # muferro_spec still leaves full validation to the Runtime on submission.
    legacy = spec.muferro_spec("not-a-workspace", ranks=2, backend="slurm", walltime_seconds=60)
    assert legacy == {"workspace_id": "not-a-workspace", "backend": "slurm", "name": "", "inputs": None,
                      "argv": ["{python}", "-m", "suan.mupro", "run", "--ranks", "{ranks}",
                               "--threads-per-rank", "{threads_per_rank}"],
                      "outputs": ["stk-mupro.json"], "env": {},
                      "resources": {"ranks": 2, "threads_per_rank": 1, "walltime_seconds": 60}}


# ---------------------------------------------------------------- parser

def test_parser_accepts_the_published_shape_and_returns_it():
    assert preflight.MAX_OBSERVATION_BYTES == 65536
    assert preflight.parse_observation(encode(VALID)) == VALID
    padded = encode(VALID) + b" " * (preflight.MAX_OBSERVATION_BYTES - len(encode(VALID)))
    assert len(padded) == preflight.MAX_OBSERVATION_BYTES
    assert preflight.parse_observation(bytearray(padded)) == VALID


@pytest.mark.parametrize("change", [
    lambda v: v["producer"].update(distribution_version=None),
    lambda v: v.update(started_at="2026-11-09T01:02:03Z", observed_at="2026-11-09T01:02:03.5+00:00"),
    # /1 records two clock readings; it does not promise wall-clock monotonicity.
    lambda v: v.update(started_at="2026-11-09T01:02:05+00:00", observed_at="2026-11-09T01:02:04+00:00"),
    lambda v: (v["checks"][3].update(status="pass"), v.update(summary="checks_passed")),
    lambda v: (v["checks"][0].update(status="fail"), v.update(summary="checks_failed")),
    lambda v: (v["checks"][4].update(status="warn"), v["checks"][3].update(status="pass")),
])
def test_parser_accepts_published_variations(change):
    value = variant(change)
    assert preflight.parse_observation(encode(value)) == value


def _replace_check(index, item):
    return lambda v: v["checks"].__setitem__(index, item)


REJECTED = {
    "extra private field": lambda v: v.update(host=MARKER),
    "missing field": lambda v: v.pop("observed_at"),
    "outer node claim": lambda v: v.update(node={"id": MARKER}),
    "producer extra": lambda v: v["producer"].update(path=MARKER),
    "producer component": lambda v: v["producer"].update(component=MARKER),
    "distribution version type": lambda v: v["producer"].update(distribution_version=1),
    "schema": lambda v: v.update(schema="stk.mupro-preflight/2"),
    "scope": lambda v: v.update(scope="remote_node"),
    "pid zero": lambda v: v.update(process_id=0),
    "pid bool": lambda v: v.update(process_id=True),
    "pid float": lambda v: v.update(process_id=4242.0),
    "pid string": lambda v: v.update(process_id="4242"),
    "naive time": lambda v: v.update(started_at="2026-11-09T01:02:03"),
    "non-UTC time": lambda v: v.update(observed_at="2026-11-09T09:02:04+08:00"),
    "unparseable time": lambda v: v.update(observed_at=MARKER),
    "time type": lambda v: v.update(started_at=1762650123),
    "check message": lambda v: v["checks"][1].update(message="/" + MARKER),
    "check order": lambda v: v["checks"].reverse(),
    "missing check": lambda v: v["checks"].pop(),
    "extra check": lambda v: v["checks"].append({"id": "gpu", "status": "pass"}),
    "check not object": _replace_check(2, "program"),
    "unknown status": _replace_check(2, {"id": "program", "status": "ok"}),
    "status not in table": _replace_check(2, {"id": "program", "status": "skip"}),
    "not_configured outside env_scripts": _replace_check(1, {"id": "sdk_prefix", "status": "not_configured"}),
    "status type": _replace_check(1, {"id": "sdk_prefix", "status": None}),
    "summary passed with skip": lambda v: v.update(summary="checks_passed"),
    "summary failed without fail": lambda v: v.update(summary="checks_failed"),
    "summary incomplete with fail": lambda v: v["checks"][2].update(status="fail"),
    "summary unknown": lambda v: v.update(summary="ready"),
    "summary list": lambda v: v.update(summary=[]),
    "summary object": lambda v: v.update(summary={}),
    "unverified changed": lambda v: v["unverified"].update(solver_execution="ran"),
    "unverified extra": lambda v: v["unverified"].update(license_file=MARKER),
    "unverified missing": lambda v: v["unverified"].pop("program_version"),
}


@pytest.mark.parametrize("name", REJECTED)
def test_parser_rejects_values_outside_the_closed_contract(name):
    with pytest.raises(ValueError) as caught:
        preflight.parse_observation(encode(variant(REJECTED[name])))
    assert str(caught.value).startswith("Invalid MuPRO preflight observation: ")
    assert MARKER not in str(caught.value)


BYTES_REJECTED = {
    "oversized": encode(VALID) + b" " * (preflight.MAX_OBSERVATION_BYTES + 1 - len(encode(VALID))),
    "truncated": encode(VALID)[:-7],
    "empty": b"",
    "invalid UTF-8": encode(VALID).replace(b'"0.0.0"', b'"\xff\xfe"'),
    "UTF-8 BOM": b"\xef\xbb\xbf" + encode(VALID),
    "top-level duplicate": encode(VALID)[:-1] + b', "summary": "checks_incomplete"}',
    "nested duplicate": encode(VALID).replace(b'"component": "suan.mupro"',
                                              b'"component": "suan.mupro", "component": "suan.mupro"'),
    "NaN": encode(VALID).replace(b'"process_id": 4242', b'"process_id": NaN'),
    "Infinity": encode(VALID).replace(b'"process_id": 4242', b'"process_id": Infinity'),
    "array": b"[" + encode(VALID) + b"]",
    "deep nesting": b"[" * 60000 + b"]" * 5000,
    "private trailing data": encode(VALID) + b"\n" + MARKER.encode(),
}


@pytest.mark.parametrize("name", BYTES_REJECTED)
def test_parser_rejects_malformed_bytes_with_static_messages(name):
    with pytest.raises(ValueError) as caught:
        preflight.parse_observation(BYTES_REJECTED[name])
    assert str(caught.value).startswith("Invalid MuPRO preflight observation: ")
    assert MARKER not in str(caught.value) and "4242" not in str(caught.value)
    # A JSONDecodeError would keep the whole document in its context.
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None or caught.value.__suppress_context__


@pytest.mark.parametrize("data", [json.dumps(VALID), None, memoryview(encode(VALID))])
def test_parser_consumes_bytes_only(data):
    with pytest.raises(ValueError, match="expected bytes"):
        preflight.parse_observation(data)


# ---------------------------------------------------------------- writer, with a controlled collector

@pytest.fixture
def collector(monkeypatch):
    state = SimpleNamespace(calls=[], observation=copy.deepcopy(VALID), error=None)

    def collect(args):
        state.calls.append(vars(args))
        if state.error:
            raise state.error
        return copy.deepcopy(state.observation)

    monkeypatch.setattr(run, "preflight_observation", collect)
    return state


@pytest.mark.parametrize("summary,changes,code", [
    ("checks_passed", {"shared_libraries": "pass"}, 0),
    ("checks_incomplete", {}, 0),
    ("checks_failed", {"program": "fail"}, 1),
])
def test_main_collects_once_with_defaults_and_writes_the_exact_observation(
        collector, tmp_path, monkeypatch, capsys, summary, changes, code):
    monkeypatch.chdir(tmp_path)
    collector.observation["checks"] = [{"id": i["id"], "status": changes.get(i["id"], i["status"])}
                                       for i in VALID["checks"]]
    collector.observation["summary"] = summary
    assert preflight.main([]) == code
    assert collector.calls == [{"sdk_prefix": None, "program": "muFerro", "env_scripts": [], "license_dir": None}]
    data = (tmp_path / preflight.OBSERVATION_NAME).read_bytes()
    assert json.loads(data.decode("utf-8")) == collector.observation
    assert preflight.parse_observation(data) == collector.observation
    assert os.listdir(tmp_path) == [preflight.OBSERVATION_NAME]
    output = capsys.readouterr()
    assert output.err == "" and summary in output.out


@pytest.mark.parametrize("arguments,code", [(["--help"], 0), (["--sdk-prefix", MARKER], 2), (["extra"], 2)])
def test_main_accepts_no_configuration_and_rejects_before_any_effect(collector, tmp_path, monkeypatch, arguments, code):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as stopped:
        preflight.main(arguments)
    assert stopped.value.code == code
    assert collector.calls == [] and os.listdir(tmp_path) == []


def _occupy(tmp_path, kind):
    target = tmp_path / preflight.OBSERVATION_NAME
    prior = tmp_path / "prior.json"
    if kind == "file":
        target.write_bytes(encode(VALID))
        return target, None
    if os.name == "nt":
        pytest.skip("Creating symlinks needs privileges on Windows")
    if kind == "symlink":
        prior.write_bytes(encode(VALID))
        target.symlink_to(prior)
    else:
        target.symlink_to(prior)
    return target, prior


@pytest.mark.parametrize("kind", ["file", "symlink", "dangling symlink"])
def test_occupied_output_is_rejected_before_collection_and_left_unchanged(collector, tmp_path, monkeypatch, capsys, kind):
    monkeypatch.chdir(tmp_path)
    target, prior = _occupy(tmp_path, kind)
    before = os.readlink(target) if prior else target.read_bytes()
    assert preflight.main([]) == 2
    assert collector.calls == []
    assert (os.readlink(target) if prior else target.read_bytes()) == before
    if kind == "symlink":
        assert prior.read_bytes() == encode(VALID)
    if kind == "dangling symlink":
        assert not prior.exists()
    assert "already exists" in capsys.readouterr().err


def test_a_previous_success_is_never_reused(collector, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    collector.observation["summary"] = "checks_passed"
    collector.observation["checks"][3]["status"] = "pass"
    assert preflight.main([]) == 0
    first = (tmp_path / preflight.OBSERVATION_NAME).read_bytes()
    collector.observation = copy.deepcopy(VALID)
    assert preflight.main([]) == 2
    assert len(collector.calls) == 1
    assert (tmp_path / preflight.OBSERVATION_NAME).read_bytes() == first


@pytest.mark.parametrize("failure", ["exception", "invalid observation", "write"])
def test_infrastructure_failure_leaves_no_observation_and_no_raw_diagnostic(
        collector, tmp_path, monkeypatch, capsys, failure):
    monkeypatch.chdir(tmp_path)
    if failure == "exception":
        collector.error = RuntimeError(f"/{MARKER}/env.sh returned 7")
    elif failure == "invalid observation":
        collector.observation["host"] = MARKER
    else:
        def broken(*_):
            raise OSError(28, f"No space left /{MARKER}")
        monkeypatch.setattr(os, "fsync", broken)
    assert preflight.main([]) == 3
    assert os.listdir(tmp_path) == []
    output = capsys.readouterr()
    assert MARKER not in output.out + output.err and "no observation was written" in output.err


@POSIX_ONLY
def test_failure_cleanup_does_not_remove_a_replaced_file(collector, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    def replace_then_fail(args):
        os.replace(tmp_path / "other", tmp_path / preflight.OBSERVATION_NAME)
        raise RuntimeError("collection failed")

    (tmp_path / "other").write_bytes(b"foreign")
    monkeypatch.setattr(run, "preflight_observation", replace_then_fail)
    assert preflight.main([]) == 3
    assert (tmp_path / preflight.OBSERVATION_NAME).read_bytes() == b"foreign"


# ---------------------------------------------------------------- real child processes (POSIX)

@pytest.fixture
def node(tmp_path):
    """A synthetic configured worker environment: SDK, scripts and licence path, no real MuPRO."""
    sdk = tmp_path / MARKER / "sdk"
    program, example = sdk / "bin" / "muFerro", sdk / run.EXAMPLES
    licence, tools = tmp_path / MARKER / "licence", tmp_path / "script-bin"
    for folder in (program.parent, example, licence, tools):
        folder.mkdir(parents=True)
    solver_started, mpi_started = tmp_path / "solver-started", tmp_path / "mpi-started"
    for executable, marker in ((program, solver_started), (tools / "mpiexec", mpi_started)):
        executable.write_text(f"#!/bin/sh\nprintf started > {shlex.quote(str(marker))}\nexit 17\n")
        executable.chmod(0o700)
    for name in run.EXAMPLE_FILES:
        (example / name).write_text("")
    (licence / "licence.dat").write_text(MARKER)
    counter = tmp_path / "sourced"
    script = tmp_path / MARKER / "env.sh"
    # mpiexec is only reachable through the sourced script: a pass proves the child sourced it.
    script.write_text(f"printf 'sourced\\n' >> {shlex.quote(str(counter))}\n"
                      f"export PATH={shlex.quote(str(tools))}:\"$PATH\"\n")
    work = tmp_path / "task" / "work"
    work.mkdir(parents=True)
    base = {"PATH": os.defpath, "LANG": "C.UTF-8", "STK_TOKEN_PLAN_API_KEY": "",
            "PYTHONPYCACHEPREFIX": str(tmp_path / "child-bytecode"), "PYTHONPATH": str(REPO)}
    configured = {**base, "MUPRO_SDK_PREFIX": str(sdk), "MUPROROOT": str(licence), "STK_MUPRO_ENV_SCRIPTS": str(script)}
    return SimpleNamespace(sdk=sdk, program=program, example=example, licence=licence, script=script,
                           counter=counter, work=work, base=base, configured=configured,
                           solver_started=solver_started, mpi_started=mpi_started)


def _child_module(environment, module):
    probe = subprocess.run([sys.executable, "-c", f"import {module} as m; print(m.__file__)"],
                           cwd=environment.get("PWD", "/"), env=environment, capture_output=True, text=True, timeout=20)
    return probe.stdout.strip()


def _run_task(node, environment):
    """Execute the preflight TaskSpec through the Runtime's own worker program, as a backend does."""
    root = node.work.parent
    task = TaskSpec(**spec.preflight_spec(WORKSPACE)).to_dict()
    (root / "launch.json").write_text(json.dumps({"task_id": "preflight-test", "spec": task, "python": sys.executable}))
    shutil.copyfile(REPO / "suan" / "runtime" / "worker.py", root / "worker.py")
    process = subprocess.run([sys.executable, str(root / "worker.py"), str(root)], cwd=root, env=environment,
                             stdin=subprocess.DEVNULL, capture_output=True, timeout=60)
    finished = json.loads((root / "finished.json").read_text())
    logs = (root / "stdout.log").read_bytes() + (root / "stderr.log").read_bytes()
    return process, finished, logs, root


@POSIX_ONLY
@pytest.mark.parametrize("child", ["configured", "unconfigured"])
def test_runtime_worker_runs_the_task_against_the_childs_own_configuration(node, parent_environment, child):
    assert _child_module(node.base, "suan.mupro.preflight").startswith(str(REPO / "suan")), \
        "The child must import this tree, not another installed checkout"
    # The parent is configured the opposite way; the artifact must describe the child.
    if child == "unconfigured":
        parent_environment.update({k: v for k, v in node.configured.items() if k not in node.base})
    parent = run.preflight_observation(SimpleNamespace(sdk_prefix=None, program="muFerro", env_scripts=[],
                                                       license_dir=None))
    node.counter.unlink(missing_ok=True)
    environment = node.configured if child == "configured" else node.base
    process, finished, logs, root = _run_task(node, environment)
    assert process.returncode == (0 if child == "configured" else 1), process.stderr
    artifact = root / "work" / preflight.OBSERVATION_NAME
    data = artifact.read_bytes()
    observation = preflight.parse_observation(data)
    # The worker execs the program in place, so the recorded program PID is the collector's PID.
    assert observation["process_id"] == json.loads((root / "program.json").read_text())["pid"] != os.getpid()
    if child == "configured":
        assert parent["summary"] == "checks_failed"
        assert finished["state"] == "succeeded" and finished["exit_code"] == 0
        assert observation["summary"] == "checks_incomplete"
        assert statuses(observation) == {"env_scripts": "pass", "sdk_prefix": "pass", "program": "pass",
                                         "shared_libraries": "skip", "mpi_launcher": "pass",
                                         "license_dir": "pass", "example_case": "pass"}
        assert node.counter.read_text().splitlines() == ["sourced"]
    else:
        assert parent["summary"] == "checks_incomplete" and statuses(parent)["mpi_launcher"] == "pass"
        # A failed check is a failed task that still leaves its valid observation artifact.
        assert finished["state"] == "failed" and finished["exit_code"] == 1
        assert observation["summary"] == "checks_failed"
        assert statuses(observation) == {"env_scripts": "not_configured", "sdk_prefix": "fail", "program": "fail",
                                         "shared_libraries": "skip", "mpi_launcher": "warn",
                                         "license_dir": "warn", "example_case": "warn"}
        assert not node.counter.exists()
    assert sorted(os.listdir(root / "work")) == [preflight.OBSERVATION_NAME]
    for text in (data, logs):
        assert MARKER.encode() not in text and str(node.sdk.parent).encode() not in text
    assert not node.solver_started.exists() and not node.mpi_started.exists()
    assert (node.licence / "licence.dat").read_text() == MARKER


@POSIX_ONLY
def test_an_older_compute_package_without_the_module_fails_without_any_observation(node, tmp_path):
    old = tmp_path / "old-install"
    (old / "suan" / "mupro").mkdir(parents=True)
    (old / "suan" / "__init__.py").write_text("")
    (old / "suan" / "mupro" / "__init__.py").write_text("")
    called = tmp_path / "old-collector-called"
    (old / "suan" / "mupro" / "run.py").write_text(
        f"def preflight_observation(args):\n    open({str(called)!r}, 'w').close()\n")
    environment = {**node.configured, "PYTHONPATH": str(old)}
    process, finished, logs, root = _run_task(node, environment)
    assert finished["state"] == "failed" and finished["exit_code"] not in (0, None)
    assert os.listdir(root / "work") == []
    assert b"No module named suan.mupro.preflight" in logs
    assert not called.exists() and not node.counter.exists()


@POSIX_ONLY
@pytest.mark.parametrize("kind", ["file", "symlink", "dangling symlink"])
def test_real_child_rejects_an_occupied_output_before_sourcing_scripts(node, kind):
    target, prior = _occupy(node.work, kind)
    before = os.readlink(target) if prior else target.read_bytes()
    process = subprocess.run([sys.executable, "-m", "suan.mupro.preflight"], cwd=node.work, env=node.configured,
                             capture_output=True, text=True, timeout=30)
    assert process.returncode == 2
    assert not node.counter.exists(), "The configured script was sourced before the output was reserved"
    assert (os.readlink(target) if prior else target.read_bytes()) == before
    if kind == "dangling symlink":
        assert not prior.exists()
    assert MARKER not in process.stdout + process.stderr


@POSIX_ONLY
def test_real_child_needs_no_science_import_network_solver_mpi_or_licence_contents(node, tmp_path):
    driver, audit_file = tmp_path / "driver.py", tmp_path / "audit.json"
    driver.write_text(f'''import json,os,runpy,sys
from pathlib import Path
sys.path.insert(0,{str(REPO)!r})
licence=Path({str(node.licence)!r})
observed={{'subprocesses':[],'network_attempts':0,'licence_reads':0,'science_attempts':[]}}
class NoScience:
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[0] in ('numpy','h5py','torch'):
            observed['science_attempts'].append(fullname)
            raise AssertionError('Preflight imported an optional scientific package')
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
import importlib.util
observed['module']=importlib.util.find_spec('suan.mupro.preflight').origin
code=0
try:
    sys.argv=['preflight']
    runpy.run_module('suan.mupro.preflight',run_name='__main__')
except SystemExit as stop:
    code=stop.code
finally:
    observed['science_loaded']=[name for name in ('numpy','h5py','torch') if name in sys.modules]
    Path({str(audit_file)!r}).write_text(json.dumps(observed))
sys.exit(code)
''')
    # -I ignores PYTHONPYCACHEPREFIX, so keep bytecode outside the tree explicitly.
    process = subprocess.run([sys.executable, "-I", "-X", f"pycache_prefix={tmp_path / 'driver-bytecode'}",
                              str(driver)], cwd=node.work, env=node.configured,
                             capture_output=True, text=True, timeout=30)
    assert process.returncode == 0, process.stderr
    audit = json.loads(audit_file.read_text())
    assert audit.pop("module").startswith(str(REPO / "suan"))
    expected = ["bash"] + (["ldd"] if shutil.which("ldd", path=node.configured["PATH"]) else [])
    assert audit == {"subprocesses": expected, "network_attempts": 0, "licence_reads": 0,
                     "science_attempts": [], "science_loaded": []}
    observation = preflight.parse_observation((node.work / preflight.OBSERVATION_NAME).read_bytes())
    assert observation["summary"] == "checks_incomplete"
    started, observed = (datetime.fromisoformat(observation[k]) for k in ("started_at", "observed_at"))
    assert started.tzinfo is not None and observed.tzinfo is not None
    assert MARKER not in process.stdout + process.stderr
    assert not node.solver_started.exists() and not node.mpi_started.exists()
