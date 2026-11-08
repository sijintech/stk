"""Metadata-only discovery of MuPRO HDF5 fields in a caller-owned stream (task CL-MUPRO-H5-DISCOVERY-03).

Internal API for root's FileSource/connector/workflow adapters; nothing is
registered here and no dataset naming is defined. :func:`_discover_hdf5_stream`
lists the ``/tNNNNNNNN/<field>`` datasets of an already content-verified,
anonymous ordinary file (the caller owns it and it is never closed here):

* only two levels are enumerated: root links named ``t`` + eight ASCII digits
  (step groups), then links inside them whose names follow the reader's
  selector grammar (an ASCII letter, then at most 63 ASCII letters, digits or
  ``_``). Other names at either level are ignored *without resolving them*;
* every visited link, ignored or not, counts toward ``max_entries``; a group's
  link count is checked against the remaining budget before its names are
  iterated, so an unbounded listing is never materialized;
* a recognized name must be a hard link to the right kind of object (group /
  dataset), and a recognized field must pass the reader's own dataset checks
  (numeric dtype, ``(nx, ny, nz, nc)`` positive shape, no VDS or external raw
  storage, built-in filters only, allocated storage). Any failure raises
  :class:`~suan.connectors.api.ConnectorError` instead of dropping the entry;
* only HDF5 metadata is read: no dataset values, ``read_direct`` or NumPy
  array allocation. The listing therefore says nothing about whether the
  values are complete or the solver finished (allocated fill values stay
  undetectable, as in the reader);
* the stream's fstat and native change time (POSIX ``st_ctime_ns``, Windows
  ``FILE_BASIC_INFO.ChangeTime``) are compared before and after the metadata
  read, each within the same API; the stream position is restored.

Each entry is ``{"selector", "step", "name", "shape": [nx, ny, nz, nc],
"dtype"}`` with ``dtype`` the native-byte-order NumPy name, sorted by step
then name. Error codes: ``invalid_param`` (arguments), ``budget_exceeded``,
``invalid_data`` (structure, damaged or changed file), ``unavailable`` (h5py
or NumPy missing); a ``check`` callback's own exception propagates unchanged.
Messages never contain a file path or file content. h5py and NumPy are
imported only when the function is called.
"""
from numbers import Integral
import os
import re
import stat as _stat

from ..api import ConnectorError

__all__ = ["DEFAULT_MAX_ENTRIES"]

DEFAULT_MAX_ENTRIES = 4096
_STEP = re.compile(r"t([0-9]{8})", re.ASCII)
_FIELD = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,63}", re.ASCII)
_H5_ERRORS = (OSError, ValueError, TypeError, KeyError, RuntimeError)


def _guard(function, *args):
    """Run one h5py metadata call; library failures become a sanitized ``invalid_data``."""
    try:
        return function(*args)
    except ConnectorError:
        raise
    except _H5_ERRORS:
        raise ConnectorError("The HDF5 file is damaged or uses unsupported metadata", "invalid_data") from None


class _Budget:
    def __init__(self, limit):
        self.limit, self.used = limit, 0

    def reserve(self, count):
        if self.used + count > self.limit:
            raise ConnectorError(f"The HDF5 file lists more than max_entries={self.limit} links to inspect",
                                 "budget_exceeded")
        self.used += count


def _names(group, budget, check):
    """The link names of ``group``, after reserving its whole link count in the budget."""
    count = _guard(len, group)
    budget.reserve(count)
    names = []
    iterator = _guard(iter, group)
    while True:
        if check is not None:
            check()
        try:
            name = next(iterator)
        except StopIteration:
            break
        except ConnectorError:
            raise
        except _H5_ERRORS:
            raise ConnectorError("The HDF5 file is damaged or uses unsupported metadata", "invalid_data") from None
        names.append(name)
        if len(names) > count:  # the group changed under the iteration
            raise ConnectorError("The HDF5 file changed while it was listed", "invalid_data")
    return names


def _discover_hdf5_stream(stream, *, max_entries=DEFAULT_MAX_ENTRIES, check=None):
    """List the valid MuPRO HDF5 fields of ``stream`` from metadata only; see the module docstring."""
    if isinstance(max_entries, bool) or not isinstance(max_entries, Integral) or max_entries < 1:
        raise ConnectorError("max_entries must be a positive integer", "invalid_param")
    if check is not None and not callable(check):
        raise ConnectorError("check must be callable or None", "invalid_param")
    try:
        descriptor = stream.fileno()
        position = stream.tell()
    except (AttributeError, OSError, ValueError):
        raise ConnectorError("stream must be an open, seekable ordinary file", "invalid_param") from None
    from .hdf5 import _change_time, _check_dataset, _hard_member, _modules, _same_file
    h5py, _ = _modules()
    opened = os.fstat(descriptor)
    if not _stat.S_ISREG(opened.st_mode):
        raise ConnectorError("The HDF5 stream is not a regular file", "invalid_data")
    changed = _change_time(descriptor)
    budget = _Budget(int(max_entries))
    entries = []
    try:
        try:
            handle = h5py.File(stream, "r")
        except _H5_ERRORS:
            raise ConnectorError("The file is not a readable HDF5 file", "invalid_data") from None
        with handle:
            for group_name in _names(handle, budget, check):
                match = _STEP.fullmatch(group_name) if isinstance(group_name, str) else None
                if match is None:
                    continue
                group = _guard(_hard_member, h5py, handle, group_name, h5py.Group, "invalid_data",
                               f"step group /{group_name}")
                step = int(match.group(1))
                for field_name in _names(group, budget, check):
                    if not isinstance(field_name, str) or _FIELD.fullmatch(field_name) is None:
                        continue
                    what = f"field /{group_name}/{field_name}"
                    dataset = _guard(_hard_member, h5py, group, field_name, h5py.Dataset, "invalid_data", what)
                    shape, _chunk_bytes = _guard(_check_dataset, h5py, dataset)
                    dtype = _guard(lambda: dataset.dtype.newbyteorder("=").name)
                    entries.append({"selector": f"/{group_name}/{field_name}", "step": step, "name": field_name,
                                    "shape": [int(n) for n in shape], "dtype": dtype})
        after = os.fstat(descriptor)
        changed_after = _change_time(descriptor)
        if changed_after != changed or not _same_file(opened, after):
            raise ConnectorError("The HDF5 file changed while it was listed", "invalid_data")
    finally:
        try:
            stream.seek(position)
        except (OSError, ValueError):
            pass
    entries.sort(key=lambda entry: (entry["step"], entry["name"]))
    return entries
