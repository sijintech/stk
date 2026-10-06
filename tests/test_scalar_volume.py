"""Scientific selection and display encoding of the signed scalar-volume preset."""
import pytest

np = pytest.importorskip("numpy")

from suan.graph import catalog  # noqa: E402
from suan.graph.evaluator import EvaluationFailed, evaluate  # noqa: E402
from suan.graph.registry import GraphError  # noqa: E402
from suan.graph.resolve import LocalDirResolver  # noqa: E402
from suan.graph.schema import GraphValidationError  # noqa: E402
from suan.graph.service import MemoryBlobSink, evaluate_request  # noqa: E402
from suan.render.layers import Layer, Scene  # noqa: E402
from suan.render.payload import PayloadError, decode, encode_scene  # noqa: E402


@pytest.fixture
def registry():
    return catalog.build_registry(entry_points=False)


def signed_values():
    # Non-cubic shape and asymmetric signed data detect axis swaps and abs/norm.
    return (np.arange(24, dtype=np.float64).reshape(2, 3, 4) * 0.75 - 7.25)


def write_field(folder, values):
    np.save(folder / "field.npy", values)


def scene(folder, registry, parameters=None, *, graph=None):
    result = evaluate(graph or catalog.load_preset("scalar-volume"), registry=registry,
                      resolver=LocalDirResolver({"data": folder}), outputs=["view"],
                      parameters={"path": "field.npy", "field": "field", **(parameters or {})})
    return {layer.id: layer for layer in result.outputs["view"].layers}


def delivered(folder, registry, parameters=None, *, profile="desktop", budget=None):
    sink = MemoryBlobSink()
    request = {"preset": "scalar-volume", "outputs": ["view"], "profile": profile,
               "parameters": {"path": "field.npy", "field": "field", **(parameters or {})}}
    if budget is not None:
        request["budget"] = budget
    result = evaluate_request(request, registry=registry, resolver=LocalDirResolver({"data": folder}),
                              cache_dir=folder / "cache", blob_sink=sink)
    return result, decode(result["outputs"]["view"]["manifest"], sink.blobs)


def physical(payload):
    volume = payload.layer("volume")
    return payload.array(volume["data"]).astype(np.float64) * volume["value_scale"] + volume["value_offset"]


@pytest.mark.parametrize("format", ["npy", "dat"])
def test_scalar_selection_keeps_signed_samples_and_xyz_orientation(tmp_path, registry, format):
    values = signed_values()
    if format == "npy":
        write_field(tmp_path, values)
        path = "field.npy"
    else:
        from suan.data.dat import write_dat
        path = "field.00000000.dat"
        write_dat(tmp_path / path, values)
    layers = scene(tmp_path, registry, {"path": path})
    np.testing.assert_array_equal(layers["volume"].geometry["data"], values.transpose(2, 1, 0))
    assert layers["volume"].geometry["field"] == "field_0"
    # The signed preset centres its diverging colormap on 0 by default.
    bound = max(abs(values.min()), abs(values.max()))
    assert layers["bar"].props["range"] == [-bound, bound]
    assert layers["bar"].props["title"] == "field_0 [unspecified]"


@pytest.mark.parametrize("component", [0, 1, 2, 1.0])
def test_vector_selects_exact_component_without_magnitude(tmp_path, registry, component):
    base = signed_values()
    vectors = np.stack([base, -2 * base - 4, base * 3 + 0.5], axis=-1)
    write_field(tmp_path, vectors)
    actual = scene(tmp_path, registry, {"component": component})["volume"].geometry["data"]
    expected = vectors[..., int(component)].transpose(2, 1, 0)
    np.testing.assert_array_equal(actual, expected)
    assert (actual < 0).any()
    assert not np.allclose(actual, np.linalg.norm(vectors, axis=-1).transpose(2, 1, 0))


def test_existing_volume_still_computes_magnitude(tmp_path, registry):
    values = signed_values()
    write_field(tmp_path, values)
    graph = catalog.load_preset("volume")
    result = evaluate(graph, registry=registry, resolver=LocalDirResolver({"data": tmp_path}),
                      outputs=["view"], parameters={"path": "field.npy"})
    np.testing.assert_array_equal(result.outputs["view"].layer("volume").geometry["data"],
                                  np.abs(values).transpose(2, 1, 0))


@pytest.mark.parametrize("parameter,value", [
    ("field", None), ("field", {"name": "field"}), ("field", True), ("field", ""),
    ("field", "a/b"), ("field", "a.b"), ("field", "f" * 129),
    ("component", None), ("component", True), ("component", -1), ("component", 0.5),
    ("component", "magnitude"), ("component", 4096),
    ("unit", ""), ("unit", 1), ("unit", []), ("unit", {}),
], ids=["field-null", "field-object", "field-bool", "field-empty", "field-slash", "field-dot", "field-long",
         "component-null", "component-bool", "component-negative", "component-fraction", "component-magnitude",
         "component-limit", "unit-empty", "unit-number", "unit-array", "unit-object"])
def test_invalid_parameters_fail_before_source_read(tmp_path, registry, parameter, value):
    with pytest.raises(GraphValidationError):
        scene(tmp_path, registry, {parameter: value})  # No source file exists.


@pytest.mark.parametrize("components,index", [(1, 1), (3, 3), (3, 4095)])
def test_component_must_exist_even_on_a_scalar(tmp_path, registry, components, index):
    write_field(tmp_path, np.zeros((2, 3, 4, components)))
    with pytest.raises(EvaluationFailed, match="outside") as error:
        scene(tmp_path, registry, {"component": index})
    assert error.value.node == "component"


def test_highest_supported_component_can_be_selected(tmp_path, registry):
    values = (np.arange(4096, dtype=np.float64) - 5000).reshape(1, 1, 1, 4096)
    write_field(tmp_path, values)
    actual = scene(tmp_path, registry, {"component": 4095})["volume"].geometry["data"]
    np.testing.assert_array_equal(actual, [[[-905.]]])


def test_missing_field_never_falls_back_to_existing_numeric_data(tmp_path, registry):
    write_field(tmp_path, signed_values())
    with pytest.raises(EvaluationFailed, match="No field 'missing'") as error:
        scene(tmp_path, registry, {"field": "missing"})
    assert error.value.node == "component"


@pytest.mark.parametrize("values", [np.full((2, 3, 4), "text"), np.zeros((2, 3)),
                                     np.zeros((2, 3, 4), dtype=np.float16)],
                         ids=["nonnumeric", "not-volume", "unsupported-precision"])
def test_reader_rejects_nonnumeric_or_wrong_array_shape(tmp_path, registry, values):
    write_field(tmp_path, values)
    with pytest.raises(EvaluationFailed, match="NPY fields must be numeric") as error:
        scene(tmp_path, registry)
    assert error.value.node == "src"


def test_vti_exact_named_numeric_array_and_string_array_rejection(tmp_path, registry):
    vtk = pytest.importorskip("vtk")
    from vtk.util.numpy_support import numpy_to_vtk
    image = vtk.vtkImageData()
    image.SetDimensions(2, 3, 4)
    values = signed_values()
    for name, data in (("other", np.full((2, 3, 4), 123.)), ("chosen", values)):
        array = numpy_to_vtk(np.ascontiguousarray(data.transpose(2, 1, 0)).reshape(-1), deep=True)
        array.SetName(name)
        image.GetPointData().AddArray(array)
    strings = vtk.vtkStringArray()
    strings.SetName("notes")
    for _ in range(24):
        strings.InsertNextValue("not a scalar")
    image.GetPointData().AddArray(strings)
    writer = vtk.vtkXMLImageDataWriter()
    writer.SetFileName(str(tmp_path / "fields.vti"))
    writer.SetInputData(image)
    assert writer.Write() == 1
    layers = scene(tmp_path, registry, {"path": "fields.vti", "field": "chosen"})
    np.testing.assert_array_equal(layers["volume"].geometry["data"], values.transpose(2, 1, 0))
    with pytest.raises(EvaluationFailed, match="No field 'notes'"):
        scene(tmp_path, registry, {"path": "fields.vti", "field": "notes"})


@pytest.fixture
def rich_file(tmp_path):
    pytest.importorskip("h5py")
    from suan.data.model import ImageData
    from suan.data.vtkhdf import write_vtkhdf
    image = ImageData((2, 3, 4), id="science")
    values = signed_values()
    image.add_field("temperature", values, layout="xyzc", unit="K", quantity="temperature")
    image.add_field("velocity", np.stack([values, -values - 2, values * 4], axis=-1), layout="xyzc",
                    tensor="vector", component_names=("x", "y", "z"), unit="m/s")
    image.add_field("cells", np.zeros((3, 2, 1)), association="cell")
    image.add_field("labels", np.ones((4, 3, 2), dtype=np.int32),
                    categories=[{"value": 1, "name": "phase"}])
    write_vtkhdf(tmp_path / "science.vtkhdf", image)
    return image


@pytest.mark.parametrize("field,message", [("cells", "No field 'cells'"), ("labels", "label field"),
                                           ("not_here", "No field 'not_here'")])
def test_explicit_field_rejects_cell_label_or_missing_without_fallback(tmp_path, registry, rich_file, field, message):
    with pytest.raises(EvaluationFailed, match=message):
        scene(tmp_path, registry, {"path": "science.vtkhdf", "field": field})


def test_cell_only_image_and_polydata_cannot_be_used_as_point_volume(tmp_path, registry):
    pytest.importorskip("h5py")
    from suan.data.model import ImageData, PolyData
    from suan.data.vtkhdf import write_vtkhdf
    image = ImageData((2, 3, 4))
    image.add_field("field", np.ones((3, 2, 1)), association="cell")
    write_vtkhdf(tmp_path / "cell.vtkhdf", image)
    with pytest.raises(EvaluationFailed, match="no point fields"):
        scene(tmp_path, registry, {"path": "cell.vtkhdf"})
    poly = PolyData(np.array([[0., 0, 0], [1., 0, 0]]))
    poly.add_field("field", np.array([-3., 7.]))
    write_vtkhdf(tmp_path / "poly.vtkhdf", poly)
    with pytest.raises(EvaluationFailed) as error:
        scene(tmp_path, registry, {"path": "poly.vtkhdf"})
    assert error.value.code == "kind_mismatch"


@pytest.mark.parametrize("unit,expected_unit", [(None, "m/s"), ("cm/s", "cm/s")])
def test_source_unit_preserved_or_relabelled_without_numeric_conversion(tmp_path, registry, rich_file,
                                                                      unit, expected_unit):
    original = rich_file.array("velocity").copy()
    parameters = {"path": "science.vtkhdf", "field": "velocity", "component": 1, "unit": unit}
    layers = scene(tmp_path, registry, parameters)
    np.testing.assert_array_equal(layers["volume"].geometry["data"], original[..., 1])
    assert layers["volume"].geometry["unit"] == expected_unit
    assert layers["bar"].props["title"] == f"velocity_y [{expected_unit}]"
    _, payload = delivered(tmp_path, registry, parameters)
    np.testing.assert_allclose(physical(payload), original[..., 1].reshape(-1), rtol=1e-7)
    assert payload.layer("volume")["unit"] == expected_unit
    assert payload.layer("bar")["unit"] == expected_unit
    from suan.data.vtkhdf import read_vtkhdf
    reread = read_vtkhdf(tmp_path / "science.vtkhdf")
    assert reread.field("velocity").unit == "m/s"
    np.testing.assert_array_equal(reread.array("velocity"), original)


@pytest.mark.parametrize("profile,kind", [("desktop", "f32"), ("phone", "u8"), ("web", "u16")])
@pytest.mark.parametrize("case", ["mixed-sign", "all-negative", "constant", "nonfinite"])
def test_complete_service_payload_preserves_signed_range_with_documented_precision(tmp_path, registry,
                                                                                  profile, kind, case):
    values = signed_values()
    if case == "all-negative":
        values = -np.arange(1, 25, dtype=np.float64).reshape(2, 3, 4)
    elif case == "constant":
        values.fill(-2.5)
    elif case == "nonfinite":
        values.reshape(-1)[:3] = [np.nan, np.inf, -np.inf]
    write_field(tmp_path, values)
    # Precision is checked against the data range; the default symmetric range is tested separately.
    _, payload = delivered(tmp_path, registry, {"range_mode": "data"}, profile=profile)
    volume, bar = payload.layer("volume"), payload.layer("bar")
    expected = values.transpose(2, 1, 0).reshape(-1)
    finite = np.isfinite(expected)
    lo, hi = expected[finite].min(), expected[finite].max()
    assert payload.accessor(volume["data"])["type"] == kind
    assert volume["value_range"] == [lo, hi]
    assert volume["transfer_function"]["range"] == bar["range"] == [lo, hi]
    restored = physical(payload)
    if kind == "f32":
        np.testing.assert_allclose(restored, expected, rtol=1e-7, atol=0, equal_nan=True)
    else:
        step = volume["value_scale"]
        np.testing.assert_allclose(restored[finite], expected[finite], rtol=0, atol=step / 2 + 1e-12)
        # Existing quantization policy: NaN/-Inf -> minimum, +Inf -> maximum.
        assert np.all(restored[np.isnan(expected) | np.isneginf(expected)] == lo)
        assert np.all(restored[np.isposinf(expected)] == hi)
        assert restored[finite].min() == pytest.approx(lo)
        assert restored[finite].max() == pytest.approx(hi)


def test_signed_preset_centres_its_diverging_colormap_on_zero_unless_asked_otherwise(tmp_path, registry):
    values = signed_values()  # -7.25 .. 10.0
    write_field(tmp_path, values)
    graph = catalog.load_preset("scalar-volume")
    defaults = {p["name"]: p["default"] for p in graph["parameters"]}
    assert defaults["colormap"] == "coolwarm" and defaults["range_mode"] == "symmetric"
    _, payload = delivered(tmp_path, registry)
    volume, bar = payload.layer("volume"), payload.layer("bar")
    assert volume["value_range"] == [-7.25, 10.0]  # stored samples keep the exact data range
    assert volume["transfer_function"]["range"] == bar["range"] == [-10.0, 10.0]
    # Explicit ends win over the automatic mode; the other end stays symmetric.
    _, payload = delivered(tmp_path, registry, {"range": [None, 4.0]})
    assert payload.layer("volume")["transfer_function"]["range"] == [-10.0, 4.0]
    _, payload = delivered(tmp_path, registry, {"range_mode": "data"})
    assert payload.layer("volume")["transfer_function"]["range"] == payload.layer("bar")["range"] == [-7.25, 10.0]
    write_field(tmp_path, np.abs(values) + 1.0)  # all positive: still centred on 0 when asked
    _, payload = delivered(tmp_path, registry)
    assert payload.layer("volume")["transfer_function"]["range"] == [-11.0, 11.0]


def test_volume_node_keeps_the_data_range_by_default(tmp_path, registry):
    """range_mode is additive: graphs that do not set it keep the data min..max."""
    values = signed_values()
    write_field(tmp_path, values)
    graph = catalog.load_preset("scalar-volume")
    for node in graph["nodes"]:
        if node["id"] == "volume":
            node["params"].pop("range_mode")
    layers = scene(tmp_path, registry, graph=graph)
    assert layers["bar"].props["range"] == [values.min(), values.max()]


@pytest.mark.parametrize("profile,top", [("desktop", None), ("phone", 255), ("web", 65535)])
@pytest.mark.parametrize("has_finite", [False, True], ids=["all-missing", "constant-with-missing"])
def test_degenerate_range_keeps_existing_nonfinite_encoding_policy(tmp_path, registry, profile, top, has_finite):
    values = np.array([np.nan, np.inf, -np.inf, -2.5 if has_finite else np.nan]).reshape(1, 1, 4)
    write_field(tmp_path, values)
    _, payload = delivered(tmp_path, registry, {"range_mode": "data"}, profile=profile)
    volume = payload.layer("volume")
    lo = -2.5 if has_finite else 0.0
    assert volume["value_range"] == [lo, lo]
    assert volume["transfer_function"]["range"] == ([-2.5, -2.5] if has_finite else [0., 1.])
    if top is None:
        np.testing.assert_array_equal(physical(payload), values.reshape(-1))
    else:
        # Quantization has no missing mask. Nonfinite samples map to saturated
        # storage endpoints; for a degenerate range codeTop is NOT data maximum.
        assert volume["value_scale"] == 1.0 and volume["value_offset"] == lo
        np.testing.assert_array_equal(payload.array(volume["data"]), [0, top, 0, 0])
        np.testing.assert_array_equal(physical(payload), [lo, lo + top, lo, lo])


def test_field_component_unit_and_source_changes_invalidate_data_cache(tmp_path, registry, rich_file):
    parameters = {"path": "science.vtkhdf", "field": "velocity"}
    first, first_payload = delivered(tmp_path, registry, parameters)
    second, _ = delivered(tmp_path, registry, {**parameters, "colormap": "gray"})
    assert first["keys"]["component"] == second["keys"]["component"]
    assert "src" not in second["evaluated"] and "component" not in second["evaluated"]
    for overrides in ({"field": "temperature"}, {"component": 1}, {"unit": "cm/s"}):
        changed, _ = delivered(tmp_path, registry, {**parameters, **overrides})
        assert changed["keys"]["src"] == first["keys"]["src"]
        assert changed["keys"]["component"] != first["keys"]["component"]
        assert "component" in changed["evaluated"]
    from suan.data.vtkhdf import write_vtkhdf
    rich_file.field("velocity").values += 13
    write_vtkhdf(tmp_path / "science.vtkhdf", rich_file)
    changed, changed_payload = delivered(tmp_path, registry, parameters)
    assert changed["keys"]["src"] != first["keys"]["src"]
    np.testing.assert_allclose(physical(changed_payload), physical(first_payload) + 13)


def volume_scene(values, *, encoding="auto"):
    data = np.asarray(values, dtype=np.float64)
    return Scene(layers=[Layer("volume", id="volume", geometry={
        "grid": {"dimensions": list(reversed(data.shape)), "origin": [0, 0, 0], "spacing": [1, 1, 1]},
        "data": data, "encoding": encoding})])


@pytest.mark.parametrize("sign", [-1, 1])
def test_finite_float32_overflow_is_rejected_even_when_budget_would_remove_it(tmp_path, registry, sign):
    values = np.ones((4, 4, 4))
    values[1, 1, 1] = sign * 1e40  # Removed by stride 2, but must not hide invalid source conversion.
    for budget in (None, {"voxels": 8}):
        with pytest.raises(PayloadError, match="Finite volume values overflow float32") as error:
            encode_scene(volume_scene(values), profile="desktop", budget=budget)
        assert error.value.path == "/layers/volume/data"
    write_field(tmp_path, values)
    with pytest.raises(GraphError, match="Finite volume values overflow float32"):
        delivered(tmp_path, registry)


def test_float32_guard_is_bounded_and_handles_noncontiguous_input():
    values = np.ones((80, 81, 82))
    view = values[:, :, ::2]
    view[-1, -1, -1] = 1e40  # Beyond the first 65536-value validation chunk.
    assert not view.flags.c_contiguous
    with pytest.raises(PayloadError, match="overflow float32"):
        encode_scene(volume_scene(view), profile="desktop")


def test_representable_large_and_small_float32_values_are_retained():
    limit = float(np.finfo(np.float32).max)
    values = np.array([-limit, -1e-38, 0, 1e-38, limit]).reshape(1, 1, 5)
    payload = encode_scene(volume_scene(values), profile="desktop")
    restored = physical(payload)
    assert np.isfinite(restored).all()
    np.testing.assert_array_equal(restored, values.astype(np.float32).reshape(-1).astype(np.float64))
    assert payload.layer("volume")["value_range"] == [-limit, limit]


@pytest.mark.parametrize("profile", ["phone", "web"])
@pytest.mark.parametrize("values", [[-1e308, 1e308], [0, np.nextafter(0., 1.)]], ids=["span-overflow", "scale-underflow"])
def test_unrepresentable_quantized_range_fails_clearly(profile, values):
    with pytest.raises(PayloadError, match="quantization scale"):
        encode_scene(volume_scene(np.array(values).reshape(1, 1, 2)), profile=profile)


@pytest.mark.parametrize("profile", ["phone", "web"])
def test_quantized_values_are_not_incorrectly_limited_to_float32_range(profile):
    values = np.array([-1e40, 0, 1e40]).reshape(1, 1, 3)
    payload = encode_scene(volume_scene(values), profile=profile)
    out = payload.layer("volume")
    np.testing.assert_allclose(physical(payload), values.reshape(-1), rtol=0, atol=out["value_scale"] / 2 + 1e25)
    assert out["value_range"] == [-1e40, 1e40]
