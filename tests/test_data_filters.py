"""suan.data.filters: VTK/NumPy geometry filters with known answers (docs/specs/stk-graph-v1.md §14)."""
import math
import os
import time

import pytest

np = pytest.importorskip("numpy")
vtk = pytest.importorskip("vtk")

from suan.data import filters  # noqa: E402
from suan.data.filters import FilterError  # noqa: E402
from suan.data.model import Category, ImageData, Provenance, TimeInfo  # noqa: E402


def frozen(image):
    """The evaluator hands nodes read-only arrays; a filter that writes into its input fails loudly."""
    for field in image.fields.values():
        field.values.flags.writeable = False
    return image


def grid_coords(dims, origin=(0.0, 0.0, 0.0), spacing=(1.0, 1.0, 1.0)):
    """Physical x, y, z of every point, each (nz, ny, nx)."""
    nx, ny, nz = dims
    z, y, x = np.meshgrid(np.arange(nz), np.arange(ny), np.arange(nx), indexing="ij")
    return (origin[0] + x * spacing[0], origin[1] + y * spacing[1], origin[2] + z * spacing[2])


def scalar_image(values, origin=(0.0, 0.0, 0.0), spacing=(1.0, 1.0, 1.0), name="s", **kw):
    nz, ny, nx = values.shape
    image = ImageData((nx, ny, nz), origin, spacing, id="img", time=TimeInfo(step=7),
                      provenance=Provenance(agent={"node": "src"}), **kw)
    image.add_field(name, np.ascontiguousarray(values, dtype=np.float64), unit="V", quantity="electric_potential")
    return frozen(image)


def sphere_distance(n=48, center=None):
    c = (n - 1) / 2 if center is None else center
    x, y, z = grid_coords((n, n, n))
    return np.sqrt((x - c) ** 2 + (y - c) ** 2 + (z - c) ** 2)


def triangle_area(poly):
    tris = poly.polys.connectivity.reshape(-1, 3)
    p = poly.points
    return 0.5 * np.linalg.norm(np.cross(p[tris[:, 1]] - p[tris[:, 0]], p[tris[:, 2]] - p[tris[:, 0]]), axis=1).sum()


def signed_volume(points, tris):
    a, b, c = points[tris[:, 0]], points[tris[:, 1]], points[tris[:, 2]]
    return float(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6)


def open_edges(points, tris):
    """Edges not shared by exactly two triangles (boundary or non-manifold); 0 for a closed 2-manifold."""
    edges = np.sort(np.concatenate([tris[:, [0, 1]], tris[:, [1, 2]], tris[:, [2, 0]]]), axis=1)
    _, counts = np.unique(edges, axis=0, return_counts=True)
    return int((counts != 2).sum())


# ---------------------------------------------------------------------------
# contour


def test_sphere_contour_area_within_two_percent():
    image = scalar_image(sphere_distance(48))
    poly = filters.contour(image, {"name": "s", "component": None}, [10.0])
    area = triangle_area(poly)
    assert abs(area - 4 * math.pi * 100) / (4 * math.pi * 100) < 0.02
    assert np.allclose(poly.array("iso_value"), 10.0)
    normals = poly.array("Normals")
    assert normals.dtype == np.float32 and normals.shape == (poly.n_points, 3)
    assert np.allclose(np.linalg.norm(normals, axis=1), 1.0, atol=1e-3)
    radius = np.linalg.norm(poly.points - 23.5, axis=1)
    assert np.abs(radius - 10).max() < 0.2
    assert poly.time.step == 7 and poly.provenance.agent == {"node": "src"}  # lineage travels with the result


def test_multi_level_contour_value_set_and_probes():
    values = sphere_distance(32)
    image = scalar_image(values)
    image.add_field("twice", np.ascontiguousarray(2 * values), unit="V")
    labels = (values < 8).astype(np.int16)
    image.add_field("inner", labels, tensor="label",
                    categories=(Category(0, "out"), Category(1, "in")))
    frozen(image)
    levels = [5.0, 7.5, 11.0]
    poly = filters.contour(image, "s", levels, probe_fields=["twice", "inner"])
    assert sorted(np.unique(np.round(poly.array("iso_value")[:, 0], 9)).tolist()) == levels
    assert np.allclose(poly.array("twice")[:, 0], 2 * poly.array("iso_value")[:, 0], atol=1e-6)
    inner = poly.fields["inner"]
    assert inner.is_label and inner.categories[1].name == "in"
    assert poly.attrs["contour"]["values"] == levels
    # One value at the middle of the finite range when none is given.
    default = filters.contour(image, "s")
    assert np.allclose(default.array("iso_value"), (values.min() + values.max()) / 2)
    with pytest.raises(FilterError):
        filters.contour(image, "inner", [0.5])  # labels are categories, not numbers
    with pytest.raises(FilterError):
        filters.contour(image, "s", [1.0] * 33)


def test_contour_component_and_magnitude_selection():
    x, y, z = grid_coords((12, 12, 12))
    vectors = np.stack([x - 5.5, y - 5.5, z - 5.5], axis=-1)
    image = ImageData((12, 12, 12))
    image.add_field("P", vectors, tensor="vector", component_names=("x", "y", "z"))
    frozen(image)
    magnitude = filters.contour(image, {"name": "P", "component": None}, [4.0])
    assert np.allclose(np.linalg.norm(magnitude.points - 5.5, axis=1), 4.0, atol=0.15)
    plane = filters.contour(image, {"name": "P", "component": 0}, [1.25])
    assert np.allclose(plane.points[:, 0], 5.5 + 1.25, atol=1e-5)


def test_contour_with_origin_spacing_direction_and_nan():
    values = sphere_distance(24)
    values[0, 0, 0] = np.nan
    rotation = (0.0, -1.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0)  # grid x -> physical y, grid y -> -x
    image = scalar_image(values, origin=(1.0e6, -2.0e6, 3.0), spacing=(0.5, 0.5, 0.5), direction=rotation)
    warnings = []
    poly = filters.contour(image, "s", [6.0], warn=lambda message, code, **kw: warnings.append(code))
    assert "nonfinite_samples" in warnings
    centre = np.array(image.point(11.5, 11.5, 11.5))
    radius = np.linalg.norm(poly.points - centre, axis=1)
    assert np.abs(radius - 3.0).max() < 0.1  # 6 grid units x 0.5 spacing, far from the origin
    normals = poly.array("Normals").astype(np.float64)
    radial = (poly.points - centre) / radius[:, None]
    assert abs(np.einsum("ij,ij->i", normals, radial)).min() > 0.9  # rotated with the grid


# ---------------------------------------------------------------------------
# slices


def test_arbitrary_plane_slice_of_a_linear_field_matches_the_plane():
    dims, origin, spacing = (20, 16, 12), (-3.0, 2.0, 10.0), (0.5, 0.25, 1.0)
    x, y, z = grid_coords(dims, origin, spacing)
    linear = 2.0 * x - 3.0 * y + 0.5 * z + 1.0
    image = scalar_image(linear, origin, spacing)
    image.add_field("f32", linear.astype(np.float32))
    image.add_field("zone", (x > 1).astype(np.int8), tensor="label",
                    categories=(Category(0, "left"), Category(1, "right")))
    image.add_field("cellz", np.arange(11 * 15 * 19, dtype=np.float64).reshape(11, 15, 19), association="cell")
    frozen(image)
    normal = np.array([1.0, 2.0, -0.5])
    plane_origin = [0.3, 4.0, 15.2]
    poly = filters.slice_plane(image, plane_origin, normal.tolist())
    n = normal / np.linalg.norm(normal)
    assert poly.n_points > 50 and poly.polys.n_cells > 50 and poly.lines.n_cells == 0
    assert np.abs((poly.points - plane_origin) @ n).max() < 1e-9
    p = poly.points
    expected = 2.0 * p[:, 0] - 3.0 * p[:, 1] + 0.5 * p[:, 2] + 1.0
    assert np.abs(poly.array("s")[:, 0] - expected).max() < 1e-5  # VTK cuts images with float32 points
    assert poly.fields["s"].unit == "V" and poly.array("f32").dtype == np.float32
    zone = poly.array("zone")[:, 0]
    assert poly.fields["zone"].is_label and set(np.unique(zone)) <= {0, 1}
    far = np.abs(p[:, 0] - 1) > 0.26  # away from the jump: nearest sample = the side of the point
    assert np.array_equal(zone[far], (p[far, 0] > 1).astype(np.int8))
    assert poly.fields["cellz"].association == "cell" and len(poly.array("cellz")) == poly.polys.n_cells
    centre = filters.slice_plane(image)  # default: through the centre, normal z
    assert np.allclose(centre.points[:, 2], image.bounds()[0][2] + 5.5)
    with pytest.raises(FilterError):
        filters.slice_plane(image, normal=[0, 0, 0])
    warnings = []
    empty = filters.slice_plane(image, [0, 0, 1000], [0, 0, 1], warn=lambda m, code, **kw: warnings.append(code))
    assert empty.n_points == 0 and warnings == ["empty_result"]


def test_axis_slice_is_exact_and_keeps_labels():
    x, y, z = grid_coords((6, 5, 4), (1.0, 2.0, 3.0), (0.5, 1.0, 2.0))
    image = scalar_image(x + 10 * y + 100 * z, (1.0, 2.0, 3.0), (0.5, 1.0, 2.0))
    image.add_field("lab", (z > 5).astype(np.int16), tensor="label", categories=(Category(0, "a"), Category(1, "b")))
    frozen(image)
    plane = filters.slice_axis(image, "y", 3)
    assert plane.dimensions == (6, 1, 4) and plane.origin == (1.0, 5.0, 3.0) and plane.spacing == image.spacing
    assert np.array_equal(plane.array("s")[:, 0, :, 0], image.array("s")[:, 3, :, 0])
    assert "labels" in plane.kinds() and plane.fields["lab"].categories[1].name == "b"
    middle = filters.slice_axis(image, "z", None, fields=["s"])
    assert middle.dimensions == (6, 5, 1) and list(middle.fields) == ["s"] and middle.origin[2] == 3.0 + 2 * 2.0
    with pytest.raises(FilterError):
        filters.slice_axis(image, "x", 6)


# ---------------------------------------------------------------------------
# crop / sample / calculator / threshold


def test_crop_keeps_origin_spacing_and_cell_fields():
    x, y, z = grid_coords((10, 8, 6), (1.0, -1.0, 0.5), (0.1, 0.2, 0.3))
    image = scalar_image(x + y + z, (1.0, -1.0, 0.5), (0.1, 0.2, 0.3))
    image.add_field("c", np.arange(5 * 7 * 9, dtype=np.int32).reshape(5, 7, 9), association="cell")
    frozen(image)
    out = filters.crop(image, [2, 5, None, 3, 4, 99])
    assert out.dimensions == (4, 4, 2)
    assert np.allclose(out.origin, image.point(2, 0, 4)) and out.spacing == image.spacing
    assert np.array_equal(out.array("s"), image.array("s")[4:6, 0:4, 2:6])
    assert out.array("s").flags.c_contiguous and out.array("c").shape == (1, 3, 3, 1)
    assert np.array_equal(out.array("c")[..., 0], image.array("c")[4:5, 0:3, 2:5, 0])
    assert out.bounds()[0] == pytest.approx(image.point(2, 0, 4))
    assert out.provenance is image.provenance and out.time.step == 7
    with pytest.raises(FilterError):
        filters.crop(image, [5, 2, None, None, None, None])
    same = filters.crop(image, None)
    assert same.dimensions == image.dimensions


def test_sample_stride_and_growth():
    image = scalar_image(np.arange(9 * 10 * 11, dtype=np.float64).reshape(9, 10, 11), spacing=(1.0, 2.0, 3.0))
    out, steps = filters.sample(image, (2, 3, 4))
    assert steps == (2, 3, 4) and out.dimensions == (6, 4, 3) and out.spacing == (2.0, 6.0, 12.0)
    assert np.array_equal(out.array("s"), image.array("s")[::4, ::3, ::2])
    grown, steps = filters.sample(image, (1, 1, 1), max_points=100)
    assert steps == (3, 3, 3) and math.prod(grown.dimensions) <= 100  # f = 2 gives 6*5*5 = 150
    assert filters.effective_stride((10, 10, 10), (1, 2, 1), 1) == (10, 20, 10)


def test_calculator_operations():
    x, y, z = grid_coords((4, 3, 2))
    vectors = np.stack([x, y, z + 1], axis=-1)
    image = ImageData((4, 3, 2))
    image.add_field("P", vectors, tensor="vector", unit="C/m2", quantity="polarization",
                    component_names=("x", "y", "z"))
    image.add_field("a", x, unit="m")
    image.add_field("b", y, unit="m")
    frozen(image)
    out = filters.calculator(image, "magnitude", field="P")
    assert np.allclose(out.array("P_magnitude")[..., 0], np.linalg.norm(vectors, axis=-1))
    assert out.fields["P_magnitude"].unit == "C/m2" and "P" in out.fields and "P_magnitude" not in image.fields
    out = filters.calculator(image, "component", field={"name": "P"}, component=1)
    assert np.array_equal(out.array("P_y"), vectors[..., 1:2])
    out = filters.calculator(image, "scale", field="P", factor=2.0, result="twice")
    assert np.allclose(out.array("twice"), 2 * vectors) and out.fields["twice"].unit == "unspecified"
    assert filters.calculator(image, "scale", field="P", factor=1.0).fields["P_scaled"].unit == "C/m2"
    out = filters.calculator(image, "normalize", field="P", keep_input=False)
    assert list(out.fields) == ["P_normalized"] and out.fields["P_normalized"].unit == "1"
    assert np.allclose(np.linalg.norm(out.array("P_normalized"), axis=-1), 1.0)
    out = filters.calculator(image, "compose", fields=["a", "b"], compose_as="vector", result="ab")
    assert out.fields["ab"].tensor == "vector" and out.fields["ab"].component_names == ("x", "y")
    assert out.fields["ab"].unit == "m" and np.array_equal(out.array("ab")[..., 1], y)
    with pytest.raises(FilterError):
        filters.calculator(image, "compose", fields=["a", "P"])
    with pytest.raises(FilterError):
        filters.calculator(image, "component", field="P", component=3)
    first = filters.calculator(image, "magnitude")  # null field: the first numeric field
    assert "P_magnitude" in first.fields


def test_threshold_ranges_labels_and_nan():
    values = np.arange(24, dtype=np.float64).reshape(2, 3, 4)
    values[0, 0, 0] = np.nan
    image = scalar_image(values)
    image.add_field("lab", (np.arange(24) % 3).reshape(2, 3, 4).astype(np.int16), tensor="label",
                    categories=tuple(Category(v, f"c{v}") for v in range(3)))
    frozen(image)
    out = filters.threshold(image, "s", lower=5, upper=10)
    mask = out.array("mask")[..., 0]
    assert out.fields["mask"].dtype == "uint8" and "labels" in out.kinds()
    assert np.array_equal(mask, ((values >= 5) & (values <= 10)).astype(np.uint8))
    inverted = filters.threshold(image, "s", lower=5, upper=10, invert=True, output="outside").array("outside")
    assert inverted[0, 0, 0, 0] == 0 and inverted.sum() == 24 - 1 - 6  # NaN stays outside
    by_label = filters.threshold(image, "lab", labels=[2]).array("mask")[..., 0]
    assert np.array_equal(by_label, (image.array("lab")[..., 0] == 2).astype(np.uint8))
    assert [c.name for c in out.fields["mask"].categories] == ["outside", "inside"]
    with pytest.raises(FilterError):
        filters.threshold(image, "s", labels=[1])


# ---------------------------------------------------------------------------
# glyph source


def test_glyph_counts_equal_numpy_counts_under_stride_and_mask():
    rng = np.random.default_rng(3)
    dims = (13, 11, 9)
    vectors = rng.normal(size=(9, 11, 13, 3))
    labels = rng.integers(-1, 4, size=(9, 11, 13)).astype(np.int16)
    image = ImageData(dims, (1.0, 2.0, 3.0), (0.5, 0.5, 2.0), provenance=Provenance(agent={"node": "src"}))
    image.add_field("P", vectors, tensor="vector", unit="C/m2")
    image.add_field("domain", labels, tensor="label", categories=tuple(Category(v, f"d{v}") for v in range(-1, 4)))
    frozen(image)
    poly, steps = filters.glyph_source(image, "P", stride=(2, 3, 1), max_points=10**6, magnitude_range=[0.5, 2.0],
                                       mask_field="domain", mask_labels=[1, 3], attributes=["domain"])
    lattice = (slice(None, None, 1), slice(None, None, 3), slice(None, None, 2))
    magnitude = np.linalg.norm(vectors[lattice], axis=-1)
    keep = (magnitude >= 0.5) & (magnitude <= 2.0) & np.isin(labels[lattice], [1, 3])
    assert steps == (2, 3, 1) and poly.n_points == int(keep.sum()) and "points" in poly.kinds()
    assert np.allclose(poly.array("P"), vectors[lattice][keep]) and set(np.unique(poly.array("domain"))) <= {1, 3}
    assert np.allclose(poly.array("magnitude")[:, 0], magnitude[keep])
    k, j, i = np.nonzero(keep)
    assert np.allclose(poly.points, np.stack([1 + 0.5 * 2 * i, 2 + 0.5 * 3 * j, 3 + 2.0 * k], axis=1))
    assert poly.attrs["sample_spacing"] == 1.0 and poly.verts.n_cells == poly.n_points
    unmasked, _ = filters.glyph_source(image, None, mask_field="domain", max_points=10**6)
    assert unmasked.n_points == int((labels != 0).sum())  # null mask_labels: nonzero values
    capped, steps = filters.glyph_source(image, "P", max_points=100)
    assert capped.n_points <= 100 and steps == (3, 3, 3)
    drawn, _ = filters.glyph_source(image, "P", sampling="random", max_points=50, seed=5)
    again, _ = filters.glyph_source(image, "P", sampling="random", max_points=50, seed=5)
    assert drawn.n_points == 50 and np.array_equal(drawn.points, again.points)
    assert len({tuple(p) for p in drawn.points}) == 50
    with pytest.raises(FilterError):
        filters.glyph_source(image, "domain")


# ---------------------------------------------------------------------------
# label surfaces


def block_labels(n=(10, 10, 10)):
    nx, ny, nz = n
    labels = np.full((nz, ny, nx), 2, dtype=np.int16)
    labels[:, :5, :] = 1
    labels[:2] = 0          # substrate layers (excluded by default)
    labels[-1] = -1         # "air"
    return labels


def label_image(labels, spacing=(1.0, 1.0, 1.0), origin=(0.0, 0.0, 0.0)):
    nz, ny, nx = labels.shape
    image = ImageData((nx, ny, nz), origin, spacing, provenance=Provenance(agent={"node": "src"}))
    categories = (Category(-1, "unclassified", color=(1, 1, 1)), Category(0, "substrate", color=(.75, .75, .75)),
                  Category(1, "T[100]", color=(1, 0, 0), family="T"), Category(2, "T[-100]", color=(0, 1, 1),
                                                                                family="T"))
    image.add_field("domain", labels, tensor="label", categories=categories, palette="stk:cubic-26-orientation",
                    unit="1", quantity="domain_variant")
    return frozen(image)


def chamfered_box_area(a, b, c):
    """Area of the unsmoothed 0.5-contour of a box indicator of a x b x c points (edges and corners cut at 45°)."""
    faces = 2 * ((a - 1) * (b - 1) + (b - 1) * (c - 1) + (a - 1) * (c - 1))
    edges = 4 * ((a - 1) + (b - 1) + (c - 1)) * 0.5 * math.sqrt(2)
    corners = 8 * math.sqrt(3) / 8
    return faces + edges + corners


def test_label_surfaces_are_closed_and_block_area_is_known():
    image = label_image(block_labels())
    raw = filters.label_surfaces(image, smoothing="none")
    labels = raw.array("label")[:, 0]
    assert raw.fields["label"].association == "cell" and raw.fields["label"].dtype == "int32"
    assert sorted(np.unique(labels).tolist()) == [1, 2] and raw.attrs["label_surfaces"]["labels"] == [1, 2]
    assert raw.fields["label"].categories == image.fields["domain"].categories
    assert raw.fields["label"].palette == "stk:cubic-26-orientation"
    tris = raw.polys.connectivity.reshape(-1, 3)
    for value, (a, b, c) in ((1, (10, 5, 7)), (2, (10, 5, 7))):
        own = tris[labels == value]
        assert open_edges(raw.points, own) == 0
        area = 0.5 * np.linalg.norm(np.cross(raw.points[own[:, 1]] - raw.points[own[:, 0]],
                                             raw.points[own[:, 2]] - raw.points[own[:, 0]]), axis=1).sum()
        assert area == pytest.approx(chamfered_box_area(a, b, c), rel=1e-6)
        assert signed_volume(raw.points, own) > 0  # outward-facing triangles
    smooth = filters.label_surfaces(image)  # windowed sinc, 30 iterations, pass band 0.1
    tris = smooth.polys.connectivity.reshape(-1, 3)
    labels = smooth.array("label")[:, 0]
    for value in (1, 2):
        own = tris[labels == value]
        assert open_edges(smooth.points, own) == 0
        area = 0.5 * np.linalg.norm(np.cross(smooth.points[own[:, 1]] - smooth.points[own[:, 0]],
                                             smooth.points[own[:, 2]] - smooth.points[own[:, 0]]), axis=1).sum()
        assert area == pytest.approx(chamfered_box_area(10, 5, 7), rel=0.1)  # VTK 9.3: -7 %, 9.7: -4 %
    normals = smooth.array("Normals")
    assert normals.shape == (smooth.n_points, 3) and np.allclose(np.linalg.norm(normals, axis=1), 1, atol=1e-3)
    assert smooth.provenance.agent == {"node": "src"}


def test_label_surfaces_sphere_area_and_geometry():
    n = 48
    labels = np.where(sphere_distance(n) <= 12, 3, -1).astype(np.int16)
    image = ImageData((n, n, n), (100.0, 200.0, 300.0), (0.5, 0.5, 0.5))
    image.add_field("domain", labels, tensor="label", categories=(Category(-1, "none"), Category(3, "ball")))
    frozen(image)
    poly = filters.label_surfaces(image, "domain")
    centre = np.array(image.point(23.5, 23.5, 23.5))
    radius = np.linalg.norm(poly.points - centre, axis=1)
    assert np.abs(radius.mean() - 6.0) < 0.1  # 12 grid units x 0.5
    area = triangle_area(poly)
    assert area == pytest.approx(4 * math.pi * 6.0 ** 2, rel=0.03)
    assert open_edges(poly.points, poly.polys.connectivity.reshape(-1, 3)) == 0


def test_label_surfaces_options():
    labels = block_labels((8, 8, 8))
    image = label_image(labels)
    explicit = filters.label_surfaces(image, labels=[0, 2], smoothing="laplacian", smooth_iterations=5)
    assert sorted(np.unique(explicit.array("label")).tolist()) == [0, 2]
    everything = filters.label_surfaces(image, exclude=[])
    assert sorted(np.unique(everything.array("label")).tolist()) == [-1, 0, 1, 2]
    no_normals = filters.label_surfaces(image, compute_normals=False, threads=1)
    assert "Normals" not in no_normals.fields
    open_surface = filters.label_surfaces(image, labels=[2], close_boundaries=False, smoothing="none")
    tris = open_surface.polys.connectivity.reshape(-1, 3)
    assert open_edges(open_surface.points, tris) > 0  # not closed where the label meets the box
    warnings = []
    empty = filters.label_surfaces(image, labels=[7], warn=lambda m, code, **kw: warnings.append(code))
    assert empty.n_points == 0 and empty.polys.n_cells == 0 and warnings == ["empty_result"]
    assert len(empty.array("label")) == 0
    plain = ImageData((4, 4, 4))
    plain.add_field("s", np.zeros((4, 4, 4)))
    with pytest.raises(FilterError) as error:
        filters.label_surfaces(plain)
    assert error.value.code == "kind_mismatch"
    same = filters.label_surfaces(image, threads=1)
    parallel = filters.label_surfaces(image, threads=4)
    assert np.array_equal(same.points, parallel.points)  # deterministic order whatever the thread count


def test_label_surfaces_cell_labels():
    labels = np.zeros((5, 5, 5), dtype=np.int16)
    labels[1:4, 1:4, 1:4] = 1
    image = ImageData((6, 6, 6), (0.0, 0.0, 0.0), (2.0, 2.0, 2.0))
    image.add_field("cells", labels, association="cell", tensor="label",
                    categories=(Category(0, "matrix"), Category(1, "grain")))
    poly = filters.label_surfaces(frozen(image), smoothing="none")
    lo, hi = poly.points.min(axis=0), poly.points.max(axis=0)
    # cell centres of cells 1..3 are at 3, 5, 7; the 0.5 contour lies half a spacing further out.
    assert np.allclose(lo, 2.0) and np.allclose(hi, 8.0)


# ---------------------------------------------------------------------------
# streamlines (stretch)


def test_streamlines_are_straight_in_a_uniform_field():
    direction = np.array([1.0, 2.0, 0.5]) / np.linalg.norm([1.0, 2.0, 0.5])
    image = ImageData((20, 20, 20), (5.0, -5.0, 0.0), (0.5, 0.5, 0.5))
    image.add_field("v", np.broadcast_to(direction, (20, 20, 20, 3)).copy(), tensor="vector")
    frozen(image)
    poly = filters.streamlines(image, "v", seed_count=12, seed_radius=1.0, seed=4)
    assert poly.lines.n_cells >= 10 and poly.n_points > 12 * 5
    offsets, connectivity = poly.lines.offsets, poly.lines.connectivity
    for start, stop in zip(offsets[:-1], offsets[1:]):
        points = poly.points[connectivity[start:stop]]
        steps = np.diff(points, axis=0)
        steps = steps[np.linalg.norm(steps, axis=1) > 1e-9]
        cosines = (steps / np.linalg.norm(steps, axis=1)[:, None]) @ direction
        assert cosines.min() > 1 - 1e-6  # straight, along the field
    assert np.allclose(poly.array("v"), direction, atol=1e-9)
    both = filters.streamlines(image, "v", seed_count=3, direction="both", seed=1)
    assert both.lines.n_cells >= 3


# ---------------------------------------------------------------------------
# Performance (approved plan: 26 label surfaces on 128^3 <= 4 s)


@pytest.mark.perf
@pytest.mark.skipif(os.environ.get("STK_PERF") != "1", reason="performance benchmark: set STK_PERF=1")
def test_perf_label_surfaces_26_labels_128_cubed():
    n = 128
    third = np.arange(n) * 3 // n
    labels = (third[:, None, None] * 9 + third[None, :, None] * 3 + third[None, None, :]).astype(np.int16)
    labels[labels == 0] = -1  # 26 variants and one unclassified block
    image = ImageData((n, n, n))
    image.add_field("domain", labels, tensor="label",
                    categories=tuple(Category(v, f"v{v}") for v in range(-1, 27)))
    frozen(image)
    started = time.perf_counter()
    poly = filters.label_surfaces(image)
    elapsed = time.perf_counter() - started
    print(f"\n26 label surfaces on 128^3: {elapsed:.2f} s, {poly.n_points} points, {poly.polys.n_cells} triangles")
    assert poly.attrs["label_surfaces"]["labels"] == list(range(1, 27))
    assert elapsed <= 4.0 * float(os.environ.get("STK_PERF_FACTOR", "1")), elapsed
