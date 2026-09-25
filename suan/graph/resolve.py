"""Binding resolvers: graph binding names -> file sources (``suan.connectors.api.FileSource``).

Graphs never contain filesystem paths. A source node names a *binding* (for
example ``"run"``) plus a relative path inside it; the caller decides what the
binding means:

* :class:`LocalDirResolver` (CLI, desktop): binding -> a local directory. Every
  path is confined to that directory: absolute paths, ``..``, backslashes, drive
  letters and symbolic links that leave the directory are refused.
* :class:`RuntimeResolver` (node agent, MCP): binding -> ``{"task_id"}`` of an
  STK Runtime task. Files come from ``RuntimeClient.artifacts`` and
  ``RuntimeClient.download`` into a content-addressed cache, verified by
  sha256 and capped at 1 GiB per file (the ``view.build`` limit).

The file sources are the connector classes of :mod:`suan.connectors.files`
(one implementation): :class:`LocalDirSource` and :class:`RuntimeTaskSource`
only adapt them to graph error codes -- a path outside the binding raises
:class:`PathNotAllowed` (code ``path_not_allowed``, still a ``ConnectorError``
and a ``PermissionError``), a file over the cap raises :class:`BudgetExceeded` --
and :class:`RuntimeTaskSource` downloads on ``local_path`` into
``<cache_dir>/<aa>/<sha256><suffix>``. Missing files raise
``suan.connectors.files.MissingFile`` (a ``FileNotFoundError`` with code
``missing_file``) everywhere. Resolvers raise ``KeyError`` for unknown bindings
(the evaluator reports ``unknown_binding``). Standard library only.
"""
from collections.abc import Mapping
from pathlib import Path
import re

from suan.connectors import files as _files
from suan.connectors.api import ConnectorError
from suan.connectors.files import MAX_DOWNLOAD_BYTES, HashMemo, MissingFile

from .registry import BudgetExceeded, GraphError
from .schema import ID_RE

__all__ = [
    "MAX_DOWNLOAD_BYTES", "BindingResolver", "HashMemo", "LocalDirResolver", "LocalDirSource", "MissingFile",
    "PathNotAllowed", "RuntimeResolver", "RuntimeTaskSource", "check_relative_path",
]

TASK_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


class PathNotAllowed(GraphError, _files.PathNotAllowed):
    """A path that would leave its binding (absolute, ``..``, backslash, drive letter or an escaping link)."""

    def __init__(self, message, **kw):
        GraphError.__init__(self, "path_not_allowed", message, **kw)
        self.args = (message,)

    def __str__(self):
        return self.message


def check_relative_path(path, *, allow_root=False):
    """Validate a POSIX path relative to a binding root and return it normalized (``"a/b"``).

    ``""`` and ``"."`` mean the root (only with ``allow_root``). Rejects absolute
    paths, drive letters, ``..`` segments, backslashes and NUL characters.
    """
    if not isinstance(path, str):
        raise PathNotAllowed(f"A path inside a binding must be a string, got {type(path).__name__}")
    relative = ""
    if path not in ("", "./"):
        try:
            relative = _files.check_path(path)
        except ConnectorError as exc:
            raise PathNotAllowed(str(exc)) from None
    if not relative and not allow_root:
        raise PathNotAllowed("A file path inside the binding is required")
    return relative


# ---------------------------------------------------------------------------
# Local directories


class LocalDirSource(_files.LocalFiles):
    """A local directory as a :class:`suan.connectors.api.FileSource`, confined to ``root``
    (:class:`suan.connectors.files.LocalFiles` with graph error codes; ``local_path`` of a missing
    file raises ``MissingFile``)."""

    path_error = PathNotAllowed

    def __init__(self, root, *, hash_memo=None, binding=None):
        super().__init__(root, binding=binding, hash_memo=hash_memo)

    def local_path(self, path):
        """The confined local path; ``""``/``"."`` is the binding directory itself."""
        found = super().local_path(path)
        if found is None:
            raise self._missing(path)
        return found


class LocalDirResolver:
    """Bindings to local directories: ``LocalDirResolver({"run": "/data/run1"})``.

    ``hash_memo`` is a :class:`HashMemo` or the path of its SQLite file; by default the
    process-wide memo, so a new resolver per request does not re-hash unchanged files.
    """

    def __init__(self, bindings, *, hash_memo=None):
        self._memo = hash_memo if isinstance(hash_memo, HashMemo) or hash_memo is None else HashMemo(hash_memo)
        self._sources = {}
        for name, root in dict(bindings).items():
            _check_binding_name(name)
            self._sources[name] = LocalDirSource(root, hash_memo=self._memo, binding=name)

    def names(self):
        return sorted(self._sources)

    def resolve(self, binding):
        try:
            return self._sources[binding]
        except KeyError:
            raise KeyError(binding) from None


# ---------------------------------------------------------------------------
# STK Runtime tasks


class RuntimeTaskSource(_files.RuntimeFiles):
    """The published artifacts of one Runtime task as a :class:`suan.connectors.api.FileSource`.

    :class:`suan.connectors.files.RuntimeFiles` with graph error codes: listing and
    hashes come from ``client.artifacts(task_id)`` (only files of finished tasks are
    listed in API v1); ``open``/``local_path`` download a file once into
    ``<cache_dir>/<sha[:2]>/<sha><suffix>`` (verified by ``RuntimeClient.download``);
    files over ``max_bytes`` raise :class:`BudgetExceeded`.
    """

    path_error = PathNotAllowed
    objects_dir = ""

    def __init__(self, client, task_id, cache_dir, *, max_bytes=MAX_DOWNLOAD_BYTES, binding=None):
        if not isinstance(task_id, str) or not TASK_ID_RE.match(task_id):
            raise GraphError("unknown_binding", f"Invalid task id {task_id!r} for binding '{binding}'")
        super().__init__(client, task_id, cache_dir, max_bytes=max_bytes, binding=binding)

    def _too_large(self, message):
        return BudgetExceeded(message)

    def local_path(self, path):
        """Download (once, sha256-verified) and return the cached local copy; directories are not available."""
        if check_relative_path(path, allow_root=True) == "":
            return None
        return self.fetch(path)


class RuntimeResolver:
    """Bindings to Runtime tasks: ``RuntimeResolver(client, cache_dir).bind({"run": {"task_id": "..."}})``."""

    def __init__(self, client, cache_dir, bindings=None, *, max_bytes=MAX_DOWNLOAD_BYTES):
        self.client = client
        self.cache_dir = Path(cache_dir)
        self.max_bytes = max_bytes
        self._tasks = {}
        self._sources = {}
        for name, value in (bindings or {}).items():
            _check_binding_name(name)
            if isinstance(value, Mapping):
                if set(value) != {"task_id"}:
                    raise GraphError("unknown_binding", f"Binding '{name}' must be {{\"task_id\": \"...\"}}; "
                                     "paths are never accepted from requests")
                value = value["task_id"]
            if not isinstance(value, str) or not TASK_ID_RE.match(value):
                raise GraphError("unknown_binding", f"Binding '{name}' has an invalid task id")
            self._tasks[name] = value

    def bind(self, bindings):
        """A resolver for request bindings ``{name: {"task_id": id}}`` sharing this client and cache."""
        return RuntimeResolver(self.client, self.cache_dir, {**self._tasks, **dict(bindings or {})},
                               max_bytes=self.max_bytes)

    def names(self):
        return sorted(self._tasks)

    def resolve(self, binding):
        if binding not in self._tasks:
            raise KeyError(binding)
        if binding not in self._sources:
            self._sources[binding] = RuntimeTaskSource(self.client, self._tasks[binding], self.cache_dir,
                                                       max_bytes=self.max_bytes, binding=binding)
        return self._sources[binding]


class BindingResolver:
    """Several resolvers (or a mapping of binding -> FileSource) combined; the first that knows a binding wins."""

    def __init__(self, *resolvers):
        self.resolvers = [r for r in resolvers if r is not None]

    def names(self):
        names = set()
        for resolver in self.resolvers:
            names.update(resolver.keys() if isinstance(resolver, Mapping) else resolver.names())
        return sorted(names)

    def resolve(self, binding):
        for resolver in self.resolvers:
            try:
                return resolver[binding] if isinstance(resolver, Mapping) else resolver.resolve(binding)
            except KeyError:
                continue
        raise KeyError(binding)

    def bind(self, bindings):
        bound = [r.bind(bindings) if hasattr(r, "bind") else r for r in self.resolvers]
        return BindingResolver(*bound)


def _check_binding_name(name):
    if not isinstance(name, str) or not ID_RE.match(name):
        raise GraphError("unknown_binding", f"Binding name {name!r} must match ^[a-z][a-z0-9_]{{0,63}}$")
