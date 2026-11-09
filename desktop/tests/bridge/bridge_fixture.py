# SPDX-License-Identifier: GPL-2.0-or-later
"""Fixtures for the stk_bridge integration tests (desktop/tests/bridge), run with the repo's Python.

    bridge_fixture.py check [bridge|graph|runtime|hub]
                                             exit 0 when that part can run here (else prints why)
    bridge_fixture.py write-run DIR          a fake muFerro run (tests/mupro_fake.write_domain_run)
    bridge_fixture.py runtime WORKDIR        a loopback Runtime (127.0.0.1, ephemeral port) running one
                                             task that, once the file `gate` exists, writes UTF-8 log
                                             lines slowly (so a test can subscribe first); prints one JSON
                                             line {url, token_file, task_id, gate, expected_stdout}, and serves
                                             until stdin reaches EOF, then cancels its tasks and stops.
    bridge_fixture.py hub WORKDIR            a loopback Hub (tests/test_hub_desktop_bridge.LiveHub: uvicorn on
                                             127.0.0.1, a real NodeAgent.run over WebSocket, the loopback Runtime)
                                             with one finished task, once a heartbeat lists it; prints one JSON
                                             line {url, node_id, task_id, workspace_id, code_file, missing_id,
                                             proxy_env_cleared}, then answers one JSON line per stdin command, each
                                             from one read of the Hub's device record:
                                               state    the device online/last_seen/features/snapshot rows (the
                                                        synthetic ones counted apart), action ids, actions.changed
                                                        count, the Runtime's task ids and its own state of the task
                                               window   the node's heartbeats list 201 newer synthetic tasks, so the
                                                        task leaves the bounded 200-task snapshot (as in
                                                        tests/test_runtime_hub_cli.py); answers with the next real
                                                        heartbeat that carries them. missing_id is listed there but
                                                        absent from the Runtime
                                               offline  stops the node agent; answers once the Hub sees it offline
                                               online   restarts it; answers with its first heartbeat after that
                                             EOF stops the agent (also when already offline), the Hub, then the
                                             Runtime (also when the Hub cleanup failed); prints {"closed": true,
                                             "stopped": {...}} and exits 0 only when everything stopped.

The token never appears on stdout: it goes to WORKDIR/token (mode 0600) for connections.add_runtime
token_file; the Hub's one-time client pairing code (no desktop profile) likewise goes to
WORKDIR/pair-code (mode 0600).
Nothing listens beyond 127.0.0.1. The hub mode drops this process's proxy variables before it creates
any client (LiveHub's httpx client trusts the environment) and reports only their names.
"""
import json
import os
from pathlib import Path
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

LOG_LINES = 30


def log_program(gate):
    """Waits for ``gate`` to exist (the test subscribed), then writes UTF-8 lines slowly."""
    return (
        "import os, sys, time\n"
        "deadline = time.monotonic() + 300\n"
        f"while not os.path.exists({str(gate)!r}) and time.monotonic() < deadline:\n"
        "    time.sleep(0.02)\n"
        f"for i in range({LOG_LINES}):\n"
        "    sys.stdout.write(f'第{i}步 计算完成：能量 −1.5e-3 🧲\\n')\n"
        "    sys.stdout.flush()\n"
        "    time.sleep(0.12)\n"
        "sys.stdout.write('结束')\n"
    )


def expected_stdout():
    return "".join(f"第{i}步 计算完成：能量 −1.5e-3 🧲\n" for i in range(LOG_LINES)) + "结束"


CHECKS = {
    "bridge": ["suan.desktop_bridge.server"],
    # Local evaluation of the fake muFerro run (tests/test_desktop_bridge.py skips likewise).
    "graph": ["suan.desktop_bridge.server", "numpy", "vtk", "matplotlib"],
    "runtime": ["suan.desktop_bridge.server", "suan.runtime.server", "suan.runtime.supervisor"],
    "hub": ["suan.desktop_bridge.server", "suan.runtime.server", "suan.runtime.supervisor", "fastapi", "uvicorn",
            "httpx", "websockets", "suan.control.app", "suan.control.agent", "test_hub_desktop_bridge"],
}


def check(what="bridge"):
    import importlib
    for module in CHECKS[what]:
        try:
            importlib.import_module(module)
        except BaseException as exc:  # pragma: no cover - diagnostic path (also pytest's import skip)
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            print(f"{module} does not import: {type(exc).__name__}: {exc}")
            return 1
    if what in ("runtime", "hub") and not sys.platform.startswith("linux"):
        print("the STK Runtime is Linux-only")
        return 1
    return 0


def write_run(directory):
    from mupro_fake import write_domain_run
    write_domain_run(Path(directory), grid=(16, 12, 10), steps=2, interval=1)
    return 0


def private_file(path, text):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(text)


def loopback_runtime(workdir):
    """A Runtime on 127.0.0.1 (ephemeral port): (client, supervisor, server, config, thread)."""
    from suan.runtime.client import RuntimeClient
    from suan.runtime.common import init_config
    from suan.runtime.server import RuntimeHTTPServer
    from suan.runtime.supervisor import Supervisor

    config = init_config(workdir / "state", workdir / "shared", port=0)
    config["scheduler_interval"] = 0
    server = RuntimeHTTPServer(config)  # binds 127.0.0.1 (the Runtime refuses anything else)
    assert server.server_address[0] == "127.0.0.1", server.server_address
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
    thread.start()
    client = RuntimeClient(f"http://127.0.0.1:{server.server_port}", config["token"])
    return client, Supervisor(config), server, config, thread


def stop_runtime(client, supervisor, server, thread):
    """Cancels unfinished tasks, lets the supervisor settle them, stops the server."""
    for record in client.tasks():
        if record["state"] not in {"succeeded", "failed", "cancelled"}:
            client.cancel(record["id"])
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        supervisor.tick()
        if all(t["state"] in {"succeeded", "failed", "cancelled", "unknown"} for t in client.tasks()):
            break
        time.sleep(0.1)
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)
    return not thread.is_alive()


def runtime(workdir):
    workdir = Path(workdir)
    client, supervisor, server, config, thread = loopback_runtime(workdir)
    url = f"http://127.0.0.1:{server.server_port}"
    token_file = workdir / "token"
    private_file(token_file, config["token"])
    workspace = client.create_workspace("桥接测试")["id"]
    gate = workdir / "go"
    task = client.submit({"workspace_id": workspace, "argv": ["{python}", "-c", log_program(gate)], "name": "日志"},
                         idempotency_key="stk-bridge-logs")
    stop = threading.Event()

    def tick():
        while not stop.is_set():
            try:
                supervisor.tick()
            except Exception as exc:  # keep ticking; report on stderr
                print(f"supervisor tick: {exc}", file=sys.stderr)
            stop.wait(0.05)
    ticker = threading.Thread(target=tick, daemon=True)
    ticker.start()
    print(json.dumps({"url": url, "token_file": str(token_file), "task_id": task["id"], "workspace_id": workspace,
                      "gate": str(gate), "expected_stdout": expected_stdout()}, ensure_ascii=False), flush=True)
    try:
        sys.stdin.read()  # until the test closes our stdin (or dies)
    finally:
        stop.set()
        ticker.join(timeout=5)
        stop_runtime(client, supervisor, server, thread)
    return 0


def wait_for(predicate, timeout, what):
    """Polls ``predicate`` until it returns something true; returns that value."""
    deadline = time.monotonic() + timeout
    while not (value := predicate()):
        if time.monotonic() >= deadline:
            raise TimeoutError(what)
        time.sleep(0.05)
    return value


PROXY_VARIABLES = {"http_proxy", "https_proxy", "all_proxy", "ws_proxy", "wss_proxy", "socks_proxy", "ftp_proxy"}
LOOPBACK = "127.0.0.1,localhost,::1"


def loopback_only():
    """Keeps this process's own HTTP traffic on loopback; returns the names (never values) dropped."""
    cleared = sorted(name for name in os.environ if name.lower() in PROXY_VARIABLES)
    for name in cleared:
        del os.environ[name]
    os.environ["NO_PROXY"] = os.environ["no_proxy"] = LOOPBACK
    return cleared


def stop_agent(live):
    """Stops LiveHub's node agent; a no-op when it already stopped (its loop is then closed)."""
    thread = live.agent_thread
    if thread.is_alive():
        # A just-restarted agent may still be creating its loop and run task.
        wait_for(lambda: not thread.is_alive() or (live.agent_loop is not None and live.agent_loop.is_running()),
                 10, "the node agent loop to run")
        if thread.is_alive():
            try:
                live.agent_loop.call_soon_threadsafe(live.agent_task.cancel)
            except RuntimeError:
                if not live.agent_loop.is_closed():
                    raise  # closed means it finished meanwhile
        thread.join(timeout=10)
    if thread.is_alive():
        raise RuntimeError("the node agent did not stop")


def close_hub(live, problems):
    """LiveHub.close, safe when the agent is already offline; every step runs, failures go to ``problems``."""
    def attempt(step):
        try:
            step()
        except Exception as exc:
            problems.append(f"{type(exc).__name__}: {exc}")
    live.stop.set()
    attempt(lambda: stop_agent(live))
    attempt(lambda: live.ticker.join(timeout=10))
    attempt(live.http.close)
    live.server.should_exit = True
    attempt(lambda: live.thread.join(timeout=10))
    return {"agent": not live.agent_thread.is_alive(), "supervisor": not live.ticker.is_alive(),
            "hub": not live.thread.is_alive()}


def hub(workdir):
    """The loopback Hub chain for the native exact task.get test (see the module docstring)."""
    cleared = loopback_only()  # before any client exists
    from test_hub_desktop_bridge import LiveHub

    workdir = Path(workdir)
    client, supervisor, server, config, thread = loopback_runtime(workdir)
    problems, stopped = [], {}
    try:
        live = LiveHub((client, supervisor, server, config), workdir)
        try:
            serve_hub(live, client, workdir, cleared)
        finally:
            stopped.update(close_hub(live, problems))
            vars(client).pop("tasks", None)  # undo window: the teardown sees the Runtime's own tasks
    finally:
        try:
            stopped["runtime"] = stop_runtime(client, supervisor, server, thread)
        except Exception as exc:
            problems.append(f"{type(exc).__name__}: {exc}")
            stopped["runtime"] = not thread.is_alive()
        if problems or not all(stopped.values()):
            print(json.dumps({"cleanup_failed": problems, "stopped": stopped}), file=sys.stderr, flush=True)
    if problems or not all(stopped.values()):
        return 1
    print(json.dumps({"closed": True, "stopped": stopped}), flush=True)
    return 0


def serve_hub(live, client, workdir, cleared):
    workspace = client.create_workspace("精确读取")["id"]
    task = client.submit({"workspace_id": workspace, "argv": ["{python}", "-c", "print('old')"]},
                         idempotency_key="stk-bridge-exact")["id"]
    wait_for(lambda: client.task(task)["state"] in {"succeeded", "failed", "cancelled"}, 60, "task finish")
    code_file = workdir / "pair-code"
    private_file(code_file, live.code())  # client role, no desktop profile
    runtime_tasks = live.agent.runtime.tasks  # the real listing, kept while the window is in effect
    missing = "e" * 32  # listed in the window snapshot, absent from the Runtime
    synthetic = {missing} | {f"{index:032x}" for index in range(200)}
    window_on = []

    def device():
        return live.store.device(live.node_id) or {}

    def rows(record):
        return [item["id"] for item in (record.get("snapshot") or {}).get("tasks") or []]

    def in_window(record):
        ids = rows(record)
        return len(ids) == 200 and set(ids) <= synthetic and missing in ids and task not in ids

    def newer(record, mark):
        return (record.get("last_seen") or 0) > mark

    def state(record):
        ids = rows(record)
        return {"node_id": record.get("id"), "online": bool(record.get("online")),
                "last_seen": record.get("last_seen"),
                "features": sorted((record.get("snapshot") or {}).get("features") or []),
                "snapshot_tasks": len(ids), "synthetic_rows": sum(i in synthetic for i in ids),
                "other_rows": [i for i in ids if i not in synthetic],
                "task_in_snapshot": task in ids, "missing_in_snapshot": missing in ids,
                "actions": [a["id"] for a in live.actions()],
                "action_events": sum(e["kind"] == "actions.changed" for e in live.store.events()),
                "runtime_tasks": sorted(t["id"] for t in runtime_tasks()),
                "task_state": client.task(task)["state"]}

    def window():
        mark = device().get("last_seen") or 0
        historic = runtime_tasks()[0]
        # Every later heartbeat (also after a reconnect) lists these synthetic DTOs first. A heartbeat
        # computed before this line is sent before any computed after it (one sender, in order).
        live.agent.runtime.tasks = lambda: [{**historic, "id": identity} for identity in
                                            [missing, *sorted(synthetic - {missing})]] + runtime_tasks()
        window_on.append(True)
        return wait_for(lambda: (r := device()) and newer(r, mark) and in_window(r) and r, 30,
                        "the next real heartbeat with the window")

    def offline():
        stop_agent(live)
        return wait_for(lambda: (r := device()) and not r.get("online") and r, 30, "hub sees the node offline")

    def online():
        mark = time.time()
        live.agent_thread = threading.Thread(target=live._run_agent, daemon=True)
        live.agent_thread.start()
        return wait_for(lambda: (r := device()) and r.get("online") and newer(r, mark) and {"read", "task.get"} <= set(
            (r.get("snapshot") or {}).get("features") or []) and (not window_on or in_window(r)) and r, 30,
            "the first heartbeat after the reconnect")

    # Start from a heartbeat that already lists the finished task (the agent pulses every 3 s).
    wait_for(lambda: any(t["id"] == task and t["state"] == client.task(task)["state"]
                         for t in (device().get("snapshot") or {}).get("tasks") or []), 30, "task in heartbeat")
    commands = {"state": device, "window": window, "offline": offline, "online": online}
    print(json.dumps({"url": live.url, "node_id": live.node_id, "task_id": task, "workspace_id": workspace,
                      "code_file": str(code_file), "missing_id": missing, "proxy_env_cleared": cleared},
                     ensure_ascii=False), flush=True)
    for line in sys.stdin:  # until the test closes our stdin (or dies)
        command = line.strip()
        try:
            reply = {"ok": True, "command": command, **state(commands[command]())}
        except Exception as exc:  # the test fails on ok=false with the reason
            reply = {"ok": False, "command": command, "error": f"{type(exc).__name__}: {exc}"}
        print(json.dumps(reply, ensure_ascii=False), flush=True)


def main(argv):
    if len(argv) in (2, 3) and argv[1] == "check" and (len(argv) == 2 or argv[2] in CHECKS):
        return check(argv[2] if len(argv) == 3 else "bridge")
    if len(argv) == 3 and argv[1] == "write-run":
        return write_run(argv[2])
    if len(argv) == 3 and argv[1] == "runtime":
        return runtime(argv[2])
    if len(argv) == 3 and argv[1] == "hub":
        return hub(argv[2])
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
