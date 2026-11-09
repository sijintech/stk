"""Local graph bindings constrained to the registered bytes of a collected case.

The proof keeps the lexical project root and case path separate. Reads use the
project's guarded descriptor traversal and return verified private streams, so a
consumer never obtains a mutable local path or follows a replaced case root.
"""
from collections.abc import Mapping
import os
from pathlib import Path
import re
from tempfile import TemporaryFile

from suan.connectors.api import FileInfo
from suan.connectors.files import _matches, check_path
from suan.project.files import _read_managed_file
from suan.project.store import ProjectError
from suan.runtime.models import relative_path

from .registry import GraphError
from .resolve import BindingResolver, LocalDirResolver


MAX_FILES = 10000
MAX_FILE_BYTES = 1024 ** 3


def _relative(value):
    try:
        if relative_path(value) != value or len(value) > 32768:
            raise ValueError
    except ValueError:
        raise GraphError("bad_request", "Collected paths must be canonical project-relative POSIX paths") from None
    return value


class CollectedFiles:
    """A case FileSource whose every content read verifies the registered SHA-256."""

    def __init__(self, root, proof, *, binding=None):
        if not isinstance(proof, dict) or set(proof) != {"project_root", "case_path", "files"}:
            raise GraphError("bad_request", "A collected source requires project_root, case_path and files")
        project_root = proof["project_root"]
        if (not isinstance(project_root, str) or not project_root or "\0" in project_root
                or len(project_root) > 32768 or not Path(project_root).is_absolute()):
            raise GraphError("bad_request", "A collected source requires an absolute lexical project root")
        self.project_root = Path(project_root)
        self.case_path = _relative(proof["case_path"])
        self.root = self.project_root.joinpath(*self.case_path.split("/"))
        try:
            matching_root = isinstance(root, (str, os.PathLike)) and Path(root) == self.root
        except (TypeError, ValueError):
            matching_root = False
        if not matching_root:
            raise GraphError("bad_request", "The local binding must match the collected project and case paths")
        entries = proof["files"]
        if not isinstance(entries, list) or not 1 <= len(entries) <= MAX_FILES:
            raise GraphError("bad_request", "A collected source requires between 1 and 10000 files")
        self.binding = binding
        self._files = {}
        normalized = set()
        prefix = self.case_path + "/"
        for entry in entries:
            if (not isinstance(entry, dict) or set(entry) != {"path", "sha256"}
                    or not isinstance(entry["sha256"], str)
                    or re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]) is None):
                raise GraphError("bad_request", "Collected file entries require a path and a lowercase SHA-256")
            path = _relative(entry["path"])
            if not path.startswith(prefix) or os.path.normcase(path) in normalized:
                raise GraphError("bad_request", "Collected files must be distinct files inside the case path")
            normalized.add(os.path.normcase(path))
            self._files[path[len(prefix):]] = (path, entry["sha256"])

    def _entry(self, path):
        try:
            relative = check_path(path)
        except ValueError:
            raise GraphError("invalid_data", "The requested collected file path is invalid") from None
        try:
            return relative, self._files[relative]
        except KeyError:
            raise GraphError("invalid_data", "The requested file is absent from the collected manifest") from None

    def _read(self, relative, project_path, expected=None, *, copy_to=None):
        try:
            info, _ = _read_managed_file(self.project_root, project_path, expected, copy_to=copy_to)
        except (ProjectError, OSError):
            raise GraphError("invalid_data", f"Collected file is missing, unsafe or changed: {relative}") from None
        if not 0 <= info.st_size <= MAX_FILE_BYTES:
            raise GraphError("invalid_data", f"Collected file exceeds the 1 GiB limit: {relative}")
        return info

    def stat(self, path):
        relative, (project_path, _) = self._entry(path)
        info = self._read(relative, project_path)
        return FileInfo(relative, info.st_size, info.st_mtime)

    def exists(self, path):
        try:
            self.stat(path)
        except GraphError:
            return False
        return True

    def list(self, prefix=""):
        prefix = prefix or ""
        try:
            wanted = "" if not prefix or prefix in (".", "./") else check_path(prefix)
        except ValueError:
            raise GraphError("invalid_data", "The collected listing prefix is invalid") from None
        directory = (not wanted or prefix.endswith("/")
                     or any(path.startswith(wanted + "/") for path in self._files))
        return [self.stat(path) for path in sorted(self._files) if _matches(path, wanted, directory)]

    def open(self, path):
        relative, (project_path, digest) = self._entry(path)
        info = self._read(relative, project_path)
        snapshot = TemporaryFile(mode="w+b", prefix="stk-collected-")
        try:
            self._read(relative, project_path, {"size": info.st_size, "sha256": digest}, copy_to=snapshot)
            snapshot.seek(0)
            return snapshot
        except BaseException:
            snapshot.close()
            raise

    def sha256(self, path):
        relative, (_, digest) = self._entry(path)
        with self.open(relative):
            return digest

    def local_path(self, path):
        return None


def local_resolver(bindings, proofs=None):
    """Resolve ordinary directories and opt-in collected sources without resolving their roots."""
    if proofs is not None and not isinstance(proofs, Mapping):
        raise GraphError("bad_request", "Local proofs must be a mapping of local binding names")
    if not proofs:
        return LocalDirResolver(bindings)
    if not isinstance(bindings, Mapping) or any(name not in bindings for name in proofs):
        raise GraphError("bad_request", "Every collected proof must name an existing local binding")
    guarded = {}
    for name, proof in proofs.items():
        if not isinstance(name, str) or re.fullmatch(r"[a-z][a-z0-9_]{0,63}", name) is None:
            raise GraphError("bad_request", "A collected proof has an invalid local binding name")
        guarded[name] = CollectedFiles(bindings[name], proof, binding=name)
    ordinary = {name: root for name, root in bindings.items() if name not in guarded}
    return BindingResolver(guarded, LocalDirResolver(ordinary))
