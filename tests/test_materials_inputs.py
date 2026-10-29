"""Frozen training inputs preserve local bytes and exact held-out identities."""
import builtins
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import random
import shutil
import stat
from types import SimpleNamespace

import pytest

from suan.materials import datasets, inputs


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def resign(folder, manifest):
    manifest["sha256"] = hashlib.sha256(canonical({k: v for k, v in manifest.items() if k != "sha256"})).hexdigest()
    (folder / "manifest.json").write_bytes(canonical(manifest) + b"\n")


@pytest.fixture
def source(tmp_path):
    # macOS's system temporary directory may itself have a /var symlink.
    root = tmp_path.resolve()
    directory = root / "live"
    datasets.write_synthetic(directory, "capacity_fade", 20, seed=3)
    return directory


def make_model(source, name, *, weights=b"synthetic model weights"):
    description, _ = datasets.load(source)
    folder = source.parent / name
    folder.mkdir()
    meta = {"format": "stk.curve-model/1", "kind": description["target"]["kind"],
            "inputs": description["inputs"], "grid": description["target"]["grid"],
            "synthetic": True}
    (folder / "model.json").write_bytes(canonical(meta) + b"\n")
    (folder / "model.pt").write_bytes(weights)
    return folder


def assert_clean(source, target):
    assert not target.exists()
    assert not list(source.parent.glob(".stk-training-input-*"))


def test_capture_is_replayable_after_live_files_change_and_disappear(source):
    target = source.parent / "frozen"
    original = {name: (source / name).read_bytes() for name in ("dataset.json", "samples.jsonl")}
    description, samples = datasets.load(source)
    manifest = inputs.capture(source, target)
    assert set(manifest) == {"format", "sha256", "kind", "dataset", "options", "split",
                             "base_model", "baseline_model", "files"}
    assert manifest["format"] == inputs.FORMAT
    assert manifest["options"] == inputs.DEFAULTS
    assert manifest["dataset"] == {"sha256": datasets.digest(description, samples), "card": datasets.validate(source)}
    assert manifest["base_model"] is None and manifest["baseline_model"] is None
    assert set(manifest["files"]) == set(original)
    for name, raw in original.items():
        assert (target / name).read_bytes() == raw
        assert manifest["files"][name] == {"size": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    assert str(source) not in (target / "manifest.json").read_text(encoding="utf-8")
    assert {name: len(ids) for name, ids in manifest["split"].items()} == {"train": 14, "validation": 3, "test": 3}
    (source / "samples.jsonl").write_text("changed live source", encoding="utf-8")
    shutil.rmtree(source)
    assert inputs.verify(target) == manifest
    assert inputs.load(target) == (manifest, description, samples)
    assert all((target / name).read_bytes() == raw for name, raw in original.items())
    if os.name != "nt":
        assert stat.S_IMODE(target.stat().st_mode) == 0o700
        assert all(stat.S_IMODE((target / name).stat().st_mode) == 0o600 for name in (*original, "manifest.json"))


def test_identity_has_no_path_timestamp_or_randomness_and_return_values_are_independent(source):
    first = inputs.capture(source, source.parent / "one")
    second = inputs.capture(source, source.parent / "two")
    assert first == second
    first["options"]["hidden"][0] = 4
    assert inputs.verify(source.parent / "one") == second
    third = inputs.capture(source, source.parent / "three", options={"seed": 1})
    assert third["sha256"] != second["sha256"] and third["split"] != second["split"]


def test_options_are_deep_copied_idempotent_and_normalize_close_fraction_sums():
    options = {"hidden": [4, 8], "split": [0.7, 0.15, 0.1500000001], "learning_rate": 1}
    original = deepcopy(options)
    result = inputs.normalize_options(options)
    assert options == original
    assert result["learning_rate"] == 1.0
    assert sum(result["split"]) == pytest.approx(1)
    assert inputs.normalize_options(result) == result
    result["hidden"][0] = 1024
    result["split"][0] = 0.1
    assert options == original and inputs.normalize_options() == inputs.DEFAULTS
    boundaries = {"epochs": 5000, "patience": 1, "batch_size": 4096, "hidden": [4, 1024, 4, 1024],
                  "seed": 2**31 - 1, "learning_rate": 1.0}
    assert all(inputs.normalize_options(boundaries)[key] == value for key, value in boundaries.items())


def test_accepted_close_fraction_sums_have_a_stable_canonical_identity(source):
    generator = random.Random(0)
    for _ in range(1000):
        first = generator.uniform(0.1, 0.8)
        second = generator.uniform(0.05, 0.9 - first)
        third = 1 - first - second + generator.choice([-1, 1]) * generator.random() * 1e-10
        settings = inputs.normalize_options({"split": [first, second, third]})
        assert canonical(inputs.normalize_options(settings)) == canonical(settings)
    manifest = inputs.capture(source, source.parent / "frozen", options={"split": [0.7, 0.15, 0.1500000001]})
    assert inputs.verify(source.parent / "frozen") == manifest


@pytest.mark.parametrize("options", [
    [], True, {"extra": 1}, {"epochs": True}, {"epochs": 0}, {"epochs": 5001},
    {"patience": 0}, {"patience": 5001}, {"batch_size": 0}, {"batch_size": 4097},
    {"batch_size": 1.0}, {"seed": -1}, {"seed": 2**31}, {"seed": False},
    {"hidden": []}, {"hidden": [4] * 5}, {"hidden": (4,)}, {"hidden": [3]},
    {"hidden": [1025]}, {"hidden": [True]}, {"learning_rate": 0}, {"learning_rate": -0.1},
    {"learning_rate": 1.01}, {"learning_rate": True}, {"learning_rate": float("nan")},
    {"learning_rate": float("inf")}, {"learning_rate": 10**400},
    {"split": [0.7, 0.3]}, {"split": [0.7, 0.3, 0]}, {"split": [0.7, -0.1, 0.4]},
    {"split": [0.7, 0.15, 0.14]}, {"split": [True, 0.1, 0.1]}, {"split": [0.7, float("nan"), 0.3]},
])
def test_invalid_options_are_rejected(options):
    with pytest.raises(inputs.InputsError):
        inputs.normalize_options(options)


def test_partitions_bind_exact_ids_independent_of_input_order():
    ids = [f"sample-{index}" for index in range(20)]
    result = inputs.partition(ids, [0.7, 0.15, 0.15], 7)
    assert result == inputs.partition(list(reversed(ids)), [0.7, 0.15, 0.15], 7)
    assert result != inputs.partition(ids, [0.7, 0.15, 0.15], 8)
    groups = [set(result[name]) for name in ("train", "validation", "test")]
    assert set.union(*groups) == set(ids)
    assert not (groups[0] & groups[1] or groups[0] & groups[2] or groups[1] & groups[2])
    assert len([identity for group in result.values() for identity in group]) == len(ids)


@pytest.mark.parametrize("ids,fractions", [
    (["same"] * 20, [0.7, 0.15, 0.15]), (["a", "b", 3], [0.34, 0.33, 0.33]),
    (["a", "b", ""], [0.34, 0.33, 0.33]), (["a", "b", "x" * 129], [0.34, 0.33, 0.33]),
    (["a", "b", "\ud800"], [0.34, 0.33, 0.33]), (["a", "b", "c"], [0.7, 0.15, 0.15]),
    ([str(i) for i in range(20)], [0.99, 0.005, 0.005]),
])
def test_partition_never_duplicates_or_borrows_training_samples(ids, fractions):
    with pytest.raises(inputs.InputsError):
        inputs.partition(ids, fractions, 0)


def test_capture_rejects_a_dataset_without_both_held_out_sets(source):
    rows = (source / "samples.jsonl").read_bytes().splitlines(keepends=True)
    (source / "samples.jsonl").write_bytes(b"".join(rows[:3]))
    target = source.parent / "frozen"
    with pytest.raises(inputs.InputsError, match="nonempty"):
        inputs.capture(source, target)
    assert_clean(source, target)


def test_base_and_active_baseline_are_independently_frozen_without_loading_torch(source, monkeypatch):
    base = make_model(source, "old-base", weights=b"synthetic base weights")
    baseline = make_model(source, "active-baseline", weights=b"synthetic active weights")
    original_import = builtins.__import__

    def no_torch(name, *args, **kwargs):
        assert name != "torch" and not name.startswith("torch."), "capture must not execute a model"
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_torch)
    target = source.parent / "frozen"
    manifest = inputs.capture(source, target, base_model=base, baseline_model=baseline)
    assert manifest["base_model"] != manifest["baseline_model"]
    for role, folder in (("base", base), ("baseline", baseline)):
        descriptor = manifest[f"{role}_model"]
        assert set(descriptor) == {"model_sha256", "weights_sha256", "model_size", "weights_size"}
        for field, filename in (("model", "model.json"), ("weights", "model.pt")):
            raw = (folder / filename).read_bytes()
            assert (target / role / filename).read_bytes() == raw
            assert descriptor[f"{field}_sha256"] == hashlib.sha256(raw).hexdigest()
            assert descriptor[f"{field}_size"] == len(raw)
        shutil.rmtree(folder)
    shutil.rmtree(source)
    assert inputs.verify(target) == manifest
    assert inputs.load(target)[0] == manifest


def test_the_same_model_source_can_supply_two_distinct_frozen_roles(source):
    model = make_model(source, "model")
    target = source.parent / "frozen"
    manifest = inputs.capture(source, target, base_model=model, baseline_model=model)
    assert manifest["base_model"] == manifest["baseline_model"]
    assert {"base/model.pt", "baseline/model.pt"} <= set(manifest["files"])
    (target / "base" / "model.pt").write_bytes(b"tampered base")
    assert (target / "baseline" / "model.pt").read_bytes() == b"synthetic model weights"
    with pytest.raises(inputs.InputsError):
        inputs.verify(target)


@pytest.mark.parametrize("change", ["format", "kind", "inputs", "units", "grid", "nonfinite", "empty-weights"])
def test_incompatible_or_invalid_base_models_never_publish(source, change):
    model = make_model(source, "model")
    meta_path = model / "model.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    if change == "format":
        meta["format"] = "other"
    elif change == "kind":
        meta["kind"] = "pe_loop"
    elif change == "inputs":
        meta["inputs"].reverse()
    elif change == "units":
        meta["inputs"][0]["unit"] = "other"
    elif change == "grid":
        meta["grid"] = {}
    elif change == "nonfinite":
        meta["unused"] = float("nan")
    else:
        (model / "model.pt").write_bytes(b"")
    meta_path.write_text(json.dumps(meta), encoding="utf-8")
    target = source.parent / "frozen"
    with pytest.raises(inputs.InputsError):
        inputs.capture(source, target, base_model=model)
    assert_clean(source, target)


@pytest.mark.parametrize("name", ["dataset.json", "samples.jsonl", "base/model.json", "base/model.pt",
                                  "baseline/model.json", "baseline/model.pt"])
def test_file_byte_tampering_is_detected_in_every_role(source, name):
    model = make_model(source, "model")
    target = source.parent / "frozen"
    inputs.capture(source, target, base_model=model, baseline_model=model)
    with (target / name).open("ab") as output:
        output.write(b"changed")
    with pytest.raises(inputs.InputsError):
        inputs.verify(target)
    with pytest.raises(inputs.InputsError):
        inputs.load(target)


@pytest.mark.parametrize("change", ["identity", "extra-top", "file-set", "file-size-bool", "dataset-card", "options",
                                    "duplicate-id", "missing-id", "swapped-id", "model-size-bool"])
def test_manifest_bindings_are_checked_beyond_its_self_digest(source, change):
    target = source.parent / "frozen"
    model = make_model(source, "model")
    manifest = inputs.capture(source, target, base_model=model)
    if change == "identity":
        manifest["sha256"] = "0" * 64
    elif change == "extra-top":
        manifest["source_path"] = "synthetic local path"
    elif change == "file-set":
        manifest["files"]["unlisted"] = manifest["files"]["dataset.json"]
    elif change == "file-size-bool":
        manifest["files"]["dataset.json"]["size"] = True
    elif change == "dataset-card":
        manifest["dataset"]["card"]["samples"] += 1
    elif change == "options":
        manifest["options"]["seed"] += 1
    elif change == "duplicate-id":
        manifest["split"]["test"][0] = manifest["split"]["train"][0]
    elif change == "missing-id":
        manifest["split"]["validation"].pop()
    elif change == "swapped-id":
        manifest["split"]["train"][0], manifest["split"]["test"][0] = (
            manifest["split"]["test"][0], manifest["split"]["train"][0])
    else:
        manifest["base_model"]["model_size"] = True
    if change == "identity":
        (target / "manifest.json").write_bytes(canonical(manifest) + b"\n")
    else:
        resign(target, manifest)
    with pytest.raises(inputs.InputsError):
        inputs.verify(target)


@pytest.mark.parametrize("change", ["extra-file", "missing-file", "extra-role-file", "duplicate-json-key"])
def test_exact_capsule_tree_and_unambiguous_json_are_required(source, change):
    target = source.parent / "frozen"
    model = make_model(source, "model")
    inputs.capture(source, target, baseline_model=model)
    if change == "extra-file":
        (target / "extra").write_bytes(b"synthetic")
    elif change == "missing-file":
        (target / "samples.jsonl").unlink()
    elif change == "extra-role-file":
        (target / "baseline" / "extra").write_bytes(b"synthetic")
    else:
        raw = (target / "manifest.json").read_bytes()
        (target / "manifest.json").write_bytes(b'{"format":"other",' + raw[1:])
    with pytest.raises(inputs.InputsError):
        inputs.verify(target)


def test_existing_target_and_missing_parent_are_never_reused_or_created(source):
    existing = source.parent / "existing"
    existing.mkdir()
    marker = existing / "owner-file"
    marker.write_bytes(b"synthetic owner bytes")
    with pytest.raises(inputs.InputsError):
        inputs.capture(source, existing)
    assert marker.read_bytes() == b"synthetic owner bytes"
    missing_parent = source.parent / "missing"
    with pytest.raises(inputs.InputsError):
        inputs.capture(source, missing_parent / "frozen")
    assert not missing_parent.exists()
    first = inputs.capture(source, source.parent / "frozen")
    with pytest.raises(inputs.InputsError):
        inputs.capture(source, source.parent / "frozen")
    assert inputs.verify(source.parent / "frozen") == first


@pytest.mark.parametrize("location", ["dataset-file", "dataset-directory", "target-parent", "base-file", "capsule-role"])
def test_links_cannot_supply_frozen_bytes_or_destination_paths(source, location):
    target = source.parent / "frozen"
    model = make_model(source, "model")
    try:
        if location == "dataset-file":
            actual = source / "actual.json"
            (source / "dataset.json").rename(actual)
            (source / "dataset.json").symlink_to(actual)
        elif location == "dataset-directory":
            alias = source.parent / "alias"
            alias.symlink_to(source, target_is_directory=True)
            source = alias
        elif location == "target-parent":
            alias = source.parent / "alias"
            alias.symlink_to(source.parent, target_is_directory=True)
            target = alias / "frozen"
        elif location == "base-file":
            actual = model / "actual.pt"
            (model / "model.pt").rename(actual)
            (model / "model.pt").symlink_to(actual)
        else:
            inputs.capture(source, target, base_model=model)
            actual = target / "actual-base"
            (target / "base").rename(actual)
            (target / "base").symlink_to(actual, target_is_directory=True)
    except (OSError, NotImplementedError) as error:
        pytest.skip(f"OS symlinks unavailable: {type(error).__name__}")
    with pytest.raises(inputs.InputsError):
        if location == "capsule-role":
            inputs.verify(target)
        else:
            inputs.capture(source, target, base_model=model)
    assert not list(source.parent.glob(".stk-training-input-*"))


def test_windows_reparse_attribute_is_rejected_even_without_a_symlink(source, monkeypatch):
    original_lstat = Path.lstat
    suspect = source / "samples.jsonl"

    def reparse(path, *args, **kwargs):
        info = original_lstat(path, *args, **kwargs)
        if path == suspect:
            return SimpleNamespace(st_mode=info.st_mode, st_file_attributes=0x400)
        return info

    monkeypatch.setattr(Path, "lstat", reparse)
    target = source.parent / "frozen"
    with pytest.raises(inputs.InputsError, match="reparse"):
        inputs.capture(source, target)
    assert_clean(source, target)


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="OS has no FIFO API")
def test_fifo_is_rejected_before_any_blocking_open(source):
    (source / "samples.jsonl").unlink()
    os.mkfifo(source / "samples.jsonl")
    target = source.parent / "frozen"
    with pytest.raises(inputs.InputsError, match="ordinary"):
        inputs.capture(source, target)
    assert_clean(source, target)


@pytest.mark.parametrize("filename", ["dataset.json", "samples.jsonl", "model.json", "model.pt"])
def test_byte_limits_fail_before_publication_with_private_staging_cleanup(source, monkeypatch, filename):
    model = make_model(source, "model")
    monkeypatch.setitem(inputs._LIMITS, filename, 1)
    target = source.parent / "frozen"
    with pytest.raises(inputs.InputsError):
        inputs.capture(source, target, base_model=model)
    assert_clean(source, target)


def test_manifest_budget_is_separate_and_failure_cleans_staging(source, monkeypatch):
    monkeypatch.setattr(inputs, "MAX_MANIFEST_BYTES", 16)
    target = source.parent / "frozen"
    with pytest.raises(inputs.InputsError, match="manifest"):
        inputs.capture(source, target)
    assert_clean(source, target)


def test_changes_during_copy_are_rejected_and_do_not_publish(source, monkeypatch):
    original_read = os.read
    changed = False

    def changing_read(descriptor, size):
        nonlocal changed
        raw = original_read(descriptor, size)
        if not changed:
            changed = True
            with (source / "dataset.json").open("ab") as handle:
                handle.write(b" ")
        return raw

    monkeypatch.setattr(os, "read", changing_read)
    target = source.parent / "frozen"
    with pytest.raises(inputs.InputsError, match="changed"):
        inputs.capture(source, target)
    assert changed
    assert_clean(source, target)


def test_ctime_is_compared_within_each_stat_api_not_between_apis(source, monkeypatch):
    original_fstat = os.fstat

    def different_ctime(descriptor):
        info = original_fstat(descriptor)
        fields = {name: getattr(info, name) for name in ("st_dev", "st_ino", "st_mode", "st_size", "st_mtime_ns")}
        fields["st_ctime_ns"] = info.st_ctime_ns + 10**12
        fields["st_file_attributes"] = getattr(info, "st_file_attributes", 0)
        return SimpleNamespace(**fields)

    monkeypatch.setattr(os, "fstat", different_ctime)
    target = source.parent / "frozen"
    manifest = inputs.capture(source, target)
    assert inputs.verify(target) == manifest


def test_changes_within_the_open_handle_stat_api_are_rejected(source, monkeypatch):
    original_fstat = os.fstat
    calls = 0

    def changed_ctime(descriptor):
        nonlocal calls
        calls += 1
        info = original_fstat(descriptor)
        fields = {name: getattr(info, name) for name in ("st_dev", "st_ino", "st_mode", "st_size", "st_mtime_ns")}
        fields["st_ctime_ns"] = info.st_ctime_ns + calls
        fields["st_file_attributes"] = getattr(info, "st_file_attributes", 0)
        return SimpleNamespace(**fields)

    monkeypatch.setattr(os, "fstat", changed_ctime)
    target = source.parent / "frozen"
    with pytest.raises(inputs.InputsError, match="changed"):
        inputs.capture(source, target)
    assert calls >= 2
    assert_clean(source, target)


def test_replacement_between_path_stat_and_open_is_rejected(source, monkeypatch):
    original_open = os.open
    suspect = source / "dataset.json"
    replacement = source / "replacement.json"
    replacement.write_bytes(suspect.read_bytes())
    swapped = False

    def replacement_open(path, *args, **kwargs):
        nonlocal swapped
        if not swapped and Path(path) == suspect:
            swapped = True
            replacement.replace(suspect)
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(os, "open", replacement_open)
    target = source.parent / "frozen"
    with pytest.raises(inputs.InputsError, match="changed"):
        inputs.capture(source, target)
    assert swapped
    assert_clean(source, target)


def test_copy_publication_failure_removes_only_owned_output(source, monkeypatch):
    original_link = os.link
    calls = 0

    def fail_second_link(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("synthetic link failure")
        return original_link(*args, **kwargs)

    monkeypatch.setattr(os, "link", fail_second_link)
    target = source.parent / "frozen"
    before = (source / "samples.jsonl").read_bytes()
    with pytest.raises(inputs.InputsError):
        inputs.capture(source, target)
    assert calls == 2
    assert_clean(source, target)
    assert (source / "samples.jsonl").read_bytes() == before


def test_racing_target_owner_is_preserved_and_manifest_is_last(source, monkeypatch):
    original_mkdir = Path.mkdir
    target = source.parent / "frozen"

    def race(path, *args, **kwargs):
        if path == target:
            original_mkdir(path)
            (path / "owner-file").write_bytes(b"synthetic race owner")
        return original_mkdir(path, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", race)
    with pytest.raises(inputs.InputsError):
        inputs.capture(source, target)
    assert (target / "owner-file").read_bytes() == b"synthetic race owner"
    assert not (target / "manifest.json").exists()
    assert not list(source.parent.glob(".stk-training-input-*"))


def test_partial_publication_is_not_loadable_before_the_atomic_manifest_marker(source, monkeypatch):
    original_link = os.link
    target = source.parent / "frozen"
    names = []

    def observe_link(src, dst, **kwargs):
        assert not (target / "manifest.json").exists()
        with pytest.raises(inputs.InputsError):
            inputs.verify(target)
        names.append(Path(dst).name)
        return original_link(src, dst, **kwargs)

    monkeypatch.setattr(os, "link", observe_link)
    manifest = inputs.capture(source, target)
    assert names == ["dataset.json", "samples.jsonl", "manifest.json"]
    assert inputs.verify(target) == manifest
