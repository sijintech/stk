"""LAMMPS full/real molecular source, with complete bounded trajectory indexing.

Only original topology bonds are shown. The source exposes PolyData, not a volume
grid; atom positions must not be queried through the field interpolation probe.
Heavy imports remain inside implementations so the catalog is NumPy-free.
"""
from collections import OrderedDict
import hashlib
import os
import threading

from suan.graph.registry import NodeExecutionError, Port, binding, boolean, node, step, string
from suan.runtime.models import relative_path

_INDEXES = OrderedDict()
_INDEX_LOCK = threading.Lock()
_INDEX_CAP = 4


def _signature(stream):
    try:
        info = os.fstat(stream.fileno())
    except (AttributeError, OSError, ValueError):
        return None
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def _paths(params):
    try:
        topology = relative_path(params["topology"])
        trajectory = params["trajectory"]
        if not isinstance(trajectory, str):
            raise ValueError("Trajectory must be a relative path or empty string")
        trajectory = relative_path(trajectory) if trajectory else ""
        if topology == trajectory:
            raise ValueError("Topology and trajectory must be separate files")
        return topology, trajectory
    except (KeyError, TypeError, ValueError):
        raise NodeExecutionError("Molecular paths must be relative files inside the binding", code="invalid_param") from None


def _topology(stream, check):
    from suan.lammps.structure import DEFAULT_LIMITS, StructureError, read_data
    signature = _signature(stream)
    digest, count = hashlib.sha256(), 0
    while chunk := stream.read(65536):
        check()
        count += len(chunk)
        if count > DEFAULT_LIMITS.max_bytes:
            raise StructureError("Topology byte budget exceeded", "budget_exceeded")
        digest.update(chunk)
    stream.seek(0)
    topology = read_data(stream, check=check)
    if signature != _signature(stream):
        raise StructureError("Topology changed while reading")
    return topology, digest.hexdigest()


def _index(stream, topology, topology_sha, check):
    from suan.lammps.structure import StructureError, index_dump, verify_dump_index
    signature = _signature(stream)
    # Cached indexes contain offsets and IDs, never the coordinates of all frames.
    # A non-file stream is reindexed and rehashed rather than trusting object identity.
    key = (topology_sha, signature) if signature is not None else None
    if key is not None:
        with _INDEX_LOCK:
            found = _INDEXES.get(key)
        if found is not None:
            try:
                verify_dump_index(stream, found, check=check)
            except StructureError as error:
                if error.code != "source_changed":
                    raise
                with _INDEX_LOCK:
                    if _INDEXES.get(key) is found:
                        del _INDEXES[key]
            else:
                with _INDEX_LOCK:
                    if _INDEXES.get(key) is found:
                        _INDEXES.move_to_end(key)
                return found
    result = index_dump(stream, topology, check=check)
    if key is not None:
        with _INDEX_LOCK:
            _INDEXES[key] = result
            _INDEXES.move_to_end(key)
            while len(_INDEXES) > _INDEX_CAP:
                _INDEXES.popitem(last=False)
    return result


def _load(ctx, params, *, read_frame=False):
    from suan.connectors.api import ConnectorError
    from suan.lammps.structure import Frame, StructureError, read_dump_frame
    topology_path, trajectory_path = _paths(params)
    source = ctx.resolve(params["binding"])
    try:
        with source.open(topology_path) as stream:
            topology, topology_sha = _topology(stream, ctx.check)
        used = [{"path": topology_path, "sha256": topology_sha, "role": "input"}]
        if trajectory_path:
            with source.open(trajectory_path) as stream:
                index = _index(stream, topology, topology_sha, ctx.check)
                choices = [ref.step for ref in index.frames]
                wanted = params["step"]
                selected = choices[-1] if wanted == "latest" else choices[0] if wanted == "first" else wanted
                if selected not in choices or isinstance(selected, bool):
                    ctx.report_choices("step", choices)
                    raise StructureError("Requested trajectory timestep is absent", "missing_frame")
                ctx.report_choices("step", choices, value=selected)
                frame = read_dump_frame(stream, topology, frame=selected, index=index, check=ctx.check) if read_frame else None
                used.append({"path": trajectory_path, "sha256": index.sha256, "role": "input"})
        else:
            selected = None
            if type(params["step"]) is int:
                raise StructureError("A static topology has no timestep; select first or latest", "missing_frame")
            ctx.report_choices("step", [])
            frame = Frame(None, topology.atoms, topology.cell, "data") if read_frame else None
        return topology, frame, used, selected
    except (ConnectorError, StructureError) as error:
        raise NodeExecutionError(str(error), code=error.code) from None
    except (OSError, UnicodeError) as error:
        raise NodeExecutionError(str(error), code="invalid_data") from None


def fingerprint(ctx, inputs, params):
    from suan.lammps.structure import READER
    _, _, used, selected = _load(ctx, params)
    return {"reader": READER, "index_verification": "raw-sha256/1", "used": used, "step": selected}


@node("stk.source.lammps_structure", title={"en": "LAMMPS molecule", "zh": "LAMMPS 分子结构"},
      description={"en": "Read full/real topology and optional complete text dump; preserve original atom IDs, charges and bonds."},
      outputs=[Port("atoms", "dataset", kind="points"), Port("bonds", "dataset", kind="polydata"),
               Port("box", "dataset", kind="polydata"), Port("diagnostics", "value", value_type="json")],
      params={"binding": binding(), "topology": string("state.data", min_length=1),
              "trajectory": string(""), "step": step("latest"), "wrapped_display": boolean(True)},
      time_dependent=True, fingerprint=fingerprint, selectors=("step",))
def molecular_source(ctx, inputs, params):
    import numpy as np
    from suan.data.model import Category, CellArray, PolyData, Provenance, TimeInfo
    from suan.lammps.structure import READER, StructureError, display_geometry
    topology, frame, used, selected = _load(ctx, params, read_frame=True)
    try:
        positions, segments, edges = display_geometry(topology, frame, wrapped=params["wrapped_display"], check=ctx.check)
    except StructureError as error:
        raise NodeExecutionError(str(error), code=error.code) from None
    provenance = Provenance(activity={"kind": "convert", "id": None},
        agent={"reader": READER, "node": ctx.node_id}, used=used)
    attrs = {"source": provenance.to_json(), "coordinate_mode": frame.coordinate_mode,
             "wrapped_display": params["wrapped_display"], "length_unit": "angstrom",
             "cell": {"origin": list(frame.cell.origin), "vectors": [list(v) for v in frame.cell.vectors],
                      "boundary": list(frame.cell.boundary)}, "probe": "atom_id_only"}
    metadata = {"length_unit": "angstrom", "frame": "world", "provenance": provenance,
                "time": TimeInfo(step=selected), "attrs": attrs}
    atoms = PolyData(np.array(positions, dtype=np.float64).reshape(-1, 3), id="atoms", label="Atoms", **metadata)
    for field, values in (("atom_id", [a.id for a in frame.atoms]), ("molecule_id", [a.molecule for a in frame.atoms])):
        atoms.add_field(field, np.array(values, dtype=np.int32), unit="1")
    categories = [Category(kind, topology.labels.get(kind) or f"Type {kind}") for kind in sorted({a.type for a in frame.atoms})]
    atoms.add_field("atom_type", np.array([a.type for a in frame.atoms], dtype=np.int32), unit="1", categories=categories)
    atoms.add_field("charge", np.array([a.charge for a in frame.atoms], dtype=np.float64), unit="e")
    atoms.add_field("source_position", np.array([a.position for a in frame.atoms], dtype=np.float64),
                    unit="angstrom", component_names=("x", "y", "z"))

    def lines(name, pieces):
        points = np.array([point for piece in pieces for point in piece[:2]], dtype=np.float64).reshape(-1, 3)
        cells = CellArray.uniform(np.arange(len(points), dtype=np.int64).reshape(-1, 2))
        return PolyData(points, lines=cells, id=name, label=name.capitalize(), **metadata)

    bonds, box = lines("bonds", segments), lines("box", edges)
    kinds = {bond.id: bond.type for bond in topology.bonds}
    for name, values in (("bond_id", [s[2] for s in segments]), ("bond_type", [kinds[s[2]] for s in segments]),
                         ("atom_a", [s[3] for s in segments]), ("atom_b", [s[4] for s in segments])):
        bonds.add_field(name, np.array(values, dtype=np.int32), association="cell", unit="1")
    diagnostics = {"reader": READER, "source": provenance.to_json(), "atom_style": "full", "units": "real",
        "units_source": "caller_declared",
        "atoms": len(frame.atoms), "bonds": len(topology.bonds), "bond_segments": len(segments),
        "step": selected, "coordinate_mode": frame.coordinate_mode, "wrapped_display": params["wrapped_display"],
        "boundary": list(frame.cell.boundary), "bonds_inferred": False,
        "positions_query": "Exact atom ID only; volume-field interpolation is unsupported."}
    if frame.coordinate_mode == "wrapped":
        ctx.warn("Wrapped coordinates have no image flags; shortest periodic bonds are a display convention, not a diffusion trajectory", code="wrapped_coordinates")
    if not params["trajectory"]:
        diagnostics["boundary_note"] = "A data file does not record boundary conditions; no periodicity is assumed."
    return {"atoms": atoms, "bonds": bonds, "box": box, "diagnostics": diagnostics}


__all__ = ["molecular_source", "fingerprint"]
