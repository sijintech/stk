"""Separate network process. Blender's main thread only exchanges private files.

The immutable command ID is also the server action/message ID, so retrying a
lost response never invents a second computational operation.
"""
import argparse
import base64
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
from queue import Empty, Queue
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener
import uuid

from suan.control.agent import endpoint
from suan.runtime.common import atomic_json, instance_lock, read_json

DEFAULT_CONTROL_URL = "http://127.0.0.1:8790"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError("Control redirects are not allowed")


class ControlConnection:
    def __init__(self, url, token=""):
        self.url, self.token = endpoint(url), token

    def request(self, method, path, body=None):
        request = Request(self.url + "/api/v1/" + path, method=method,
                          data=json.dumps(body, ensure_ascii=False, allow_nan=False).encode() if body is not None else None,
                          headers={"Authorization": "Bearer " + self.token, "Content-Type": "application/json"})
        try:
            with build_opener(NoRedirect()).open(request, timeout=20) as response:
                return json.load(response)
        except HTTPError as exc:
            if exc.code == 429 or exc.code == 408 or exc.code >= 500:
                raise URLError("Transient control error; retry the same operation identity") from exc
            try:
                message = json.load(exc).get("detail", "Control request rejected")
            except (ValueError, AttributeError):
                message = "Control request rejected"
            raise ValueError(str(message)) from exc

    def events(self, after, stop):
        request = Request(self.url + "/api/v1/events?after=" + str(after), headers={
            "Authorization": "Bearer " + self.token, "Accept": "text/event-stream",
            "Last-Event-ID": str(after)})
        with build_opener(NoRedirect()).open(request, timeout=20) as response:
            cursor = after
            for raw in response:
                if stop.is_set():
                    return
                line = raw.decode("utf-8").strip()
                if line.startswith("id:"):
                    cursor = int(line[3:].strip())
                elif not line and cursor > after:
                    yield cursor
                    after = cursor


class EventReader:
    """A dedicated SSE reader only queues cursors; it never mutates UI state."""
    def __init__(self, connection, cursor):
        self.connection, self.cursor = connection, cursor
        self.stop, self.events = threading.Event(), Queue()
        self.thread = threading.Thread(target=self.run, daemon=True, name="stk-control-events")
        self.thread.start()

    def run(self):
        delay = 1
        while not self.stop.is_set():
            try:
                for cursor in self.connection.events(self.cursor, self.stop):
                    self.cursor = cursor
                    self.events.put(cursor)
                    delay = 1
            except (OSError, ValueError):
                pass
            self.stop.wait(delay)
            delay = min(30, delay * 2)


class Bridge:
    def __init__(self, state_dir, connection=None):
        self.root = Path(state_dir)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        (self.root / "commands").mkdir(exist_ok=True, mode=0o700)
        (self.root / "receipts").mkdir(exist_ok=True, mode=0o700)
        self.config = {"url": DEFAULT_CONTROL_URL, "token": "", **read_json(self.root / "client.json", {})}
        self.connection = connection or ControlConnection(self.config["url"], self.config.get("token", ""))
        self.state = read_json(self.root / "state.json", {})
        self.state.setdefault("selection", {"node_id": "", "workspace_id": "", "task_id": "", "path": ""})
        self.state.setdefault("session_id", uuid.uuid4().hex)
        self.state.setdefault("messages", [])
        self.state.setdefault("devices", [])
        self.state.setdefault("actions", [])
        self.state.setdefault("artifacts", [])
        self.state.setdefault("logs", "")
        self.state.setdefault("pending", {})
        self.state.setdefault("view_request", "")
        self.state.setdefault("inspected_action", "")
        self.state.setdefault("event_cursor", 0)
        self.event_reader = None
        self.state["connected"] = False
        self.last_refresh = 0
        self.publish()

    def publish(self):
        self.state["revision"] = self.state.get("revision", 0) + 1
        atomic_json(self.root / "state.json", self.state)

    def remember(self, command):
        atomic_json(self.root / "receipts" / (command["id"] + ".json"), {"command": command})

    def execute(self, command):
        identity = command.get("id", "")
        if len(identity) != 32 or any(c not in "0123456789abcdef" for c in identity):
            raise ValueError("Invalid command identity")
        receipt = read_json(self.root / "receipts" / (identity + ".json"))
        if receipt:
            if receipt["command"] != command:
                raise ValueError("Command ID reused with different content")
            return
        kind = command["kind"]
        p = command.get("payload", {})
        selection = self.state["selection"]
        if kind == "select":
            allowed = {"node_id", "workspace_id", "task_id", "path"}
            if set(p) - allowed:
                raise ValueError("Invalid selection")
            if "node_id" in p:
                selection.update(workspace_id="", task_id="", path="")
            if "workspace_id" in p:
                selection.update(task_id="", path="")
            if "task_id" in p:
                selection["path"] = ""
            if set(p) & {"node_id", "workspace_id", "task_id"}:
                self.state.update(artifacts=[], logs="")
            for key in set(p) - {"path"}:
                if p[key] and not re.fullmatch(r"[a-f0-9]{32}", p[key]):
                    raise ValueError("Invalid selection identity")
            selection.update(p)
            self.state["status"] = "选择已更新"
        elif kind == "pair":
            connection = ControlConnection(p["url"])
            result = connection.request("POST", "pairings/claim", {"code": p["code"], "name": "STK Blender 工作台"})
            if result["role"] != "client":
                raise ValueError("Use a client pairing code")
            # As in the launcher, the template belongs to the service it was chosen for.
            same = self.config["url"] == connection.url
            self.config = {**({"template": self.config["template"]} if same and self.config.get("template") else {}),
                           "url": connection.url, "token": result["token"]}
            atomic_json(self.root / "client.json", self.config)
            self.connection = ControlConnection(connection.url, result["token"])
            self.state["event_cursor"] = 0
            if self.event_reader:
                self.event_reader.stop.set()
                self.event_reader = None
            # Do not preserve one-time pairing codes in receipts.
            self.state["status"] = "设备已配对"
            self.publish()
            return
        elif kind == "session.select":
            session_id = p["session_id"]
            if not re.fullmatch(r"[a-f0-9]{32}", session_id):
                raise ValueError("Invalid session identity")
            result = self.connection.request("GET", "sessions/" + session_id)
            self.state.update(session_id=session_id, messages=result["messages"])
        elif kind == "chat":
            result = self.connection.request("POST", "sessions/" + self.state["session_id"] + "/messages",
                                             {"id": identity, "content": p["content"]})
            self.state["messages"] = result["messages"]
        elif kind == "review.inspect":
            if not re.fullmatch(r"[a-f0-9]{32}", p["action_id"]):
                raise ValueError("Invalid action identity")
            result = self.connection.request("GET", "actions/" + p["action_id"])
            self.state["logs"] = json.dumps({"id": result["id"], "state": result["state"],
                "reason": result["review_reason"], "request": result["request"]}, ensure_ascii=False, indent=2)
            self.state["inspected_action"] = result["id"]
        elif kind == "review":
            if not re.fullmatch(r"[a-f0-9]{32}", p["action_id"]):
                raise ValueError("Invalid action identity")
            if p["approved"] and self.state["inspected_action"] != p["action_id"]:
                raise ValueError("请先查看操作详情，在日志区检查完整参数和资源后再批准")
            self.connection.request("POST", f"actions/{p['action_id']}/review", {"approved": p["approved"]})
        elif kind == "refresh":
            self.last_refresh = 0
        else:
            if kind == "task.submit" and "template" in p and "spec" not in p and self.config.get("template"):
                # The native run button sends demo-field; run the workbench's configured template.
                # The receipt keeps the original command, so a replay stays idempotent.
                p = {**p, "template": self.config["template"]}
            body = {"id": identity, "node_id": command.get("node_id", selection["node_id"]), "kind": kind, "payload": p}
            if not body["node_id"]:
                raise ValueError("请先选择执行节点")
            result = self.connection.request("POST", "actions", body)
            self.state["pending"][identity] = {"request": body, "state": result["state"]}
            if kind == "view.build":
                self.state["view_request"] = identity
            self.state["status"] = "操作等待复核" if result["state"] == "review" else "操作已提交"
            # Persist tracking before acknowledging the command file.
            self.publish()
        self.publish()
        self.remember(command)

    def apply_result(self, record):
        request, result = record["request"], record["result"]
        kind, payload = request["kind"], request["payload"]
        selection = self.state["selection"]
        if request["node_id"] != selection["node_id"]:
            return
        if kind == "workspace.create":
            selection["workspace_id"] = result["id"]
        elif kind == "task.submit":
            if payload.get("spec", {}).get("workspace_id") != selection["workspace_id"]:
                return
            selection["task_id"] = result["id"]
            selection["path"] = ""
            self.state.update(artifacts=[], logs="")
        elif payload.get("task_id") != selection["task_id"]:
            return
        elif kind == "task.artifacts":
            self.state["artifacts"] = result
        elif kind == "task.logs":
            self.state["logs"] = base64.b64decode(result["data"]).decode("utf-8", errors="replace")
        elif kind == "view.probe":
            self.state["logs"] = json.dumps(result, ensure_ascii=False, indent=2)
        elif (kind == "view.build" and payload.get("path") == selection["path"]
              and record["id"] == self.state["view_request"]):
            from .scene import validate_scene
            validate_scene(result)
            result["manifest"]["source"] = {"node_id": request["node_id"],
                "task_id": payload["task_id"], "path": payload["path"], "action_id": record["id"]}
            atomic_json(self.root / "scene.json", result)
            self.state["scene_id"] = record["id"]
            self.state["manifest"] = result["manifest"]

    def refresh(self):
        if not self.config.get("token") and isinstance(self.connection, ControlConnection):
            self.state["status"] = "输入控制服务地址和客户端配对码"
            self.publish()
            return
        self.state["devices"] = self.connection.request("GET", "devices")
        self.state["actions"] = self.connection.request("GET", "actions")
        self.state["sessions"] = self.connection.request("GET", "sessions")
        session = self.connection.request("GET", "sessions/" + self.state["session_id"])
        self.state["messages"] = session["messages"]
        # Actions initiated on another device (including AI tools) need the
        # same result handling when this desktop has the corresponding task open.
        for action in self.state["actions"]:
            if action["request"]["node_id"] == self.state["selection"]["node_id"] and action["state"] in {"queued", "review"}:
                self.state["pending"].setdefault(action["id"], {"request": action["request"], "state": action["state"]})
        for identity in list(self.state["pending"]):
            record = self.connection.request("GET", "actions/" + identity)
            if record["state"] == "succeeded":
                self.apply_result(record)
            elif record["state"] == "failed":
                self.state["status"] = record["error"]
            if record["state"] in {"succeeded", "failed", "rejected"}:
                self.state["pending"].pop(identity)
        self.state["connected"] = True
        self.state["last_seen"] = datetime.now(timezone.utc).isoformat()
        self.publish()

    def tick(self):
        if self.event_reader:
            try:
                while True:
                    self.state["event_cursor"] = self.event_reader.events.get_nowait()
                    self.last_refresh = 0
            except Empty:
                pass
        elif isinstance(self.connection, ControlConnection) and self.connection.token:
            self.event_reader = EventReader(self.connection, self.state["event_cursor"])
        for path in sorted((self.root / "commands").glob("*.json"), key=lambda p: p.stat().st_mtime_ns):
            if path.is_symlink():
                continue
            try:
                command = read_json(path)
                self.execute(command)
                path.unlink()
            except (OSError, URLError):
                self.state.update(connected=False, status="连接中断，保留原操作 ID 自动重试")
                self.publish()
                break
            except (ValueError, KeyError, TypeError) as exc:
                self.state["status"] = str(exc)[:2000]
                self.publish()
                path.rename(path.with_suffix(".rejected"))
        if time.monotonic() - self.last_refresh >= 3:
            self.last_refresh = time.monotonic()
            try:
                self.refresh()
            except (OSError, ValueError):
                self.state.update(connected=False, status="控制服务不可用，显示最近状态")
                self.publish()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-dir", required=True)
    args = parser.parse_args()
    root = Path(args.state_dir)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    with instance_lock(root / "bridge.lock"):
        bridge = Bridge(root)
        while True:
            bridge.tick()
            time.sleep(.2)


if __name__ == "__main__":
    main()
