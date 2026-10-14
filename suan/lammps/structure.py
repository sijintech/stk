"""Bounded, standard-library readers for full/real LAMMPS topology and text dumps.

Atom identity comes from IDs and bonds come only from the data file. Coordinates remain
float64 Python numbers. Wrapped coordinates without image flags are labelled wrapped;
they must not be used as an unwrapped diffusion trajectory. No solver or model is run.
"""
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import io
import math
import os
from pathlib import Path
import re
import stat
from types import MappingProxyType


READER = "stk.lammps-structure/1"
MAX_ID = 2147483647


class StructureError(ValueError):
    def __init__(self, message, code="invalid_data"):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Limits:
    max_bytes: int = 256 * 1024 * 1024
    max_atoms: int = 50000
    max_bonds: int = 100000
    max_terms: int = 500000
    max_frames: int = 10000
    max_line_bytes: int = 8192
    max_image_search: int = 10000
    max_bond_pieces: int = 128
    max_display_segments: int = 200000

    def __post_init__(self):
        caps = (256 * 1024 * 1024, 50000, 100000, 500000, 10000, 8192, 10000, 128, 200000)
        for value, cap in zip(self.__dict__.values(), caps):
            if type(value) is not int or not 1 <= value <= cap:
                raise ValueError("Reader limits must be positive integers within the documented hard caps")


DEFAULT_LIMITS = Limits()


def _finite(value, what):
    try:
        value = float(value)
    except (ValueError, TypeError, OverflowError):
        raise StructureError(f"Invalid {what}") from None
    if not math.isfinite(value):
        raise StructureError(f"Non-finite {what}")
    return value


def _integer(value, what, minimum=1, maximum=MAX_ID):
    if not isinstance(value, str) or not re.fullmatch(r"[+-]?[0-9]{1,12}", value):
        raise StructureError(f"Invalid {what}")
    number = int(value)
    if not minimum <= number <= maximum:
        raise StructureError(f"Out-of-range {what}")
    return number


def _vec(values, what):
    if len(values) != 3:
        raise StructureError(f"Invalid {what}")
    return tuple(_finite(value, what) for value in values)


@dataclass(frozen=True)
class Cell:
    origin: tuple
    vectors: tuple  # a=(lx,0,0), b=(xy,ly,0), c=(xz,yz,lz), in Angstrom
    boundary: tuple = ("unknown", "unknown", "unknown")

    def __post_init__(self):
        if len(self.vectors) != 3 or len(self.boundary) != 3:
            raise StructureError("Invalid cell")
        _vec(self.origin, "cell origin")
        for vector in self.vectors:
            _vec(vector, "cell vector")
        a, b, c = self.vectors
        if a[1:] != (0.0, 0.0) or b[2] != 0.0 or min(a[0], b[1], c[2]) <= 0:
            raise StructureError("Only a nondegenerate restricted triclinic cell is supported", "unsupported")

    @property
    def periodic(self):
        return tuple(value == "pp" for value in self.boundary)

    def cartesian(self, fractional):
        values = tuple(self.origin[j] + sum(fractional[i] * self.vectors[i][j] for i in range(3))
                       for j in range(3))
        return _vec(values, "transformed coordinates")

    def fractional(self, position):
        a, b, c = self.vectors
        z = (position[2] - self.origin[2]) / c[2]
        y = (position[1] - self.origin[1] - c[1] * z) / b[1]
        x = (position[0] - self.origin[0] - b[0] * y - c[0] * z) / a[0]
        return _vec((x, y, z), "fractional coordinates")

    def translate(self, position, images):
        return _vec(tuple(position[j] + sum(images[i] * self.vectors[i][j] for i in range(3))
                          for j in range(3)), "unwrapped coordinates")

    def wrap(self, position):
        if not any(self.periodic):
            return position
        values = self.fractional(position)
        return self.cartesian(tuple(value - math.floor(value) if periodic else value
                                    for value, periodic in zip(values, self.periodic)))

    def corners(self):
        return tuple(self.cartesian((x, y, z)) for x, y, z in
                     ((0, 0, 0), (1, 0, 0), (0, 1, 0), (1, 1, 0),
                      (0, 0, 1), (1, 0, 1), (0, 1, 1), (1, 1, 1)))


@dataclass(frozen=True)
class Atom:
    id: int
    molecule: int
    type: int
    charge: float
    position: tuple
    image: tuple | None = None


@dataclass(frozen=True)
class TopologyTerm:
    id: int
    type: int
    atoms: tuple


@dataclass(frozen=True)
class Structure:
    atoms: tuple
    bonds: tuple
    angles: tuple
    dihedrals: tuple
    impropers: tuple
    cell: Cell
    masses: object
    labels: object
    coefficients: object
    counts: object
    atom_style: str = "full"
    units: str = "real"

    @property
    def atom_by_id(self):
        return {atom.id: atom for atom in self.atoms}


@dataclass(frozen=True)
class Frame:
    step: int | None
    atoms: tuple
    cell: Cell
    coordinate_mode: str
    columns: tuple = ()

    @property
    def has_unwrapped(self):
        return self.coordinate_mode == "unwrapped"


@dataclass(frozen=True)
class FrameRef:
    step: int
    offset: int
    end: int
    cell: Cell
    columns: tuple
    coordinate_columns: tuple
    coordinate_mode: str


@dataclass(frozen=True)
class DumpIndex:
    frames: tuple
    sha256: str
    signature: tuple | None
    topology_identity: tuple


@contextmanager
def _stream(source):
    if isinstance(source, (str, os.PathLike)):
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(Path(source), flags)
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise StructureError("Structure input must be a regular file")
            stream = os.fdopen(descriptor, "rb")
        except BaseException:
            os.close(descriptor)
            raise
        with stream:
            yield stream
    else:
        if not callable(getattr(source, "readline", None)) or not source.seekable():
            raise StructureError("Structure input must be a seekable stream", "unsupported")
        yield source


def _signature(stream):
    try:
        value = os.fstat(stream.fileno())
    except (OSError, ValueError, AttributeError, io.UnsupportedOperation):
        return None
    return value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns


class _Lines:
    def __init__(self, stream, limits, check=None):
        self.stream, self.limits, self.check = stream, limits, check
        self.bytes, self.number = 0, 0
        self.hash = hashlib.sha256()

    def read(self, *, required=False):
        if self.check is not None:
            self.check()
        raw = self.stream.readline(self.limits.max_line_bytes + 1)
        if not raw:
            if required:
                raise StructureError("Incomplete structure or trajectory frame")
            return None
        data = raw.encode("utf-8") if isinstance(raw, str) else raw
        self.bytes += len(data)
        self.number += 1
        if len(data) > self.limits.max_line_bytes or self.bytes > self.limits.max_bytes:
            raise StructureError("Structure input exceeds the line or byte budget", "budget_exceeded")
        self.hash.update(data)
        try:
            return data.decode("utf-8").strip()
        except UnicodeError:
            raise StructureError("Structure input must be UTF-8 text") from None


_COUNTS = {"atoms": "Atoms", "bonds": "Bonds", "angles": "Angles", "dihedrals": "Dihedrals", "impropers": "Impropers"}
_ARITY = {"Bonds": 2, "Angles": 3, "Dihedrals": 4, "Impropers": 4}
_COEFFICIENTS = ("Pair Coeffs", "PairIJ Coeffs", "Bond Coeffs", "Angle Coeffs", "Dihedral Coeffs", "Improper Coeffs")
_SECTIONS = {"Masses", "Atoms", "Velocities", *_ARITY, *_COEFFICIENTS}


def _cell(bounds, tilt=(0.0, 0.0, 0.0), boundary=("unknown", "unknown", "unknown")):
    lengths = tuple(_finite(hi - lo, "cell length") for lo, hi in bounds)
    xy, xz, yz = tilt
    return Cell(tuple(lo for lo, hi in bounds),
                ((lengths[0], 0.0, 0.0), (xy, lengths[1], 0.0), (xz, yz, lengths[2])), boundary)


def parse_data(text, **options):
    """Parse supplied text; full/real only, and no inference of atom style or units."""
    if not isinstance(text, str):
        raise TypeError("parse_data takes text")
    return read_data(io.StringIO(text), **options)


def read_data(source, *, atom_style="full", units="real", limits=DEFAULT_LIMITS, check=None):
    """Read full/real topology, masses, coefficients and explicit bonded interactions.

    The data format itself does not encode boundary conditions. Its cell therefore has
    unknown boundaries; the dump supplies the actual boundary flags for a trajectory.
    """
    if atom_style != "full" or units != "real":
        raise StructureError("The structure reader currently supports atom_style full / units real only", "unsupported")
    with _stream(source) as stream:
        stream.seek(0)
        signature = _signature(stream)
        lines = _Lines(stream, limits, check)
        if lines.read() is None:
            raise StructureError("Empty LAMMPS data file")
        counts, types, bounds, tilt = {}, {}, {}, None
        seen, section = set(), None
        atoms, masses, labels, velocities = {}, {}, {}, set()
        terms = {name: {} for name in _ARITY}
        coefficients = {name: {} for name in _COEFFICIENTS}
        atom_width = None
        while (line := lines.read()) is not None:
            body, _, comment = line.partition("#")
            body = body.strip()
            if not body:
                continue
            if body in _SECTIONS:
                if body in seen:
                    raise StructureError("Duplicate LAMMPS data section")
                section = body
                seen.add(body)
                if body == "Atoms" and comment.strip() and comment.strip().split()[0] != "full":
                    raise StructureError("The Atoms section is not atom_style full", "unsupported")
                continue
            values = body.split()
            if section is None:
                if len(values) == 2 and values[1] in _COUNTS:
                    name = values[1]
                    if name in counts:
                        raise StructureError("Duplicate data count")
                    cap = limits.max_atoms if name == "atoms" else limits.max_bonds if name == "bonds" else limits.max_terms
                    counts[name] = _integer(values[0], "data count", 0, cap)
                elif len(values) == 3 and values[2] == "types" and values[1] in {"atom", "bond", "angle", "dihedral", "improper"}:
                    if values[1] in types:
                        raise StructureError("Duplicate type count")
                    types[values[1]] = _integer(values[0], "type count", 0, limits.max_terms)
                elif len(values) == 4 and values[2:] in (["xlo", "xhi"], ["ylo", "yhi"], ["zlo", "zhi"]):
                    axis = values[2][0]
                    if axis in bounds:
                        raise StructureError("Duplicate cell bounds")
                    bounds[axis] = tuple(_finite(value, "cell bound") for value in values[:2])
                elif len(values) == 6 and values[3:] == ["xy", "xz", "yz"] and tilt is None:
                    tilt = _vec(values[:3], "cell tilt")
                else:
                    raise StructureError("Unsupported LAMMPS data header", "unsupported")
                continue
            if section == "Atoms":
                if len(values) not in (7, 10) or atom_width is not None and len(values) != atom_width:
                    raise StructureError("Full atoms need id, molecule, type, charge, xyz and optional three image flags")
                atom_width = len(values)
                identity = _integer(values[0], "atom ID")
                if identity in atoms or len(atoms) >= limits.max_atoms:
                    raise StructureError("Duplicate atom ID or atom budget exceeded")
                images = tuple(_integer(value, "image flag", -1000000000, 1000000000) for value in values[7:]) or None
                atoms[identity] = Atom(identity, _integer(values[1], "molecule ID", 0),
                                       _integer(values[2], "atom type"), _finite(values[3], "charge"),
                                       _vec(values[4:7], "atom coordinates"), images)
            elif section in _ARITY:
                if len(values) != 2 + _ARITY[section]:
                    raise StructureError("Invalid bonded interaction record")
                identity = _integer(values[0], "interaction ID")
                if (identity in terms[section] or sum(map(len, terms.values())) >= limits.max_terms
                        or section == "Bonds" and len(terms[section]) >= limits.max_bonds):
                    raise StructureError("Duplicate interaction ID or interaction budget exceeded")
                ids = tuple(_integer(value, "interaction atom ID") for value in values[2:])
                if len(set(ids)) != len(ids):
                    raise StructureError("A bonded interaction repeats an atom ID")
                terms[section][identity] = TopologyTerm(identity, _integer(values[1], "interaction type"), ids)
            elif section == "Masses":
                if len(values) != 2:
                    raise StructureError("Invalid mass record")
                identity, mass = _integer(values[0], "mass type"), _finite(values[1], "mass")
                if identity in masses or mass <= 0 or len(masses) >= limits.max_atoms:
                    raise StructureError("Duplicate/invalid mass or mass budget exceeded")
                masses[identity] = mass
                labels[identity] = comment.strip().split()[0][:64] if comment.strip() else f"type-{identity}"
            elif section == "Velocities":
                if len(values) != 4:
                    raise StructureError("Invalid velocity record")
                identity = _integer(values[0], "velocity atom ID")
                if identity in velocities or len(velocities) >= limits.max_atoms:
                    raise StructureError("Duplicate velocity or velocity budget exceeded")
                velocities.add(identity)
                _vec(values[1:], "velocity")
            else:
                pair = section == "PairIJ Coeffs"
                if len(values) < (3 if pair else 2):
                    raise StructureError("Invalid coefficient record")
                key = tuple(_integer(value, "coefficient type") for value in values[:2]) if pair else _integer(values[0], "coefficient type")
                if key in coefficients[section] or sum(map(len, coefficients.values())) >= limits.max_terms:
                    raise StructureError("Duplicate coefficient or coefficient budget exceeded")
                coefficients[section][key] = tuple(_finite(value, "coefficient") for value in values[2 if pair else 1:])
        if signature != _signature(stream):
            raise StructureError("Data file changed while reading")
    if set(bounds) != {"x", "y", "z"} or counts.get("atoms", 0) < 1 or "Atoms" not in seen:
        raise StructureError("Data file lacks its atom count, Atoms section or cell bounds")
    if sum(counts.get(name, 0) for name in _COUNTS if name != "atoms") > limits.max_terms:
        raise StructureError("Interaction budget exceeded", "budget_exceeded")
    if len(atoms) != counts["atoms"]:
        raise StructureError("Atom records do not match the declared count")
    for name, section in _COUNTS.items():
        if name != "atoms" and len(terms[section]) != counts.get(name, 0):
            raise StructureError("Interaction records do not match the declared count")
    if not set(velocities) <= atoms.keys():
        raise StructureError("Velocity record names an unknown atom")
    for atom in atoms.values():
        if atom.type > types.get("atom", 0) or atom.type not in masses:
            raise StructureError("An atom type has no declared type or mass")
    if any(identity > types.get("atom", 0) for identity in masses):
        raise StructureError("Mass record names an undeclared atom type")
    for section, entries in terms.items():
        name = section.lower()[:-1]
        for entry in entries.values():
            if entry.type > types.get(name, 0) or not set(entry.atoms) <= atoms.keys():
                raise StructureError("A bonded interaction has an unknown type or atom")
    for section, entries in coefficients.items():
        category = "atom" if section.startswith("Pair") else section.split()[0].lower()
        for key in entries:
            identities = key if isinstance(key, tuple) else (key,)
            if any(identity > types.get(category, 0) for identity in identities):
                raise StructureError("Coefficient record names an undeclared type")
    cell = _cell(tuple(bounds[axis] for axis in "xyz"), tilt or (0.0, 0.0, 0.0))
    ordered = tuple(Atom(atom.id, atom.molecule, atom.type, atom.charge,
                         cell.translate(atom.position, atom.image) if atom.image is not None else atom.position,
                         atom.image) for atom in sorted(atoms.values(), key=lambda atom: atom.id))
    return Structure(ordered, *(tuple(sorted(terms[name].values(), key=lambda term: term.id)) for name in _ARITY),
                     cell, MappingProxyType(masses), MappingProxyType(labels),
                     MappingProxyType({key: MappingProxyType(value) for key, value in coefficients.items()}),
                     MappingProxyType({**counts, **{name + "_types": count for name, count in types.items()}}))


def _topology_identity(topology):
    return tuple((atom.id, atom.molecule, atom.type) for atom in topology.atoms)


def _dump_cell(lines, header):
    words = header.split()[3:]
    triclinic = words[:3] == ["xy", "xz", "yz"]
    flags = words[3:] if triclinic else words
    if len(flags) != 3 or any(flag != "pp" and not re.fullmatch(r"[fsm]{2}", flag) for flag in flags):
        raise StructureError("Unsupported dump box header or boundary flags", "unsupported")
    values = []
    for _ in range(3):
        row = lines.read(required=True).split()
        if len(row) != (3 if triclinic else 2):
            raise StructureError("Invalid dump cell bounds")
        values.append(tuple(_finite(value, "dump cell bound") for value in row))
    if triclinic:
        xy, xz, yz = values[0][2], values[1][2], values[2][2]
        bounds = ((values[0][0] - min(0.0, xy, xz, xy + xz), values[0][1] - max(0.0, xy, xz, xy + xz)),
                  (values[1][0] - min(0.0, yz), values[1][1] - max(0.0, yz)), values[2][:2])
        return _cell(bounds, (xy, xz, yz), tuple(flags))
    return _cell(tuple(row[:2] for row in values), boundary=tuple(flags))


def _coordinate_columns(columns):
    for names, mode in ((('xu', 'yu', 'zu'), 'unwrapped'), (('xsu', 'ysu', 'zsu'), 'unwrapped_scaled'),
                        (('x', 'y', 'z'), 'wrapped'), (('xs', 'ys', 'zs'), 'wrapped_scaled')):
        if all(name in columns for name in names):
            images = [name in columns for name in ("ix", "iy", "iz")]
            if any(images) and not all(images):
                raise StructureError("Dump image flags must include ix, iy and iz")
            return names, mode
    raise StructureError("Dump has no complete supported xyz coordinate triplet", "unsupported")


def _dump_atoms(lines, topology, cell, columns, names, mode, *, keep):
    if (not 2 <= len(columns) <= 64 or any(len(name) > 64 for name in columns)
            or len(set(columns)) != len(columns) or not {"id", "type"} <= set(columns)):
        raise StructureError("Dump columns need unique names, id and type")
    indices, original = {name: i for i, name in enumerate(columns)}, topology.atom_by_id
    seen, atoms = set(), []
    for _ in topology.atoms:
        values = lines.read(required=True).split()
        if len(values) != len(columns):
            raise StructureError("Dump atom record does not match its columns")
        identity = _integer(values[indices["id"]], "dump atom ID")
        if identity in seen or identity not in original:
            raise StructureError("Duplicate or unknown dump atom ID")
        seen.add(identity)
        basis = original[identity]
        kind = _integer(values[indices["type"]], "dump atom type")
        molecule = _integer(values[indices["mol"]], "dump molecule ID", 0) if "mol" in indices else basis.molecule
        if kind != basis.type or molecule != basis.molecule:
            raise StructureError("Dump type/molecule identity differs from its static topology", "unsupported")
        charge = _finite(values[indices["q"]], "dump charge") if "q" in indices else basis.charge
        position = _vec(tuple(values[indices[name]] for name in names), "dump coordinates")
        images = tuple(_integer(values[indices[name]], "dump image flag", -1000000000, 1000000000)
                       for name in ("ix", "iy", "iz")) if "ix" in indices else None
        if mode.endswith("scaled"):
            position = cell.cartesian(position)
        if mode.startswith("wrapped") and images is not None:
            position = cell.translate(position, images)
        if keep:
            atoms.append(Atom(identity, molecule, kind, charge, position, images))
    if seen != original.keys():
        raise StructureError("Dump frame does not contain every topology atom")
    return tuple(sorted(atoms, key=lambda atom: atom.id))


def index_dump(source, topology, *, limits=DEFAULT_LIMITS, check=None):
    """Scan and validate every complete frame with bounded memory; duplicates/resets reject.

    Orthogonal and restricted triclinic text dumps are supported. General triclinic,
    binary/compressed dumps, changing atom identity, repeated or backward steps reject.
    """
    if len(topology.atoms) > limits.max_atoms:
        raise StructureError("Atom budget exceeded", "budget_exceeded")
    with _stream(source) as stream:
        stream.seek(0)
        signature = _signature(stream)
        lines, frames = _Lines(stream, limits, check), []
        while (line := lines.read()) is not None:
            if not line:
                continue
            if len(frames) >= limits.max_frames:
                raise StructureError("Trajectory frame budget exceeded", "budget_exceeded")
            if line != "ITEM: TIMESTEP":
                raise StructureError("Expected a text dump TIMESTEP header", "unsupported")
            step = _integer(lines.read(required=True), "dump timestep", 0, 2147483647)
            if frames and step <= frames[-1].step:
                raise StructureError("Repeated or backward dump steps are unsupported; reset before enabling dump", "unsupported")
            if lines.read(required=True) != "ITEM: NUMBER OF ATOMS":
                raise StructureError("Missing dump atom-count header")
            count = _integer(lines.read(required=True), "dump atom count", 1, limits.max_atoms)
            if count != len(topology.atoms):
                raise StructureError("Dump atom count differs from its topology")
            header = lines.read(required=True)
            if not header.startswith("ITEM: BOX BOUNDS "):
                raise StructureError("Missing supported dump cell header", "unsupported")
            cell = _dump_cell(lines, header)
            header = lines.read(required=True)
            if not header.startswith("ITEM: ATOMS "):
                raise StructureError("Missing dump ATOMS header")
            columns = tuple(header.split()[2:])
            names, mode = _coordinate_columns(columns)
            offset = stream.tell()
            _dump_atoms(lines, topology, cell, columns, names, mode, keep=False)
            frames.append(FrameRef(step, offset, stream.tell(), cell, columns, names, mode))
        if not frames:
            raise StructureError("Trajectory has no complete frames")
        if signature != _signature(stream):
            raise StructureError("Dump file changed while indexing")
        return DumpIndex(tuple(frames), lines.hash.hexdigest(), signature, _topology_identity(topology))


def verify_dump_index(source, index, *, limits=DEFAULT_LIMITS, check=None):
    """Verify the complete raw bytes before reusing offsets, preserving stream position.

    File metadata is only a fast rejection path: an equal-size rewrite can retain all
    available timestamps. Every reuse therefore hashes the bounded input on every OS.
    """
    with _stream(source) as stream:
        position = stream.tell()
        try:
            signature = _signature(stream)
            if signature is not None and signature != index.signature:
                raise StructureError("Dump file changed after indexing", "source_changed")
            stream.seek(0)
            digest, count = hashlib.sha256(), 0
            while True:
                if check is not None:
                    check()
                raw = stream.read(min(65536, limits.max_bytes - count + 1))
                if not raw:
                    break
                data = raw.encode("utf-8") if isinstance(raw, str) else raw
                count += len(data)
                if count > limits.max_bytes:
                    raise StructureError("Dump byte budget exceeded", "budget_exceeded")
                digest.update(data)
            if signature != _signature(stream) or digest.hexdigest() != index.sha256:
                raise StructureError("Dump input changed after indexing", "source_changed")
        finally:
            stream.seek(position)


def read_dump_frame(source, topology, *, frame="latest", index=None, limits=DEFAULT_LIMITS, check=None):
    """Read an exact timestep, ``first`` or ``latest``. Atom rows are sorted by actual ID."""
    index = index_dump(source, topology, limits=limits, check=check) if index is None else index
    if index.topology_identity != _topology_identity(topology):
        raise StructureError("Trajectory index belongs to another topology")
    if frame in ("latest", "first"):
        selected = index.frames[-1 if frame == "latest" else 0]
    elif type(frame) is int:
        selected = next((value for value in index.frames if value.step == frame), None)
        if selected is None:
            raise StructureError("Requested trajectory timestep is absent", "missing_frame")
    else:
        raise StructureError("Select an exact integer timestep, first or latest")
    with _stream(source) as stream:
        verify_dump_index(stream, index, limits=limits, check=check)
        before = _signature(stream)
        stream.seek(selected.offset)
        lines = _Lines(stream, limits, check)
        atoms = _dump_atoms(lines, topology, selected.cell, selected.columns,
                            selected.coordinate_columns, selected.coordinate_mode, keep=True)
        if stream.tell() != selected.end or before != _signature(stream):
            raise StructureError("Dump frame changed after indexing")
    unwrapped = selected.coordinate_mode.startswith("unwrapped") or "ix" in selected.columns
    return Frame(selected.step, atoms, selected.cell, "unwrapped" if unwrapped else "wrapped", selected.columns)


def iter_dump_frames(source, topology, *, limits=DEFAULT_LIMITS, check=None):
    """Yield complete validated frames without retaining the trajectory's coordinates in memory."""
    with _stream(source) as stream:
        index = index_dump(stream, topology, limits=limits, check=check)
        for ref in index.frames:
            yield read_dump_frame(stream, topology, frame=ref.step, index=index, limits=limits, check=check)


def atom_sample(frame, atom_id):
    """Exact original float64 values by ID, never a distance-based guess from a picked pixel."""
    if type(atom_id) is not int:
        raise StructureError("Atom ID must be an integer")
    atom = next((atom for atom in frame.atoms if atom.id == atom_id), None)
    if atom is None:
        raise StructureError("Requested atom ID is absent", "not_found")
    return {"id": atom.id, "molecule": atom.molecule, "type": atom.type, "charge": atom.charge,
            "position": list(atom.position), "length_unit": "angstrom", "step": frame.step,
            "coordinate_mode": frame.coordinate_mode}


def _near_integers(center, lower, upper):
    if lower > upper:
        return
    first = min(upper, max(lower, round(center)))
    yield first
    distance = 1
    while first - distance >= lower or first + distance <= upper:
        for value in (first - distance, first + distance):
            if lower <= value <= upper:
                yield value
        distance += 1


def minimum_image(cell, delta, *, limits=DEFAULT_LIMITS):
    """Exact bounded closest-image search for a restricted triclinic cell.

    Rounding fractional components alone is incorrect even for ordinary tilted boxes.
    A triangular branch-and-bound search checks the lattice candidates within the best
    current sphere. Ill-conditioned cells that exceed the search cap explicitly reject.
    """
    delta = _vec(delta, "minimum-image displacement")
    a, b, c = cell.vectors
    periodic = cell.periodic
    nz = round(_finite(delta[2] / c[2], "periodic image ratio")) if periodic[2] else 0
    ny = round(_finite((delta[1] - c[1] * nz) / b[1], "periodic image ratio")) if periodic[1] else 0
    nx = round(_finite((delta[0] - b[0] * ny - c[0] * nz) / a[0], "periodic image ratio")) if periodic[0] else 0

    def residual(x, y, z):
        return (delta[0] - a[0] * x - b[0] * y - c[0] * z,
                delta[1] - b[1] * y - c[1] * z, delta[2] - c[2] * z)

    best = residual(nx, ny, nz)
    squared = _finite(sum(value * value for value in best), "minimum-image radius")
    visited = 0

    def candidates(center, radius, length, enabled):
        if not enabled:
            return (0,)
        lo, hi = (center - radius) / length, (center + radius) / length
        if not math.isfinite(lo) or not math.isfinite(hi):
            raise StructureError("Periodic image search is ill-conditioned", "unsupported")
        return _near_integers(center / length, math.ceil(lo - 1e-12), math.floor(hi + 1e-12))

    for z in candidates(delta[2], math.sqrt(squared), c[2], periodic[2]):
        visited += 1
        if visited > limits.max_image_search:
            raise StructureError("Periodic image search exceeds its candidate budget", "budget_exceeded")
        rz = delta[2] - c[2] * z
        remaining = squared - rz * rz
        if remaining < -1e-12:
            continue
        center_y = delta[1] - c[1] * z
        for y in candidates(center_y, math.sqrt(max(0.0, remaining)), b[1], periodic[1]):
            visited += 1
            if visited > limits.max_image_search:
                raise StructureError("Periodic image search exceeds its candidate budget", "budget_exceeded")
            ry = center_y - b[1] * y
            if ry * ry > remaining + 1e-12:
                continue
            x = round(_finite((delta[0] - b[0] * y - c[0] * z) / a[0], "periodic image ratio")) if periodic[0] else 0
            value = residual(x, y, z)
            distance = sum(part * part for part in value)
            if distance < squared:
                squared, best = distance, value
    return _vec(best, "minimum-image displacement")


def _bond_pieces(cell, start, delta, limits):
    f0 = cell.fractional(start)
    end = tuple(start[i] + delta[i] for i in range(3))
    f1 = cell.fractional(end)
    cuts = {0.0, 1.0}
    for axis, periodic in enumerate(cell.periodic):
        if not periodic or f0[axis] == f1[axis]:
            continue
        lo, hi = sorted((f0[axis], f1[axis]))
        if math.ceil(hi) - math.floor(lo) > limits.max_bond_pieces:
            raise StructureError("Bond display exceeds the periodic piece budget", "budget_exceeded")
        for boundary in range(math.floor(lo) + 1, math.ceil(hi)):
            value = (boundary - f0[axis]) / (f1[axis] - f0[axis])
            if 0.0 < value < 1.0:
                cuts.add(value)
    ordered = sorted(cuts)
    if len(ordered) - 1 > limits.max_bond_pieces:
        raise StructureError("Bond display exceeds the periodic piece budget", "budget_exceeded")
    result = []
    for lower, upper in zip(ordered, ordered[1:]):
        middle = (lower + upper) / 2
        image = tuple(math.floor(f0[i] + middle * (f1[i] - f0[i])) if periodic else 0
                      for i, periodic in enumerate(cell.periodic))
        p = cell.cartesian(tuple(f0[i] + lower * (f1[i] - f0[i]) - image[i] for i in range(3)))
        q = cell.cartesian(tuple(f0[i] + upper * (f1[i] - f0[i]) - image[i] for i in range(3)))
        result.append((p, q))
    return result


def display_geometry(topology, frame=None, *, wrapped=True, limits=DEFAULT_LIMITS, check=None):
    """Return point positions, true-bond segments and the twelve actual cell edges.

    Periodic wrapping is a display operation. With only wrapped coordinates the shortest
    lattice image is displayed and winding is unknown; no unwrapped source is invented.
    With xu/image flags the original bond displacement is retained before splitting.
    Each segment keeps its actual bond ID and endpoint atom IDs.
    """
    if type(wrapped) is not bool:
        raise TypeError("wrapped must be a boolean")
    frame = frame or Frame(None, topology.atoms, topology.cell, "data")
    if _topology_identity(topology) != tuple((a.id, a.molecule, a.type) for a in frame.atoms):
        raise StructureError("Displayed frame differs from its topology")
    atoms, cell = {atom.id: atom for atom in frame.atoms}, frame.cell
    positions = tuple(cell.wrap(atom.position) if wrapped else atom.position for atom in frame.atoms)
    segments = []
    for bond in topology.bonds:
        if check is not None:
            check()
        first, last = (atoms[identity].position for identity in bond.atoms)
        delta = _vec(tuple(last[i] - first[i] for i in range(3)), "bond displacement")
        if frame.coordinate_mode == "wrapped":
            delta = minimum_image(cell, delta, limits=limits)
        if wrapped:
            start = cell.wrap(first)
            pairs = _bond_pieces(cell, start, delta, limits)
        else:
            # Wrapped input has no winding information: retain the shortest-image convention.
            pairs = [(first, tuple(first[i] + delta[i] for i in range(3)))]
        if len(segments) + len(pairs) > limits.max_display_segments:
            raise StructureError("Molecular display exceeds the total segment budget", "budget_exceeded")
        segments.extend((p, q, bond.id, *bond.atoms) for p, q in pairs)
    corners = cell.corners()
    edges = tuple((corners[i], corners[j]) for i, j in
                  ((0, 1), (2, 3), (4, 5), (6, 7), (0, 2), (1, 3),
                   (4, 6), (5, 7), (0, 4), (1, 5), (2, 6), (3, 7)))
    return positions, tuple(segments), edges
