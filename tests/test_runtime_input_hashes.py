"""Expected input hashes are checked on the task's copied bytes before it can be queued."""
import hashlib

import pytest

from conftest import finish
from suan.runtime.client import RuntimeErrorResponse
from suan.runtime.models import TaskSpec
from suan.desktop_bridge.backends import RuntimeBackend, HubBackend
from suan.desktop_bridge.protocol import BridgeError


def test_checked_inputs_are_frozen_and_retries_do_not_recheck_changed_workspace(runtime, tmp_path):
    client, supervisor, _, _ = runtime
    assert "input_checksums" in client.health()["features"]
    workspace = client.create_workspace("Checked inputs")["id"]
    path = tmp_path / "input.txt"
    path.write_bytes(b"version one")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    client.upload(workspace, path)
    spec = TaskSpec(workspace, ["{python}", "-c", "from pathlib import Path; Path('result.txt').write_bytes(Path('input.txt').read_bytes())"],
                    inputs=["input.txt"], input_hashes={"input.txt": digest}, outputs=["result.txt"])
    task = client.submit(spec, "checked-job")
    assert task["state"] == "queued" and task["input_manifest"][0]["sha256"] == digest
    path.write_bytes(b"version two")
    client.upload(workspace, path)
    assert client.submit(spec, "checked-job")["id"] == task["id"]
    changed = {**spec.to_dict(), "input_hashes": {"input.txt": hashlib.sha256(path.read_bytes()).hexdigest()}}
    with pytest.raises(RuntimeErrorResponse, match="different task"):
        client.submit(changed, "checked-job")
    assert finish(client, supervisor, task["id"])["state"] == "succeeded"
    artifact = next(item for item in client.artifacts(task["id"]) if item["path"] == "result.txt")
    assert artifact["sha256"] == digest


def test_mismatch_records_failure_and_never_starts_the_program(runtime, tmp_path):
    client, supervisor, server, _ = runtime
    workspace = client.create_workspace("Mismatch")["id"]
    path = tmp_path / "input.txt"
    path.write_bytes(b"unexpected bytes")
    client.upload(workspace, path)
    spec = TaskSpec(workspace, ["{python}", "-c", "open('ran', 'w').close()"], inputs=["input.txt"], input_hashes={"input.txt": "0" * 64})
    with pytest.raises(RuntimeErrorResponse, match="checksum mismatch"):
        client.submit(spec, "mismatch")
    failed = client.tasks()[0]
    assert failed["state"] == "failed" and "not queued" in failed["reason"]
    assert failed["input_manifest"][0]["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    supervisor.tick()
    assert not (server.service.task_dir(failed["id"]) / "work/ran").exists()
    assert not client.task(failed["id"]).get("attempted_at")
    # The failed attempt still owns the key; fixing the input requires a deliberately new attempt.
    assert client.submit(spec, "mismatch")["id"] == failed["id"]
    assert len(client.tasks()) == 1


def test_checks_the_actual_copy_not_a_prior_workspace_observation(runtime, tmp_path, monkeypatch):
    from suan.runtime import service
    client, supervisor, _, _ = runtime
    workspace = client.create_workspace("Copy race")["id"]
    path = tmp_path / "input.txt"
    path.write_bytes(b"expected")
    client.upload(workspace, path)
    original = service.shutil.copy2
    def changed_copy(source, target, *args, **kwargs):
        answer = original(source, target, *args, **kwargs)
        target.write_bytes(b"different copied bytes")
        return answer
    monkeypatch.setattr(service.shutil, "copy2", changed_copy)
    with pytest.raises(RuntimeErrorResponse, match="checksum mismatch"):
        client.submit(TaskSpec(workspace, ["{python}", "-c", "pass"], inputs=["input.txt"],
                               input_hashes={"input.txt": hashlib.sha256(path.read_bytes()).hexdigest()}), "copy-race")
    supervisor.tick()
    assert client.tasks()[0]["state"] == "failed"


def test_bridge_refuses_unadvertised_support_without_posting_a_task_or_hub_action():
    class Client:
        url = "http://127.0.0.1:1"
        def health(self):
            return {"features": ["events"]}
        def submit(self, *args):
            raise AssertionError("unsupported submission must not be posted")
        def devices(self):
            return [{"id": "b" * 32, "role": "node", "snapshot": {"health": self.health()}}]
        def post_action(self, *args):
            raise AssertionError("unsupported submission must not create an action")
    spec = {"workspace_id": "a" * 32, "argv": ["solver"], "inputs": [], "input_hashes": {}}
    for backend in (RuntimeBackend("local", Client()), HubBackend("hub:test", Client(), "b" * 32)):
        with pytest.raises(BridgeError) as caught:
            backend.submit(spec, "checked")
        assert caught.value.code == "unsupported"
