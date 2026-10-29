"""Real controlled subprocess evidence, deliberately not a TeX installation test."""
import base64
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import threading
import time
from uuid import uuid4

import psutil
import pytest

from suan.documents import latex
from suan.project import ProjectStore, ProjectError, RevisionConflict


@pytest.fixture
def project(tmp_path):
    store = ProjectStore.create(tmp_path / "project", "LaTeX")
    paths = []
    for name, content in (("main.tex", "good"), ("章节.tex", "selected source\n")):
        path = store.directory / name
        path.write_text(content, encoding="utf-8")
        paths.append(str(path))
    records = store.files.index(paths, expected_revision=0)["record_ids"]
    snapshot = store.snapshots.capture(records, expected_revision=1)["snapshot"]
    assets = [{"record_id": records[0], "path": "main.tex"}, {"record_id": records[1], "path": "sub/章节.tex"}]
    inputs = latex.freeze_inputs(store, snapshot["id"], assets, entry_path="main.tex", expected_revision=2)
    compiler = latex.freeze_compiler(sys.executable)
    return store, inputs, compiler


@pytest.fixture
def compiler_fixture(tmp_path, monkeypatch):
    """Substitute only the program's body; exercise the actual gate/job/log lifecycle."""
    script, trace, mode, child = [tmp_path / name for name in ("compiler.py", "trace.jsonl", "mode.txt", "child.json")]
    mode.write_text("good")
    script.write_text("""
import json, os, pathlib, subprocess, sys, time
root = pathlib.Path.cwd().parent
receipt = json.loads((root / 'compile.json').read_text(encoding='utf-8'))
assert receipt['state'] == 'running' and receipt['runner']['pid'] > 0
if os.name != 'nt':
    assert receipt['runner']['pid'] == os.getpid()
with pathlib.Path(TRACE).open('a', encoding='utf-8') as log:
    log.write(json.dumps({'argv': sys.argv, 'pid': os.getpid()}) + '\\n')
mode = pathlib.Path(MODE).read_text()
if '--version' in sys.argv:
    if mode == 'unknown_compiler':
        print('unknown local tool'); raise SystemExit(0)
    print('pdfTeX (TeX Live controlled fixture)')
    raise SystemExit(0)
assert 'STK_TOKEN_PLAN_API_KEY' not in os.environ and 'STK_TOKEN_PLAN_MODEL' not in os.environ
assert 'TEXINPUTS' not in os.environ and 'PYTHONHOME' not in os.environ
out = pathlib.Path('_stk-out')
print('sub/章节.tex:7:3: selected source diagnostic', flush=True)
print('/private/outside.tex:2: must never become an authorized path', flush=True)
(out / 'report.log').write_text('main.tex:4: TeX diagnostic\\n', encoding='utf-8')
if mode == 'failed':
    raise SystemExit(9)
if mode == 'log_limit':
    sys.stdout.buffer.write(b'x' * (1024 * 1024)); sys.stdout.flush()
if mode == 'native_log_limit':
    (out / 'report.log').write_bytes(b'x' * (1024 * 1024))
if mode == 'child':
    process = subprocess.Popen([sys.executable, '-I', '-S', '-c', 'import time; time.sleep(30)'])
    pathlib.Path(CHILD).write_text(json.dumps({'pid': process.pid}))
if mode in ('sleep', 'child'):
    print('READY', flush=True)
    time.sleep(30)
if mode == 'mutate_input':
    pathlib.Path('main.tex').write_text('changed')
pdf = b'%PDF-1.4\\ncontrolled fixture only\\n%%EOF\\n'
if mode == 'bad_pdf':
    pdf = b'not a pdf'
if mode == 'big_pdf':
    pdf = b'%PDF-' + b'x' * (4 * 1024 * 1024)
(out / 'report.pdf').write_bytes(pdf)
""".replace("pathlib.Path(TRACE)", "pathlib.Path(" + repr(str(trace)) + ")")
       .replace("pathlib.Path(MODE)", "pathlib.Path(" + repr(str(mode)) + ")")
       .replace("pathlib.Path(CHILD)", "pathlib.Path(" + repr(str(child)) + ")"), encoding="utf-8")
    run = latex._run_command
    def controlled(argv, *args, **kwargs):
        actual = [sys.executable, "-X", "utf8", str(script), *argv[1:]]
        args[2]["argv"] = actual  # the actual controlled invocation is recorded
        return run(actual, *args, **kwargs)
    monkeypatch.setattr(latex, "_run_command", controlled)
    return mode, trace, child


def execute(project, **kwargs):
    store, inputs, compiler = project
    identity = str(uuid4())
    directory = "results/workflow-runs/" + identity
    receipt = latex.compile_frozen(store, inputs, compiler, attempt_id=identity, directory=directory, **kwargs)
    return identity, directory, receipt


def until(condition, seconds=5):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(0.01)
    raise AssertionError("Controlled execution did not reach its handshake")


def alive(pid):
    try:
        return psutil.Process(pid).status() != psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return False


def test_preparation_never_spawns_and_rejects_revision_drift(project, monkeypatch):
    store, inputs, _ = project
    before = store.history()
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: pytest.fail("preparation spawned a process"))
    selected = [{"record_id": item["record_id"], "path": item["path"]} for item in inputs["assets"]]
    assert latex.freeze_inputs(store, inputs["snapshot_id"], selected, entry_path="main.tex", expected_revision=2) == inputs
    assert latex.freeze_compiler(sys.executable)["sha256"]
    with pytest.raises(RevisionConflict):
        latex.freeze_inputs(store, inputs["snapshot_id"], selected, entry_path="main.tex", expected_revision=1)
    assert store.history() == before


def test_real_gate_success_uses_frozen_bytes_and_receipt_reopens(project, compiler_fixture, monkeypatch):
    store, inputs, _ = project
    for name in ("main.tex", "章节.tex"):
        (store.directory / name).unlink()
    before = store.history()
    identity, directory, receipt = execute(project)
    assert receipt["state"] == "succeeded", receipt
    assert len(compiler_fixture[1].read_text().splitlines()) == 2  # version and one compilation
    assert (store.directory / directory / "input/main.tex").read_text() == "good"
    assert len(receipt["diagnostics"]) == 2
    assert receipt["diagnostics"][0]["path"] == "sub/章节.tex"
    assert receipt["diagnostics"][0]["line"] == 7 and receipt["diagnostics"][0]["column"] == 3
    assert receipt["diagnostics"][1]["column"] is None
    for item in receipt["files"]:
        data = (store.directory / directory / item["path"]).read_bytes()
        assert len(data) == item["size"] and hashlib.sha256(data).hexdigest() == item["sha256"]
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: pytest.fail("read/recovery spawned a process"))
    reopened = ProjectStore(store.directory)
    assert latex.read_receipt(reopened, directory, attempt_id=identity) == receipt
    assert latex.recover(reopened, directory, attempt_id=identity) == receipt
    page = latex.read_log(reopened, directory, attempt_id=identity, limit=7)
    assert page["next_offset"] == 7 and len(base64.b64decode(page["data"])) == 7
    assert store.history() == before  # output registration is owned by the integrating workflow


@pytest.mark.parametrize("mode,reason", [("failed", "compiler_failed"), ("log_limit", "log_limit"),
    ("native_log_limit", "log_limit"), ("mutate_input", "compile_error"), ("bad_pdf", "compile_error"), ("big_pdf", "compile_error")])
def test_failed_outputs_are_not_published_but_logs_persist(project, compiler_fixture, mode, reason):
    compiler_fixture[0].write_text(mode)
    identity, directory, receipt = execute(project)
    assert receipt["state"] == "failed" and receipt["reason"] == reason, receipt
    assert not (project[0].directory / directory / "report.pdf").exists()
    assert not (project[0].directory / directory / "input/_stk-out").exists()
    assert all(item["size"] <= 3 * latex.MAX_LOG_BYTES for item in receipt["files"])
    assert latex.read_receipt(project[0], directory, attempt_id=identity) == receipt


def test_cancel_before_start_has_zero_child_execution(project, compiler_fixture):
    cancel = threading.Event()
    cancel.set()
    _, _, receipt = execute(project, cancel=cancel)
    assert receipt["state"] == "cancelled"
    assert not compiler_fixture[1].exists()


def test_timeout_stops_actual_process(project, compiler_fixture):
    compiler_fixture[0].write_text("sleep")
    started = time.monotonic()
    _, _, receipt = execute(project, timeout_seconds=0.5)
    assert receipt["state"] == "failed" and receipt["reason"] == "timeout"
    assert time.monotonic() - started < 5
    for event in map(json.loads, compiler_fixture[1].read_text().splitlines()):
        assert not alive(event["pid"])


def test_live_logs_and_explicit_cancel_stop_descendants(project, compiler_fixture):
    compiler_fixture[0].write_text("child")
    store, inputs, compiler = project
    identity, cancel, result = str(uuid4()), threading.Event(), []
    directory = "results/workflow-runs/" + identity
    thread = threading.Thread(target=lambda: result.append(latex.compile_frozen(store, inputs, compiler,
        attempt_id=identity, directory=directory, cancel=cancel)))
    thread.start()
    try:
        until(lambda: compiler_fixture[2].exists())
        until(lambda: b"READY" in base64.b64decode(latex.read_log(store, directory, attempt_id=identity)["data"]))
        with pytest.raises(latex.LatexError, match="live execution"):
            latex.recover(store, directory, attempt_id=identity)
    finally:
        cancel.set()
        thread.join(timeout=6)
    assert not thread.is_alive() and result[0]["state"] == "cancelled"
    pid = json.loads(compiler_fixture[2].read_text())["pid"]
    until(lambda: not alive(pid))


def test_identity_publish_failure_never_authorizes_compiler(project, compiler_fixture, monkeypatch):
    write = latex._write
    def fail(path, value):
        if value.get("runner"):
            raise OSError("controlled identity publication failure")
        write(path, value)
    monkeypatch.setattr(latex, "_write", fail)
    with pytest.raises(OSError, match="controlled identity"):
        execute(project)  # terminal publication deliberately fails too
    assert not compiler_fixture[1].exists()


@pytest.mark.parametrize("change", ["digest", "foreign", "path", "duplicate", "entry"])
def test_forged_input_closure_rejected_before_process_or_directory(project, compiler_fixture, change):
    store, original, compiler = project
    inputs = deepcopy(original)
    if change == "digest": inputs["assets"][0]["sha256"] = "0" * 64
    if change == "foreign": inputs["project_id"] = str(uuid4())
    if change == "path": inputs["assets"][0]["path"] = "../main.tex"
    if change == "duplicate": inputs["assets"].append(inputs["assets"][0])
    if change == "entry": inputs["entry_path"] = "missing.tex"
    with pytest.raises((latex.LatexError, ProjectError)):
        execute((store, inputs, compiler))
    assert not compiler_fixture[1].exists()
    assert not (store.directory / "results").exists()


def test_changed_compiler_rejected_without_execution(project, compiler_fixture):
    descriptor = deepcopy(project[2])
    descriptor["sha256"] = "0" * 64
    with pytest.raises(latex.LatexError, match="compiler changed"):
        execute((project[0], project[1], descriptor))
    assert not compiler_fixture[1].exists()


def test_unknown_compiler_fails_after_probe_without_compiling(project, compiler_fixture):
    compiler_fixture[0].write_text("unknown_compiler")
    identity, directory, receipt = execute(project)
    assert receipt["state"] == "failed" and receipt["reason"] == "compile_error"
    assert len(compiler_fixture[1].read_text().splitlines()) == 1
    assert latex.read_receipt(project[0], directory, attempt_id=identity) == receipt


def test_fixed_profiles_disable_shell_escape_and_package_installer(project, compiler_fixture, monkeypatch):
    monkeypatch.setenv("TEXINPUTS", "/not-authorized-by-the-frozen-selection")
    monkeypatch.setenv("PYTHONHOME", "/not-an-authorized-python-runtime")
    _, _, receipt = execute(project)
    assert receipt["state"] == "succeeded", receipt
    events = list(map(json.loads, compiler_fixture[1].read_text().splitlines()))
    assert events[1]["argv"][1:] == ["-no-shell-escape", "-interaction=nonstopmode", "-halt-on-error",
        "-file-line-error", "-recorder", "-jobname=report", "-output-directory=_stk-out", "./main.tex"]
    miktex = latex._arguments(project[2], project[1], "miktex")
    assert "--disable-installer" in miktex and "--no-shell-escape" in miktex


def test_same_attempt_directory_cannot_be_replayed(project, compiler_fixture):
    identity, directory, _ = execute(project)
    before = compiler_fixture[1].read_bytes()
    with pytest.raises(FileExistsError):
        latex.compile_frozen(*project, attempt_id=identity, directory=directory)
    assert compiler_fixture[1].read_bytes() == before


@pytest.mark.parametrize("component", ["results", "results/workflow-runs", "results/workflow-runs/attempt"])
@pytest.mark.parametrize("when", ["before_mkdir", "after_mkdir", "read_existing"])
def test_compilation_directory_rejects_reparse_attributes_on_each_component(tmp_path, monkeypatch, component, when):
    from types import SimpleNamespace

    root = tmp_path / "project"
    root.mkdir()
    store = SimpleNamespace(directory=root)
    target = root / component
    target.parent.mkdir(parents=True, exist_ok=True)
    # The leaf is genuinely new for the post-mkdir check, preserving no-replay.
    if when != "after_mkdir" or target.name != "attempt":
        target.mkdir(exist_ok=True)
    actual_stat, actual_mkdir = Path.lstat, Path.mkdir
    created, observed, marked = [], [], []

    def lstat(path, *args, **kwargs):
        info = actual_stat(path, *args, **kwargs)
        if path == target:
            observed.append(path)
            if when != "after_mkdir" or marked:
                values = {key: getattr(info, key) for key in dir(info) if key.startswith("st_")}
                values["st_file_attributes"] = getattr(info, "st_file_attributes", 0) | 0x400
                # A directory junction can have S_IFDIR without S_IFLNK.
                assert stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode)
                return SimpleNamespace(**values)
        return info

    def mkdir(path, *args, **kwargs):
        created.append(path)
        result = actual_mkdir(path, *args, **kwargs)
        if path == target:
            marked.append(path)
        return result

    with monkeypatch.context() as patch:
        patch.setattr(Path, "lstat", lstat)
        patch.setattr(Path, "mkdir", mkdir)
        with pytest.raises(latex.LatexError, match="links or reparse"):
            latex._directory(store, "results/workflow-runs/attempt", create=when != "read_existing")
    assert observed and (bool(marked) == (when == "after_mkdir"))
    assert all(path == target or path in target.parents for path in created)
    if when == "read_existing":
        assert created == []


def test_missing_compilation_directory_is_read_only_until_explicit_create(tmp_path):
    from types import SimpleNamespace

    root = tmp_path / "project"
    root.mkdir()
    store = SimpleNamespace(directory=root)
    with pytest.raises(latex.LatexError, match="missing"):
        latex._directory(store, "results/workflow-runs/attempt")
    assert list(root.iterdir()) == []
    path = latex._directory(store, "results/workflow-runs/attempt", create=True)
    assert path == root / "results/workflow-runs/attempt" and path.is_dir()
    assert latex._directory(store, "results/workflow-runs/attempt") == path
    with pytest.raises(FileExistsError):
        latex._directory(store, "results/workflow-runs/attempt", create=True)


@pytest.mark.skipif(os.name != "nt", reason="Actual Windows directory junctions require Windows")
@pytest.mark.parametrize("component", ["results", "results/workflow-runs", "results/workflow-runs/attempt"])
@pytest.mark.parametrize("create", [False, True])
def test_actual_windows_junction_cannot_redirect_compilation_directories(tmp_path, component, create):
    from types import SimpleNamespace
    import _winapi

    root, outside = tmp_path / "project", tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    marker = outside / "unchanged.txt"
    marker.write_bytes(b"public junction boundary fixture")
    junction = root / component
    junction.parent.mkdir(parents=True, exist_ok=True)
    # CPython's Windows API takes (existing target, new junction), positional only.
    # Failure is a test failure on Windows, not a capability skip.
    _winapi.CreateJunction(str(outside), str(junction))
    try:
        info = junction.lstat()
        assert info.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT
        assert not junction.is_symlink() and junction.samefile(outside)
        with pytest.raises(latex.LatexError, match="links or reparse"):
            latex._directory(SimpleNamespace(directory=root), "results/workflow-runs/attempt", create=create)
        assert list(outside.iterdir()) == [marker]
        assert marker.read_bytes() == b"public junction boundary fixture"
    finally:
        junction.rmdir()  # Remove the junction itself, never its target contents.


def test_log_path_and_wrong_identity_cannot_authorize_host_reads(project, compiler_fixture):
    identity, directory, _ = execute(project)
    with pytest.raises(latex.LatexError):
        latex.read_log(project[0], directory, attempt_id=identity, stream="../../outside")
    with pytest.raises(latex.LatexError):
        latex.read_log(project[0], directory, attempt_id=str(uuid4()))
    with pytest.raises(latex.LatexError):
        latex.read_log(project[0], directory, attempt_id=identity, limit=latex.MAX_LOG_PAGE + 1)


def test_diagnostic_columns_are_optional_and_paths_are_selected_only(project):
    raw = b"/tmp/arbitrary.tex:1:2: ignore\nmain.tex:0: bad\nmain.tex:3: valid\nmain.tex:5:9: valid column\n"
    result = latex._diagnostics(raw, project[1])
    assert [(item["line"], item["column"]) for item in result] == [(3, None), (5, 9)]


def test_native_diagnostic_spellings_only_map_known_staged_inputs(project):
    from pathlib import PureWindowsPath
    work = PureWindowsPath("C:/controlled/attempt/input")
    raw = ("C:\\controlled\\attempt\\input\\sub\\章节.tex:3:4: staged Windows file\n"
           "C:/controlled/attempt/input/main.tex:5: staged forward path\n"
           ".\\sub\\章节.tex:8: relative Windows file\n"
           "C:/controlled/attempt/input/../private.tex:2: not selected\n"
           "C:/elsewhere/main.tex:1: not selected\n").encode("utf-8")
    result = latex._diagnostics(raw, project[1], work)
    assert [(item["path"], item["line"], item["column"]) for item in result] == [
        ("sub/章节.tex", 3, 4), ("main.tex", 5, None), ("sub/章节.tex", 8, None)]
    assert {item["record_id"] for item in result} == {item["record_id"] for item in project[1]["assets"]}


@pytest.mark.parametrize("change", ["diagnostic_record", "diagnostic_hash", "diagnostic_path", "line", "column",
    "output_path", "duplicate_output", "output_size", "compiler_shape", "owner", "terminal_files"])
def test_damaged_receipt_never_authorizes_diagnostic_or_log_reads(project, compiler_fixture, change):
    identity, directory, receipt = execute(project)
    bad = deepcopy(receipt)
    if change == "diagnostic_record": bad["diagnostics"][0]["record_id"] = str(uuid4())
    if change == "diagnostic_hash": bad["diagnostics"][0]["source_sha256"] = "0" * 64
    if change == "diagnostic_path": bad["diagnostics"][0]["path"] = "/private/arbitrary.tex"
    if change == "line": bad["diagnostics"][0]["line"] = True
    if change == "column": bad["diagnostics"][0]["column"] = 2147483648
    if change == "output_path": bad["files"][1]["path"] = "../outside.txt"
    if change == "duplicate_output": bad["files"][1] = bad["files"][0]
    if change == "output_size": bad["files"][1]["size"] = 4 * 1024 * 1024
    if change == "compiler_shape": bad["compiler"]["size"] = True
    if change == "owner": bad["owner"] = None
    if change == "terminal_files": bad["files"] = []
    (project[0].directory / directory / "compile.json").write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(latex.LatexError):
        latex.read_receipt(project[0], directory, attempt_id=identity)
    with pytest.raises(latex.LatexError):
        latex.read_log(project[0], directory, attempt_id=identity)


def test_terminal_log_same_length_tamper_is_rejected(project, compiler_fixture):
    identity, directory, _ = execute(project)
    log = project[0].directory / directory / "stdout.txt"
    raw = log.read_bytes()
    log.write_bytes(b"X" + raw[1:])
    with pytest.raises(latex.LatexError, match="checksum"):
        latex.read_log(project[0], directory, attempt_id=identity, limit=7)


def test_atomic_receipt_replacement_yields_one_complete_generation(project, compiler_fixture, monkeypatch):
    from suan.project import snapshots
    identity, directory, old = execute(project)
    path = project[0].directory / directory / "compile.json"
    new = deepcopy(old)
    new["version"] += "\nnext complete publication"
    reader, replaced = snapshots._reader, []
    def replace_after_open(candidate, **options):
        stream = reader(candidate, **options)
        if candidate == path and not replaced:
            replaced.append(True)
            latex._write(path, new)
        return stream
    monkeypatch.setattr(snapshots, "_reader", replace_after_open)
    assert latex.read_receipt(project[0], directory, attempt_id=identity) == old
    assert latex.read_receipt(project[0], directory, attempt_id=identity) == new


@pytest.mark.parametrize("changed_during_read", [False, True])
def test_windows_fd_change_time_is_checked_within_its_own_api(tmp_path, monkeypatch, changed_during_read):
    from types import SimpleNamespace
    path = tmp_path / "source.tex"
    path.write_bytes(b"frozen source")
    actual = os.fstat
    calls = []

    def fd_stat(fd):
        info = actual(fd)
        values = {key: getattr(info, key) for key in dir(info) if key.startswith("st_")}
        calls.append(fd)
        # fstat and path.lstat have different ctime meanings on Windows 3.12.
        # A further fd-to-fd change must still be rejected, regardless of path metadata.
        values["st_ctime_ns"] += 2 if changed_during_read and len(calls) > 1 else 1
        return SimpleNamespace(**values)

    # Keep the real os module and pathlib unchanged; only the reader's API interpretation is Windows.
    monkeypatch.setattr(latex, "os", SimpleNamespace(name="nt", fstat=fd_stat))
    if changed_during_read:
        with pytest.raises(latex.LatexError, match="changed"):
            latex._regular(path, 1024)
    else:
        assert latex._regular(path, 1024) == b"frozen source"
    assert len(calls) == 2


def test_atomic_record_reader_is_not_inherited_by_child_processes(tmp_path):
    from suan.project.snapshots import _reader
    path = tmp_path / "record.json"
    path.write_bytes(b"{}")
    with _reader(path, share_delete=True) as stream:
        assert not os.get_inheritable(stream.fileno())
        assert stream.read() == b"{}"


@pytest.mark.parametrize("boundary", ["before_authorization", "interrupted_publication", "running_with_descendant"])
def test_lost_owner_stops_gate_and_process_tree_without_replay(project, compiler_fixture, tmp_path, boundary):
    """Kill the actual executor, rather than merely calling its cancellation handler."""
    store, inputs, compiler = project
    identity = str(uuid4())
    directory = "results/workflow-runs/" + identity
    ready = tmp_path / "publication-ready.json"
    config = tmp_path / "execution.json"
    compiler_fixture[0].write_text("child")
    config.write_text(json.dumps({"project": str(store.directory), "inputs": inputs, "compiler": compiler,
        "attempt_id": identity, "directory": directory, "script": str(tmp_path / "compiler.py"),
        "ready": str(ready), "boundary": boundary}), encoding="utf-8")
    owner_source = """
import json, pathlib, sys, time
from suan.documents import latex
from suan.project import ProjectStore
value = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding='utf-8'))
actual_run, actual_write = latex._run_command, latex._write
def controlled(argv, *args, **kwargs):
    actual = [sys.executable, '-X', 'utf8', value['script'], *argv[1:]]
    args[2]['argv'] = actual
    return actual_run(actual, *args, **kwargs)
def pause_before_identity(path, record):
    if record.get('runner'):
        if value['boundary'] == 'interrupted_publication':
            for name in ('compile.json', 'stdout.txt', 'stderr.txt', 'compiler.txt'):
                (path.parent / (name + '.new')).write_bytes(b'interrupted publication')
        pathlib.Path(value['ready']).write_text(json.dumps(record['runner']))
        time.sleep(60)
    return actual_write(path, record)
latex._run_command = controlled
if value['boundary'] != 'running_with_descendant':
    latex._write = pause_before_identity
latex.compile_frozen(ProjectStore(value['project']), value['inputs'], value['compiler'],
    attempt_id=value['attempt_id'], directory=value['directory'])
"""
    # Named infrastructure only: no credentials or model environment reaches this child.
    environment = {key: os.environ[key] for key in ("PATH", "SystemRoot", "WINDIR") if key in os.environ}
    owner = subprocess.Popen([sys.executable, "-c", owner_source, str(config)], env=environment,
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        handshake = ready if boundary != "running_with_descendant" else compiler_fixture[2]
        until(handshake.exists, seconds=10)
        if boundary != "running_with_descendant":
            processes = [json.loads(ready.read_text())["pid"]]
        else:
            receipt = latex.read_receipt(store, directory, attempt_id=identity)
            processes = [receipt["runner"]["pid"], json.loads(handshake.read_text())["pid"]]
            until(lambda: b"READY" in base64.b64decode(latex.read_log(store, directory, attempt_id=identity)["data"]))
        owner.kill()
        owner.wait(timeout=5)
        for pid in processes:
            until(lambda: not alive(pid), seconds=5)
        trace_before = compiler_fixture[1].read_bytes() if compiler_fixture[1].exists() else b""
        recovered = latex.recover(store, directory, attempt_id=identity)
        assert recovered["state"] == "interrupted"
        assert latex.recover(store, directory, attempt_id=identity) == recovered
        page = latex.read_log(store, directory, attempt_id=identity)
        assert page["terminal"] is True
        if boundary != "running_with_descendant":
            assert trace_before == b"" and page["data"] == ""
        else:
            assert b"READY" in base64.b64decode(page["data"])
        assert (compiler_fixture[1].read_bytes() if compiler_fixture[1].exists() else b"") == trace_before
        if boundary == "interrupted_publication":
            for name in ("compile.json", "stdout.txt", "stderr.txt", "compiler.txt"):
                assert (store.directory / directory / (name + ".new")).read_bytes() == b"interrupted publication"
    finally:
        if owner.poll() is None:
            owner.kill()
        owner.communicate(timeout=5)
