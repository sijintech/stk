# SPDX-License-Identifier: GPL-2.0-or-later
"""A loopback STK Runtime for the Jobs editor's integration test (desktop/tests/app).

    jobs_fixture.py check                exit 0 when the bridge and the Runtime can run here (else prints why)
    jobs_fixture.py case DIR             writes an input folder (input.json, job.py, sub/notes.txt) into DIR
    jobs_fixture.py runtime WORKDIR      starts a Runtime on 127.0.0.1 (ephemeral port) with its supervisor
                                         ticking; prints one JSON line {url, token_file} and then answers
                                         commands on stdin, one JSON line each:
                                           task <id>            the task record
                                           wait <id> <seconds>  the record once the task finished (or timed out)
                                         At stdin EOF it cancels unfinished tasks and stops.

The token is written to WORKDIR/token (mode 0600) and never printed. Nothing listens beyond 127.0.0.1.
"""
import json
import os
from pathlib import Path
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

TERMINAL = {"succeeded", "failed", "cancelled"}

JOB = r'''
import json, struct, sys, time, zlib
pause = float(sys.argv[1]) if len(sys.argv) > 1 else 0.0
cfg = json.load(open("case/input.json", encoding="utf-8"))
for i in range(5):
    print(f"第{i}步 能量 {cfg['e0'] * (i + 1):.4g}", flush=True)
    time.sleep(0.05)
print("警告：这是测试", file=sys.stderr, flush=True)
w, h = 32, 16
raw = b"".join(b"\x00" + bytes(v for x in range(w) for v in (x * 8 % 256, y * 16 % 256, 128, 255)) for y in range(h))
def chunk(tag, data):
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)) + \
      chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")
open("result.png", "wb").write(png)
time.sleep(pause)
print("结束", flush=True)
'''


def check():
    try:
        import suan.desktop_bridge.server  # noqa: F401
        import suan.runtime.server  # noqa: F401
        import suan.runtime.supervisor  # noqa: F401
    except Exception as exc:  # pragma: no cover - diagnostic path
        print(f"cannot import the bridge or the Runtime: {type(exc).__name__}: {exc}")
        return 1
    if not sys.platform.startswith("linux"):
        print("the STK Runtime is Linux-only")
        return 1
    return 0


def case(directory):
    d = Path(directory)
    (d / "sub").mkdir(parents=True, exist_ok=True)
    (d / "input.json").write_text(json.dumps({"e0": -1.5e-3, "名称": "铁电畴"}, ensure_ascii=False), encoding="utf-8")
    (d / "job.py").write_text(JOB, encoding="utf-8")
    (d / "sub" / "notes.txt").write_text("乙\n", encoding="utf-8")
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
    print(json.dumps({"url": url, "token_file": str(token_file)}), flush=True)
    try:
        for line in sys.stdin:
            words = line.split()
            if not words:
                continue
            try:
                if words[0] == "task":
                    record = client.task(words[1])
                elif words[0] == "wait":
                    deadline = time.monotonic() + float(words[2])
                    record = client.task(words[1])
                    while record["state"] not in TERMINAL and time.monotonic() < deadline:
                        time.sleep(0.1)
                        record = client.task(words[1])
                else:
                    record = {"error": f"unknown command {words[0]}"}
            except Exception as exc:
                record = {"error": f"{type(exc).__name__}: {exc}"}
            print(json.dumps(record, ensure_ascii=False), flush=True)
    finally:
        stop.set()
        ticker.join(timeout=5)
        for record in client.tasks():
            if record["state"] not in TERMINAL:
                client.cancel(record["id"])
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            supervisor.tick()
            if all(t["state"] in TERMINAL | {"unknown"} for t in client.tasks()):
                break
            time.sleep(0.1)
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    return 0


def main(argv):
    if len(argv) == 2 and argv[1] == "check":
        return check()
    if len(argv) == 3 and argv[1] == "case":
        return case(argv[2])
    if len(argv) == 3 and argv[1] == "runtime":
        return runtime(argv[2])
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
