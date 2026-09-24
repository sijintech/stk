"""STK render payload v2 (``stk.payload/2``): builder, scene encoder, decoder, validator and ``.stkp`` I/O.

See docs/specs/stk-render-payload-v2.md. A payload is a JSON manifest plus
content-addressed little-endian buffers (``uri: "sha256:<hex>"``, or ``"#<k>"``
inside a ``.stkp`` file). Accessors are tightly packed, 8-byte aligned views.
Positions are float32 relative to the float64 ``render_origin`` (or a layer's
own ``origin`` when a layer is far from it). Producers enforce per-profile
budgets (phone/web/desktop), recording every reduction in ``budget.reductions``
and ``source.reduced``.

Main entry points:

* :func:`encode_scene` -- :class:`suan.render.layers.Scene` -> :class:`Payload`, a ``dict``
  ``{"manifest": {...}, "buffers": {sha256 hex: bytes}}`` with helper methods
* :class:`PayloadBuilder` -- low-level manifest/buffer assembly
* :func:`read_stkp`, :func:`read_directory`, :func:`decode` -- decode + validate
* :meth:`Payload.to_stkp`, :meth:`Payload.write_directory`, :meth:`Payload.validate`
"""
from contextlib import contextmanager
from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path
import re
import struct

from .colormaps import ORIENTATION_HSL, canonical_name, lut_rgba8_bytes, opacity_points

__all__ = [
    "ENCODINGS", "MIB", "PROFILES", "SCHEMA", "TYPE_DTYPES", "TYPE_SIZES",
    "Payload", "PayloadBuilder", "PayloadError",
    "budget_limits", "cluster_decimate", "decode", "encode_scene", "pack_stkp", "read_directory", "read_stkp",
    "unpack_stkp",
]

SCHEMA = "stk.payload/2"
MIB = 1024 * 1024
# docs/specs/stk-render-payload-v2.md §7
PROFILES = {
    "phone": {"triangles": 300_000, "instances": 50_000, "points": 200_000, "voxels": 128 ** 3, "bytes": 32 * MIB},
    "web": {"triangles": 2_000_000, "instances": 500_000, "points": 2_000_000, "voxels": 256 ** 3,
            "bytes": 128 * MIB},
    "desktop": {"triangles": 20_000_000, "instances": 5_000_000, "points": 20_000_000, "voxels": 1024 ** 3,
                "bytes": 2048 * MIB},
}
ENCODINGS = {"phone": "u8", "web": "u16", "desktop": "f32"}
TYPE_DTYPES = {"i8": "<i1", "u8": "<u1", "i16": "<i2", "u16": "<u2", "i32": "<i4", "u32": "<u4", "f32": "<f4",
               "f64": "<f8"}
TYPE_SIZES = {name: int(dtype[-1]) for name, dtype in TYPE_DTYPES.items()}
_ID = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.:-]{0,127}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_MAGIC = b"STKP"
_VERSION = 2
UNKNOWN_COLOR = [0.5, 0.5, 0.5]


class PayloadError(ValueError):
    """Invalid payload (decoder validation) or a payload that cannot meet its budget."""

    def __init__(self, message, *, path="", code="invalid_payload"):
        super().__init__(f"{path}: {message}" if path else message)
        self.path = path
        self.code = code


def _np():
    import numpy
    return numpy


def type_of(array):
    """Accessor type name of a NumPy array's dtype."""
    kind, size = array.dtype.kind, array.dtype.itemsize
    name = {"i": "i", "u": "u", "f": "f"}.get(kind)
    if name is None or f"{name}{size * 8}" not in TYPE_DTYPES:
        raise PayloadError(f"Unsupported array dtype {array.dtype}")
    return f"{name}{size * 8}"


def budget_limits(profile="web", overrides=None):
    """Profile limits ``{triangles, instances, points, voxels, bytes}`` with ``overrides`` applied."""
    if profile not in PROFILES:
        raise PayloadError(f"Unknown profile {profile!r}; expected one of {', '.join(PROFILES)}", code="invalid_param")
    limits = dict(PROFILES[profile])
    for key, value in (overrides or {}).items():
        if key not in limits:
            raise PayloadError(f"Unknown budget key {key!r}", code="invalid_param")
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise PayloadError(f"Budget {key!r} must be a non-negative integer", code="invalid_param")
        limits[key] = value
    return limits


# ---------------------------------------------------------------------------
# Builder


class PayloadBuilder:
    """Assemble a manifest and its buffers.

    Accessors added inside ``with builder.buffer("id"):`` share one buffer
    (8-byte aligned, zero padded, as in the spec example); otherwise each
    accessor gets its own buffer, and identical content reuses one buffer.
    """

    def __init__(self, render_origin=(0.0, 0.0, 0.0), length_unit="unspecified"):
        origin = [float(v) for v in render_origin]
        if len(origin) != 3 or not all(math.isfinite(v) for v in origin):
            raise PayloadError("render_origin must be 3 finite numbers")
        self.render_origin = origin
        self.length_unit = length_unit
        self.buffers = []           # (id, bytes)
        self.accessors = []
        self.colormaps = []
        self.layers = []
        self._ids = set()
        self._buffer_ids = set()
        self._group = None
        self._by_digest = {}
        self._colormap_keys = {}

    @contextmanager
    def buffer(self, buffer_id):
        if self._group is not None:
            raise PayloadError("Buffers cannot be nested")
        self._check_buffer_id(buffer_id)
        self._group = [buffer_id, bytearray()]
        try:
            yield buffer_id
        finally:
            group, self._group = self._group, None
            self.buffers.append((group[0], bytes(group[1])))

    def _check_buffer_id(self, buffer_id):
        if not isinstance(buffer_id, str) or not _ID.match(buffer_id) or buffer_id in self._buffer_ids:
            raise PayloadError(f"Invalid or duplicate buffer id {buffer_id!r}")
        self._buffer_ids.add(buffer_id)

    def _new_buffer_id(self):
        index = len(self._buffer_ids)
        while f"b{index}" in self._buffer_ids:
            index += 1
        return f"b{index}"

    def add_accessor(self, accessor_id, array, type=None, components=None, *, normalized=False, hints=True):
        """Append ``array`` (``(count,)`` or ``(count, components)``) and return ``accessor_id``."""
        np = _np()
        if not isinstance(accessor_id, str) or not _ID.match(accessor_id) or accessor_id in self._ids:
            raise PayloadError(f"Invalid or duplicate accessor id {accessor_id!r}")
        array = np.asarray(array)
        type_name = type or type_of(array)
        if type_name not in TYPE_DTYPES:
            raise PayloadError(f"Unknown accessor type {type_name!r}")
        count = int(array.shape[0]) if array.ndim else 1
        components = int(components or (1 if array.ndim <= 1 else math.prod(array.shape[1:])))
        stored = np.ascontiguousarray(array.reshape(count, components).astype(TYPE_DTYPES[type_name], copy=False))
        data = stored.tobytes()
        accessor = {"id": accessor_id, "buffer": None, "byteOffset": 0, "count": count, "type": type_name,
                    "components": components}
        if normalized:
            if type_name[0] == "f":
                raise PayloadError("normalized applies to integer accessors only")
            accessor["normalized"] = True
        if hints and count:
            if type_name[0] == "f":
                finite = np.isfinite(stored).all(axis=1)
                if finite.any():
                    subset = stored if finite.all() else stored[finite]
                    accessor["min"] = [v.item() for v in subset.min(axis=0)]
                    accessor["max"] = [v.item() for v in subset.max(axis=0)]
            else:
                accessor["min"] = [v.item() for v in stored.min(axis=0)]
                accessor["max"] = [v.item() for v in stored.max(axis=0)]
        if self._group is not None:
            buffer_id, blob = self._group
            blob.extend(b"\0" * (-len(blob) % 8))
            accessor["buffer"], accessor["byteOffset"] = buffer_id, len(blob)
            blob.extend(data)
        else:
            digest = hashlib.sha256(data).hexdigest()
            if digest not in self._by_digest:
                buffer_id = self._new_buffer_id()
                self._check_buffer_id(buffer_id)
                self.buffers.append((buffer_id, data))
                self._by_digest[digest] = buffer_id
            accessor["buffer"] = self._by_digest[digest]
        self._ids.add(accessor_id)
        self.accessors.append(accessor)
        return accessor_id

    def add_colormap(self, entry):
        """Add a raw ``colormaps[]`` entry; returns its id."""
        self.colormaps.append(entry)
        return entry["id"]

    def add_lut(self, name, **colors):
        """Register a built-in continuous colormap (deduplicated by name); returns its colormap id."""
        name = canonical_name(name)
        key = ("lut", name, json.dumps(colors, sort_keys=True))
        if key not in self._colormap_keys:
            colormap_id = f"cm{sum(1 for k in self._colormap_keys if k[0] == 'lut')}"
            lut = self.add_accessor(f"lut.{name}" if f"lut.{name}" not in self._ids else f"lut.{colormap_id}",
                                    _np().frombuffer(lut_rgba8_bytes(name), dtype="u1").reshape(256, 4), "u8", 4)
            entry = {"id": colormap_id, "name": name, "categorical": False, "lut": lut, "size": 256}
            entry.update({k: [float(c) for c in v] for k, v in colors.items() if v is not None})
            self.colormaps.append(entry)
            self._colormap_keys[key] = colormap_id
        return self._colormap_keys[key]

    def add_palette(self, name, entries, unknown_color=None):
        """Register a categorical palette (deduplicated by name and entries); returns its colormap id."""
        key = ("pal", name, json.dumps(entries, sort_keys=True))
        if key not in self._colormap_keys:
            colormap_id = f"pal{sum(1 for k in self._colormap_keys if k[0] == 'pal')}"
            self.colormaps.append({"id": colormap_id, "name": name, "categorical": True, "entries": list(entries),
                                   "unknown_color": list(unknown_color or UNKNOWN_COLOR)})
            self._colormap_keys[key] = colormap_id
        return self._colormap_keys[key]

    def add_layer(self, layer):
        self.layers.append(layer)
        return layer["id"]

    def build(self, *, source=None, bounds=None, view=None, stats=None, budget=None, extra=None):
        """The :class:`Payload` (``stats.bytes`` is filled with the total buffer size)."""
        if self._group is not None:
            raise PayloadError("A buffer group is still open")
        manifest = {"schema": SCHEMA}
        if source is not None:
            manifest["source"] = source
        manifest["render_origin"] = list(self.render_origin)
        manifest["length_unit"] = self.length_unit
        if bounds is not None:
            manifest["bounds"] = bounds
        manifest["buffers"] = []
        blobs = {}
        for buffer_id, data in self.buffers:
            digest = hashlib.sha256(data).hexdigest()
            manifest["buffers"].append({"id": buffer_id, "uri": "sha256:" + digest, "sha256": digest,
                                        "byteLength": len(data), "encoding": "raw"})
            blobs[digest] = data
        manifest["accessors"] = self.accessors
        if self.colormaps:
            manifest["colormaps"] = self.colormaps
        manifest["layers"] = self.layers
        if view is not None:
            manifest["view"] = view
        if stats is not None:
            manifest["stats"] = {**stats, "bytes": sum(len(data) for data in blobs.values())}
        if budget is not None:
            manifest["budget"] = budget
        manifest.update(extra or {})
        try:        # a detached, plain-JSON manifest (no shared dicts, no NumPy scalars)
            manifest = json.loads(json.dumps(manifest, allow_nan=False))
        except (TypeError, ValueError) as error:
            raise PayloadError(f"The manifest is not plain JSON: {error}") from None
        return Payload(manifest, blobs)


# ---------------------------------------------------------------------------
# Payload, decoding and validation


class Payload(dict):
    """A manifest plus its buffers: ``{"manifest": {...}, "buffers": {sha256 hex: bytes}}``.

    A ``dict`` (the graph service delivers ``payload["manifest"]`` and pushes
    each ``payload["buffers"][sha]`` to the blob store) with helpers for
    arrays, validation and files. The manifest always references buffers as
    ``"sha256:<hex>"``; ``.stkp`` chunk URIs exist only inside the file.
    ``scene_v1`` (also the key ``"scene_v1"`` when set) holds the optional
    scene v1 downgrade of ``stk.output.payload@1`` ``v1_fallback``.
    """

    def __init__(self, manifest, blobs=None):
        super().__init__(manifest=manifest, buffers=dict(blobs or {}))
        self._arrays = {}

    def __repr__(self):
        layers = [f"{layer.get('id')}:{layer.get('type')}" for layer in self.manifest.get("layers", ())]
        return f"Payload(layers={layers}, bytes={self.nbytes})"

    @property
    def manifest(self):
        return self["manifest"]

    @property
    def blobs(self):
        """sha256 hex -> bytes (the ``"buffers"`` key)."""
        return self["buffers"]

    @property
    def scene_v1(self):
        return self.get("scene_v1")

    @scene_v1.setter
    def scene_v1(self, value):
        if value is None:
            self.pop("scene_v1", None)
        else:
            self["scene_v1"] = value

    @property
    def nbytes(self):
        return sum(len(self.blobs[b["sha256"]]) for b in self.manifest.get("buffers", ()) if b["sha256"] in self.blobs)

    @property
    def layers(self):
        return self.manifest.get("layers", [])

    def layer(self, layer_id):
        try:
            return next(layer for layer in self.layers if layer.get("id") == layer_id)
        except StopIteration:
            raise KeyError(f"No layer {layer_id!r}") from None

    def accessor(self, accessor_id):
        try:
            return next(a for a in self.manifest["accessors"] if a["id"] == accessor_id)
        except StopIteration:
            raise KeyError(f"No accessor {accessor_id!r}") from None

    def colormap(self, colormap_id):
        try:
            return next(c for c in self.manifest.get("colormaps", ()) if c["id"] == colormap_id)
        except StopIteration:
            raise KeyError(f"No colormap {colormap_id!r}") from None

    def buffer_bytes(self, buffer_id):
        buffer = next((b for b in self.manifest["buffers"] if b["id"] == buffer_id), None)
        if buffer is None:
            raise KeyError(f"No buffer {buffer_id!r}")
        try:
            return self.blobs[buffer["sha256"]]
        except KeyError:
            raise PayloadError(f"Missing bytes of buffer {buffer_id!r} (sha256 {buffer['sha256']})") from None

    def array(self, accessor_id):
        """Read-only NumPy view: ``(count,)`` for one component, else ``(count, components)``."""
        if accessor_id not in self._arrays:
            np = _np()
            accessor = self.accessor(accessor_id)
            data = self.buffer_bytes(accessor["buffer"])
            n = accessor["count"] * accessor["components"]
            array = np.frombuffer(data, dtype=TYPE_DTYPES[accessor["type"]], count=n, offset=accessor["byteOffset"])
            components = accessor["components"]
            self._arrays[accessor_id] = array if components == 1 else array.reshape(-1, components)
        return self._arrays[accessor_id]

    def lut(self, colormap_id):
        """``(256, 4)`` uint8 LUT of a continuous colormap."""
        return self.array(self.colormap(colormap_id)["lut"])

    def validate(self):
        """Raise :class:`PayloadError` unless the payload satisfies spec §10; returns ``self``."""
        _Validator(self).run()
        return self

    def to_stkp(self):
        return pack_stkp(self.manifest, self.blobs)

    def write_stkp(self, path):
        path = Path(path)
        path.write_bytes(self.to_stkp())
        return path

    def write_directory(self, directory):
        """Directory form: ``manifest.json`` + ``<sha256>.bin`` per buffer. Returns the manifest path."""
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        for buffer in self.manifest["buffers"]:
            (directory / f"{buffer['sha256']}.bin").write_bytes(bytes(self.blobs[buffer["sha256"]]))
        path = directory / "manifest.json"
        path.write_text(json.dumps(self.manifest, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        return path


def pack_stkp(manifest, blobs):
    """``.stkp`` bytes: ``"STKP"``, u32 2, u64 total; chunks ``[u64 len][4-byte type][u32 0][data padded to 8]``."""
    packed = json.loads(json.dumps(manifest))
    chunks = []
    for index, buffer in enumerate(packed["buffers"], start=1):
        buffer["uri"] = f"#{index}"
        chunks.append((b"BIN ", bytes(blobs[buffer["sha256"]])))
    text = json.dumps(packed, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    body = bytearray()
    for kind, data in [(b"JSON", text)] + chunks:
        body += struct.pack("<Q4sI", len(data), kind, 0) + data
        body += (b" " if kind == b"JSON" else b"\0") * (-len(data) % 8)
    return _MAGIC + struct.pack("<IQ", _VERSION, 16 + len(body)) + bytes(body)


def unpack_stkp(data):
    """``(manifest, blobs)`` of ``.stkp`` bytes; buffer URIs are rewritten to ``"sha256:<hex>"``."""
    view = memoryview(data)
    if len(view) < 16:
        raise PayloadError("Not an .stkp file (too short)")
    magic, version, total = struct.unpack_from("<4sIQ", view, 0)
    if magic != _MAGIC:
        raise PayloadError("Not an .stkp file (bad magic)")
    if version != _VERSION:
        raise PayloadError(f".stkp version {version} is not supported (expected {_VERSION})")
    if total != len(view):
        raise PayloadError(f".stkp length field {total} differs from the file size {len(view)}")
    chunks, offset = [], 16
    while offset < len(view):
        if offset + 16 > len(view):
            raise PayloadError(".stkp chunk header is truncated")
        length, kind, reserved = struct.unpack_from("<Q4sI", view, offset)
        offset += 16
        if reserved != 0:
            raise PayloadError(".stkp chunk reserved field must be 0")
        if offset + length > len(view):
            raise PayloadError(".stkp chunk data is truncated")
        chunks.append((bytes(kind), view[offset:offset + length]))
        offset += length + (-length % 8)
    if offset != len(view):
        raise PayloadError(".stkp padding runs past the end of the file")
    if not chunks or chunks[0][0] != b"JSON":
        raise PayloadError(".stkp chunk 0 must be the JSON manifest")
    if any(kind != b"BIN " for kind, _ in chunks[1:]):
        raise PayloadError(".stkp chunks after the manifest must be 'BIN '")
    try:
        manifest = json.loads(bytes(chunks[0][1]).decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as error:
        raise PayloadError(f".stkp manifest is not valid JSON: {error}") from None
    blobs = {}
    for index, buffer in enumerate(manifest.get("buffers", ())):
        uri = buffer.get("uri", "")
        match = re.fullmatch(r"#([1-9][0-9]*)", uri) if isinstance(uri, str) else None
        if not match or int(match.group(1)) >= len(chunks):
            raise PayloadError(f"Buffer URI {uri!r} does not name a chunk of this file", path=f"/buffers/{index}/uri")
        blob = chunks[int(match.group(1))][1]
        digest = buffer.get("sha256")
        _check_blob(buffer, blob, f"/buffers/{index}")
        buffer["uri"] = "sha256:" + digest
        blobs[digest] = blob
    return manifest, blobs


def read_stkp(source):
    """Decode and validate an ``.stkp`` file (path or bytes)."""
    data = source if isinstance(source, (bytes, bytearray, memoryview)) else Path(source).read_bytes()
    manifest, blobs = unpack_stkp(data)
    return Payload(manifest, blobs).validate()


def read_directory(path):
    """Decode and validate the directory form (``manifest.json`` + ``<sha256>.bin``)."""
    path = Path(path)
    manifest_path = path / "manifest.json" if path.is_dir() else path
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except ValueError as error:
        raise PayloadError(f"{manifest_path.name} is not valid JSON: {error}") from None
    blobs = {}
    for index, buffer in enumerate(manifest.get("buffers", ())):
        digest = buffer.get("sha256")
        if not isinstance(digest, str) or not _SHA.match(digest) or buffer.get("uri") != "sha256:" + digest:
            raise PayloadError("Directory payloads reference buffers as 'sha256:<hex>'", path=f"/buffers/{index}")
        file = manifest_path.parent / f"{digest}.bin"
        if not file.is_file():
            raise PayloadError(f"Missing buffer file {file.name}", path=f"/buffers/{index}")
        blobs[digest] = file.read_bytes()
    return Payload(manifest, blobs).validate()


def decode(manifest, blobs):
    """Validate a manifest against its buffers: ``blobs`` maps sha256 -> bytes, or is ``callable(sha256)``."""
    if callable(blobs):
        blobs = {b["sha256"]: blobs(b["sha256"]) for b in manifest.get("buffers", ()) if isinstance(b, dict)
                 and "sha256" in b}
    return Payload(manifest, blobs).validate()


def _check_blob(buffer, blob, path):
    digest = buffer.get("sha256")
    if not isinstance(digest, str) or not _SHA.match(digest):
        raise PayloadError("sha256 must be 64 lower-case hex digits", path=path + "/sha256")
    if buffer.get("byteLength") != len(blob):
        raise PayloadError(f"byteLength {buffer.get('byteLength')} differs from the data size {len(blob)}",
                           path=path + "/byteLength")
    if hashlib.sha256(blob).hexdigest() != digest:
        raise PayloadError("buffer bytes do not hash to its sha256", path=path + "/sha256")


class _Validator:
    """Decoder validation (spec §10); raises on the first problem with a JSON-pointer path."""

    LAYER_REQUIRED = {
        "triangles": ("positions", "indices"), "slice_image": ("plane", "size", "attributes"),
        "lines": ("positions", "mode", "indices"), "points": ("positions",),
        "instances": ("positions", "directions", "glyph"),
        "volume": ("grid", "data", "value_range", "transfer_function"), "overlay": ("kind",),
    }

    def __init__(self, payload):
        self.payload = payload
        self.m = payload.manifest

    def fail(self, message, path=""):
        raise PayloadError(message, path=path)

    def run(self):
        np = _np()
        m = self.m
        if not isinstance(m, dict):
            self.fail("manifest must be a JSON object")
        if m.get("schema") != SCHEMA:
            self.fail(f"schema must be {SCHEMA!r}, got {m.get('schema')!r}", "/schema")
        for key in ("render_origin", "length_unit", "buffers", "accessors", "layers"):
            if key not in m:
                self.fail(f"missing required key {key!r}", "")
        self.vec3(m["render_origin"], "/render_origin")
        if not isinstance(m["length_unit"], str) or not m["length_unit"]:
            self.fail("length_unit must be a non-empty string", "/length_unit")
        self.buffers = {}
        for i, buffer in enumerate(self.list(m["buffers"], "/buffers")):
            path = f"/buffers/{i}"
            self.unique_id(buffer, self.buffers, path)
            digest = buffer.get("sha256")
            if buffer.get("uri") != f"sha256:{digest}":
                self.fail("in-memory buffers are referenced as 'sha256:<hex>'", path + "/uri")
            if buffer.get("encoding", "raw") != "raw":
                self.fail("encoding must be 'raw'", path + "/encoding")
            if digest not in self.payload.blobs:
                self.fail(f"missing bytes for sha256 {digest}", path)
            _check_blob(buffer, self.payload.blobs[digest], path)
            self.buffers[buffer["id"]] = buffer
        self.accessors = {}
        for i, accessor in enumerate(self.list(m["accessors"], "/accessors")):
            path = f"/accessors/{i}"
            self.unique_id(accessor, self.accessors, path)
            buffer = self.buffers.get(accessor.get("buffer"))
            if buffer is None:
                self.fail(f"unknown buffer {accessor.get('buffer')!r}", path + "/buffer")
            kind = accessor.get("type")
            if kind not in TYPE_DTYPES:
                self.fail(f"unknown type {kind!r}", path + "/type")
            count, components, offset = accessor.get("count"), accessor.get("components"), accessor.get("byteOffset")
            for key, value, low in (("count", count, 0), ("components", components, 1), ("byteOffset", offset, 0)):
                if isinstance(value, bool) or not isinstance(value, int) or value < low:
                    self.fail(f"{key} must be an integer >= {low}", f"{path}/{key}")
            if components > 16:
                self.fail("components must be <= 16", path + "/components")
            if offset % 8:
                self.fail("byteOffset must be a multiple of 8", path + "/byteOffset")
            if offset + count * components * TYPE_SIZES[kind] > buffer["byteLength"]:
                self.fail("accessor runs past the end of its buffer", path)
            if accessor.get("normalized") and kind[0] == "f":
                self.fail("normalized applies to integer types only", path + "/normalized")
            self.accessors[accessor["id"]] = accessor
        self.colormaps = {}
        for i, colormap in enumerate(self.list(m.get("colormaps", []), "/colormaps")):
            path = f"/colormaps/{i}"
            self.unique_id(colormap, self.colormaps, path)
            if colormap.get("categorical"):
                entries = self.list(colormap.get("entries"), path + "/entries")
                values = []
                for j, entry in enumerate(entries):
                    value = entry.get("value") if isinstance(entry, dict) else None
                    if isinstance(value, bool) or not isinstance(value, int):
                        self.fail("category value must be an integer", f"{path}/entries/{j}/value")
                    self.rgb(entry.get("color"), f"{path}/entries/{j}/color")
                    values.append(value)
                if len(values) != len(set(values)):
                    self.fail("category values must be unique", path + "/entries")
            else:
                self.expect(colormap.get("lut"), ("u8",), 4, 256, path + "/lut")
                if colormap.get("size") != 256:
                    self.fail("size must be 256", path + "/size")
            self.colormaps[colormap["id"]] = colormap
        layers = {}
        for i, layer in enumerate(self.list(m["layers"], "/layers")):
            path = f"/layers/{i}"
            self.unique_id(layer, layers, path)
            layers[layer["id"]] = layer
            kind = layer.get("type")
            if kind not in self.LAYER_REQUIRED:
                continue            # clients skip layers of unknown type
            for key in self.LAYER_REQUIRED[kind]:
                if key not in layer:
                    self.fail(f"{kind} layer needs {key!r}", path)
            if "origin" in layer:
                self.vec3(layer["origin"], path + "/origin")
            getattr(self, "layer_" + kind)(layer, path, np)
        if "bounds" in m:
            bounds = m["bounds"]
            if not isinstance(bounds, list) or len(bounds) != 2:
                self.fail("bounds must be [[min], [max]]", "/bounds")
            self.vec3(bounds[0], "/bounds/0")
            self.vec3(bounds[1], "/bounds/1")
        if "view" in m and (not isinstance(m["view"], dict) or m["view"].get("schema") != "stk.view/1"):
            self.fail("view must be an stk.view/1 document", "/view")

    # -- helpers --------------------------------------------------------------

    def list(self, value, path):
        if not isinstance(value, list):
            self.fail("must be a list", path)
        for i, item in enumerate(value):
            if not isinstance(item, dict):
                self.fail("must be an object", f"{path}/{i}")
        return value

    def unique_id(self, item, seen, path):
        value = item.get("id")
        if not isinstance(value, str) or not _ID.match(value):
            self.fail(f"invalid id {value!r}", path + "/id")
        if value in seen:
            self.fail(f"duplicate id {value!r}", path + "/id")

    def vec3(self, value, path):
        if (not isinstance(value, list) or len(value) != 3
                or not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
                           for v in value)):
            self.fail("must be 3 finite numbers", path)

    def rgb(self, value, path):
        if (not isinstance(value, list) or len(value) not in (3, 4)
                or not all(isinstance(v, (int, float)) and not isinstance(v, bool) and 0 <= v <= 1 for v in value)):
            self.fail("colour must be 3 or 4 numbers in [0, 1]", path)

    def expect(self, accessor_id, types, components, count, path):
        accessor = self.accessors.get(accessor_id)
        if accessor is None:
            self.fail(f"unknown accessor {accessor_id!r}", path)
        if types and accessor["type"] not in types:
            self.fail(f"accessor {accessor_id!r} must have type {'/'.join(types)}, not {accessor['type']}", path)
        if components is not None and accessor["components"] != components:
            self.fail(f"accessor {accessor_id!r} must have {components} components", path)
        if count is not None and accessor["count"] != count:
            self.fail(f"accessor {accessor_id!r} has {accessor['count']} elements; expected {count}", path)
        return accessor

    def positions(self, layer, path, np):
        accessor = self.expect(layer["positions"], ("f32",), 3, None, path + "/positions")
        if not np.isfinite(self.payload.array(accessor["id"])).all():
            self.fail("positions must be finite", path + "/positions")
        return accessor["count"]

    def attributes(self, layer, path, counts):
        attributes = layer.get("attributes", {})
        if not isinstance(attributes, dict):
            self.fail("attributes must be an object", path + "/attributes")
        for name, attribute in attributes.items():
            apath = f"{path}/attributes/{name}"
            association = attribute.get("association", "point")
            if association not in counts:
                self.fail(f"association {association!r} is not valid here", apath + "/association")
            self.expect(attribute.get("accessor"), None, None, counts[association], apath + "/accessor")
            palette = attribute.get("palette")
            if palette is not None and not self.colormaps.get(palette, {}).get("categorical"):
                self.fail(f"palette {palette!r} is not a categorical colormap", apath + "/palette")
        return attributes

    def color(self, spec, attributes, path):
        if spec is None:
            return
        by = spec.get("by")
        if by not in ("solid", "attribute", "direction"):
            self.fail(f"unknown colour mode {by!r}", path + "/by")
        if by == "attribute" and spec.get("attribute") not in attributes:
            self.fail(f"unknown attribute {spec.get('attribute')!r}", path + "/attribute")
        colormap = spec.get("colormap")
        if colormap is not None and colormap != ORIENTATION_HSL and colormap not in self.colormaps:
            self.fail(f"unknown colormap {colormap!r}", path + "/colormap")

    def indices(self, accessor_id, n_points, multiple, path, np):
        accessor = self.expect(accessor_id, ("u32", "u16"), 1, None, path)
        if accessor["count"] % multiple:
            self.fail(f"index count must be a multiple of {multiple}", path)
        values = self.payload.array(accessor_id)
        if len(values) and int(values.max()) >= n_points:
            self.fail("index refers to a missing position", path)
        return accessor["count"] // multiple

    # -- layers ---------------------------------------------------------------

    def layer_triangles(self, layer, path, np):
        n = self.positions(layer, path, np)
        n_tri = self.indices(layer["indices"], n, 3, path + "/indices", np)
        if "normals" in layer:
            self.expect(layer["normals"], ("f32",), 3, n, path + "/normals")
        attributes = self.attributes(layer, path, {"point": n, "cell": n_tri})
        self.color((layer.get("appearance") or {}).get("color"), attributes, path + "/appearance/color")
        for j, lod in enumerate(layer.get("lods", [])):
            lpath = f"{path}/lods/{j}"
            count = self.expect(lod.get("positions"), ("f32",), 3, None, lpath + "/positions")["count"]
            cells = self.indices(lod.get("indices"), count, 3, lpath + "/indices", np)
            self.attributes(lod, lpath, {"point": count, "cell": cells})

    def layer_slice_image(self, layer, path, np):
        plane = layer["plane"]
        for key in ("origin", "u", "v"):
            self.vec3(plane.get(key) if isinstance(plane, dict) else None, f"{path}/plane/{key}")
        size = layer["size"]
        if (not isinstance(size, list) or len(size) != 2
                or not all(isinstance(v, int) and not isinstance(v, bool) and v >= 1 for v in size)):
            self.fail("size must be [w, h] positive integers", path + "/size")
        attributes = self.attributes(layer, path, {"point": size[0] * size[1]})
        self.color((layer.get("appearance") or {}).get("color"), attributes, path + "/appearance/color")

    def layer_lines(self, layer, path, np):
        n = self.positions(layer, path, np)
        if layer["mode"] == "segments":
            segments = self.indices(layer["indices"], n, 2, path + "/indices", np)
        elif layer["mode"] == "polylines":
            count = self.indices(layer["indices"], n, 1, path + "/indices", np)
            if "offsets" not in layer:
                self.fail("polylines need offsets", path)
            offsets = self.payload.array(self.expect(layer["offsets"], ("u32",), 1, None, path + "/offsets")["id"])
            steps = np.diff(offsets.astype(np.int64))
            if len(offsets) < 1 or offsets[0] != 0 or offsets[-1] != count or (steps < 0).any():
                self.fail("offsets must rise from 0 to the index count", path + "/offsets")
            segments = int(np.maximum(steps - 1, 0).sum())
        else:
            self.fail(f"unknown lines mode {layer['mode']!r}", path + "/mode")
        attributes = self.attributes(layer, path, {"point": n, "cell": segments})
        self.color((layer.get("appearance") or {}).get("color"), attributes, path + "/appearance/color")

    def layer_points(self, layer, path, np):
        n = self.positions(layer, path, np)
        if "radii" in layer:
            self.expect(layer["radii"], ("f32",), 1, n, path + "/radii")
        attributes = self.attributes(layer, path, {"point": n})
        self.color((layer.get("appearance") or {}).get("color"), attributes, path + "/appearance/color")

    def layer_instances(self, layer, path, np):
        n = self.positions(layer, path, np)
        self.expect(layer["directions"], ("f32",), 3, n, path + "/directions")
        if "scales" in layer:
            self.expect(layer["scales"], ("f32",), 1, n, path + "/scales")
        if layer["glyph"].get("shape") not in ("arrow", "cone", "sphere", "line", "cube"):
            self.fail(f"unknown glyph shape {layer['glyph'].get('shape')!r}", path + "/glyph/shape")
        attributes = self.attributes(layer, path, {"point": n})
        appearance = layer.get("appearance") or {}
        self.color(appearance.get("color"), attributes, path + "/appearance/color")
        scale = appearance.get("scale")
        if scale is not None and scale.get("by") == "attribute" and scale.get("attribute") not in attributes:
            self.fail(f"unknown scale attribute {scale.get('attribute')!r}", path + "/appearance/scale")

    def layer_volume(self, layer, path, np):
        grid = layer["grid"]
        dims = grid.get("dimensions") if isinstance(grid, dict) else None
        if (not isinstance(dims, list) or len(dims) != 3
                or not all(isinstance(v, int) and not isinstance(v, bool) and v >= 1 for v in dims)):
            self.fail("dimensions must be 3 positive integers", path + "/grid/dimensions")
        self.vec3(grid.get("origin"), path + "/grid/origin")
        self.vec3(grid.get("spacing"), path + "/grid/spacing")
        if min(grid["spacing"]) <= 0:
            self.fail("spacing must be positive", path + "/grid/spacing")
        self.expect(layer["data"], ("u8", "u16", "f32"), 1, math.prod(dims), path + "/data")
        tf = layer["transfer_function"]
        if tf.get("colormap") not in self.colormaps:
            self.fail(f"unknown colormap {tf.get('colormap')!r}", path + "/transfer_function/colormap")
        for j, lod in enumerate(layer.get("lods", [])):
            self.expect(lod.get("data"), ("u8", "u16", "f32"), 1, math.prod(lod.get("dimensions") or [0]),
                        f"{path}/lods/{j}/data")

    def layer_overlay(self, layer, path, np):
        kind = layer["kind"]
        if kind not in ("scalar_bar", "legend", "orientation_legend", "text", "axes_triad"):
            self.fail(f"unknown overlay kind {kind!r}", path + "/kind")
        colormap = layer.get("colormap")
        if kind in ("scalar_bar", "legend") and colormap not in self.colormaps:
            self.fail(f"unknown colormap {colormap!r}", path + "/colormap")
        if kind == "scalar_bar" and self.colormaps[colormap].get("categorical"):
            self.fail("a scalar bar needs a continuous colormap", path + "/colormap")
        if kind == "legend" and not self.colormaps[colormap].get("categorical"):
            self.fail("a legend needs a categorical colormap", path + "/colormap")
        if kind == "text" and not isinstance(layer.get("text"), str):
            self.fail("text overlays need 'text'", path + "/text")


# ---------------------------------------------------------------------------
# Budget reductions


def cluster_decimate(positions, triangles, target, *, normals=None, point_attributes=None, cell_attributes=None):
    """Reduce a triangle mesh to at most ``target`` triangles by uniform vertex clustering.

    Vertices in the same cubic cell merge (mean position, renormalized mean
    normal); continuous point attributes are averaged, categorical ones keep
    the first vertex's value; degenerate triangles are dropped and their cell
    attributes with them (labels are never interpolated). Returns
    ``(positions, triangles, normals, point_attributes, cell_attributes)``.
    ``point_attributes``/``cell_attributes`` map names to ``(values, categorical)``.
    """
    np = _np()
    positions = np.asarray(positions, dtype=np.float64)
    triangles = np.asarray(triangles, dtype=np.int64).reshape(-1, 3)
    point_attributes, cell_attributes = dict(point_attributes or {}), dict(cell_attributes or {})
    if len(triangles) <= target:
        return positions, triangles, normals, point_attributes, cell_attributes
    lo = positions.min(axis=0)
    extent = float((positions.max(axis=0) - lo).max()) or 1.0

    def cluster(size):
        cells = np.floor((positions - lo) / size).astype(np.int64)
        dims = cells.max(axis=0) + 1
        keys = (cells[:, 2] * dims[1] + cells[:, 1]) * dims[0] + cells[:, 0]
        _, inverse = np.unique(keys, return_inverse=True)
        tri = inverse.reshape(-1)[triangles]
        keep = (tri[:, 0] != tri[:, 1]) & (tri[:, 1] != tri[:, 2]) & (tri[:, 0] != tri[:, 2])
        return inverse.reshape(-1), tri, keep

    small, large = extent * 1e-7, extent * 2.0
    best = cluster(large)
    for _ in range(40):
        size = math.sqrt(small * large)
        attempt = cluster(size)
        if attempt[2].sum() <= target:
            best, large = attempt, size
        else:
            small = size
        if large / small < 1.02:
            break
    inverse, tri, keep = best
    k = int(inverse.max()) + 1
    counts = np.bincount(inverse, minlength=k).astype(np.float64)
    merged = np.stack([np.bincount(inverse, weights=positions[:, a], minlength=k) for a in range(3)], axis=1)
    merged /= counts[:, None]
    first = np.full(k, len(inverse), dtype=np.int64)
    np.minimum.at(first, inverse, np.arange(len(inverse)))
    new_normals = None
    if normals is not None:
        normals = np.asarray(normals, dtype=np.float64)
        summed = np.stack([np.bincount(inverse, weights=normals[:, a], minlength=k) for a in range(3)], axis=1)
        length = np.linalg.norm(summed, axis=1, keepdims=True)
        new_normals = np.where(length > 0, summed / np.where(length > 0, length, 1.0), normals[first])
    new_points = {}
    for name, (values, categorical) in point_attributes.items():
        values = np.asarray(values)
        if categorical:
            new_points[name] = (values[first], True)
        else:
            flat = values.reshape(len(values), -1).astype(np.float64)
            mean = np.stack([np.bincount(inverse, weights=flat[:, c], minlength=k) for c in range(flat.shape[1])],
                            axis=1) / counts[:, None]
            new_points[name] = (mean.reshape((k,) + values.shape[1:]), False)
    tri = tri[keep]
    used, remap = np.unique(tri, return_inverse=True)
    tri = remap.reshape(-1, 3)
    result_points = {name: (values[used], categorical) for name, (values, categorical) in new_points.items()}
    result_cells = {name: (np.asarray(values)[keep], categorical) for name, (values, categorical)
                    in cell_attributes.items()}
    return (merged[used], tri, None if new_normals is None else new_normals[used], result_points, result_cells)


def _stride_for(dims, target):
    """Smallest integer f >= 1 with prod(ceil(n / f)) <= target."""
    f = 1
    while math.prod(-(-n // f) for n in dims) > max(target, 1):
        f += 1
    return f


# ---------------------------------------------------------------------------
# Scene encoder


def encode_scene(scene, *, profile="web", budget=None, generator="suan.render.payload"):
    """Encode a :class:`suan.render.layers.Scene` as ``stk.payload/2`` within the profile budget.

    ``budget`` overrides individual limits (``{triangles, instances, points,
    voxels, bytes}``). Counts over a limit are reduced (triangles decimated,
    instances/points truncated to a prefix of their shuffled order, volumes and
    slice images strided); when the bytes are still over, the count targets
    shrink and the scene is re-encoded. Raises :class:`PayloadError` (code
    ``budget_exceeded``) if the byte limit cannot be met.

    Returns a :class:`Payload`: ``{"manifest": <stk.payload/2>, "buffers":
    {sha256 hex: bytes}}`` whose manifest URIs are ``"sha256:<hex>"`` of those keys.
    """
    limits = budget_limits(profile, budget)
    targets = {"triangles": limits["triangles"], "instances": limits["instances"], "points": limits["points"],
               "voxels": limits["voxels"], "texels": limits["voxels"]}
    for _ in range(8):
        payload = _Encoder(scene, profile, limits, targets, generator).run()
        stats = payload.manifest["stats"]
        if stats["bytes"] <= limits["bytes"]:
            return payload
        ratio = limits["bytes"] / stats["bytes"] * 0.9
        usage = {"triangles": stats["triangles"], "instances": stats["instances"], "points": stats["points"],
                 "voxels": stats["voxels"], "texels": stats["texels"]}
        shrunk = {key: max(1, int(min(targets[key], usage[key]) * ratio)) if usage[key] else targets[key]
                  for key in targets}
        if shrunk == targets:
            break
        targets = shrunk
    raise PayloadError(f"The scene needs {payload.manifest['stats']['bytes']} bytes, over the {profile} budget of "
                       f"{limits['bytes']} bytes; reduce the data (sample, crop) or use a larger profile",
                       code="budget_exceeded")


_CATEGORY = {"triangles": "triangles", "instances": "instances", "points": "points", "volume": "voxels",
             "slice_image": "texels"}


class _Encoder:
    def __init__(self, scene, profile, limits, targets, generator):
        self.scene = scene
        self.profile = profile
        self.limits = limits
        self.targets = targets
        self.generator = generator
        self.origin = [float(v) for v in scene.render_origin]
        self.builder = PayloadBuilder(self.origin, scene.length_unit or "unspecified")
        self.reductions = []
        self.stats = {"triangles": 0, "instances": 0, "points": 0, "line_segments": 0, "voxels": 0, "texels": 0}
        self.bounds = []
        self.allocation = self._allocate()

    def _allocate(self):
        totals = {}
        for layer in self.scene.layers:
            category = _CATEGORY.get(layer.type)
            if category:
                totals[category] = totals.get(category, 0) + layer.count()
        allocation = {}
        for layer in self.scene.layers:
            category = _CATEGORY.get(layer.type)
            if category:
                count, total, limit = layer.count(), totals[category], self.targets[category]
                allocation[layer.id] = count if total <= limit else max(1, count * limit // total)
        return allocation

    def reduce(self, layer, reason, before, after):
        self.reductions.append({"layer": layer.id, "reason": reason, "from": int(before), "to": int(after)})

    def run(self):
        layers = []
        for layer in self.scene.layers:
            layers.append(getattr(self, "layer_" + layer.type)(layer))
        for entry in layers:
            self.builder.add_layer(entry)
        rel = [[[b[0][a] - self.origin[a] for a in range(3)], [b[1][a] - self.origin[a] for a in range(3)]]
               for b in self.bounds]
        bounds = None
        if rel:
            bounds = [[min(b[0][a] for b in rel) for a in range(3)], [max(b[1][a] for b in rel) for a in range(3)]]
        source = {}
        if self.scene.time:
            source["time"] = {"step": self.scene.time.get("step"), "time": self.scene.time.get("time")}
        source.update(profile=self.profile, reduced=bool(self.reductions), generator=self.generator)
        view = dict(self.scene.view or {"schema": "stk.view/1"})
        view.setdefault("schema", "stk.view/1")
        budget = {"profile": self.profile, "limits": dict(self.limits), "reductions": self.reductions}
        return self.builder.build(source=source, bounds=bounds, view=view, stats=dict(self.stats), budget=budget)

    # -- shared ---------------------------------------------------------------

    def common(self, layer):
        entry = {"id": layer.id, "type": layer.type, "node": layer.node}
        if layer.name is not None:
            entry["name"] = layer.name
        if not layer.visible:
            entry["visible"] = False
        return entry

    def layer_origin(self, layer, entry):
        """The origin positions are relative to (a layer's own when far from ``render_origin``)."""
        bounds = layer.bounds()
        if bounds is None:
            return self.origin
        self.bounds.append(bounds)
        centre = [(lo + hi) / 2 for lo, hi in zip(*bounds)]
        extent = max(hi - lo for lo, hi in zip(*bounds))
        far = max(abs(c - o) for c, o in zip(centre, self.origin))
        if far > 1e3 * max(extent, 1e-300):
            entry["origin"] = centre
            return centre
        return self.origin

    def relative(self, positions, origin, path):
        np = _np()
        rel = (np.asarray(positions, dtype=np.float64).reshape(-1, 3) - np.asarray(origin)).astype(np.float32)
        if not np.isfinite(rel).all():
            raise PayloadError("positions must be finite", path=path)
        return rel

    def attributes(self, layer, attributes, counts):
        """Encode attributes; returns the manifest ``attributes`` object."""
        np = _np()
        result = {}
        for index, (name, attribute) in enumerate(attributes.items()):
            association = attribute.association if attribute.association in counts else "point"
            values = np.asarray(attribute.values)
            if len(values) != counts[association]:
                raise PayloadError(f"attribute {name!r} has {len(values)} values; expected {counts[association]}",
                                   path=f"/layers/{layer.id}/attributes")
            entry = {"accessor": None, "association": association}
            if attribute.categorical:
                ints = values.astype(np.int64)
                kind = "i16" if len(ints) == 0 or (ints.min() >= -32768 and ints.max() <= 32767) else "i32"
                entry["accessor"] = self.builder.add_accessor(f"{layer.id}.a{index}", ints, kind)
                entry["categorical"] = True
                entry["palette"] = self.builder.add_palette(attribute.palette or "stk:categorical", attribute.entries())
            else:
                entry["accessor"] = self.builder.add_accessor(f"{layer.id}.a{index}", values.astype(np.float32), "f32")
                value_range = attribute.finite_range()
                if value_range is not None:
                    entry["range"] = value_range
            for key in ("unit", "quantity"):
                if getattr(attribute, key):
                    entry[key] = getattr(attribute, key)
            if attribute.component_names:
                entry["component_names"] = list(attribute.component_names)
            result[name] = entry
        return result

    def color_info(self, layer):
        try:
            return layer.color_info()
        except (KeyError, ValueError) as error:
            message = error.args[0] if isinstance(error, KeyError) and error.args else str(error)
            raise PayloadError(f"Layer {layer.id!r}: {message}", code="invalid_param") from None

    def color(self, layer, attributes):
        """Payload colour spec of a layer (registers LUTs/palettes)."""
        info = self.color_info(layer)
        if info["by"] == "solid":
            return {"by": "solid", "solid": info["solid"]}
        if info["by"] == "direction":
            spec = {"by": "direction", "colormap": ORIENTATION_HSL, "max_magnitude": info["max_magnitude"],
                    "lightness_range": info["lightness_range"]}
            if info.get("attribute") is not None:
                spec["attribute"] = info["attribute"]
            return spec
        name = info["attribute"]
        if info["categorical"]:
            return {"by": "attribute", "attribute": name, "colormap": self.builder.add_palette(info["palette"],
                                                                                              info["entries"]),
                    "interpolate": "nearest"}
        spec = {"by": "attribute", "attribute": name, "colormap": self.builder.add_lut(info["colormap"]),
                "range": info["range"], "interpolate": "linear"}
        if info.get("component") is not None and layer.attributes[name].components > 1:
            spec["component"] = info["component"]
        return spec

    # -- layer types ----------------------------------------------------------

    def layer_triangles(self, layer):
        np = _np()
        g, entry = layer.geometry, self.common(layer)
        origin = self.layer_origin(layer, entry)
        positions = np.asarray(g["positions"], dtype=np.float64).reshape(-1, 3)
        triangles = np.asarray(g["indices"], dtype=np.int64).reshape(-1, 3)
        normals = g.get("normals")
        attributes = dict(layer.attributes)
        target = self.allocation.get(layer.id, len(triangles))
        if len(triangles) > target:
            points = {k: (a.values, a.categorical) for k, a in attributes.items() if a.association == "point"}
            cells = {k: (a.values, a.categorical) for k, a in attributes.items() if a.association == "cell"}
            positions, new, normals, points, cells = cluster_decimate(positions, triangles, target, normals=normals,
                                                                      point_attributes=points, cell_attributes=cells)
            if len(new) == 0:
                raise PayloadError(f"Layer {layer.id!r} cannot be decimated to {target} triangles without vanishing",
                                   code="budget_exceeded")
            self.reduce(layer, "triangles over budget: vertex-clustering decimation", len(triangles), len(new))
            triangles = new
            attributes = {k: _replace_values(a, (points if a.association == "point" else cells)[k][0])
                          for k, a in attributes.items()}
            layer = layer.copy(attributes=attributes)
        entry["positions"] = self.builder.add_accessor(f"{layer.id}.positions", self.relative(positions, origin,
                                                       f"/layers/{layer.id}"), "f32", 3)
        if normals is not None:
            normals = np.asarray(normals, dtype=np.float64).reshape(-1, 3)
            length = np.linalg.norm(normals, axis=1, keepdims=True)
            normals = np.where(length > 0, normals / np.where(length > 0, length, 1.0), 0.0)
            entry["normals"] = self.builder.add_accessor(f"{layer.id}.normals", normals.astype(np.float32), "f32", 3)
        entry["indices"] = self.builder.add_accessor(f"{layer.id}.indices", triangles.reshape(-1).astype(np.uint32),
                                                     "u32", 1)
        entry["attributes"] = self.attributes(layer, attributes, {"point": len(positions), "cell": len(triangles)})
        a = layer.appearance
        entry["appearance"] = {"color": self.color(layer, entry["attributes"]),
                               "opacity": float(a.get("opacity", 1.0)), "shading": a.get("shading", "smooth"),
                               "lighting": bool(a.get("lighting", True))}
        if a.get("edges"):
            entry["appearance"]["edges"] = {"visible": True, "color": [0.0, 0.0, 0.0], "width_px": 1.0}
        self.stats["triangles"] += len(triangles)
        return entry

    def layer_slice_image(self, layer):
        np = _np()
        g, entry = layer.geometry, self.common(layer)
        origin = self.layer_origin(layer, entry)
        w, h = (int(v) for v in g["size"])
        plane = {k: np.asarray(g["plane"][k], dtype=np.float64) for k in ("origin", "u", "v")}
        attributes = dict(layer.attributes)
        target = self.allocation.get(layer.id, w * h)
        if w * h > target:
            f = _stride_for((w, h), target)
            nw, nh = -(-w // f), -(-h // f)
            if w > 1:
                plane["u"] = plane["u"] * ((nw - 1) * f / (w - 1))
            if h > 1:
                plane["v"] = plane["v"] * ((nh - 1) * f / (h - 1))

            def strided(attribute):
                values = np.asarray(attribute.values)
                tail = values.shape[1:]
                return _replace_values(attribute, values.reshape((h, w) + tail)[::f, ::f].reshape((-1,) + tail))

            attributes = {k: strided(a) for k, a in attributes.items()}
            self.reduce(layer, f"texels over budget: stride {f}", w * h, nw * nh)
            w, h = nw, nh
            layer = layer.copy(attributes=attributes)
        entry["plane"] = {"origin": (plane["origin"] - np.asarray(origin)).tolist(), "u": plane["u"].tolist(),
                          "v": plane["v"].tolist()}
        entry["size"] = [w, h]
        entry["attributes"] = self.attributes(layer, attributes, {"point": w * h})
        a = layer.appearance
        entry["appearance"] = {"color": self.color(layer, entry["attributes"]),
                               "opacity": float(a.get("opacity", 1.0)), "lighting": False}
        self.stats["texels"] += w * h
        return entry

    def layer_lines(self, layer):
        np = _np()
        g, entry = layer.geometry, self.common(layer)
        origin = self.layer_origin(layer, entry)
        positions = np.asarray(g["positions"], dtype=np.float64).reshape(-1, 3)
        segments = np.asarray(g["indices"], dtype=np.int64).reshape(-1, 2)
        entry["positions"] = self.builder.add_accessor(f"{layer.id}.positions", self.relative(positions, origin,
                                                       f"/layers/{layer.id}"), "f32", 3)
        entry["mode"] = "segments"
        entry["indices"] = self.builder.add_accessor(f"{layer.id}.indices", segments.reshape(-1).astype(np.uint32),
                                                     "u32", 1)
        entry["attributes"] = self.attributes(layer, layer.attributes, {"point": len(positions), "cell": len(segments)})
        if not entry["attributes"]:
            del entry["attributes"]
        a = layer.appearance
        entry["appearance"] = {"color": self.color(layer, entry.get("attributes", {})),
                               "opacity": float(a.get("opacity", 1.0)), "width_px": float(a.get("width_px", 1.0)),
                               "lighting": False}
        self.stats["line_segments"] += len(segments)
        return entry

    def _prefix(self, layer, n):
        target = self.allocation.get(layer.id, n)
        if n <= target:
            return layer, n
        self.reduce(layer, f"{layer.type} over budget: prefix of the shuffled order", n, target)
        geometry = {k: (v[:target] if k in ("positions", "directions", "scales", "radii") and v is not None else v)
                    for k, v in layer.geometry.items()}
        attributes = {k: a.take(slice(0, target)) for k, a in layer.attributes.items()}
        return layer.copy(geometry=geometry, attributes=attributes, stats={}), target

    def layer_points(self, layer):
        np = _np()
        layer, n = self._prefix(layer, len(layer.geometry["positions"]))
        g, entry = layer.geometry, self.common(layer)
        origin = self.layer_origin(layer, entry)
        entry["positions"] = self.builder.add_accessor(f"{layer.id}.positions", self.relative(g["positions"], origin,
                                                       f"/layers/{layer.id}"), "f32", 3)
        if g.get("radii") is not None:
            entry["radii"] = self.builder.add_accessor(f"{layer.id}.radii", np.asarray(g["radii"], dtype=np.float32),
                                                       "f32", 1)
        entry["attributes"] = self.attributes(layer, layer.attributes, {"point": n})
        a = layer.appearance
        entry["appearance"] = {"color": self.color(layer, entry["attributes"]),
                               "opacity": float(a.get("opacity", 1.0)), "render_as": a.get("render_as", "points"),
                               "size_px": float(a.get("size_px", 3.0))}
        if a.get("radius") is not None:
            entry["appearance"]["radius"] = float(a["radius"])
        if layer.props.get("progressive"):
            entry["progressive"] = dict(layer.props["progressive"])
        self.stats["points"] += n
        return entry

    def layer_instances(self, layer):
        np = _np()
        layer, n = self._prefix(layer, len(layer.geometry["positions"]))
        g, entry = layer.geometry, self.common(layer)
        origin = self.layer_origin(layer, entry)
        directions = np.asarray(g["directions"], dtype=np.float64).reshape(-1, 3)
        entry["positions"] = self.builder.add_accessor(f"{layer.id}.positions", self.relative(g["positions"], origin,
                                                       f"/layers/{layer.id}"), "f32", 3)
        entry["directions"] = self.builder.add_accessor(f"{layer.id}.directions", directions.astype(np.float32),
                                                        "f32", 3)
        if g.get("scales") is not None:
            entry["scales"] = self.builder.add_accessor(f"{layer.id}.scales", np.asarray(g["scales"], dtype=np.float32),
                                                        "f32", 1)
        entry["attributes"] = self.attributes(layer, layer.attributes, {"point": n})
        a = layer.appearance
        entry["glyph"] = {"shape": a.get("shape", "arrow"), "resolution": int(a.get("resolution", 8)),
                          "center": bool(a.get("center", True))}
        entry["appearance"] = {"color": self.color(layer, entry["attributes"]),
                               "opacity": float(a.get("opacity", 1.0)), "scale": glyph_scale(layer),
                               "lighting": True}
        if layer.props.get("progressive"):
            entry["progressive"] = dict(layer.props["progressive"])
        self.stats["instances"] += n
        return entry

    def layer_volume(self, layer):
        np = _np()
        g, entry = layer.geometry, self.common(layer)
        origin = self.layer_origin(layer, entry)
        grid = dict(g["grid"])
        data = np.asarray(g["data"])
        dims = [int(n) for n in grid["dimensions"]]
        target = self.allocation.get(layer.id, math.prod(dims))
        if math.prod(dims) > target:
            f = _stride_for(dims, target)
            data = data[::f, ::f, ::f]
            new_dims = [int(data.shape[2]), int(data.shape[1]), int(data.shape[0])]
            self.reduce(layer, f"voxels over budget: stride {f}", math.prod(dims), math.prod(new_dims))
            grid["spacing"] = [float(s) * f for s in grid["spacing"]]
            dims = new_dims
        info = self.color_info(layer)
        categorical = info["categorical"]
        encoding = g.get("encoding") or "auto"
        if encoding == "auto":
            encoding = ENCODINGS[self.profile]
        values = data.reshape(-1)
        finite = values[np.isfinite(values)] if values.dtype.kind == "f" else values
        lo, hi = (float(finite.min()), float(finite.max())) if len(finite) else (0.0, 0.0)
        scale, offset = 1.0, 0.0
        if categorical:
            span = hi - lo
            kind = "u8" if span <= 255 else ("u16" if span <= 65535 else "f32")
            if kind == "f32":
                stored = values.astype(np.float32)
            else:
                stored = (values.astype(np.int64) - int(lo)).astype(np.uint8 if kind == "u8" else np.uint16)
                offset = lo
        elif encoding in ("u8", "u16"):
            kind = encoding
            top = 255 if kind == "u8" else 65535
            scale = (hi - lo) / top if hi > lo else 1.0
            with np.errstate(invalid="ignore"):
                quantized = np.clip(np.rint((values.astype(np.float64) - lo) / scale), 0, top)
            stored = np.nan_to_num(quantized, nan=0.0).astype(np.uint8 if kind == "u8" else np.uint16)
            offset = lo
            if values.dtype.kind == "f" or hi - lo > top:
                self.reductions.append({"layer": layer.id, "reason": f"volume quantized to {kind}"})
        else:
            kind = "f32"
            stored = values.astype(np.float32)
        entry["grid"] = {"dimensions": dims, "origin": (np.asarray(grid["origin"], dtype=np.float64)
                                                         - np.asarray(origin)).tolist(),
                         "spacing": [float(s) for s in grid["spacing"]],
                         "direction": [float(v) for v in grid.get("direction") or (1, 0, 0, 0, 1, 0, 0, 0, 1)]}
        entry["data"] = self.builder.add_accessor(f"{layer.id}.data", stored, kind, 1)
        entry["value_scale"] = scale
        entry["value_offset"] = offset
        entry["value_range"] = [lo, hi]
        for key in ("unit", "quantity"):
            if g.get(key):
                entry[key] = g[key]
        a = layer.appearance
        if categorical:
            colormap = self.builder.add_palette(info["palette"], info["entries"])
            value_range = [lo, hi]
        else:
            colormap = self.builder.add_lut(info["colormap"])
            value_range = info["range"]
        entry["transfer_function"] = {"colormap": colormap, "range": value_range,
                                      "opacity": opacity_points(a.get("opacity") or [[0.0, 0.0], [1.0, 0.8]],
                                                                value_range)}
        entry["sampling"] = "nearest" if categorical else a.get("sampling", "linear")
        entry["shade"] = bool(a.get("shade", False))
        self.stats["voxels"] += math.prod(dims)
        return entry

    def layer_overlay(self, layer):
        entry = self.common(layer)
        props = dict(layer.props)
        a = {**props, **{k: v for k, v in layer.appearance.items() if v is not None}}
        kind = props.pop("kind")
        entry["kind"] = kind
        for key in ("anchor", "offset_px", "title", "source_layer"):
            if a.get(key) is not None:
                entry[key] = a[key]
        size = a.get("size_px")
        if size is not None:
            size = [size, size] if isinstance(size, (int, float)) else size
            entry["size_px"] = [float(v) for v in size]
        if kind == "scalar_bar":
            entry["colormap"] = self.builder.add_lut(props["colormap"])
            entry["range"] = [float(v) for v in props["range"]]
            if props.get("unit") is not None:
                entry["unit"] = props["unit"]
            entry["orientation"] = a.get("orientation", "vertical")
            entry["label_count"] = int(a.get("label_count", 5))
            entry["format"] = a.get("format", ".3g")
        elif kind == "legend":
            entry["colormap"] = self.builder.add_palette(props.get("palette") or "stk:categorical", props["entries"])
            entry["values"] = [int(v) for v in props["values"]]
            entry["columns"] = int(a.get("columns", 1))
        elif kind == "orientation_legend":
            entry["colormap"] = ORIENTATION_HSL
            entry["lightness_range"] = [float(v) for v in a.get("lightness_range") or (0.0, 1.0)]
        elif kind == "text":
            entry["text"] = str(a.get("text", ""))
            entry["font_size_px"] = float(a.get("font_size_px", 14))
            entry["color"] = [float(c) for c in a.get("color") or (0.1, 0.1, 0.1)]
        elif kind == "axes_triad":
            entry["labels"] = [str(v) for v in a.get("labels") or ("x", "y", "z")]
        return entry


def _replace_values(attribute, values):
    return replace(attribute, values=values)


def glyph_scale(layer):
    """Payload ``appearance.scale`` of an instances layer, resolving ``factor: "auto"``.

    ``auto`` = 0.8 x sample spacing / max|v| (``magnitude``), 0.8 x sample spacing
    (``uniform``) or 0.8 x sample spacing / max|field| (``field``); without a
    sample spacing, 0.05 x the bounds diagonal replaces 0.8 x sample spacing.
    """
    np = _np()
    spec = dict(layer.appearance.get("scale") or {"by": "magnitude", "factor": "auto"})
    by = spec.get("by", "magnitude")
    result = {"by": "attribute" if by == "field" else by}
    if by == "field":
        name = spec.get("field") or next(iter(layer.attributes), None)
        if name not in layer.attributes:
            raise PayloadError(f"Layer {layer.id!r} has no attribute {name!r} to scale by", code="invalid_param")
        result["attribute"] = name
        reference = np.abs(layer.attributes[name].scalar())
    elif by == "magnitude":
        reference = np.linalg.norm(np.asarray(layer.geometry["directions"], dtype=np.float64).reshape(-1, 3), axis=1)
    else:
        reference = None
    factor = spec.get("factor", "auto")
    if factor == "auto":
        spacing = layer.props.get("sample_spacing")
        if spacing:
            length = 0.8 * float(spacing)
        else:
            bounds = layer.bounds()
            diagonal = math.dist(bounds[0], bounds[1]) if bounds else 0.0
            length = 0.05 * diagonal if diagonal > 0 else 1.0
        peak = 0.0
        if reference is not None:
            finite = reference[np.isfinite(reference)]
            peak = float(finite.max()) if len(finite) else 0.0
        factor = length / peak if reference is not None and peak > 0 else length
    result["factor"] = float(factor)
    return result
