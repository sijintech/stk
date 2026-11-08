"""D1 input uploads and existing Hub device revocation on one Linux host.

Reuse offline.py's real two-deployment lifecycle, origin checks, deadlines and owned cleanup.
This module supplies a different fixed scenario; no product method, policy or schema is added.
Upload resumption here means querying/reopening the same partially uploaded session, without
injecting a transport failure. It does not test bridge-journal recovery or authorization races.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
HELPER = Path(__file__).with_name("offline.py")
INPUT = bytes(range(256)) * 4096 + "公开输入 input ✓\n".encode("utf-8")
DIGEST = hashlib.sha256(INPUT).hexdigest()
PATH = "input.bin"
CHUNK = 1024 * 1024
PROGRAM = (
    "import os, hashlib\n"
    "fd = os.open('../parity-start.marker', os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)\n"
    "os.write(fd, f'start {os.getpid()}\\n'.encode()); os.close(fd)\n"
    "data = open('input.bin', 'rb').read()\n"
    "open('digest.txt', 'w', encoding='ascii').write(hashlib.sha256(data).hexdigest() + '\\n')\n"
)
TASK = {"argv": ["{python}", "-c", PROGRAM], "inputs": [PATH], "input_hashes": {PATH: DIGEST},
        "outputs": ["digest.txt"], "name": "parity-input"}


def load_helper():
    spec = importlib.util.spec_from_file_location("input_transfer_offline_helper", HELPER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def wait_action(helper, hub, identity):
    deadline = time.monotonic() + helper.budget(30)
    while time.monotonic() < deadline:
        record = hub.action(identity)
        if time.monotonic() > deadline:
            break  # a terminal reply arriving after the frozen deadline cannot pass
        if record["state"] in ("succeeded", "failed", "rejected"):
            return record
        time.sleep(min(.05, helper.budget(.05)))
    raise helper.Unknown("the original input action did not finish within its frozen deadline")


def checks(a, b):
    """Expected public bytes and policy outcomes are fixed here, independent of reported success."""
    def both(predicate):
        return all(predicate(value) for value in (a, b))

    def once(value):
        runs = value.get("executions", [])
        return (value.get("task_count") == 1 and len(runs) == 1 and runs[0].get("start_markers") == 1
                and all(runs[0].get(key) is True for key in (
                    "marker_lines_valid", "marker_pid_is_program", "program_recorded", "program_exited",
                    "worker_exited", "finished_record")))

    expected_denials = {"upload.begin", "upload.status", "upload.chunk", "upload.finish", "action.read",
                       "action.create", "action.replay", "blob.read", "task.read", "workspace.read", "cold.status"}
    values = [
        ("I1", both(lambda v: v["partial"] == {"offset": CHUNK, "completed": False}
                     and v["resumed"] == {"same_id": True, "offset": CHUNK})),
        ("I2", both(lambda v: v["finish"] == {"size": len(INPUT), "offset": len(INPUT),
                                             "sha256": DIGEST, "completed": True})),
        ("I3", both(lambda v: v["files"] == [{"path": PATH, "size": len(INPUT), "sha256": DIGEST}])),
        ("I4", b["import"] == {"before": "review", "workspace_empty": True, "tasks_before": 0,
                                "approved": True, "after": "succeeded", "original_request": True}),
        ("I5", both(lambda v: v["task"]["state"] == "succeeded"
                     and v["task"]["input_manifest"] == [{"path": PATH, "size": len(INPUT), "sha256": DIGEST}]
                     and v["task"]["input_hashes"] == {PATH: DIGEST})),
        ("I6", both(lambda v: v["output"] == (DIGEST + "\n"))),
        ("I7", both(once)),
        ("I8", b["submit_review"] is True),
        ("I9", set(b["revoked"]["denials"]) == expected_denials
               and set(b["revoked"]["denials"].values()) == {401}),
        ("I10", b["revoked"]["before_authorized"] is True and b["revoked"]["acknowledged"] is True
                and b["revoked"]["node_online"] is True and b["revoked"]["new_action_absent"] is True
                and b["revoked"]["blob_target_absent"] is True),
        ("I11", b["revoked"]["runtime_task_unchanged"] is True
                and b["revoked"]["runtime_task_count"] == 1 and b["revoked"]["action_count_unchanged"] is True),
    ]
    return [{"id": name, "status": "pass" if ok else "fail"} for name, ok in values]


def configure(helper):
    """Adapt only this fresh helper module; product modules and their business methods stay intact."""
    context = {}
    original_hub, original_manifest, original_origins = helper.start_hub, helper.manifest, helper.module_origins
    helper.TEMPLATES = {}  # full frozen TaskSpecs require an explicit Hub review
    helper.KEY_MODULES += ("suan.control.uploads", "suan.control.blobs")

    def start_hub(owned, base, env, runtime_state):
        from suan.desktop_bridge.hub import HubClient
        ordinary, node_id, port = original_hub(owned, base, env, runtime_state)
        control = helper.python_cli("suan.control.cli:control", "suan-control")
        # Only credentials just generated by this owned test deployment are used; never exported.
        code = json.loads(owned.run("B pair desktop", control + ["pair", "--state-dir", str(base / "control"),
                                      "--role", "client", "--profile", "desktop"], env))["code"]
        claim = HubClient(ordinary.url).request("POST", "pairings/claim", {"code": code, "name": "input-client"})
        owner = json.loads((base / "control" / "control.json").read_text(encoding="utf-8"))["owner_token"]
        context.update(owner=HubClient(ordinary.url, owner, timeout=helper.HTTP_TIMEOUT),
                       device_id=claim["device_id"], work=owned.work)
        return HubClient(ordinary.url, claim["token"], timeout=helper.HTTP_TIMEOUT), node_id, port

    def exercise(side):
        backend = side.backend
        workspace = backend.create_workspace("input-parity", "input-workspace")["workspace"]["id"]
        side.record("workspace.create", workspace_id=workspace)
        begun = backend.upload_begin(workspace, PATH, len(INPUT), DIGEST)
        identity = begun["id"]
        backend.upload_chunk(workspace, identity, 0, INPUT[:CHUNK])
        partial = backend.upload_status(workspace, identity)
        resumed = backend.upload_begin(workspace, PATH, len(INPUT), DIGEST)
        backend.upload_chunk(workspace, identity, resumed["offset"], INPUT[resumed["offset"]:])
        finished = backend.upload_finish(workspace, identity)
        value = {"partial": {k: partial[k] for k in ("offset", "completed")},
                 "resumed": {"same_id": resumed["id"] == identity, "offset": resumed["offset"]},
                 "finish": {k: finished[k] for k in ("size", "offset", "sha256", "completed")}}
        side.record("upload.finish", size=finished["size"], sha256=finished["sha256"])
        if side.name == "B":
            from suan.desktop_bridge.backends import action_id
            files = [{"path": PATH, "size": len(INPUT), "sha256": DIGEST}]
            action = backend.post_import(workspace, files, action_id("workspace.import", backend.node_id, "input"))
            original = action["request"]
            before = {"before": action["state"], "workspace_empty": side.observer.files(workspace) == [],
                      "tasks_before": len(side.observer.tasks(workspace))}
            # An explicit test operator reviews the exact original request, then decides once.
            expected = {"workspace_id": workspace, "files": files}
            if original["payload"] != expected or action["state"] != "review":
                raise helper.HarnessError("the input import was not the expected reviewed request")
            approved = context["owner"].review(action["id"], True)
            after = wait_action(helper, backend.hub, action["id"])
            value["import"] = {**before, "approved": approved["state"] == "queued", "after": after["state"],
                               "original_request": after["request"] == original}
            side.record("workspace.import", action_id=action["id"], state=after["state"])
        value["files"] = [{k: item[k] for k in ("path", "size", "sha256")}
                          for item in backend.files(workspace)["files"]]
        spec = {**TASK, "workspace_id": workspace}
        submitted = backend.submit(spec, "input-task")
        if side.name == "B":
            action = backend.action_record(submitted["action"]["id"])
            value["submit_review"] = action["state"] == "review" and len(side.observer.tasks(workspace)) == 0
            if action["request"]["payload"]["spec"] != spec or not value["submit_review"]:
                raise helper.HarnessError("the input task was not the original frozen reviewed request")
            context["owner"].review(action["id"], True)
            submitted = {"task": wait_action(helper, backend.hub, action["id"])["result"]}
        task_id = submitted["task"]["id"]
        side.record("task.submit", task_id=task_id)
        task = helper.wait_terminal(side, task_id, 30)
        original_task = side.observer.task(task_id)
        value["task"] = {"state": task["state"], "input_manifest": [
                            {k: item[k] for k in ("path", "size", "sha256")} for item in original_task["input_manifest"]],
                         "input_hashes": original_task["spec"]["input_hashes"]}
        value["output"] = backend.read_chunk("task", task_id, "digest.txt", 0).decode("ascii")
        value["executions"] = helper.executions(side, workspace)
        value["task_count"] = len(side.observer.tasks(workspace))
        if side.name == "B":
            value["revoked"] = revoke(side, workspace, task_id)
        return value

    def revoke(side, workspace, task_id):
        from suan.desktop_bridge.hub import HubClient, HubResponseError
        from suan.desktop_bridge.protocol import BridgeError
        from suan.desktop_bridge.backends import action_id
        hub, owner = side.backend.hub, context["owner"]
        data = b"pending public input"
        digest = hashlib.sha256(data).hexdigest()
        pending = hub.upload_begin(digest, len(data))
        hub.upload_chunk(pending["id"], 0, data[:1])
        before_authorized = hub.upload_status(pending["id"])["offset"] == 1
        before_task = side.observer.task(task_id)
        before_actions = owner.actions()
        before_authorized = before_authorized and hub.action(before_actions[0]["id"])["id"] == before_actions[0]["id"]
        blocked = {"id": action_id("workspace.create", side.backend.node_id, "revoked-create"),
                   "node_id": side.backend.node_id, "kind": "workspace.create", "payload": {"name": "blocked"}}
        target = context["work"] / "revoked-download.bin"
        acknowledged = owner.request("DELETE", "devices/" + context["device_id"])
        cold = HubClient(hub.url, hub.token, timeout=helper.HTTP_TIMEOUT)
        denials = {}
        calls = {"upload.begin": lambda: hub.upload_begin(digest, len(data)),
                 "upload.status": lambda: hub.upload_status(pending["id"]),
                 "upload.chunk": lambda: hub.upload_chunk(pending["id"], 1, data[1:]),
                 "upload.finish": lambda: hub.upload_finish(pending["id"]),
                 "action.read": lambda: hub.action(before_actions[0]["id"]),
                 "action.create": lambda: hub.post_action(blocked),
                 "action.replay": lambda: hub.post_action(before_actions[0]["request"]),
                 "blob.read": lambda: hub.blob(DIGEST, target),
                 "task.read": lambda: hub.read(side.backend.node_id, "task.get", {"task_id": task_id}),
                 "workspace.read": lambda: hub.read(side.backend.node_id, "workspace.files", {"workspace_id": workspace}),
                 "cold.status": lambda: cold.upload_status(pending["id"])}
        for label, call in calls.items():
            helper.budget(1)
            try:
                call()
            except HubResponseError as exc:
                denials[label] = exc.status
            except BridgeError:
                denials[label] = "unexpected bridge error"
            else:
                denials[label] = "allowed"
        after_actions = owner.actions()
        return {"denials": denials, "before_authorized": before_authorized,
                "acknowledged": acknowledged == {"revoked": context["device_id"]},
                "node_online": any(d["id"] == side.backend.node_id and d["online"] for d in owner.devices()),
                "new_action_absent": blocked["id"] not in {a["id"] for a in after_actions},
                "blob_target_absent": not target.exists(),
                "runtime_task_unchanged": side.observer.task(task_id) == before_task,
                "runtime_task_count": len(side.observer.tasks(workspace)),
                "action_count_unchanged": len(after_actions) == len(before_actions)}

    def origins(env, mode):
        result = original_origins(env, mode)
        result["input_transfer_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        return result

    def manifest(*args):
        result = original_manifest(*args)
        result["verified"] = ["two-deployment input upload, reviewed Hub import and current device revocation"]
        result["input"] = {"size": len(INPUT), "sha256": DIGEST, "program_sha256": hashlib.sha256(PROGRAM.encode()).hexdigest()}
        result["not_verified"] += ["upload interruption or bridge journal recovery", "revocation racing an accepted request",
                                   "project/user authorization or recall of already delivered bytes"]
        return result

    helper.start_hub, helper.exercise = start_hub, exercise
    helper.module_origins, helper.manifest = origins, manifest
    helper.compare = lambda a, b: [{"A": a, "B": b, "category": "deployment policy and input semantics"}]
    helper.assertions = lambda a, b, rows: checks(a, b)
    return helper


def main(argv=None):
    helper = configure(load_helper())
    return helper.main(argv)


if __name__ == "__main__":
    sys.exit(main())
