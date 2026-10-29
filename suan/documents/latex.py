"""Explicit, bounded local LaTeX compilation of a frozen project selection.

This module is not a graph node or a scheduler. Preparation never spawns a process.
The caller owns the workflow claim, cancellation event and publication of the returned
files into Files/Snapshots/Reports. Each execution requires a new attempt directory;
reading or recovering a receipt never reruns a compiler. TeX is a local program, not
an OS sandbox. Only fixed pdfLaTeX/XeLaTeX profiles are admitted; shell escape and
MiKTeX's package installer are disabled.
"""
from __future__ import annotations

import base64
import codecs
import hashlib
import json
import math
import os
from pathlib import Path, PureWindowsPath
import queue
import re
import signal
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time

MAX_INPUTS = 60
MAX_FILE_BYTES = 4 * 1024 * 1024
MAX_INPUT_BYTES = 24 * 1024 * 1024
MAX_LOG_BYTES = 512 * 1024
MAX_RECEIPT_BYTES = 256 * 1024
MAX_COMPILER_BYTES = 256 * 1024 * 1024
MAX_DIAGNOSTICS = 256
MAX_LOG_PAGE = 64 * 1024
FORMAT = "stk.latex-compile/1"
_SHA = re.compile(r"[0-9a-f]{64}\Z")
INPUT_SUFFIXES = frozenset({".tex", ".bib", ".bst", ".sty", ".cls", ".png", ".jpg", ".jpeg", ".pdf"})
_LOGS = {"stdout.txt", "stderr.txt", "compiler.txt"}


class LatexError(ValueError):
    """The compilation selection or stored evidence is not admissible."""


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _sha(value):
    return hashlib.sha256(_json(value)).hexdigest()


def _uuid(value):
    from uuid import UUID
    try:
        valid = type(value) is str and str(UUID(value)) == value
    except ValueError:
        valid = False
    if not valid:
        raise LatexError("Expected a canonical UUID")
    return value


def _regular(path, maximum, *, atomic_record=False):
    from suan.project.snapshots import _reader, _signature
    before_path = path.lstat()
    if stat.S_ISLNK(before_path.st_mode) or not stat.S_ISREG(before_path.st_mode):
        raise LatexError("Expected a regular, non-link file")
    with _reader(path) as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size > maximum:
            raise LatexError("File exceeds its byte budget or is not regular")
        raw = stream.read(maximum + 1)
        after = os.fstat(stream.fileno())
    signatures = (_signature(before), _signature(after))
    stable = signatures[0][:4] == signatures[1][:4] if atomic_record else signatures[0] == signatures[1]
    if (len(raw) > maximum or not stable
            or not atomic_record and _signature(after) != _signature(path.lstat())):
        raise LatexError("File changed while reading or exceeds its byte budget")
    return raw


def _write_bytes(path, raw):
    from suan.project.snapshots import _sync_directory
    temporary = None
    try:
        # A killed writer may leave a partial temporary file. A fresh name lets
        # recovery publish without adopting or deleting that unknown preimage.
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=path.name + ".", suffix=".new", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        _sync_directory(path.parent)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _write(path, value):
    """Publish a small record durably before permitting any compiler execution."""
    raw = _json(value)
    if len(raw) > MAX_RECEIPT_BYTES:
        raise LatexError("Compilation metadata exceeds 256 KiB")
    _write_bytes(path, raw)


def _directory(store, directory, *, create=False):
    """Only a caller-selected project-local attempt directory, with no link traversal."""
    from suan.project.reports import _path
    _path(directory)
    parts = directory.split("/")
    if parts[:2] != ["results", "workflow-runs"] or len(parts) < 3:
        raise LatexError("Compilation attempts belong below results/workflow-runs")
    current = store.directory
    for index, part in enumerate(parts):
        current = current / part
        if current.is_symlink():
            raise LatexError("Compilation directories cannot contain links")
        if create:
            current.mkdir(mode=0o700, exist_ok=index != len(parts) - 1)
        if not current.is_dir():
            raise LatexError("Compilation directory is missing or is not a directory")
    return current


def freeze_inputs(store, snapshot_id, assets, *, entry_path, expected_revision):
    """Read metadata only; bind explicit portable paths to one existing file snapshot."""
    from suan.project.reports import _paths, _revision, _snapshot
    _uuid(snapshot_id)
    if type(expected_revision) is not int or expected_revision < 0:
        raise LatexError("Expected revision must be a nonnegative integer")
    if type(assets) is not list or not 1 <= len(assets) <= MAX_INPUTS:
        raise LatexError("Select between 1 and 60 explicit input files")
    with store._connect() as db:
        _revision(db, expected_revision)
        snapshot = _snapshot(store, db, snapshot_id)
    selected, seen, total = [], set(), 0
    available = {item["record_id"]: item for item in snapshot["manifest"]["files"]}
    for item in assets:
        if type(item) is not dict or set(item) != {"record_id", "path"}:
            raise LatexError("Input selections are exactly record_id and path")
        identity, path = _uuid(item["record_id"]), item["path"]
        if identity in seen or identity not in available:
            raise LatexError("Input records must be distinct members of the selected snapshot")
        if type(path) is not str or path.split("/")[0].casefold().startswith("_stk"):
            raise LatexError("Input paths cannot use the reserved _stk namespace")
        suffix = Path(path).suffix.lower()
        if suffix not in INPUT_SUFFIXES or Path(available[identity]["name"]).suffix.lower() != suffix:
            raise LatexError("Input paths must preserve an admitted source suffix")
        source = available[identity]
        if source["size"] > MAX_FILE_BYTES:
            raise LatexError("Each input file must be at most 4 MiB")
        total += source["size"]
        selected.append({"record_id": identity, "path": path, "sha256": source["sha256"], "size": source["size"]})
        seen.add(identity)
    _paths([item["path"] for item in selected])
    if total > MAX_INPUT_BYTES or entry_path not in [item["path"] for item in selected] or Path(entry_path).suffix.lower() != ".tex":
        raise LatexError("Choose a selected .tex entry and at most 24 MiB of input files")
    value = {"format": "stk.latex-input/1", "project_id": store._project_id, "source_revision": expected_revision,
             "snapshot_id": snapshot_id, "snapshot_sha256": snapshot["sha256"], "entry_path": entry_path, "assets": selected}
    if len(_json(value)) > MAX_RECEIPT_BYTES // 2:
        raise LatexError("Frozen compilation input metadata is too large")
    return value


def freeze_compiler(path, *, engine="pdflatex"):
    """Hash the selected executable without running it or reading tool configuration."""
    if engine not in {"pdflatex", "xelatex"}:
        raise LatexError("Only the fixed pdflatex and xelatex profiles are supported")
    if type(path) is not str or len(path.encode("utf-8")) > 4096 or any(ord(c) < 32 for c in path):
        raise LatexError("Compiler path must be a bounded local path")
    candidate = Path(path)
    if not candidate.is_absolute():
        raise LatexError("Select an absolute compiler executable")
    resolved = candidate.resolve(strict=True)
    raw = _regular(resolved, MAX_COMPILER_BYTES)
    if os.name != "nt" and not os.access(resolved, os.X_OK):
        raise LatexError("Selected compiler is not executable")
    return {"format": "stk.latex-compiler/1", "engine": engine, "path": str(candidate),
            "resolved_path": str(resolved), "sha256": hashlib.sha256(raw).hexdigest(), "size": len(raw)}


def _validate_compiler(compiler):
    _compiler_shape(compiler)
    if freeze_compiler(compiler["path"], engine=compiler["engine"]) != compiler:
        raise LatexError("The compiler changed after preparation; prepare a new run")


def _compiler_shape(compiler):
    if (type(compiler) is not dict or set(compiler) != {"format", "engine", "path", "resolved_path", "sha256", "size"}
            or compiler["format"] != "stk.latex-compiler/1" or type(compiler["engine"]) is not str
            or compiler["engine"] not in {"pdflatex", "xelatex"}
            or type(compiler["sha256"]) is not str or not _SHA.fullmatch(compiler["sha256"])
            or type(compiler["size"]) is not int or not 0 < compiler["size"] <= MAX_COMPILER_BYTES):
        raise LatexError("Invalid frozen compiler descriptor")
    for field in ("path", "resolved_path"):
        path = compiler[field]
        if (type(path) is not str or len(path.encode("utf-8")) > 4096
                or any(ord(c) < 32 for c in path)
                or not (Path(path).is_absolute() or PureWindowsPath(path).is_absolute())):
            raise LatexError("Invalid frozen compiler path")


def _validate_inputs(store, inputs):
    if type(inputs) is not dict or set(inputs) != {"format", "project_id", "source_revision", "snapshot_id", "snapshot_sha256", "entry_path", "assets"}:
        raise LatexError("Invalid frozen input descriptor")
    _uuid(inputs["snapshot_id"])
    if len(_json(inputs)) > MAX_RECEIPT_BYTES // 2:
        raise LatexError("Frozen compilation input metadata is too large")
    # Rebuild against the same immutable snapshot, never against working files or current rows.
    from suan.project.reports import _snapshot
    with store._connect() as db:
        snapshot = _snapshot(store, db, inputs["snapshot_id"])
    if inputs["project_id"] != store._project_id or inputs["format"] != "stk.latex-input/1" or snapshot["sha256"] != inputs["snapshot_sha256"]:
        raise LatexError("Compilation input belongs to another project or snapshot")
    if type(inputs["source_revision"]) is not int or inputs["source_revision"] < snapshot["revision"]:
        raise LatexError("Compilation source revision precedes its snapshot")
    if type(inputs["assets"]) is not list or not 1 <= len(inputs["assets"]) <= MAX_INPUTS:
        raise LatexError("Invalid compilation asset count")
    from suan.project.reports import _paths
    if any(type(item) is not dict or set(item) != {"record_id", "path", "sha256", "size"}
           or type(item["path"]) is not str for item in inputs["assets"]):
        raise LatexError("Invalid compilation asset descriptor")
    _paths([item["path"] for item in inputs["assets"]])
    available = {item["record_id"]: item for item in snapshot["manifest"]["files"]}
    seen, total = set(), 0
    for item in inputs["assets"]:
        if type(item) is not dict or set(item) != {"record_id", "path", "sha256", "size"}:
            raise LatexError("Invalid compilation asset descriptor")
        source = available.get(_uuid(item["record_id"]))
        suffix = Path(item["path"]).suffix.lower()
        if (source is None or item["record_id"] in seen or type(item["size"]) is not int or not 0 <= item["size"] <= MAX_FILE_BYTES
                or item["sha256"] != source["sha256"] or item["size"] != source["size"] or suffix not in INPUT_SUFFIXES
                or Path(source["name"]).suffix.lower() != suffix or item["path"].split("/")[0].casefold().startswith("_stk")):
            raise LatexError("Compilation asset differs from its frozen snapshot")
        seen.add(item["record_id"])
        total += item["size"]
    if total > MAX_INPUT_BYTES or inputs["entry_path"] not in [item["path"] for item in inputs["assets"]] or Path(inputs["entry_path"]).suffix.lower() != ".tex":
        raise LatexError("Invalid compilation entry or input budget")


def _environment(work):
    # Read only named infrastructure variables; never copy credentials or model settings.
    result = {key: os.environ[key] for key in ("PATH", "SystemRoot", "WINDIR") if key in os.environ}
    result.update(HOME=str(work), USERPROFILE=str(work), TMP=str(work), TEMP=str(work), TMPDIR=str(work),
                  TEXMFOUTPUT=str(work / "_stk-out"), openin_any="p", openout_any="p", shell_escape="f")
    return result


class _Job:
    """Windows kill-on-close job; no unprotected fallback on assignment failure."""
    def __init__(self, process):
        self.handle = None
        if os.name != "nt":
            return
        import ctypes
        from ctypes import wintypes as w
        class Basic(ctypes.Structure):
            _fields_ = [("a", ctypes.c_int64), ("b", ctypes.c_int64), ("flags", w.DWORD),
                        ("min", ctypes.c_size_t), ("max", ctypes.c_size_t), ("count", w.DWORD),
                        ("affinity", ctypes.c_size_t), ("priority", w.DWORD), ("scheduling", w.DWORD)]
        class Extended(ctypes.Structure):
            _fields_ = [("basic", Basic), ("io", ctypes.c_uint64 * 6), ("process", ctypes.c_size_t),
                        ("job", ctypes.c_size_t), ("peak_process", ctypes.c_size_t), ("peak_job", ctypes.c_size_t)]
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateJobObjectW.argtypes, kernel.CreateJobObjectW.restype = [ctypes.c_void_p, w.LPCWSTR], w.HANDLE
        kernel.SetInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD]
        kernel.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
        kernel.CloseHandle.argtypes = [w.HANDLE]
        self.kernel = kernel
        self.handle = kernel.CreateJobObjectW(None, None)
        value = Extended()
        value.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.handle or not kernel.SetInformationJobObject(self.handle, 9, ctypes.byref(value), ctypes.sizeof(value)) or not kernel.AssignProcessToJobObject(self.handle, int(process._handle)):
            self.close()
            raise LatexError("Cannot establish the Windows compilation process job")

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def _gate_main():
    """Isolated stdlib bootstrap. No target execution before the parent's durable receipt."""
    raw = sys.stdin.buffer.read(16385)
    if len(raw) > 16384 or not raw.startswith(b"\x01"):
        return 125
    payload = json.loads(raw[1:])
    if os.name != "nt":
        lifeline = int(sys.argv[2])
        os.set_inheritable(lifeline, False)
        group = os.getpid()
        guardian = os.fork()
        if guardian == 0:
            # Parent owns the only write endpoint. Its death or normal cleanup closes
            # the whole execution group, including any remaining compiler children.
            try:
                os.close(0)
                os.close(1)
                os.close(2)
                while os.read(lifeline, 1):
                    pass
            finally:
                os.killpg(group, signal.SIGKILL)
            os._exit(125)
        os.close(lifeline)
        for name in ("SIGPIPE", "SIGXFZ", "SIGXFSZ"):
            if hasattr(signal, name):
                signal.signal(getattr(signal, name), signal.SIG_DFL)
        os.execvpe(payload["argv"][0], payload["argv"], payload["env"])
        return 127
    # The parent has already assigned this gate to a kill-on-close Job. The
    # compiler inherits that job. Windows does not promise POSIX same-PID exec.
    return subprocess.call(payload["argv"], env=payload["env"], stdin=subprocess.DEVNULL)


def _run_command(argv, work, root, receipt, cancel, deadline, *, budget):
    import psutil
    if cancel.is_set() or time.monotonic() >= deadline:
        return None, "cancelled" if cancel.is_set() else "timeout", {"stdout": b"", "stderr": b""}
    gate_env = {key: os.environ[key] for key in ("PATH", "SystemRoot", "WINDIR") if key in os.environ}
    payload = b"\x01" + _json({"argv": argv, "env": _environment(work)})
    if len(payload) > 16384:
        raise LatexError("Compiler invocation exceeds the fixed launch budget")
    life_read = life_write = None
    options = {}
    if os.name != "nt":
        life_read, life_write = os.pipe()
        options.update(pass_fds=(life_read,), start_new_session=True)
    else:
        options["creationflags"] = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
    process = job = None
    readers, writer, messages = [], None, queue.Queue(maxsize=8)
    persisted = {}
    stopped, reader_failed = threading.Event(), threading.Event()
    captured = {"stdout": bytearray(), "stderr": bytearray()}
    reason = None
    try:
        process = subprocess.Popen([sys.executable, "-I", "-S", str(Path(__file__).resolve()), "--gate", str(life_read or 0)],
                                   cwd=work, env=gate_env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **options)
        if life_read is not None:
            os.close(life_read)
            life_read = None
        job = _Job(process)
        child = psutil.Process(process.pid)
        receipt["runner"] = {"host": socket.gethostname(), "pid": child.pid, "create_time": child.create_time()}
        _write(root / "compile.json", receipt)
        if cancel.is_set() or time.monotonic() >= deadline:
            return None, "cancelled" if cancel.is_set() else "timeout", {"stdout": b"", "stderr": b""}
        decoders = {label: codecs.getincrementaldecoder("utf-8")("replace") for label in captured}
        if budget == MAX_LOG_BYTES:
            for label in captured:
                persisted[label] = (root / (label + ".txt")).open("xb", buffering=0)
        # This write is the authorization point, strictly after publication.
        def authorize():
            try:
                process.stdin.write(payload)
                process.stdin.close()
            except (OSError, ValueError):
                pass
        writer = threading.Thread(target=authorize, daemon=True)
        writer.start()
        def read(stream, label):
            try:
                while not stopped.is_set():
                    raw = os.read(stream.fileno(), 4096)
                    if not raw:
                        break
                    while not stopped.is_set():
                        try:
                            messages.put((label, raw), timeout=0.05)
                            break
                        except queue.Full:
                            pass
            except (OSError, ValueError):
                if not stopped.is_set():
                    reader_failed.set()
            finally:
                stream.close()
        for label in captured:
            thread = threading.Thread(target=read, args=(getattr(process, label), label), daemon=True)
            thread.start()
            readers.append(thread)
        while True:
            if reader_failed.is_set():
                raise LatexError("Compiler log pipe failed while reading")
            if cancel.is_set():
                reason = "cancelled"
            elif time.monotonic() >= deadline:
                reason = "timeout"
            try:
                label, raw = messages.get(timeout=0.02)
                remaining = budget - sum(len(value) for value in captured.values())
                accepted = raw[:max(0, remaining)]
                captured[label].extend(accepted)
                if label in persisted:
                    persisted[label].write(decoders[label].decode(accepted).encode("utf-8"))
                if len(raw) > remaining:
                    reason = "log_limit"
            except queue.Empty:
                pass
            # TeX writes its own .log as well as stdout. Monitor it independently;
            # terminal publication never adopts an oversized or linked file.
            logfile = work / "_stk-out" / "report.log"
            if logfile.exists() and (logfile.is_symlink() or logfile.stat().st_size > MAX_LOG_BYTES):
                reason = "log_limit"
            if reason:
                break
            if process.poll() is not None and all(not thread.is_alive() for thread in readers) and messages.empty():
                break
        if reason:
            return None, reason, {key: bytes(value) for key, value in captured.items()}
        return process.returncode, None, {key: bytes(value) for key, value in captured.items()}
    finally:
        stopped.set()
        if life_write is not None:
            os.close(life_write)
        if life_read is not None:
            os.close(life_read)
        if job is not None:
            job.close()
        if process is not None:
            if process.poll() is None:
                if os.name != "nt":
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                else:
                    process.kill()
            process.wait(timeout=5)
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream and not stream.closed:
                    stream.close()
        if writer:
            writer.join(timeout=1)
        for thread in readers:
            thread.join(timeout=1)
        for label, stream in persisted.items():
            try:
                stream.write(decoders[label].decode(b"", final=True).encode("utf-8"))
                os.fsync(stream.fileno())
            finally:
                stream.close()


def _diagnostics(raw, inputs, work=None):
    """Log paths only locate already selected virtual inputs; never authorize host paths."""
    files = {}
    for item in inputs["assets"]:
        path = item["path"]
        # Only these exact spellings name an already selected input. In particular
        # no normalization of '..', symlinks or arbitrary diagnostic paths occurs.
        spellings = {path, "./" + path, path.replace("/", "\\"), ".\\" + path.replace("/", "\\")}
        if work is not None:
            staged = work / path
            spellings.update((str(staged), staged.as_posix()))
        files.update((spelling, item) for spelling in spellings)
    result = []
    for line in raw.decode("utf-8", errors="replace").splitlines():
        match = re.match(r"^(.{1,8192}?):([0-9]{1,10})(?::([0-9]{1,10}))?:\s*(.{1,2048})$", line)
        if not match or match[1] not in files:
            continue
        row, column = int(match[2]), int(match[3]) if match[3] else None
        if not 1 <= row <= 2147483647 or column is not None and not 1 <= column <= 2147483647:
            continue
        item = files[match[1]]
        diagnostic = {"record_id": item["record_id"], "path": item["path"], "source_sha256": item["sha256"],
                      "line": row, "column": column, "message": match[4]}
        if len(_json([*result, diagnostic])) > 64 * 1024:
            break
        result.append(diagnostic)
        if len(result) == MAX_DIAGNOSTICS:
            break
    return result


def _arguments(compiler, inputs, distribution):
    prefix = "--" if distribution == "miktex" else "-"
    flags = [prefix + value for value in ("no-shell-escape", "interaction=nonstopmode", "halt-on-error", "file-line-error",
                                          "recorder", "jobname=report", "output-directory=_stk-out")]
    if distribution == "miktex":
        flags.append("--disable-installer")
    return [compiler["path"], *flags, "./" + inputs["entry_path"]]


def compile_frozen(store, inputs, compiler, *, attempt_id, directory, cancel=None, timeout_seconds=60):
    """The only execution entry. A terminal receipt never implies automatic report creation."""
    _uuid(attempt_id)
    if type(timeout_seconds) not in (int, float) or not math.isfinite(timeout_seconds) or not 0 < timeout_seconds <= 300:
        raise LatexError("Compilation timeout must be positive and at most 300 seconds")
    inputs, compiler = json.loads(_json(inputs)), json.loads(_json(compiler))
    _validate_inputs(store, inputs)
    _validate_compiler(compiler)
    cancel = cancel if cancel is not None else threading.Event()
    root = _directory(store, directory, create=True)
    work = root / "input"
    work.mkdir(mode=0o700)
    (work / "_stk-out").mkdir(mode=0o700)
    receipt = {"format": FORMAT, "attempt_id": attempt_id, "project_id": store._project_id,
               "inputs": inputs, "inputs_sha256": _sha(inputs), "compiler": compiler, "state": "preparing",
               "runner": None, "exit_code": None, "reason": None, "version": "", "argv": [],
               "files": [], "diagnostics": []}
    import psutil
    owner = psutil.Process()
    receipt["owner"] = {"host": socket.gethostname(), "pid": owner.pid, "create_time": owner.create_time()}
    _write(root / "compile.json", receipt)
    streams = {name: None for name in sorted(_LOGS)}
    streams["compiler.txt"] = b""
    try:
        for item in inputs["assets"]:
            if cancel.is_set():
                receipt.update(state="cancelled", reason="cancelled")
                return receipt
            source = store.snapshots.resolve(inputs["snapshot_id"], item["record_id"])
            raw = _regular(Path(source["path"]), MAX_FILE_BYTES)
            if len(raw) != item["size"] or hashlib.sha256(raw).hexdigest() != item["sha256"]:
                raise LatexError("Frozen input bytes do not match the selected manifest")
            target = work / item["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as output:
                output.write(raw)
        deadline = time.monotonic() + timeout_seconds
        receipt["state"] = "running"
        version_argv = [compiler["path"], "--version"]
        receipt["argv"] = version_argv
        code, reason, output = _run_command(version_argv, work, root, receipt, cancel, deadline, budget=16384)
        version = (output["stdout"] + output["stderr"]).decode("utf-8", errors="replace")
        receipt["version"] = version
        if reason or code != 0:
            receipt.update(state="cancelled" if reason == "cancelled" else "failed", reason=reason or "compiler_probe_failed", exit_code=code)
            return receipt
        distribution = "miktex" if "miktex" in version.lower() else "texlive" if "tex live" in version.lower() else None
        if distribution is None:
            raise LatexError("Only recognized TeX Live and MiKTeX compiler profiles are supported")
        if len(_json(receipt)) > MAX_RECEIPT_BYTES - 80 * 1024:
            raise LatexError("Compiler version metadata leaves insufficient space for bounded diagnostic evidence")
        _validate_compiler(compiler)
        receipt["argv"] = _arguments(compiler, inputs, distribution)
        code, reason, output = _run_command(receipt["argv"], work, root, receipt, cancel, deadline, budget=MAX_LOG_BYTES)
        streams["stdout.txt"], streams["stderr.txt"] = output["stdout"], output["stderr"]
        logfile = work / "_stk-out" / "report.log"
        if logfile.exists():
            from suan.project.snapshots import _reader
            with _reader(logfile) as log:
                if not stat.S_ISREG(os.fstat(log.fileno()).st_mode):
                    raise LatexError("Compiler log is not a regular file")
                raw = log.read(MAX_LOG_BYTES + 1)
            streams["compiler.txt"] = raw[:MAX_LOG_BYTES]
            if len(raw) > MAX_LOG_BYTES:
                reason = "log_limit"
        receipt["diagnostics"] = _diagnostics(streams["stdout.txt"] + b"\n" + streams["stderr.txt"] + b"\n" + streams["compiler.txt"], inputs, work)
        receipt.update(exit_code=code, state="cancelled" if reason == "cancelled" else "failed", reason=reason or "compiler_failed")
        if reason or code != 0:
            return receipt
        _validate_compiler(compiler)
        for item in inputs["assets"]:
            if hashlib.sha256(_regular(work / item["path"], MAX_FILE_BYTES)).hexdigest() != item["sha256"]:
                raise LatexError("Compiler changed a frozen input; no output is accepted")
        pdf = _regular(work / "_stk-out" / "report.pdf", MAX_FILE_BYTES)
        if not pdf.startswith(b"%PDF-"):
            raise LatexError("Compiler produced no PDF header; output is not accepted")
        if cancel.is_set():
            receipt.update(state="cancelled", reason="cancelled")
            return receipt
        # Header admission is not a full PDF decoder or proof of visual correctness.
        _write_bytes(root / "report.pdf", pdf)
        receipt["files"].append({"path": "report.pdf", "sha256": hashlib.sha256(pdf).hexdigest(), "size": len(pdf)})
        receipt.update(state="succeeded", reason=None)
        return receipt
    except (OSError, ValueError) as exc:
        receipt.update(state="failed", reason="compile_error", error=str(exc)[:2048])
        return receipt
    finally:
        # Scratch aux/log files are not historical assets. Only bounded, checked
        # files and the frozen input tree survive terminal publication.
        scratch = work / "_stk-out"
        if scratch.is_symlink():
            scratch.unlink()
        elif scratch.exists():
            shutil.rmtree(scratch)
        for name, raw in streams.items():
            # Public log text is UTF-8; raw source byte offsets are not claimed.
            if raw is None:
                # A transport exception must not erase already persisted live text.
                path = root / name
                text = _regular(path, 3 * MAX_LOG_BYTES) if path.exists() else b""
            else:
                text = raw.decode("utf-8", errors="replace").encode("utf-8")
            _write_bytes(root / name, text)
            receipt["files"].append({"path": name, "sha256": hashlib.sha256(text).hexdigest(), "size": len(text)})
        _write(root / "compile.json", receipt)


def read_receipt(store, directory, *, attempt_id):
    root = _directory(store, directory)
    from suan.project.analysis_runs import _unpack
    # Replacement is atomic: either complete generation is admissible. Requiring
    # the pathname to retain its inode would reject a normal concurrent publication.
    receipt = _unpack(_regular(root / "compile.json", MAX_RECEIPT_BYTES, atomic_record=True).decode("utf-8"), MAX_RECEIPT_BYTES)
    required = {"format", "attempt_id", "project_id", "inputs", "inputs_sha256", "compiler", "state", "runner", "owner",
                "exit_code", "reason", "version", "argv", "files", "diagnostics"}
    if type(receipt) is not dict or set(receipt) not in (required, required | {"error"}):
        raise LatexError("Invalid compilation receipt fields")
    if receipt.get("format") != FORMAT or receipt.get("project_id") != store._project_id or receipt.get("attempt_id") != _uuid(attempt_id):
        raise LatexError("Compilation receipt identity does not match")
    _validate_inputs(store, receipt["inputs"])
    if receipt.get("inputs_sha256") != _sha(receipt["inputs"]):
        raise LatexError("Compilation input checksum does not match")
    _compiler_shape(receipt["compiler"])  # Historical reads do not inspect the current executable.
    if type(receipt["state"]) is not str or receipt["state"] not in {"preparing", "running", "succeeded", "failed", "cancelled", "interrupted"}:
        raise LatexError("Invalid compilation lifecycle state")
    if receipt["owner"] is None:
        raise LatexError("Compilation owner identity is required")
    for owner in (receipt["owner"], receipt["runner"]):
        if owner is not None and (type(owner) is not dict or set(owner) != {"host", "pid", "create_time"}
                                  or type(owner["host"]) is not str or not 1 <= len(owner["host"]) <= 255
                                  or type(owner["pid"]) is not int or owner["pid"] <= 0
                                  or type(owner["create_time"]) not in (int, float) or not math.isfinite(owner["create_time"])):
            raise LatexError("Invalid compilation execution identity")
    if (receipt["exit_code"] is not None and type(receipt["exit_code"]) is not int
            or type(receipt["version"]) is not str or len(receipt["version"].encode("utf-8")) > 3 * 16384
            or type(receipt["argv"]) is not list or len(receipt["argv"]) > 16
            or any(type(arg) is not str or len(arg.encode("utf-8")) > 8192 for arg in receipt["argv"])
            or "error" in receipt and (type(receipt["error"]) is not str or len(receipt["error"]) > 2048)):
        raise LatexError("Invalid compilation invocation or exit evidence")
    reasons = {"cancelled", "timeout", "log_limit", "compiler_probe_failed", "compiler_failed", "compile_error", "execution_owner_lost"}
    if receipt["reason"] is not None and (type(receipt["reason"]) is not str or receipt["reason"] not in reasons):
        raise LatexError("Invalid compilation failure reason")
    if (type(receipt["files"]) is not list or len(receipt["files"]) > 4
            or type(receipt["diagnostics"]) is not list or len(receipt["diagnostics"]) > MAX_DIAGNOSTICS
            or len(_json(receipt["diagnostics"])) > 64 * 1024):
        raise LatexError("Invalid compilation evidence budget")
    names = set()
    for item in receipt["files"]:
        if (type(item) is not dict or set(item) != {"path", "sha256", "size"}
                or type(item["path"]) is not str or item["path"] not in _LOGS | {"report.pdf"}
                or item["path"] in names or type(item["sha256"]) is not str or not _SHA.fullmatch(item["sha256"])
                or type(item["size"]) is not int or not 0 <= item["size"] <= (MAX_FILE_BYTES if item["path"] == "report.pdf" else 3 * MAX_LOG_BYTES)):
            raise LatexError("Invalid compilation output descriptor")
        names.add(item["path"])
    if receipt["state"] == "succeeded":
        if names != _LOGS | {"report.pdf"} or receipt["exit_code"] != 0 or receipt["reason"] is not None or receipt["runner"] is None:
            raise LatexError("Successful compilation receipt is incomplete")
    elif "report.pdf" in names:
        raise LatexError("Unsuccessful compilation cannot publish a PDF")
    if receipt["state"] in {"failed", "cancelled", "interrupted"} and (names != _LOGS or receipt["reason"] is None):
        raise LatexError("Terminal compilation failure evidence is incomplete")
    files = {item["path"]: item for item in receipt["inputs"]["assets"]}
    for item in receipt["diagnostics"]:
        if (type(item) is not dict or set(item) != {"record_id", "path", "source_sha256", "line", "column", "message"}
                or type(item["path"]) is not str or item["path"] not in files):
            raise LatexError("Invalid compilation diagnostic source")
        source = files[item["path"]]
        if (item["record_id"] != source["record_id"] or item["source_sha256"] != source["sha256"]
                or type(item["line"]) is not int or not 1 <= item["line"] <= 2147483647
                or item["column"] is not None and (type(item["column"]) is not int or not 1 <= item["column"] <= 2147483647)
                or type(item["message"]) is not str or not 1 <= len(item["message"]) <= 2048):
            raise LatexError("Compilation diagnostic differs from its frozen input")
    return receipt


def read_log(store, directory, *, attempt_id, stream="stdout.txt", offset=0, limit=MAX_LOG_PAGE,
             expected_binding=None):
    if type(stream) is not str or stream not in _LOGS or type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= MAX_LOG_PAGE:
        raise LatexError("Invalid bounded compilation log page")
    receipt = read_receipt(store, directory, attempt_id=attempt_id)
    if expected_binding is not None and {key: receipt[key] for key in ("compiler", "inputs")} != expected_binding:
        raise LatexError("Compilation log receipt differs from its bound compiler or inputs")
    root = _directory(store, directory)
    path = root / stream
    terminal = receipt["state"] in {"succeeded", "failed", "cancelled", "interrupted"}
    if terminal:
        descriptor = next((item for item in receipt["files"] if item["path"] == stream), None)
        if descriptor is None:
            raise LatexError("Terminal compilation log has no frozen descriptor")
        raw = _regular(path, 3 * MAX_LOG_BYTES)
        if len(raw) != descriptor["size"] or hashlib.sha256(raw).hexdigest() != descriptor["sha256"]:
            raise LatexError("Compilation log differs from its frozen checksum")
    elif path.exists():
        from suan.project.snapshots import _reader
        if path.is_symlink():
            raise LatexError("Compilation log cannot be a link")
        with _reader(path) as source:
            info = os.fstat(source.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > 3 * MAX_LOG_BYTES:
                raise LatexError("Invalid live compilation log")
            # Append may continue; only the observed bounded prefix belongs to this page.
            raw = source.read(info.st_size)
    else:
        raw = b""
    if offset > len(raw):
        raise LatexError("Log offset exceeds the persisted log")
    selected = raw[offset:offset + limit]
    return {"attempt_id": attempt_id, "stream": stream, "offset": offset, "next_offset": offset + len(selected),
            "data": base64.b64encode(selected).decode("ascii"), "terminal": terminal}


def recover(store, directory, *, attempt_id):
    """Observe lost execution without spawning, signalling a metadata-supplied PID or retrying."""
    import psutil
    root = _directory(store, directory)
    receipt = read_receipt(store, directory, attempt_id=attempt_id)
    if receipt["state"] in {"succeeded", "failed", "cancelled", "interrupted"}:
        return receipt
    for owner in (receipt.get("owner"), receipt.get("runner")):
        if not owner:
            continue
        if owner.get("host") != socket.gethostname():
            raise LatexError("Cannot recover an attempt owned by another host")
        try:
            process = psutil.Process(owner["pid"])
            if process.create_time() == owner["create_time"] and process.status() != psutil.STATUS_ZOMBIE:
                raise LatexError("A live execution still owns this attempt; cancel through its executor")
        except psutil.NoSuchProcess:
            pass
    # No process owns these files now. Freeze bounded existing text for later
    # terminal reads; never adopt an unverified PDF from an interrupted attempt.
    receipt["files"] = []
    for name in sorted(_LOGS):
        path = root / name
        raw = _regular(path, 3 * MAX_LOG_BYTES) if path.exists() else b""
        _write_bytes(path, raw)
        receipt["files"].append({"path": name, "sha256": hashlib.sha256(raw).hexdigest(), "size": len(raw)})
    receipt.update(state="interrupted", reason="execution_owner_lost")
    _write(root / "compile.json", receipt)
    return receipt


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--gate":
        raise SystemExit(_gate_main())
    raise SystemExit("This module has no implicit compilation command; use the explicit project executor")
