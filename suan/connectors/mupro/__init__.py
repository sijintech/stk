"""The public muFerro connector ``mupro.muferro`` (stk-data-format-v1.md §14, contracts §2.4).

It wraps STK's own launcher/verifier ``suan.mupro.run`` (``FRAME``,
``COMPONENTS``, ``ENERGY_ROW``, ``RESULT``, ``read_case``, ``expected_frames``,
``verify_run``, ``MuproError``) and never imports MuPRO code:

* ``sniff`` -- ``stk-mupro.json``, ``mupro_completion.json``, ``<Stem>.<8 digits>.dat``
  frames, or an ``input.toml`` with ``[system].simulation_grid``;
* ``describe`` -- stk.result/1 from file names, headers and the small text
  outputs (``energy_out.dat``, ``mupro_progress.jsonl``, ``stk-mupro.json``);
  field values are never parsed. Each stem is an ``image`` dataset on the
  shared ``grid`` frame (``grid_index`` units, spacing 1, origin 0); ``Polar``
  and 3-component stems are vectors (x, y, z), 6-component stems stay
  ``tensor: "array"`` until MuPRO confirms their component order; units are
  ``unspecified``. ``energy`` and ``progress`` are tables;
* ``open`` -- frames read with the fast DAT reader (region/stride applied after
  the read; DAT has no random access), tables parsed on demand;
* ``verify`` -- ``verify_run`` on a local run directory, else the verification
  recorded by the launcher in ``stk-mupro.json``.

The full muFerro input schema, exact thresholds and label maps belong to the
private ``stk-mupro`` package (priority 10); the light half here
(:mod:`.inputs`) ships a minimal schema.
"""
from importlib.metadata import PackageNotFoundError, version as _package_version
import json
from pathlib import PurePosixPath
import tempfile

from suan.mupro.run import COMPONENTS, FRAME, RESULT, MuproError, expected_frames, read_case, verify_run

from ..api import API_VERSION, ConnectorError, Match
from ..builtin import crop_sample, field_stats, select_frame
from .tables import read_energy, read_progress

__all__ = ["CONNECTOR_ID", "MuFerroConnector", "VERSION", "case_prefix", "field_descriptor", "frame_rows", "run_files",
           "stem_field"]

CONNECTOR_ID = "mupro.muferro"
VERSION = "0.1.0"
READER = "mupro.dat@1"
IDENTITY = [1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0]
OUTPUTS = ("energy_out.dat", "mupro_progress.jsonl", "mupro_completion.json")
# Stem -> (quantity, vector?) for the stems STK knows; never an assumed unit or tensor order.
_QUANTITIES = {
    "Polar": "polarization", "Displace": "displacement", "Elefield": "electric_field",
    "Elas_For": "mupro:elastic_force", "Elec_For": "mupro:electric_force", "LandPFor": "mupro:landau_force",
    "Charges": "charge_density", "Elec_Phi": "electric_potential", "Elast_En": "energy_density",
    "Elect_En": "energy_density", "LandP_En": "energy_density", "Strain": "strain", "Stress": "stress",
    "Eigen_St": "eigenstrain",
}


def _stk_version():
    try:
        return _package_version("suan_toolkits")
    except PackageNotFoundError:
        return None


def stem_field(stem, components=None):
    """field-1 descriptor of a muFerro stem (``components`` from ``COMPONENTS``/the header when unknown)."""
    count = 3 if stem == "Polar" else COMPONENTS.get(stem, components)
    if count is None:
        raise ConnectorError(f"Unknown component count for stem {stem!r}", "invalid_data")
    entry = {"name": stem, "association": "point", "dtype": "float64", "components": count,
             "tensor": "scalar" if count == 1 else ("vector" if count == 3 else "array"), "unit": "unspecified"}
    if count == 3:
        entry["component_names"] = ["x", "y", "z"]
    if stem in _QUANTITIES:
        entry["quantity"] = _QUANTITIES[stem]
    return entry


def field_descriptor(stem, grid, frames, components=None):
    """stk.dataset/1 of one stem: an image on the ``grid`` frame with its frame list."""
    return {"schema": "stk.dataset/1", "id": stem, "kind": "image",
            "geometry": {"frame": "grid", "length_unit": "grid_index", "dimensions": list(grid),
                         "origin": [0.0, 0.0, 0.0], "spacing": [1.0, 1.0, 1.0], "direction": list(IDENTITY)},
            "fields": [stem_field(stem, components)],
            "time": {"index": "step", "step": None, "value": None, "physical": {"unit": "unspecified", "known": False}},
            "frames": frames}


def frame_rows(result):
    """Rows ``{dataset, step, time, path, size, sha256, reader, components}`` of every image frame of a result."""
    rows = []
    for dataset in result.get("datasets", ()):
        if dataset.get("kind") != "image":
            continue
        components = dataset["fields"][0]["components"] if dataset.get("fields") else None
        for frame in dataset.get("frames", ()):
            for source in frame["sources"].values():
                rows.append({"dataset": dataset["id"], "step": frame.get("step"), "time": frame.get("time"),
                             "path": source["path"], "size": source.get("size"), "sha256": source.get("sha256"),
                             "reader": source.get("reader", READER), "components": components})
    return sorted(rows, key=lambda r: (r["dataset"], r["step"] if r["step"] is not None else -1))


def case_prefix(case_dir):
    """``""`` for the binding root (``"."``, ``"./"``), else ``"<case_dir>/"`` (a checked relative path)."""
    from ..files import check_path
    relative = check_path(case_dir or ".")
    return relative.rstrip("/") + "/" if relative else ""


def run_files(run, prefix=""):
    """``{path: FileInfo}`` of a run: the whole binding plus the case directory (which may be a linked directory)."""
    names = {item.path: item for item in run.list("")}
    if prefix:
        names.update({item.path: item for item in run.list(prefix)})
    return names


def _read_text(run, path, limit=64 * 1024 * 1024):
    with run.open(path) as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ConnectorError(f"{path} is larger than {limit} bytes", "invalid_data")
    return data.decode("utf-8", "replace")


def _media_type(path):
    suffix = PurePosixPath(path).suffix.lower()
    return {".dat": "text/plain", ".toml": "application/toml", ".json": "application/json",
            ".jsonl": "application/x-ndjson", ".log": "text/plain", ".h5": "application/x-hdf5"}.get(suffix)


class _Mirror:
    """TOML files of a remote source copied to a temporary directory, so ``read_case`` can follow includes."""

    def __init__(self, run, names):
        self._tmp = tempfile.TemporaryDirectory(prefix="stk-muferro-")
        from pathlib import Path
        self.root = Path(self._tmp.name)
        for name in names:
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            with run.open(name) as stream:
                target.write_bytes(stream.read(1 << 22))

    def close(self):
        self._tmp.cleanup()


class MuFerroConnector:
    """Heavy half of the muFerro connector (``suan.connectors.api.Connector``)."""

    id = CONNECTOR_ID
    version = VERSION
    api = API_VERSION

    def __init__(self, *, case_dir="."):
        self.case_dir = case_dir

    def info(self):
        return {"id": self.id, "version": self.version, "api": self.api, "apps": [CONNECTOR_ID], "priority": 0,
                "license": "MIT",
                "capabilities": {"read": ["image", "table"],
                                 "inputs": {"schema": "mupro.muferro/input@1", "read": True, "write": True},
                                 "verify": "stk-mupro-1", "monitor_adapter": True, "task_spec": True,
                                 "default_graphs": ["muferro-domains", "energy-plot"]},
                "runs_on": {"describe": "node", "read": "node|desktop", "inputs": "any", "monitor_adapter": "task"}}

    # -- discovery ------------------------------------------------------------

    def sniff(self, run):
        names = {item.path for item in run.list("")}
        if RESULT in names:
            return Match(self.id, 1.0, CONNECTOR_ID, f"{RESULT} (STK muFerro launcher record)")
        if any(name.endswith("mupro_completion.json") for name in names):
            return Match(self.id, 0.95, CONNECTOR_ID, "mupro_completion.json")
        frames = [name for name in names if FRAME.search(name)]
        if frames:
            return Match(self.id, 0.9, CONNECTOR_ID, f"{len(frames)} muFerro field frame(s)")
        for name in sorted(n for n in names if PurePosixPath(n).name == "input.toml"):
            text = _read_text(run, name, 1 << 20)
            if "simulation_grid" in text and "[system]" in text:
                return Match(self.id, 0.6, CONNECTOR_ID, f"{name} with [system].simulation_grid")
        return None

    def _record(self, run, names=None):
        """The launcher's ``stk-mupro.json`` (``None`` when absent or unreadable)."""
        names = names if names is not None else {item.path for item in run.list("")}
        if RESULT not in names:
            return None
        try:
            record = json.loads(_read_text(run, RESULT, 1 << 22))
        except (ConnectorError, FileNotFoundError, ValueError):
            return None
        return record if isinstance(record, dict) else None

    def _case(self, run, case_dir, record, files=None):
        """``(case dict | None, error message | None)`` from input.toml (and includes) or the launcher record."""
        prefix = case_prefix(case_dir)
        names = [path for path in (files if files is not None else run_files(run, prefix)) if path.endswith(".toml")]
        if prefix + "input.toml" in names:
            local = run.local_path(".")
            mirror = None
            try:
                if local is None:
                    mirror = _Mirror(run, names)
                    local = mirror.root
                return read_case(local / prefix if prefix else local, local), None
            except MuproError as exc:
                return None, str(exc)
            finally:
                if mirror is not None:
                    mirror.close()
        recorded = (record or {}).get("case")
        if isinstance(recorded, dict) and isinstance(recorded.get("grid"), list) and len(recorded["grid"]) == 3:
            return recorded, None
        return None, None

    def _frames(self, run, prefix):
        found = {}
        for item in run.list(prefix):
            name = item.path[len(prefix):]
            if "/" in name:
                continue
            match = FRAME.search(name)
            if match:
                found.setdefault(match[1], []).append((int(match[2]), item))
        return found

    def _grid(self, run, case, frames):
        if case:
            return list(case["grid"]), None
        for stem, items in sorted(frames.items()):
            from suan.data.dat import DatError, dat_info
            with run.open(items[0][1].path) as stream:
                try:
                    info = dat_info(stream)
                except (DatError, UnicodeDecodeError):
                    continue
            return info["dimensions"], info
        return None, None

    def describe(self, run, *, live=False, case_dir=None):
        """stk.result/1 of a muFerro run directory (``live``: frames so far, ``complete: false``)."""
        from suan.data.manifest import file_entry, qoi_entry, result_manifest
        case_dir = case_dir or self.case_dir
        prefix = case_prefix(case_dir)
        names = run_files(run, prefix)
        record = self._record(run, names)
        case, case_error = self._case(run, case_dir, record, names)
        frames = self._frames(run, prefix)
        grid, header = self._grid(run, case, frames)
        known = getattr(run, "known_sha256", None)
        datasets = []
        for stem in sorted(frames, key=lambda s: (s != "Polar", s)):
            if grid is None:
                break
            entries = [{"step": step, "time": None,
                        "sources": {stem: {"path": item.path, "reader": READER, "size": item.size,
                                           "sha256": known(item.path) if known else None}}}
                       for step, item in sorted(frames[stem], key=lambda pair: pair[0])]
            components = None
            if stem != "Polar" and stem not in COMPONENTS:
                components = self._components(run, entries[0]["sources"][stem]["path"])
            datasets.append(field_descriptor(stem, grid, entries, components))
        qoi = []
        energy_path = prefix + "energy_out.dat"
        if energy_path in names:
            table = None
            try:
                table = read_energy(_read_text(run, energy_path))
            except ConnectorError:
                pass
            columns = table.columns[1:] if table is not None else [f"energy_{i}" for i in range(1, 6)]
            datasets.append(self._table("energy", energy_path, names[energy_path], "mupro.energy@1",
                                        ["step"] + list(columns), "normalized", table))
            if table is not None and table.n_rows:
                qoi.append(qoi_entry("total_energy", float(table.column(columns[-1])[-1]), "normalized",
                                     quantity="energy", step=int(table.column("step")[-1]),
                                     source={"dataset": "energy", "column": columns[-1], "path": energy_path},
                                     definition=f"Last native {columns[-1]} row"))
        progress_path = prefix + "mupro_progress.jsonl"
        if progress_path in names:
            datasets.append(self._table("progress", progress_path, names[progress_path], "mupro.progress@1",
                                        ["step", "completed_steps", "total_steps"], "1", None))
        completion = prefix + "mupro_completion.json" in names
        missing = []
        if case and {"start_step", "steps", "output_interval"} <= set(case):
            present = {f"{stem}.{step:08d}.dat" for stem, items in frames.items() for step, _ in items}
            missing = sorted(set(expected_frames(case)) - present)
        complete = not live and completion and not missing
        verification = None
        state = "unknown"
        outcome = {"classification": None, "retryable": False, "reason": ""}
        if record:
            if record.get("state") in ("prepared", "queued", "running", "succeeded", "failed", "cancelled",
                                       "interrupted"):
                state = record["state"]
            outcome = {"classification": record.get("classification"), "retryable": False,
                       "reason": record.get("reason") or ""}
            recorded = record.get("verification") or {}
            if recorded.get("status") in ("passed", "failed"):
                verification = {"verifier": recorded.get("verifier", "stk-mupro-1"), "status": recorded["status"],
                                "checks": [{k: v for k, v in c.items() if k in ("id", "status", "message")}
                                           for c in recorded.get("checks", ())]}
            if record.get("qoi") and not qoi:
                qoi.append(qoi_entry("total_energy", record["qoi"].get("total_energy"), "normalized",
                                     quantity="energy", step=record["qoi"].get("step"),
                                     source={"dataset": "energy", "column": "Total Energy"},
                                     definition="Last native Total Energy row"))
        elif live:
            state = "running"
        if verification is None and not live and completion and run.local_path(".") is not None:
            verification = self.verify(run, case_dir=case_dir)
            if state == "unknown" and verification:
                state = "succeeded" if verification["status"] == "passed" else "failed"
        run_info = {"case": {"case_id": None, "dir": case_dir, "manifest": None}}
        extensions = {"mupro": {"case": case}}
        if case_error:
            extensions["mupro"]["case_error"] = case_error
        if missing:
            extensions["mupro"]["missing_frames"] = missing[:50]
        if header:
            extensions["mupro"]["header"] = header
        app = {"id": CONNECTOR_ID, "name": "muFerro", "version": None, "executable_sha256": None}
        if record:
            program = record.get("program") or {}
            app["executable_sha256"] = program.get("sha256")
            layout = record.get("layout") or {}
            run_info["layout"] = {k: layout.get(k) for k in ("ranks", "threads_per_rank", "launcher")}
            run_info.update(started_at=record.get("started_at"), finished_at=record.get("finished_at"),
                            exit_code=record.get("exit_code"))
            extensions["mupro"].update({k: record.get(k) for k in ("command", "environment", "sdk_prefix")})
        files = []
        for path, item in sorted(names.items()):
            name = PurePosixPath(path).name
            role = ("manifest" if path == RESULT else "input" if name.endswith(".toml")
                    else "log" if name.endswith(".log") else "output" if (FRAME.search(name) or name in OUTPUTS)
                    else "other")
            files.append(file_entry(path, size=item.size, sha256=known(path) if known else None,
                                    media_type=_media_type(path), role=role))
        return result_manifest(
            connector=self.id, connector_version=self.version, stk=_stk_version(), app=app, state=state,
            complete=complete, datasets=datasets, files=files, qoi=qoi, verification=verification, run=run_info,
            outcome=outcome, scientific_status="exploratory",
            native=[{"path": RESULT, "schema": "stk-mupro/1"}] if record else [], extensions=extensions)

    def _components(self, run, path):
        from suan.data.dat import DatError, dat_info
        with run.open(path) as stream:
            try:
                return dat_info(stream)["components"]
            except (DatError, UnicodeDecodeError) as exc:
                raise ConnectorError(f"{path}: {exc}", "invalid_data") from None

    @staticmethod
    def _table(dataset_id, path, item, reader, columns, unit, table):
        entries = []
        for name in columns:
            entry = {"name": name, "association": "row", "dtype": "int64" if name in (
                "step", "completed_steps", "total_steps") else "float64", "components": 1, "tensor": "scalar",
                "unit": "1" if name == "step" else unit}
            if name == "step":
                entry.update(role="index", quantity="step")
            elif unit == "normalized":
                entry["quantity"] = "energy"
            entries.append(entry)
        return {"schema": "stk.dataset/1", "id": dataset_id, "kind": "table",
                "geometry": {"rows": table.n_rows if table is not None else None}, "columns": entries,
                "frames": [{"step": None, "time": None,
                            "sources": {"*": {"path": path, "reader": reader, "size": item.size}}}]}

    # -- data -------------------------------------------------------------------

    def open(self, run, dataset_id, *, case_dir=None, result=None):
        """A handle on ``Polar``, an auxiliary stem, ``energy`` or ``progress``."""
        result = result or self.describe(run, live=True, case_dir=case_dir)
        descriptor = next((d for d in result["datasets"] if d["id"] == dataset_id), None)
        if descriptor is None:
            raise ConnectorError(f"No dataset {dataset_id!r} in this run; datasets: "
                                 f"{', '.join(d['id'] for d in result['datasets']) or 'none'}", "not_found")
        if descriptor["kind"] == "table":
            return _TableHandle(run, descriptor)
        return FrameHandle(run, descriptor)

    def verify(self, run, *, case_dir=None):
        """``verify_run`` of a local run directory, else the launcher's recorded verification (or ``None``)."""
        case_dir = case_dir or self.case_dir
        local = run.local_path(".")
        if local is not None:
            result = verify_run(local, case_dir)
            verification = dict(result["verification"])
            for check in verification.get("checks", ()):
                if check["status"] == "fail" and result.get("classification") and check["message"] == result.get(
                        "reason"):
                    check["classification"] = result["classification"]
            return verification
        record = self._record(run)
        recorded = (record or {}).get("verification") or {}
        if recorded.get("status") in ("passed", "failed"):
            return {"verifier": recorded.get("verifier", "stk-mupro-1"), "status": recorded["status"],
                    "checks": list(recorded.get("checks", ()))}
        return None

    def monitor_adapter(self, run, case, *, case_dir=None):
        """A :class:`~.monitor.MuferroMonitorAdapter` over a run directory on this host (``None`` for remote runs).

        It applies the adapt-mode rules of ``suan.mupro.monitor`` (the launcher's own adapter:
        progress, energy metrics, published frames, completion) and returns ``{type, data}``
        events from ``poll``; ``replay()`` gives every event of a finished run, including
        ``verification`` and ``run.completed``.
        """
        local = run.local_path(".")
        if local is None:
            return None
        from .monitor import MuferroMonitorAdapter
        return MuferroMonitorAdapter(local, case_dir or self.case_dir)

    def default_graphs(self, result):
        """The ``muferro-domains`` and ``energy-plot`` presets bound to ``run``, when installed."""
        from importlib.resources import files
        graphs = []
        try:
            presets = files("suan.graph").joinpath("presets")
        except ModuleNotFoundError:  # pragma: no cover
            return graphs
        for name in ("muferro-domains", "energy-plot"):
            resource = presets.joinpath(name + ".json")
            if resource.is_file():
                graphs.append(json.loads(resource.read_text(encoding="utf-8")))
        return graphs


class FrameHandle:
    """``DatasetHandle`` of one muFerro stem (frames = steps)."""

    def __init__(self, run, descriptor):
        self.run = run
        self.descriptor = descriptor
        self._stats = {}

    @property
    def frames(self):
        return [{"step": f["step"], **next(iter(f["sources"].values()))} for f in self.descriptor["frames"]]

    def frame(self, selector):
        return select_frame(self.frames, selector)

    def read(self, *, frame=None, fields=None, region=None, stride=None, dtype="float64", check=None,
             spacing=None, origin=None, length_unit="grid_index", unit=None, quantity=None):
        from suan.data.dat import DatError, read_dat_image
        from suan.data.model import Provenance
        from ..files import materialize
        chosen = self.frame(frame)
        entry = self.descriptor["fields"][0]
        if fields is not None and entry["name"] not in fields:
            raise ConnectorError(f"Dataset {self.descriptor['id']!r} has only the field {entry['name']!r}",
                                 "invalid_param")
        sha = self.run.sha256(chosen["path"])
        provenance = Provenance(activity={"kind": "run", "id": None},
                                agent={"connector": f"{CONNECTOR_ID}@{VERSION}", "reader": READER},
                                used=[{"path": chosen["path"], "sha256": sha, "role": "input"}])
        try:
            image = read_dat_image(materialize(self.run, chosen["path"]), name=entry["name"], id=self.descriptor["id"],
                                   dtype=dtype, spacing=spacing, origin=origin, length_unit=length_unit,
                                   unit=unit or entry["unit"], quantity=quantity or entry.get("quantity"),
                                   tensor=entry["tensor"], component_names=entry.get("component_names"),
                                   step=chosen["step"], provenance=provenance, check=check)
        except DatError as exc:
            raise ConnectorError(f"{chosen['path']}: {exc}", "invalid_data") from None
        expected = self.descriptor["geometry"]["dimensions"]
        if list(image.dimensions) != list(expected) or image.field(entry["name"]).components != entry["components"]:
            raise ConnectorError(f"{chosen['path']} has grid {list(image.dimensions)} x "
                                 f"{image.field(entry['name']).components}; the run declares {expected} x "
                                 f"{entry['components']}", "invalid_data")
        return crop_sample(image, region, stride)

    def stats(self, *, frame=None, field=None):
        chosen = self.frame(frame)
        key = (chosen["path"], self.run.sha256(chosen["path"]))
        if key not in self._stats:
            self._stats[key] = field_stats(self.read(frame={"step": chosen["step"], "policy": "exact"}),
                                           self.descriptor["fields"][0]["name"])
        return self._stats[key]


class _TableHandle:
    """``DatasetHandle`` of ``energy`` or ``progress`` (no frames)."""

    def __init__(self, run, descriptor):
        self.run = run
        self.descriptor = descriptor

    def read(self, *, frame=None, fields=None, region=None, stride=None):
        source = self.descriptor["frames"][0]["sources"]["*"]
        text = _read_text(self.run, source["path"])
        reader = read_energy if self.descriptor["id"] == "energy" else read_progress
        return reader(text, keep=list(fields) if fields else None)

    def stats(self, *, frame=None, field):
        return field_stats(self.read(fields=[field]), field)
