"""Small real CPU models prove frozen training and comparable held-out evaluation."""
import hashlib
import json
import threading

import numpy as np
import pytest

from suan.materials import curves, datasets, inputs, training


OPTIONS = {"hidden": [8], "epochs": 12, "patience": 12, "batch_size": 16,
           "learning_rate": 0.025, "seed": 7}


@pytest.fixture
def tmp_path(tmp_path):
    # macOS may spell its system temporary directory through the /var alias.
    # Capsules require a physical, link-free spelling of every ancestor.
    return tmp_path.resolve()


@pytest.fixture
def torch():
    # The reference scientific environment provides CPU Torch. Other supported
    # client-only installations may exercise the optional-dependency boundary.
    return pytest.importorskip("torch")


def data(folder, *, shift=0, count=40):
    folder.mkdir()
    description = {"format": datasets.FORMAT, "name": "Public deterministic training fixture",
        "target": {"kind": "capacity_fade", "grid": curves.grid("capacity_fade")},
        "inputs": [{"name": "temperature", "unit": "K"}, {"name": "rate", "unit": "1"}],
        "source": "Synthetic software test", "license": "CC0-1.0", "sensitivity": "public", "synthetic": True}
    samples = []
    for index in range(count):
        temperature, rate = 20 + shift + index / 3, 0.5 + index % 5 / 3
        curve = (1 - (0.16 + index / 250 + rate / 50) * np.linspace(0, 1, curves.FADE_POINTS)).tolist()
        if index % 4 == 0:
            curve[5 + index % 12] = None
        samples.append({"id": f"sample-{index:03}", "inputs": {"temperature": temperature, "rate": rate},
                        "curve": curve})
    write_data(folder, description, samples)
    return description, samples


def write_data(folder, description, samples):
    (folder / "dataset.json").write_text(json.dumps(description), encoding="utf-8")
    (folder / "samples.jsonl").write_text("".join(json.dumps(sample) + "\n" for sample in samples), encoding="utf-8")


def sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                                     allow_nan=False).encode()).hexdigest()


def expected_metrics(predict, samples):
    predicted = np.asarray(predict([sample["inputs"] for sample in samples]))
    truth = np.asarray([[np.nan if point is None else point for point in sample["curve"]] for sample in samples])
    known = ~np.isnan(truth)
    rmse = float(np.sqrt(np.mean((predicted[known] - truth[known]) ** 2)))
    return rmse, rmse / float(np.std(truth[known]))


def test_frozen_finetuning_and_active_comparison_use_the_exact_same_heldout_samples(tmp_path, torch):
    data(tmp_path / "old-data", shift=-10)
    base_path, baseline_path = tmp_path / "base-model", tmp_path / "baseline-model"
    base_meta = training.train(tmp_path / "old-data", base_path, options={**OPTIONS, "seed": 1})
    training.train(tmp_path / "old-data", baseline_path, options={**OPTIONS, "hidden": [4], "epochs": 3, "seed": 2})
    _, base_predict = training.load(base_path)
    _, baseline_predict = training.load(baseline_path)
    _, samples = data(tmp_path / "live-data", shift=30)
    capsule = tmp_path / "capsule"
    fine_options = {**OPTIONS, "epochs": 2, "batch_size": 4096}
    frozen = inputs.capture(tmp_path / "live-data", capsule, options=fine_options,
                            base_model=base_path, baseline_model=baseline_path)
    lookup = {sample["id"]: sample for sample in samples}
    initial_train = [lookup[identity] for identity in frozen["split"]["train"]]
    initial_truth = np.asarray([[np.nan if point is None else point for point in sample["curve"]]
                                for sample in initial_train])
    initial_error = ((np.asarray(base_predict([sample["inputs"] for sample in initial_train])) - initial_truth) /
                     np.asarray(base_meta["normalization"]["y_std"]))
    expected_initial_loss = float(np.mean(initial_error[~np.isnan(initial_truth)] ** 2))
    for path in (tmp_path / "live-data", base_path, baseline_path):
        for name in path.iterdir():
            name.unlink()  # Frozen training must not consult any of these live files.
    progress = []
    result = training.train(capsule, tmp_path / "candidate", frozen=True,
                            progress=lambda epoch, train, validation: progress.append((epoch, train, validation)))
    assert progress and all(len(item) == 3 and np.isfinite(item).all() for item in progress)
    # One complete batch means the first loss observes the frozen base weights,
    # before the first optimizer step, with only genuinely measured points counted.
    assert progress[0][1] == pytest.approx(expected_initial_loss, rel=1e-12)
    assert result["normalization"] == base_meta["normalization"]
    assert result["layers"] == base_meta["layers"]
    assert result["training_input"] == {"capsule_sha256": frozen["sha256"], "split_sha256": sha(frozen["split"]),
        "split_counts": {key: len(value) for key, value in frozen["split"].items()},
        "base_model": frozen["base_model"], "baseline_model": frozen["baseline_model"]}
    comparison = result["comparison"]
    assert comparison["format"] == "stk.materials-training-comparison/1"
    assert comparison["test_sha256"] == sha(frozen["split"]["test"])
    assert comparison["test_samples"] == len(frozen["split"]["test"])
    assert comparison["candidate"] == result["metrics"]["test"]
    heldout = [lookup[identity] for identity in frozen["split"]["test"]]
    loaded, predict = training.load(tmp_path / "candidate")
    for role, function in (("candidate", predict), ("base", base_predict), ("baseline", baseline_predict)):
        rmse, normalized = expected_metrics(function, heldout)
        assert comparison[role]["samples"] == len(heldout)
        assert comparison[role]["rmse"] == pytest.approx(rmse, rel=1e-12)
        assert comparison[role]["normalized_rmse"] == pytest.approx(normalized, rel=1e-12)
    preview = result["evaluation_preview"]
    assert preview["grid"] == curves.grid("capacity_fade")
    assert [sample["id"] for sample in preview["samples"]] == frozen["split"]["test"][:3]
    assert len(preview["samples"]) == 3
    for sample, expected in zip(preview["samples"], heldout[:3]):
        assert sample["inputs"] == expected["inputs"] and sample["observed"] == expected["curve"]
        for role, function in (("candidate", predict), ("base", base_predict), ("baseline", baseline_predict)):
            np.testing.assert_allclose(sample[role], function([expected["inputs"]])[0], rtol=1e-12, atol=1e-12)
    assert loaded["evaluation_preview"] == preview
    assert loaded["weights_verified"] is True and loaded["weights_integrity"] == "sha256"
    assert result["weights_sha256"] == hashlib.sha256((tmp_path / "candidate/model.pt").read_bytes()).hexdigest()
    encoded = json.dumps(result)
    shown = {sample["id"] for sample in preview["samples"]}
    assert all(sample["id"] not in encoded for sample in samples if sample["id"] not in shown)
    assert inputs.verify(capsule) == frozen


def test_baseline_evaluation_does_not_initialize_or_change_scratch_training(tmp_path, torch):
    _, samples = data(tmp_path / "data")
    baseline = tmp_path / "baseline"
    training.train(tmp_path / "data", baseline, options={**OPTIONS, "seed": 44, "epochs": 2})
    plain, compared = tmp_path / "plain-input", tmp_path / "compared-input"
    a = inputs.capture(tmp_path / "data", plain, options=OPTIONS)
    b = inputs.capture(tmp_path / "data", compared, options=OPTIONS, baseline_model=baseline)
    first = training.train(plain, tmp_path / "first", frozen=True)
    second = training.train(compared, tmp_path / "second", frozen=True)
    assert a["split"] == b["split"]
    assert first["normalization"] == second["normalization"]
    assert first["metrics"]["test"] == second["metrics"]["test"]
    assert first["comparison"]["baseline"] is None and second["comparison"]["baseline"] is not None
    assert all(sample["base"] is None and sample["baseline"] is None
               for sample in first["evaluation_preview"]["samples"])
    assert all(sample["base"] is None and sample["baseline"] is not None
               for sample in second["evaluation_preview"]["samples"])
    _, predict_a = training.load(tmp_path / "first")
    _, predict_b = training.load(tmp_path / "second")
    rows = [sample["inputs"] for sample in samples]
    np.testing.assert_array_equal(predict_a(rows), predict_b(rows))


def test_direct_training_retains_its_return_shape_and_is_stable_under_sample_reordering(tmp_path, torch):
    description, samples = data(tmp_path / "data")
    first = training.train(tmp_path / "data", tmp_path / "first", options=OPTIONS)
    split = inputs.partition([sample["id"] for sample in samples], inputs.DEFAULTS["split"], OPTIONS["seed"])
    selected = [sample for sample in samples if sample["id"] in split["train"]]
    np.testing.assert_allclose(first["normalization"]["x_mean"],
        np.mean([[sample["inputs"][field["name"]] for field in description["inputs"]] for sample in selected], axis=0))
    np.testing.assert_allclose(first["normalization"]["y_mean"],
        np.nanmean([[np.nan if point is None else point for point in sample["curve"]] for sample in selected], axis=0))
    write_data(tmp_path / "data", description, list(reversed(samples)))
    second = training.train(tmp_path / "data", tmp_path / "second", options=OPTIONS)
    assert first["format"] == training.MODEL_FORMAT
    assert {"train", "test", "epochs", "best_epoch", "seconds"} <= first["metrics"].keys()
    assert first["training_input"]["capsule_sha256"] is None
    assert first["training_input"]["split_sha256"] == second["training_input"]["split_sha256"]
    assert first["metrics"]["test"] == second["metrics"]["test"]
    assert training.load(tmp_path / "first")[1]([]) == []


@pytest.mark.parametrize("change", [{"epochs": 3}, {"hidden": [16]}, {"seed": 8}])
def test_frozen_options_cannot_override_the_prepared_experiment(tmp_path, change):
    data(tmp_path / "data")
    inputs.capture(tmp_path / "data", tmp_path / "capsule", options=OPTIONS)
    with pytest.raises(ValueError, match="differ"):
        training.train(tmp_path / "capsule", tmp_path / "model", frozen=True, options=change)
    assert not (tmp_path / "model").exists()


@pytest.mark.parametrize("split", [[0.98, 0.01, 0.01], [0.5, 0.49, 0.01]])
def test_empty_heldout_partitions_are_rejected_without_training_fallback(tmp_path, monkeypatch, split):
    data(tmp_path / "data", count=20)
    monkeypatch.setattr(training, "torch_module", lambda: pytest.fail("Empty partition reached training"))
    with pytest.raises(ValueError, match="nonempty"):
        training.train(tmp_path / "data", tmp_path / "model", options={**OPTIONS, "split": split})
    assert not (tmp_path / "model").exists()


def test_a_resealed_capsule_cannot_leak_training_ids_into_the_test_partition(tmp_path):
    data(tmp_path / "data")
    capsule = tmp_path / "capsule"
    manifest = inputs.capture(tmp_path / "data", capsule, options=OPTIONS)
    manifest["split"]["test"][0] = manifest["split"]["train"][0]
    manifest["sha256"] = sha({key: value for key, value in manifest.items() if key != "sha256"})
    (capsule / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="partition"):
        training.train(capsule, tmp_path / "model", frozen=True)
    assert not (tmp_path / "model").exists()


def test_missing_training_output_is_rejected_even_when_heldout_points_exist(tmp_path, monkeypatch):
    description, samples = data(tmp_path / "data")
    split = inputs.partition([sample["id"] for sample in samples], OPTIONS.get("split", inputs.DEFAULTS["split"]), OPTIONS["seed"])
    for sample in samples:
        if sample["id"] in split["train"]:
            sample["curve"][1] = sample["curve"][63] = None
    write_data(tmp_path / "data", description, samples)
    monkeypatch.setattr(training, "torch_module", lambda: pytest.fail("Unobserved outputs reached Torch"))
    with pytest.raises(datasets.DatasetError, match="no observations.*1, 63"):
        training.train(tmp_path / "data", tmp_path / "model", options=OPTIONS)
    assert not (tmp_path / "model").exists()


@pytest.mark.parametrize("when", ["before", "progress"])
def test_cancel_never_publishes_a_candidate_model(tmp_path, torch, when):
    data(tmp_path / "data")
    cancel = threading.Event()
    if when == "before":
        cancel.set()
    with pytest.raises(training.Cancelled):
        training.train(tmp_path / "data", tmp_path / "model", options=OPTIONS, cancel=cancel,
                       progress=lambda *args: cancel.set())
    assert not (tmp_path / "model").exists()


def test_new_weight_digest_is_checked_before_torch_deserialization_and_legacy_remains_explicit(tmp_path, torch, monkeypatch):
    data(tmp_path / "data")
    model = tmp_path / "model"
    meta = training.train(tmp_path / "data", model, options={**OPTIONS, "epochs": 2})
    original = (model / "model.pt").read_bytes()
    (model / "model.pt").write_bytes(original[:-1] + bytes([original[-1] ^ 1]))
    with monkeypatch.context() as patch:
        patch.setattr(torch, "load", lambda *a, **k: pytest.fail("Unchecked weights were deserialized"))
        with pytest.raises(ValueError, match="checksum"):
            training.load(model)
    (model / "model.pt").write_bytes(original)
    del meta["weights_sha256"]
    del meta["training_input"]
    del meta["comparison"]
    (model / "model.json").write_text(json.dumps(meta), encoding="utf-8")
    legacy, predict = training.load(model)
    assert "weights_sha256" not in legacy and legacy["weights_verified"] is False
    assert legacy["weights_integrity"] == "legacy_unverified"
    assert len(predict([{"temperature": 25, "rate": 1}])[0]) == curves.FADE_POINTS


@pytest.mark.parametrize("damage", ["architecture", "activation", "unit", "order", "kind", "grid"])
def test_incompatible_base_is_never_reinterpreted_or_used_for_initialization(tmp_path, torch, damage):
    data(tmp_path / "data")
    model = tmp_path / "base"
    meta = training.train(tmp_path / "data", model, options={**OPTIONS, "hidden": [4], "epochs": 2})
    if damage == "activation":
        meta["layers"]["activation"] = "relu"
    elif damage == "unit":
        meta["inputs"][0]["unit"] = "degC"
    elif damage == "order":
        meta["inputs"].reverse()
    elif damage == "kind":
        meta["kind"] = "pe_loop"
    elif damage == "grid":
        meta["grid"]["points"] += 1
    (model / "model.json").write_text(json.dumps(meta), encoding="utf-8")
    with pytest.raises(ValueError, match="architecture|activation|inputs|kind|grid"):
        inputs.capture(tmp_path / "data", tmp_path / "capsule", options=OPTIONS, base_model=model)
        training.train(tmp_path / "capsule", tmp_path / "candidate", frozen=True)
    assert not (tmp_path / "candidate").exists()


def test_frozen_training_refuses_to_write_inside_its_capsule(tmp_path):
    data(tmp_path / "data")
    manifest = inputs.capture(tmp_path / "data", tmp_path / "capsule", options=OPTIONS)
    with pytest.raises(ValueError, match="must not modify"):
        training.train(tmp_path / "capsule", tmp_path / "capsule/model", frozen=True)
    assert inputs.verify(tmp_path / "capsule") == manifest
