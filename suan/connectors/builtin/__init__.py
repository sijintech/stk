"""Built-in connectors for plain field files, and the shared single-file readers.

* ``stk.numpy`` (:mod:`.numpy`): ``.npy`` arrays ``(x, y, z[, c])`` and MuPRO field DATs;
* ``stk.vtk`` (:mod:`.vtk`): ``.vti``, legacy ``.vtk`` STRUCTURED_POINTS and VTKHDF.

:func:`read_file` is what ``stk.source.file@1`` uses: it reads one file of a
binding by format (``auto`` = by extension, VTKHDF recognized by its
``/VTKHDF`` group) into an in-memory dataset. Region/stride hints follow the
``DatasetHandle`` contract (crop then sample, point fields only).
"""
from pathlib import PurePosixPath
import re

from ..api import ConnectorError

__all__ = ["FORMATS", "READERS", "FileHandle", "SingleFileConnector", "crop_sample", "detect_format", "field_stats",
           "read_file", "select_frame"]

FORMATS = ("dat", "npy", "vti", "vtk", "vtkhdf")
EXTENSIONS = {".dat": "dat", ".npy": "npy", ".vti": "vti", ".vtk": "vtk", ".vtkhdf": "vtkhdf", ".hdf": "vtkhdf",
              ".h5": "vtkhdf", ".hdf5": "vtkhdf"}
READERS = {"dat": "mupro.dat@1", "npy": "stk.npy@1", "vti": "vtk.vti@1", "vtk": "vtk.legacy@1",
           "vtkhdf": "stk.vtkhdf@1"}


def _np():
    import numpy
    return numpy


def detect_format(path, format="auto"):
    """The reader format of ``path`` (``dat npy vti vtk vtkhdf``); ``ConnectorError('unsupported')`` if unknown."""
    if format != "auto":
        if format not in FORMATS:
            raise ConnectorError(f"Unknown file format {format!r}; known: {', '.join(FORMATS)}", "unsupported")
        return format
    suffix = PurePosixPath(path).suffix.lower()
    if suffix not in EXTENSIONS:
        raise ConnectorError(f"Cannot tell the format of {path!r} from its extension; set 'format'", "unsupported")
    return EXTENSIONS[suffix]


def dataset_id(path):
    """A dataset id from a file name (``Polar.00001000.dat`` -> ``Polar``)."""
    stem = PurePosixPath(path).name.split(".")[0]
    stem = re.sub(r"[^A-Za-z0-9_]", "_", stem)[:128]
    return stem or "dataset"


def _npy_image(local, name):
    from suan.data.model import ImageData
    np = _np()
    data = np.load(local, allow_pickle=False, mmap_mode=None)
    if data.ndim == 3:
        data = data[..., None]
    if data.ndim != 4 or min(data.shape) < 1 or data.dtype.kind not in "fiu" or data.dtype.name == "float16":
        raise ConnectorError("NPY fields must be numeric (x, y, z[, c]) arrays", "invalid_data")
    nx, ny, nz, _ = data.shape
    image = ImageData((nx, ny, nz), length_unit="grid_index", id=name)
    image.add_field(name, data, layout="xyzc")
    return image


def read_file(source, path, *, format="auto", fields=None, association="auto", check=None):
    """Read one field file of a :class:`~suan.connectors.api.FileSource` into an STK dataset.

    DAT and NPY give an image in ``grid_index`` units (DAT indices); VTI/VTK go
    through VTK (``STK_*`` annotations honoured); VTKHDF through h5py. Units
    stay ``unspecified`` unless the file says otherwise.
    """
    from ..files import materialize
    kind = detect_format(path, format)
    local = materialize(source, path)
    name = dataset_id(path)
    if kind == "dat":
        from suan.data.dat import DatError, read_dat_image
        try:
            dataset = read_dat_image(local, check=check)
        except DatError as exc:
            raise ConnectorError(str(exc), "invalid_data") from None
    elif kind == "npy":
        dataset = _npy_image(local, name)
    elif kind == "vtkhdf":
        from suan.data.vtkhdf import is_vtkhdf, read_vtkhdf
        if not is_vtkhdf(local):
            raise ConnectorError(f"{path} is not a VTKHDF file (no /VTKHDF group)", "unsupported")
        dataset = read_vtkhdf(local, fields=fields)
    else:
        from .vtk import read_vtk_image
        dataset = read_vtk_image(local, kind, fields=fields, id=name)
    if fields is not None:
        missing = [f for f in fields if f not in dataset.fields]
        if missing:
            raise ConnectorError(f"{path} has no field(s) {', '.join(missing)}; fields: "
                                 f"{', '.join(dataset.fields) or 'none'}", "invalid_param")
        for name in list(dataset.fields):
            if name not in fields:
                del dataset.fields[name]
    if association in ("point", "cell"):
        for name in [n for n, f in dataset.fields.items() if f.association != association]:
            del dataset.fields[name]
        if not dataset.fields:
            raise ConnectorError(f"{path} has no {association} fields", "invalid_param")
    return dataset


def crop_sample(image, region=None, stride=None):
    """Crop to inclusive point ranges, then keep every stride-th point (point fields only).

    Equals ``stk.filter.crop`` then ``stk.filter.sample``: the origin moves to
    the first kept point and the spacing is multiplied by the stride.
    """
    from suan.data.model import ImageData
    np = _np()
    if region is None and stride is None:
        return image
    dims = image.dimensions
    window = []
    for (lo, hi), n in zip(region or [(0, n - 1) for n in dims], dims):
        lo = 0 if lo is None else max(0, int(lo))
        hi = n - 1 if hi is None else min(n - 1, int(hi))
        if lo > hi:
            raise ConnectorError(f"Empty region {region!r} for dimensions {dims}", "invalid_param")
        window.append((lo, hi))
    steps = tuple(int(s) for s in (stride or (1, 1, 1)))
    if len(steps) != 3 or min(steps) < 1:
        raise ConnectorError("stride must be three integers >= 1", "invalid_param")
    if any(f.association == "cell" for f in image.fields.values()):
        raise ConnectorError("Region/stride reads support point fields only", "unsupported")
    sizes = tuple(len(range(lo, hi + 1, s)) for (lo, hi), s in zip(window, steps))
    result = ImageData(sizes, image.point(window[0][0], window[1][0], window[2][0]),
                       tuple(d * s for d, s in zip(image.spacing, steps)), image.direction, frame=image.frame,
                       length_unit=image.length_unit, id=image.id, time=image.time, frames=image.frames,
                       provenance=image.provenance, attrs=image.attrs, label=image.label)
    selection = tuple(slice(lo, hi + 1, s) for (lo, hi), s in reversed(list(zip(window, steps))))
    for field in image.fields.values():
        result.add(field.with_values(np.ascontiguousarray(field.values[selection])))
    return result


def field_stats(dataset, name):
    """Per-component ``{min, max, mean, count, nan_count}`` (+ ``magnitude`` for 2+ components)."""
    np = _np()
    field = dataset.field(name)
    values = np.asarray(field.values, dtype=np.float64).reshape(-1, field.components)
    finite = np.isfinite(values)

    def summary(column, ok):
        good = column[ok]
        return {"min": float(good.min()) if good.size else None, "max": float(good.max()) if good.size else None,
                "mean": float(good.mean()) if good.size else None, "count": int(good.size),
                "nan_count": int(column.size - good.size)}
    result = {"field": name, "frame": {"step": dataset.time.step if dataset.time else None},
              "components": [summary(values[:, c], finite[:, c]) for c in range(field.components)],
              "magnitude": None, "unit": field.unit}
    if field.components > 1:
        magnitude = np.sqrt((values * values).sum(axis=1))
        result["magnitude"] = summary(magnitude, np.isfinite(magnitude))
    return result


def select_frame(frames, selector):
    """The frame (dict with ``step``) chosen by an ref-1 frame selector.

    ``None`` or ``{"latest": true}`` -> the last frame; ``{"first": true}``;
    ``{"index": i}`` (negative from the end); ``{"step": N, "policy":
    "latest_at_or_before" | "exact"}``. ``ConnectorError(code="frame_not_found")``.
    """
    ordered = sorted(frames, key=lambda f: (f.get("step") is None, f.get("step")))
    if not ordered:
        raise ConnectorError("The dataset has no frames yet", "frame_not_found")
    selector = dict(selector or {"latest": True})
    if selector.get("latest"):
        return ordered[-1]
    if selector.get("first"):
        return ordered[0]
    if "index" in selector:
        index = int(selector["index"])
        if not -len(ordered) <= index < len(ordered):
            raise ConnectorError(f"Frame index {index} is outside 0..{len(ordered) - 1}", "frame_not_found")
        return ordered[index]
    if "step" in selector:
        step = int(selector["step"])
        policy = selector.get("policy", "latest_at_or_before")
        if policy not in ("latest_at_or_before", "exact"):
            raise ConnectorError(f"Unknown frame policy {policy!r}", "invalid_param")
        exact = [f for f in ordered if f.get("step") == step]
        if exact:
            return exact[0]
        earlier = [f for f in ordered if f.get("step") is not None and f["step"] <= step]
        if policy == "exact" or not earlier:
            steps = [f.get("step") for f in ordered]
            raise ConnectorError(f"No frame at step {step} (policy {policy}); steps: {steps[:20]}", "frame_not_found")
        return earlier[-1]
    raise ConnectorError(f"Unknown frame selector {selector!r}", "invalid_param")


class FileHandle:
    """``DatasetHandle`` of one plain file (datasets without frames; ``frame`` is ignored)."""

    def __init__(self, source, path, format, descriptor):
        self.source, self.path, self.format, self.descriptor = source, path, format, descriptor
        self._stats = {}

    def read(self, *, frame=None, fields=None, region=None, stride=None):
        if self.format == "vtkhdf" and (region is not None or stride is not None):
            from suan.data.vtkhdf import read_vtkhdf
            from ..files import materialize
            return read_vtkhdf(materialize(self.source, self.path), fields=fields, region=region, stride=stride)
        dataset = read_file(self.source, self.path, format=self.format, fields=fields)
        if dataset.kind == "image":
            return crop_sample(dataset, region, stride)
        if region is not None or stride is not None:
            raise ConnectorError("Region/stride reads apply to images only", "unsupported")
        return dataset

    def stats(self, *, frame=None, field):
        if field not in self._stats:
            self._stats[field] = field_stats(self.read(fields=[field]), field)
        return self._stats[field]


class SingleFileConnector:
    """Base of the built-in connectors: every supported file of a source is one dataset."""

    id = None
    version = "0.1.0"
    api = 1
    formats = ()
    reads = ("image",)

    def info(self):
        return {"id": self.id, "version": self.version, "api": self.api, "apps": [], "priority": 0,
                "license": "MIT",
                "capabilities": {"read": list(self.reads), "inputs": None, "verify": None, "monitor_adapter": False,
                                 "task_spec": False, "default_graphs": [], "formats": list(self.formats)},
                "runs_on": {"describe": "node|desktop", "read": "node|desktop", "inputs": None,
                            "monitor_adapter": None}}

    def _files(self, run):
        found = []
        for item in run.list(""):
            suffix = PurePosixPath(item.path).suffix.lower()
            if EXTENSIONS.get(suffix) in self.formats:
                found.append(item)
        return found

    def sniff(self, run):
        from ..api import Match
        files = self._files(run)
        if not files:
            return None
        return Match(self.id, 0.3, None, f"{len(files)} {'/'.join(self.formats)} file(s)")

    def describe_file(self, run, item):
        """stk.dataset/1 descriptor of one file (headers only); subclasses override."""
        raise NotImplementedError

    def describe(self, run, *, live=False):
        from suan.data.manifest import file_entry, result_manifest
        datasets, files, ids = [], [], set()
        for item in self._files(run):
            descriptor = self.describe_file(run, item)
            base, n = descriptor["id"], 2
            while descriptor["id"] in ids:
                descriptor["id"] = f"{base[:120]}_{n}"
                n += 1
            ids.add(descriptor["id"])
            known = getattr(run, "known_sha256", None)
            descriptor["frames"] = [{"step": None, "time": None, "sources": {"*": {
                "path": item.path, "reader": READERS[EXTENSIONS[PurePosixPath(item.path).suffix.lower()]],
                "size": item.size, "sha256": known(item.path) if known else None}}}]
            datasets.append(descriptor)
            files.append(file_entry(item.path, size=item.size, sha256=known(item.path) if known else None,
                                    role="output"))
        return result_manifest(connector=self.id, connector_version=self.version, app={"id": self.id},
                               state="unknown" if not live else "running", complete=not live, datasets=datasets,
                               files=files)

    def open(self, run, dataset_id):
        described = self.describe(run)
        descriptor = next((d for d in described["datasets"] if d["id"] == dataset_id), None)
        if descriptor is None:
            raise ConnectorError(f"No dataset {dataset_id!r}; datasets: "
                                 f"{', '.join(d['id'] for d in described['datasets']) or 'none'}", "not_found")
        path = descriptor["frames"][0]["sources"]["*"]["path"]
        return FileHandle(run, path, detect_format(path), descriptor)

    def verify(self, run):
        return None

    def monitor_adapter(self, run, case):
        return None

    def default_graphs(self, result):
        return []
