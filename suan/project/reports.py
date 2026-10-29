"""Explicit reports: ordinary metadata records over immutable, selected snapshot bytes.

Reads never evaluate cells, load plugins, execute runs or read live input files. A
report's manifest hash identifies the complete frozen selection and provenance;
each asset has a separate byte hash. Generic table edits remain possible and are
validated on every read. Asset reads and exports require the caller's manifest hash.
"""
import base64
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import unicodedata
from uuid import NAMESPACE_URL, uuid4, uuid5
import zipfile

from suan.contracts import load_schema
from suan.graph.schema import check_value

from .file_tree import _directory, _link
from .managed import ManagedTable, clone, name, MAX_SNAPSHOT_BYTES
from .snapshots import _signature
from .store import ProjectError, RevisionConflict, _expected_revision, _id
from .workspace_bundle import _name as _portable_name, _output_path, _sensitive_name


DOCUMENT_FORMAT = "stk.report/1"
TABLE_ID = str(uuid5(NAMESPACE_URL, "urn:stk:project:reports:1"))
FIELDS = {"name": ("Name", "text"), "format": ("Format", "text"), "manifest": ("Manifest", "json")}
FIELD_IDS = {key: str(uuid5(NAMESPACE_URL, "urn:stk:project:reports:1:" + key)) for key in FIELDS}
MAX_REPORTS = 64
MAX_COLLECTION_BYTES = 4 * 1024 * 1024
MAX_MANIFEST_BYTES = 384 * 1024
MAX_ASSETS = 64
MAX_ASSET_BYTES = 4 * 1024 * 1024
MAX_TOTAL_BYTES = 32 * 1024 * 1024
MAX_SOURCES = 16
MAX_SOURCE_READ_BYTES = 32 * 1024 * 1024
EXPORT_MANIFEST = "stk-report.json"
_MIMES = {".md": "text/markdown; charset=utf-8", ".markdown": "text/markdown; charset=utf-8",
          ".html": "text/html; charset=utf-8", ".htm": "text/html; charset=utf-8",
          ".css": "text/css; charset=utf-8", ".txt": "text/plain; charset=utf-8",
          ".tex": "text/plain; charset=utf-8", ".log": "text/plain; charset=utf-8",
          ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
          ".gif": "image/gif", ".webp": "image/webp", ".pdf": "application/pdf",
          ".mp4": "video/mp4"}
_KINDS = {"context", "simulation_run", "analysis_run", "workflow_run"}


class ReportNotFound(ProjectError):
    """The report UUID is not in the ordinary Reports table."""


_TABLE = ManagedTable(table_id=TABLE_ID, table_name="Reports", fields=FIELDS, field_ids=FIELD_IDS,
                      subject="Report", not_found=ReportNotFound,
                      limits=lambda: (MAX_REPORTS, MAX_COLLECTION_BYTES, MAX_SNAPSHOT_BYTES),
                      limit_text="64 records or 4 MiB", max_cell_bytes=2 * MAX_MANIFEST_BYTES)


def _json(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def _hash(value):
    return hashlib.sha256(_json(value)).hexdigest()


def _digest(value):
    if type(value) is not str or re.fullmatch("[a-f0-9]{64}", value) is None:
        raise ProjectError("Report checksums must be lowercase SHA-256 values")
    return value


def _path(value):
    try:
        parts = _portable_name(value)
        if (len(value.encode("utf-8")) > 1024 or any(c in value for c in '<>"|?*')
                or any(127 <= ord(c) <= 159 for c in value)
                or unicodedata.normalize("NFC", parts[0]).casefold() == EXPORT_MANIFEST
                or any(part.split(".", 1)[0].casefold() in
                       {"com¹", "com²", "com³", "lpt¹", "lpt²", "lpt³"} for part in parts)):
            raise ProjectError("Report paths must be portable, bounded and outside the reserved manifest path")
    except UnicodeError:
        raise ProjectError("Report paths must be valid UTF-8") from None
    return value


def _mime(path):
    result = _MIMES.get(PurePosixPath(path).suffix.lower())
    if result is None:
        raise ProjectError("Report assets support Markdown, HTML, CSS, text, PNG, JPEG, GIF, WebP, PDF and MP4")
    return result


def _paths(values):
    """Reject collisions of files and implicit directories on portable filesystems."""
    entries = {}
    for path in values:
        parts = _path(path).split("/")
        for index in range(1, len(parts) + 1):
            original = "/".join(parts[:index])
            key = unicodedata.normalize("NFC", original).casefold()
            directory = index < len(parts)
            previous = entries.get(key)
            if previous is not None and (previous != (original, True) or not directory):
                raise ProjectError("Report paths collide as portable files or directories")
            entries[key] = (original, directory)


def _revision(db, expected=None):
    revision = db.execute("SELECT revision FROM project").fetchone()[0]
    if expected is not None and revision != expected:
        raise RevisionConflict(f"Expected revision {expected}, current revision is {revision}")
    return revision


def _snapshot(store, db, identity):
    store.snapshots._require(db)
    row = db.execute("SELECT length(CAST(manifest AS BLOB)) FROM project_snapshots WHERE id=?", (identity,)).fetchone()
    if row is not None and row[0] > 2 * 1024 * 1024:
        raise ProjectError("Report input snapshot metadata exceeds 2 MiB")
    return store.snapshots._decode(db.execute("SELECT * FROM project_snapshots WHERE id=?", (identity,)).fetchone())


def _source_selection(sources):
    if type(sources) is not list or len(sources) > MAX_SOURCES:
        raise ProjectError("Report sources require at most 16 explicit selections")
    seen = set()
    for source in sources:
        if (type(source) is not dict or set(source) != {"kind", "id"}
                or type(source["kind"]) is not str or source["kind"] not in _KINDS):
            raise ProjectError("Report source requires a supported kind and UUID")
        key = (source["kind"], _id(source["id"]))
        if key in seen:
            raise ProjectError("Report sources must be distinct")
        seen.add(key)


def _capture_sources(store, db, sources):
    """All selected provenance is captured from the caller's one SQLite snapshot."""
    from . import contexts, analysis_runs, workflow_runs
    _source_selection(sources)
    result, consumed = [], 0
    for selected in sources:
        kind, identity = selected["kind"], selected["id"]
        tables = {"context": [("project_contexts", "id", "payload")],
                  "simulation_run": [("run_plans", "id", "plan"), ("run_observations", "run_id", "payload")],
                  "analysis_run": [("analysis_run_plans", "id", "payload"), ("analysis_run_events", "run_id", "payload")],
                  "workflow_run": [("workflow_run_plans", "id", "payload"), ("workflow_run_events", "run_id", "payload")]}
        if kind == "context":
            contexts._require(db)
        elif kind == "simulation_run":
            store.runs._require(db)
        elif kind == "analysis_run":
            analysis_runs._require(db)
        else:
            workflow_runs._require(db)
        for table, column, payload in tables[kind]:
            size, count = db.execute(f"SELECT coalesce(sum(length(CAST({payload} AS BLOB))),0),count(*) "
                                     f"FROM {table} WHERE {column}=?", (identity,)).fetchone()
            consumed += size
            if consumed > MAX_SOURCE_READ_BYTES or count > 100000:
                raise ProjectError("Selected report provenance exceeds its bounded read budget")
        if kind == "context":
            context = store.contexts._get(db, identity)
            result.append({"kind": kind, "id": identity, "project_id": store._project_id,
                           "source_revision": context["source_revision"],
                           "context_sha256": _hash(context), "context": context})
            continue
        if kind == "simulation_run":
            run = store.runs._decode(db.execute("SELECT * FROM run_plans WHERE id=?", (identity,)).fetchone())
            plan, digest = run["plan"], run["sha256"]
            state = store.runs._observation(db, identity)
        elif kind == "analysis_run":
            plan, state, _ = store.analysis_runs._read(db, identity)
            digest = analysis_runs._hash(plan)
        else:
            plan, events = store.workflow_runs._read(db, identity)
            digest = workflow_runs._hash(plan)
            state = store.workflow_runs._state(plan, events)
            state = {key: state[key] for key in ("status", "complete", "counts", "stop_error")}
        if plan["project_id"] != store._project_id or plan["id"] != identity:
            raise ProjectError("Report run source belongs to another project")
        result.append({"kind": kind, "id": identity, "project_id": store._project_id,
                       "source_revision": plan["source_revision"], "plan_sha256": digest,
                       "captured_status": state})
    return result


@lru_cache(maxsize=1)
def _context_schema():
    """Resolve the shipped context contract without bridge, registry or plugin imports."""
    document = load_schema("desktop-bridge-1")

    def inline(node):
        if isinstance(node, dict):
            if "$ref" in node:
                target = document
                for part in node["$ref"].removeprefix("#/").split("/"):
                    target = target[part.replace("~1", "/").replace("~0", "~")]
                rest = {key: inline(value) for key, value in node.items() if key != "$ref"}
                return {"allOf": [inline(target), rest]} if rest else inline(target)
            return {key: inline(value) for key, value in node.items()}
        if isinstance(node, list):
            return [inline(value) for value in node]
        return node

    return inline(document["$defs"]["projectContext"])


def _provenance(value, project_id, source_revision):
    if type(value) is not list or len(value) > MAX_SOURCES:
        raise ProjectError("Report has invalid frozen sources")
    seen = set()
    for source in value:
        if type(source) is not dict:
            raise ProjectError("Report has invalid frozen provenance")
        kind, identity = source.get("kind"), _id(source.get("id"))
        if type(kind) is not str or kind not in _KINDS or (kind, identity) in seen:
            raise ProjectError("Report has unsupported or duplicate frozen sources")
        seen.add((kind, identity))
        keys = {"kind", "id", "project_id", "source_revision"}
        if source.get("project_id") != project_id:
            raise ProjectError("Report provenance belongs to another project")
        _expected_revision(source.get("source_revision"))
        if source["source_revision"] > source_revision:
            raise ProjectError("Report provenance revision is later than its capture")
        if kind == "context":
            if set(source) != keys | {"context", "context_sha256"}:
                raise ProjectError("Report has invalid context provenance")
            context = source["context"]
            if (type(context) is not dict or context.get("id") != identity
                    or context.get("project_id") != project_id
                    or context.get("source_revision") != source["source_revision"]
                    or _digest(source["context_sha256"]) != _hash(context)):
                raise ProjectError("Report context identity or checksum does not match")
            from .contexts import _ids, MAX_CONTEXT_BYTES
            expected = {"id", "project_id", "title", "source_revision", "created_at", "selection", "content",
                        "diagnostics", "omitted_values", "limits"}
            if set(context) != expected or len(_json(context)) > MAX_CONTEXT_BYTES:
                raise ProjectError("Report context descriptor is invalid or exceeds its limit")
            if check_value(context, _context_schema()):
                raise ProjectError("Report context descriptor does not match its published contract")
            selection, content = context["selection"], context["content"]
            if type(selection) is not dict or set(selection) != {"table_id", "record_ids", "field_ids"}:
                raise ProjectError("Report context selection is invalid")
            _id(selection["table_id"])
            records = _ids(selection["record_ids"], "Context records", 100)
            fields = _ids(selection["field_ids"], "Context fields", 64)
            if len(records) * len(fields) > 1000 or type(content) is not dict:
                raise ProjectError("Report context selection or content is invalid")
            _digest(content.get("sha256"))
            if type(content.get("size_bytes")) is not int or content["size_bytes"] < 0:
                raise ProjectError("Report context content size is invalid")
            if content.get("state") == "included":
                encoded = _json(content.get("value"))
                if len(encoded) != content["size_bytes"] or hashlib.sha256(encoded).hexdigest() != content["sha256"]:
                    raise ProjectError("Report context content checksum does not match")
            elif (content.get("state") != "omitted" or content.get("reason") != "context_limit"
                  or "value" in content):
                raise ProjectError("Report context omission descriptor is invalid")
        else:
            if set(source) != keys | {"plan_sha256", "captured_status"}:
                raise ProjectError("Report has invalid run provenance")
            _digest(source["plan_sha256"])
            status = source["captured_status"]
            if type(status) is not dict:
                raise ProjectError("Report run observation must be an object")
            if kind == "simulation_run":
                if (set(status) != {"observation_id", "observed_at", "status"}
                        or type(status["observation_id"]) is not int or status["observation_id"] < 0
                        or type(status["status"]) is not dict):
                    raise ProjectError("Report simulation observation is invalid")
            elif kind == "analysis_run":
                from .analysis_runs import STATES, _STATE_KEYS
                if set(status) != _STATE_KEYS or type(status["status"]) is not str or status["status"] not in STATES:
                    raise ProjectError("Report analysis observation is invalid")
            elif (set(status) != {"status", "complete", "counts", "stop_error"}
                  or type(status["status"]) is not str
                  or status["status"] not in {"prepared", "running", "cancel_requested", "stopped"}
                  or type(status["complete"]) is not bool or type(status["counts"]) is not dict
                  or any(type(count) is not int or count < 0 for count in status["counts"].values())):
                raise ProjectError("Report workflow observation is invalid")


def _manifest(store, db, value):
    value = clone(value, "Report", max_bytes=MAX_MANIFEST_BYTES)
    if type(value) is dict and value.get("format") == "stk.report/2":
        from .report_generation import validate_manifest
        return validate_manifest(store, db, value)
    keys = {"format", "project_id", "snapshot_id", "snapshot_sha256", "source_revision",
            "entry_path", "assets", "sources"}
    if type(value) is not dict or set(value) != keys or value["format"] != DOCUMENT_FORMAT:
        raise ProjectError("Report manifest has an unsupported or invalid structure")
    if value["project_id"] != store._project_id:
        raise ProjectError("Report manifest belongs to another project")
    _id(value["snapshot_id"])
    _expected_revision(value["source_revision"])
    snapshot = _snapshot(store, db, value["snapshot_id"])
    if _digest(value["snapshot_sha256"]) != snapshot["sha256"]:
        raise ProjectError("Report snapshot checksum does not match")
    if not snapshot["revision"] <= value["source_revision"] <= _revision(db):
        raise ProjectError("Report source revision is outside its snapshot and project revisions")
    assets = value["assets"]
    if type(assets) is not list or not 1 <= len(assets) <= MAX_ASSETS:
        raise ProjectError("Report requires 1 to 64 selected assets")
    originals = {item["record_id"]: item for item in snapshot["manifest"]["files"]}
    seen, total = set(), 0
    for asset in assets:
        if type(asset) is not dict or set(asset) != {"record_id", "path", "mime", "sha256", "size"}:
            raise ProjectError("Report asset has invalid metadata")
        identity = _id(asset["record_id"])
        original = originals.get(identity)
        if identity in seen or original is None:
            raise ProjectError("Report assets must be distinct members of the selected input snapshot")
        seen.add(identity)
        if type(asset["size"]) is not int or not 0 <= asset["size"] <= MAX_ASSET_BYTES:
            raise ProjectError("Report assets are limited to 4 MiB each")
        total += asset["size"]
        if total > MAX_TOTAL_BYTES:
            raise ProjectError("Report assets exceed the 32 MiB total limit")
        if (_digest(asset["sha256"]) != original["sha256"] or asset["size"] != original["size"]
                or asset["mime"] != _mime(original["name"]) or asset["mime"] != _mime(_path(asset["path"]))):
            raise ProjectError("Report asset identity, size or MIME differs from its frozen source")
    _paths([asset["path"] for asset in assets])
    if value["entry_path"] not in [asset["path"] for asset in assets]:
        raise ProjectError("Report entry must be exactly one selected asset")
    _provenance(value["sources"], store._project_id, value["source_revision"])
    if len(_json(value)) > MAX_MANIFEST_BYTES:
        raise ProjectError("Report manifest exceeds 384 KiB")
    return value


def _read_asset(store, asset):
    """Publish only bytes read from one stable, non-linked descriptor with the saved hash."""
    try:
        path = store.snapshots._object(asset["sha256"])
        with _directory(store.directory, path.parent.relative_to(store.directory).parts) as parent:
            kwargs = {"dir_fd": parent} if isinstance(parent, int) else {}
            target = path.name if kwargs else path
            before_path = os.stat(target, follow_symlinks=False, **kwargs)
            if (_link(before_path) or not stat.S_ISREG(before_path.st_mode)
                    or before_path.st_size != asset["size"] or before_path.st_size > MAX_ASSET_BYTES):
                raise ProjectError("Report asset type or size does not match its frozen manifest")
            flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
            with os.fdopen(os.open(target, flags, **kwargs), "rb") as stream:
                before = os.fstat(stream.fileno())
                if not stat.S_ISREG(before.st_mode) or _signature(before)[:4] != _signature(before_path)[:4]:
                    raise ProjectError("Report asset changed before reading")
                data = stream.read(MAX_ASSET_BYTES + 1)
                after = os.fstat(stream.fileno())
            after_path = os.stat(target, follow_symlinks=False, **kwargs)
            if (len(data) != asset["size"] or len(data) > MAX_ASSET_BYTES
                    or _signature(before) != _signature(after) or _link(after_path)
                    or _signature(after_path)[:4] != _signature(after)[:4]
                    or hashlib.sha256(data).hexdigest() != asset["sha256"]):
                raise ProjectError("Report asset changed or its checksum does not match")
    except (OSError, RuntimeError):
        raise ProjectError("Frozen report asset is unavailable or changed") from None
    if asset["mime"].startswith("text/"):
        try:
            text = data.decode("utf-8")
        except UnicodeError:
            raise ProjectError("Report text assets must be valid UTF-8") from None
        if any(ord(c) < 32 and c not in "\t\r\n" or 127 <= ord(c) <= 159 for c in text):
            raise ProjectError("Report text assets cannot contain control characters")
    return data


def _report_asset(store, manifest, item):
    if manifest["format"] == "stk.report/2" and item["path"] == manifest["entry_path"]:
        return manifest["generation"]["body"].encode("utf-8")
    return _read_asset(store, item)


def _record(store, db, identity, compatible, error):
    result = {"id": identity, "name": None, "format": None, "state": "invalid", "error": "",
              "source_sha256": None, "manifest": None}
    try:
        result["name"] = name(_TABLE.literal(db, identity, "name"), "Report")
    except ProjectError:
        pass
    try:
        value = _TABLE.literal(db, identity, "format")
        if type(value) is str and 0 < len(value.encode("utf-8")) <= 128 and "\0" not in value:
            result["format"] = value
    except ProjectError:
        pass
    try:
        if not compatible:
            raise ProjectError(error)
        if _TABLE.indirect(db, identity):
            raise ProjectError("Report managed cells must be literals; undo or repair the formula/reference")
        if result["name"] is None or result["format"] not in (DOCUMENT_FORMAT, "stk.report/2"):
            raise ProjectError("Report name or format is invalid or unsupported")
        manifest = _manifest(store, db, _TABLE.literal(db, identity, "manifest"))
        if manifest["format"] != result["format"]:
            raise ProjectError("Report format differs from its manifest")
        if len(_json({"name": result["name"], "format": result["format"], "manifest": manifest})) > MAX_MANIFEST_BYTES:
            raise ProjectError("Report metadata exceeds 384 KiB")
        result.update(state="readable", manifest=manifest, source_sha256=_hash(manifest))
    except (ProjectError, ValueError, TypeError, KeyError, RecursionError, UnicodeError):
        result["error"] = "Report metadata is invalid or unsupported; undo or explicitly repair the table edit"
    return result


class Reports:
    def __init__(self, store):
        self.store = store

    def generation_request(self, request_id):
        from .report_generation import request_details
        return request_details(self.store, request_id)

    def create_generated(self, name, request_id, body, *, report_id, expected_revision, expected_input_sha256,
                         expected_response_sha256, entry_path="report.md"):
        from .report_generation import create
        return create(self.store, name, request_id, body, report_id=report_id, expected_revision=expected_revision,
                      expected_input_sha256=expected_input_sha256,
                      expected_response_sha256=expected_response_sha256, entry_path=entry_path)

    def _get(self, db, report_id):
        _TABLE.require(db, "reports")
        if db.execute("SELECT 1 FROM records WHERE table_id=? AND id=?", (TABLE_ID, report_id)).fetchone() is None:
            raise ReportNotFound("Report not found")
        _, compatible, error = _TABLE.schema(db)
        return _record(self.store, db, report_id, compatible, error)

    def get(self, report_id):
        _id(report_id)
        with self.store._connect() as db:
            return {"revision": _revision(db), "table_id": TABLE_ID, "report": self._get(db, report_id)}

    def list(self, *, offset=0, limit=50):
        if type(offset) is not int or not 0 <= offset < 2**63 or type(limit) is not int or not 1 <= limit <= 100:
            raise ProjectError("Report pagination requires offset >= 0 and limit between 1 and 100")
        with self.store._connect() as db:
            _TABLE.require(db, "reports")
            revision = _revision(db)
            _, compatible, error = _TABLE.schema(db)
            total = db.execute("SELECT count(*) FROM records WHERE table_id=?", (TABLE_ID,)).fetchone()[0]
            reports = []
            for row in db.execute("SELECT id FROM records WHERE table_id=? ORDER BY rowid LIMIT ? OFFSET ?", (TABLE_ID, limit, offset)):
                item = _record(self.store, db, row[0], compatible, error)
                del item["manifest"]
                reports.append(item)
            return {"revision": revision, "table_id": TABLE_ID, "offset": offset, "total": total, "reports": reports}

    def review_sources(self, sources, *, expected_revision):
        """Read one bounded, consistent provenance snapshot without reading source assets.

        Lifecycle observations are independent of the editable project revision. The returned
        digest can therefore guard create against observations advancing after this review.
        """
        _expected_revision(expected_revision)
        selected = clone(sources, "Report source selection")
        with self.store._connect() as db:
            _TABLE.require(db, "reports")
            _revision(db, expected_revision)
            try:
                frozen = _capture_sources(self.store, db, selected)
                _provenance(frozen, self.store._project_id, expected_revision)
                result = {"project_id": self.store._project_id, "revision": expected_revision,
                          "sources": frozen, "sources_sha256": _hash(frozen)}
                encoded_size = len(_json(result))
            except (KeyError, TypeError, ValueError, RecursionError, UnicodeError):
                raise ProjectError("Selected report provenance is invalid") from None
            if encoded_size > MAX_MANIFEST_BYTES:
                raise ProjectError("Report source review exceeds the 384 KiB metadata limit")
            return result

    def create(self, name, snapshot_id, entry_record_id, assets, *, report_id, expected_revision, sources=None,
               expected_sources_sha256=None):
        _id(report_id); _id(snapshot_id); _id(entry_record_id)
        _expected_revision(expected_revision)
        if expected_sources_sha256 is not None:
            _digest(expected_sources_sha256)
        values = clone({"name": name, "assets": assets, "sources": [] if sources is None else sources}, "Report")
        from .managed import name as report_name
        title, selected, sources = report_name(values["name"], "Report"), values["assets"], values["sources"]
        if type(selected) is not list or not 1 <= len(selected) <= MAX_ASSETS:
            raise ProjectError("Report requires 1 to 64 selected assets")
        with self.store._connect() as db:
            _TABLE.require(db, "reports")
            _revision(db, expected_revision)
            if db.execute("SELECT 1 FROM records WHERE id=?", (report_id,)).fetchone():
                raise RevisionConflict("Report record UUID already exists")
            snapshot = _snapshot(self.store, db, snapshot_id)
            originals = {item["record_id"]: item for item in snapshot["manifest"]["files"]}
            entries = []
            for item in selected:
                if type(item) is not dict or set(item) != {"record_id", "path"}:
                    raise ProjectError("Select report assets using only record_id and a virtual path")
                original = originals.get(_id(item["record_id"]))
                if original is None:
                    raise ProjectError("Report asset is not in the selected input snapshot")
                entries.append({**item, "mime": _mime(original["name"]), "sha256": original["sha256"], "size": original["size"]})
            entry = [item["path"] for item in entries if item["record_id"] == entry_record_id]
            if len(entry) != 1:
                raise ProjectError("Report entry must be exactly one selected asset")
            try:
                frozen_sources = _capture_sources(self.store, db, sources)
                captured_digest = _hash(frozen_sources) if expected_sources_sha256 is not None else None
            except (KeyError, TypeError, ValueError, RecursionError, UnicodeError):
                raise ProjectError("Selected report provenance is invalid") from None
            # Bind the exact ordered provenance reviewed by the caller, including lifecycle
            # observations which may advance without changing the project revision. This is
            # the same captured value used in the manifest, before asset I/O or any write.
            if expected_sources_sha256 is not None and captured_digest != expected_sources_sha256:
                raise RevisionConflict("Report sources changed; explicitly review the selected sources again")
            manifest = _manifest(self.store, db, {"format": DOCUMENT_FORMAT, "project_id": self.store._project_id,
                "snapshot_id": snapshot_id, "snapshot_sha256": snapshot["sha256"], "source_revision": expected_revision,
                "entry_path": entry[0], "assets": entries, "sources": frozen_sources})
            if len(_json({"name": title, "format": DOCUMENT_FORMAT, "manifest": manifest})) > MAX_MANIFEST_BYTES:
                raise ProjectError("Report metadata exceeds 384 KiB")
        for item in manifest["assets"]:
            _read_asset(self.store, item)
        with self.store._connect(write=True) as db:
            return _TABLE.write(self.store, db, report_id,
                                {"name": title, "format": DOCUMENT_FORMAT, "manifest": manifest},
                                expected_revision, create=True, document_format=DOCUMENT_FORMAT)

    def _selected(self, report_id, revision, digest):
        _id(report_id); _expected_revision(revision); _digest(digest)
        with self.store._connect() as db:
            _revision(db, revision)
            report = self._get(db, report_id)
            if report["state"] != "readable":
                raise ProjectError("Report metadata is invalid or unsupported")
            if report["source_sha256"] != digest:
                raise RevisionConflict("Report source version changed; explicitly reopen the report")
            return report

    def asset(self, report_id, path, *, expected_revision, expected_source_sha256):
        _path(path)
        report = self._selected(report_id, expected_revision, expected_source_sha256)
        item = next((item for item in report["manifest"]["assets"] if item["path"] == path), None)
        if item is None:
            raise ReportNotFound("Asset is not in the selected report manifest")
        data = _report_asset(self.store, report["manifest"], item)
        self._selected(report_id, expected_revision, expected_source_sha256)
        return {"project_id": self.store._project_id, "report_id": report_id,
                "source_sha256": report["source_sha256"], "path": path, "mime": item["mime"],
                "content_sha256": item["sha256"], "size": len(data), "data": base64.b64encode(data).decode("ascii")}

    def export_file(self, report_id, destination, *, expected_revision, expected_source_sha256):
        report = self._selected(report_id, expected_revision, expected_source_sha256)
        destination = _output_path(destination)
        if (_sensitive_name(destination.parts) or destination.is_relative_to(self.store.directory / ".stk")
                or destination == self.store.path):
            raise ProjectError("Report destination cannot be project storage or host configuration")
        # Copy each bounded source once; only complete, verified bytes enter the ZIP.
        assets = [(item, _report_asset(self.store, report["manifest"], item)) for item in report["manifest"]["assets"]]
        if report["format"] == "stk.report/2":
            from .report_generation import exported_evidence
            assets.extend(({"path": path}, data) for path, data in exported_evidence(self.store, report["manifest"]))
        envelope = {"format": report["format"], "project_id": self.store._project_id, "report_id": report_id,
                    "name": report["name"], "source_sha256": report["source_sha256"], "manifest": report["manifest"]}
        temporary = ".stk-report-" + uuid4().hex + ".part"
        cleanup_parent, published, created_identity = None, False, None
        try:
            with _directory(Path(destination.anchor), destination.parent.parts[1:]) as parent:
                # Retain the real directory through the context manager's final identity check,
                # so a rename during publication cannot prevent precise rollback on POSIX.
                if isinstance(parent, int):
                    cleanup_parent = os.dup(parent)
                kwargs = {"dir_fd": parent} if isinstance(parent, int) else {}
                target = temporary if kwargs else destination.parent / temporary
                final = destination.name if kwargs else destination
                flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
                descriptor = os.open(target, flags, 0o600, **kwargs)
                try:
                    with os.fdopen(descriptor, "w+b") as output:
                        created_identity = _signature(os.fstat(output.fileno()))[:2]
                        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
                            archive.writestr(EXPORT_MANIFEST, _json(envelope))
                            for item, data in assets:
                                archive.writestr(item["path"], data)
                        output.flush(); os.fsync(output.fileno())
                        size = output.tell()
                        output.seek(0)
                        digest = hashlib.sha256()
                        for chunk in iter(lambda: output.read(1024 * 1024), b""):
                            digest.update(chunk)
                    # Recheck the selected version after I/O, before the only publication.
                    self._selected(report_id, expected_revision, expected_source_sha256)
                    try:
                        if kwargs:
                            os.link(target, final, src_dir_fd=parent, dst_dir_fd=parent, follow_symlinks=False)
                        else:
                            os.link(target, final)
                        published = True
                        if isinstance(parent, int):
                            os.fsync(parent)
                    except FileExistsError:
                        raise ProjectError("Report output already exists; choose a new path") from None
                finally:
                    os.unlink(target, **kwargs)
        except BaseException as error:
            if published:
                rollback = {"dir_fd": cleanup_parent} if cleanup_parent is not None else {}
                final = destination.name if rollback else destination
                try:
                    info = os.stat(final, follow_symlinks=False, **rollback)
                    if not _link(info) and _signature(info)[:2] == created_identity:
                        os.unlink(final, **rollback)
                except FileNotFoundError:
                    pass
            if isinstance(error, OSError):
                raise ProjectError("Report export could not publish a complete output") from None
            raise
        finally:
            if cleanup_parent is not None:
                os.close(cleanup_parent)
        return {"project_id": self.store._project_id, "report_id": report_id,
                "source_sha256": report["source_sha256"], "path": str(destination),
                "sha256": digest.hexdigest(), "size": size}
