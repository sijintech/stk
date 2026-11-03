"""Actual persistent headless/graph-worker/Report-1 integration; manufactured science only."""
import hashlib
import http.client
import importlib.util
import json
import os
from pathlib import Path
import socket
import stat
import subprocess
import sys
import time
from uuid import uuid4
import zipfile

import pytest

from suan.desktop_bridge.graph_worker import GraphWorker
from suan.models.local import LocalModels
from suan.project.request_executor import RequestExecutor
from suan.project.reports import TABLE_ID as REPORT_TABLE, FIELD_IDS as REPORT_FIELDS
from suan.reproduction import ComparisonError, verify
from suan.scripting import ProjectAnalysisRuns, ProjectReports, ScriptError
from suan.scripting.headless import connect

EXAMPLE = Path(__file__).with_name("offline.py")
if not EXAMPLE.exists():
    EXAMPLE = Path(__file__).parents[1] / "examples/reproduction_comparison/offline.py"
spec = importlib.util.spec_from_file_location("reproduction_workflow_example", EXAMPLE)
demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo)


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    # Discovery does not import Matplotlib or inspect its user configuration.
    # Actual rendering occurs only in the guarded worker with private MPLCONFIGDIR.
    for package in ("numpy", "matplotlib"):
        if importlib.util.find_spec(package) is None:
            pytest.fail("Integration validation requires the declared renderer dependency: " + package)
    monkeypatch.setenv("STK_TOKEN_PLAN_API_KEY", "")
    monkeypatch.delenv("STK_TOKEN_PLAN_MODEL", raising=False)
    guard = tmp_path / "guard"
    guard.mkdir()
    log = tmp_path / "guard.jsonl"
    # Real subprocesses load this guard too. It does not replace the GraphWorker,
    # evaluator, node, Table sources, renderer or any returned DTO.
    (guard / "sitecustomize.py").write_text(
        "import json, os, sys\n"
        "assert os.environ.get('STK_TOKEN_PLAN_API_KEY') == ''\n"
        "assert 'STK_TOKEN_PLAN_MODEL' not in os.environ\n"
        "with open(os.environ['STK_EXAMPLE_GUARD_LOG'], 'a') as f: f.write(json.dumps({'pid':os.getpid(),'loaded':True})+'\\n')\n"
        "def audit(event, args):\n"
        "    if event.startswith('socket.'):\n"
        "        with open(os.environ['STK_EXAMPLE_GUARD_LOG'], 'a') as f: f.write(json.dumps({'pid':os.getpid(),'blocked':event})+'\\n')\n"
        "        raise RuntimeError('offline socket guard')\n"
        "sys.addaudithook(audit)\n", encoding="utf-8")
    repo = Path(__file__).parents[1] if not EXAMPLE.parent.samefile(Path(__file__).parent) else Path.cwd()
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join((str(guard), str(repo))))
    monkeypatch.setenv("STK_EXAMPLE_GUARD_LOG", str(log))
    calls = []
    real_evaluate = GraphWorker.evaluate
    def evaluate(self, *args, **kwargs):
        calls.append(args[0])
        return real_evaluate(self, *args, **kwargs)
    monkeypatch.setattr(GraphWorker, "evaluate", evaluate)
    def forbidden(*args, **kwargs):
        pytest.fail("An offline example attempted a socket/model/autostart request")
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(http.client.HTTPConnection, "request", forbidden)
    monkeypatch.setattr(RequestExecutor, "start", forbidden)
    monkeypatch.setattr(LocalModels, "autostart", forbidden)
    with demo.private_environment(tmp_path / "private"):
        with connect(tmp_path / "private/service") as stk:
            sentinel = stk.use(stk.projects.create(tmp_path / "visible-sentinel", "Untouched current project"))
            before = sentinel.snapshot(), sentinel.history()
            yield stk, calls, log
            assert stk.project.handle == sentinel.handle
            assert (sentinel.snapshot(), sentinel.history()) == before


def prepare(stk, tmp_path):
    directory = tmp_path / "comparison"
    identities = {name: str(uuid4()) for name in ("analysis_id", "run_id", "report_id")}
    receipt = demo.prepare_demo(stk, directory, **identities)
    assert all(receipt[key] == value for key, value in identities.items())
    return directory, receipt


def completed(isolated, tmp_path):
    stk, calls, log = isolated
    directory, receipt = prepare(stk, tmp_path)
    result = demo.start_demo(stk, directory, wait_seconds=30)
    assert result["execution_status"] == "succeeded" and not result["observation_timed_out"]
    assert len(calls) == 1
    return stk, calls, log, directory, receipt


def publish(stk, directory, destination):
    demo.create_report(stk, directory)
    return demo.export_report(stk, directory, destination)


def archive_files(directory, receipt):
    root = directory / ".stk/analysis-runs" / receipt["run_id"] / "result"
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in root.rglob("*") if path.is_file()}


def test_prepare_and_repeated_reads_recover_do_not_execute_or_change_frozen_intent(isolated, tmp_path):
    stk, calls, _ = isolated
    directory, receipt = prepare(stk, tmp_path)
    p = stk.projects.open(directory, expected_id=receipt["project_id"])
    history = p.history()
    intent = (directory / "run-request.json").read_bytes()
    assert json.loads(intent)["request"]["run_id"] == receipt["run_id"]
    for _ in range(2):
        assert demo.read_demo(stk, directory)["execution_status"] == "prepared"
        assert p.analysis_runs.recover(receipt["run_id"])["status"] == "prepared"
    assert not calls and not (directory / "start-intent.json").exists()
    assert p.history() == history and (directory / "run-request.json").read_bytes() == intent
    frozen = p.analysis_runs.get(receipt["run_id"])["document"]
    assert frozen == demo.definition()
    for node in frozen["graph"]["nodes"]:
        if node["type"] == "stk.analysis.reproduction_compare@1":
            assert node["params"]["absolute"] == .25 and node["params"]["relative"] == 0


def test_actual_analysis_archives_five_outcomes_error_rows_pngs_and_guarded_child(isolated, tmp_path):
    stk, calls, log, directory, receipt = completed(isolated, tmp_path)
    result = demo.read_demo(stk, directory)
    assert result["comparison_statuses"] == demo.EXPECTED and result["verified_archive"]
    p, _, run = demo._opened(stk, directory)
    archive = p.analysis_runs.result(receipt["run_id"])
    manifest = (Path(archive["blob_dir"]).parent / "graph-result.json").read_bytes()
    assert hashlib.sha256(manifest).hexdigest() == run["result"]["manifest_sha256"]
    for case in demo.CASES:
        value, errors = demo._output(archive, case), demo._output(archive, case + "_errors")
        assert verify(value) and len(value["result"]["points"]) == 3
        assert errors["type"] == "table" and errors["column_names"][0] == "reference_index"
        assert errors["units"]["absolute_error"] == "m"
    missing = demo._output(archive, "missing_rows")
    assert missing["plan"]["actual"]["source"]["columns"]["value"]["values"] == [0.0,"NaN",4.0]
    assert [p["status"] for p in missing["plan"]["actual"]["points"]] == ["ok","missing","failed"]
    assert missing["result"]["metrics"]["compared_samples"] == 1
    missing_errors = demo._output(archive, "missing_rows_errors")["columns"]
    assert missing_errors["actual"] == [0.0, "NaN", 4.0]
    assert missing_errors["absolute_error"] == [0.0, "NaN", "NaN"]
    assert [point["absolute_error"] for point in missing["result"]["points"]] == [0.0, None, None]
    within_errors = demo._output(archive, "within_tolerance_errors")["columns"]
    assert within_errors["reference"] == [0.0, 2.0, 4.0]
    assert within_errors["actual"] == [0.125, 2.125, 4.125]
    assert within_errors["signed_error"] == within_errors["absolute_error"] == [.125]*3
    assert within_errors["allowed_error"] == [.25]*3
    outside_errors = demo._output(archive, "outside_tolerance_errors")["columns"]
    assert outside_errors["signed_error"] == outside_errors["absolute_error"] == [.5]*3
    assert "actual_run_failed" in demo._output(archive,"failed_run")["result"]["reasons"]
    assert "unit_mismatch" in demo._output(archive,"unit_mismatch")["result"]["reasons"]
    for name in ("curves", "errors"):
        output = archive["result"]["outputs"][name]
        raw = demo._blob(archive, output["blob"], output["size"])
        assert raw[:8] == b"\x89PNG\r\n\x1a\n" and len(raw) > 1000
        data = json.loads(demo._blob(archive, archive["result"]["outputs"][name + "_plot"]["data_blob"]))
        assert data["schema"] == "stk.plot-data/1"
        names = ["reference", "actual"] if name == "curves" else ["absolute_error", "allowed_error"]
        expected = [[0., 2., 4.], [.125, 2.125, 4.125]] if name == "curves" else [[.125]*3, [.25]*3]
        assert [mark["columns"] for mark in data["marks"]] == [{"x":"x", "y":name} for name in names]
        assert [mark["data"] for mark in data["marks"]] == [{"x":[0.,1.,2.],"y":values} for values in expected]
    events = [json.loads(line) for line in log.read_text().splitlines()]
    assert any(event["loaded"] for event in events) and not any("blocked" in event for event in events)
    assert len(calls) == 1


def test_socket_guard_really_rejects_a_subprocess_connection(isolated):
    _, _, log = isolated
    result = subprocess.run([sys.executable, "-c", "import socket; socket.socket()"], capture_output=True, timeout=10)
    assert result.returncode != 0 and b"offline socket guard" in result.stderr
    assert any("blocked" in json.loads(line) for line in log.read_text().splitlines())


def test_read_recover_and_headless_reopen_do_not_reexecute_or_rewrite_archive(isolated, tmp_path, monkeypatch):
    stk, calls, _, directory, receipt = completed(isolated, tmp_path)
    before = archive_files(directory, receipt)
    p = stk.projects.open(directory, expected_id=receipt["project_id"])
    history, frozen_run = p.history(), p.analysis_runs.get(receipt["run_id"])
    def no_start(*args, **kwargs):
        pytest.fail("A read/recovery path dispatched execution")
    monkeypatch.setattr(ProjectAnalysisRuns, "start", no_start)
    monkeypatch.setattr(GraphWorker, "evaluate", no_start)
    for _ in range(2):
        assert demo.read_demo(stk, directory)["verified_archive"]
        assert p.analysis_runs.recover(receipt["run_id"]) == frozen_run
    p.close()
    with connect(tmp_path / "private/reopened-service") as reopened:
        assert demo.read_demo(reopened, directory)["run_id"] == receipt["run_id"]
        history2 = reopened.projects.open(directory).history()
        assert history2 == history
    assert archive_files(directory, receipt) == before and len(calls) == 1


def test_real_report_source_export_exact_bytes_and_reopen(isolated, tmp_path):
    stk, calls, _, directory, receipt = completed(isolated, tmp_path)
    destination = tmp_path / "evidence.zip"
    summary = publish(stk, directory, destination)
    assert hashlib.sha256(destination.read_bytes()).hexdigest() == summary["export_sha256"]
    assert summary["export_size"] == destination.stat().st_size and summary["assets"] == 18
    p, _, run = demo._opened(stk, directory)
    report = p.reports.get(receipt["report_id"])["report"]
    source = report["manifest"]["sources"][0]
    assert source["kind"] == "analysis_run" and source["id"] == run["id"]
    assert source["plan_sha256"] == run["plan_sha256"] and source["project_id"] == receipt["project_id"]
    assert source["captured_status"]["status"] == "succeeded"
    assert source["captured_status"]["result"]["manifest_sha256"] == run["result"]["manifest_sha256"]
    with zipfile.ZipFile(destination) as bundle:
        envelope = json.loads(bundle.read("stk-report.json"))
        assert envelope["manifest"] == report["manifest"]
        assert hashlib.sha256(bundle.read("graph-result.json.txt")).hexdigest() == run["result"]["manifest_sha256"]
        for case in demo.CASES:
            comparison = json.loads(bundle.read(case + ".json.txt"))
            assert verify(comparison) and comparison["result"]["status"] == demo.EXPECTED[case]
        for asset in report["manifest"]["assets"]:
            raw = bundle.read(asset["path"])
            assert hashlib.sha256(raw).hexdigest() == asset["sha256"] and len(raw) == asset["size"]
        assert b"not paper" in bundle.read("report.md")
    with connect(tmp_path / "private/report-reopen") as reopened:
        assert demo.read_demo(reopened, directory)["report_source_sha256"] == report["source_sha256"]
    assert len(calls) == 1


def test_live_working_files_do_not_replace_frozen_inputs_or_report_assets(isolated, tmp_path):
    stk, calls, _, directory, receipt = completed(isolated, tmp_path)
    publish(stk, directory, tmp_path / "evidence.zip")
    before = demo.read_demo(stk, directory)
    for name in demo.INPUTS:
        (directory / name).write_bytes(b"edited working input")
    for path in (directory / "report-evidence").iterdir():
        path.write_bytes(b"edited working report")
    assert demo.read_demo(stk, directory) == before and len(calls) == 1


def test_lost_start_response_retains_original_identity_and_does_not_replay(isolated, tmp_path, monkeypatch):
    stk, calls, _ = isolated
    directory, receipt = prepare(stk, tmp_path)
    original = ProjectAnalysisRuns.start
    def lose_reply(self, identity):
        original(self, identity)
        raise RuntimeError("manufactured lost start reply")
    monkeypatch.setattr(ProjectAnalysisRuns, "start", lose_reply)
    with pytest.raises(RuntimeError, match="lost start reply"):
        demo.start_demo(stk, directory)
    intent = json.loads((directory / "start-intent.json").read_bytes())
    assert intent["run_id"] == receipt["run_id"] and intent["plan_sha256"] == receipt["plan_sha256"]
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        result = demo.read_demo(stk, directory)
        if result["execution_status"] not in demo.ACTIVE:
            break
        time.sleep(.05)
    assert result["verified_archive"] and len(calls) == 1
    with pytest.raises(ValueError, match="already started"):
        demo.start_demo(stk, directory)


def test_lost_prepare_reply_is_read_back_by_exact_original_request_without_forged_ack(isolated, tmp_path, monkeypatch):
    stk, calls, _ = isolated
    original = ProjectAnalysisRuns.prepare
    attempts = []
    def lose_reply(self, *args, **kwargs):
        attempts.append(kwargs["run_id"])
        original(self, *args, **kwargs)
        raise RuntimeError("manufactured lost prepare reply")
    monkeypatch.setattr(ProjectAnalysisRuns, "prepare", lose_reply)
    directory = tmp_path / "comparison"
    identities = {key: str(uuid4()) for key in ("analysis_id", "run_id", "report_id")}
    with pytest.raises(RuntimeError, match="lost prepare reply"):
        demo.prepare_demo(stk, directory, **identities)
    note_before = (directory / "run-request.json").read_bytes()
    assert not (directory / "prepared.json").exists() and not calls
    p = stk.projects.open(directory, expected_id=json.loads(note_before)["identity"]["project_id"])
    history = p.history()
    for _ in range(2):
        observed = demo.read_demo(stk, directory)
        assert observed["run_id"] == identities["run_id"] and observed["execution_status"] == "prepared"
        assert observed["prepare_response_received"] is False
        assert p.analysis_runs.recover(identities["run_id"])["status"] == "prepared"
    with connect(tmp_path / "private/prepare-reopen") as reopened:
        assert demo.read_demo(reopened, directory) == observed
    assert attempts == [identities["run_id"]] and not calls
    assert p.history() == history and not (directory / "prepared.json").exists()
    assert (directory / "run-request.json").read_bytes() == note_before
    # A separate, explicit start still uses that exact original run, never a new UUID.
    assert demo.start_demo(stk, directory, wait_seconds=30)["execution_status"] == "succeeded"
    assert demo.read_demo(stk, directory)["verified_archive"] and len(calls) == 1


def test_unaccepted_prepare_remains_not_found_and_is_never_replayed(isolated, tmp_path, monkeypatch):
    stk, calls, _ = isolated
    attempts = []
    def unavailable(self, *args, **kwargs):
        attempts.append(kwargs["run_id"])
        raise RuntimeError("manufactured unavailable before prepare")
    monkeypatch.setattr(ProjectAnalysisRuns, "prepare", unavailable)
    directory = tmp_path / "comparison"
    identities = {key: str(uuid4()) for key in ("analysis_id", "run_id", "report_id")}
    with pytest.raises(RuntimeError, match="before prepare"):
        demo.prepare_demo(stk, directory, **identities)
    for _ in range(2):
        with pytest.raises(ScriptError) as error:
            demo.read_demo(stk, directory)
        assert error.value.code == "not_found"
    assert attempts == [identities["run_id"]] and not calls and not (directory / "prepared.json").exists()


@pytest.mark.parametrize("field", ["run_id", "analysis_id", "snapshot_id", "expected_revision", "bindings"])
def test_changed_prepare_request_is_rejected_without_execution(isolated, tmp_path, field):
    stk, calls, _ = isolated
    directory, _ = prepare(stk, tmp_path)
    path = directory / "run-request.json"
    note = json.loads(path.read_bytes())
    note["request"][field] = {} if field == "bindings" else 99 if field == "expected_revision" else str(uuid4())
    note["request_sha256"] = hashlib.sha256(demo._json(note["request"])).hexdigest()
    path.write_bytes(demo._json(note))
    with pytest.raises(ValueError, match="request note changed"):
        demo.read_demo(stk, directory)
    assert not calls


def test_lost_report_create_response_is_recovered_by_original_uuid_only(isolated, tmp_path, monkeypatch):
    stk, calls, _, directory, receipt = completed(isolated, tmp_path)
    original = ProjectReports.create
    def lose_reply(self, *args, **kwargs):
        original(self, *args, **kwargs)
        raise RuntimeError("manufactured lost report reply")
    monkeypatch.setattr(ProjectReports, "create", lose_reply)
    with pytest.raises(RuntimeError, match="lost report reply"):
        demo.create_report(stk, directory)
    assert not (tmp_path / "absent.zip").exists()
    assert demo.read_demo(stk, directory)["report_id"] == receipt["report_id"]
    exported = demo.export_report(stk, directory, tmp_path / "recovered.zip")
    assert exported["report_id"] == receipt["report_id"] and (tmp_path / "recovered.zip").is_file()
    p, _, _ = demo._opened(stk, directory)
    assert p.reports.list()["total"] == 1 and len(calls) == 1


@pytest.mark.parametrize("damage", ["manifest", "blob", "snapshot"])
def test_archive_or_frozen_input_tampering_is_rejected_by_real_api(isolated, tmp_path, damage):
    stk, calls, _, directory, receipt = completed(isolated, tmp_path)
    p, _, _ = demo._opened(stk, directory)
    archive = p.analysis_runs.result(receipt["run_id"])
    if damage == "manifest":
        target = Path(archive["blob_dir"]).parent / "graph-result.json"
    elif damage == "blob":
        digest = archive["result"]["outputs"]["curves"]["blob"]
        target = Path(archive["blob_dir"]) / digest[:2] / digest
    else:
        target = Path(p.snapshots.resolve(receipt["snapshot_id"], receipt["records"]["reference.csv"])["path"])
    target.write_bytes(b"tampered evidence")
    with pytest.raises((ScriptError, ValueError)):
        demo.read_demo(stk, directory)
    assert len(calls) == 1


def test_report_frozen_asset_tampering_rejects_read_and_further_export(isolated, tmp_path):
    stk, calls, _, directory, receipt = completed(isolated, tmp_path)
    publish(stk, directory, tmp_path / "original.zip")
    p, _, _ = demo._opened(stk, directory)
    value = p.reports.get(receipt["report_id"])
    manifest = value["report"]["manifest"]
    target_asset = next(a for a in manifest["assets"] if a["path"] == "within_tolerance.json.txt")
    target = p.snapshots.resolve(manifest["snapshot_id"], target_asset["record_id"])["path"]
    Path(target).write_bytes(b"tampered report asset")
    with pytest.raises((ScriptError, ValueError)):
        demo.read_demo(stk, directory)
    with pytest.raises(ScriptError):
        p.reports.export_file(receipt["report_id"], tmp_path / "absent.zip", expected_revision=value["revision"],
                              expected_source_sha256=value["report"]["source_sha256"])
    assert not (tmp_path / "absent.zip").exists() and len(calls) == 1


def test_report_source_review_sha_is_passed_to_actual_create_cas(isolated, tmp_path, monkeypatch):
    stk, calls, _, directory, receipt = completed(isolated, tmp_path)
    original = ProjectReports.review_sources
    def damaged_review(self, *args, **kwargs):
        value = original(self, *args, **kwargs)
        return {**value, "sources_sha256": "0" * 64}
    monkeypatch.setattr(ProjectReports, "review_sources", damaged_review)
    with pytest.raises(ScriptError) as error:
        demo.create_report(stk, directory)
    assert error.value.code == "conflict"
    p, _, _ = demo._opened(stk, directory)
    assert p.reports.list()["total"] == 0 and not (tmp_path / "absent.zip").exists() and len(calls) == 1


def test_numeric_document_recomputation_and_export_no_overwrite(isolated, tmp_path):
    stk, _, _, directory, receipt = completed(isolated, tmp_path)
    destination = tmp_path / "evidence.zip"
    publish(stk, directory, destination)
    before = destination.read_bytes()
    p, _, _ = demo._opened(stk, directory)
    value = p.reports.get(receipt["report_id"])
    with pytest.raises(ScriptError):
        p.reports.export_file(receipt["report_id"], destination, expected_revision=value["revision"],
                              expected_source_sha256=value["report"]["source_sha256"])
    assert destination.read_bytes() == before
    with zipfile.ZipFile(destination) as bundle:
        changed = json.loads(bundle.read("within_tolerance.json.txt"))
    changed["result"]["metrics"]["rmse"] = 0
    changed["result_sha256"] = hashlib.sha256(demo._json({key: changed[key] for key in ("format", "plan_sha256", "result")})).hexdigest()
    with pytest.raises(ComparisonError):
        verify(changed)


def test_export_failure_can_be_retried_explicitly_without_recreating_report(isolated, tmp_path, monkeypatch):
    stk, calls, _, directory, receipt = completed(isolated, tmp_path)
    demo.create_report(stk, directory)
    destination = tmp_path / "occupied.zip"
    destination.write_bytes(b"keep existing file")
    with pytest.raises(ScriptError):
        demo.export_report(stk, directory, destination)
    assert destination.read_bytes() == b"keep existing file"
    def never_create(*args, **kwargs):
        pytest.fail("Export recovery recreated a report")
    monkeypatch.setattr(ProjectReports, "create", never_create)
    result = demo.export_report(stk, directory, tmp_path / "second.zip")
    assert result["report_id"] == receipt["report_id"] and len(calls) == 1
    assert demo.read_demo(stk, directory)["report_id"] == receipt["report_id"]


@pytest.mark.parametrize("damage", ["remove_asset", "entry_path", "record_mapping"])
def test_valid_edited_report_selection_is_not_accepted_as_original_complete_evidence(isolated, tmp_path, damage):
    stk, calls, _, directory, receipt = completed(isolated, tmp_path)
    demo.create_report(stk, directory)
    p, _, _ = demo._opened(stk, directory)
    value = p.reports.get(receipt["report_id"])
    manifest = value["report"]["manifest"]
    if damage == "remove_asset":
        manifest["assets"] = [a for a in manifest["assets"] if a["path"] != "outside_tolerance.json.txt"]
    elif damage == "entry_path":
        manifest["entry_path"] = "within_tolerance.json.txt"
    else:
        # Swap path labels between same-MIME text assets; the backend metadata remains readable.
        a = next(a for a in manifest["assets"] if a["path"] == "within_tolerance.json.txt")
        b = next(a for a in manifest["assets"] if a["path"] == "outside_tolerance.json.txt")
        a["path"], b["path"] = b["path"], a["path"]
    p.apply([{"op":"set_cell", "table_id":REPORT_TABLE,"record_id":receipt["report_id"],
              "field_id":REPORT_FIELDS["manifest"],"value":manifest}], expected_revision=value["revision"])
    assert p.reports.get(receipt["report_id"])["report"]["state"] == "readable"
    with pytest.raises(ValueError, match="Report (asset membership|identity/provenance)"):
        demo.read_demo(stk, directory)
    with pytest.raises(ValueError):
        demo.export_report(stk, directory, tmp_path / "absent.zip")
    assert not (tmp_path / "absent.zip").exists() and len(calls) == 1


def test_preparation_rejects_existing_destination_and_preserves_original_ids(isolated, tmp_path):
    stk, calls, _ = isolated
    directory, receipt = prepare(stk, tmp_path)
    before = (directory / "intent.json").read_bytes()
    with pytest.raises(FileExistsError):
        demo.prepare_demo(stk, directory, **{key: str(uuid4()) for key in ("analysis_id", "run_id", "report_id")})
    assert (directory / "intent.json").read_bytes() == before and not calls
    intent = json.loads(before)
    assert all(intent[key] == receipt[key] for key in ("analysis_id", "run_id", "report_id"))


def _fifo_probe(tmp_path, *, replace_on_open):
    if not hasattr(os, "mkfifo") or os.name == "nt":
        pytest.skip("Real FIFO opening is a POSIX-specific acceptance case")
    target, entered = tmp_path / "intent.json", tmp_path / "entered"
    if replace_on_open:
        target.write_bytes(b"ordinary before open")
    else:
        os.mkfifo(target)
    code = r'''
import importlib.util, os, pathlib, sys
spec = importlib.util.spec_from_file_location("example", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
target, entered = pathlib.Path(sys.argv[2]), pathlib.Path(sys.argv[3])
if sys.argv[4] == "replace":
    original = os.open
    def race(path, flags, *args, **kwargs):
        if pathlib.Path(path) == target:
            target.unlink()
            os.mkfifo(target)
        return original(path, flags, *args, **kwargs)
    module.os.open = race
entered.write_text("entered")
try:
    module._read(target)
except (ValueError, OSError):
    print("rejected")
else:
    raise AssertionError("FIFO was accepted as evidence")
'''
    command = [sys.executable, "-c", code, str(EXAMPLE), str(target), str(entered),
               "replace" if replace_on_open else "fifo"]
    with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as child:
        try:
            stdout, stderr = child.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            child.kill()
            child.communicate()
            pytest.fail("Evidence reader blocked on a real FIFO; child killed and reaped")
    assert entered.read_text() == "entered" and child.returncode == 0, stderr.decode("utf-8", "replace")
    assert stdout.strip() == b"rejected"


def test_reader_rejects_a_real_fifo_without_waiting_for_a_writer(tmp_path):
    _fifo_probe(tmp_path, replace_on_open=False)


def test_reader_rejects_real_fifo_replacement_between_lstat_and_open(tmp_path):
    _fifo_probe(tmp_path, replace_on_open=True)


@pytest.mark.parametrize("kind", ["directory", "symlink"])
def test_reader_rejects_nonregular_names_before_open(tmp_path, monkeypatch, kind):
    target = tmp_path / "intent.json"
    if kind == "directory":
        target.mkdir()
    else:
        original = tmp_path / "original"
        original.write_bytes(b"original")
        try:
            target.symlink_to(original)
        except OSError:
            pytest.skip("This platform requires additional symbolic-link permission")
    def no_open(*args, **kwargs):
        pytest.fail("A nonregular input reached the opening API")
    monkeypatch.setattr(demo, "_read_fd", no_open)
    with pytest.raises(ValueError, match="ordinary file"):
        demo._read(target)


@pytest.mark.parametrize("moment", ["before_open", "after_read"])
def test_reader_rejects_actual_named_file_replacement_and_closes_descriptor(tmp_path, monkeypatch, moment):
    if moment == "before_open" and os.name == "nt":
        pytest.skip("This race interception targets the POSIX os.open path")
    target, replacement = tmp_path / "intent.json", tmp_path / "replacement"
    target.write_bytes(b"original")
    replacement.write_bytes(b"replaced")
    real_open, real_read, descriptors = demo.os.open, demo.os.read, []
    changed = False
    def open_file(path, flags, *args, **kwargs):
        nonlocal changed
        if Path(path) == target and moment == "before_open":
            os.replace(replacement, target)
            changed = True
        fd = real_open(path, flags, *args, **kwargs)
        if Path(path) == target:
            descriptors.append(fd)
        return fd
    def read_file(fd, size):
        nonlocal changed
        data = real_read(fd, size)
        if not changed and moment == "after_read":
            os.replace(replacement, target)
            changed = True
        return data
    monkeypatch.setattr(demo.os, "open", open_file)
    monkeypatch.setattr(demo.os, "read", read_file)
    with pytest.raises(ValueError, match="changed"):
        demo._read(target)
    assert changed and target.read_bytes() == b"replaced"
    for fd in descriptors:
        with pytest.raises(OSError):
            os.fstat(fd)


def test_reader_rejects_same_inode_same_size_mutation_during_read(tmp_path, monkeypatch):
    target = tmp_path / "intent.json"
    target.write_bytes(b"original")
    before = target.stat()
    real_read = demo.os.read
    changed = False
    def mutate(fd, size):
        nonlocal changed
        data = real_read(fd, size)
        if not changed:
            target.write_bytes(b"modified")
            os.utime(target, ns=(before.st_atime_ns, before.st_mtime_ns + 1000000000))
            changed = True
        return data
    monkeypatch.setattr(demo.os, "read", mutate)
    with pytest.raises(ValueError, match="changed while reading"):
        demo._read(target)
    assert target.stat().st_ino == before.st_ino


def test_reader_uses_consistent_api_signatures_for_ctime_and_permission_bits(tmp_path, monkeypatch):
    from types import SimpleNamespace
    target = tmp_path / "intent.exe"
    target.write_bytes(b"ordinary bytes")
    real_fstat = os.fstat
    def descriptor_info(fd):
        info = real_fstat(fd)
        return SimpleNamespace(st_dev=info.st_dev, st_ino=info.st_ino, st_size=info.st_size,
                               st_mtime_ns=info.st_mtime_ns, st_ctime_ns=info.st_ctime_ns + 100,
                               st_mode=stat.S_IFREG | 0o444, st_file_attributes=0)
    monkeypatch.setattr(demo.os, "fstat", descriptor_info)
    assert demo._read(target) == b"ordinary bytes"


@pytest.mark.parametrize("limit", [-1, True, 1.0, 32 * 1024 * 1024 + 1])
def test_reader_rejects_invalid_budgets_before_filesystem_access(tmp_path, limit):
    with pytest.raises(ValueError, match="bounded byte limit"):
        demo._read(tmp_path / "missing", limit=limit)


def test_reader_accepts_exact_budget_and_empty_file_but_not_oversize(tmp_path):
    target = tmp_path / "intent.json"
    target.write_bytes(b"exact")
    assert demo._read(target, limit=5) == b"exact"
    with pytest.raises(ValueError, match="byte budget"):
        demo._read(target, limit=4)
    target.write_bytes(b"")
    assert demo._read(target, limit=0) == b""


def test_reader_rejects_short_eof_despite_stable_regular_file_metadata(tmp_path, monkeypatch):
    target = tmp_path / "intent.json"
    target.write_bytes(b"complete original")
    before = target.stat()
    real_read = demo.os.read
    calls = 0
    def short_eof(fd, size):
        nonlocal calls
        calls += 1
        return real_read(fd, 1) if calls == 1 else b""
    monkeypatch.setattr(demo.os, "read", short_eof)
    with pytest.raises(ValueError, match="pinned file size"):
        demo._read(target)
    after = target.stat()
    assert (before.st_ino, before.st_size, before.st_mtime_ns) == (after.st_ino, after.st_size, after.st_mtime_ns)


def test_new_evidence_is_exclusive_and_uses_private_posix_mode(tmp_path):
    target = tmp_path / "intent.json"
    demo._new(target, b"original")
    with pytest.raises(FileExistsError):
        demo._new(target, b"replacement")
    assert target.read_bytes() == b"original"
    if os.name != "nt":
        assert stat.S_IMODE(target.stat().st_mode) & 0o077 == 0
