"""Passive verification of one explicitly selected native helper installation.

Hashes establish local integrity, not publisher authenticity. The caller must
trust the installation owner and keep its bytes immutable until process startup.
This module never searches PATH, reads a discovery environment variable, starts a
process, downloads a component, or grants any peer/session/file permission.
"""
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import stat
import unicodedata


MANIFEST_NAME = "helper-manifest.json"
INSTALLATION_FORMAT = "stk.peer-helper-installation/1"
HELPER_ABI = "stk.peer-helper-ipc/1"
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_ID = re.compile(r"[a-z0-9][a-z0-9_.-]{0,63}\Z")
_ROLES = {"executable", "library", "notice", "source", "build"}
_ROOT_KEYS = {"format", "abi", "protocol", "platform", "architecture",
              "executable", "files", "components", "host_requirements"}


class HelperInstallationError(RuntimeError):
    """Fixed safe error: never includes a rejected path or manifest value."""

    def __init__(self, code, message):
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class InstalledHelper:
    executable: Path
    manifest_sha256: str
    platform: str
    architecture: str
    abi: str


def _bad(code="invalid_installation", message="Invalid helper installation"):
    raise HelperInstallationError(code, message)


def _ordinary(path, directory=False):
    try:
        value = path.lstat()
    except FileNotFoundError:
        _bad("unavailable", "Helper installation is unavailable")
    except OSError:
        _bad()
    if (stat.S_ISLNK(value.st_mode)
            or getattr(value, "st_file_attributes", 0) & 0x400
            or not (stat.S_ISDIR(value.st_mode) if directory else stat.S_ISREG(value.st_mode))):
        _bad()
    return value


def _stamp(value):
    return (value.st_dev, value.st_ino, value.st_mode, value.st_size,
            value.st_mtime_ns, value.st_ctime_ns)


def _cross_api_stamp(value):
    mode = value.st_mode
    if os.name == "nt":
        # CPython path stat infers these bits from .exe/.bat/.cmd/.com, while
        # descriptor stat has no filename. Full per-API stamps below still
        # detect every mode or ctime change during and after hashing.
        mode &= ~0o111
    return (value.st_dev, value.st_ino, mode, value.st_size, value.st_mtime_ns)


def _digest(path, maximum):
    before = _ordinary(path)
    if before.st_size > maximum:
        _bad()
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    flags |= getattr(os, "O_NONBLOCK", 0)
    try:
        fd = os.open(path, flags)
        with os.fdopen(fd, "rb") as stream:
            opened = os.fstat(stream.fileno())
            # Windows fd/path APIs expose different ctime and executable bits.
            # Compare each API's full metadata against its own final observation.
            if not stat.S_ISREG(opened.st_mode) or _cross_api_stamp(before) != _cross_api_stamp(opened):
                _bad()
            digest = hashlib.sha256()
            count = 0
            while block := stream.read(1024 * 1024):
                count += len(block)
                if count > maximum:
                    _bad()
                digest.update(block)
            if _stamp(opened) != _stamp(os.fstat(stream.fileno())):
                _bad("changed_installation", "Helper installation changed during verification")
    except HelperInstallationError:
        raise
    except OSError:
        _bad()
    if _stamp(before) != _stamp(_ordinary(path)) or count != before.st_size:
        _bad("changed_installation", "Helper installation changed during verification")
    return digest.hexdigest(), count, before


def _path(value):
    if (type(value) is not str or not value or len(value.encode("utf-8")) > 512
            or unicodedata.normalize("NFC", value) != value
            or "\\" in value or ":" in value or "\x00" in value
            or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        _bad()
    parts = value.split("/")
    if any(not p or p in (".", "..") or p.endswith((".", " ")) for p in parts):
        _bad()
    if PurePosixPath(value).is_absolute():
        _bad()
    reserved = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)),
                *(f"lpt{i}" for i in range(1, 10))}
    if any(p.split(".", 1)[0].casefold() in reserved for p in parts):
        _bad()
    return value


def _text(value, maximum=160):
    if (type(value) is not str or not value or len(value) > maximum
            or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        _bad()
    return value


def _unique_pairs(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            _bad()
        value[key] = item
    return value


def _host():
    systems = {"Linux": "linux", "Darwin": "darwin", "Windows": "windows"}
    machines = {"x86_64": "x86_64", "amd64": "x86_64", "aarch64": "aarch64", "arm64": "aarch64"}
    system, machine = systems.get(platform.system()), machines.get(platform.machine().lower())
    if system is None or machine is None:
        _bad("unsupported_platform", "Unsupported helper platform")
    return system, machine


def load_helper_installation(prefix, *, expected_manifest_sha256=None):
    """Verify a closed manifest and its complete file set without starting it.

    An optional independently trusted manifest digest binds a particular release.
    Self-consistent manifest hashes alone do not authenticate a publisher. Local
    integrity checks are not a sandbox against an installation owner racing or
    replacing files after this function returns.
    """
    try:
        root = Path(prefix)
        if not root.is_absolute() or ".." in root.parts:
            _bad()
        for ancestor in reversed((root, *root.parents)):
            _ordinary(ancestor, directory=True)
        if expected_manifest_sha256 is not None and (
                type(expected_manifest_sha256) is not str or not _HEX.fullmatch(expected_manifest_sha256)):
            _bad()
        manifest_path = root / MANIFEST_NAME
        manifest_digest, _, manifest_stat = _digest(manifest_path, 1024 * 1024)
        if expected_manifest_sha256 is not None and manifest_digest != expected_manifest_sha256:
            _bad("manifest_mismatch", "Helper manifest does not match the selected release")
        with manifest_path.open("rb") as stream:
            raw = stream.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024 or hashlib.sha256(raw).hexdigest() != manifest_digest:
            _bad("changed_installation", "Helper installation changed during verification")
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_pairs,
                           parse_constant=lambda _: _bad())
        if type(value) is not dict or set(value) != _ROOT_KEYS:
            _bad()
        system, architecture = _host()
        if value["format"] != INSTALLATION_FORMAT or value["abi"] != HELPER_ABI or value["protocol"] != "stk.peer/1":
            _bad("incompatible_abi", "Incompatible helper installation ABI")
        if value["platform"] != system or value["architecture"] != architecture:
            _bad("unsupported_platform", "Helper installation platform does not match this machine")
        executable = _path(value["executable"])
        if executable != "bin/stk-peer-transport" + (".exe" if system == "windows" else ""):
            _bad()
        if type(value["host_requirements"]) is not list or len(value["host_requirements"]) > 64:
            _bad()
        for requirement in value["host_requirements"]:
            _text(requirement)
        files = value["files"]
        if type(files) is not list or not 3 <= len(files) <= 512:
            _bad()
        paths, folded, ancestors, stamps = {}, set(), set(), {}
        total = 0
        for item in files:
            if type(item) is not dict or set(item) != {"path", "bytes", "sha256", "role", "component"}:
                _bad()
            path = _path(item["path"])
            if path == MANIFEST_NAME or path.casefold() in folded:
                _bad()
            folded.add(path.casefold())
            if (type(item["bytes"]) is not int or not 0 <= item["bytes"] <= 1024 ** 3
                    or type(item["sha256"]) is not str or not _HEX.fullmatch(item["sha256"])
                    or item["role"] not in _ROLES or type(item["component"]) is not str
                    or not _ID.fullmatch(item["component"])):
                _bad()
            paths[path] = item
            total += item["bytes"]
            if total > 4 * 1024 ** 3:
                _bad()
            for parent in PurePosixPath(path).parents:
                if str(parent) != ".":
                    ancestors.add(str(parent))
        if any(path.casefold() in folded for path in ancestors):
            _bad()
        if executable not in paths or paths[executable]["role"] != "executable":
            _bad()
        if sum(item["role"] == "executable" for item in files) != 1:
            _bad()
        components = value["components"]
        if type(components) is not list or not 1 <= len(components) <= 128:
            _bad()
        component_ids = set()
        for component in components:
            if type(component) is not dict or set(component) != {"id", "version", "license", "notices", "sources"}:
                _bad()
            identity = component["id"]
            if type(identity) is not str or not _ID.fullmatch(identity) or identity in component_ids:
                _bad()
            component_ids.add(identity)
            _text(component["version"])
            _text(component["license"], maximum=512)
            for key, role in (("notices", "notice"), ("sources", "source")):
                items = component[key]
                if type(items) is not list or not 1 <= len(items) <= 32 or len(set(items)) != len(items):
                    _bad()
                for path in items:
                    if (type(path) is not str or path not in paths or paths[path]["role"] != role
                            or paths[path]["component"] != identity):
                        _bad()
        if {item["component"] for item in files} != component_ids:
            _bad()
        actual = set()
        for directory, dirnames, filenames in os.walk(root, followlinks=False):
            for name in dirnames:
                path = Path(directory) / name
                _ordinary(path, directory=True)
                if path.relative_to(root).as_posix() not in ancestors:
                    _bad()
            for name in filenames:
                relative = (Path(directory) / name).relative_to(root).as_posix()
                if relative != MANIFEST_NAME and relative not in paths:
                    _bad()
                actual.add(relative)
        if actual != set(paths) | {MANIFEST_NAME}:
            _bad()
        for path, item in paths.items():
            digest, size, before = _digest(root / path, 1024 ** 3)
            if digest != item["sha256"] or size != item["bytes"]:
                _bad("file_mismatch", "Helper installation file integrity check failed")
            stamps[path] = _stamp(before)
        if system != "windows" and not _ordinary(root / executable).st_mode & 0o111:
            _bad()
        for path, stamp in stamps.items():
            if _stamp(_ordinary(root / path)) != stamp:
                _bad("changed_installation", "Helper installation changed during verification")
        if _stamp(_ordinary(manifest_path)) != _stamp(manifest_stat):
            _bad("changed_installation", "Helper installation changed during verification")
        return InstalledHelper(root / executable, manifest_digest, system, architecture, HELPER_ABI)
    except HelperInstallationError:
        raise
    except (OSError, ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        _bad()
