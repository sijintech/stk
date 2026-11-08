"""Reader for one MuPRO HDF5 field frame (docs/specs/mupro-hdf5-1.md).

The explicit graph source and FileSource adapter use provenance reader id
``mupro.hdf5@1``. Automatic MuFerro run discovery and verification remain
separate; this reader does not determine solver completion.

A MuPRO HDF5 frame is the dataset ``/tNNNNNNNN/<name>`` of shape
``(nx, ny, nz, nc)`` with x slowest. :func:`read_hdf5_image` reads one such
dataset into a :class:`suan.data.model.ImageData` with the frozen layout
``(nz, ny, nx, nc)`` C-contiguous:

* the selector is explicit (no "latest", no search); the step comes from it;
* values and their dtype are kept (``float64 float32 int* uint*``; big-endian
  data is only converted to native byte order). NaN and other values are never
  replaced, and native float32 is not flagged ``lossy``;
* geometry is the grid frame in ``grid_index`` units (origin 0, spacing 1),
  field units ``unspecified`` and physical time unknown. Component meaning
  follows the public muFerro mapping (``stem_field``) only when the stem and
  component count both match it; 6 components stay ``tensor: "array"``;
* ``region`` (inclusive point indices ``((i0, i1), (j0, j1), (k0, k1))``,
  clipped, ``None`` = open end) and ``stride`` ``(sx, sy, sz)`` are read as an
  HDF5 hyperslab; the result equals ``crop_sample`` of the full frame;
* the estimated allocation is checked against ``max_bytes`` before reading:
  the hyperslab buffer plus the transposed copy (twice the selected bytes),
  plus one chunk for chunked layouts (doubled when filtered: stored and
  decoded copy). HDF5 metadata and its chunk cache are not counted;
* fields with no written storage, or chunked fields with unallocated chunks,
  are refused instead of returning fill values (a contiguous field that was
  only partly written, or chunks allocated early with fill values, cannot be
  told apart from data and are not detected). Only built-in filters are
  accepted, so no filter plugin is loaded.

The file is opened read-only once, without following a symbolic link or
reparse point in its last component, must be a regular file, and HDF5 reads go
through that open descriptor (never by path again). After the read, the
descriptor's fstat is compared with its fstat at open and the path's lstat
with its lstat before open (device, inode, size, mtime), and the descriptor's
change time is compared with its change time at open: POSIX
``st_ctime_ns`` of fstat, Windows ``FILE_BASIC_INFO.ChangeTime`` of the pinned
HANDLE (``GetFileInformationByHandleEx``; Windows ``st_ctime`` is the creation
time and is never used). The path's lstat ctime is also compared on POSIX. So
a replacement or an in-place rewrite with a restored mtime is refused; a
change time that cannot be read fails closed. Soft and external HDF5
links, virtual (VDS) datasets and datasets with external raw storage are
refused before any data is read, so the reader never opens another path.
Parent directories are trusted as given by the caller (bindings keep paths
inside their root, see ``suan.connectors.files``).

Errors are :class:`~suan.connectors.api.ConnectorError` with stable codes:
``invalid_param`` (selector, region, stride, max_bytes), ``missing_file``,
``invalid_path`` (a link), ``frame_not_found`` / ``not_found`` (missing step
group / field), ``invalid_data`` (structure, dtype, corrupt or changed file,
refused links or storage), ``budget_exceeded`` and ``unavailable`` (h5py or
NumPy missing). Messages never echo the file path or file contents.

h5py and NumPy are imported only inside :func:`read_hdf5_image`; importing
this module reads no file and starts nothing.
"""
from numbers import Integral
import os
import re
import stat as _stat

from ..api import ConnectorError

__all__ = ["DEFAULT_MAX_BYTES", "READER", "read_hdf5_image"]

READER = "mupro.hdf5@1"
DEFAULT_MAX_BYTES = 256 * 1024 * 1024
_SELECTOR = re.compile(r"/t([0-9]{8})/([A-Za-z][A-Za-z0-9_]{0,63})", re.ASCII)  # used with fullmatch only
_DTYPES = ("float64", "float32", "int64", "int32", "int16", "int8", "uint64", "uint32", "uint16", "uint8")
_REPARSE = 0x400  # FILE_ATTRIBUTE_REPARSE_POINT
# HDF5 built-in filters plus h5py's bundled LZF: deflate, shuffle, fletcher32, szip, nbit, scaleoffset, lzf.
# Anything else would make HDF5 load a plugin library (HDF5_PLUGIN_PATH) while reading.
_BUILTIN_FILTERS = frozenset({1, 2, 3, 4, 5, 6, 32000})


def _modules():
    try:
        import h5py
        import numpy
    except ImportError:
        raise ConnectorError("Reading MuPRO HDF5 needs h5py and NumPy", "unavailable") from None
    return h5py, numpy


def _parse_selector(selector):
    match = _SELECTOR.fullmatch(selector) if isinstance(selector, str) else None
    if match is None:
        raise ConnectorError("selector must be '/tNNNNNNNN/<field>' (8-digit step, field name of letters, digits "
                             "and '_')", "invalid_param")
    return f"t{match.group(1)}", int(match.group(1)), match.group(2)


def _index(value, what):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise ConnectorError(f"{what} must be an integer or None", "invalid_param")
    return int(value)


def _check_region(region):
    if region is None:
        return None
    try:
        pairs = [tuple(pair) for pair in region]
    except TypeError:
        raise ConnectorError("region must be three (lo, hi) pairs", "invalid_param") from None
    if len(pairs) != 3 or any(len(pair) != 2 for pair in pairs):
        raise ConnectorError("region must be three (lo, hi) pairs", "invalid_param")
    return [(_index(lo, "region bound"), _index(hi, "region bound")) for lo, hi in pairs]


def _check_stride(stride):
    if stride is None:
        return (1, 1, 1)
    try:
        steps = tuple(stride)
    except TypeError:
        raise ConnectorError("stride must be three integers >= 1", "invalid_param") from None
    if len(steps) != 3 or any(isinstance(s, bool) or not isinstance(s, Integral) or s < 1 for s in steps):
        raise ConnectorError("stride must be three integers >= 1", "invalid_param")
    return tuple(int(s) for s in steps)


def _window(region, dims):
    """``crop_sample``'s clipping: ``None`` ends are open, bounds are clamped, an empty range is an error."""
    window = []
    for (lo, hi), n in zip(region or [(None, None)] * 3, dims):
        lo = 0 if lo is None else max(0, lo)
        hi = n - 1 if hi is None else min(n - 1, hi)
        if lo > hi:
            raise ConnectorError(f"Empty region {region!r} for dimensions {tuple(dims)}", "invalid_param")
        window.append((lo, hi))
    return window


_WINDOWS = os.name == "nt"


def _same_file(a, b, *, ctime=False):
    """Same device, inode, size and mtime. With ``ctime`` (POSIX only, and only for two results of the same
    API: lstat/lstat) also the status-change time; on Windows ``st_ctime`` is the creation time and is never
    used, the pinned handle's change time comes from :func:`_change_time` instead."""
    same = (a.st_dev, a.st_ino, a.st_size, a.st_mtime_ns) == (b.st_dev, b.st_ino, b.st_size, b.st_mtime_ns)
    return same and (not ctime or _WINDOWS or a.st_ctime_ns == b.st_ctime_ns)


def _windows_change_time(descriptor):
    """``FILE_BASIC_INFO.ChangeTime`` of the HANDLE behind ``descriptor`` (GetFileInformationByHandleEx)."""
    import ctypes
    from ctypes import wintypes
    import msvcrt

    class FileBasicInfo(ctypes.Structure):
        _fields_ = [("CreationTime", ctypes.c_int64), ("LastAccessTime", ctypes.c_int64),
                    ("LastWriteTime", ctypes.c_int64), ("ChangeTime", ctypes.c_int64),
                    ("FileAttributes", wintypes.DWORD)]

    query = ctypes.WinDLL("kernel32", use_last_error=True).GetFileInformationByHandleEx
    query.argtypes = (wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD)
    query.restype = wintypes.BOOL
    handle = msvcrt.get_osfhandle(descriptor)
    info = FileBasicInfo()
    if not query(handle, 0, ctypes.byref(info), ctypes.sizeof(info)):  # 0 = FileBasicInfo
        raise OSError(ctypes.get_last_error(), "GetFileInformationByHandleEx failed")
    return int(info.ChangeTime)


def _change_time(descriptor):
    """Last data or metadata change of the open file: POSIX ``fstat().st_ctime_ns``; Windows the HANDLE's
    ``FILE_BASIC_INFO.ChangeTime``. Any failure is fail-closed (``invalid_data``)."""
    try:
        return _windows_change_time(descriptor) if _WINDOWS else os.fstat(descriptor).st_ctime_ns
    except (OSError, AttributeError, ValueError):
        raise ConnectorError("The HDF5 file's change time cannot be verified", "invalid_data") from None


def _is_link(info):
    return _stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & _REPARSE)


def _open_pinned(path):
    """Open ``path`` read-only without following a final link.

    Returns ``(file, lstat, fstat, change_time)`` of a regular file; ``change_time`` is :func:`_change_time`
    of the pinned descriptor at open."""
    from ..files import MissingFile, PathNotAllowed
    try:
        before = os.lstat(path)
    except FileNotFoundError:
        raise MissingFile("The HDF5 file does not exist") from None
    except OSError:
        raise ConnectorError("The HDF5 file cannot be inspected", "invalid_data") from None
    if _is_link(before):
        raise PathNotAllowed("The HDF5 path is a symbolic link or reparse point; links are not followed")
    if not _stat.S_ISREG(before.st_mode):
        raise ConnectorError("The HDF5 path is not a regular file", "invalid_data")
    flags = (os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0)
             | getattr(os, "O_BINARY", 0) | getattr(os, "O_CLOEXEC", 0))
    try:
        descriptor = os.open(path, flags)
    except FileNotFoundError:
        raise MissingFile("The HDF5 file does not exist") from None
    except OSError:
        raise ConnectorError("The HDF5 file cannot be opened as a regular file", "invalid_data") from None
    try:
        opened = os.fstat(descriptor)
        if not _stat.S_ISREG(opened.st_mode) or not _same_file(before, opened):
            raise ConnectorError("The HDF5 file changed while it was opened", "invalid_data")
        if getattr(os, "O_NONBLOCK", 0):
            import fcntl
            fcntl.fcntl(descriptor, fcntl.F_SETFL, fcntl.fcntl(descriptor, fcntl.F_GETFL) & ~os.O_NONBLOCK)
        changed = _change_time(descriptor)
        return os.fdopen(descriptor, "rb"), before, opened, changed
    except BaseException:
        os.close(descriptor)
        raise


def _hard_member(h5py, group, name, kind, code, what):
    """``group[name]`` only through a hard link to an object of class ``kind`` (never resolving other links)."""
    link = group.get(name, getlink=True)
    if link is None:
        raise ConnectorError(f"The HDF5 file has no {what}", code)
    if not isinstance(link, h5py.HardLink):
        raise ConnectorError(f"The HDF5 {what} is a soft or external link; only hard links are read",
                             "invalid_data")
    member = group[name]
    if not isinstance(member, kind):
        raise ConnectorError(f"The HDF5 {what} has the wrong object type", "invalid_data")
    return member


def _check_dataset(h5py, dataset):
    if dataset.is_virtual:
        raise ConnectorError("Virtual (VDS) HDF5 datasets are not read", "invalid_data")
    if dataset.external:
        raise ConnectorError("HDF5 datasets with external raw storage are not read", "invalid_data")
    dtype = dataset.dtype
    if (dtype.names is not None or dtype.subdtype is not None or dtype.kind not in "fiu"
            or h5py.check_enum_dtype(dtype) is not None or dtype.name not in _DTYPES):
        raise ConnectorError(f"MuPRO HDF5 fields must be numeric ({', '.join(_DTYPES)}); got {dtype}",
                             "invalid_data")
    shape = tuple(int(n) for n in dataset.shape)
    if len(shape) != 4 or min(shape) < 1:
        raise ConnectorError(f"MuPRO HDF5 fields must be (nx, ny, nz, nc) with positive sizes; got {shape}",
                             "invalid_data")
    plist = dataset.id.get_create_plist()
    filters = [plist.get_filter(i)[0] for i in range(plist.get_nfilters())]
    if any(f not in _BUILTIN_FILTERS for f in filters):
        raise ConnectorError("The HDF5 field uses a filter that is not built in; plugin filters are not loaded",
                             "invalid_data")
    if dataset.id.get_storage_size() == 0:
        raise ConnectorError("The HDF5 field has no written data (only fill values)", "invalid_data")
    chunk_bytes = 0
    if dataset.chunks is not None:
        chunks = tuple(int(n) for n in dataset.chunks)
        expected = 1
        for n, c in zip(shape, chunks):
            expected *= -(-n // c)
        if dataset.id.get_num_chunks() < expected:
            raise ConnectorError("The HDF5 field is only partly written (unallocated chunks read as fill values)",
                                 "invalid_data")
        chunk_bytes = chunks[0] * chunks[1] * chunks[2] * chunks[3] * dataset.dtype.itemsize
        if filters:
            chunk_bytes *= 2  # the stored (filtered) chunk and its decoded copy
    return shape, chunk_bytes


def _read_hyperslab(dataset, destination, selection):
    dataset.read_direct(destination, source_sel=selection)


def _field_meta(name, components):
    """Published muFerro stem metadata for a known stem with the expected count; else generic, never guessed."""
    from suan.mupro.run import COMPONENTS
    from . import stem_field
    entry = stem_field(name) if name == "Polar" or name in COMPONENTS else None
    if entry is None or entry["components"] != components:
        return {"tensor": "scalar" if components == 1 else "array", "unit": "unspecified"}
    meta = {"tensor": entry["tensor"], "unit": "unspecified"}
    for key in ("component_names", "quantity"):
        if key in entry:
            meta[key] = tuple(entry[key]) if key == "component_names" else entry[key]
    return meta


def _read_options(selector, region, stride, max_bytes):
    group_name, step, field_name = _parse_selector(selector)
    wanted = _check_region(region)
    steps = _check_stride(stride)
    if isinstance(max_bytes, bool) or not isinstance(max_bytes, Integral) or max_bytes < 1:
        raise ConnectorError("max_bytes must be a positive integer", "invalid_param")
    return group_name, step, field_name, wanted, steps


def _read_open(stream, options, max_bytes, h5py, np, *, opened=None, changed=None):
    """Read a caller-owned ordinary stream, without resolving a filename or closing the stream."""
    from suan.data.model import ImageData, Provenance, TimeInfo
    group_name, step, field_name, wanted, steps = options
    opened = os.fstat(stream.fileno()) if opened is None else opened
    if not _stat.S_ISREG(opened.st_mode):
        raise ConnectorError("The HDF5 stream is not a regular file", "invalid_data")
    changed = _change_time(stream.fileno()) if changed is None else changed
    try:
        handle = h5py.File(stream, "r")
    except (OSError, ValueError):
        raise ConnectorError("The file is not a readable HDF5 file", "invalid_data") from None
    with handle:
        try:
            group = _hard_member(h5py, handle, group_name, h5py.Group, "frame_not_found",
                                 f"step group /{group_name}")
            dataset = _hard_member(h5py, group, field_name, h5py.Dataset, "not_found",
                                   f"field /{group_name}/{field_name}")
            (nx, ny, nz, nc), chunk_bytes = _check_dataset(h5py, dataset)
            window = _window(wanted, (nx, ny, nz))
            sizes = tuple(len(range(lo, hi + 1, s)) for (lo, hi), s in zip(window, steps))
            dtype = dataset.dtype.newbyteorder("=")
            selected = sizes[0] * sizes[1] * sizes[2] * nc * dtype.itemsize
            estimate = 2 * selected + chunk_bytes
            if estimate > max_bytes:
                raise ConnectorError(f"Reading {sizes} x {nc} {dtype.name} needs about {estimate} bytes "
                                     f"(buffer, transposed copy and one decoded chunk); max_bytes is "
                                     f"{max_bytes}", "budget_exceeded")
            buffer = np.empty((*sizes, nc), dtype=dtype)
            selection = tuple(slice(lo, hi + 1, s) for (lo, hi), s in zip(window, steps)) + (slice(None),)
            _read_hyperslab(dataset, buffer, selection)
        except ConnectorError:
            raise
        except (OSError, ValueError, TypeError, KeyError, RuntimeError):
            raise ConnectorError("The HDF5 file is damaged or uses unsupported storage", "invalid_data") \
                from None
    after = os.fstat(stream.fileno())
    changed_after = _change_time(stream.fileno())
    if changed_after != changed or not _same_file(opened, after):
        raise ConnectorError("The HDF5 file changed while it was read", "invalid_data")
    values = np.ascontiguousarray(buffer.transpose(2, 1, 0, 3))
    del buffer
    origin = tuple(float(lo) for lo, _ in window)
    image = ImageData(sizes, origin, tuple(float(s) for s in steps), frame="grid", length_unit="grid_index",
                      id=field_name, time=TimeInfo(step=step),
                      provenance=Provenance(agent={"reader": READER}))
    image.add_field(field_name, values, **_field_meta(field_name, nc))
    return image


def _read_hdf5_stream(stream, selector, *, region=None, stride=None, max_bytes=DEFAULT_MAX_BYTES):
    """Internal FileSource adapter entry: caller owns the anonymous, verified temporary file."""
    options = _read_options(selector, region, stride, max_bytes)
    h5py, np = _modules()
    return _read_open(stream, options, max_bytes, h5py, np)


def read_hdf5_image(path, selector, *, region=None, stride=None, max_bytes=DEFAULT_MAX_BYTES):
    """Read one explicit MuPRO HDF5 field from a pinned local ordinary file. See module rules."""
    options = _read_options(selector, region, stride, max_bytes)
    try:
        path = os.fspath(path)
    except TypeError:
        raise ConnectorError("path must be a file system path", "invalid_param") from None
    if not isinstance(path, str) or not path or "\x00" in path:
        raise ConnectorError("path must be a non-empty text path", "invalid_param")
    h5py, np = _modules()
    stream, before, opened, changed = _open_pinned(path)
    with stream:
        image = _read_open(stream, options, max_bytes, h5py, np, opened=opened, changed=changed)
    try:
        current = os.lstat(path)
    except OSError:
        current = None
    if current is None or _is_link(current) or not _same_file(before, current, ctime=True):
        raise ConnectorError("The HDF5 file changed while it was read", "invalid_data")
    return image
