"""Resumable Hub input uploads for the CLI (docs/design/hub-cli-transfers.md); private module.

The CLI parent only checks arguments and the paired profile, then runs one private worker process:

* the worker takes an exclusive OS lock on ``<hub-state-dir>/cli/namespace.lock`` and keeps it until the process
  really exits (it never unlocks; it ends with ``os._exit`` after flushing its receipt);
* under that lease it re-checks the paired device, profile and endpoint, the original key and raw request, and a
  complete content manifest, retires only journals the existing ``TransferManager`` GC removes, publishes the
  sidecar ``<id>.cli.json`` (never overwriting identity) and only then constructs the real ``TransferManager``;
* the manager's backend is wrapped by a strict guard: ``upload_begin`` and ``post_import`` must match the frozen
  workspace and ordered manifest, and the import intent is persisted before the import request is sent.

The parent supervises the worker with bounded IPC and an absolute deadline (stop, then terminate, then kill,
always reaping) and reports the worker's last complete receipt; anything read afterwards is only a subsequent
observation. ``list``/``show`` read the namespace files only (bounded, no lock, no manager, no network).
Top-level imports are standard library only: ``suan.runtime.cli`` stays lightweight.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat as stat_module
import subprocess
import sys
import tempfile
import threading
import time
import uuid

WAIT_SECONDS = 600          # default bound of one upload/resume command
STOP_GRACE = 45             # TransferManager.stop timeout in the worker; >= the hub HTTP timeout (30 s)
KILL_GRACE = 10             # parent: after the stop grace, terminate then kill, each bounded
IPC_LINE_BYTES = 1024 * 1024
IPC_MAX_RECORDS = 1000
READ_FILE_BYTES = 8 * 1024 * 1024
READ_TOTAL_BYTES = 64 * 1024 * 1024
READ_MAX_FILES = 10_000
READ_MAX_ENTRIES = 4 * READ_MAX_FILES  # directory entries examined (journals, sidecars, locks and others)
MAX_ATTEMPTS = 4096         # bound of the import attempt search when matching an action ID
JOURNAL_NAME = re.compile(r"[0-9a-f]{32}\.json")
SIDECAR_NAME = re.compile(r"[0-9a-f]{32}\.cli\.json")
TRANSFER_ID = re.compile(r"[0-9a-f]{32}")
SIDECAR_VERSION = 1
JOURNAL_STATES = {"queued", "running", "interrupted", "completed", "failed", "cancelled"}
EXPLICIT_FAILURES = {"checksum_mismatch", "conflict", "invalid_params", "not_found", "unauthorized"}
EXIT_CODES = {"completed": 0, "pending_review": 0, "interrupted": 1, "unknown": 1, "failed": 1, "rejected": 1,
              "cancelled": 1, "conflict": 1, "busy": 3, "refused": 2}


class Busy(Exception):
    """Another worker holds the namespace lease."""


class Refused(Exception):
    """A pre-check under the lease refused the command; nothing remote was changed."""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def canonical(value):
    """Compact, sorted, finite JSON (NaN/Infinity are refused, never serialized)."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def _no_duplicate_keys(pairs):
    result = {}
    for key, item in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = item
    return result


def _no_constants(name):
    raise ValueError(f"non-finite number {name}")


def _finite_float(text):
    """A JSON number with a fraction or exponent; overflow such as ``1e999`` (which ``float`` turns into an
    infinity without calling ``parse_constant``) is refused like a literal ``Infinity``."""
    import math
    value = float(text)
    if not math.isfinite(value):
        raise ValueError(f"non-finite number {text[:32]}")
    return value


def strict_json(data):
    """Parse IPC JSON strictly, at every nesting level: no duplicate keys, no NaN/Infinity literals and no
    number that overflows to an infinity."""
    return json.loads(data, object_pairs_hook=_no_duplicate_keys, parse_constant=_no_constants,
                      parse_float=_finite_float)


def finite_wait(value):
    """A finite, positive number of seconds (bool excluded); raises ValueError otherwise."""
    import math
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError("The wait must be a finite, positive number of seconds")
    return float(value)


def sha256_of(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def namespace(state_dir):
    return Path(state_dir) / "cli"


def journal_dir(state_dir):
    return namespace(state_dir) / "transfers"


def journal_path(state_dir, transfer_id):
    return journal_dir(state_dir) / f"{transfer_id}.json"


def sidecar_path(state_dir, transfer_id):
    return journal_dir(state_dir) / f"{transfer_id}.cli.json"


def keyed_transfer_id(key):
    """The transfer ID the existing TransferManager derives from an upload key."""
    return hashlib.sha256(f"upload.start\0{key}".encode("utf-8")).hexdigest()[:32]


# ----------------------------------------------------------------------------------------------------
# Bounded, link-refusing reads (also used by the worker for its own namespace files)


class ReadBudget:
    def __init__(self, total=None):
        self.total = READ_TOTAL_BYTES if total is None else total
        self.used = 0
        self.exhausted = False


def bounded_names(root):
    """At most ``READ_MAX_ENTRIES`` directory entry names (the scan stops there), sorted, and whether it stopped."""
    names = []
    try:
        iterator = os.scandir(root)
    except (FileNotFoundError, NotADirectoryError):
        return names, False
    with iterator:
        for entry in iterator:
            if len(names) >= READ_MAX_ENTRIES:
                return sorted(names), True
            names.append(entry.name)
    return sorted(names), False


def read_json_file(path, budget):
    """``(status, value)``: ``ok`` with a dict, or ``missing``/``not_regular``/``too_large``/``budget``/``unreadable``.

    Symbolic links are never followed and the opened descriptor itself must be a regular file: a path replaced by
    a FIFO or device between the ``lstat`` and the open is refused without blocking (non-blocking, no-follow
    open, then ``fstat``). At most the file cap and the bytes left in the budget are read, whatever the file's
    earlier size; a file that grew beyond what may be read is refused, and the budget records it."""
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return "missing", None
    except OSError:
        return "unreadable", None
    if not stat_module.S_ISREG(info.st_mode):
        return "not_regular", None
    if info.st_size > READ_FILE_BYTES:
        return "too_large", None
    remaining = budget.total - budget.used
    if remaining <= 0:
        budget.exhausted = True
        return "budget", None
    limit = min(READ_FILE_BYTES, remaining)
    flags = (os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
             | getattr(os, "O_NOCTTY", 0) | getattr(os, "O_BINARY", 0))
    try:
        descriptor = os.open(path, flags)
    except FileNotFoundError:
        return "missing", None
    except OSError:
        return "unreadable", None  # e.g. ELOOP: replaced by a symbolic link
    blocks, size = [], 0
    try:
        if not stat_module.S_ISREG(os.fstat(descriptor).st_mode):
            return "not_regular", None
        while size < limit:
            block = os.read(descriptor, min(1024 * 1024, limit - size))
            if not block:
                break
            blocks.append(block)
            size += len(block)
        larger = os.fstat(descriptor).st_size > size
    except OSError:
        return "unreadable", None
    finally:
        os.close(descriptor)
        budget.used += size  # every byte actually read is charged, also when a later read or fstat failed
    if larger:
        if limit < READ_FILE_BYTES:
            budget.exhausted = True
            return "budget", None
        return "too_large", None
    data = b"".join(blocks)
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return "unreadable", None
    return ("ok", value) if isinstance(value, dict) else ("unreadable", None)


def journal_shape(record, transfer_id):
    """A journal of ``transfer_id`` whose fields the views use have the expected types (else it is skipped)."""
    if not (isinstance(record, dict) and record.get("id") == transfer_id and record.get("kind") == "upload"
            and isinstance(record.get("state"), str) and record["state"] in JOURNAL_STATES):
        return False  # types are checked before any set membership (an unhashable state is just invalid)
    optional_text = (str, type(None))
    action, error = record.get("action"), record.get("error")
    if action is not None and not (isinstance(action, dict)
                                   and all(isinstance(action.get(k), optional_text) for k in ("id", "state"))):
        return False
    if error is not None and not (isinstance(error, dict) and isinstance(error.get("code"), optional_text)):
        return False
    for key in ("bytes_done", "bytes_total", "files_done", "files_total", "import_attempt"):
        number = record.get(key)
        if number is not None and (isinstance(number, bool) or not isinstance(number, int)):
            return False
    return all(isinstance(record.get(key), optional_text) for key in ("workspace_id", "node", "remote"))


MANIFEST_KEYS = {"path", "size", "sha256"}
SIDECAR_KEYS = {"version", "transfer_id", "idempotency_key", "request", "connection", "node_id", "workspace_id",
                "server_key", "device_id", "profile", "manifest", "manifest_sha256", "import_intent", "created_at"}
REQUEST_KEYS = ["connection", "node", "workspace_id", "source", "remote"]
INTENT_KEYS = {"attempt", "action_id", "request_sha256", "files_sha256", "recorded_at"}


def sidecar_problem(sidecar, transfer_id):
    """``None`` for a well-formed sidecar of ``transfer_id``, else a short reason (never its content)."""
    if not isinstance(sidecar, dict) or set(sidecar) != SIDECAR_KEYS:
        return "shape"
    if "id" in sidecar or "state" in sidecar:
        return "shape"
    if sidecar["version"] != SIDECAR_VERSION or sidecar["transfer_id"] != transfer_id:
        return "binding"
    if not isinstance(sidecar["idempotency_key"], str) or keyed_transfer_id(sidecar["idempotency_key"]) != transfer_id:
        return "binding"
    for key in ("connection", "node_id", "workspace_id", "server_key", "device_id", "profile", "created_at",
                "manifest_sha256"):
        if not isinstance(sidecar[key], str):
            return "shape"
    request = sidecar["request"]
    if (not isinstance(request, dict) or set(request) != set(REQUEST_KEYS)
            or any(not isinstance(request[key], str) for key in ("connection", "node", "workspace_id", "source"))
            or not isinstance(request["remote"], (str, type(None)))):
        return "shape"
    if (request["connection"] != sidecar["connection"] or request["node"] != sidecar["node_id"]
            or request["workspace_id"] != sidecar["workspace_id"]):
        return "binding"
    manifest = sidecar["manifest"]
    if (not isinstance(manifest, list) or not manifest
            or any(not isinstance(e, dict) or set(e) != MANIFEST_KEYS or not isinstance(e["path"], str)
                   or isinstance(e["size"], bool) or not isinstance(e["size"], int) or e["size"] < 0
                   or not isinstance(e["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", e["sha256"])
                   for e in manifest)):
        return "shape"
    if sha256_of(manifest) != sidecar["manifest_sha256"]:
        return "binding"
    intent = sidecar["import_intent"]
    if intent is not None and not (isinstance(intent, dict) and set(intent) == INTENT_KEYS and all(
            isinstance(intent[key], kind) and not isinstance(intent[key], bool) for key, kind in INTENT_TYPES.items())):
        return "shape"
    return None


# ----------------------------------------------------------------------------------------------------
# Read-only views (no manager, no lease, no lock file, no network, no writes)


def summarize(record):
    action = record.get("action") or {}
    return {"id": record["id"], "state": record["state"], "workspace_id": record.get("workspace_id"),
            "node": record.get("node"), "remote": record.get("remote"),
            "bytes_done": record.get("bytes_done"), "bytes_total": record.get("bytes_total"),
            "files_done": record.get("files_done"), "files_total": record.get("files_total"),
            "action": {"id": action.get("id"), "state": action.get("state")} if action else None,
            "error": {"code": (record.get("error") or {}).get("code")} if record.get("error") else None}


def list_transfers(state_dir, budget_bytes=None):
    root = journal_dir(state_dir)
    budget = ReadBudget(budget_bytes)
    counts = {"journals": 0, "sidecar_missing": 0, "sidecar_invalid": 0, "skipped": 0}
    transfers = []
    names, truncated = bounded_names(root)
    journals = [name for name in names if JOURNAL_NAME.fullmatch(name)]
    if len(journals) > READ_MAX_FILES:
        journals, truncated = journals[:READ_MAX_FILES], True
    for name in journals:
        transfer_id = name[:32]
        status, record = read_json_file(root / name, budget)
        if status == "budget":
            truncated = True
            break
        if status != "ok" or not journal_shape(record, transfer_id):
            counts["skipped"] += 1
            continue
        counts["journals"] += 1
        status, sidecar = read_json_file(root / f"{transfer_id}.cli.json", budget)
        if status == "budget":
            truncated = True
            break
        item = summarize(record)
        if status == "missing":
            item["sidecar"] = "missing"
            counts["sidecar_missing"] += 1
        elif status != "ok" or sidecar_problem(sidecar, transfer_id) or not bound(sidecar, record):
            item["sidecar"] = "invalid"
            counts["sidecar_invalid"] += 1
        else:
            item["sidecar"] = "valid"
        transfers.append(item)
    return {"transfers": transfers, "counts": counts, "truncated": truncated or budget.exhausted,
            "observation": "last_journaled", "observed_at": utc_now(), "observed_from": "journal"}


def bound(sidecar, record):
    """The sidecar binds this journal: same transfer, raw request and endpoint identity."""
    return (record.get("id") == sidecar["transfer_id"] and record.get("request") == sidecar["request"]
            and record.get("connection_identity") == sidecar["server_key"])


def show_transfer(state_dir, transfer_id):
    if not TRANSFER_ID.fullmatch(transfer_id or ""):
        raise ValueError("A transfer ID is 32 lowercase hexadecimal characters")
    budget = ReadBudget()
    status, record = read_json_file(journal_path(state_dir, transfer_id), budget)
    journal_ok = status == "ok" and journal_shape(record, transfer_id)
    side_status, sidecar = read_json_file(sidecar_path(state_dir, transfer_id), budget)
    if side_status == "missing":
        sidecar_state, intent = "missing", None
    elif side_status != "ok" or sidecar_problem(sidecar, transfer_id) or (journal_ok and not bound(sidecar, record)):
        sidecar_state, intent = "invalid", None
    else:
        sidecar_state, intent = "valid", sidecar["import_intent"]
    return {"transfer": summarize(record) if journal_ok else None,
            "journal": "ok" if journal_ok else ("missing" if status == "missing" else "invalid"),
            "sidecar": sidecar_state, "import_intent": intent, "observation": "last_journaled",
            "observed_at": utc_now(), "observed_from": "journal"}, (sidecar if sidecar_state == "valid" else None)


def check_import(state_dir, transfer_id, hub, node):
    """``show --check``: read the one import action the sidecar records as last dispatched (read only)."""
    from suan.desktop_bridge.backends import summary
    from suan.desktop_bridge.connections import ConnectionStore
    view, sidecar = show_transfer(state_dir, transfer_id)
    if sidecar is None or view["journal"] != "ok":
        raise Refused("sidecar_missing_or_invalid")
    intent = sidecar["import_intent"]
    if intent is None:
        view["check"] = {"action": None, "observed_at": utc_now(), "observed_from": "hub",
                         "note": "no import was dispatched by this transfer yet"}
        return view
    store = ConnectionStore(state_dir)
    try:
        binding, backend = current_binding(store, hub, node)
        if binding != {key: sidecar[key] for key in binding}:
            raise Refused("binding_changed")
        record = backend.call(backend.hub.action, intent["action_id"])
    finally:
        store.close()
    request = record.get("request") or {}
    matches = (request.get("kind") == "workspace.import" and request.get("node_id") == node
               and record.get("id") == intent["action_id"] and sha256_of(request) == intent["request_sha256"])
    view["check"] = {"action": summary(record), "matches_intent": matches, "observed_at": utc_now(),
                     "observed_from": "hub"}
    return view


# ----------------------------------------------------------------------------------------------------
# Worker


def current_binding(store, hub, node):
    """The paired device, profile and endpoint identity of ``hub:<hub>`` for ``node``, from hubs.json."""
    connection = "hub:" + hub
    described = store.describe(connection)
    backend = store.backend(connection, node)
    return {"connection": connection, "node_id": node, "server_key": backend.server_key,
            "device_id": described.get("device_id"), "profile": described.get("profile") or ""}, backend


_LEASE = []  # keeps the worker's lease object (and its open file) referenced until os._exit


class NamespaceLease:
    """An exclusive OS lock on ``<namespace>/namespace.lock`` held until this process exits.

    There is deliberately no release: the worker ends with ``os._exit`` and the OS drops the lock only then, so
    the namespace is never handed over while a transfer thread of this process could still write.
    """

    def __init__(self, root):
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.stream = open(root / "namespace.lock", "a+b")
        try:
            if os.name == "nt":
                import msvcrt
                self.stream.seek(0, os.SEEK_END)
                if self.stream.tell() == 0:
                    self.stream.write(b"0")
                    self.stream.flush()
                self.stream.seek(0)
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.stream.close()
            raise Busy() from None


def upload_items(source, remote):
    """``[(path, remote name)]`` exactly as ``TransferManager._start_upload`` enumerates them."""
    from suan.desktop_bridge.transfers import MAX_FILES
    from suan.runtime.models import relative_path
    source = Path(source)
    if not source.is_absolute():
        raise Refused("source_not_absolute")
    if source.is_symlink() or not source.exists():
        raise Refused("source_missing")
    into_root = remote in (".", "./")
    if remote is not None and not into_root:
        try:
            remote = relative_path(remote)
        except ValueError:
            raise Refused("invalid_remote") from None
    items = []
    if source.is_file():
        items.append((source, source.name if into_root else (remote or source.name)))
    elif source.is_dir():
        prefix = "" if into_root else (remote or source.name).strip("/")
        for directory, dirs, files in os.walk(source, followlinks=False):
            dirs[:] = sorted(d for d in dirs if not (Path(directory) / d).is_symlink())
            for file in sorted(files):
                path = Path(directory) / file
                if path.is_symlink() or not path.is_file():
                    continue
                relative = path.relative_to(source).as_posix()
                items.append((path, f"{prefix}/{relative}" if prefix else relative))
                if len(items) > MAX_FILES:
                    raise Refused("too_many_files")
        if not items:
            raise Refused("empty_folder")
    else:
        raise Refused("source_not_regular")
    named = []
    for path, name in items:
        try:
            named.append((path, relative_path(name)))
        except ValueError:
            raise Refused("invalid_remote") from None
    return named


def stable_entry(path, name):
    """``{path, size, sha256}`` of one file, read once; refused if it changed while being read."""
    try:
        before = os.lstat(path)
    except OSError:
        raise Refused("source_missing") from None
    if not stat_module.S_ISREG(before.st_mode):
        raise Refused("source_not_regular")
    digest, size = hashlib.sha256(), 0
    try:
        with open(path, "rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
                size += len(block)
        after = os.lstat(path)
    except OSError:
        raise Refused("source_unreadable") from None
    if ((before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino)
            or size != before.st_size):
        raise Refused("source_changed_while_hashing")
    return {"path": name, "size": size, "sha256": digest.hexdigest()}


def build_manifest(source, remote):
    return build_manifest_items(source, remote)[1]


def build_manifest_items(source, remote):
    """``(items, manifest)``: the enumerated ``(path, remote)`` pairs and their frozen entries."""
    items = upload_items(source, remote)
    return items, [stable_entry(path, name) for path, name in items]


# The largest import intent the sidecar may later hold, and room for what the manager adds to its journal later
# (action summary with review reason, error text, counters); both stay inside the reader's per-file cap.
INTENT_RESERVE = {"attempt": MAX_ATTEMPTS, "action_id": "f" * 32, "request_sha256": "f" * 64,
                  "files_sha256": "f" * 64, "recorded_at": "0000-00-00T00:00:00.000000+00:00"}
JOURNAL_RESERVE = 64 * 1024


def require_readable_identity(sidecar, items, source, remote, transfer_id):
    """Refuse (before any recovery, GC, publication or upload) a transfer whose own sidecar or journal could not
    later be read back under the per-file cap: such an upload could neither be resumed nor cancelled."""
    if len(canonical({**sidecar, "import_intent": INTENT_RESERVE})) > READ_FILE_BYTES:
        raise Refused("identity_too_large")
    largest = 10 ** 19
    journal = {"id": transfer_id, "kind": "upload", "state": "interrupted", "bytes_done": largest,
               "files_done": largest, "created_at": INTENT_RESERVE["recorded_at"], "updated_at": INTENT_RESERVE["recorded_at"],
               "connection": sidecar["connection"], "node": sidecar["node_id"], "workspace_id": sidecar["workspace_id"],
               "local": str(source), "remote": remote, "connection_identity": sidecar["server_key"],
               "idempotency_key": sidecar["idempotency_key"], "request": sidecar["request"],
               "files_total": largest, "bytes_total": largest, "import_attempt": MAX_ATTEMPTS,
               "current": max((name for _, name in items), key=len),
               "items": [{"local": str(path), "remote": entry["path"], "size": entry["size"], "mtime_ns": largest,
                          "sha256": entry["sha256"], "done": False, "upload_id": "f" * 32}
                         for (path, _), entry in zip(items, sidecar["manifest"])]}
    # The manager writes json.dump(..., ensure_ascii=False) with the default separators.
    if len(json.dumps(journal, ensure_ascii=False).encode("utf-8")) + JOURNAL_RESERVE > READ_FILE_BYTES:
        raise Refused("identity_too_large")


class SidecarHolder:
    """The worker's sidecar, updated (import intent only) atomically under the lease."""

    def __init__(self, state_dir, transfer_id, sidecar=None):
        self.state_dir, self.transfer_id, self.sidecar = state_dir, transfer_id, sidecar
        self.lock = threading.Lock()

    def _temporary(self):
        # Not matching *.json: neither the manager nor the readers ever see a partial sidecar.
        return journal_dir(self.state_dir) / f".{self.transfer_id}.cli.tmp-{os.getpid()}"

    def _write_temporary(self, sidecar):
        temporary = self._temporary()
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_BINARY", 0), 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(canonical(sidecar))
            stream.flush()
            os.fsync(stream.fileno())
        return temporary

    def publish(self, sidecar):
        """Create the sidecar with the atomic no-overwrite primitive only (a hard link fails if the name exists).

        There is no check-then-replace fallback: the lease excludes other compliant workers, not other writers, so
        a filesystem without hard links refuses publication (``sidecar_publication_unsupported``) instead. A
        present final sidecar is never replaced, removed or changed, and ``self.sidecar`` adopts the incoming
        identity only after the link succeeded. Only this publication's temporary file is removed. A sidecar
        that could not be read back under the per-file cap (with room for its later import intent) is refused
        before any write."""
        if len(canonical({**sidecar, "import_intent": INTENT_RESERVE})) > READ_FILE_BYTES:
            raise Refused("identity_too_large")
        final = sidecar_path(self.state_dir, self.transfer_id)
        temporary = self._temporary()
        try:
            self._write_temporary(sidecar)
            try:
                os.link(temporary, final)
            except FileExistsError:
                raise Refused("sidecar_exists") from None
            except OSError:
                raise Refused("sidecar_publication_unsupported") from None
        finally:
            temporary.unlink(missing_ok=True)
        self.sidecar = sidecar

    def record_intent(self, intent):
        with self.lock:
            previous = self.sidecar.get("import_intent") or {}
            if all(previous.get(key) == intent[key] for key in ("attempt", "action_id", "request_sha256", "files_sha256")):
                return  # the same action sent again (resume after review): keep the original record unchanged
            updated = {**self.sidecar, "import_intent": intent}
            temporary = self._write_temporary(updated)
            os.replace(temporary, sidecar_path(self.state_dir, self.transfer_id))
            self.sidecar = updated


class GuardedBackend:
    """The manager's backend, bound to the frozen workspace and ordered manifest (content gate B)."""

    def __init__(self, real, holder):
        self._real, self._holder = real, holder

    def __getattr__(self, name):
        return getattr(self._real, name)

    def upload_begin(self, workspace_id, path, size, digest):
        from suan.desktop_bridge.protocol import BridgeError
        sidecar = self._holder.sidecar
        if workspace_id != sidecar["workspace_id"] or {"path": path, "size": size, "sha256": digest} not in sidecar["manifest"]:
            raise BridgeError("conflict", "The upload does not match its frozen content manifest; nothing was sent")
        return self._real.upload_begin(workspace_id, path, size, digest)

    def post_import(self, workspace_id, files, identity):
        from suan.desktop_bridge.backends import action_id
        from suan.desktop_bridge.protocol import BridgeError
        sidecar = self._holder.sidecar
        expected = [{"path": e["path"], "sha256": e["sha256"], "size": e["size"]} for e in sidecar["manifest"]]
        if workspace_id != sidecar["workspace_id"] or files != expected:
            raise BridgeError("conflict", "The import does not match the frozen content manifest; it was not sent")
        attempt = next((a for a in range(MAX_ATTEMPTS)
                        if action_id("workspace.import", self._real.node_id, sidecar["transfer_id"], a) == identity), None)
        if attempt is None:
            raise BridgeError("conflict", "The import action ID does not belong to this transfer; it was not sent")
        request = {"id": identity, "node_id": self._real.node_id, "kind": "workspace.import",
                   "payload": {"workspace_id": workspace_id, "files": files}}
        self._holder.record_intent({"attempt": attempt, "action_id": identity, "request_sha256": sha256_of(request),
                                    "files_sha256": sha256_of(files), "recorded_at": utc_now()})
        return self._real.post_import(workspace_id, files, identity)


def retired_journals(state_dir):
    """IDs of terminal journals the manager's GC is about to remove (read-only scan)."""
    from suan.desktop_bridge.transfers import FINAL, KEEP_FINISHED_SECONDS
    cutoff = time.time() - KEEP_FINISHED_SECONDS
    retired = []
    root = journal_dir(state_dir)
    names, _ = bounded_names(root)  # a journal left out is still collected by the manager; its sidecar then stays
    for name in names:
        if not JOURNAL_NAME.fullmatch(name):
            continue
        status, record = read_json_file(root / name, ReadBudget(READ_FILE_BYTES))
        try:
            old = os.lstat(root / name).st_mtime < cutoff
        except OSError:
            continue
        if status == "ok" and isinstance(record.get("state"), str) and record["state"] in FINAL and old:
            retired.append(name[:32])
    return retired


def hub_says_review(store, binding, node, action_id):
    """A read of the original import action on the hub (no dispatch); unreachable means not confirmed."""
    from suan.desktop_bridge.protocol import BridgeError
    if not action_id:
        return False
    try:
        return store.backend(binding["connection"], node).action_record(action_id).get("state") == "review"
    except BridgeError:
        return False


def classify(journal, threads_alive):
    if journal is None or threads_alive:
        return "unknown"
    state, action = journal.get("state"), journal.get("action") or {}
    code = (journal.get("error") or {}).get("code")
    if state == "completed":
        return "completed"
    if state == "cancelled":
        return "cancelled"
    if state == "failed":
        if action.get("state") in ("rejected", "failed"):
            return action["state"]
        return "failed" if code in EXPLICIT_FAILURES else "unknown"  # a lost ACK is not a remote terminal
    if action.get("state") == "review":
        return "pending_review"
    if state == "interrupted":
        return "interrupted"
    return "unknown"


def run_worker(job, stop, emit):
    """One command under the lease; returns the receipt. Raises Busy or Refused before any change."""
    from suan.desktop_bridge.connections import ConnectionStore
    from suan.desktop_bridge.protocol import BridgeError
    from suan.desktop_bridge.transfers import FINAL, TransferManager
    import suan
    if str(Path(suan.__file__).resolve().parent.parent) != job["origin"]:
        raise Refused("origin_mismatch")
    started = time.monotonic()
    deadline = started + float(job["wait"])
    state_dir, op = job["state_dir"], job["op"]
    _LEASE.append(NamespaceLease(namespace(state_dir)))  # held until os._exit; never released here
    store = ConnectionStore(state_dir)
    binding, _ = current_binding(store, job["hub"], job["node"])
    if binding["profile"] != "desktop":
        raise Refused("not_desktop")
    if op == "upload":
        transfer_id = keyed_transfer_id(job["key"])
        request = {"connection": binding["connection"], "node": job["node"], "workspace_id": job["workspace_id"],
                   "source": job["source"], "remote": job["remote"]}
    else:
        transfer_id = job["transfer_id"]
        if not TRANSFER_ID.fullmatch(transfer_id or ""):
            raise Refused("invalid_transfer_id")
    budget = ReadBudget()
    status, journal = read_json_file(journal_path(state_dir, transfer_id), budget)
    if status not in ("ok", "missing") or (status == "ok" and not journal_shape(journal, transfer_id)):
        raise Refused("journal_invalid")
    side_status, sidecar = read_json_file(sidecar_path(state_dir, transfer_id), budget)
    if side_status not in ("ok", "missing"):
        raise Refused("sidecar_invalid")
    if side_status == "ok" and sidecar_problem(sidecar, transfer_id):
        raise Refused("sidecar_invalid")
    sidecar = sidecar if side_status == "ok" else None
    retired = retired_journals(state_dir)
    if transfer_id in retired:
        if op != "upload":
            raise Refused("retired")
        journal, sidecar = None, None  # removed by this command's GC; the key then starts a new transfer
    identity = {key: binding[key] for key in ("connection", "node_id", "server_key", "device_id", "profile")}
    if sidecar is not None and {key: sidecar[key] for key in identity} != identity:
        raise Refused("binding_changed")
    if journal is not None:
        if sidecar is None:
            raise Refused("sidecar_missing")
        if not bound(sidecar, journal):
            raise Refused("sidecar_invalid")
    if op == "upload":
        if sidecar is not None and (sidecar["idempotency_key"] != job["key"] or sidecar["request"] != request):
            return {"outcome": "conflict", "transfer_id": transfer_id, "reason": "the key names a different request"}
        items, manifest = build_manifest_items(job["source"], job["remote"])
        if sidecar is not None and manifest != sidecar["manifest"]:
            raise Refused("content_changed")
        fresh = {"version": SIDECAR_VERSION, "transfer_id": transfer_id, "idempotency_key": job["key"],
                 "request": request, **identity, "workspace_id": job["workspace_id"], "manifest": manifest,
                 "manifest_sha256": sha256_of(manifest), "import_intent": None, "created_at": utc_now()}
        # Before any recovery, GC, publication or byte: its own identity must stay readable later.
        require_readable_identity(sidecar or fresh, items, job["source"], job["remote"], transfer_id)
    else:
        if sidecar is None:
            raise Refused("sidecar_missing")
        if journal is None:
            raise Refused("journal_missing")
        if op == "resume" and build_manifest(sidecar["request"]["source"], sidecar["request"]["remote"]) != sidecar["manifest"]:
            raise Refused("content_changed")
    holder = SidecarHolder(state_dir, transfer_id, sidecar)
    manager = TransferManager(namespace(state_dir), emit, lambda connection, node: GuardedBackend(
        store.backend(connection, node), holder))
    for old in retired:  # only journals the manager's GC really removed
        if not journal_path(state_dir, old).exists():
            sidecar_path(state_dir, old).unlink(missing_ok=True)
    # Re-read the target after the manager's recovery and GC: only the journal's state may have changed.
    after_budget = ReadBudget()
    status, journal_after = read_json_file(journal_path(state_dir, transfer_id), after_budget)
    side_status, sidecar_after = read_json_file(sidecar_path(state_dir, transfer_id), after_budget)
    identity_keys = ("id", "request", "connection_identity")
    if journal is None:
        if status != "missing":
            raise Refused("changed_during_recovery")
    elif (status != "ok" or not journal_shape(journal_after, transfer_id)
          or {k: journal_after.get(k) for k in identity_keys} != {k: journal.get(k) for k in identity_keys}):
        raise Refused("changed_during_recovery")
    if (sidecar is None and side_status != "missing") or (sidecar is not None and sidecar_after != sidecar):
        raise Refused("changed_during_recovery")
    if op == "upload" and holder.sidecar is None:
        if journal_path(state_dir, transfer_id).exists():
            raise Refused("sidecar_missing")
        holder.publish(fresh)
    reason = None
    try:
        try:
            if op == "upload":
                manager.start_upload(binding["connection"], job["workspace_id"], job["source"], job["remote"],
                                     job["node"], idempotency_key=job["key"])
            elif op == "resume":
                manager.resume(transfer_id)
            else:
                manager.cancel(transfer_id)
        except BridgeError as exc:
            if exc.code == "conflict" and op == "upload":
                return {"outcome": "conflict", "transfer_id": transfer_id, "reason": "the key names a different request"}
            raise
        while op != "cancel":
            record = manager.load(transfer_id)
            thread = manager.threads.get(transfer_id)
            if record["state"] in FINAL:
                break
            action = record.get("action") or {}
            if action.get("state") == "review" and hub_says_review(store, binding, job["node"], action.get("id")):
                # The journal keeps an unchanged review view from an earlier run; only a current hub read
                # of the same action makes "pending_review" an observation of now.
                reason = "review"
                break
            if thread is None or not thread.is_alive():
                reason = "not_running"
                break
            if stop.is_set():
                reason = "stopped"
                break
            if time.monotonic() >= deadline:
                reason = "deadline"
                break
            time.sleep(0.2)
    finally:
        manager.stop(timeout=STOP_GRACE)
    threads_alive = any(thread.is_alive() for thread in manager.threads.values())
    status, final = read_json_file(journal_path(state_dir, transfer_id), ReadBudget())
    final = final if status == "ok" and journal_shape(final, transfer_id) else None
    return {"outcome": classify(final, threads_alive), "transfer_id": transfer_id, "reason": reason,
            "journal": summarize(final) if final else None,
            "import_intent": (holder.sidecar or {}).get("import_intent"), "threads_alive": threads_alive,
            "binding_sha256": sha256_of(identity)}


def worker_main():
    """Entry of the private worker process: one JSON job on stdin, one receipt on stdout, then os._exit."""
    out = sys.stdout.buffer

    def send(message):
        data = canonical(message)[:IPC_LINE_BYTES - 1] + b"\n"
        out.write(data)
        out.flush()

    stop = threading.Event()
    raw = sys.stdin.buffer.readline(IPC_LINE_BYTES)
    try:
        job = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        send({"type": "receipt", "outcome": "unknown", "reason": "invalid job"})
        os._exit(1)

    def watch():
        for line in sys.stdin.buffer:
            if line.strip() == b"stop":
                break
        stop.set()  # an explicit stop or the end of the parent's input

    threading.Thread(target=watch, daemon=True).start()
    send({"type": "hello", "pid": os.getpid()})
    try:
        receipt = run_worker(job, stop, lambda *args: None)
    except Busy:
        receipt = {"outcome": "busy"}
    except Refused as exc:
        receipt = {"outcome": "refused", "reason": exc.reason}
    except Exception as exc:  # noqa: BLE001 - any other failure is reported as unknown, never as a result
        receipt = {"outcome": "unknown", "reason": f"worker error: {type(exc).__name__}"}
    receipt.update(type="receipt", nonce=job.get("nonce") if isinstance(job, dict) else None,
                   observed_at=utc_now(), observed_from="worker_receipt")
    try:
        send(receipt)
    finally:
        os._exit(EXIT_CODES.get(receipt.get("outcome"), 1))


# ----------------------------------------------------------------------------------------------------
# Parent


def _settle(process, seconds):
    """Wait up to ``seconds`` for the worker to exit. Never raises: an interrupt (at any point, including the
    poll and the loop condition) only ends this wait early with ``False``."""
    try:
        end = time.monotonic() + seconds
        while True:
            try:
                if process.poll() is not None:
                    return True
                if time.monotonic() >= end:
                    return False
                process.wait(timeout=0.05)
            except subprocess.TimeoutExpired:
                continue
    except KeyboardInterrupt:
        return False


def _reap(process):
    """Terminate, then kill, the owned worker and return only after its real exit; ``True`` when it was forced.

    A step counts as done only after its signal call returned, so an interrupt delivered before ``terminate`` or
    ``kill`` actually ran retries that call instead of skipping it. Once terminated, every further round sends
    ``kill`` again and waits a bounded time; there is no untimed wait. An interrupt during a settle wait only
    ends that wait early (escalating from terminate to kill). Returning means the worker has exited, so the
    namespace lease it holds is released by the OS, never assumed released."""
    terminated, forced = False, False
    while True:
        try:
            if process.poll() is not None:
                return forced
            forced = True
            if not terminated:
                process.terminate()
                terminated = True
                if _settle(process, KILL_GRACE):
                    return forced
                continue
            process.kill()  # idempotent; resent each round until the exit is observed
            if _settle(process, KILL_GRACE):
                return forced
        except KeyboardInterrupt:
            continue
        except OSError:  # the process exited between the poll and the signal; the next poll records it
            continue


INTENT_TYPES = {"attempt": int, "action_id": str, "request_sha256": str, "files_sha256": str, "recorded_at": str}


def receipt_payload_problem(receipt):
    """A short reason when a receipt's fields do not have their expected types, before any lookup uses them."""
    if not isinstance(receipt.get("outcome"), str) or not isinstance(receipt.get("nonce"), str):
        return "receipt field types"
    for key, kinds in (("transfer_id", str), ("reason", (str, type(None))), ("binding_sha256", str),
                       ("observed_at", str), ("observed_from", str), ("threads_alive", bool)):
        if key in receipt and not isinstance(receipt[key], kinds):
            return "receipt field types"
    journal, intent = receipt.get("journal"), receipt.get("import_intent")
    if journal is not None and not (isinstance(journal, dict) and isinstance(journal.get("id"), str)
                                    and isinstance(journal.get("state"), str) and journal["state"] in JOURNAL_STATES):
        return "receipt journal shape"
    if intent is not None and not (isinstance(intent, dict) and set(intent) == set(INTENT_TYPES) and all(
            isinstance(intent[key], kind) and not isinstance(intent[key], bool) for key, kind in INTENT_TYPES.items())):
        return "receipt import intent shape"
    return None


def _accepted_receipt(records, problem, forced, exit_code, job):
    """The worker's one final receipt, only if the whole exchange was well-formed; else ``(None, reason)``."""
    if problem:
        return None, problem
    if forced:
        return None, "worker forced"
    receipts = [record for record in records if record["type"] == "receipt"]
    hellos = [record for record in records if record["type"] == "hello"]
    if len(receipts) != 1 or records[-1] is not receipts[0]:
        return None, "not exactly one final receipt"
    if len(hellos) > 1 or (hellos and records[0] is not hellos[0]):
        return None, "unexpected hello"
    receipt = receipts[0]
    payload = receipt_payload_problem(receipt)
    if payload:
        return None, payload
    outcome = receipt["outcome"]
    if outcome not in EXIT_CODES:
        return None, "unknown outcome"
    if exit_code != EXIT_CODES[outcome]:
        return None, "exit code does not agree with the receipt"
    if receipt.get("nonce") != job.get("nonce"):
        return None, "receipt of another job"
    return receipt, None


def supervise(command, job, env, wait, cwd=None):
    """Run the owned worker under one absolute deadline and return ``(receipt or None, reap facts)``.

    The job and the later stop request are written by a separate thread, so a worker that does not read cannot
    delay the deadline; reading is bounded by line size and record count. At the deadline, or on a second
    interrupt, the worker is terminated, then killed, and always reaped (a first interrupt asks it to stop within
    its grace). Only a well-formed exchange with one final receipt that agrees with the real exit code is
    returned; anything else is ``None``. Progress never extends the deadline and the host process never exits."""
    wait = finite_wait(wait)  # a NaN or infinite wait would disable every deadline comparison below
    line = canonical(job) + b"\n"
    if len(line) > IPC_LINE_BYTES:
        raise ValueError("The worker job exceeds the IPC line limit")
    kwargs = {"start_new_session": True} if os.name != "nt" else {
        "creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)}
    started = time.monotonic()
    stop_at = started + wait + 5  # the worker stops itself at --wait; this is the parent's backstop
    hard_deadline = started + wait + STOP_GRACE + KILL_GRACE
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                               env=env, cwd=cwd, **kwargs)
    records, state = [], {"problem": None}
    stop = threading.Event()

    def read():
        try:
            while True:
                raw = process.stdout.readline(IPC_LINE_BYTES + 1)
                if not raw:
                    return
                if len(records) >= IPC_MAX_RECORDS:
                    state["problem"] = "too many records"
                    return
                if len(raw) > IPC_LINE_BYTES or not raw.endswith(b"\n"):
                    state["problem"] = "unframed or oversized record"
                    return
                try:
                    message = strict_json(raw.decode("utf-8"))
                except (UnicodeDecodeError, ValueError, RecursionError):
                    state["problem"] = "malformed record"
                    return
                if not isinstance(message, dict) or message.get("type") not in ("hello", "receipt"):
                    state["problem"] = "unexpected record"
                    return
                records.append(message)
        except (OSError, ValueError):
            state["problem"] = "read failed"

    def write():
        try:
            process.stdin.write(line)
            process.stdin.flush()
            stop.wait()
            process.stdin.write(b"stop\n")
            process.stdin.flush()
        except (OSError, ValueError):
            pass
        finally:
            try:
                process.stdin.close()
            except (OSError, ValueError):
                pass

    reader = threading.Thread(target=read, daemon=True)
    writer = threading.Thread(target=write, daemon=True)
    reader.start()
    writer.start()
    counters = {"interrupts": 0, "forced": False}
    try:
        while True:
            try:
                if process.poll() is not None:
                    break
                now = time.monotonic()
                if now >= stop_at:
                    stop.set()
                if now >= hard_deadline:
                    break
                try:
                    process.wait(timeout=max(0.01, min(0.2, hard_deadline - now)))
                except subprocess.TimeoutExpired:
                    pass
            except KeyboardInterrupt:
                counters["interrupts"] += 1
                stop.set()
                if counters["interrupts"] > 1:
                    break
                hard_deadline = min(hard_deadline, time.monotonic() + STOP_GRACE + KILL_GRACE)
    except KeyboardInterrupt:  # an interrupt inside the handler above: go straight to the cleanup
        counters["interrupts"] += 1
    finally:
        # Interrupt-resilient cleanup: the owned worker is always reaped before this function returns or raises.
        while True:
            try:
                stop.set()
                counters["forced"] = _reap(process)
                break
            except KeyboardInterrupt:
                counters["interrupts"] += 1
        for thread, seconds in ((reader, 5), (writer, 1)):
            try:
                thread.join(timeout=seconds)
            except KeyboardInterrupt:
                counters["interrupts"] += 1
    interrupts, forced = counters["interrupts"], counters["forced"]
    receipt, problem = _accepted_receipt(records, state["problem"], forced, process.returncode, job)
    return receipt, {"exit_code": process.returncode, "forced": forced, "stop_sent": stop.is_set(),
                     "interrupts": interrupts, "protocol_error": problem if receipt is None else None,
                     "elapsed_seconds": round(time.monotonic() - started, 3)}


def worker_command():
    # -P (Python 3.11+): no working directory on sys.path; the origin comes from PYTHONPATH and is verified.
    safe_path = ["-P"] if sys.version_info >= (3, 11) else []
    return [sys.executable, *safe_path, "-m", "suan.runtime.hub_transfers", "--worker"]


def worker_environment():
    """The parent's own environment, with this process's ``suan`` origin first (verified by the worker)."""
    import suan
    origin = str(Path(suan.__file__).resolve().parent.parent)
    env = dict(os.environ)
    env["PYTHONPATH"] = origin + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    return env, origin


def run_command(op, *, state_dir, hub, node, wait=WAIT_SECONDS, **fields):
    """Parent side of upload/resume/cancel: one supervised worker; returns ``(result, exit code)``."""
    env, origin = worker_environment()
    wait = finite_wait(wait)  # refused before any worker or file: a non-finite wait has no deadline
    job = {"op": op, "state_dir": str(Path(state_dir).absolute()), "hub": hub, "node": node, "wait": wait,
           "origin": origin, "nonce": uuid.uuid4().hex, **fields}
    expected = fields.get("transfer_id") or (keyed_transfer_id(fields["key"]) if fields.get("key") else None)
    receipt, reaped = supervise(worker_command(), job, env, wait, cwd=tempfile.gettempdir())
    if receipt is not None:
        names_other = (("transfer_id" in receipt and receipt["transfer_id"] != expected)
                       or ("transfer_id" not in receipt and receipt["outcome"] not in ("busy", "refused", "unknown")))
        journal = receipt.get("journal")
        if names_other or (journal is not None and journal["id"] != expected):
            # Bound to the original transfer: a top-level or inner journal naming another one is not this receipt.
            receipt, reaped = None, {**reaped, "protocol_error": "receipt names another transfer"}
    if receipt is None:
        result = {"outcome": "unknown", "reason": "no complete worker receipt", "transfer_id": expected,
                  "observed_at": utc_now(), "observed_from": "parent"}
    else:
        result = dict(receipt)
        for key in ("type", "nonce"):
            result.pop(key, None)
    result["worker"] = reaped
    transfer_id = result.get("transfer_id")
    if transfer_id and TRANSFER_ID.fullmatch(transfer_id) and (receipt is None or "journal" in result):
        later, _ = show_transfer(job["state_dir"], transfer_id)
        # Without a receipt this read is the only place the original transfer and import intent can be shown;
        # it is still an observation after the reap, never the command's receipt.
        if receipt is None or later["transfer"] != result.get("journal") or later["import_intent"] != result.get(
                "import_intent"):
            result["subsequent_observation"] = later
    return result, EXIT_CODES.get(result.get("outcome"), 1)


if __name__ == "__main__" and sys.argv[1:] == ["--worker"]:
    worker_main()
