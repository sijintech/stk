"""Persistent local training through the bridge and scripting facade, without granting agent tools access."""
from copy import deepcopy
import re

import pytest

from suan.agent import levels
from suan.desktop_bridge import schema
from suan.materials import datasets, inputs, training
from suan.scripting import Materials
from test_desktop_bridge import bridge_env, inproc  # noqa: F401


NEW_METHODS = {"materials.prepare", "materials.start", "materials.jobs.list",
               "materials.jobs.curves", "materials.jobs.recover"}
INTERNAL_FIELDS = {"request", "admission", "owner", "baseline_generation"}
OPTIONS = {"epochs": 3, "patience": 3, "hidden": [4], "batch_size": 40, "seed": 7}


@pytest.fixture
def tmp_path(tmp_path):
    return tmp_path.resolve()  # macOS /var is a link; capsules require physical ancestor paths.


def facade(harness):
    return Materials(lambda method, params: harness.call(method, params))


def outgoing(method, result):
    return schema.validate_outgoing({"id": 1, "result": result}, method)


def test_prepare_read_reopen_recover_and_cancel_never_load_torch_or_train(inproc, tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Preparation or observation attempted to load Torch or train")
    monkeypatch.setattr(training, "torch_module", forbidden)
    monkeypatch.setattr(training, "train", forbidden)
    h = inproc("persistent-materials")
    api = facade(h)
    directory = tmp_path / "public-data"
    card = api.synthetic(directory, "capacity_fade", 40, seed=5)
    first = api.prepare(directory, job_id="first", options=OPTIONS)
    second = api.prepare(directory, job_id="second", options=OPTIONS)
    assert first["state"] == second["state"] == "prepared"
    assert first["started_at"] is None and first["evaluation_preview"] is None
    assert first["card"]["sha256"] == card["sha256"]
    assert first["split_counts"] == {"train": 28, "validation": 6, "test": 6}
    assert not INTERNAL_FIELDS & first.keys()
    for path in directory.iterdir():
        path.unlink()
    assert api.prepare(directory, job_id="first", options=OPTIONS) == first
    page = api.jobs(limit=1)
    assert [job["id"] for job in page["jobs"]] == ["second"]
    assert (page["offset"], page["total"], page["next_offset"]) == (0, 2, 1)
    page = api.jobs(offset=1, limit=1)
    assert page["jobs"] == [first] and page["next_offset"] is None
    assert api.curves("first") == {"id": "first", "curves": [], "next_after": None, "recorded_epochs": 0}
    assert api.recover("first") == first
    assert api.cancel("second")["state"] == "cancelled"
    h.close()
    reopened = inproc("persistent-materials")
    again = facade(reopened)
    assert again.job("first") == first and again.job("second")["state"] == "cancelled"
    assert again.recover("first") == first
    assert again.models()["kinds"]["capacity_fade"]["versions"] == []
    assert not h.violations and not reopened.violations


def test_explicit_start_reports_missing_optional_torch_without_changing_the_frozen_task(inproc, tmp_path, monkeypatch):
    h = inproc()
    api = facade(h)
    directory = tmp_path / "data"
    api.synthetic(directory, "capacity_fade", 40)
    prepared = api.prepare(directory, job_id="without-torch", options=OPTIONS)
    def missing():
        raise training.TrainingUnavailable("Public test: CPU Torch is not installed")
    monkeypatch.setattr(training, "torch_module", missing)
    assert h.error("materials.start", {"job_id": prepared["id"]})["code"] == "unsupported"
    assert api.job(prepared["id"]) == prepared
    assert not h.violations


def test_real_cpu_start_uses_frozen_bytes_and_persists_losses_and_heldout_preview(inproc, tmp_path, monkeypatch):
    pytest.importorskip("torch")
    h = inproc("real-training")
    api = facade(h)
    directory = tmp_path / "data"
    api.synthetic(directory, "capacity_fade", 40, seed=9)
    prepared = api.prepare(directory, job_id="real", options=OPTIONS)
    frozen = inputs.verify(h.bridge.materials.root / "jobs" / "real" / "inputs")
    for path in directory.iterdir():
        path.unlink()
    job = api.start("real", poll=0.01, timeout=30)
    assert job["state"] in {"done", "rejected"}, job
    assert job["input_sha256"] == prepared["input_sha256"] == frozen["sha256"]
    assert job["comparison"]["candidate"] == job["metrics"]["test"]
    assert job["comparison"]["test_samples"] == len(frozen["split"]["test"])
    assert [sample["id"] for sample in job["evaluation_preview"]["samples"]] == frozen["split"]["test"][:3]
    assert all(sample["base"] is None and sample["baseline"] is None
               for sample in job["evaluation_preview"]["samples"])
    assert not INTERNAL_FIELDS & job.keys()
    after, epochs = 0, []
    while True:
        page = api.curves("real", after=after, limit=1)
        assert page["recorded_epochs"] == job["epoch"]
        epochs.extend(page["curves"])
        if page["next_after"] is None:
            break
        assert page["next_after"] > after
        after = page["next_after"]
    assert [item["epoch"] for item in epochs] == list(range(1, job["epoch"] + 1))
    assert epochs[-1]["train_loss"] == job["train_loss"]
    assert epochs[-1]["validation_loss"] == job["validation_loss"]
    h.close()
    def forbidden(*args, **kwargs):
        pytest.fail("Reading or replaying a completed task attempted new training")
    monkeypatch.setattr(training, "torch_module", forbidden)
    monkeypatch.setattr(training, "train", forbidden)
    reopened = inproc("real-training")
    again = facade(reopened)
    assert again.job("real") == job and again.jobs()["jobs"] == [job]
    assert again.curves("real")["curves"] == epochs
    assert again.start("real") == job and again.recover("real") == job
    assert again.train(directory, job_id="real") == job
    assert not h.violations and not reopened.violations


def test_explicit_recovery_records_interruption_without_loading_torch(inproc, tmp_path, monkeypatch):
    h = inproc()
    api = facade(h)
    directory = tmp_path / "data"
    api.synthetic(directory, "capacity_fade", 40)
    api.prepare(directory, job_id="stopped", options=OPTIONS)
    h.bridge.materials._store.update("stopped", {"state": "running", "started_at": "2026-10-29T00:00:00Z"})
    monkeypatch.setattr(training, "torch_module", lambda: pytest.fail("Recovery loaded Torch"))
    monkeypatch.setattr(training, "train", lambda *a, **k: pytest.fail("Recovery restarted training"))
    assert api.job("stopped")["state"] == api.jobs()["jobs"][0]["state"] == "running"
    recovered = api.recover("stopped")
    assert recovered["state"] == "interrupted" and recovered["reason"] == "trainer_stopped"
    assert api.start("stopped") == recovered
    assert not h.violations


@pytest.mark.parametrize("operation", ["materials.prepare", "materials.train"])
@pytest.mark.parametrize("options", [{"seed": 2**31}, {"seed": True}, {"split": [0.7, 0.3]},
                                     {"split": [0.7, 0.3, 0]}, {"split": [1.1, 0.1, 0.1]}, {"extra": 1}])
def test_training_options_share_the_strict_schema_bounds(operation, options):
    assert schema.validate_params(operation, {"directory": "/public-data", "job_id": "x", "options": options})


def test_split_sum_and_realized_nonempty_bounds_are_checked_before_training(inproc, tmp_path, monkeypatch):
    h = inproc()
    monkeypatch.setattr(training, "torch_module", lambda: pytest.fail("Invalid split loaded Torch"))
    directory = tmp_path / "data"
    datasets.write_synthetic(directory, "capacity_fade", 20)
    for split in ([0.3, 0.3, 0.3], [0.98, 0.01, 0.01]):
        params = {"directory": str(directory), "job_id": "bad", "options": {"split": split}}
        assert not schema.validate_params("materials.prepare", params)
        assert h.error("materials.prepare", params)["code"] == "invalid_params"
    assert facade(h).jobs()["total"] == 0


@pytest.mark.parametrize("method,params", [
    ("materials.jobs.list", {"offset": -1}), ("materials.jobs.list", {"offset": 1000001}),
    ("materials.jobs.list", {"limit": 0}), ("materials.jobs.list", {"limit": 101}),
    ("materials.jobs.curves", {"job_id": "x", "after": 5001}),
    ("materials.jobs.curves", {"job_id": "x", "limit": 1001}),
    ("materials.start", {"job_id": "../x"}), ("materials.jobs.recover", {"job_id": "x", "start": True})])
def test_new_api_rejects_out_of_bounds_and_extra_parameters(inproc, method, params):
    h = inproc()
    assert schema.validate_params(method, params)
    assert h.error(method, params)["code"] == "invalid_params"
    assert not h.violations


def test_new_methods_are_discoverable_without_expanding_agent_tool_permissions(inproc):
    h = inproc()
    catalog = h.call("script.catalog")["operations"]
    assert NEW_METHODS <= catalog.keys()
    assert {name: levels.level(name) for name in NEW_METHODS} == {
        "materials.prepare": "prepare_run", "materials.start": "submit_run", "materials.jobs.list": "read",
        "materials.jobs.curves": "read", "materials.jobs.recover": "record"}
    assert all(levels.OPERATIONS[name][1] for name in NEW_METHODS)
    assert not NEW_METHODS & {operation for operations in levels.TOOL_USES.values() for operation in operations}
    assert levels.AGENT_LEVELS == ("read", "record", "model", "draft")
    assert not h.violations


@pytest.mark.parametrize("state", ["running", "done", "rejected", "cancelled", "failed"])
def test_schema_keeps_legacy_jobs_and_model_versions_readable(state):
    old_job = {"id": "old", "kind": "capacity_fade", "state": state, "epoch": 1, "epochs": 2,
               "error": None, "version": None, "metrics": None, "gate": 0.1, "started_at": "2026-10-01"}
    assert not outgoing("materials.jobs.get", {"job": old_job})
    old_version = {"version": "v1", "created_at": "2026-10-01", "dataset": {"synthetic": True},
                   "metrics": {"normalized_rmse": 0.05}, "gate": 0.1}
    assert not outgoing("materials.models.list", {"kinds": {"capacity_fade": {"active": "v1", "versions": [old_version]}},
                                                 "gates": {"capacity_fade": 0.1}})


def test_schema_validates_new_provenance_and_excludes_private_job_fields(inproc, tmp_path):
    h = inproc()
    directory = tmp_path / "data"
    datasets.write_synthetic(directory, "capacity_fade", 40)
    job = facade(h).prepare(directory, job_id="provenance", options={**OPTIONS, "seed": 2**31 - 1})
    for state in ("prepared", "interrupted", "uncertain"):
        assert not outgoing("materials.jobs.get", {"job": {**job, "state": state}})
    for field in INTERNAL_FIELDS:
        assert outgoing("materials.jobs.get", {"job": {**job, field: None}})
    comparison = {"format": "stk.materials-training-comparison/1", "test_sha256": "a" * 64,
                  "test_samples": 6, "candidate": {"samples": 6, "rmse": 0.01, "normalized_rmse": 0.05},
                  "base": None, "baseline": None}
    version = {"version": "v1", "job_id": job["id"], "input_sha256": job["input_sha256"],
               "model_sha256": "b" * 64, "weights_sha256": "c" * 64, "comparison": comparison,
               "base_version": None, "baseline_version": None}
    result = {"entry": {"active": "v1", "versions": [version]}}
    assert not outgoing("materials.models.activate", result)
    damaged = deepcopy(result)
    damaged["entry"]["versions"][0]["weights_sha256"] = "not-a-checksum"
    assert outgoing("materials.models.activate", damaged)
    assert h.error("materials.prepare", {"directory": str(directory), "job_id": "missing-base", "base_version": "v9"})["code"] == "not_found"
    assert not h.violations


@pytest.mark.parametrize("action", ["train", "start"])
def test_scripting_wait_preserves_explicit_start_and_legacy_train_polling(action, monkeypatch):
    calls = []
    def call(method, params):
        calls.append((method, params))
        return {"job": {"id": "job", "state": "done" if method == "materials.jobs.get" else "running"}}
    monkeypatch.setattr("time.sleep", lambda seconds: None)
    api = Materials(call)
    if action == "train":
        job = api.train("/data", job_id="job", base_version="v2", options={"seed": 5}, poll=0)
        assert calls[0] == ("materials.train", {"directory": "/data", "job_id": "job", "options": {"seed": 5}, "base_version": "v2"})
    else:
        job = api.start("job", poll=0)
        assert calls[0] == ("materials.start", {"job_id": "job"})
    assert job["state"] == "done" and calls[1:] == [("materials.jobs.get", {"job_id": "job"})]


def test_scripting_forwards_prepare_pagination_recovery_and_nonwaiting_train():
    calls = []
    def call(method, params):
        calls.append((method, params))
        return {"job": {"id": params.get("job_id"), "state": "prepared"}, "jobs": [], "curves": []}
    api = Materials(call)
    api.prepare("/data", options={}, base_version="v3")
    assert calls[-1][0] == "materials.prepare" and re.fullmatch("[a-f0-9]{32}", calls[-1][1]["job_id"])
    assert calls[-1][1]["options"] == {} and calls[-1][1]["base_version"] == "v3"
    api.jobs(offset=4, limit=7)
    api.curves("old", after=10, limit=3)
    api.recover("old")
    api.train("/data", job_id="old", wait=False)
    assert calls[1:] == [("materials.jobs.list", {"offset": 4, "limit": 7}),
                         ("materials.jobs.curves", {"job_id": "old", "after": 10, "limit": 3}),
                         ("materials.jobs.recover", {"job_id": "old"}),
                         ("materials.train", {"directory": "/data", "job_id": "old"})]
