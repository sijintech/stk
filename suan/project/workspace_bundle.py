"""Portable, explicit workspace packages. Import only verifies and writes local data.

``stk.workspace/1`` is a ZIP container with a checksummed file inventory. The project
is an unchanged SQLite online backup, not an upgrade or a replay of its journal.
Only the opened project and explicitly supplied external *files* are collected;
host preferences, Runtime credentials and model/network configuration are excluded.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import ctypes
import errno
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import sqlite3
import stat
import struct
import sys
import tempfile
import unicodedata
from uuid import UUID
import zipfile

from .store import DATABASE_NAME, ProjectError, ProjectStore, RevisionConflict, _expected_revision

FORMAT = "stk.workspace/1"
DEFAULT_MAX_BYTES = 8 * 1024 ** 3
MAX_BYTES = 1024 ** 4
MAX_FILES = 20000
MAX_STATE_BYTES = 8 * 1024 ** 2
MAX_MANIFEST_BYTES = 16 * 1024 ** 2
CHUNK = 1024 * 1024
_RESOURCE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,95}\Z")
_SHA = re.compile(r"[a-f0-9]{64}\Z")
_INTERNAL_ALLOWED = {"objects", "analysis-runs"}
_EXCLUDE_DIRECTORIES = {".git", ".ssh", ".aws", ".azure", ".config", ".cache", ".venv", "venv",
                        "__pycache__", "node_modules", "backups", ".idea", ".vscode"}
_EXCLUDE_FILES = {".env", ".netrc", ".npmrc", ".pypirc", ".git-credentials", "id_rsa", "id_dsa",
                  "id_ecdsa", "id_ed25519", "known_hosts", "authorized_keys", "credentials",
                  "credentials.json", "secrets.json", "runtime.json", "runtime.sqlite3",
                  "model-config.json", "network-policy.json"}
_SECRET_SUFFIXES = {".key", ".pem", ".p12", ".pfx", ".jks", ".keystore"}
_DENIED_STATE_KEYS = {"apikey", "password", "passphrase", "secret", "secrets", "credential", "credentials",
                      "accesstoken", "refreshtoken", "authorization", "sshprivatekey", "privatekey",
                      "modelendpoint", "modelconfig", "networkpolicy", "runtimeconfig", "environment", "env"}
_RESERVED_WINDOWS = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)),
                     *(f"lpt{i}" for i in range(1, 10))}


def _json(value):
    try:
        return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    except (TypeError, ValueError, RecursionError):
        raise ProjectError("Workspace data must be finite JSON") from None


def _unique_object(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ProjectError("Workspace JSON contains duplicate object keys")
        result[key] = value
    return result


def _decode(data):
    try:
        return json.loads(data, object_pairs_hook=_unique_object,
                          parse_constant=lambda value: (_ for _ in ()).throw(ValueError()))
    except (ValueError, UnicodeError, RecursionError):
        raise ProjectError("Workspace JSON is invalid") from None


def _limit(max_bytes):
    if type(max_bytes) is not int or not 1 <= max_bytes <= MAX_BYTES:
        raise ProjectError("Workspace max_bytes must be an integer between 1 and 1 TiB")
    return max_bytes


def _name(value):
    if type(value) is not str or not value or len(value) > 4096 or "\\" in value:
        raise ProjectError("Workspace paths must be bounded relative POSIX paths")
    parts = value.split("/")
    if len(parts) > 64 or any(not part or part in {".", ".."} or ":" in part or part[-1:] in {".", " "}
                              or any(ord(c) < 32 or ord(c) == 127 for c in part)
                              or part.split(".", 1)[0].casefold() in _RESERVED_WINDOWS for part in parts):
        raise ProjectError("Workspace paths must be portable and cannot escape the package")
    return parts


def _signature(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def _link(info):
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) &
                                            getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def _standard_macos_alias(path):
    return (sys.platform == "darwin" and path in {Path("/var"), Path("/tmp"), Path("/etc")}
            and path.is_symlink() and path.resolve() == Path("/private") / path.name)


def _safe_ancestors(path):
    # Checking every existing parent also prevents following a directory junction on Windows.
    for candidate in (path, *path.parents):
        try:
            if _link(candidate.lstat()):
                if _standard_macos_alias(candidate):
                    continue  # macOS's root-owned standard aliases, never arbitrary project links.
                raise ProjectError("Workspace paths cannot contain symbolic links or reparse points")
        except FileNotFoundError:
            continue


def _physical_path(path):
    """Normalize only an already-verified fixed system prefix, never a user link."""
    _safe_ancestors(path)
    for prefix in reversed((path, *path.parents)):
        if _standard_macos_alias(prefix):
            physical = prefix.resolve() / path.relative_to(prefix)
            _safe_ancestors(physical)
            return physical
    return path


@contextmanager
def _reader(path):
    if _sensitive_name(path.parts):
        raise ProjectError("Workspace paths cannot select host configuration or credential files")
    path = _physical_path(path)
    if _sensitive_name(path.parts):
        raise ProjectError("Workspace paths cannot select host configuration or credential files")
    descriptors = []
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        if os.open in os.supports_dir_fd:
            descriptor = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            descriptors.append(descriptor)
            for part in path.parts[1:-1]:
                descriptor = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
                descriptors.append(descriptor)
            fd = os.open(path.name, flags, dir_fd=descriptor)
        else:
            fd = os.open(path, flags)
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise ProjectError("Workspace assets must be regular files")
        yield stream, before
        after = os.fstat(stream.fileno())
        # Windows fstat/path stat can disagree on ctime semantics; compare it fd-to-fd only.
        if _signature(before) != _signature(after) or _signature(path.stat())[:4] != _signature(after)[:4]:
            raise ProjectError("Workspace source changed while being read; refresh and export again")
        _safe_ancestors(path)


def _digest(path, max_bytes):
    with _reader(path) as (stream, before):
        if before.st_size > max_bytes:
            raise ProjectError("Workspace byte budget exceeded")
        checksum, count = hashlib.sha256(), 0
        for data in iter(lambda: stream.read(CHUNK), b""):
            count += len(data)
            if count > max_bytes:
                raise ProjectError("Workspace byte budget exceeded")
            checksum.update(data)
    return checksum.hexdigest(), count


def _sensitive_name(parts):
    for part in parts:
        name = part.casefold()
        if name in _EXCLUDE_DIRECTORIES or name in _EXCLUDE_FILES or name.startswith(".env.") \
                or Path(name).suffix in _SECRET_SUFFIXES or name.startswith("id_rsa.") \
                or name.startswith("id_ed25519."):
            return True
    return False


def _state(value):
    count = 0
    def visit(item, depth):
        nonlocal count
        count += 1
        if count > 150000 or depth > 64:
            raise ProjectError("Workspace state exceeds its nesting or value budget")
        if type(item) is dict:
            for key, child in item.items():
                if type(key) is not str or len(key) > 4096:
                    raise ProjectError("Workspace state object keys must be bounded strings")
                normalized = re.sub(r"[^a-z0-9]", "", key.casefold())
                if normalized in _DENIED_STATE_KEYS or normalized.endswith("apikey") \
                        or normalized.startswith("stktokenplan"):
                    raise ProjectError("Workspace state cannot include credentials or host model/Runtime/network configuration")
                visit(child, depth + 1)
        elif type(item) is list:
            for child in item:
                visit(child, depth + 1)
        elif item is None or type(item) in (bool, int):
            return
        elif type(item) is float and math.isfinite(item):
            return
        elif type(item) is str and "\0" not in item:
            return
        else:
            raise ProjectError("Workspace state must contain finite JSON without NUL")
    if type(value) is not dict:
        raise ProjectError("Workspace state must be a JSON object")
    visit(value, 0)
    encoded = _json(value)
    if len(encoded) > MAX_STATE_BYTES:
        raise ProjectError("Workspace state exceeds 8 MiB")
    return _decode(encoded)


def _absolute(value):
    return PurePosixPath(value).is_absolute() or PureWindowsPath(value).is_absolute()


def _transform(value, mapper):
    if type(value) is dict:
        return {key: _transform(child, mapper) for key, child in value.items()}
    if type(value) is list:
        return [_transform(child, mapper) for child in value]
    return mapper(value) if type(value) is str else value


def _diagnostic(code, **values):
    return {"code": code, **values}


def _project_files(directory, diagnostics, directories=None, *, project=True):
    result, folded = [], set()
    def walk(root, relative=()):
        with os.scandir(root) as listing:
            entries = sorted(listing, key=lambda entry: entry.name)
        for entry in entries:
            parts = (*relative, entry.name)
            name = "/".join(parts)
            # The live database is handled by SQLite backup, never by byte-copying WAL files.
            if len(parts) == 1 and entry.name.startswith(DATABASE_NAME):
                continue
            if project and parts == ("backups",):
                diagnostics.append(_diagnostic("excluded_internal_file", path=name))
                continue
            if _sensitive_name(parts):
                diagnostics.append(_diagnostic("excluded_private_file", path=name))
                continue
            if parts[0] == ".stk":
                if len(parts) == 1:
                    pass
                elif parts[1] not in _INTERNAL_ALLOWED:
                    if len(parts) == 2:
                        diagnostics.append(_diagnostic("excluded_internal_file", path=name))
                    continue
            elif any(part.startswith(".") for part in parts):
                diagnostics.append(_diagnostic("excluded_hidden_file", path=name))
                continue
            try:
                info = entry.stat(follow_symlinks=False)
            except FileNotFoundError:
                raise ProjectError("Workspace project tree changed during export") from None
            if _link(info):
                diagnostics.append(_diagnostic("excluded_link", path=name))
                continue
            _name(name)
            folded_name = unicodedata.normalize("NFC", name).casefold()
            if folded_name in folded:
                raise ProjectError("Project contains names that collide on another platform")
            folded.add(folded_name)
            if len(folded) > MAX_FILES:
                raise ProjectError("Workspace file count budget exceeded")
            if stat.S_ISDIR(info.st_mode):
                if directories is not None:
                    directories.append("project/" + name)
                walk(Path(entry.path), parts)
            elif stat.S_ISREG(info.st_mode):
                result.append(("project/" + name, Path(entry.path), _signature(info)))
            else:
                diagnostics.append(_diagnostic("excluded_nonregular_file", path=name))
    walk(directory)
    return result


def _origins(item, primary="source"):
    from .workspace_paths import _syntax
    if type(item) is not dict or primary not in item:
        raise ProjectError("Workspace source mapping is invalid")
    aliases = item.get("aliases", [])
    if type(aliases) is not list or len(aliases) > 128:
        raise ProjectError("Workspace source aliases must be an array of at most 128 absolute paths")
    values, seen = [], set()
    for value in [item[primary], *aliases]:
        identity = _syntax(value)
        if _sensitive_name(identity[1].parts):
            raise ProjectError("Workspace source aliases cannot refer to host configuration or credential files")
        if identity not in seen:
            values.append(value); seen.add(identity)
    return values


def _relative_origin(value, root):
    from .workspace_paths import _syntax
    try:
        flavor, path = _syntax(value)
        root_flavor, source = _syntax(root)
        if flavor != root_flavor:
            return None
        return path.relative_to(source).parts
    except (ProjectError, ValueError):
        return None


def _check_aliases(resources, project=None):
    from .workspace_paths import _syntax
    origins = {}
    groups = [(item, "source", item["path"]) for item in resources]
    if project is not None:
        groups.append((project, "source_root", "project"))
    for item, primary, target in groups:
        for value in _origins(item, primary):
            identity = _syntax(value)
            if identity in origins and origins[identity] != target:
                raise ProjectError("Workspace source aliases point to different package targets")
            origins[identity] = target


def _inherit_aliases(store, specs):
    if store is None:
        return []
    descriptor = store.directory.parent / "workspace.json"
    if not descriptor.exists():
        return []
    previous = open_workspace(descriptor)
    if previous["project_directory"] is None or Path(previous["project_directory"]) != store.directory:
        return []
    # Re-open validates the descriptor/UUID without probing any original-machine source.
    with _reader(descriptor) as (stream, before):
        if before.st_size > MAX_MANIFEST_BYTES:
            raise ProjectError("Workspace descriptor exceeds 16 MiB")
        saved = _decode(stream.read(MAX_MANIFEST_BYTES + 1))
    from .workspace_paths import _syntax
    for spec in specs:
        aliases = list(spec.get("aliases", []))
        for old in saved["resources"]:
            actual = str(store.directory.parent / old["path"])
            relative = _relative_origin(str(_physical_path(Path(spec["source"]))), actual)
            if relative is None or relative and old["kind"] != "directory":
                continue
            for origin in _origins(old):
                pure = _syntax(origin)[1]
                aliases.append(str(pure.joinpath(*relative)))
        normalized = {identity: text for text in [spec["source"], *aliases]
                      for identity in [_syntax(text)]}
        normalized.pop(_syntax(spec["source"]), None)
        if len(normalized) > 128:
            raise ProjectError("Workspace source alias history exceeds 128 entries; explicit consolidation is required")
        if normalized:
            spec["aliases"] = list(normalized.values())
    return _origins(saved["project"], "source_root") if saved["project"] is not None else []


def _resource_specs(resources, diagnostics):
    if resources is None:
        return []
    if type(resources) is not list or len(resources) > 1024:
        raise ProjectError("Workspace resources must be at most 1024 explicit file descriptors")
    result, ids, paths, physical_resources = [], set(), set(), {}
    for resource in resources:
        if type(resource) is not dict or not {"id", "path"} <= resource.keys() or resource.keys() - {"id", "path", "aliases"} \
                or type(resource["id"]) is not str or not _RESOURCE_ID.fullmatch(resource["id"]) \
                or type(resource["path"]) is not str or not _absolute(resource["path"]) \
                or "\0" in resource["path"] or len(resource["path"]) > 32768:
            raise ProjectError("Workspace resources require a portable id and an explicit absolute file path")
        identity, source = resource["id"], Path(resource["path"])
        if identity.casefold() in ids or str(source) in paths:
            raise ProjectError("Workspace resource ids and paths must be unique")
        ids.add(identity.casefold()); paths.add(str(source))
        if _sensitive_name(source.parts):
            diagnostics.append(_diagnostic("excluded_private_resource", resource_id=identity))
            continue
        try:
            physical = _physical_path(source)
            if _sensitive_name(physical.parts):
                diagnostics.append(_diagnostic("excluded_private_resource", resource_id=identity))
                continue
            info = physical.lstat()
        except FileNotFoundError:
            diagnostics.append(_diagnostic("missing_resource", resource_id=identity))
            continue
        if stat.S_ISREG(info.st_mode):
            kind, files, directories = "file", [("", physical, _signature(info))], []
        elif stat.S_ISDIR(info.st_mode):
            kind = "directory"
            resource_diagnostics, directory_names = [], []
            files = [(name.removeprefix("project/"), item, signature)
                     for name, item, signature in _project_files(physical, resource_diagnostics, directory_names, project=False)]
            directories = ["", *[name.removeprefix("project/") for name in directory_names]]
            diagnostics.extend({**item, "resource_id": identity} for item in resource_diagnostics)
        else:
            diagnostics.append(_diagnostic("nonregular_resource", resource_id=identity))
            continue
        _name(source.name)
        item = {"id": identity, "source": str(source), "path": f"resources/{identity}/{source.name}",
                "kind": kind, "signature": _signature(info), "files": files, "directories": directories}
        if "aliases" in resource:
            item["aliases"] = resource["aliases"]
            _origins(item)
        if physical != source:
            item["aliases"] = list(dict.fromkeys([*item.get("aliases", []), str(physical)]))
            _origins(item)
        if physical in physical_resources:
            previous = physical_resources[physical]
            previous["aliases"] = list(dict.fromkeys([*previous.get("aliases", []), *_origins(item)]))
            previous["aliases"] = [value for value in previous["aliases"] if value != previous["source"]]
            _origins(previous)
            continue  # e.g. an explicit /var selection plus the same canonical FileIndex asset
        physical_resources[physical] = item
        result.append(item)
    return result


def _sync_directory(path):
    if os.name != "nt":
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def _publish_file(source, destination):
    # Hard link is no-replace on all three supported desktop platforms.
    try:
        os.link(source, destination)
    except FileExistsError:
        raise ProjectError("Workspace output already exists; choose a new path") from None
    _sync_directory(destination.parent)


def _publish_directory(source, destination):
    # Plain POSIX rename can replace an empty directory. Use the OS no-replace primitive.
    if os.name == "nt":
        os.rename(source, destination)
    elif sys.platform.startswith("linux"):
        libc = ctypes.CDLL(None, use_errno=True)
        rename = getattr(libc, "renameat2", None)
        if rename is None:
            raise ProjectError("This platform lacks atomic no-replace directory publication")
        rename.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint)
        rename.restype = ctypes.c_int
        if rename(-100, os.fsencode(source), -100, os.fsencode(destination), 1) != 0:
            code = ctypes.get_errno()
            if code in (errno.EEXIST, errno.ENOTEMPTY):
                raise ProjectError("Workspace destination already exists; choose a new directory")
            raise OSError(code, "Cannot publish workspace directory")
    elif sys.platform == "darwin":
        libc = ctypes.CDLL(None, use_errno=True)
        rename = libc.renamex_np
        rename.argtypes = (ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint)
        rename.restype = ctypes.c_int
        if rename(os.fsencode(source), os.fsencode(destination), 0x00000004) != 0:  # RENAME_EXCL
            code = ctypes.get_errno()
            if code in (errno.EEXIST, errno.ENOTEMPTY):
                raise ProjectError("Workspace destination already exists; choose a new directory")
            raise OSError(code, "Cannot publish workspace directory")
    else:
        raise ProjectError("This platform lacks atomic no-replace directory publication")
    _sync_directory(destination.parent)


def _output_path(path):
    if not isinstance(path, (str, os.PathLike)):
        raise ProjectError("Workspace output path must be a filesystem path")
    result = Path(os.path.abspath(Path(path).expanduser()))
    result = _physical_path(result)
    if result.exists():
        raise ProjectError("Workspace output already exists; choose a new path")
    if not result.parent.is_dir():
        raise ProjectError("Workspace output parent directory must already exist")
    return result


def _write_member(archive, name, source, remaining):
    with _reader(source) as (reader, before):
        if before.st_size > remaining:
            raise ProjectError("Workspace byte budget exceeded")
        checksum, size = hashlib.sha256(), 0
        info = zipfile.ZipInfo(name)
        info.external_attr = (stat.S_IFREG | 0o600) << 16
        info.compress_type = zipfile.ZIP_DEFLATED
        with archive.open(info, "w", force_zip64=before.st_size >= zipfile.ZIP64_LIMIT) as writer:
            for data in iter(lambda: reader.read(CHUNK), b""):
                size += len(data)
                if size > remaining:
                    raise ProjectError("Workspace byte budget exceeded")
                writer.write(data); checksum.update(data)
    return {"path": name, "size": size, "sha256": checksum.hexdigest()}


def export_workspace(directory, path, *, state, expected_revision=None, resources=None,
                     max_bytes=DEFAULT_MAX_BYTES):
    """Export one project and captured UI state, with explicit missing-resource diagnostics.

    Resources are ``[{"id": "viewer-1", "path": "/absolute/data.vtk"}]``. State
    strings exactly equal to a resource path or under the project root are mapped
    to portable ``stk-resource://ID`` / ``stk-project://relative`` URIs. Unknown
    absolute strings are not opened; they produce a diagnostic and remain visible.
    No destination is replaced. A stale revision, changed source or budget failure
    publishes nothing and does not change the project.
    """
    max_bytes, state = _limit(max_bytes), _state(state)
    if expected_revision is not None:
        _expected_revision(expected_revision)
    destination = _output_path(path)
    root = Path(directory).expanduser().absolute() if directory else None
    if root is not None:
        if _sensitive_name(root.parts):
            raise ProjectError("Workspace project cannot be inside host configuration or credential directories")
        _safe_ancestors(root / DATABASE_NAME)
    store = ProjectStore(root) if root is not None else None
    if store is not None and destination.is_relative_to(store.directory):
        raise ProjectError("Export the workspace outside its project directory")
    diagnostics = []
    specs = _resource_specs(resources, diagnostics)
    project_aliases = _inherit_aliases(store, specs)
    if store is not None and root != store.directory and ".." not in root.parts:
        # Ancestors were checked before ProjectStore resolved the directory. The only
        # permitted linked prefix is a fixed system alias; preserve its caller spelling
        # so state using /var/... still relocates to the canonical /private/var project.
        project_aliases = list(dict.fromkeys([*project_aliases, str(root)]))
    _check_aliases(specs)
    project_directories = []
    selected = _project_files(store.directory, diagnostics, project_directories) if store is not None else []
    directories = [*project_directories, *[item["path"] + ("/" + relative if relative else "")
                   for item in specs for relative in item["directories"]]]
    if len(directories) + len(selected) > MAX_FILES:
        raise ProjectError("Workspace file and directory count budget exceeded")
    for resource in specs:
        source = _physical_path(Path(resource["source"]))
        if destination == source or resource["kind"] == "directory" and destination.is_relative_to(source):
            raise ProjectError("Export the workspace outside its resource directories")
    available = {name.removeprefix("project/") for name, _, _ in selected}
    source_resources = {origin: item for item in specs for origin in _origins(item)}
    unknown = set()
    def portable(value):
        if value.startswith(("stk-project://", "stk-resource://")):
            raise ProjectError("Workspace export state must contain local paths, not reserved package URIs")
        if value in source_resources:
            return "stk-resource://" + source_resources[value]["id"]
        from .workspace_paths import _syntax
        for origin, item in sorted(source_resources.items(), key=lambda entry: len(_syntax(entry[0])[1].parts), reverse=True):
            relative = _relative_origin(value, origin)
            if relative is not None and (item["kind"] == "directory" or not relative):
                return "stk-resource://" + item["id"] + ("/" + "/".join(relative) if relative else "")
        if not _absolute(value):
            return value
        from .workspace_paths import _syntax
        roots = [str(store.directory), *project_aliases] if store is not None else []
        for origin in sorted(roots, key=lambda text: len(_syntax(text)[1].parts), reverse=True):
            parts = _relative_origin(value, origin)
            if parts is None:
                continue
            relative = "/".join(parts)
            if not relative:
                return "stk-project://"
            if relative not in available and "project/" + relative not in project_directories:
                diagnostics.append(_diagnostic("missing_project_resource", path=relative))
            return "stk-project://" + relative
        if value not in unknown:
            unknown.add(value)
            diagnostics.append(_diagnostic("unmapped_absolute_path", path=value))
        return value
    portable_state = _transform(state, portable)
    encoded_state = _json(portable_state)
    with tempfile.TemporaryDirectory(prefix=".stk-workspace-", dir=destination.parent) as work:
        staging = Path(work)
        database = staging / DATABASE_NAME
        project_meta = None
        database_files = []
        if store is not None:
            with store._connect() as db:
                project = dict(db.execute("SELECT * FROM project").fetchone())
                if expected_revision is not None and project["revision"] != expected_revision:
                    raise RevisionConflict(f"Expected revision {expected_revision}, current revision is {project['revision']}")
                version = db.execute("PRAGMA user_version").fetchone()[0]
                copied = sqlite3.connect(database)
                try:
                    db.backup(copied)
                finally:
                    copied.close()
            copied_store = ProjectStore(staging)
            if copied_store.info() != {**project, "format_version": version}:
                raise ProjectError("Workspace project backup identity changed")
            project_meta = {**project, "format_version": version, "source_root": str(store.directory)}
            inherited = [origin for origin in project_aliases if origin != str(store.directory)]
            if inherited:
                project_meta["aliases"] = inherited
            _check_aliases(specs, project_meta)
            database_files = [("project/" + DATABASE_NAME, database, None)]
            # Inspect indexed metadata only. Unselected external paths are never read.
            for record in copied_store.files.list()["records"] if version >= 3 else []:
                value = record.get("path")
                included = type(value) is str and any(value == origin or item["kind"] == "directory"
                    and _relative_origin(value, origin) is not None for item in specs for origin in _origins(item))
                if record.get("location", "").startswith("external:") and not included:
                    diagnostics.append(_diagnostic("external_not_included", record_id=record["id"]))
        archive_path = staging / "bundle.zip"
        inventory, total = [], len(encoded_state)
        if total > max_bytes:
            raise ProjectError("Workspace byte budget exceeded")
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            archive.writestr("state.json", encoded_state)
            inventory.append({"path": "state.json", "size": len(encoded_state),
                              "sha256": hashlib.sha256(encoded_state).hexdigest()})
            for name, source, _ in [*database_files, *selected,
                                    *[(item["path"] + ("/" + relative if relative else ""), source, signature)
                                      for item in specs for relative, source, signature in item["files"]]]:
                entry = _write_member(archive, name, source, max_bytes - total)
                inventory.append(entry); total += entry["size"]
            if len(inventory) + len(directories) > MAX_FILES:
                raise ProjectError("Workspace file and directory count budget exceeded")
            manifest = {"format": FORMAT, "created_at": datetime.now(timezone.utc).isoformat(),
                        "project": project_meta,
                        "state": "state.json", "files": inventory, "directories": directories,
                        "resources": [{key: item[key] for key in ("id", "source", "path", "kind", "aliases") if key in item} for item in specs],
                        "diagnostics": diagnostics,
                        "complete": not any(item["code"] not in {"excluded_internal_file", "excluded_hidden_file"} for item in diagnostics)}
            encoded = _json(manifest)
            if len(encoded) > MAX_MANIFEST_BYTES:
                raise ProjectError("Workspace manifest exceeds 16 MiB")
            archive.writestr("manifest.json", encoded)
        os.chmod(archive_path, 0o600)
        # Recheck all source identities after the complete archive has been written.
        for _, source, signature in selected:
            if _signature(source.lstat()) != signature:
                raise ProjectError("Workspace project files changed during export")
        for resource in specs:
            if _signature(_physical_path(Path(resource["source"])).lstat()) != resource["signature"]:
                raise ProjectError("Workspace external resources changed during export")
            for _, source, signature in resource["files"]:
                if _signature(source.lstat()) != signature:
                    raise ProjectError("Workspace external resources changed during export")
        if store is not None:
            current_directories = []
            if _project_files(store.directory, [], current_directories) != selected or current_directories != project_directories:
                raise ProjectError("Workspace project tree changed during export")
        for resource in specs:
            if resource["kind"] == "directory":
                current_directories = []
                current = [(name.removeprefix("project/"), source, signature)
                     for name, source, signature in _project_files(_physical_path(Path(resource["source"])), [], current_directories, project=False)]
                current_directories = ["", *[name.removeprefix("project/") for name in current_directories]]
                if current != resource["files"] or current_directories != resource["directories"]:
                    raise ProjectError("Workspace resource tree changed during export")
        if store is not None and store.info()["revision"] != project["revision"]:
            raise RevisionConflict("Project changed during workspace export; refresh and try again")
        sha256, archive_bytes = _digest(archive_path, max_bytes + MAX_MANIFEST_BYTES + 64 * 1024 ** 2)
        with archive_path.open("rb") as stream:
            os.fsync(stream.fileno())
        _publish_file(archive_path, destination)
    return {"path": str(destination), "sha256": sha256, "archive_bytes": archive_bytes,
            "file_count": len(inventory), "total_bytes": total, "project": manifest["project"],
            "diagnostics": diagnostics, "complete": manifest["complete"], "format": FORMAT}


def _preflight(stream, size):
    # Bound the central directory before ZipFile allocates an entry per member.
    stream.seek(max(0, size - 65557))
    tail = stream.read(65557)
    offset = tail.rfind(b"PK\x05\x06")
    if offset < 0 or offset + 22 > len(tail):
        raise ProjectError("Workspace is not a valid ZIP container")
    _, disk, directory_disk, disk_count, total_count, directory_size, _, comment = struct.unpack(
        "<4s4H2LH", tail[offset:offset + 22])
    if offset + 22 + comment != len(tail) or disk or directory_disk or disk_count != total_count \
            or not 1 <= total_count <= MAX_FILES + 1 or directory_size > 64 * 1024 ** 2:
        raise ProjectError("Workspace ZIP directory exceeds supported bounds or spans disks")
    stream.seek(0)


def _manifest(archive, max_bytes):
    members, folded, total = {}, set(), 0
    for info in archive.infolist():
        _name(info.filename)
        folded_name = unicodedata.normalize("NFC", info.filename).casefold()
        mode = stat.S_IFMT(info.external_attr >> 16)
        if folded_name in folded or info.is_dir() or mode not in (0, stat.S_IFREG) \
                or info.flag_bits & 1 or info.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
            raise ProjectError("Workspace ZIP contains duplicate, linked, encrypted or unsupported members")
        folded.add(folded_name); members[info.filename] = info
        total += info.file_size
        if info.file_size > max_bytes + MAX_MANIFEST_BYTES or total > max_bytes + MAX_MANIFEST_BYTES:
            raise ProjectError("Workspace uncompressed byte budget exceeded")
    prefixes = {}
    for name in members:
        parts = name.split("/")
        for end in range(1, len(parts) + 1):
            prefix = "/".join(parts[:end])
            folded_prefix = unicodedata.normalize("NFC", prefix).casefold()
            if folded_prefix in prefixes and prefixes[folded_prefix] != prefix:
                raise ProjectError("Workspace directory names collide on another platform")
            prefixes[folded_prefix] = prefix
            if end < len(parts) and prefix in members:
                raise ProjectError("Workspace member cannot be both a file and a parent directory")
    if "manifest.json" not in members or members["manifest.json"].file_size > MAX_MANIFEST_BYTES:
        raise ProjectError("Workspace manifest is missing or exceeds 16 MiB")
    try:
        manifest = _decode(archive.read("manifest.json"))
    except (zipfile.BadZipFile, RuntimeError, OSError):
        raise ProjectError("Workspace manifest cannot be read") from None
    required = {"format", "created_at", "project", "state", "files", "directories", "resources", "diagnostics", "complete"}
    if type(manifest) is not dict or set(manifest) != required or manifest["format"] != FORMAT:
        raise ProjectError("Unsupported workspace manifest format")
    if type(manifest["created_at"]) is not str or len(manifest["created_at"]) > 64 or "\0" in manifest["created_at"]:
        raise ProjectError("Workspace creation timestamp is invalid")
    project = manifest["project"]
    if project is not None:
        if type(project) is not dict or not {"id", "name", "revision", "format_version", "source_root"} <= project.keys() \
                or project.keys() - {"id", "name", "revision", "format_version", "source_root", "aliases"} \
                or type(project["revision"]) is not int or project["revision"] < 0 \
                or type(project["format_version"]) is not int or type(project["name"]) is not str \
                or type(project["source_root"]) is not str or not _absolute(project["source_root"]):
            raise ProjectError("Workspace project metadata is invalid")
        _origins(project, "source_root")
        try:
            UUID(project["id"])
        except (ValueError, TypeError, AttributeError):
            raise ProjectError("Workspace project identity is invalid") from None
    if manifest["state"] != "state.json" or type(manifest["complete"]) is not bool \
            or type(manifest["diagnostics"]) is not list or len(manifest["diagnostics"]) > MAX_FILES \
            or type(manifest["files"]) is not list or not 1 <= len(manifest["files"]) <= MAX_FILES:
        raise ProjectError("Workspace manifest state, inventory or diagnostics are invalid")
    for diagnostic in manifest["diagnostics"]:
        if type(diagnostic) is not dict or "code" not in diagnostic or set(diagnostic) - {"code", "path", "resource_id", "record_id"} \
                or any(type(value) is not str or len(value) > 32768 or "\0" in value for value in diagnostic.values()):
            raise ProjectError("Workspace diagnostics are invalid")
    inventory, total = {}, 0
    for entry in manifest["files"]:
        if type(entry) is not dict or set(entry) != {"path", "size", "sha256"} \
                or type(entry["path"]) is not str or type(entry["size"]) is not int or entry["size"] < 0 \
                or type(entry["sha256"]) is not str or not _SHA.fullmatch(entry["sha256"]):
            raise ProjectError("Workspace file inventory is invalid")
        name = entry["path"]
        _name(name)
        if name in inventory or name not in members or name == "manifest.json" \
                or name != "state.json" and not name.startswith(("project/", "resources/")) \
                or members[name].file_size != entry["size"]:
            raise ProjectError("Workspace inventory does not match ZIP members")
        inventory[name] = entry
        total += entry["size"]
    if total > max_bytes or set(members) != {"manifest.json", *inventory} \
            or project is not None and "project/" + DATABASE_NAME not in inventory or "state.json" not in inventory \
            or inventory["state.json"]["size"] > MAX_STATE_BYTES:
        raise ProjectError("Workspace inventory is incomplete or exceeds its byte budget")
    directories = manifest["directories"]
    if type(directories) is not list or len(directories) + len(inventory) > MAX_FILES:
        raise ProjectError("Workspace directory inventory exceeds its count budget")
    folded_directories = set()
    for name in directories:
        _name(name)
        folded_name = unicodedata.normalize("NFC", name).casefold()
        if folded_name in folded_directories or name in members or not name.startswith(("project/", "resources/")):
            raise ProjectError("Workspace directory inventory is invalid or collides with a file")
        folded_directories.add(folded_name)
        parts = name.split("/")
        for end in range(1, len(parts) + 1):
            prefix = "/".join(parts[:end])
            folded_prefix = unicodedata.normalize("NFC", prefix).casefold()
            if folded_prefix in prefixes and prefixes[folded_prefix] != prefix:
                raise ProjectError("Workspace directory names collide on another platform")
            prefixes[folded_prefix] = prefix
            if prefix in members:
                raise ProjectError("Workspace file cannot also be a parent directory")
    resources, resource_paths = manifest["resources"], set()
    if type(resources) is not list or len(resources) > 1024:
        raise ProjectError("Workspace resource mappings are invalid")
    ids, sources = set(), set()
    for resource in resources:
        if type(resource) is not dict or not {"id", "source", "path", "kind"} <= resource.keys() \
                or resource.keys() - {"id", "source", "path", "kind", "aliases"} \
                or type(resource["id"]) is not str or not _RESOURCE_ID.fullmatch(resource["id"]) \
                or resource["id"].casefold() in ids or type(resource["source"]) is not str \
                or not _absolute(resource["source"]) or resource["source"] in sources \
                or type(resource["path"]) is not str or type(resource["kind"]) is not str or resource["kind"] not in {"file", "directory"} \
                or resource["kind"] == "file" and resource["path"] not in inventory \
                or not resource["path"].startswith("resources/" + resource["id"] + "/"):
            raise ProjectError("Workspace resource mappings are invalid")
        _name(resource["path"])
        if len(resource["path"].split("/")) != 3:
            raise ProjectError("Workspace resource root path is invalid")
        ids.add(resource["id"].casefold()); sources.add(resource["source"])
        resource_paths.update(name for name in inventory if name == resource["path"] or
                              resource["kind"] == "directory" and name.startswith(resource["path"] + "/"))
    _check_aliases(resources, project)
    if resource_paths != {name for name in inventory if name.startswith("resources/")}:
        raise ProjectError("Workspace contains resources without explicit mappings")
    if project is None and any(name.startswith("project/") for name in inventory):
        raise ProjectError("Workspace without a project cannot contain project files")
    if project is None and any(name.startswith("project/") for name in directories):
        raise ProjectError("Workspace without a project cannot contain project directories")
    for name in directories:
        if name.startswith("resources/") and not any(item["kind"] == "directory" and
            (name == item["path"] or name.startswith(item["path"] + "/")) for item in resources):
            raise ProjectError("Workspace directory has no declared directory resource")
    # A forged archive cannot smuggle machine credentials that export would exclude.
    for name in [*inventory, *directories]:
        parts = name.split("/")[1:]
        if _sensitive_name(parts) or name.startswith("project/" + DATABASE_NAME + "-"):
            raise ProjectError("Workspace contains excluded host configuration or credential files")
        if name == "project/.stk" and name in inventory or name.startswith("project/.stk/") and (
                len(parts) < 2 or parts[1] not in _INTERNAL_ALLOWED or name in inventory and len(parts) < 3):
            raise ProjectError("Workspace contains unsupported internal project files")
    return manifest, inventory, total


def _verify_members(archive, inventory, staging=None):
    state = None
    for name, entry in inventory.items():
        checksum, count, state_data = hashlib.sha256(), 0, bytearray() if name == "state.json" else None
        target = staging / name if staging is not None else None
        if target is not None:
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        writer = target.open("xb") if target is not None else None
        if target is not None:
            os.chmod(target, 0o600)
        try:
            with archive.open(name) as reader:
                for data in iter(lambda: reader.read(CHUNK), b""):
                    count += len(data)
                    if count > entry["size"]:
                        raise ProjectError("Workspace member exceeds its declared size")
                    checksum.update(data)
                    if state_data is not None:
                        state_data.extend(data)
                    if writer is not None:
                        writer.write(data)
            if count != entry["size"] or checksum.hexdigest() != entry["sha256"]:
                raise ProjectError("Workspace member SHA-256 does not match its manifest")
            if writer is not None:
                writer.flush(); os.fsync(writer.fileno())
        except (zipfile.BadZipFile, RuntimeError, OSError):
            raise ProjectError("Workspace member cannot be verified") from None
        finally:
            if writer is not None:
                writer.close()
        if state_data is not None:
            state = _state(_decode(state_data))
    return state


def _read_archive(path, max_bytes, staging=None, expected_sha256=None):
    maximum = max_bytes + MAX_MANIFEST_BYTES + 64 * 1024 ** 2
    with _reader(Path(path).expanduser().absolute()) as (stream, before):
        if before.st_size > maximum:
            raise ProjectError("Workspace archive exceeds its byte budget")
        checksum = hashlib.sha256()
        for data in iter(lambda: stream.read(CHUNK), b""):
            checksum.update(data)
        digest = checksum.hexdigest()
        if expected_sha256 is not None and digest != expected_sha256:
            raise ProjectError("Workspace archive changed since preview")
        _preflight(stream, before.st_size)
        try:
            with zipfile.ZipFile(stream) as archive:
                manifest, inventory, total = _manifest(archive, max_bytes)
                state = _verify_members(archive, inventory, staging)
                _relocate(state, manifest["project"], manifest["resources"], Path("/workspace-preview"))
        except (zipfile.BadZipFile, NotImplementedError, EOFError):
            raise ProjectError("Workspace ZIP container is invalid") from None
    return manifest, state, digest, total


def preview_workspace(path, *, max_bytes=DEFAULT_MAX_BYTES):
    """Read and verify every member, without extracting or opening a project/model/Runtime."""
    manifest, state, digest, total = _read_archive(path, _limit(max_bytes))
    return {"format": FORMAT, "path": str(Path(path).expanduser().absolute()), "sha256": digest,
            "project": manifest["project"], "state": state, "file_count": len(manifest["files"]),
            "total_bytes": total, "resources": manifest["resources"],
            "diagnostics": manifest["diagnostics"], "complete": manifest["complete"]}


def import_workspace(path, destination, *, expected_sha256=None, max_bytes=DEFAULT_MAX_BYTES):
    """Verify into a private staging directory, then atomically publish a new workspace.

    The result's ``state`` contains relocated local paths. ``path_map`` maps the
    old project root and explicitly authorized resource paths to this machine.
    The unchanged source mapping is also stored in ``workspace.json`` for reopen.
    Existing destinations are never overwritten; no scripts or model/Runtime
    tasks run, and no host preferences, credentials or network policy are restored.
    """
    max_bytes = _limit(max_bytes)
    if expected_sha256 is not None and (type(expected_sha256) is not str or not _SHA.fullmatch(expected_sha256)):
        raise ProjectError("Workspace expected_sha256 must be a SHA-256 hex digest")
    destination = _output_path(destination)
    with tempfile.TemporaryDirectory(prefix=".stk-import-", dir=destination.parent) as work:
        staging = Path(work) / "workspace"
        staging.mkdir(mode=0o700)
        manifest, state, digest, total = _read_archive(path, max_bytes, staging, expected_sha256)
        for name in manifest["directories"]:
            (staging / name).mkdir(mode=0o700, parents=True, exist_ok=True)
        expected = manifest["project"]
        if expected is not None:
            project = ProjectStore(staging / "project")
            if project.info() != {key: expected[key] for key in ("id", "name", "revision", "format_version")}:
                raise ProjectError("Workspace database does not match its manifest project identity")
        for item in manifest["resources"]:
            if item["kind"] == "directory":
                (staging / item["path"]).mkdir(mode=0o700, parents=True, exist_ok=True)
        restored, path_map = _relocate(state, expected, manifest["resources"], destination)
        saved = {"format": FORMAT, "archive_sha256": digest, "project": expected,
                 "state": state, "resources": manifest["resources"], "diagnostics": manifest["diagnostics"],
                 "complete": manifest["complete"]}
        workspace_path = staging / "workspace.json"
        with workspace_path.open("xb") as stream:
            os.chmod(workspace_path, 0o600)
            stream.write(_json(saved)); stream.flush(); os.fsync(stream.fileno())
        (staging / "state.json").unlink()  # Captured state is now part of the durable reopen descriptor.
        _safe_ancestors(destination.parent)
        _publish_directory(staging, destination)
    return {"format": FORMAT, "directory": str(destination), "project_directory": str(destination / "project") if expected is not None else None,
            "workspace_path": str(destination / "workspace.json"), "sha256": digest,
            "project": expected, "state": restored, "path_map": path_map,
            "file_count": len(manifest["files"]), "total_bytes": total,
            "diagnostics": manifest["diagnostics"], "complete": manifest["complete"]}


def _relocate(state, project, resources, destination):
    resource_map = {item["id"]: str(destination / item["path"]) for item in resources}
    resource_specs = {item["id"]: item for item in resources}
    _check_aliases(resources, project)
    path_map = {origin: str(destination / item["path"]) for item in resources for origin in _origins(item)}
    if project is not None:
        path_map.update({origin: str(destination / "project") for origin in _origins(project, "source_root")})
    def local(value):
        if value.startswith("stk-project://"):
            if project is None:
                raise ProjectError("Workspace state references an absent project")
            relative = value[len("stk-project://"):]
            if relative:
                _name(relative)
            return str(destination / "project" / relative)
        if value.startswith("stk-resource://"):
            identity, _, relative = value[len("stk-resource://"):].partition("/")
            if identity not in resource_map:
                raise ProjectError("Workspace state references an undeclared resource")
            if relative:
                _name(relative)
                if resource_specs[identity]["kind"] != "directory":
                    raise ProjectError("Workspace file resource cannot contain child paths")
            return str(Path(resource_map[identity]) / relative)
        return value
    return _transform(state, local), path_map


def open_workspace(directory):
    """Restore a previously imported directory after moving it, without applying UI state.

    This reads a bounded local descriptor and the project's identity. Frozen file
    hashes remain verified by their existing project/Viewer readers; it neither
    replays jobs nor requires the original archive or the exporting computer.
    """
    destination = _physical_path(Path(directory).expanduser().absolute())
    if destination.name == "workspace.json":
        destination = destination.parent
    path = destination / "workspace.json"
    with _reader(path) as (stream, before):
        if before.st_size > MAX_MANIFEST_BYTES:
            raise ProjectError("Workspace descriptor exceeds 16 MiB")
        saved = _decode(stream.read(MAX_MANIFEST_BYTES + 1))
    if type(saved) is not dict or set(saved) != {"format", "archive_sha256", "project", "state", "resources",
                                              "diagnostics", "complete"} or saved["format"] != FORMAT \
            or type(saved["archive_sha256"]) is not str or not _SHA.fullmatch(saved["archive_sha256"]):
        raise ProjectError("Workspace descriptor is invalid")
    state = _state(saved["state"])
    resources = saved["resources"]
    if type(resources) is not list or len(resources) > 1024:
        raise ProjectError("Workspace descriptor resources are invalid")
    for item in resources:
        if type(item) is not dict or not {"id", "source", "path", "kind"} <= item.keys() \
                or item.keys() - {"id", "source", "path", "kind", "aliases"} \
                or type(item["id"]) is not str or not _RESOURCE_ID.fullmatch(item["id"]) \
                or type(item["source"]) is not str or not _absolute(item["source"]) \
                or type(item["path"]) is not str or type(item["kind"]) is not str or item["kind"] not in {"file", "directory"}:
            raise ProjectError("Workspace descriptor resources are invalid")
        _name(item["path"])
        if len(item["path"].split("/")) != 3 or not item["path"].startswith("resources/" + item["id"] + "/"):
            raise ProjectError("Workspace descriptor resource path is invalid")
        _safe_ancestors(destination / item["path"])
    _check_aliases(resources, saved["project"])
    if len({item["id"].casefold() for item in resources}) != len(resources):
        raise ProjectError("Workspace descriptor contains duplicate resource ids")
    expected = saved["project"]
    if expected is not None:
        if type(expected) is not dict or type(expected.get("source_root")) is not str \
                or not _absolute(expected["source_root"]):
            raise ProjectError("Workspace descriptor project is invalid")
        _safe_ancestors(destination / "project" / DATABASE_NAME)
        actual = ProjectStore(destination / "project").info()
        if actual["id"] != expected.get("id"):
            raise ProjectError("Workspace descriptor does not match the opened project")
    restored, path_map = _relocate(state, expected, resources, destination)
    return {"format": FORMAT, "directory": str(destination),
            "project_directory": str(destination / "project") if expected is not None else None,
            "workspace_path": str(path), "sha256": saved["archive_sha256"], "project": expected,
            "state": restored, "path_map": path_map, "diagnostics": saved["diagnostics"], "complete": saved["complete"]}
