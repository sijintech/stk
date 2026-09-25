"""Connector protocols (API version 1). Standard library only; heavy imports stay inside methods.

A connector has two halves:

* the heavy half (:class:`Connector`, entry-point group ``stk.connectors``)
  runs where the data lives (node-agent host or desktop): ``sniff``,
  ``describe`` (-> stk.result/1), ``open`` (-> :class:`DatasetHandle` with
  region/stride pushdown), ``verify``, ``monitor_adapter``, ``default_graphs``;
* the light half (:class:`InputConnector`, group ``stk.inputs``) needs only the
  standard library (plus tomllib/jsonschema when available) and runs on any OS:
  ``input_schema``, ``read_case``, ``write_case``, ``validate_case``,
  ``task_spec``.

Graph node catalogs register under group ``stk.nodes``. When two installed
connectors claim the same id, the higher ``info()["priority"]`` wins (the
private ``stk-mupro`` package uses 10). See docs/specs/stk-data-format-v1.md.
"""
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, BinaryIO, Iterable, Mapping, Protocol, Sequence, runtime_checkable

if TYPE_CHECKING:  # pragma: no cover
    from suan.data.model import Dataset

__all__ = [
    "API_VERSION", "ENTRY_POINT_GROUPS",
    "Connector", "ConnectorError", "DatasetHandle", "FileInfo", "FileSource", "InputConnector", "Match",
    "MonitorAdapter", "Resolver",
]

API_VERSION = 1
ENTRY_POINT_GROUPS = {"connectors": "stk.connectors", "inputs": "stk.inputs", "nodes": "stk.nodes"}


class ConnectorError(ValueError):
    """A connector failure with a stable ``code`` (e.g. ``not_found``, ``unsupported``, ``invalid_data``)."""

    def __init__(self, message, code="connector_error"):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class FileInfo:
    """One file of a :class:`FileSource`: POSIX ``path`` relative to the source root, ``size`` in bytes,
    ``mtime`` in Unix seconds (float, may be ``None`` for remote listings)."""

    path: str
    size: int
    mtime: float | None = None


@dataclass(frozen=True)
class Match:
    """Result of :meth:`Connector.sniff`: ``confidence`` in [0, 1] and a human-readable ``reason``."""

    connector: str
    confidence: float
    app: str | None = None
    reason: str = ""


@runtime_checkable
class FileSource(Protocol):
    """A run directory, local or remote (e.g. a Runtime task). Paths are POSIX, relative, never '..'."""

    def list(self, prefix: str = "") -> Iterable[FileInfo]:
        """Files under ``prefix`` (recursive), each with path, size and mtime."""

    def open(self, path: str) -> BinaryIO:
        """A seekable binary stream (remote sources may download to a local cache first)."""

    def local_path(self, path: str) -> Path | None:
        """The local filesystem path when the file is on this host (zero-copy), else ``None``."""

    def sha256(self, path: str) -> str:
        """Hex sha256 of the file content, cached by (path, size, mtime)."""


@runtime_checkable
class DatasetHandle(Protocol):
    """An opened dataset of a run.

    ``frame`` is a frame selector (ref-1 ``frame_selector``): ``{"step": N}``,
    ``{"latest": True}``, ``{"first": True}`` or ``{"index": i}`` (optionally with
    ``"policy": "latest_at_or_before" | "exact"``), or ``None`` for datasets
    without frames. ``region`` is ``((i0, i1), (j0, j1), (k0, k1))`` inclusive
    point indices; ``stride`` is ``(sx, sy, sz)``. Both are pushdown hints for
    image kinds: a reader may read less, and the result must equal
    crop-then-sample of the full frame.
    """

    descriptor: dict  # stk.dataset/1

    def read(self, *, frame: Mapping[str, Any] | None, fields: Sequence[str] | None = None,
             region: Sequence[Sequence[int]] | None = None, stride: Sequence[int] | None = None) -> "Dataset":
        """Read one frame as an in-memory dataset (suan.data.model)."""

    def stats(self, *, frame: Mapping[str, Any] | None, field: str) -> dict:
        """Cached per-component statistics:
        ``{"field", "frame": {"step"}, "components": [{"min", "max", "mean", "count", "nan_count"}],
        "magnitude": {...} | None}``."""


@runtime_checkable
class MonitorAdapter(Protocol):
    """Turns a legacy program's native progress files into stk events v1 (adapt mode)."""

    def poll(self, *, final: bool = False) -> list[dict]:
        """New events since the last poll as ``{"type", "data"}`` dicts (the emitter adds v/seq/ts/src).
        ``final=True`` after the child exited: flush everything still pending."""


@runtime_checkable
class Connector(Protocol):
    """Heavy half: runs where the data lives."""

    id: str        # e.g. "mupro.muferro"
    version: str   # connector version, e.g. "0.1.0"
    api: int       # API_VERSION it implements

    def info(self) -> dict:
        """Static description (exported by ``suan connectors list --json``):
        ``{"id", "version", "api", "apps": [...], "priority": 0, "license",
        "capabilities": {"read": [kinds], "inputs": {...}, "verify": verifier|None,
        "monitor_adapter": bool, "task_spec": bool, "default_graphs": [...]},
        "runs_on": {"describe": "node", "read": "node|desktop", "inputs": "any", "monitor_adapter": "task"}}``."""

    def sniff(self, run: FileSource) -> Match | None:
        """Recognize a run from file names and headers only (< 100 ms); ``None`` if not ours."""

    def describe(self, run: FileSource, *, live: bool = False) -> dict:
        """The stk.result/1 manifest, without reading field values. ``live=True`` lists frames found
        so far and sets ``complete: false``."""

    def open(self, run: FileSource, dataset_id: str) -> DatasetHandle:
        """Open one dataset listed by :meth:`describe`."""

    def verify(self, run: FileSource) -> dict | None:
        """``{"verifier", "status", "checks": [...]}`` or ``None`` when the connector cannot verify."""

    def monitor_adapter(self, run: FileSource, case: dict | None) -> MonitorAdapter | None:
        """An adapter for programs that do not emit events themselves, or ``None``."""

    def default_graphs(self, result: dict) -> list[dict]:
        """stk.graph/1 templates suited to this result (e.g. the muferro-domains preset, bound to ``run``)."""


@runtime_checkable
class InputConnector(Protocol):
    """Light half: standard library only; runs on the Windows client, the hub and MCP servers."""

    def input_schema(self, app: str) -> dict:
        """JSON Schema 2020-12 of the case parameters with ``x-stk-*`` form annotations."""

    def read_case(self, case: FileSource) -> dict:
        """Native input files -> stk.case/1."""

    def write_case(self, case: dict, out_dir: Path) -> list[dict]:
        """stk.case/1 -> native files in ``out_dir``; returns ``[{"path", "sha256", "generated": True}]``."""

    def validate_case(self, case_dir: Path) -> list[dict]:
        """Checks only, never executes: ``[{"id", "status": "pass|fail|warn", "message"}]``."""

    def task_spec(self, case: dict, resources: dict, **opts: Any) -> dict:
        """Runtime TaskSpec keyword arguments for this case (cf. ``suan.mupro.spec.muferro_spec``)."""


@runtime_checkable
class Resolver(Protocol):
    """Maps graph binding names to file sources (implemented in suan.graph.resolve, Phase B2)."""

    def resolve(self, binding: str) -> FileSource:
        """The :class:`FileSource` for ``binding``; raises ``KeyError`` for unknown bindings."""
