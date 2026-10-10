"""Materials prediction models (S3a, docs/design/materials-models-s3.md): synthetic P-E loops and capacity fade, the
stk.dataset/1 contract, training on this computer (PyTorch CPU, skipped without it), the registry gate and prediction."""
import json
import time

import numpy as np
import pytest

from suan.materials import curves, datasets, service, synthetic, training
from test_desktop_bridge import bridge_env, inproc  # noqa: F401

try:
    import torch  # noqa: F401
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False
needs_torch = pytest.mark.skipif(not HAS_TORCH, reason="PyTorch (CPU) is an optional dependency")


def test_synthetic_loops_switch_below_the_curie_temperature_and_not_far_above():
    base = {"curie_temperature": np.array([700.0, 700.0]), "landau_a0": np.array([5e-3, 5e-3]),
            "landau_b": np.array([1e-3, 1e-3]), "e_max": np.array([200.0, 200.0]), "frequency": np.array([100.0, 100.0])}
    loops = synthetic.pe_loops({**base, "temperature": np.array([300.0, 900.0])})
    ferro, para = (curves.readout("pe_loop", list(loop), {"e_max": 200.0}) for loop in loops)
    # Single domain, quasi-static: P_s = sqrt(-a / 2b) = 31.6 and intrinsic E_c = 4/(3 sqrt 3) |a| P_s = 48.7 kV/cm.
    assert ferro["remanent_polarization"] == pytest.approx(31.6, rel=0.05)
    assert 48.7 * 0.95 < ferro["coercive_field"] < 48.7 * 1.25  # a little wider: 100 Hz is not fully quasi-static
    # Far above T_c only the lag behind the field leaves a thin loop.
    assert para["remanent_polarization"] < 2.0 and (para["coercive_field"] is None or para["coercive_field"] < 10)
    # The branches meet at the field's ends, and the up branch never exceeds the down branch.
    up, down = loops[0][:curves.PE_POINTS], loops[0][curves.PE_POINTS:]
    assert abs(up[-1] - down[-1]) < 1.0 and abs(up[0] - down[0]) < 1.0 and np.all(up <= down + 1e-6)
    # A faster sweep widens the loop (the domain lags the field).
    fast = synthetic.pe_loops({**base, "temperature": np.array([300.0, 300.0]), "frequency": np.array([100.0, 10000.0])})
    slow_ec, fast_ec = (curves.readout("pe_loop", list(loop), {"e_max": 200.0})["coercive_field"] for loop in fast)
    assert fast_ec > slow_ec * 1.2


def test_synthetic_fade_is_faster_when_hot_and_the_generators_are_deterministic():
    values = {"temperature": np.array([15.0, 45.0]), "charge_c_rate": np.array([1.0, 1.0]),
              "discharge_c_rate": np.array([1.0, 1.0]), "depth_of_discharge": np.array([1.0, 1.0]),
              "fade_exponent": np.array([0.7, 0.7])}
    cool, hot = synthetic.capacity_fades(values, np.random.default_rng(0), noise=0.0)
    assert cool[0] == hot[0] == 1.0 and np.all(np.diff(cool) <= 0) and hot[-1] < cool[-1]
    cool_life, hot_life = (curves.readout("capacity_fade", list(curve))["cycle_life"] for curve in (cool, hot))
    assert hot_life is not None and (cool_life is None or hot_life < cool_life)
    assert synthetic.generate("pe_loop", 3, seed=7) == synthetic.generate("pe_loop", 3, seed=7)
    assert synthetic.generate("capacity_fade", 3, seed=7) != synthetic.generate("capacity_fade", 3, seed=8)


def test_readouts_of_known_curves():
    up = [-10.0 if x < 0.5 else 10.0 for x in curves.PE_GRID]
    down = [10.0 if x > -0.5 else -10.0 for x in curves.PE_GRID]
    loop = curves.readout("pe_loop", up + down, {"e_max": 100.0})
    assert loop["remanent_polarization"] == pytest.approx(10.0) and loop["saturation_polarization"] == pytest.approx(10.0)
    assert loop["coercive_field"] == pytest.approx(50.0, abs=2.0)
    soh = [1 - 0.0002 * n for n in curves.FADE_GRID]
    assert curves.readout("capacity_fade", soh)["cycle_life"] == pytest.approx(1000.0, abs=1.0)
    # Points not measured (null) are skipped; a cell that stays above 80 % has no cycle life yet.
    assert curves.readout("capacity_fade", [1.0, 0.95] + [None] * (curves.FADE_POINTS - 2))["cycle_life"] is None


def test_the_dataset_contract_is_checked_and_its_card_stays_local(tmp_path):
    card = datasets.write_synthetic(tmp_path / "fade", "capacity_fade", 50, seed=1)
    assert card["ok"] and card["synthetic"] is True and card["samples"] == 50 and len(card["sha256"]) == 64
    assert set(card["inputs"]) == {item["name"] for item in synthetic.FADE_INPUTS} and "cycle_life" in card["readouts"]
    assert datasets.validate(tmp_path / "fade")["sha256"] == card["sha256"]  # the digest is stable
    with pytest.raises(datasets.DatasetError, match="not empty"):
        datasets.write_synthetic(tmp_path / "fade", "capacity_fade", 5)
    # A loop dataset without e_max, a wrong grid, a short curve and a line that is not an object are reported.
    broken = tmp_path / "broken"
    broken.mkdir()
    description = {"format": "stk.dataset/1", "name": "x", "target": {"kind": "pe_loop", "grid": {"x": "E"}},
                   "inputs": [{"name": "temperature", "unit": "K"}], "sensitivity": "private", "synthetic": False}
    (broken / "dataset.json").write_text(json.dumps(description))
    (broken / "samples.jsonl").write_text(json.dumps({"inputs": {"temperature": 300}, "curve": [1.0] * 3}) + "\n[1]\n")
    problems = datasets.validate(broken)["problems"]
    assert not datasets.validate(broken)["ok"]
    assert any("e_max" in p for p in problems) and any("grid" in p for p in problems)
    with pytest.raises(datasets.DatasetError):
        datasets.load(broken)
    # With a valid description, a short curve and a line that is not an object are reported line by line.
    description.update(target={"kind": "pe_loop", "grid": curves.grid("pe_loop")}, inputs=[{"name": "e_max", "unit": "kV/cm"}])
    (broken / "dataset.json").write_text(json.dumps(description))
    (broken / "samples.jsonl").write_text(json.dumps({"inputs": {"e_max": 100}, "curve": [1.0] * 3}) + "\n[1]\n")
    problems = datasets.validate(broken)["problems"]
    assert any("curve is 128 numbers" in p for p in problems) and any("JSON object" in p for p in problems)


@needs_torch
def test_training_registers_a_model_that_passes_its_gate_and_versions_can_be_rolled_back(tmp_path):
    datasets.write_synthetic(tmp_path / "fade", "capacity_fade", 300, seed=2)
    materials = service.MaterialsService(tmp_path / "state")

    def finished(job_id):
        for _ in range(1200):
            job = materials.job(job_id)
            if job["state"] != "running":
                return job
            time.sleep(0.05)
        raise AssertionError("training did not end")
    first = finished(materials.train(tmp_path / "fade", "first", options={"epochs": 400})["id"])
    assert first["state"] == "done" and first["version"] == "v1", first
    assert first["metrics"]["test"]["normalized_rmse"] <= service.GATES["capacity_fade"]
    assert materials.train(tmp_path / "fade", "first")["id"] == "first"  # the same job again
    # A tiny network trained for one epoch does not pass the gate: nothing is registered.
    rejected = finished(materials.train(tmp_path / "fade", "tiny", options={"epochs": 1, "hidden": [4]})["id"])
    assert rejected["state"] == "rejected" and rejected["version"] is None
    second = finished(materials.train(tmp_path / "fade", "second", options={"epochs": 400, "seed": 1})["id"])
    listed = materials.models("capacity_fade")["kinds"]["capacity_fade"]
    assert second["version"] == "v2" and listed["active"] == "v2" and [v["version"] for v in listed["versions"]] == ["v1", "v2"]
    assert all(item["dataset"]["synthetic"] for item in listed["versions"])
    materials.activate("capacity_fade", "v1")
    row = {"temperature": 35.0, "charge_c_rate": 2.0, "discharge_c_rate": 1.5, "depth_of_discharge": 0.8, "fade_exponent": 0.7}
    predicted = materials.predict("capacity_fade", [row])
    assert predicted["model"]["version"] == "v1" and predicted["model"]["synthetic"] is True
    curve = predicted["results"][0]["curve"]
    truth = synthetic.capacity_fades({key: np.array([value]) for key, value in row.items()}, np.random.default_rng(0), noise=0.0)[0]
    assert len(curve) == curves.FADE_POINTS and np.max(np.abs(np.array(curve) - truth)) < 0.05
    assert predicted["results"][0]["readout"]["cycle_life"] is not None
    with pytest.raises(service.MaterialsError, match="finite number"):
        materials.predict("capacity_fade", [{"temperature": 25.0}])
    with pytest.raises(service.MaterialsNotFound):
        materials.predict("pe_loop", [row])


@needs_torch
def test_a_loop_model_learns_the_readouts_and_training_can_be_cancelled(tmp_path):
    datasets.write_synthetic(tmp_path / "loops", "pe_loop", 400, seed=3)
    meta = training.train(tmp_path / "loops", tmp_path / "model", options={"epochs": 200})
    test = meta["metrics"]["test"]
    assert meta["dataset"]["synthetic"] and test["remanent_polarization_mae"] < 3.0 and test["normalized_rmse"] < 0.3
    loaded, predict = training.load(tmp_path / "model")
    assert loaded["kind"] == "pe_loop" and len(predict([{item["name"]: 1.0 for item in loaded["inputs"]}])[0]) == 128
    materials = service.MaterialsService(tmp_path / "state")
    job = materials.train(tmp_path / "loops", "long", options={"epochs": 5000, "patience": 5000})
    with pytest.raises(service.MaterialsBusy):
        materials.train(tmp_path / "loops", "another")
    materials.cancel(job["id"])
    for _ in range(600):
        if materials.job("long")["state"] != "running":
            break
        time.sleep(0.05)
    assert materials.job("long")["state"] == "cancelled" and materials.models("pe_loop")["kinds"]["pe_loop"]["versions"] == []


def test_the_service_offers_materials_to_scripts_and_the_desktop(inproc, tmp_path, monkeypatch):
    h = inproc()
    card = h.call("materials.datasets.synthetic", {"directory": str(tmp_path / "fade"), "kind": "capacity_fade", "samples": 40})["card"]
    assert card["ok"] and card["samples"] == 40
    assert h.call("materials.datasets.validate", {"directory": str(tmp_path / "fade")})["card"]["sha256"] == card["sha256"]
    assert h.error("materials.datasets.validate", {"directory": "relative/path"})["code"] == "invalid_params"
    assert h.call("materials.models.list", {})["kinds"]["pe_loop"] == {"active": None, "versions": []}
    assert h.error("materials.predict", {"kind": "pe_loop", "inputs": [{"e_max": 1.0}]})["code"] == "not_found"
    catalog = set(h.call("script.catalog")["operations"])
    assert {"materials.train", "materials.predict", "materials.models.activate"} <= catalog

    def missing():
        raise training.TrainingUnavailable("Training needs PyTorch (CPU)")
    monkeypatch.setattr(training, "torch_module", missing)
    assert h.error("materials.train", {"directory": str(tmp_path / "fade"), "job_id": "j1"})["code"] == "unsupported"
    assert not h.violations


@needs_torch
def test_scripts_train_and_predict_through_the_service(inproc, tmp_path):
    from suan.scripting import API
    h = inproc()
    api = API(lambda operation, params: h.call(operation, params))
    api.materials.synthetic(tmp_path / "fade", "capacity_fade", 300, seed=2)
    job = api.materials.train(tmp_path / "fade", options={"epochs": 400}, poll=0.05)
    assert job["state"] == "done", job
    result = api.materials.predict("capacity_fade", {"temperature": 25.0, "charge_c_rate": 1.0, "discharge_c_rate": 1.0,
                                                     "depth_of_discharge": 0.8, "fade_exponent": 0.6})
    assert result["model"]["synthetic"] is True and len(result["results"][0]["curve"]) == curves.FADE_POINTS
    assert not h.violations


def test_readouts_are_numbers_or_none_never_nan():
    loop = [float(x) for x in np.linspace(-10, 10, curves.PE_POINTS)] * 2
    loop[curves.PE_POINTS - 1] = None  # the end of the up branch was not measured
    loop[31] = None  # nor the point next to E = 0
    values = curves.readout("pe_loop", loop, {"e_max": 100.0})
    assert all(value is None or np.isfinite(value) for value in values.values())
    assert curves.readout("pe_loop", [None] * (2 * curves.PE_POINTS))["remanent_polarization"] is None
    # SOH reaching 0.8 exactly at the last point, and a cell that starts below it.
    soh = list(np.linspace(1.0, 0.8, curves.FADE_POINTS))
    assert curves.readout("capacity_fade", soh)["cycle_life"] == pytest.approx(2000.0)
    assert curves.readout("capacity_fade", [0.7] * curves.FADE_POINTS)["cycle_life"] == 0.0


def test_malformed_datasets_are_reported_never_raised(tmp_path):
    def card(description, lines):
        folder = tmp_path / str(len(list(tmp_path.iterdir())))
        folder.mkdir()
        (folder / "dataset.json").write_text(description if isinstance(description, str) else json.dumps(description))
        (folder / "samples.jsonl").write_bytes(lines if isinstance(lines, bytes) else "\n".join(lines).encode())
        return datasets.validate(folder)
    good = {"format": "stk.dataset/1", "name": "x", "target": {"kind": "capacity_fade", "grid": curves.grid("capacity_fade")},
            "inputs": [{"name": "t", "unit": "degC"}], "sensitivity": "private", "synthetic": False}
    curve = [1.0] * curves.FADE_POINTS
    sample = json.dumps({"id": "a", "inputs": {"t": 25.0}, "curve": curve})
    assert card(good, [sample])["ok"]
    for description, lines, expected in (
            ({**good, "target": "x"}, [sample], "target"),
            ({**good, "inputs": [{"name": "a"}, {"name": "a"}]}, ['{"inputs": {}, "curve": []}'], "distinct names"),
            ({**good, "inputs": "a"}, ['{"inputs": {}, "curve": []}'], "distinct names"),
            (good, ['{"id": "a", "inputs": {"t": 1' + "0" * 400 + '}, "curve": ' + json.dumps(curve) + "}"], "number"),
            (good, [sample, sample], "used twice"),
            (good, [json.dumps({"inputs": {"t": 25.0}, "curve": [2.0] * curves.FADE_POINTS})], "between 0 and 1.5"),
            ({**good, "synthetic": "yes", "sensitivity": "confidential-internal"}, [sample], "synthetic"),
            (good, b"\xff\xfe\x00bad", "UTF-8")):
        result = card(description, lines)
        assert not result["ok"] and any(expected in problem for problem in result["problems"]), (expected, result["problems"])
        assert all(len(problem) <= 500 for problem in result["problems"])
        assert result.get("synthetic") in (True, False, None) and result.get("sensitivity") in ("private", "public", None)
    huge = [json.dumps({"id": str(i), "inputs": {"t": value}, "curve": curve}) for i, value in enumerate((-1e12, 1e12))]
    assert card(good, huge)["inputs"]["t"]["std"] == pytest.approx(1e12)  # no overflow in the statistics


@needs_torch
def test_versions_never_reuse_a_folder_and_a_late_cancel_registers_nothing(tmp_path, monkeypatch):
    datasets.write_synthetic(tmp_path / "fade", "capacity_fade", 60, seed=5)
    materials = service.MaterialsService(tmp_path / "state")

    def finished(job_id):
        for _ in range(1200):
            job = materials.job(job_id)
            if job["state"] != "running":
                return job
            time.sleep(0.05)
        raise AssertionError("training did not end")
    monkeypatch.setitem(service.GATES, "capacity_fade", 10.0)  # any model passes: this test is about the registry
    assert finished(materials.train(tmp_path / "fade", "a", options={"epochs": 5})["id"])["version"] == "v1"
    (tmp_path / "state" / "registry.json").unlink()  # a lost registry: the v1 folder stays
    again = finished(materials.train(tmp_path / "fade", "b", options={"epochs": 5})["id"])
    assert again["version"] == "v2" and (tmp_path / "state" / "models" / "capacity_fade" / "v2" / "model.json").exists()
    # Cancelled while the last epoch ends: nothing is registered.
    original = training.train

    def cancelled_at_the_end(*args, **kwargs):
        meta = original(*args, **kwargs)
        kwargs["cancel"].set()
        return meta
    monkeypatch.setattr(training, "train", cancelled_at_the_end)
    late = finished(materials.train(tmp_path / "fade", "c", options={"epochs": 5})["id"])
    assert late["state"] == "cancelled" and materials.models("capacity_fade")["kinds"]["capacity_fade"]["active"] == "v2"
    # A damaged registry is reported as such.
    (tmp_path / "state" / "registry.json").write_text("{")
    with pytest.raises(service.MaterialsUnavailable, match="cannot be read"):
        materials.models()
