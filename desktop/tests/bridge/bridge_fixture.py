# SPDX-License-Identifier: GPL-2.0-or-later
"""Fixtures for the stk_bridge integration tests (desktop/tests/bridge), run with the repo's Python.

    bridge_fixture.py check [bridge|graph|runtime]
                                             exit 0 when that part can run here (else prints why)
    bridge_fixture.py write-run DIR          a fake muFerro run (tests/mupro_fake.write_domain_run)
    bridge_fixture.py runtime WORKDIR        a loopback Runtime (127.0.0.1, ephemeral port) running one
                                             task that, once the file `gate` exists, writes UTF-8 log
                                             lines slowly (so a test can subscribe first); prints one JSON
                                             line {url, token_file, task_id, gate, expected_stdout}, and serves
                                             until stdin reaches EOF, then cancels its tasks and stops.

The token never appears on stdout: it goes to WORKDIR/token (mode 0600) for connections.add_runtime
token_file. Nothing listens beyond 127.0.0.1.
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
}


def check(what="bridge"):
    import importlib
    for module in CHECKS[what]:
        try:
            importlib.import_module(module)
        except Exception as exc:  # pragma: no cover - diagnostic path
            print(f"{module} does not import: {type(exc).__name__}: {exc}")
            return 1
    if what == "runtime" and not sys.platform.startswith("linux"):
        print("the STK Runtime is Linux-only")
        return 1
    return 0


def write_run(directory):
    from mupro_fake import write_domain_run
    write_domain_run(Path(directory), grid=(16, 12, 10), steps=2, interval=1)
    return 0


def runtime(workdir):
    from suan.runtime.client import RuntimeClient
    from suan.runtime.common import init_config
    from suan.runtime.server import RuntimeHTTPServer
    from suan.runtime.supervisor import Supervisor

    workdir = Path(workdir)
    config = init_config(workdir / "state", workdir / "shared", port=0)
    config["scheduler_interval"] = 0
    server = RuntimeHTTPServer(config)  # binds 127.0.0.1 (the Runtime refuses anything else)
    assert server.server_address[0] == "127.0.0.1", server.server_address
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}"
    client = RuntimeClient(url, config["token"])
    supervisor = Supervisor(config)
    token_file = workdir / "token"
    fd = os.open(token_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(config["token"])
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
    return 0


def main(argv):
    if len(argv) in (2, 3) and argv[1] == "check" and (len(argv) == 2 or argv[2] in CHECKS):
        return check(argv[2] if len(argv) == 3 else "bridge")
    if len(argv) == 3 and argv[1] == "write-run":
        return write_run(argv[2])
    if len(argv) == 3 and argv[1] == "runtime":
        return runtime(argv[2])
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
