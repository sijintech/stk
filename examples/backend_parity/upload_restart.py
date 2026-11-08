"""D1 upload restart (CL-D1-UPLOAD-RESTART-15): a real desktop Bridge is SIGKILLed after the Hub accepted an
input chunk but before the Bridge journaled that acknowledgement; the same Bridge state resumes the original
transfer at the Hub's held offset, and the reviewed workspace.import still needs an explicit decision.

One private loopback deployment on one Linux host, through the helpers of ``offline.py`` (lifecycle, origin,
deadline, owned cleanup) and ``disconnect.py`` (process identities, the SIGKILL record), both loaded by file
path and read-only: a Runtime, a real Hub and an outbound NodeAgent; plus a real stdio Bridge
(``suan.desktop_bridge``) paired with the Hub as a desktop client, whose real TransferManager uploads one fixed
public multi-chunk input.

Two test-only drivers, written into this run's private directory and bound by SHA-256 (hashed when written and
again right before launch; a missing or mismatched proof fails the run), start the real Bridge entry point:

* the crash driver wraps the real ``HubClient.upload_chunk``: it calls it first, and its first successful return
  (the Hub now holds exactly one chunk) is held, so the Bridge never journals that ACK; the harness proves the
  accepted offset and bytes, then SIGKILLs that Bridge. If the hold expires the driver exits (status 75), which
  can never count as the injected fault.
* the observe driver records the real ``HubClient.upload_begin/status/chunk/finish`` calls of the restarted
  Bridge (offsets, the session ID, the returned offset) and changes nothing.

Evidence (``--evidence-dir``, new or empty): run-manifest.json, requests.jsonl, phases.json, assertions.json,
resources.json -- no tokens, pairing codes, environment values, absolute paths, file content or raw exception text.
This is a software-behaviour check: one Linux host and one process crash; not a network partition, cross-host
recovery, R3, a licensed solver or scientific validation.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import queue
import subprocess
import sys
import tempfile
import threading
import time

HERE = Path(__file__).resolve().parent
DISCONNECT_FILE = HERE / "disconnect.py"


def load_disconnect():
    """disconnect.py, which loads offline.py by file path: one shared helper instance, read-only reuse."""
    spec = importlib.util.spec_from_file_location("backend_parity_upload_restart_helpers", DISCONNECT_FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


dis = load_disconnect()
off = dis.off
# Bind the Bridge, its transfer journal and the Hub upload sessions into the module-origin hashes too (this
# fresh helper instance only; the helper files are not changed).
off.KEY_MODULES += ("suan.desktop_bridge.server", "suan.desktop_bridge.transfers", "suan.desktop_bridge.connections",
                    "suan.desktop_bridge.__main__", "suan.control.uploads")

CHUNK = 1024 * 1024
INPUT = bytes(range(256)) * (10 * 1024) + "公开上传 upload ✓\n".encode("utf-8")  # 2.5 MiB + a UTF-8 tail
DIGEST = hashlib.sha256(INPUT).hexdigest()
REMOTE = "input.bin"
HUB = "parity-hub"  # the Bridge's name for its paired Hub connection
WORKSPACE_KEY, UPLOAD_KEY = "ur-ws", "ur-upload"  # caller idempotency keys, not secrets
HOLD_EXPIRED = 75

CRASH_DRIVER = r'''"""Test-only Bridge driver (crash run) of upload_restart.py; it exists only in that run's private directory.

It wraps the real HubClient.upload_chunk: the real call runs first; its first successful return is held, so
the Bridge never journals that acknowledgement. Stages only; if the hold expires the process exits (75).
"""
import json
import os
from pathlib import Path
import sys
import threading
import time


def install(client_class, control, hold_seconds):
    stages, lock, state = Path(control) / "stages.jsonl", threading.Lock(), {"held": False}
    deadline = time.monotonic() + hold_seconds
    original = client_class.upload_chunk

    def stage(name, **fields):
        with lock, open(stages, "a", encoding="utf-8") as stream:
            stream.write(json.dumps({"stage": name, "t": time.monotonic(), **fields}) + "\n")

    def upload_chunk(self, upload_id, offset, data):
        result = original(self, upload_id, offset, data)
        with lock:
            hold = not state["held"]
            state["held"] = True
        if hold:
            stage("accepted_held", upload_id=upload_id, offset=offset, length=len(data),
                  returned_offset=result.get("offset"), completed=result.get("completed"))
            while time.monotonic() < deadline:
                time.sleep(0.05)
            stage("hold_expired")
            os._exit(75)
        return result

    client_class.upload_chunk = upload_chunk


def main():
    control, hold_seconds = sys.argv[1], float(sys.argv[2])
    from suan.desktop_bridge.hub import HubClient
    install(HubClient, control, hold_seconds)
    from suan.desktop_bridge.__main__ import main as bridge
    bridge(sys.argv[3:])


if __name__ == "__main__":
    main()
'''

OBSERVE_DRIVER = r'''"""Test-only Bridge driver (restart run) of upload_restart.py; it exists only in that run's private directory.

It records the real HubClient upload calls (offsets, session ID, returned offset) and changes nothing.
"""
import json
from pathlib import Path
import sys
import threading
import time


def install(client_class, control):
    stages, lock = Path(control) / "stages.jsonl", threading.Lock()

    def stage(name, **fields):
        with lock, open(stages, "a", encoding="utf-8") as stream:
            stream.write(json.dumps({"stage": name, "t": time.monotonic(), **fields}) + "\n")

    def wrap(name, describe):
        original = getattr(client_class, name)

        def call(self, *args):
            result = original(self, *args)
            stage(name, **describe(args, result))
            return result
        setattr(client_class, name, call)

    record = lambda result: {"returned_id": result.get("id"), "returned_offset": result.get("offset"),
                             "completed": result.get("completed")}
    wrap("upload_begin", lambda a, r: {"sha256": a[0], "size": a[1], **record(r)})
    wrap("upload_status", lambda a, r: {"upload_id": a[0], **record(r)})
    wrap("upload_chunk", lambda a, r: {"upload_id": a[0], "offset": a[1], "length": len(a[2]), **record(r)})
    wrap("upload_finish", lambda a, r: {"upload_id": a[0], **record(r)})


def main():
    control = sys.argv[1]
    from suan.desktop_bridge.hub import HubClient
    install(HubClient, control)
    from suan.desktop_bridge.__main__ import main as bridge
    bridge(sys.argv[3:])


if __name__ == "__main__":
    main()
'''

DRIVERS = {"crash": CRASH_DRIVER, "observe": OBSERVE_DRIVER}
DRIVER_SHA256 = {name: hashlib.sha256(text.encode("utf-8")).hexdigest() for name, text in DRIVERS.items()}
DRIVER_MISMATCH = "a private Bridge driver file does not have the expected bytes; it was not launched"


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def drivers_bound(facts):
    """Both Bridge drivers were the expected text: hashed when written and right before launch, and launched.
    Missing proof is no proof."""
    drivers = facts.get("drivers")
    if not isinstance(drivers, dict) or set(drivers) != set(DRIVERS):
        return False
    return all(isinstance(drivers[name], dict) and drivers[name].get("expected_sha256") == DRIVER_SHA256[name]
               and drivers[name].get("written_sha256") == DRIVER_SHA256[name]
               and drivers[name].get("launch_sha256") == DRIVER_SHA256[name] and drivers[name].get("launched") is True
               for name in DRIVERS)


# ----------------------------------------------------------------------------------------------------
# The real Bridge over stdio


class BridgeCallError(Exception):
    """A Bridge error response; only its fixed code is kept."""

    def __init__(self, code):
        super().__init__(code)
        self.code = code


class Bridge:
    """A real ``suan.desktop_bridge --stdio`` process started through a driver, registered with this run's owned
    processes (so the helpers' cleanup stops it). Requests are NDJSON lines; replies are matched by ID."""

    def __init__(self, owned, label, driver_file, control, env, state_dir, cache_dir, log):
        self.label, self.log, self.next_id, self.replies = label, log, 0, {}
        self.condition = threading.Condition()
        command = [sys.executable, str(driver_file), str(control), str(off.budget(170)), "--stdio", "--state-dir",
                   str(state_dir), "--cache-dir", str(cache_dir), "--strict"]
        with open(owned.work / f"{label.replace(' ', '-')}.stderr", "ab") as errors:
            self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors,
                                            env=env, cwd=owned.work, start_new_session=True)
        owned.processes.append((label, self.process))
        owned.resources["processes"].append({"label": label, "pid": self.process.pid, "how": "spawned by this run"})
        self.identity = None
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self):
        for line in self.process.stdout:
            try:
                message = json.loads(line)
            except ValueError:
                continue
            if isinstance(message, dict) and "id" in message and ("result" in message or "error" in message):
                with self.condition:
                    self.replies[message["id"]] = message
                    self.condition.notify_all()

    def call(self, method, params, timeout=30):
        """One request; a reply after the frozen deadline is not accepted. The request log keeps the method and
        its outcome only, never the params (a pairing code, local paths)."""
        self.next_id += 1
        identity = f"{self.label[0]}{self.next_id}"
        deadline = time.monotonic() + off.remaining(timeout)
        line = json.dumps({"id": identity, "method": method, "params": params}) + "\n"
        try:
            self.process.stdin.write(line.encode("utf-8"))
            self.process.stdin.flush()
        except OSError:
            self.log.append({"bridge": self.label, "method": method, "outcome": "not sent"})
            raise off.HarnessError(f"{self.label}: the request {method} could not be sent")
        with self.condition:
            while identity not in self.replies and time.monotonic() < deadline:
                self.condition.wait(min(0.1, max(0.0, deadline - time.monotonic())))
            reply = self.replies.pop(identity, None)
        if reply is None or time.monotonic() > deadline:
            self.log.append({"bridge": self.label, "method": method, "outcome": "unknown"})
            raise off.Unknown(f"{self.label}: {method} did not answer within its frozen deadline")
        if "error" in reply:
            code = (reply["error"] or {}).get("code") if isinstance(reply["error"], dict) else None
            self.log.append({"bridge": self.label, "method": method, "outcome": "error", "code": code})
            raise BridgeCallError(code)
        self.log.append({"bridge": self.label, "method": method, "outcome": "ok"})
        return reply["result"]

    def close(self, timeout=15):
        """End the protocol stream (stdin EOF) and wait, bounded, for the process to exit."""
        try:
            self.process.stdin.close()
        except OSError:
            pass
        try:
            return self.process.wait(min(timeout, off.CLEANUP_GRACE))
        except subprocess.TimeoutExpired:
            return None


def read_stages(control):
    try:
        lines = (Path(control) / "stages.jsonl").read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return []
    stages = []
    for line in lines:
        try:
            stages.append(json.loads(line))
        except ValueError:
            stages.append({"stage": "malformed"})
    return stages


def wait_until(predicate, timeout, what):
    """Poll ``predicate`` within a frozen deadline; a value that arrives after it cannot pass."""
    deadline = time.monotonic() + off.remaining(timeout)
    while time.monotonic() < deadline:
        value = predicate()
        if value and time.monotonic() <= deadline:
            return value
        time.sleep(0.05)
    raise off.Unknown(f"{what} before its frozen deadline")


def write_driver(owned, name, facts):
    path = owned.work / "drivers" / name / "bridge_driver.py"
    path.parent.mkdir(parents=True)
    path.write_bytes(DRIVERS[name].encode("utf-8"))
    facts["drivers"][name] = {"expected_sha256": DRIVER_SHA256[name], "written_sha256": sha256_file(path),
                              "launch_sha256": None, "launched": False}
    if facts["drivers"][name]["written_sha256"] != DRIVER_SHA256[name]:
        raise off.HarnessError(DRIVER_MISMATCH)
    return path


def launch_bridge(owned, name, label, path, env, bridge_state, facts, log):
    """Hash the driver file right before launch; a mismatch launches nothing."""
    facts["drivers"][name]["launch_sha256"] = sha256_file(path)
    if facts["drivers"][name]["launch_sha256"] != DRIVER_SHA256[name]:
        raise off.HarnessError(DRIVER_MISMATCH)
    bridge = Bridge(owned, label, path, path.parent, env, bridge_state / "state", bridge_state / "cache", log)
    facts["drivers"][name]["launched"] = True
    bridge.identity = dis.identity_of(bridge.process.pid)
    return bridge


def session_status(hub_client, upload_id):
    """The Hub's answer for an upload session: ``open``/``completed`` while it exists, else the HTTP status."""
    from suan.desktop_bridge.hub import HubResponseError
    try:
        return "completed" if hub_client.upload_status(upload_id).get("completed") else "open"
    except HubResponseError as exc:
        return exc.status


def session_view(hub_client, upload_id):
    """The Hub's public record of an upload session (``{id, offset, completed, size}``), or ``{"http": status}``
    when it does not exist (an observation, never an error that hides the state)."""
    from suan.desktop_bridge.hub import HubResponseError
    try:
        return hub_client.upload_status(upload_id)
    except HubResponseError as exc:
        return {"http": exc.status}


def hub_part(control_state, upload_id):
    """The Hub's partial upload file of a session, from this run's own Hub state (read-only)."""
    found = list(Path(control_state).glob(f"**/.uploads/{upload_id}.part"))
    return found[0] if len(found) == 1 else None


# ----------------------------------------------------------------------------------------------------
# Scenario


def scenario(owned, env, facts, log, clients):
    from suan.desktop_bridge.backends import RuntimeBackend, action_id
    from suan.desktop_bridge.hub import HubClient
    from suan.desktop_bridge.protocol import PROTOCOL_VERSION
    from suan.desktop_bridge.transfers import TransferManager
    work = owned.work
    facts["drivers"] = {}
    crash_file, observe_file = write_driver(owned, "crash", facts), write_driver(owned, "observe", facts)
    client, port_runtime, workspace_root = off.start_runtime(owned, work / "B" / "runtime", env, "B")
    clients.append(("B", client))
    hub, node_id, port_hub = off.start_hub(owned, work / "B", env, work / "B" / "runtime")
    facts["ports"] = {"runtime": port_runtime, "hub": port_hub}
    direct = RuntimeBackend("runtime:upload-restart-direct", client)  # this run's own Runtime, read-only here
    off.wait_node_live(dis.budgeted_hub_backend()("hub:upload-restart", hub, node_id, wait=30),
                       time.monotonic() + off.budget(30))
    control_state = work / "B" / "control"
    cli = off.python_cli("suan.control.cli:control", "suan-control")
    # Test-owned credentials of this deployment only, kept in memory and never exported.
    code = json.loads(owned.run("B pair desktop", cli + ["pair", "--state-dir", str(control_state), "--role",
                                                         "client", "--profile", "desktop"], env))["code"]
    owner = HubClient(hub.url, json.loads((control_state / "control.json").read_text(encoding="utf-8"))["owner_token"],
                      timeout=off.HTTP_TIMEOUT)
    pids = {item["label"]: item["pid"] for item in owned.resources["processes"]}
    services = {label: dis.identity_of(pids[label]) for label in ("B hub serve", "B node run", "B runtime api",
                                                                    "B runtime supervisor")}
    source = work / "source" / REMOTE
    source.parent.mkdir()
    source.write_bytes(INPUT)
    bridge_state = work / "bridge"
    connection = "hub:" + HUB

    # 1. The original Bridge pairs once, creates the workspace and starts the one keyed upload.
    first = launch_bridge(owned, "crash", "Bridge original", crash_file, env, bridge_state, facts, log)
    first.call("hello", {"protocol": PROTOCOL_VERSION, "resume_transfers": False})
    first.call("connections.pair_hub", {"name": HUB, "url": hub.url, "code": code, "device_name": "upload-restart"})
    code = None
    hubs = json.loads((bridge_state / "state" / "hubs.json").read_text(encoding="utf-8"))
    device_before = hubs[HUB]["device_id"]
    created = first.call("workspace.create", {"connection": connection, "node": node_id, "name": "upload-restart",
                                              "idempotency_key": WORKSPACE_KEY})
    workspace = (created.get("workspace") or {}).get("id")
    if not workspace:
        raise off.Unknown("the workspace was not created")
    request = {"connection": connection, "node": node_id, "workspace_id": workspace, "source": str(source),
               "remote": REMOTE}
    started = first.call("upload.start", {**request, "idempotency_key": UPLOAD_KEY})
    transfer_id = started["transfer"]["id"]
    accepted = wait_until(lambda: next((s for s in read_stages(crash_file.parent) if s["stage"] == "accepted_held"),
                                       None), 30, "the Hub did not accept a held first chunk")
    upload_id = accepted["upload_id"]
    bridge_client = HubClient(hub.url, hubs[HUB]["token"], timeout=off.HTTP_TIMEOUT)  # the Bridge's own device
    status = session_view(bridge_client, upload_id)
    part = hub_part(control_state, upload_id)
    held = part.read_bytes() if part is not None else b""
    journal_path = bridge_state / "state" / "transfers" / f"{transfer_id}.json"
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    item = (journal.get("items") or [{}])[0]
    facts["accepted"] = {
        "transfer_is_keyed": transfer_id == TransferManager.keyed_id("upload", UPLOAD_KEY),
        "first_chunk_offset": accepted["offset"], "first_chunk_length": accepted["length"],
        "hub_returned_offset": accepted["returned_offset"], "hub_completed": accepted["completed"],
        "hub_status": {"same_session": status.get("id") == upload_id, "offset": status.get("offset"),
                       "completed": status.get("completed"), "size": status.get("size")},
        "hub_part": {"present": part is not None, "bytes": len(held),
                     "matches_input_prefix": held == INPUT[:len(held)] and len(held) > 0},
        "journal": {"state": journal.get("state"), "upload_id_is_session": item.get("upload_id") == upload_id,
                    "bytes_done": journal.get("bytes_done"), "item_done": item.get("done"),
                    "request_is_original": journal.get("request") == request},
        "bridge_alive": dis.alive(first.identity), "total": len(INPUT)}

    # 2. Only the original Bridge dies.
    facts["bridge_stop"] = dis.stop_node(first.process, first.identity)
    after_kill = json.loads(journal_path.read_text(encoding="utf-8"))
    facts["outage"] = {"services_alive": {label: dis.alive(identity) for label, identity in services.items()},
                       "journal_state": after_kill.get("state"),
                       "journal_upload_id_kept": ((after_kill.get("items") or [{}])[0]).get("upload_id") == upload_id,
                       "hub_offset": session_view(bridge_client, upload_id).get("offset"),
                       "hold_expired": any(s["stage"] == "hold_expired" for s in read_stages(crash_file.parent))}

    # 3. The same Bridge state reopens and explicitly resumes the original transfer.
    second = launch_bridge(owned, "observe", "Bridge restarted", observe_file, env, bridge_state, facts, log)
    second.call("hello", {"protocol": PROTOCOL_VERSION, "resume_transfers": False})
    recovered = second.call("transfer.get", {"id": transfer_id})["transfer"]
    hubs_after = [c for c in second.call("connections.list", {})["connections"] if c.get("kind") == "hub"]
    replay = second.call("upload.start", {**request, "idempotency_key": UPLOAD_KEY})["transfer"]  # same key: same transfer
    resumed = second.call("transfer.resume", {"id": transfer_id})["transfer"]
    in_review = wait_until(lambda: (lambda t: t if (t.get("action") or {}).get("state") == "review" else None)(
        second.call("transfer.get", {"id": transfer_id})["transfer"]), 60, "the import did not reach review")
    stages = read_stages(observe_file.parent)
    begins = [s for s in stages if s["stage"] == "upload_begin"]
    chunks = [s for s in stages if s["stage"] == "upload_chunk"]
    finishes = [s for s in stages if s["stage"] == "upload_finish"]
    expected_offsets = list(range(accepted["returned_offset"] or -1, len(INPUT), CHUNK))
    facts["restart"] = {
        "recovered_state": recovered.get("state"), "same_transfer": recovered.get("id") == transfer_id,
        "same_hub_device": [c.get("device_id") for c in hubs_after] == [device_before],
        "key_replay_same_transfer": replay.get("id") == transfer_id, "resumed_state": resumed.get("state"),
        "begins": [{"same_session": b.get("returned_id") == upload_id, "returned_offset": b.get("returned_offset"),
                    "frozen_digest": b.get("sha256") == DIGEST and b.get("size") == len(INPUT)} for b in begins],
        "chunks": [{"same_session": c.get("upload_id") == upload_id, "offset": c.get("offset"),
                    "length": c.get("length"), "returned_offset": c.get("returned_offset")} for c in chunks],
        "expected_chunk_offsets": expected_offsets,
        "finishes": [{"same_session": f.get("upload_id") == upload_id, "completed": f.get("completed")}
                     for f in finishes]}

    # 4. The reviewed import: nothing lands before an explicit decision on the exact original request.
    action = in_review["action"]
    expected_action = action_id("workspace.import", node_id, transfer_id, 0)
    record = owner.action(action["id"])
    files = [{"path": REMOTE, "sha256": DIGEST, "size": len(INPUT)}]
    facts["review"] = {"action_is_derived": action["id"] == expected_action,
                       "request_exact": record.get("request") == {"id": expected_action, "node_id": node_id,
                                                                  "kind": "workspace.import",
                                                                  "payload": {"workspace_id": workspace, "files": files}},
                       "state_before": record.get("state"), "transfer_before": in_review.get("state"),
                       "workspace_files_before": len(direct.files(workspace)["files"]),
                       "tasks_before": len(direct.tasks(workspace)["tasks"])}
    approved = owner.review(action["id"], True)
    done = wait_until(lambda: (lambda t: t if t.get("state") in ("completed", "failed", "cancelled") else None)(
        second.call("transfer.get", {"id": transfer_id})["transfer"]), 60, "the transfer did not finish")
    target = work / "check" / REMOTE
    target.parent.mkdir()
    client.download_input(workspace, REMOTE, target)
    landed = target.read_bytes()
    actions = [a for a in owner.actions() if (a.get("request") or {}).get("node_id") == node_id]
    facts["completion"] = {"approved": approved.get("state") == "queued", "transfer_state": done.get("state"),
                           "same_transfer": done.get("id") == transfer_id,
                           "action_after": owner.action(action["id"]).get("state"),
                           "files": [{k: f.get(k) for k in ("path", "size", "sha256")}
                                     for f in direct.files(workspace)["files"]],
                           "bytes_match": landed == INPUT,
                           "tasks": len(direct.tasks(workspace)["tasks"]),
                           "action_kinds": sorted((a.get("request") or {}).get("kind") for a in actions),
                           "transfers": len(second.call("transfer.list", {})["transfers"]),
                           "hub_session_after": session_status(bridge_client, upload_id)}
    facts["bridge_close_exit"] = second.close()


def assertions(facts, requests):
    """U0-U9 over the recorded facts; any missing or malformed fact fails its check."""
    def check(predicate):
        try:
            return bool(predicate())
        except (KeyError, TypeError, AttributeError, IndexError):
            return False

    accepted, stop, outage, restart, review, completion = (
        facts.get(name) or {} for name in ("accepted", "bridge_stop", "outage", "restart", "review", "completion"))
    total = len(INPUT)

    def held_offset():
        return accepted["hub_returned_offset"]

    checks = [
        ("U0 both Bridge drivers had the expected bytes (hashed when written and right before launch)",
         lambda: drivers_bound(facts)),
        ("U1 accepted before the lost ACK: the Hub returned and holds at least 1 MiB but not all bytes, the held bytes "
         "are the input's prefix, and the Bridge's journal has the session but not that acknowledgement",
         lambda: accepted["transfer_is_keyed"] is True and accepted["first_chunk_offset"] == 0
         and accepted["hub_completed"] is False and CHUNK <= held_offset() < total
         and held_offset() == accepted["first_chunk_length"]
         and accepted["hub_status"] == {"same_session": True, "offset": held_offset(), "completed": False, "size": total}
         and accepted["hub_part"] == {"present": True, "bytes": held_offset(), "matches_input_prefix": True}
         and accepted["journal"]["upload_id_is_session"] is True and accepted["journal"]["request_is_original"] is True
         and accepted["journal"]["item_done"] is False and accepted["journal"]["bytes_done"] < held_offset()
         and accepted["journal"]["state"] == "running" and accepted["bridge_alive"] is True),
        ("U2 only the original Bridge was killed: alive right before the SIGKILL, killed by it, reaped and gone; Hub, "
         "node and Runtime stayed alive; the hold never expired",
         lambda: stop["identity_valid"] is True and stop["running_before_kill"] is True
         and stop["alive_before_kill"] is True and stop["signal_sent"] is True and stop["exit_code"] == -9
         and stop["killed_by_sigkill"] is True and stop["reaped"] is True and stop["node_alive_after"] is False
         and len(outage["services_alive"]) == 4 and all(outage["services_alive"].values())
         and outage["hold_expired"] is False),
        ("U3 the crash left the original journal unfinished (running, same session) and the Hub still held the offset",
         lambda: outage["journal_state"] == "running" and outage["journal_upload_id_kept"] is True
         and outage["hub_offset"] == held_offset()),
        ("U4 the same Bridge state reopened the same transfer (interrupted), the same Hub device, and the same key "
         "returned the same transfer; the explicit resume ran it",
         lambda: restart["recovered_state"] == "interrupted" and restart["same_transfer"] is True
         and restart["same_hub_device"] is True and restart["key_replay_same_transfer"] is True
         and restart["resumed_state"] in ("queued", "running")),
        ("U5 resumed at the held offset in the same Hub session: never from zero, contiguous to the end, one finish",
         lambda: len(restart["begins"]) == 1 and restart["begins"][0] == {"same_session": True,
                                                                         "returned_offset": held_offset(),
                                                                         "frozen_digest": True}
         and restart["expected_chunk_offsets"] and restart["expected_chunk_offsets"][0] == held_offset()
         and [c["offset"] for c in restart["chunks"]] == restart["expected_chunk_offsets"]
         and all(c["same_session"] is True for c in restart["chunks"])
         and all(c["offset"] + c["length"] == c["returned_offset"] for c in restart["chunks"])
         and restart["chunks"][-1]["returned_offset"] == total
         and restart["finishes"] == [{"same_session": True, "completed": True}]),
        ("U6 the import waited for an explicit review of its exact original request; nothing landed before it",
         lambda: review["action_is_derived"] is True and review["request_exact"] is True
         and review["state_before"] == "review" and review["transfer_before"] == "running"
         and review["workspace_files_before"] == 0 and review["tasks_before"] == 0),
        ("U7 after the approval the original transfer completed and the workspace holds exactly the input",
         lambda: completion["approved"] is True and completion["transfer_state"] == "completed"
         and completion["same_transfer"] is True and completion["action_after"] == "succeeded"
         and completion["files"] == [{"path": REMOTE, "size": total, "sha256": DIGEST}]
         and completion["bytes_match"] is True and completion["hub_session_after"] == 404),  # released at finish
        ("U8 nothing else ran: one transfer, no task, only the workspace creation and the one import",
         lambda: completion["transfers"] == 1 and completion["tasks"] == 0
         and completion["action_kinds"] == ["workspace.create", "workspace.import"]),
        ("U9 requests: one pairing, one workspace creation, the keyed upload (and its same-key replay), one explicit "
         "resume; no pairing after the restart",
         lambda: [(r["bridge"], r["method"]) for r in requests if r["method"] in (
             "connections.pair_hub", "workspace.create", "upload.start", "transfer.resume")] == [
             ("Bridge original", "connections.pair_hub"), ("Bridge original", "workspace.create"),
             ("Bridge original", "upload.start"), ("Bridge restarted", "upload.start"),
             ("Bridge restarted", "transfer.resume")]
         and all(r["outcome"] == "ok" for r in requests)),
    ]
    return [{"id": name, "status": "pass" if check(predicate) else "fail"} for name, predicate in checks]


# ----------------------------------------------------------------------------------------------------
# Run


def manifest(origins, ports):
    record = off.manifest("<private temporary directory>", ports, origins)
    record.pop("schema", None)  # informal trial evidence, not a published format
    record.pop("templates", None)
    record.update({
        "record": "D1 upload-restart trial evidence (informal)",
        "deployments": {"B": ["B/runtime (api, supervisor)", "B/control (hub serve)", "B/node (node run)",
                              "bridge (stdio Bridge; original SIGKILLed, then the same state restarted)"]},
        "input": {"size": len(INPUT), "sha256": DIGEST, "chunk": CHUNK},
        "drivers": {name: {"sha256": digest} for name, digest in DRIVER_SHA256.items()},
        "verified": ["on one Linux host: a real Bridge is SIGKILLed after the Hub accepted an upload chunk whose ACK "
                     "the Bridge had not journaled; the same Bridge state resumes the original transfer in the same "
                     "Hub session at the held offset, and the reviewed import lands only after an explicit decision"],
        "not_verified": ["a crash at other points (before a chunk is sent, during finish or the import)",
                         "a Bridge crash with several chunks in flight or several files",
                         "network partitions, cross-host recovery, Hub or Runtime restarts, R3",
                         "a program reading the uploaded input (no task is submitted here)",
                         "Windows/macOS, sites, licensed software or scientific validity"]})
    return record


def run(evidence, work_root=None, keep=False, mode="installed", deadline_seconds=170):
    deadline_seconds = off.check_deadline(deadline_seconds)
    started = time.monotonic()
    off.DEADLINE = started + deadline_seconds
    owned, env = None, None
    resources = {"processes": [], "directories": [], "cleanup": [], "work_dir_created": False}
    log, facts, clients, error, origins, scenario_seconds = [], {}, [], None, None, None
    try:
        owned = off.Owned(Path(tempfile.mkdtemp(prefix="stk-upload-restart-", dir=work_root)))
        owned.resources["work_dir_created"] = True
        resources = owned.resources
        env = owned.env(mode)
        origins = off.module_origins(env, mode)
        origins["offline_helper_sha256"] = origins.pop("harness_sha256", None)
        origins["disconnect_helper_sha256"] = sha256_file(DISCONNECT_FILE)
        origins["upload_restart_sha256"] = sha256_file(__file__)
        origins["driver_sha256"] = dict(DRIVER_SHA256)
        if not origins["consistent"]:
            raise off.HarnessError(f"--mode {mode} does not match where STK is imported from")
        scenario(owned, env, facts, log, clients)
        scenario_seconds = time.monotonic() - started
    except BridgeCallError as exc:
        error = {"kind": "error", "code": exc.code, "message": "a Bridge call failed"}
    except Exception as exc:  # noqa: BLE001 - evidence is still written and owned processes stopped
        error = off.exported_error(exc)
    finally:
        if owned is None:
            resources["leftover_pids_after_cleanup"] = []
        else:
            off.clean_up(owned, env, keep, clients)
    elapsed = time.monotonic() - started
    cleanup_ok = off.cleanup_status(resources, keep)
    checks = assertions(facts, log) if error is None else []
    within_deadline = scenario_seconds is not None and scenario_seconds <= deadline_seconds
    driver_ok = drivers_bound(facts)  # required explicitly, besides U0
    ok = (error is None and bool(checks) and all(c["status"] == "pass" for c in checks) and cleanup_ok
          and within_deadline and driver_ok)
    if origins is not None:
        origins["driver_files_match"] = driver_ok
    evidence = Path(evidence)
    evidence.mkdir(parents=True, exist_ok=True)
    ports = {f"B_{name}": port for name, port in (facts.get("ports") or {}).items()}
    phases = {key: value for key, value in facts.items() if key != "ports"}
    (evidence / "run-manifest.json").write_text(json.dumps({
        **manifest(origins, ports), "deadline_seconds": deadline_seconds, "scenario_seconds": scenario_seconds,
        "within_deadline": within_deadline, "elapsed_seconds_including_cleanup": elapsed,
        "cleanup_grace_seconds_per_step": off.CLEANUP_GRACE, "error": error, "cleanup_ok": cleanup_ok, "ok": ok},
        indent=1, ensure_ascii=False), encoding="utf-8")
    with open(evidence / "requests.jsonl", "w", encoding="utf-8") as stream:
        for entry in log:
            stream.write(json.dumps(entry, ensure_ascii=False) + "\n")
    (evidence / "phases.json").write_text(json.dumps(phases, indent=1, ensure_ascii=False), encoding="utf-8")
    (evidence / "assertions.json").write_text(json.dumps({"error": error, "assertions": checks, "cleanup_ok": cleanup_ok,
                                                          "within_deadline": within_deadline,
                                                          "drivers_bound": driver_ok, "ok": ok},
                                                         indent=1, ensure_ascii=False), encoding="utf-8")
    (evidence / "resources.json").write_text(json.dumps(resources, indent=1), encoding="utf-8")
    return ok, error, elapsed


def main(argv=None):
    parser = argparse.ArgumentParser(description="A real Bridge dies after the Hub accepted a chunk; it resumes.")
    parser.add_argument("--evidence-dir", required=True, type=Path, help="A new or empty directory for this trial.")
    parser.add_argument("--mode", choices=("installed", "source"), default="installed",
                        help="installed: the interpreter's installed STK (nothing injected); source: this source tree "
                             "through PYTHONPATH. The run fails if the actual import origin differs.")
    parser.add_argument("--deadline", type=float, default=170,
                        help="Budget in seconds for setup and the scenario (finite, positive). Cleanup afterwards "
                             f"gets its own bounded grace per step (up to {off.CLEANUP_GRACE} s); use an external "
                             "watchdog for an absolute limit.")
    parser.add_argument("--work-root", type=Path, default=None, help="Parent of the private temporary directory.")
    parser.add_argument("--keep", action="store_true", help="Keep the deployment's state for inspection.")
    args = parser.parse_args(argv)
    if platform.system() != "Linux":
        print("The STK Runtime and control service run on Linux only.", file=sys.stderr)
        return 2
    try:
        off.check_deadline(args.deadline)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    try:
        if args.evidence_dir.exists() and any(args.evidence_dir.iterdir()):
            print("--evidence-dir must be a new or empty directory (earlier trials are never overwritten).",
                  file=sys.stderr)
            return 2
    except OSError:
        print("--evidence-dir cannot be inspected.", file=sys.stderr)
        return 2
    if args.mode == "source":
        root = str(HERE.parents[1])
        if root not in sys.path:
            sys.path.insert(0, root)
    try:
        ok, error, elapsed = run(args.evidence_dir, args.work_root, args.keep, args.mode, args.deadline)
    except Exception as exc:  # noqa: BLE001 - never print raw exception text
        ok, error, elapsed = False, off.exported_error(exc), None
    print(json.dumps({"ok": ok, "error": error, "elapsed_seconds": elapsed}))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
