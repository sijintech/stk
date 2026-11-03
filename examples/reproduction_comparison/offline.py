"""Manufactured comparison example over the normal, persistent headless STK API.

prepare_demo saves explicit inputs and tolerances; only start_demo executes a graph.
read_demo never starts, retries, recovers, renders or requests a model. create_report
and export_report are separate explicit actions. None selects a visible project.
"""
import argparse
import base64
from contextlib import contextmanager
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import tempfile
import time
from uuid import UUID, uuid4
import zipfile


CASES = ("within_tolerance", "outside_tolerance", "missing_rows", "failed_run", "unit_mismatch")
EXPECTED = dict(zip(CASES, ("passed", "failed", "indeterminate", "indeterminate", "indeterminate")))
INPUTS = {
    "reference.csv": b"x,value\n0,0\n1,2\n2,4\n",
    "within.csv": b"x,value\n0,0.125\n1,2.125\n2,4.125\n",
    "outside.csv": b"x,value\n0,0.5\n1,2.5\n2,4.5\n",
    "missing.csv": b"x,value,state\n0,0,ok\n1,,missing\n2,4,failed\n",
}
ACTIVE = {"running", "cancel_requested"}
MAX_BYTES = 4 * 1024 * 1024


def _json(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _new(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
                 | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        stream = os.fdopen(fd, "wb")
    except BaseException:
        os.close(fd)
        raise
    with stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


@contextmanager
def private_environment(directory):
    """Isolate non-secret service/cache locations without changing product settings."""
    directory = Path(directory)
    values = {"STK_MODULES_DIR": str(directory / "modules"),
              "STK_PROFILES_FILE": str(directory / "profiles.json"),
              "STK_STATE_DIR": str(directory / "runtime"), "MPLCONFIGDIR": str(directory / "matplotlib")}
    previous = {key: os.environ.get(key) for key in values}
    try:
        os.environ.update(values)
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _regular(info):
    if (not stat.S_ISREG(info.st_mode) or getattr(info, "st_file_attributes", 0)
            & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)):
        raise ValueError("Example evidence must be an ordinary file")


def _file_identity(info):
    # Compare only fields with the same meaning across path and descriptor APIs.
    # Windows lstat/fstat can expose different ctime and synthesized permission bits.
    return info.st_dev, info.st_ino, stat.S_IFMT(info.st_mode), info.st_size, info.st_mtime_ns


def _file_state(info):
    # This signature is compared only within lstat or within fstat, never across them.
    return _file_identity(info), info.st_ctime_ns, info.st_mode, getattr(info, "st_file_attributes", 0)


def _read_fd(path):
    if os.name != "nt":
        return os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0)
                       | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    # Windows has no POSIX O_NOFOLLOW/O_NONBLOCK. Open the final reparse point
    # itself and reject it before converting the handle into a readable descriptor.
    import ctypes
    from ctypes import wintypes
    import msvcrt
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    create = kernel.CreateFileW
    create.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                       wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE)
    create.restype = wintypes.HANDLE
    close = kernel.CloseHandle
    close.argtypes, close.restype = (wintypes.HANDLE,), wintypes.BOOL
    handle = create(str(path), 0x80000000, 0x1 | 0x2 | 0x4, None, 3, 0x00200000, None)
    if handle in (None, wintypes.HANDLE(-1).value):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        class Attributes(ctypes.Structure):
            _fields_ = [("attributes", wintypes.DWORD), ("tag", wintypes.DWORD)]
        attributes = Attributes()
        inspect = kernel.GetFileInformationByHandleEx
        inspect.argtypes = (wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD)
        inspect.restype = wintypes.BOOL
        if not inspect(handle, 9, ctypes.byref(attributes), ctypes.sizeof(attributes)):
            raise ctypes.WinError(ctypes.get_last_error())
        if attributes.attributes & 0x400:  # FILE_ATTRIBUTE_REPARSE_POINT
            raise ValueError("Example evidence must not be a reparse point")
        fd = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY | os.O_NOINHERIT)
    except BaseException:
        close(handle)
        raise
    return fd  # Descriptor now owns the Windows handle.


def _read(path, *, limit=MAX_BYTES):
    if type(limit) is not int or not 0 <= limit <= 32 * 1024 * 1024:
        raise ValueError("Example evidence requires a finite bounded byte limit")
    path = Path(path)
    before = path.lstat()
    _regular(before)
    if before.st_size > limit:
        raise ValueError("Example evidence exceeds its byte budget")
    fd = _read_fd(path)
    try:
        opened, named = os.fstat(fd), path.lstat()
        _regular(opened)
        _regular(named)
        if _file_identity(before) != _file_identity(opened) or _file_state(before) != _file_state(named):
            raise ValueError("Example evidence changed before reading")
        chunks, remaining = [], limit + 1
        while remaining:
            chunk = os.read(fd, min(65536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        after, named_after = os.fstat(fd), path.lstat()
        _regular(after)
        _regular(named_after)
        if (_file_state(opened) != _file_state(after) or _file_state(before) != _file_state(named_after)
                or _file_identity(after) != _file_identity(named_after)):
            raise ValueError("Example evidence changed while reading")
        data = b"".join(chunks)
        if len(data) > limit:
            raise ValueError("Example evidence exceeds its byte budget")
        if len(data) != opened.st_size:
            raise ValueError("Example evidence byte count differs from its pinned file size")
        return data
    finally:
        os.close(fd)


def _load(path):
    def constant(_):
        raise ValueError("Evidence must be finite JSON")
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Evidence must not contain duplicate JSON keys")
            result[key] = value
        return result
    return json.loads(_read(path), parse_constant=constant, object_pairs_hook=pairs)


def definition():
    """All five rules and unit labels are authored before preparation/execution."""
    sources = {"reference": ("reference.csv", "m"), "within": ("within.csv", "m"),
               "outside": ("outside.csv", "m"), "missing": ("missing.csv", "m"),
               "wrong_unit": ("within.csv", "cm")}
    nodes = [{"id": name, "type": "stk.source.table@1", "params": {
        "binding": "data", "path": path, "format": "csv", "units": {"x": "s", "value": unit}}}
        for name, (path, unit) in sources.items()]
    actuals = ("within", "outside", "missing", "within", "wrong_unit")
    outputs = {}
    for case, actual in zip(CASES, actuals):
        params = {"kind": "curve", "reference_value": "value", "actual_value": "value",
                  "reference_x": "x", "actual_x": "x", "reference_status": "succeeded",
                  "actual_status": "failed" if case == "failed_run" else "succeeded",
                  "absolute": 0.25, "relative": 0, "alignment": "exact", "domain": [0, 2]}
        if case == "missing_rows":
            params["actual_row_status"] = "state"
        nodes.append({"id": case, "type": "stk.analysis.reproduction_compare@1", "params": params,
                      "inputs": {"reference": {"from": "reference.out"}, "actual": {"from": actual + ".out"}}})
        outputs[case] = case + ".comparison"
        outputs[case + "_errors"] = case + ".errors"
    for name, columns in (("curves", ["reference", "actual"]),
                          ("errors", ["absolute_error", "allowed_error"])):
        nodes.append({"id": name, "type": "stk.plot.line@1", "inputs": {
            "table": {"from": "within_tolerance.errors"}}, "params": {
            "x": "x", "y": columns, "title": "Manufactured software example: " + name,
            "size_in": [6, 4], "dpi": 100}})
        nodes.append({"id": name + "_png", "type": "stk.output.image@1", "inputs": {
            "source": {"from": name + ".plot"}}, "params": {"format": "png"}})
        outputs[name] = name + "_png.image"
        outputs[name + "_plot"] = name + ".plot"
    return {"format": "stk.analysis-document/1", "graph": {
        "schema": "stk.graph/1", "id": "manufactured-comparison-example", "nodes": nodes,
        "outputs": outputs}, "parameters": {}, "outputs": list(outputs)}


def prepare_demo(stk, directory, *, analysis_id, run_id, report_id):
    """Create a new project and prepare one saved analysis; execute nothing.

    Callers retain their original UUIDs. intent.json and run-request.json are local
    request notes, not server edit-operation receipts or authenticated paper claims.
    A partial failure is left for inspection, never retried under new identities.
    """
    for identity in (analysis_id, run_id, report_id):
        if str(UUID(identity)) != identity:
            raise ValueError("Supply canonical UUID strings")
    if len({analysis_id, run_id, report_id}) != 3:
        raise ValueError("Supply distinct analysis, run and report UUIDs")
    directory = Path(os.path.abspath(Path(directory).expanduser()))
    directory.mkdir(parents=True, exist_ok=False, mode=0o700)
    document = definition()
    _new(directory / "intent.json", _json({"format": "stk.example-reproduction-intent/1",
         "analysis_id": analysis_id, "run_id": run_id, "report_id": report_id,
         "document_sha256": _sha(_json(document)), "manufactured": True}))
    p = stk.projects.create(directory, "Manufactured comparison software example")
    project_id = p.snapshot()["project"]["id"]
    for name, data in INPUTS.items():
        _new(directory / name, data)
    _new(directory / "analysis-document.json", _json(document))
    indexed = p.files.index([directory / name for name in INPUTS], expected_revision=0)
    records = dict(zip(INPUTS, indexed["record_ids"]))
    captured = p.snapshots.capture(list(records.values()), expected_revision=indexed["revision"])
    snapshot = captured["snapshot"]
    saved = p.analyses.create("Manufactured five-case comparison", document,
                              analysis_id=analysis_id, expected_revision=captured["revision"])
    request = {"analysis_id": analysis_id, "snapshot_id": snapshot["id"],
               "bindings": {"data": records}, "run_id": run_id, "expected_revision": saved["revision"]}
    identity = {"project_id": project_id, "analysis_id": analysis_id, "run_id": run_id,
                "report_id": report_id, "snapshot_id": snapshot["id"], "snapshot_sha256": snapshot["sha256"],
                "records": records, "revision": saved["revision"], "document_sha256": _sha(_json(document)),
                "input_sha256": {k: _sha(v) for k, v in INPUTS.items()}}
    # This exact request is durable before prepare; no UUID is regenerated after an uncertain reply.
    _new(directory / "run-request.json", _json({"identity": identity, "request": request,
         "request_sha256": _sha(_json(request))}))
    run = p.analysis_runs.prepare(**request)
    receipt = {**identity, "plan_sha256": run["plan_sha256"]}
    _new(directory / "prepared.json", _json(receipt))
    return receipt


def _opened(stk, directory):
    directory = Path(directory)
    note, intent = _load(directory / "run-request.json"), _load(directory / "intent.json")
    identity, request = note["identity"], note["request"]
    if set(identity["records"]) != set(INPUTS):
        raise ValueError("The preparation note does not select the complete original input set")
    expected_request = {"analysis_id": identity["analysis_id"], "snapshot_id": identity["snapshot_id"],
                        "bindings": {"data": identity["records"]}, "run_id": identity["run_id"],
                        "expected_revision": identity["revision"]}
    if (_json(request) != _json(expected_request) or _sha(_json(request)) != note["request_sha256"]
            or any(identity[key] != intent[key] for key in ("analysis_id", "run_id", "report_id", "document_sha256"))
            or identity["document_sha256"] != _sha(_json(definition()))
            or identity["input_sha256"] != {k: _sha(v) for k, v in INPUTS.items()}):
        raise ValueError("The original preparation request note changed")
    p = stk.projects.open(directory, expected_id=identity["project_id"])
    # Query only the original UUID. Missing/uncertain preparation is never replayed.
    run = p.analysis_runs.get(request["run_id"])
    observed_request = {"analysis_id": run["analysis_id"], "snapshot_id": run["snapshot_id"],
                        "bindings": {binding: {path: item["record_id"] for path, item in files.items()}
                                     for binding, files in run["bindings"].items()},
                        "run_id": run["id"], "expected_revision": run["source_revision"]}
    expected_bindings = {"data": {name: {"record_id": record, "sha256": identity["input_sha256"][name],
                                       "size": len(INPUTS[name])} for name, record in identity["records"].items()}}
    if (_json(observed_request) != _json(request) or run["project_id"] != identity["project_id"]
            or _sha(_json(run["document"])) != identity["document_sha256"]
            or _json(run["bindings"]) != _json(expected_bindings) or run.get("parameter_overrides")
            or run["snapshot_id"] != request["snapshot_id"] or run["snapshot_sha256"] != identity["snapshot_sha256"]):
        raise ValueError("The observed run differs from the original preparation request")
    prepared = directory / "prepared.json"
    if prepared.exists() or prepared.is_symlink():
        receipt = _load(prepared)
        if _json(receipt) != _json({**identity, "plan_sha256": run["plan_sha256"]}):
            raise ValueError("The saved run differs from the original preparation receipt")
    # This is an observed identity, not a fabricated acknowledgement or new on-disk receipt.
    return p, {**identity, "plan_sha256": run["plan_sha256"],
               "prepare_response_received": prepared.exists()}, run


def start_demo(stk, directory, *, wait_seconds=60):
    """One explicit start. Timeout ends observation; it does not request cancellation.

    Keep the headless session open while work runs: closing it cancels local work.
    Reopen/read/recover do not start it again. A new calculation needs a new project.
    """
    if type(wait_seconds) not in (int, float) or not math.isfinite(wait_seconds) or not 0 <= wait_seconds <= 300:
        raise ValueError("wait_seconds must be finite and between 0 and 300")
    p, receipt, run = _opened(stk, directory)
    if run["status"] != "prepared":
        raise ValueError("This run was already started; read the original identity instead")
    _new(Path(directory) / "start-intent.json", _json({"operation": "project.analysis_runs.start",
         "project_id": receipt["project_id"], "run_id": receipt["run_id"], "plan_sha256": receipt["plan_sha256"]}))
    run = p.analysis_runs.start(receipt["run_id"])
    deadline = time.monotonic() + wait_seconds
    while run["status"] in ACTIVE and time.monotonic() < deadline:
        time.sleep(min(0.05, max(0, deadline - time.monotonic())))
        run = p.analysis_runs.get(receipt["run_id"])
    return {"run_id": run["id"], "execution_status": run["status"],
            "observation_timed_out": run["status"] in ACTIVE}


def _blob(archive, digest, size=None):
    if type(digest) is not str or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise ValueError("Invalid archived blob digest")
    data = _read(Path(archive["blob_dir"]) / digest[:2] / digest)
    if _sha(data) != digest or size is not None and len(data) != size:
        raise ValueError("Archived blob bytes disagree with their receipt")
    return data


def _output(archive, name):
    output = archive["result"]["outputs"][name]
    if output["type"] == "value":
        return json.loads(_blob(archive, output["blob"], output["size"])) if "blob" in output else output["value"]
    if output["type"] == "table":
        return json.loads(_blob(archive, output["blob"], output["size"])) if "blob" in output else output
    raise ValueError("Expected archived JSON or table output")


def _verified_archive(p, receipt, run):
    from suan.reproduction import verify
    archive = p.analysis_runs.result(receipt["run_id"])
    if archive["run"] != run or run["status"] != "succeeded" or archive["result"].get("errors"):
        raise ValueError("The manufactured software analysis did not succeed completely")
    if set(archive["result"]["outputs"]) != set(run["document"]["outputs"]):
        raise ValueError("An explicit analysis output is missing")
    for case in CASES:
        comparison, errors = _output(archive, case), _output(archive, case + "_errors")
        verify(comparison)
        if (comparison["result"]["status"] != EXPECTED[case]
                or comparison["plan"]["tolerance"] != {"absolute": 0.25, "relative": 0}
                or len(errors["columns"]["status"]) != 3
                or errors["columns"]["status"] != [point["status"] for point in comparison["result"]["points"]]):
            raise ValueError("Manufactured comparison outcomes or retained rows changed")
        if case == "within_tolerance" and comparison["result"]["metrics"]["rmse"] != 0.125:
            raise ValueError("Independent analytic error changed")
        if case == "outside_tolerance" and comparison["result"]["metrics"]["rmse"] != 0.5:
            raise ValueError("Independent analytic failure error changed")
        if case in ("within_tolerance", "outside_tolerance"):
            delta = 0.125 if case == "within_tolerance" else 0.5
            expected = {"x": [0, 1, 2], "reference": [0, 2, 4], "actual": [delta, 2 + delta, 4 + delta],
                        "signed_error": [delta]*3, "absolute_error": [delta]*3, "allowed_error": [0.25]*3}
            if any(errors["columns"].get(key) != values for key, values in expected.items()):
                raise ValueError("Archived errors differ from the independent analytic fixture")
    for name in ("curves", "errors"):
        plot = archive["result"]["outputs"][name]
        if plot["type"] != "image" or plot["media_type"] != "image/png":
            raise ValueError("Expected the real archived Agg PNG")
        if not _blob(archive, plot["blob"], plot["size"]).startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError("Archived curve image is not PNG")
        plotted = json.loads(_blob(archive, archive["result"]["outputs"][name + "_plot"]["data_blob"]))
        columns = ("reference", "actual") if name == "curves" else ("absolute_error", "allowed_error")
        ys = ([0, 2, 4], [0.125, 2.125, 4.125]) if name == "curves" else ([0.125]*3, [0.25]*3)
        if (plotted.get("schema") != "stk.plot-data/1" or len(plotted.get("marks", [])) != 2
                or any(mark.get("columns") != {"x": "x", "y": column}
                       or mark.get("data") != {"x": [0, 1, 2], "y": y}
                       for mark, column, y in zip(plotted["marks"], columns, ys))):
            raise ValueError("Archived plot data differs from the independent analytic fixture")
    return archive


def read_demo(stk, directory):
    """Verify frozen identities/bytes, comparisons and any saved report; execute nothing."""
    p, receipt, run = _opened(stk, directory)
    snapshot = p.snapshots.get(receipt["snapshot_id"])
    if snapshot["sha256"] != receipt["snapshot_sha256"]:
        raise ValueError("Original snapshot identity changed")
    p.snapshots.verify(receipt["snapshot_id"])
    for name, record in receipt["records"].items():
        resolved = p.snapshots.resolve(receipt["snapshot_id"], record)
        if _sha(_read(resolved["path"])) != receipt["input_sha256"][name]:
            raise ValueError("Frozen input differs from its original receipt")
    result = {"project_id": receipt["project_id"], "run_id": run["id"], "plan_sha256": run["plan_sha256"],
              "execution_status": run["status"], "verified_archive": False,
              "prepare_response_received": receipt["prepare_response_received"]}
    if run["result"] is not None:
        archive = _verified_archive(p, receipt, run)
        result.update(verified_archive=True, manifest_sha256=run["result"]["manifest_sha256"],
                      comparison_statuses={case: _output(archive, case)["result"]["status"] for case in CASES})
    request_path = Path(directory) / "report-request.json"
    if request_path.exists():
        request = _load(request_path)
        report = p.reports.get(receipt["report_id"])
        _verify_report(p, receipt, request, report)
        result["report_id"] = receipt["report_id"]
        result["report_source_sha256"] = report["report"]["source_sha256"]
    return result


def _verify_report(p, receipt, request, value):
    report = value["report"]
    manifest = report["manifest"]
    if (report["id"] != receipt["report_id"] or report["format"] != "stk.report/1"
            or report["state"] != "readable" or manifest["sources"] != request["sources"]
            or _sha(_json(manifest["sources"])) != request["sources_sha256"]
            or manifest["snapshot_id"] != request["snapshot_id"]
            or manifest["snapshot_sha256"] != request["snapshot_sha256"]
            or manifest["source_revision"] != request["creation"]["expected_revision"]
            or manifest["entry_path"] != request["entry_path"]
            or report["source_sha256"] != _sha(_json(manifest))):
        raise ValueError("Report identity/provenance does not match the reviewed source")
    expected_assets = {item["path"]: item["record_id"] for item in request["creation"]["assets"]}
    if (len(manifest["assets"]) != len(expected_assets) or set(expected_assets) != set(request["assets_sha256"])
            or {item["path"]: item["record_id"] for item in manifest["assets"]} != expected_assets):
        raise ValueError("Report asset membership differs from the complete original selection")
    selection = {"expected_revision": value["revision"], "expected_source_sha256": report["source_sha256"]}
    for asset in manifest["assets"]:
        observed = p.reports.asset(receipt["report_id"], asset["path"], **selection)
        raw = base64.b64decode(observed["data"], validate=True)
        if (_sha(raw) != asset["sha256"] or len(raw) != asset["size"]
                or request["assets_sha256"].get(asset["path"]) != asset["sha256"]):
            raise ValueError("Report asset SHA/size does not match the frozen evidence")


def create_report(stk, directory):
    """Explicitly freeze Report/1, linked to the real saved analysis_run.

    JSON is exact UTF-8 text in *.json.txt: this uses supported Report/1 text assets.
    Sources authenticate local project/run identity, not paper authorship or science.
    If the create reply is lost, read_demo/export_report query the original report
    UUID; do not call this function again to replay a possibly accepted write.
    """
    p, receipt, run = _opened(stk, directory)
    archive = _verified_archive(p, receipt, run)
    folder = Path(directory) / "report-evidence"
    folder.mkdir(mode=0o700, exist_ok=False)
    manifest_path = Path(archive["blob_dir"]).parent / "graph-result.json"
    archived_bytes = _read(manifest_path)
    if _sha(archived_bytes) != run["result"]["manifest_sha256"]:
        raise ValueError("Exact archived manifest SHA changed")
    assets = {"graph-result.json.txt": archived_bytes, "execution.json.txt": _json(run),
              "analysis-document.json.txt": _json(run["document"])}
    for case in CASES:
        assets[case + ".json.txt"] = _json(_output(archive, case))
        assets[case + "-errors.json.txt"] = _json(_output(archive, case + "_errors"))
    for name in ("curves", "errors"):
        output = archive["result"]["outputs"][name]
        assets[name + ".png"] = _blob(archive, output["blob"], output["size"])
        assets[name + "-plot-data.json.txt"] = _blob(archive, archive["result"]["outputs"][name + "_plot"]["data_blob"])
    text = ("# Manufactured comparison: software integration only\n\n"
            "These self-authored analytic fixtures are not paper, experimental or MuPRO results.\n"
            "Reference y = 2x; within-tolerance actual y = 2x + 0.125; outside actual y = 2x + 0.5.\n"
            "x is labelled s; y is labelled m, with an intentionally incompatible cm case.\n"
            "Frozen absolute tolerance 0.25 m, relative tolerance 0; exact alignment on [0, 2], no extrapolation.\n\n"
            "The saved analysis executed successfully. Its comparisons include failures and indeterminate outcomes:\n\n"
            + "\n".join("- " + case + ": " + EXPECTED[case] for case in CASES)
            + "\n\nMissing and failed rows remain in the comparison JSON and ordered error tables.\n"
            "![Manufactured curves](curves.png)\n\n![Manufactured errors](errors.png)\n\n"
            + f"Project: {receipt['project_id']}\n\nAnalysis run: {run['id']}\n\n"
            + f"Plan SHA-256: {run['plan_sha256']}\n\nArchive SHA-256: {run['result']['manifest_sha256']}\n\n"
            "The report source binds this local project's actual analysis_run and reviewed lifecycle.\n"
            "Caller unit/status/provenance labels remain unauthenticated scientific input.\n"
            "Exact JSON evidence uses supported UTF-8 .txt assets; the ZIP is an evidence export, not an importable project.\n"
            "No paper parameters, solver validation, sensitivity study, physical conclusion or native UI acceptance is claimed.\n")
    assets["report.md"] = text.encode("utf-8")
    for name, data in assets.items():
        _new(folder / name, data)
    revision = p.snapshot()["project"]["revision"]
    indexed = p.files.index([folder / name for name in assets], expected_revision=revision)
    selected = dict(zip(assets, indexed["record_ids"]))
    captured = p.snapshots.capture(list(selected.values()), expected_revision=indexed["revision"])
    sources = [{"kind": "analysis_run", "id": run["id"]}]
    reviewed = p.reports.review_sources(sources, expected_revision=captured["revision"])
    creation = {"name": "Manufactured comparison software evidence", "snapshot_id": captured["snapshot"]["id"],
                "entry_record_id": selected["report.md"], "assets": [
                    {"record_id": record, "path": name} for name, record in selected.items()],
                "report_id": receipt["report_id"], "expected_revision": captured["revision"],
                "sources": sources, "expected_sources_sha256": reviewed["sources_sha256"]}
    request = {"creation": creation, "snapshot_id": captured["snapshot"]["id"],
               "snapshot_sha256": captured["snapshot"]["sha256"], "entry_path": "report.md", "sources": reviewed["sources"],
               "sources_sha256": reviewed["sources_sha256"], "assets_sha256": {k: _sha(v) for k, v in assets.items()}}
    _new(Path(directory) / "report-request.json", _json(request))
    p.reports.create(**creation)
    report = p.reports.get(receipt["report_id"])
    _verify_report(p, receipt, request, report)
    return {"report_id": receipt["report_id"], "source_sha256": report["report"]["source_sha256"], "assets": len(assets)}


def export_report(stk, directory, destination):
    """Explicitly export an existing report using its original request and UUID.

    This action can follow a lost create reply or a failed earlier export; it
    queries/verifies the original report and never creates a replacement.
    """
    p, receipt, run = _opened(stk, directory)
    _verified_archive(p, receipt, run)
    request = _load(Path(directory) / "report-request.json")
    report = p.reports.get(receipt["report_id"])
    _verify_report(p, receipt, request, report)
    exported = p.reports.export_file(receipt["report_id"], destination, expected_revision=report["revision"],
                                    expected_source_sha256=report["report"]["source_sha256"])
    raw = _read(destination, limit=32 * 1024 * 1024)
    if _sha(raw) != exported["sha256"] or len(raw) != exported["size"]:
        raise ValueError("Export receipt does not match actual ZIP bytes")
    with zipfile.ZipFile(destination) as bundle:
        envelope = json.loads(bundle.read("stk-report.json"))
        if (envelope["manifest"] != report["report"]["manifest"] or envelope["report_id"] != receipt["report_id"]
                or envelope["source_sha256"] != report["report"]["source_sha256"]
                or set(bundle.namelist()) != set(request["assets_sha256"]) | {"stk-report.json"}):
            raise ValueError("Export manifest differs from the authenticated local report")
        for name, digest in request["assets_sha256"].items():
            if _sha(bundle.read(name)) != digest:
                raise ValueError("Export changed frozen evidence bytes")
    return {"report_id": receipt["report_id"], "source_sha256": report["report"]["source_sha256"],
            "export_sha256": exported["sha256"], "export_size": exported["size"], "assets": len(request["assets_sha256"])}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "start", "read", "report", "export"))
    parser.add_argument("directory", type=Path)
    parser.add_argument("--export", type=Path, help="New ZIP destination, required for export")
    args = parser.parse_args(argv)
    if args.action == "export" and args.export is None:
        parser.error("export requires --export NEW.zip")
    if args.action != "export" and args.export is not None:
        parser.error("--export belongs only to the explicit export action")
    from suan.scripting.headless import connect
    # Never open existing user service/model settings or call hello/autostart.
    with tempfile.TemporaryDirectory(prefix="stk-reproduction-headless-") as private, private_environment(private):
        with connect(Path(private) / "service") as stk:
            if args.action == "prepare":
                result = prepare_demo(stk, args.directory, analysis_id=str(uuid4()), run_id=str(uuid4()), report_id=str(uuid4()))
            elif args.action == "start":
                result = start_demo(stk, args.directory, wait_seconds=300)
            elif args.action == "read":
                result = read_demo(stk, args.directory)
            elif args.action == "report":
                result = create_report(stk, args.directory)
            else:
                result = export_report(stk, args.directory, args.export)
            print(json.dumps(result, ensure_ascii=False, allow_nan=False, sort_keys=True))


if __name__ == "__main__":
    main()
