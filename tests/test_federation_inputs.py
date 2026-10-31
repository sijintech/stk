"""Private owner capsules bind metadata and bytes without choosing cooperation formats."""
from copy import deepcopy
import json
from uuid import UUID

import pytest

from suan.federation import inputs


def capsule(tmp_path, **kwargs):
    return inputs.capture(tmp_path / "datasets" / str(UUID(int=1)), str(UUID(int=1)),
                          [[1.0], [2.0]], [[3.0], [5.0]], **kwargs)


def test_capsule_exact_retry_and_changed_original(tmp_path):
    expected = capsule(tmp_path, feature_names=["temperature"], target_names=["response"])
    actual, raw = inputs.load(tmp_path / "datasets" / str(UUID(int=1)))
    assert actual == expected and actual["dataset_sha256"] != actual["data_sha256"]
    assert capsule(tmp_path, feature_names=["temperature"], target_names=["response"]) == expected
    with pytest.raises(ValueError):
        capsule(tmp_path, feature_names=["renamed"], target_names=["response"])
    assert raw and actual["num_examples"] == 2


@pytest.mark.parametrize("field,value", [("feature_names", ["different"]), ("target_names", ["different"]),
                                        ("num_examples", True), ("bytes", True), ("dataset_id", str(UUID(int=2)))])
def test_capsule_metadata_tampering_is_rejected(tmp_path, field, value):
    capsule(tmp_path)
    path = tmp_path / "datasets" / str(UUID(int=1)) / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest[field] = value
    path.write_bytes(inputs.canonical(manifest))
    with pytest.raises(ValueError):
        inputs.load(path.parent)


@pytest.mark.parametrize("x,y", [([[True]], [[1]]), ([[float("nan")]], [[1]]),
    ([[float("inf")]], [[1]]), ([[1], [2, 3]], [[1], [2]]), ([[1]], [[1], [2]]), ([], []), ([[1]], [[None]])])
def test_numeric_capsule_rejects_bad_values_and_shapes(tmp_path, x, y):
    with pytest.raises(ValueError):
        inputs.capture(tmp_path / "datasets" / str(UUID(int=1)), str(UUID(int=1)), x, y)


def test_budget_is_enforced_before_registration_publication(tmp_path, monkeypatch):
    monkeypatch.setattr(inputs, "MAX_PRIVATE_BYTES", 8)
    with pytest.raises(ValueError, match="quota"):
        capsule(tmp_path)
    assert not (tmp_path / "datasets" / str(UUID(int=1))).exists()


def test_concurrent_capsules_share_the_same_quota_lease(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    first = capsule(tmp_path)
    monkeypatch.setattr(inputs, "MAX_PRIVATE_BYTES", first["bytes"] * 2 + 1)
    barrier = Barrier(2)
    def register(index):
        barrier.wait()
        identity = str(UUID(int=index))
        try:
            inputs.capture(tmp_path / "datasets" / identity, identity, [[1.], [2.]], [[3.], [5.]])
            return True
        except ValueError:
            return False
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(register, (2, 3)))
    assert sorted(results) == [False, True]


def test_dataset_payload_tamper_and_unlisted_files(tmp_path):
    capsule(tmp_path)
    folder = tmp_path / "datasets" / str(UUID(int=1))
    original = (folder / "data.bin").read_bytes()
    (folder / "data.bin").write_bytes(original[:-1] + b"\xff")
    with pytest.raises(ValueError):
        inputs.load(folder)
    (folder / "data.bin").write_bytes(original)
    (folder / "extra").write_bytes(b"unexpected")
    with pytest.raises(ValueError):
        inputs.load(folder)


def test_capsule_rejects_links(tmp_path):
    capsule(tmp_path)
    folder = tmp_path / "datasets" / str(UUID(int=1))
    original = folder / "data.bin"
    other = tmp_path / "other.bin"
    original.rename(other)
    try:
        original.symlink_to(other)
    except OSError:
        pytest.skip("symlink unavailable on this host")
    with pytest.raises(ValueError):
        inputs.load(folder)
