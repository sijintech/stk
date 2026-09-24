"""Graph result cache (docs/specs/stk-graph-v1.md §5): Merkle keys, an in-memory LRU and a disk store.

Keys are hex sha256 of canonical JSON (``suan.graph.schema.canonical_json``:
sorted keys, no whitespace, shortest round-trip floats, -0.0 -> 0.0, no NaN)::

    data_key = sha256({"type": id, "impl": impl_version, "params": data params (normalized),
                       "inputs": {port: ["<upstream data key>:<port>", ...]}, "source": fingerprint | null})
    full_key = sha256({"data": data_key, "client": client params (normalized),
                       "inputs": {port: ["<upstream full key>:<port>", ...]}})

Node params are normalized by their schema before hashing (``1`` and ``1.0`` of a
``number`` param hash equally; ``0.1`` and ``1e-1`` are the same float), and
dict order never matters. Fingerprints are converted to plain JSON first
(NumPy scalars -> Python numbers), so a source key covers the content sha256 of
the files it reads.

Tiers:

* memory: an LRU bounded by an estimate of the bytes held (default 2 GiB);
  values larger than the budget are not kept in memory;
* disk (``root`` given, nodes with ``cache="disk"``): immutable entry
  directories written to ``<root>/tmp`` and renamed into place, pruned
  least-recently-used when they exceed ``disk_bytes`` (default 20 GiB), with
  SQLite metadata. Readers never see partial entries; a corrupt entry is a miss.

Disk layout::

    <root>/objects/<key[:2]>/<key>/entry.json    {"schema": "stk.cache-entry/1", "key", "ports", "notes", ...}
    <root>/objects/<key[:2]>/<key>/<nn>.<ext>    one file per port, written by a codec
    <root>/index.sqlite                          size, created and last-access time per entry (LRU)
    <root>/tmp/, <root>/trash/                   atomic writes and deferred deletes
    <root>/scratch/<key[:2]>/<key>/              NodeContext.cache_dir

Codecs are pluggable (``GraphCache(codecs=[...])``); the defaults store M1
datasets (``ImageData``/``PolyData``/``Table``) as ``.npz`` + JSON metadata,
NumPy arrays as ``.npy`` (never pickled), JSON values and raw bytes. A value no
codec accepts stays memory-only. NumPy is imported lazily: the module imports
without it (the hub validates graphs without NumPy).
"""
from collections import OrderedDict
from contextlib import closing
from dataclasses import dataclass, fields as dataclass_fields, is_dataclass
import json
import math
import os
from pathlib import Path, PurePath
import re
import shutil
import sqlite3
import sys
import threading
import time
import uuid

from .schema import canonical_json, sha256_hex

__all__ = [
    "DEFAULT_DISK_BYTES", "DEFAULT_MEMORY_BYTES", "ENTRY_SCHEMA",
    "BytesCodec", "CacheHit", "Codec", "DatasetNpzCodec", "GraphCache", "JsonCodec", "NdarrayCodec",
    "canonical", "data_key", "default_codecs", "estimate_nbytes", "freeze", "full_key", "plain_json", "sub_key",
]

DEFAULT_MEMORY_BYTES = 2 * 1024**3
DEFAULT_DISK_BYTES = 20 * 1024**3
ENTRY_SCHEMA = "stk.cache-entry/1"
KEY_RE = re.compile(r"^[0-9a-f]{64}$")
_TOUCH_INTERVAL = 30.0  # seconds between access-time updates of one disk entry
_PRUNE_TARGET = 0.9     # prune down to this fraction of the disk budget


# ---------------------------------------------------------------------------
# Keys


def plain_json(value, _depth=0):
    """Plain JSON value for hashing: NumPy scalars/arrays -> Python, tuples -> lists, paths -> POSIX strings.

    Raises ``TypeError`` for values JSON cannot represent (bytes, arbitrary objects).
    """
    if _depth > 64:
        raise TypeError("Value is nested too deeply to hash")
    if value is None or isinstance(value, (bool, str, int, float)):
        return value
    if isinstance(value, dict):
        return {(key if isinstance(key, str) else _key_str(key)): plain_json(item, _depth + 1)
                for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain_json(item, _depth + 1) for item in value]
    if isinstance(value, PurePath):
        return value.as_posix()
    module = type(value).__module__ or ""
    if module.startswith("numpy"):
        if hasattr(value, "tolist"):
            return plain_json(value.tolist(), _depth + 1)
        if hasattr(value, "item"):
            return value.item()
    raise TypeError(f"Cannot hash a value of type {type(value).__name__}")


def _key_str(key):
    module = type(key).__module__ or ""
    if module.startswith("numpy") and hasattr(key, "item"):
        key = key.item()
    if isinstance(key, (int, float, bool)) or key is None:
        return json.dumps(key)
    raise TypeError(f"Object keys must be strings, got {type(key).__name__}")


def canonical(value):
    """Canonical JSON bytes of ``plain_json(value)``."""
    return canonical_json(plain_json(value))


def data_key(type_id, impl_version, params, inputs, source=None):
    """Data key of a node: type, implementation version, data-stage params, upstream data keys, source content."""
    return sha256_hex(canonical({"type": type_id, "impl": impl_version, "params": params, "inputs": inputs,
                                 "source": source}))


def full_key(data, client_params, inputs):
    """Full key: the data key plus client-stage params and the upstream full keys."""
    return sha256_hex(canonical({"data": data, "client": client_params, "inputs": inputs}))


def sub_key(key, name):
    """Key of a named intermediate of a node (``NodeContext.cached``) or of a derived value (finalize)."""
    return sha256_hex(canonical({"key": key, "name": name}))


# ---------------------------------------------------------------------------
# Sizes and immutability


def _dataset_arrays(value):
    """Arrays held by an ``suan.data.model`` dataset (field values, points and cells)."""
    arrays = [f.values for f in getattr(value, "fields", {}).values() if getattr(f, "values", None) is not None]
    points = getattr(value, "points", None)
    if points is not None:
        arrays.append(points)
    for name in ("verts", "lines", "polys"):
        cells = getattr(value, name, None)
        if cells is not None and hasattr(cells, "offsets"):
            arrays.extend(a for a in (cells.offsets, cells.connectivity) if a is not None)
    return arrays


def _is_dataset(value):
    return hasattr(value, "fields") and hasattr(value, "kinds") and hasattr(value, "descriptor")


def _members(value):
    """Attribute values of STK objects (dataclasses, or plain classes defined in ``suan.*``), else ``None``."""
    if isinstance(value, type):
        return None
    if is_dataclass(value):
        return [getattr(value, f.name, None) for f in dataclass_fields(value)]
    if (type(value).__module__ or "").startswith("suan.") and hasattr(value, "__dict__"):
        return list(vars(value).values())
    return None


def estimate_nbytes(value, _depth=0):
    """Approximate bytes held by a value (arrays, datasets, bytes, JSON-like containers)."""
    if _depth > 32:
        return 64
    if value is None or isinstance(value, (bool, int, float)):
        return 16
    if isinstance(value, (bytes, bytearray)):
        return len(value) + 32
    if isinstance(value, memoryview):
        return value.nbytes + 32
    if isinstance(value, str):
        return len(value) + 48
    if _is_dataset(value):
        return 1024 + sum(int(getattr(a, "nbytes", 0)) for a in _dataset_arrays(value))
    nbytes = getattr(value, "nbytes", None)
    if isinstance(nbytes, int) and not isinstance(value, (dict, list, tuple)):
        return nbytes + 96
    if isinstance(value, dict):
        return 64 + sum(estimate_nbytes(k, _depth + 1) + estimate_nbytes(v, _depth + 1) for k, v in value.items())
    if isinstance(value, (list, tuple)):
        return 56 + sum(estimate_nbytes(item, _depth + 1) for item in value)
    members = _members(value)
    if members is not None:
        return 64 + sum(estimate_nbytes(item, _depth + 1) for item in members)
    return sys.getsizeof(value)


def freeze(value, _depth=0):
    """Mark every NumPy array reachable from ``value`` read-only (cached values are shared between nodes).

    Walks datasets, dicts, lists, tuples, dataclasses and objects of ``suan.*``
    classes; returns ``value``.
    """
    if _depth > 32 or value is None or isinstance(value, (bool, int, float, str, bytes)):
        return value
    if _is_dataset(value):
        for array in _dataset_arrays(value):
            _freeze_array(array)
        return value
    if isinstance(value, dict):
        for item in value.values():
            freeze(item, _depth + 1)
    elif isinstance(value, (list, tuple)):
        for item in value:
            freeze(item, _depth + 1)
    elif not _freeze_array(value):
        for item in _members(value) or ():
            freeze(item, _depth + 1)
    return value


def _freeze_array(value):
    flags = getattr(value, "flags", None)
    if flags is not None and hasattr(flags, "writeable") and (type(value).__module__ or "").startswith("numpy"):
        try:
            flags.writeable = False
        except (ValueError, AttributeError, TypeError):  # NumPy scalars have read-only flags
            pass
        return True
    return False


# ---------------------------------------------------------------------------
# Codecs


class Codec:
    """Serializer for one kind of value in a disk entry.

    ``write(value, directory, stem)`` stores the value in files named
    ``<stem>.*`` inside ``directory`` and returns JSON metadata (it must list the
    file names under ``"files"``); ``read(directory, meta)`` rebuilds the value.
    ``name`` and ``version`` are recorded; entries of an unknown codec or version
    are treated as misses.
    """

    name = "codec"
    version = 1

    def accepts(self, value):
        raise NotImplementedError

    def write(self, value, directory, stem):
        raise NotImplementedError

    def read(self, directory, meta):
        raise NotImplementedError


def _json_dump(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=True, separators=(",", ":"))


def _json_like(value, _depth=0):
    if _depth > 64:
        return False
    if value is None or isinstance(value, (bool, str, int)):
        return True
    if isinstance(value, float):
        return True
    if isinstance(value, dict):
        return all(isinstance(k, str) and _json_like(v, _depth + 1) for k, v in value.items())
    if isinstance(value, (list, tuple)):
        return all(_json_like(item, _depth + 1) for item in value)
    return False


class JsonCodec(Codec):
    """Small JSON values (``value`` ports); tuples come back as lists, NaN/Infinity are kept."""

    name = "json"

    def accepts(self, value):
        return _json_like(value)

    def write(self, value, directory, stem):
        name = stem + ".json"
        (Path(directory) / name).write_text(_json_dump(value), encoding="utf-8")
        return {"files": [name]}

    def read(self, directory, meta):
        return json.loads((Path(directory) / meta["files"][0]).read_text(encoding="utf-8"))


class BytesCodec(Codec):
    name = "bytes"

    def accepts(self, value):
        return isinstance(value, (bytes, bytearray))

    def write(self, value, directory, stem):
        name = stem + ".bin"
        (Path(directory) / name).write_bytes(bytes(value))
        return {"files": [name], "type": type(value).__name__}

    def read(self, directory, meta):
        data = (Path(directory) / meta["files"][0]).read_bytes()
        return bytearray(data) if meta.get("type") == "bytearray" else data


def _is_ndarray(value):
    return type(value).__module__ == "numpy" and type(value).__name__ in ("ndarray", "memmap")


class NdarrayCodec(Codec):
    """NumPy arrays (``.npy``, never pickled; object arrays are not accepted)."""

    name = "npy"

    def accepts(self, value):
        return _is_ndarray(value) and value.dtype.kind != "O" and not value.dtype.hasobject

    def write(self, value, directory, stem):
        import numpy as np
        name = stem + ".npy"
        np.save(Path(directory) / name, value, allow_pickle=False)
        return {"files": [name]}

    def read(self, directory, meta):
        import numpy as np
        return np.load(Path(directory) / meta["files"][0], allow_pickle=False)


def _plain_attrs(value):
    """JSON-able copy of dataset attrs (arrays -> lists); NaN/Infinity survive (allow_nan)."""
    try:
        return plain_json(value)
    except TypeError:
        return None


class DatasetNpzCodec(Codec):
    """``suan.data.model`` ``ImageData``/``PolyData``/``Table`` as ``.npz`` arrays + JSON metadata.

    Only these exact classes are accepted (a subclass may carry state this codec
    does not know). String columns are stored as NumPy unicode arrays. The
    VTKHDF container (``suan.data.vtkhdf``) can be plugged in as another codec.
    """

    name = "dataset-npz"
    version = 1

    def _classes(self):
        from suan.data.model import ImageData, PolyData, Table
        return {"ImageData": ImageData, "PolyData": PolyData, "Table": Table}

    def accepts(self, value):
        try:
            classes = self._classes()
        except ImportError:  # pragma: no cover - suan.data is part of the package
            return False
        if type(value) not in classes.values():
            return False
        if _plain_attrs(value.attrs) is None:
            return False
        return all(f.values is None or (_is_ndarray(f.values) and (f.values.dtype.kind != "O" or f.dtype == "string"))
                   for f in value.fields.values())

    def write(self, value, directory, stem):
        import numpy as np
        arrays, fields = {}, []
        for index, f in enumerate(value.fields.values()):
            meta = f.to_json()
            for key in ("range", "magnitude_range"):
                if getattr(f, key) is not None:
                    meta[key] = plain_json(getattr(f, key))
            entry = {"descriptor": meta, "array": None}
            if f.values is not None:
                values = f.values
                if values.dtype.kind == "O":
                    values = np.asarray(values.tolist(), dtype=str).reshape(values.shape)
                entry["array"] = f"f{index}"
                entry["object"] = f.values.dtype.kind == "O"
                arrays[f"f{index}"] = np.ascontiguousarray(values)
            fields.append(entry)
        kind = type(value).__name__
        meta = {
            "class": kind, "id": value.id, "label": value.label, "fields": fields,
            "time": value.time.to_json() if value.time is not None else None,
            "frames": [{"ref": hasattr(f, "to_json"), "data": plain_json(f.to_json() if hasattr(f, "to_json") else f)}
                       for f in value.frames],
            "provenance": value.provenance.to_json() if value.provenance is not None else None,
            "attrs": _plain_attrs(value.attrs),
        }
        if kind == "ImageData":
            meta["geometry"] = value.geometry()
        elif kind == "PolyData":
            meta["geometry"] = {"frame": value.frame, "length_unit": value.length_unit,
                                "has_points": value.points is not None}
            if value.points is not None:
                arrays["points"] = value.points
                for name in ("verts", "lines", "polys"):
                    cells = getattr(value, name)
                    arrays[f"{name}_offsets"] = np.asarray(cells.offsets, dtype=np.int64)
                    arrays[f"{name}_connectivity"] = np.asarray(cells.connectivity, dtype=np.int64)
        elif kind == "Table":
            meta["index"] = value.index
        name = stem + ".npz"
        np.savez(Path(directory) / name, **arrays)
        meta_name = stem + ".json"
        (Path(directory) / meta_name).write_text(_json_dump(meta), encoding="utf-8")
        return {"files": [name, meta_name], "class": kind}

    def read(self, directory, meta):
        import numpy as np
        from suan.data.model import CellArray, Field, FrameRef, Provenance, TimeInfo
        directory = Path(directory)
        info = json.loads((directory / meta["files"][1]).read_text(encoding="utf-8"))
        with np.load(directory / meta["files"][0], allow_pickle=False) as data:
            arrays = {key: data[key] for key in data.files}
        classes = self._classes()
        common = {
            "id": info["id"], "label": info.get("label"),
            "time": TimeInfo.from_json(info["time"]) if info.get("time") else None,
            "frames": [FrameRef.from_json(item["data"]) if item["ref"] else item["data"]
                       for item in info.get("frames", ())],
            "provenance": Provenance.from_json(info["provenance"]) if info.get("provenance") else None,
            "attrs": info.get("attrs"),
        }
        kind = info["class"]
        if kind == "ImageData":
            g = info["geometry"]
            dataset = classes["ImageData"](tuple(g["dimensions"]), g["origin"], g["spacing"], g["direction"],
                                           frame=g["frame"], length_unit=g["length_unit"], **common)
        elif kind == "PolyData":
            g = info["geometry"]
            if g.get("has_points"):
                cells = {name: CellArray(arrays[f"{name}_offsets"], arrays[f"{name}_connectivity"])
                         for name in ("verts", "lines", "polys")}
                dataset = classes["PolyData"](arrays["points"], frame=g["frame"], length_unit=g["length_unit"],
                                              **cells, **common)
            else:
                dataset = classes["PolyData"](frame=g["frame"], length_unit=g["length_unit"], **common)
        elif kind == "Table":
            dataset = classes["Table"](index=info.get("index"), **common)
        else:
            raise ValueError(f"Unknown dataset class {kind!r}")
        for entry in info["fields"]:
            values = arrays[entry["array"]] if entry.get("array") else None
            if values is not None and entry.get("object"):
                values = values.astype(object)
            dataset.add(Field.from_json(entry["descriptor"], values=values))
        return dataset


def default_codecs():
    """The built-in codecs, in selection order."""
    return [DatasetNpzCodec(), NdarrayCodec(), BytesCodec(), JsonCodec()]


# ---------------------------------------------------------------------------
# The cache


@dataclass(frozen=True)
class CacheHit:
    """A cache lookup result: ``value`` (a dict of named values), ``notes`` (JSON) and ``tier``."""

    value: object
    notes: object
    tier: str


class GraphCache:
    """Two-tier cache of node results keyed by hex sha256.

    ``root=None`` gives a memory-only cache. Safe to share between threads (one
    lock around the memory tier) and between processes (the disk tier writes
    immutable entries with atomic renames). Stored values are dicts of named
    values (the node's output ports); NumPy arrays inside them are made
    read-only by the evaluator before they are stored.
    """

    def __init__(self, root=None, *, memory_bytes=DEFAULT_MEMORY_BYTES, disk_bytes=DEFAULT_DISK_BYTES, codecs=None):
        self.root = Path(root).expanduser().resolve() if root is not None else None
        self.memory_bytes = int(memory_bytes)
        self.disk_bytes = int(disk_bytes)
        self.codecs = list(codecs) if codecs is not None else default_codecs()
        self._memory = OrderedDict()  # key -> (value, notes, nbytes)
        self._memory_used = 0
        self._lock = threading.RLock()
        self._touched = {}
        self._index_ready = False
        if self.root is not None:
            for sub in ("", "objects", "tmp", "trash"):
                (self.root / sub).mkdir(mode=0o700, parents=True, exist_ok=True)

    def __repr__(self):
        return f"GraphCache(root={str(self.root) if self.root else None!r})"

    # -- lookups ------------------------------------------------------------

    def contains(self, key, *, disk=True):
        """``"memory"``, ``"disk"`` or ``None`` (cheap; does not load the value)."""
        with self._lock:
            if key in self._memory:
                return "memory"
        directory = self._entry_dir(key) if disk else None
        if directory is not None and (directory / "entry.json").is_file():
            return "disk"
        return None

    def get(self, key, *, disk=True):
        """A :class:`CacheHit` or ``None``; a disk hit is promoted to memory."""
        with self._lock:
            item = self._memory.get(key)
            if item is not None:
                self._memory.move_to_end(key)
                return CacheHit(item[0], item[1], "memory")
        if not disk:
            return None
        loaded = self._read_disk(key)
        if loaded is None:
            return None
        value, notes = loaded
        freeze(value)
        self._remember(key, value, notes)
        return CacheHit(value, notes, "disk")

    def notes(self, key, *, disk=True):
        """The notes stored with an entry (choices, warnings) without loading its value, or ``None``."""
        with self._lock:
            item = self._memory.get(key)
            if item is not None:
                return item[1]
        directory = self._entry_dir(key) if disk else None
        if directory is None:
            return None
        try:
            entry = json.loads((directory / "entry.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if entry.get("schema") != ENTRY_SCHEMA or entry.get("key") != key:
            return None
        return entry.get("notes")

    def put(self, key, value, *, notes=None, disk=False, label=None):
        """Store ``value`` (a dict of named values) in memory and, if ``disk``, on disk.

        Returns True if a disk entry exists afterwards. Values no codec accepts
        are kept in memory only.
        """
        if not isinstance(value, dict):
            raise TypeError("Cache values are dicts of named values")
        self._remember(key, value, notes)
        if disk and self.root is not None:
            return self._write_disk(key, value, notes, label)
        return False

    def discard(self, key, *, disk=True):
        with self._lock:
            item = self._memory.pop(key, None)
            if item is not None:
                self._memory_used -= item[2]
        if disk:
            self._remove_disk(key)

    def clear(self, *, disk=False):
        with self._lock:
            self._memory.clear()
            self._memory_used = 0
        if disk and self.root is not None:
            for directory in list((self.root / "objects").glob("*/*")):
                self._remove_disk(directory.name)

    def scratch_dir(self, key):
        """A private directory for large intermediates of the node with this key (``None`` without a root)."""
        if self.root is None or not KEY_RE.match(key or ""):
            return None
        path = self.root / "scratch" / key[:2] / key
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        return path

    def stats(self):
        with self._lock:
            memory = {"entries": len(self._memory), "bytes": self._memory_used, "limit": self.memory_bytes}
        disk = {"entries": 0, "bytes": 0, "limit": self.disk_bytes, "root": str(self.root) if self.root else None}
        if self.root is not None:
            rows = self._index_query("SELECT COUNT(*), COALESCE(SUM(bytes), 0) FROM entries")
            if rows:
                disk["entries"], disk["bytes"] = rows[0]
        return {"memory": memory, "disk": disk}

    # -- memory tier --------------------------------------------------------

    def _remember(self, key, value, notes):
        size = estimate_nbytes(value)
        with self._lock:
            old = self._memory.pop(key, None)
            if old is not None:
                self._memory_used -= old[2]
            if size > self.memory_bytes:
                return
            self._memory[key] = (value, notes, size)
            self._memory_used += size
            while self._memory_used > self.memory_bytes and self._memory:
                _, (_, _, dropped) = self._memory.popitem(last=False)
                self._memory_used -= dropped

    # -- disk tier ----------------------------------------------------------

    def _entry_dir(self, key):
        if self.root is None or not isinstance(key, str) or not KEY_RE.match(key):
            return None
        return self.root / "objects" / key[:2] / key

    def _codec(self, value):
        for codec in self.codecs:
            try:
                if codec.accepts(value):
                    return codec
            except Exception:  # a codec probe must never break evaluation
                continue
        return None

    def _write_disk(self, key, value, notes, label):
        final = self._entry_dir(key)
        if final is None:
            return False
        if (final / "entry.json").is_file():
            self._touch(key, force=True)
            return True
        codecs = {}
        for name, item in value.items():
            codec = self._codec(item)
            if codec is None:
                return False
            codecs[name] = codec
        try:
            notes_text = _json_dump(notes)
        except (TypeError, ValueError):
            return False
        tmp = self.root / "tmp" / uuid.uuid4().hex
        try:
            tmp.mkdir(mode=0o700, parents=True)
            ports = {}
            for index, (name, item) in enumerate(value.items()):
                codec = codecs[name]
                meta = codec.write(item, tmp, f"{index:02d}")
                ports[name] = {"codec": codec.name, "version": codec.version, **meta}
            entry = {"schema": ENTRY_SCHEMA, "key": key, "created": time.time(), "label": label, "ports": ports,
                     "notes": json.loads(notes_text)}
            (tmp / "entry.json").write_text(_json_dump(entry), encoding="utf-8")
            size = sum(path.stat().st_size for path in tmp.iterdir())
            final.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            try:
                os.rename(tmp, final)
            except OSError:
                if not (final / "entry.json").is_file():
                    raise
                return True  # another writer won the race; entries are immutable
        except Exception:
            shutil.rmtree(tmp, ignore_errors=True)
            return False
        finally:
            if tmp.exists():
                shutil.rmtree(tmp, ignore_errors=True)
        now = time.time()
        self._index_exec("INSERT OR REPLACE INTO entries (key, bytes, created, accessed, label) VALUES (?, ?, ?, ?, ?)",
                         (key, size, now, now, label))
        self._touched[key] = time.monotonic()
        self._maybe_prune()
        return True

    def _read_disk(self, key):
        directory = self._entry_dir(key)
        if directory is None:
            return None
        try:
            entry = json.loads((directory / "entry.json").read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, ValueError):
            self._remove_disk(key)
            return None
        if entry.get("schema") != ENTRY_SCHEMA or entry.get("key") != key:
            self._remove_disk(key)
            return None
        codecs = {codec.name: codec for codec in self.codecs}
        value = {}
        for name, meta in (entry.get("ports") or {}).items():
            codec = codecs.get(meta.get("codec"))
            if codec is None or meta.get("version") != codec.version:
                return None  # written by another codec set; leave it for its owner
            try:
                value[name] = codec.read(directory, meta)
            except FileNotFoundError:
                return None  # pruned while reading
            except Exception:
                self._remove_disk(key)
                return None
        self._touch(key)
        return value, entry.get("notes")

    def _remove_disk(self, key):
        directory = self._entry_dir(key)
        if directory is None:
            return
        if directory.exists():
            trash = self.root / "trash" / uuid.uuid4().hex
            try:
                os.rename(directory, trash)
            except OSError:
                trash = directory
            shutil.rmtree(trash, ignore_errors=True)
        self._index_exec("DELETE FROM entries WHERE key = ?", (key,))
        self._touched.pop(key, None)

    def prune(self, max_bytes=None):
        """Remove least-recently-used disk entries until they use at most ``max_bytes`` (default: the budget).

        Returns ``{"removed": n, "freed": bytes}``.
        """
        if self.root is None:
            return {"removed": 0, "freed": 0}
        limit = self.disk_bytes if max_bytes is None else int(max_bytes)
        rows = self._index_query("SELECT key, bytes FROM entries ORDER BY accessed ASC, created ASC") or []
        total = sum(size for _, size in rows)
        removed = freed = 0
        for key, size in rows:
            if total <= limit:
                break
            self._remove_disk(key)
            total -= size
            removed += 1
            freed += size
        return {"removed": removed, "freed": freed}

    def _maybe_prune(self):
        rows = self._index_query("SELECT COALESCE(SUM(bytes), 0) FROM entries")
        if rows and rows[0][0] > self.disk_bytes:
            self.prune(int(self.disk_bytes * _PRUNE_TARGET))

    def _touch(self, key, force=False):
        now = time.monotonic()
        if not force and now - self._touched.get(key, -math.inf) < _TOUCH_INTERVAL:
            return
        self._touched[key] = now
        directory = self._entry_dir(key)
        updated = self._index_exec("UPDATE entries SET accessed = ? WHERE key = ?", (time.time(), key))
        if updated == 0 and directory is not None and directory.is_dir():  # entry without an index row
            size = sum(path.stat().st_size for path in directory.iterdir() if path.is_file())
            self._index_exec("INSERT OR IGNORE INTO entries (key, bytes, created, accessed, label) "
                             "VALUES (?, ?, ?, ?, NULL)", (key, size, time.time(), time.time()))

    def rebuild_index(self):
        """Re-create the SQLite metadata from the entry directories (after the index was lost)."""
        if self.root is None:
            return 0
        count = 0
        for directory in (self.root / "objects").glob("*/*"):
            if KEY_RE.match(directory.name) and (directory / "entry.json").is_file():
                stat = (directory / "entry.json").stat()
                size = sum(path.stat().st_size for path in directory.iterdir() if path.is_file())
                self._index_exec("INSERT OR REPLACE INTO entries (key, bytes, created, accessed, label) "
                                 "VALUES (?, ?, ?, ?, NULL)", (directory.name, size, stat.st_mtime, stat.st_mtime))
                count += 1
        return count

    # -- SQLite metadata (best effort: the entry directories are the truth) --

    def _connect(self):
        path = self.root / "index.sqlite"
        fresh = not path.exists()
        conn = sqlite3.connect(str(path), timeout=30, isolation_level=None)
        if not self._index_ready:
            try:
                conn.execute("PRAGMA journal_mode=WAL")
            except sqlite3.DatabaseError:
                pass
            conn.execute("CREATE TABLE IF NOT EXISTS entries (key TEXT PRIMARY KEY, bytes INTEGER NOT NULL, "
                         "created REAL NOT NULL, accessed REAL NOT NULL, label TEXT)")
            self._index_ready = True
            if fresh:
                try:
                    os.chmod(path, 0o600)
                except OSError:
                    pass
                if any((self.root / "objects").glob("*/*")):
                    conn.close()
                    self.rebuild_index()
                    return sqlite3.connect(str(path), timeout=30, isolation_level=None)
        return conn

    def _index_exec(self, sql, args=()):
        if self.root is None:
            return 0
        try:
            with closing(self._connect()) as conn:
                return conn.execute(sql, args).rowcount
        except sqlite3.Error:
            return 0

    def _index_query(self, sql, args=()):
        if self.root is None:
            return None
        try:
            with closing(self._connect()) as conn:
                return conn.execute(sql, args).fetchall()
        except sqlite3.Error:
            return None
