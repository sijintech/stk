"""Identity, coordinates, completeness and resource bounds of the molecular readers."""
import io
import math
import random

import pytest

from suan.lammps import structure
from suan.lammps.structure import (Cell, Limits, StructureError, atom_sample, display_geometry,
                                   index_dump, iter_dump_frames, minimum_image, parse_data,
                                   read_data, read_dump_frame, verify_dump_index)


DATA = """Synthetic full/real topology; no material validation

4 atoms
2 bonds
1 angles
0 dihedrals
0 impropers
3 atom types
1 bond types
1 angle types
0 dihedral types
0 improper types

0 10 xlo xhi
0 10 ylo yhi
0 10 zlo zhi
0 0 0 xy xz yz

Masses
1 12.011 # C
2 15.999 # O
3 1.008 # H

Pair Coeffs
1 0.07 3.5
2 0.17 3.0
3 0.03 2.4

Bond Coeffs
1 400 1.4

Angle Coeffs
1 50 120

Atoms # full
40 2 3 0.2 4 4 4
30 1 2 -0.4 3 1 1
10 1 1 0.1 1 1 1
20 1 1 0.1 2 1 1

Velocities
10 0 0 0
20 0 0 0
30 0 0 0
40 0 0 0

Bonds
8 1 20 30
7 1 10 20

Angles
17 1 10 20 30
"""


def dump_frame(step=0, *, coordinates="xu yu zu", box=None, rows=None, extra=""):
    box = box or "ITEM: BOX BOUNDS pp pp pp\n0 10\n0 10\n0 10\n"
    rows = rows or [(40, 2, 3, 0.2, 4, 4, 4), (30, 1, 2, -0.4, 3, 1, 1),
                    (10, 1, 1, 0.1, 1, 1, 1), (20, 1, 1, 0.1, 2, 1, 1)]
    return (f"ITEM: TIMESTEP\n{step}\nITEM: NUMBER OF ATOMS\n4\n" + box
            + f"ITEM: ATOMS id mol type q {coordinates}{extra}\n"
            + "".join(" ".join(map(str, row)) + "\n" for row in rows))


def test_data_preserves_ids_charge_masses_coefficients_and_real_topology():
    topology = parse_data(DATA)
    assert [atom.id for atom in topology.atoms] == [10, 20, 30, 40]
    assert [atom.charge for atom in topology.atoms] == [0.1, 0.1, -0.4, 0.2]
    assert math.isclose(math.fsum(atom.charge for atom in topology.atoms), 0, abs_tol=1e-15)
    assert topology.masses == {1: 12.011, 2: 15.999, 3: 1.008}
    assert topology.labels == {1: "C", 2: "O", 3: "H"}
    assert [(bond.id, bond.atoms) for bond in topology.bonds] == [(7, (10, 20)), (8, (20, 30))]
    assert topology.angles[0].atoms == (10, 20, 30)
    assert topology.coefficients["Bond Coeffs"][1] == (400, 1.4)
    assert topology.cell.boundary == ("unknown",) * 3
    with pytest.raises(TypeError):
        topology.masses[1] = 0


def test_data_images_use_actual_triclinic_lattice_and_do_not_touch_charge():
    text = DATA.replace("0 0 0 xy xz yz", "2 3 4 xy xz yz")
    text = text.replace(" 4 4 4\n", " 4 4 4 0 0 0\n").replace(" 3 1 1\n", " 3 1 1 0 0 0\n")
    text = text.replace(" 1 1 1\n", " 1 1 1 1 -2 3\n").replace(" 2 1 1\n", " 2 1 1 0 0 0\n")
    topology = parse_data(text)
    assert topology.atom_by_id[10].position == (16, -7, 31)
    assert topology.atom_by_id[10].image == (1, -2, 3)
    assert topology.atom_by_id[10].charge == 0.1


@pytest.mark.parametrize("before,after", [
    ("4 atoms", "5 atoms"), ("2 bonds", "1 bonds"), ("40 2 3 0.2", "20 2 3 0.2"),
    ("8 1 20 30", "8 1 20 99"), ("17 1 10 20 30", "17 1 10 20 20"),
    ("0.2 4 4 4", "nan 4 4 4"), ("0.2 4 4 4", "0.2 inf 4 4"),
    ("0 10 xlo xhi", "0 0 xlo xhi"), ("Atoms # full", "Atoms # atomic"),
    ("3 1.008 # H", "3 0 # H"), ("1 400 1.4", "2 400 1.4"),
    ("1 0.07 3.5", "1 NaN 3.5"), ("3 atom types", "1 atom types"),
    ("40 2 3 0.2 4 4 4", "40 2 3 0.2 4 4 4 0 0"),
])
def test_invalid_topology_is_rejected(before, after):
    with pytest.raises(StructureError):
        parse_data(DATA.replace(before, after))


def test_duplicate_sections_header_missing_mass_and_unsupported_style_reject():
    for text in (DATA + "\nAtoms\n", DATA.replace("4 atoms", "4 atoms\n4 atoms"),
                 DATA.replace("3 1.008 # H\n", ""), DATA.replace("0 0 0 xy xz yz", "0 0 0 abc origin")):
        with pytest.raises(StructureError):
            parse_data(text)
    with pytest.raises(StructureError, match="full / units real"):
        parse_data(DATA, units="lj")


def test_bounds_and_cancellation_do_not_allocate_or_read_unlimited_input():
    with pytest.raises(StructureError):
        parse_data(DATA, limits=Limits(max_atoms=3))
    with pytest.raises(StructureError, match="budget"):
        parse_data(DATA, limits=Limits(max_bytes=32))
    with pytest.raises(StructureError, match="budget"):
        parse_data("x" * 8193 + "\n" + DATA)
    with pytest.raises(ValueError):
        Limits(max_frames=10001)
    visits = 0

    def check():
        nonlocal visits
        visits += 1
        if visits == 5:
            raise RuntimeError("synthetic cancellation")

    with pytest.raises(RuntimeError, match="synthetic cancellation"):
        parse_data(DATA, check=check)


def test_dump_exact_selection_order_identity_and_float64_sample():
    topology = parse_data(DATA)
    text = dump_frame(5) + dump_frame(20)
    index = index_dump(io.BytesIO(text.encode()), topology)
    assert [frame.step for frame in index.frames] == [5, 20]
    frame = read_dump_frame(io.BytesIO(text.encode()), topology, frame=5, index=index)
    assert [atom.id for atom in frame.atoms] == [10, 20, 30, 40]
    assert frame.has_unwrapped
    assert atom_sample(frame, 30)["charge"] == -0.4
    assert atom_sample(frame, 30)["position"] == [3, 1, 1]
    assert [frame.step for frame in iter_dump_frames(io.BytesIO(text.encode()), topology)] == [5, 20]
    with pytest.raises(StructureError, match="absent"):
        read_dump_frame(io.StringIO(text), topology, frame=6)


def test_total_display_segment_budget_rejects_before_large_result_allocation():
    topology = parse_data(DATA)
    with pytest.raises(StructureError, match="total segment budget"):
        display_geometry(topology, limits=Limits(max_display_segments=1))
    with pytest.raises(ValueError):
        Limits(max_display_segments=200001)


def test_finite_inputs_that_overflow_transformations_fail_explicitly():
    cell = Cell((0, 0, 0), ((1e-308, 0, 0), (0, 1e-308, 0), (0, 0, 1e-308)), ("pp",) * 3)
    with pytest.raises(StructureError, match="Non-finite"):
        minimum_image(cell, (1e308, 1e308, 1e308))
    topology = parse_data(DATA.replace("10 1 1 0.1 1 1 1", "10 1 1 0.1 -1e308 1 1")
                               .replace("20 1 1 0.1 2 1 1", "20 1 1 0.1 1e308 1 1"))
    with pytest.raises(StructureError, match="bond displacement"):
        display_geometry(topology)


@pytest.mark.parametrize("boundary", [("pp", "ff", "pp"), ("ff", "pp", "ff"), ("ff", "ff", "ff")])
def test_partial_periodicity_uses_only_allowed_lattice_images(boundary):
    from itertools import product
    cell = Cell((2, -3, 4), ((10, 0, 0), (-3, 8, 0), (2, -4, 9)), boundary)
    delta = (8.5, -6.2, 7.7)
    expected = min((tuple(delta[j] - sum(image[i] * cell.vectors[i][j] for i in range(3)) for j in range(3))
        for image in product(*(range(-3, 4) if flag == "pp" else (0,) for flag in boundary))),
        key=lambda value: sum(part * part for part in value))
    assert minimum_image(cell, delta) == pytest.approx(expected)


def test_negative_triclinic_tilts_convert_outer_bounds_to_true_cell():
    box = "ITEM: BOX BOUNDS xy xz yz pp pp pp\n-4 11 -2\n-2 12 -3\n3 13 -4\n"
    frame = read_dump_frame(io.StringIO(dump_frame(box=box)), parse_data(DATA))
    assert frame.cell.origin == (1, 2, 3)
    assert frame.cell.vectors == ((10, 0, 0), (-2, 10, 0), (-3, -4, 10))


@pytest.mark.parametrize("columns,coordinates,images,expected,mode", [
    ("xu yu zu", (16, -7, 31), None, (16, -7, 31), "unwrapped"),
    ("xsu ysu zsu", (1, -2, 3), None, (16, -6, 33), "unwrapped"),
    ("x y z", (2, 3, 4), None, (2, 3, 4), "wrapped"),
    ("xs ys zs", (0.1, 0.2, 0.3), None, (3.3, 5.2, 6), "wrapped"),
    ("x y z", (2, 3, 4), (1, -2, 3), (17, -5, 34), "unwrapped"),
    ("xs ys zs", (0.1, 0.2, 0.3), (1, -2, 3), (18.3, -2.8, 36), "unwrapped"),
])
def test_orthogonal_and_restricted_triclinic_coordinate_forms(columns, coordinates, images, expected, mode):
    # Dump bounds are the outer bounding box, NOT the true data-file box.
    box = "ITEM: BOX BOUNDS xy xz yz pp pp pp\n1 16 2\n2 16 3\n3 13 4\n"
    rows = [(identity, molecule, kind, charge, *coordinates, *(images or ()))
            for identity, molecule, kind, charge in ((40, 2, 3, .2), (30, 1, 2, -.4), (10, 1, 1, .1), (20, 1, 1, .1))]
    text = dump_frame(coordinates=columns, box=box, rows=rows, extra=" ix iy iz" if images else "")
    frame = read_dump_frame(io.StringIO(text), parse_data(DATA))
    assert frame.cell.origin == (1, 2, 3)
    assert frame.cell.vectors == ((10, 0, 0), (2, 10, 0), (3, 4, 10))
    assert frame.coordinate_mode == mode
    assert frame.atoms[0].position == pytest.approx(expected)


@pytest.mark.parametrize("change", [
    lambda text: text.replace("NUMBER OF ATOMS\n4", "NUMBER OF ATOMS\n3"),
    lambda text: text.replace("40 2 3", "30 2 3"),
    lambda text: text.replace("40 2 3", "99 2 3"),
    lambda text: text.replace("40 2 3", "40 2 2"),
    lambda text: text.replace("40 2 3", "40 1 3"),
    lambda text: text.replace("0.2 4 4 4", "nan 4 4 4"),
    lambda text: text.replace("0.2 4 4 4", "0.2 4 4 NaN"),
    lambda text: text.replace("xu yu zu", "xu yu missing"),
    lambda text: text.replace("xu yu zu", "xu yu zu ix"),
    lambda text: text.replace("q xu", "type xu"),
    lambda text: text.replace("BOX BOUNDS pp", "BOX BOUNDS abc origin pp"),
    lambda text: text.replace("0 10\n", "0 0\n", 1),
    lambda text: text.rsplit("\n", 2)[0] + "\n",
])
def test_bad_dump_frames_reject_instead_of_silently_dropping_atoms(change):
    with pytest.raises(StructureError):
        index_dump(io.StringIO(change(dump_frame())), parse_data(DATA))


def test_repeated_reset_backward_steps_and_frame_budget_are_explicit():
    topology = parse_data(DATA)
    for second in (0, 4):
        with pytest.raises(StructureError, match="Repeated or backward"):
            index_dump(io.StringIO(dump_frame(5) + dump_frame(second)), topology)
    with pytest.raises(StructureError, match="frame budget"):
        index_dump(io.StringIO(dump_frame(0) + dump_frame(1)), topology, limits=Limits(max_frames=1))


def test_index_refuses_changed_file_and_another_topology(tmp_path):
    path = tmp_path / "trajectory.dump"
    path.write_text(dump_frame(), encoding="utf-8")
    topology = parse_data(DATA)
    index = index_dump(path, topology)
    path.write_text(dump_frame(1), encoding="utf-8")
    with pytest.raises(StructureError, match="changed"):
        read_dump_frame(path, topology, index=index)
    other = parse_data(DATA.replace("40 2 3", "40 3 3"))
    with pytest.raises(StructureError, match="another topology"):
        read_dump_frame(path, other, index=index)


@pytest.mark.parametrize("change", [
    lambda raw: raw.replace(b"TIMESTEP\n0\n", b"TIMESTEP\n1\n"),
    lambda raw: raw.replace(b"0.2 4 4 4", b"0.3 4 4 4"),
    lambda raw: raw.replace(b"0 10\n", b"0 11\n", 1),
])
def test_index_rejects_same_size_changed_bytes_even_with_identical_file_stat(tmp_path, monkeypatch, change):
    path = tmp_path / "trajectory.dump"
    original = dump_frame().encode()
    path.write_bytes(original)
    with path.open("rb") as stream:
        signature = structure._signature(stream)
    # Some file systems retain all available metadata for a rapid equal-size rewrite.
    monkeypatch.setattr(structure, "_signature", lambda stream: signature)
    topology = parse_data(DATA)
    index = index_dump(path, topology)
    changed = change(original)
    assert changed != original and len(changed) == len(original)
    path.write_bytes(changed)
    with pytest.raises(StructureError, match="changed") as failure:
        read_dump_frame(path, topology, index=index)
    assert failure.value.code == "source_changed"


@pytest.mark.parametrize("binary", [False, True])
def test_raw_index_verification_preserves_stream_position_and_enforces_byte_limit(binary):
    original = dump_frame()
    stream = io.BytesIO(original.encode()) if binary else io.StringIO(original)
    index = index_dump(stream, parse_data(DATA))
    stream.seek(11)
    verify_dump_index(stream, index)
    assert stream.tell() == 11
    with pytest.raises(StructureError, match="byte budget"):
        verify_dump_index(stream, index, limits=Limits(max_bytes=8))
    assert stream.tell() == 11
    stream.seek(0)
    changed = original.replace("TIMESTEP\n0\n", "TIMESTEP\n1\n")
    stream.write(changed.encode() if binary else changed)
    stream.seek(11)
    with pytest.raises(StructureError, match="changed"):
        verify_dump_index(stream, index)
    assert stream.tell() == 11


def test_raw_index_verification_cancels_mid_hash_and_restores_position():
    stream = io.BytesIO((dump_frame() + "\n" * 70000).encode())
    index = index_dump(stream, parse_data(DATA))
    stream.seek(11)
    checks = 0

    def cancel():
        nonlocal checks
        checks += 1
        if checks == 2:
            raise RuntimeError("fixture cancelled during raw hash")

    with pytest.raises(RuntimeError, match="cancelled during raw hash"):
        verify_dump_index(stream, index, check=cancel)
    assert stream.tell() == 11 and checks == 2


def test_index_signature_change_rejects_before_reading_bytes(tmp_path, monkeypatch):
    path = tmp_path / "trajectory.dump"
    path.write_bytes(dump_frame().encode())
    index = index_dump(path, parse_data(DATA))
    changed = (*index.signature[:-1], index.signature[-1] + 1)
    monkeypatch.setattr(structure, "_signature", lambda stream: changed)
    with path.open("rb") as stream:
        stream.seek(11)
        with pytest.raises(StructureError, match="changed"):
            verify_dump_index(stream, index, check=lambda: pytest.fail("stat change must reject before hashing"))
        assert stream.tell() == 11


def test_periodic_display_splits_real_bonds_and_never_infers_nearby_bonds():
    topology = parse_data(DATA)
    rows = [(40, 2, 3, .2, .21, 1, 1), (30, 1, 2, -.4, 9.5, 1, 1),
            (10, 1, 1, .1, .2, 1, 1), (20, 1, 1, .1, 9.8, 1, 1)]
    frame = read_dump_frame(io.StringIO(dump_frame(coordinates="x y z", rows=rows)), topology)
    positions, bonds, cell = display_geometry(topology, frame)
    assert len(positions) == 4 and len(cell) == 12
    assert [piece[2] for piece in bonds] == [7, 7, 8]
    assert all(piece[3:] in ((10, 20), (20, 30)) for piece in bonds)
    assert math.fsum(math.dist(piece[0], piece[1]) for piece in bonds if piece[2] == 7) == pytest.approx(.4)


def test_triclinic_minimum_image_matches_independent_exhaustive_lattice():
    cell = Cell((0, 0, 0), ((10, 0, 0), (5, 10, 0), (-4, 3, 10)), ("pp",) * 3)
    assert minimum_image(cell, (7.35, 4.9, 0)) == pytest.approx((-2.65, 4.9, 0))
    generator = random.Random(12)
    for _ in range(40):
        delta = tuple(generator.uniform(-15, 15) for _ in range(3))
        actual = minimum_image(cell, delta)
        expected = min(sum((delta[j] - sum(n[i] * cell.vectors[i][j] for i in range(3))) ** 2 for j in range(3))
                       for n in ((x, y, z) for x in range(-4, 5) for y in range(-4, 5) for z in range(-4, 5)))
        assert sum(value * value for value in actual) == pytest.approx(expected)


def test_ill_conditioned_periodic_geometry_has_a_search_budget():
    cell = Cell((0, 0, 0), ((10, 0, 0), (5, 1e-9, 0), (0, 0, 10)), ("pp",) * 3)
    with pytest.raises(StructureError, match="candidate budget"):
        minimum_image(cell, (4.9, .3, 0), limits=Limits(max_image_search=2))
