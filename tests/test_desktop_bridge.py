"""Desktop bridge (suan.desktop_bridge): protocol hygiene, schema, probe port, UTF-8 logs, local graphs.

Also hosts the harnesses the other ``test_desktop_bridge_*`` modules use: :class:`InProcessBridge`
(a :class:`suan.desktop_bridge.server.Bridge` writing into memory) and :class:`ProcessBridge`
(``python -m suan.desktop_bridge --stdio`` as a child process). Both validate every message they
see against ``desktop-bridge-1.schema.json`` and check that each stdout line is one strict JSON
message.
"""
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time

import pytest

from suan.desktop_bridge import schema as bridge_schema
from suan.desktop_bridge.protocol import ERROR_CODES, LineReader, decode_line
from suan.desktop_bridge.server import Bridge
from suan.desktop_bridge.subscriptions import LogDecoder

ROOT = Path(__file__).resolve().parents[1]
TIMEOUT = 60


class BridgeCallError(Exception):
    def __init__(self, error):
        super().__init__(f"{error['code']}: {error['message']}")
        self.error = error
        self.code = error["code"]


def _jsonschema_errors():
    """A second opinion from ``jsonschema`` (Draft 2020-12) when it is installed; else ``None``."""
    try:
        import jsonschema
        import referencing
    except ImportError:
        return None
    from suan.contracts import load_all_schemas
    registry = referencing.Registry().with_resources(
        [(urn, referencing.Resource.from_contents(schema)) for urn, schema in load_all_schemas().items()])
    cache = {}

    def errors(pointer, document):
        if pointer not in cache:
            cache[pointer] = jsonschema.Draft202012Validator({"$ref": "urn:stk:schema:desktop-bridge-1" + pointer},
                                                             registry=registry)
        return [f"{'/'.join(map(str, e.absolute_path))}: {e.message}" for e in cache[pointer].iter_errors(document)]
    return errors


JSONSCHEMA = _jsonschema_errors()


def second_opinion(message, method=None):
    if JSONSCHEMA is None:
        return []
    found = JSONSCHEMA("#", message)
    if "event" in message and not found:
        found = JSONSCHEMA(f"#/$defs/events/{message['event']}", message["data"])
    elif "result" in message and method and not found:
        found = JSONSCHEMA(f"#/$defs/methods/{method}/result", message["result"])
    elif "method" in message and not found:
        found = JSONSCHEMA(f"#/$defs/methods/{message['method']}/params", message.get("params", {}))
    return found


def _strict(raw):
    """One protocol line: UTF-8, strict JSON (no NaN, no duplicate keys), exactly one trailing newline."""
    assert raw.endswith(b"\n") and raw.count(b"\n") == 1, raw[:200]
    return decode_line(raw)


class _Harness:
    """Request/response bookkeeping and schema checks shared by both harnesses."""

    def __init__(self):
        self.cond = threading.Condition()
        self.responses = {}
        self.events = []
        self.lines = []
        self.methods = {}
        self.violations = []
        self.next_id = 0

    def receive(self, raw):
        message = _strict(raw)
        with self.cond:
            self.lines.append(raw)
            method = None if "event" in message else self.methods.get(message.get("id"))
            issues = bridge_schema.validate_outgoing(message, method) + second_opinion(message, method)
            if "event" in message:
                self.events.append(message)
            else:
                self.responses.setdefault(message.get("id"), []).append(message)
            if issues:
                self.violations.append((message.get("event") or self.methods.get(message.get("id")), issues))
            self.cond.notify_all()

    def request(self, method, params=None, *, check=True):
        with self.cond:
            self.next_id += 1
            identity = self.next_id
            self.methods[identity] = method
        message = {"id": identity, "method": method, "params": params or {}}
        if check:
            issues = bridge_schema.validate_incoming(message) + second_opinion(message)
            assert issues == [], issues
        self.send_line(json.dumps(message, ensure_ascii=False).encode("utf-8") + b"\n")
        return identity

    def response(self, identity, timeout=TIMEOUT):
        deadline = time.monotonic() + timeout
        with self.cond:
            while identity not in self.responses:
                remaining = deadline - time.monotonic()
                assert remaining > 0, f"no response to request {identity} ({self.methods.get(identity)})"
                self.cond.wait(remaining)
            return self.responses[identity][0]

    def call(self, method, params=None, timeout=TIMEOUT, *, check=True):
        message = self.response(self.request(method, params, check=check), timeout)
        if "error" in message:
            raise BridgeCallError(message["error"])
        return message["result"]

    def error(self, method, params=None, timeout=TIMEOUT):
        """The error of a request that must fail (sent even when it violates the schema)."""
        with pytest.raises(BridgeCallError) as info:
            self.call(method, params, timeout, check=False)
        return info.value.error

    def wait_event(self, predicate, timeout=TIMEOUT, start=0):
        deadline = time.monotonic() + timeout
        with self.cond:
            while True:
                for event in self.events[start:]:
                    if predicate(event):
                        return event
                remaining = deadline - time.monotonic()
                assert remaining > 0, f"event not seen; last events: {[e['event'] for e in self.events[-10:]]}"
                self.cond.wait(min(remaining, 0.5))

    def events_of(self, name, sub=None):
        with self.cond:
            return [e["data"] for e in self.events if e["event"] == name
                    and (sub is None or e["data"].get("sub") == sub)]

    def mark(self):
        """The current event count: ``wait_event(..., start=mark)`` ignores earlier events."""
        with self.cond:
            return len(self.events)

    def wait_transfer(self, transfer_id, states=("completed", "failed", "cancelled"), timeout=TIMEOUT, start=0):
        def match(event):
            transfer = event["data"].get("transfer") if event["event"] == "transfer.updated" else None
            return transfer is not None and transfer["id"] == transfer_id and transfer["state"] in states
        return self.wait_event(match, timeout, start)["data"]["transfer"]

    def output_text(self):
        with self.cond:
            return b"".join(self.lines).decode("utf-8")

    def assert_clean(self):
        assert self.violations == []


class InProcessBridge(_Harness):
    class _Writer:
        def __init__(self, harness):
            self.harness = harness

        def write(self, data):
            self.harness.receive(bytes(data))

        def flush(self):
            pass

    def __init__(self, state_dir, cache_dir=None, **options):
        super().__init__()
        self.bridge = Bridge(state_dir, cache_dir, writer=self._Writer(self), strict=True, **options)

    def send_line(self, raw):
        self.bridge.handle_line(raw)

    def close(self):
        self.bridge.shutdown()
        self.assert_clean()


class ProcessBridge(_Harness):
    def __init__(self, state_dir, *, argv=None, env=None, stderr_path=None):
        super().__init__()
        env = dict(os.environ if env is None else env)
        env["PYTHONPATH"] = os.pathsep.join([str(ROOT), *filter(None, [env.get("PYTHONPATH")])])
        env.pop("STK_RUNTIME_URL", None)
        env.pop("STK_RUNTIME_TOKEN", None)
        self.stderr_path = Path(stderr_path or Path(state_dir).parent / f"bridge-{os.getpid()}-{time.time_ns()}.err")
        self.stderr = open(self.stderr_path, "wb")
        command = argv or [sys.executable, "-m", "suan.desktop_bridge", "--stdio", "--strict",
                           "--state-dir", str(state_dir)]
        self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.stderr,
                                        env=env, cwd=str(ROOT))
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self):
        for raw in self.process.stdout:
            self.receive(raw)

    def send_line(self, raw):
        self.process.stdin.write(raw)
        self.process.stdin.flush()

    def close(self, timeout=30):
        """EOF on stdin: the bridge shuts down gracefully and exits 0."""
        try:
            self.process.stdin.close()
        except OSError:
            pass
        code = self.process.wait(timeout=timeout)
        self.reader.join(timeout=5)
        self.stderr.close()
        self.assert_clean()
        return code

    def kill(self):
        self.process.kill()
        self.process.wait(timeout=30)
        self.reader.join(timeout=5)
        self.stderr.close()

    def stderr_text(self):
        return self.stderr_path.read_text(encoding="utf-8", errors="replace")


@pytest.fixture
def bridge_env(tmp_path, monkeypatch):
    """Private Runtime profile file and (absent) local Runtime for every bridge in the test."""
    monkeypatch.setenv("STK_PROFILES_FILE", str(tmp_path / "profiles" / "connections.json"))
    monkeypatch.setenv("STK_STATE_DIR", str(tmp_path / "no-local-runtime"))
    monkeypatch.delenv("STK_RUNTIME_URL", raising=False)
    monkeypatch.delenv("STK_RUNTIME_TOKEN", raising=False)
    return tmp_path


@pytest.fixture
def inproc(bridge_env):
    harnesses = []

    def make(state="bridge", **options):
        harness = InProcessBridge(bridge_env / state, **options)
        harnesses.append(harness)
        return harness
    yield make
    for harness in harnesses:
        harness.bridge.shutdown()


# ---------------------------------------------------------------------------
# Schema and packaging


def test_schema_describes_every_method_and_event():
    from suan.contracts import SCHEMA_IDS, load_schema
    assert "desktop-bridge-1" in SCHEMA_IDS
    document = load_schema("desktop-bridge-1")
    methods = document["$defs"]["methods"]
    assert len(methods) >= 40
    for name, spec in methods.items():
        assert spec["description"] and set(spec) == {"description", "params", "result"}, name
        assert spec["params"].get("additionalProperties") is False, name
    assert set(document["$defs"]["error"]["properties"]["code"]["enum"]) == set(ERROR_CODES)
    # Every keyword the schema uses is in the subset suan.graph.schema.check_value (and stk_io) implement.
    allowed = {"$schema", "$id", "$defs", "$ref", "title", "description", "type", "enum", "const", "minimum",
               "maximum", "minLength", "maxLength", "pattern", "items", "minItems", "maxItems", "properties",
               "required", "additionalProperties", "patternProperties", "maxProperties", "anyOf", "oneOf", "allOf"}

    def walk(node, where):
        if isinstance(node, dict):
            for key, value in node.items():
                if where.endswith(("/properties", "/patternProperties", "/$defs", "/methods", "/events")) or (
                        re.fullmatch(r"/\$defs/methods/[^/]+", where) and key in ("params", "result")):
                    walk(value, f"{where}/{key}")
                    continue
                assert key in allowed, f"{where}: keyword {key}"
                walk(value, f"{where}/{key}")
        elif isinstance(node, list):
            for index, item in enumerate(node):
                walk(item, f"{where}/{index}")
    walk(document, "")


def test_schema_is_valid_draft_2020_12_and_agrees_with_the_subset_validator():
    jsonschema = pytest.importorskip("jsonschema")
    from suan.contracts import load_schema
    jsonschema.Draft202012Validator.check_schema(load_schema("desktop-bridge-1"))
    good = [{"id": 1, "method": "hello", "params": {"protocol": 1}},
            {"id": "x", "method": "task.get", "params": {"connection": "local", "task_id": "a" * 32}},
            {"id": 1, "result": {}}, {"id": None, "error": {"code": "parse_error", "message": "m", "retryable": False}},
            {"event": "logs.end", "data": {"sub": "a" * 32, "offsets": {}}}]
    bad = [{"id": True, "method": "hello"}, {"id": 1}, {"id": 1, "result": {}, "error": {}},
           {"id": 1, "method": "hello", "params": {"protocol": 1, "x": 1}},
           {"id": 1, "method": "task.get", "params": {"connection": "elsewhere", "task_id": "t"}},
           {"id": None, "error": {"code": "no_such_code", "message": "m", "retryable": False}}]
    for message in good:
        assert bridge_schema.validate_incoming(message) == [] or "method" not in message
        assert second_opinion(message) == [], message
    for message in bad:
        subset = (bridge_schema.validate_incoming(message) if "method" in message
                  else bridge_schema.validate_outgoing(message))
        assert subset and second_opinion(message), message


def test_pyproject_excludes_desktop_from_the_wheel():
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    exclude = re.search(r"^exclude = \[(.*?)\]", text, re.M | re.S)
    assert exclude and '"desktop/**"' in exclude.group(1)


def test_the_bridge_starts_without_numpy():
    """Start-up and protocol handling import only the standard-library core (fast spawn, small installs)."""
    code = ("import sys, suan.desktop_bridge.server, suan.desktop_bridge.__main__; "
            "heavy = {'numpy', 'vtk', 'matplotlib', 'PySide6'} & set(sys.modules); assert not heavy, heavy")
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(ROOT), *filter(None, [os.environ.get("PYTHONPATH")])]))
    subprocess.run([sys.executable, "-c", code], check=True, env=env, cwd=str(ROOT))


def test_nothing_under_suan_references_desktop():
    """The MIT Python core never refers to the GPL desktop tree (desktop/)."""
    pattern = re.compile(rb"(?<![A-Za-z0-9_.-])desktop/")
    offenders = []
    for path in (ROOT / "suan").rglob("*"):
        if path.is_file() and "__pycache__" not in path.parts and pattern.search(path.read_bytes()):
            offenders.append(path.relative_to(ROOT).as_posix())
    assert offenders == []


# ---------------------------------------------------------------------------
# Framing


def test_line_reader_bounds_lines_and_keeps_going():
    stream = io.BytesIO(b'{"a":1}\n' + b"x" * 50 + b"\n" + b'{"b":2}\n' + b'{"c":3}')
    reader = LineReader(stream, max_bytes=20)
    assert reader.next() == (b'{"a":1}\n', None)
    line, error = reader.next()
    assert line is None and error.code == "line_too_long"
    assert reader.next() == (b'{"b":2}\n', None)
    assert reader.next() == (b'{"c":3}', None)  # a last line without a newline still counts
    assert reader.next() == (None, None)


@pytest.mark.parametrize("raw, message", [
    (b"not json\n", "strict JSON"),
    (b"\xff\xfe{}\n", "UTF-8"),
    (b'{"id": 1, "method": "hello", "params": {"protocol": NaN}}\n', "strict JSON"),
    (b'{"id": 1, "id": 2, "method": "hello"}\n', "duplicate"),
])
def test_decode_line_is_strict(raw, message):
    from suan.desktop_bridge.protocol import BridgeError
    with pytest.raises(BridgeError, match=message) as info:
        decode_line(raw)
    assert info.value.code == "parse_error"


def test_malformed_requests_get_stable_errors(inproc):
    harness = inproc()
    cases = [
        (b"garbage\n", None, "parse_error"),
        (b"[1, 2]\n", None, "invalid_request"),
        (b'{"method": "hello"}\n', None, "invalid_request"),
        (b'{"id": true, "method": "hello"}\n', None, "invalid_request"),
        (b'{"id": "a", "method": 5}\n', "a", "invalid_request"),
        (b'{"id": "b", "method": "hello", "params": []}\n', "b", "invalid_request"),
        (b'{"id": "c", "method": "hello", "extra": 1}\n', "c", "invalid_request"),
        (b'{"id": "d", "method": "no.such.method"}\n', "d", "unknown_method"),
        (b'{"id": "e", "method": "hello", "params": {"protocol": "one"}}\n', "e", "invalid_params"),
        (b'{"id": "f", "method": "hello", "params": {"protocol": 1, "surprise": true}}\n', "f", "invalid_params"),
        (b'{"id": "g", "method": "hello", "params": {"protocol": 2}}\n', "g", "unsupported"),
        (b'{"id": "h", "method": "task.get", "params": {"connection": "runtime:nowhere", "task_id": "x"}}\n', "h",
         "not_found"),
    ]
    for raw, identity, code in cases:
        before = len(harness.lines)
        harness.send_line(raw)
        deadline = time.monotonic() + 10
        while len(harness.lines) == before:
            assert time.monotonic() < deadline, raw
            time.sleep(0.01)
        message = _strict(harness.lines[before])
        assert message["id"] == identity and message["error"]["code"] == code, (raw, message)
        assert message["error"]["retryable"] is False and message["error"]["message"]
    harness.send_line(b"   \n")  # blank lines are ignored
    assert harness.call("hello", {"protocol": 1})["protocol"] == 1
    harness.close()


def test_serve_handles_oversized_lines_and_eof(bridge_env):
    output = io.BytesIO()
    lines = [b'{"id": 1, "method": "hello", "params": {"protocol": 1}}\n',
             b'{"id": 2, "pad": "' + b"x" * 10000 + b'"}\n', b'{"id": 3, "method": "connections.list"}\n']
    bridge = Bridge(bridge_env / "bridge", writer=output, strict=True, max_line=4096)
    bridge.serve(io.BytesIO(b"".join(lines)))  # EOF: returns after a graceful shutdown
    assert bridge.closed.is_set()
    deadline = time.monotonic() + 10
    while output.getvalue().count(b"\n") < 3:
        assert time.monotonic() < deadline
        time.sleep(0.01)
    messages = [_strict(line + b"\n") for line in output.getvalue().splitlines()]
    assert {m["id"] for m in messages if "result" in m} == {1, 3}
    assert [m["error"]["code"] for m in messages if "error" in m] == ["line_too_long"]


NOISY = r"""
import logging, os, subprocess, sys
from suan.desktop_bridge import server
original = server.Bridge.hello
def hello(self, params, context):
    print("stray print from a library")
    sys.stdout.write("stray sys.stdout write\n")
    os.write(1, b"raw write to file descriptor 1\n")
    subprocess.run([sys.executable, "-c", "print('child process output')"], check=True)
    # a child process must not see (or steal) protocol input: its stdin is the null device
    subprocess.run([sys.executable, "-c", "import sys; assert sys.stdin.buffer.read() == b''"], check=True)
    logging.getLogger("noisy").warning("a warning through logging")
    return original(self, params, context)
server.Bridge.hello = hello
from suan.desktop_bridge.__main__ import main
main(["--stdio", "--strict", "--state-dir", sys.argv[1]])
"""


def test_stdout_carries_only_ndjson_in_a_child_process(bridge_env):
    """Stray output of the bridge, libraries and child processes goes to stderr; EOF exits cleanly."""
    harness = ProcessBridge(bridge_env / "bridge", argv=[sys.executable, "-c", NOISY, str(bridge_env / "bridge")])
    hello = harness.call("hello", {"protocol": 1, "client": {"name": "pytest", "version": "1"}})
    assert hello["protocol"] == 1 and "graph.evaluate" in hello["methods"] and "logs.chunk" in hello["events"]
    assert hello["limits"]["max_line_bytes"] == 16 * 1024 * 1024
    assert harness.error("no.such.method")["code"] == "unknown_method"
    harness.send_line(b"{broken\n")
    harness.send_line('{"id": "中文", "method": "colormaps.list"}\n'.encode("utf-8"))
    assert harness.response("中文")["result"]["colormaps"][0]["name"] == "viridis"
    started = time.monotonic()
    assert harness.close() == 0
    assert time.monotonic() - started < 20
    for raw in harness.lines:  # every stdout line is one protocol message
        message = _strict(raw)
        assert set(message) in ({"id", "result"}, {"id", "error"}, {"event", "data"})
    assert any(json.loads(raw).get("error", {}).get("code") == "parse_error" for raw in harness.lines)
    stderr = harness.stderr_text()
    for noise in ("stray print from a library", "stray sys.stdout write", "raw write to file descriptor 1",
                  "child process output", "a warning through logging"):
        assert noise in stderr
        assert noise not in harness.output_text()


def test_shutdown_method_exits_the_process(bridge_env):
    harness = ProcessBridge(bridge_env / "bridge")
    assert harness.call("shutdown") == {"ok": True}
    assert harness.process.wait(timeout=30) == 0
    harness.close()


# ---------------------------------------------------------------------------
# UTF-8 safe log decoding


def test_log_decoder_joins_characters_split_across_chunks():
    text = "计算完成 ✓ energy=−1.5e-3 🧲 done\n第二行"
    data = text.encode("utf-8")
    for size in range(1, 8):
        decoder, pieces = LogDecoder(), []
        for start in range(0, len(data), size):
            pieces.append(decoder.feed(data[start:start + size]))
            # The decoded offset is always on a character boundary.
            data[:decoder.decoded_offset].decode("utf-8")
        pieces.append(decoder.feed(b"", final=True))
        assert "".join(pieces) == text
        assert decoder.decoded_offset == decoder.read_offset == len(data)
    # A new decoder started at any reported offset continues the text exactly.
    decoder = LogDecoder()
    decoder.feed(data[:5])
    resumed = LogDecoder(decoder.decoded_offset)
    assert data[:decoder.decoded_offset].decode("utf-8") + resumed.feed(data[decoder.decoded_offset:]) == text


def test_log_decoder_replaces_invalid_bytes():
    decoder = LogDecoder()
    assert decoder.feed(b"ok \xff\xfe ") == "ok �� "
    assert decoder.feed(b"\xe8\xae") == ""  # an incomplete character is held back
    assert decoder.decoded_offset == 6
    assert decoder.feed(b"", final=True) == "�"


# ---------------------------------------------------------------------------
# suan.graph.probe (the port of web/src/graph.ts::resolveProbeTarget)


def domains_graph():
    from suan.graph.catalog import load_preset
    return load_preset("muferro-domains")


def test_probe_target_of_a_muferro_frame():
    from suan.graph.probe import frame_dataset, frames_from_artifacts, resolve_probe_target
    graph = domains_graph()
    task = "a" * 32
    result = {"parameters": {"step": {"value": 200, "choices": [0, 100, 200]}}}
    target = resolve_probe_target(graph, {"node": "surface_layer", "dataset": "Polar"}, bindings={"run": task},
                                  values={"step": "latest"}, result=result)
    assert target == {"binding": "run", "task_id": task, "path": "Polar.00000200.dat", "node": "polar"}
    # The published artifact wins (its case directory), a digit string step works without a result.
    artifacts = [{"path": "case/Polar.00000100.dat"}, {"path": "case/Polar.00000200.dat"},
                 {"path": "case/Strain.00000100.dat"}]
    target = resolve_probe_target(graph, {"node": "polar"}, bindings={"run": task}, values={"step": "100"},
                                  artifacts=artifacts)
    assert target["path"] == "case/Polar.00000100.dat"
    assert frame_dataset(graph) == "Polar" and frames_from_artifacts(artifacts, "Polar") == [100, 200]
    # An explicit case_dir names the directory when nothing was published.
    graph["nodes"][0]["params"]["case_dir"] = "runs/a/"
    target = resolve_probe_target(graph, {"node": "polar"}, bindings={"run": task}, values={"step": 7})
    assert target["path"] == "runs/a/Polar.00000007.dat"


def test_probe_target_of_a_file_source_and_errors():
    from suan.graph.probe import resolve_probe_target
    source = {"binding": "data", "path": "f.vti", "origin": {"$param": "o"}, "spacing": [0.5, 0.5, 0.5]}
    graph = {"schema": "stk.graph/1", "parameters": [{"name": "o", "type": "vector3", "default": [1, 2, 3]}],
             "nodes": [{"id": "src", "type": "stk.source.file@1", "params": source},
                       {"id": "slice", "type": "stk.filter.slice@1", "inputs": {"in": {"from": "src.out"}}},
                       {"id": "layer", "type": "stk.render.slice@1", "inputs": {"in": [{"from": "slice.out"}]}}]}
    target = resolve_probe_target(graph, {"node": "layer"}, bindings={"data": "t1"})
    assert target == {"binding": "data", "task_id": "t1", "path": "f.vti", "node": "src",
                      "metadata": {"origin": [1, 2, 3], "spacing": [0.5, 0.5, 0.5]}}
    assert resolve_probe_target(graph, {"node": "layer"}, bindings={})["error"] == "数据源 data 尚未绑定任务"
    assert "pick.probe" in resolve_probe_target(graph, {}, bindings={})["error"]
    assert "图定义" in resolve_probe_target(None, {"node": "x"}, bindings={})["error"]
    assert "向上未找到" in resolve_probe_target(graph, {"node": "nowhere"}, bindings={})["error"]
    graph["nodes"][0]["params"]["path"] = ""
    assert "缺少文件路径" in resolve_probe_target(graph, {"node": "layer"}, bindings={"data": "t"})["error"]
    frames = domains_graph()
    latest = resolve_probe_target(frames, {"node": "polar"}, bindings={"run": "t"}, values={"step": "latest"})
    assert "时间步" in latest["error"]
    assert resolve_probe_target(frames, {"node": "polar"}, bindings={}, values={"step": 1})["error"] == \
        "数据源 run 尚未绑定任务"


# ---------------------------------------------------------------------------
# Graph methods, colormaps, blobs and probes without a Runtime


def test_catalog_presets_validate_and_colormaps(inproc):
    import base64
    harness = inproc()
    catalog = harness.call("graph.catalog")["catalog"]
    assert any(n["id"] == "stk.source.muferro_run@1" for n in catalog["nodes"])
    presets = harness.call("graph.presets")["presets"]
    assert "muferro-domains" in [p["id"] for p in presets]
    graph = domains_graph()
    assert harness.call("graph.validate", {"graph": graph}) == {"ok": True, "issues": []}
    graph["nodes"][0]["type"] = "stk.source.nothing@1"
    checked = harness.call("graph.validate", {"graph": graph})
    assert checked["ok"] is False and checked["issues"][0]["code"] == "unknown_type"
    colormaps = harness.call("colormaps.list")
    names = [c["name"] for c in colormaps["colormaps"]]
    assert names[:2] == ["viridis", "cividis"] and colormaps["aliases"]["grey"] == "gray"
    assert all(len(base64.b64decode(c["lut_rgba8"])) == 1024 for c in colormaps["colormaps"])
    missing = "0" * 64
    assert harness.call("blob.ensure", {"sha256": [missing]})["missing"] == [missing]
    assert harness.call("graph.cancel", {"eval_id": "nothing"}) == {"cancelled": False}
    harness.close()


def test_local_graph_evaluate_on_a_fake_domain_run(inproc, tmp_path):
    """graph.evaluate in local mode over a local directory binding, blobs in the cache, then a probe."""
    np = pytest.importorskip("numpy")
    pytest.importorskip("vtk")
    pytest.importorskip("matplotlib")
    from mupro_fake import write_domain_run
    from suan.render.payload import decode
    frames = write_domain_run(tmp_path / "run", grid=(16, 12, 10), steps=2, interval=1)
    harness = inproc()
    request = {"preset": "muferro-domains", "outputs": ["view", "fractions"], "parameters": {"step": "latest"}}
    params = {"eval_id": "eval-1", "mode": "local", "request": request,
              "local_bindings": {"run": str(tmp_path / "run")}}
    evaluated = harness.call("graph.evaluate", params, timeout=180)
    result = evaluated["result"]
    assert result["schema"] == "stk.graph-result/1" and result["parameters"]["step"]["value"] == 2
    blob_dir = Path(evaluated["blob_dir"])
    manifest = result["outputs"]["view"]["manifest"]
    digests = [b["sha256"] for b in manifest["buffers"]]
    for digest in digests:  # buffers are in the content-addressed cache <blobs>/<aa>/<sha256>
        path = blob_dir / digest[:2] / digest
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
    payload = decode(manifest, lambda digest: (blob_dir / digest[:2] / digest).read_bytes())
    assert payload.manifest["schema"] == "stk.payload/2"
    assert result["outputs"]["fractions"]["type"] == "table"
    progress = harness.events_of("graph.progress")
    assert progress and all(p["eval_id"] == "eval-1" for p in progress)
    assert {"node.started", "node.finished"} <= {p["event"]["type"] for p in progress}
    ensured = harness.call("blob.ensure", {"sha256": digests})
    assert ensured["missing"] == [] and set(ensured["blobs"]) == set(digests)
    # A client-stage change re-runs no data node.
    again = harness.call("graph.evaluate", {**params, "eval_id": "eval-2",
                                            "request": {**request, "parameters": {"step": "latest", "view": "+x"}}})
    assert "polar" not in again["result"]["evaluated"] and "domains" not in again["result"]["evaluated"]
    # Probe the picked surface: the original Polar values at a grid point (grid-index coordinates).
    layer = next(item for item in manifest["layers"] if item["id"] == "surface_layer")
    probe = harness.call("probe", {"preset": "muferro-domains", "pick": layer["pick"]["probe"],
                                   "context": {"values": {"step": "latest"}, "result": result},
                                   "local_bindings": {"run": str(tmp_path / "run")}, "position": [3.0, 4.0, 5.0]})
    assert probe["target"]["path"] == "Polar.00000002.dat" and probe["target"]["node"] == "polar"
    assert "task_id" not in probe["target"]
    assert np.allclose(probe["sample"]["values"], frames[2][3, 4, 5])
    # A graph error keeps its graph code.
    error = harness.error("graph.evaluate", {**params, "eval_id": "eval-3", "request": {"preset": "no-such"}})
    assert error["code"] == "graph_error" and error["data"]["graph_code"] == "unknown_preset"
    error = harness.error("graph.evaluate", {**params, "eval_id": "eval-4",
                                             "request": {**request, "bindings": {"run": {"task_id": "a" * 32}}},
                                             "local_bindings": {}})
    assert error["code"] == "invalid_params"
    harness.close()


def test_credentials_never_reach_the_app(inproc, bridge_env):
    harness = inproc()
    secret = "runtime-secret-token-" + "q" * 20
    added = harness.call("connections.add_runtime", {"name": "cluster", "url": "http://127.0.0.1:9", "token": secret,
                                                     "check": False})
    assert added["connection"] == {"id": "runtime:cluster", "kind": "runtime", "name": "cluster",
                                   "url": "http://127.0.0.1:9"}
    token_file = bridge_env / "token.txt"
    token_file.write_text(secret + "\n", encoding="utf-8", newline="\n")
    harness.call("connections.add_runtime", {"name": "second", "url": "http://localhost:9",
                                             "token_file": str(token_file), "check": False})
    listed = harness.call("connections.list")["connections"]
    assert [c["id"] for c in listed] == ["runtime:cluster", "runtime:second"]
    checked = harness.call("connections.check", {"id": "runtime:cluster"})
    assert checked["ok"] is False and checked["error"]["code"] == "unavailable"
    error = harness.error("connections.add_runtime", {"name": "remote", "url": "http://example.com:1", "token": secret})
    assert error["code"] == "invalid_params"
    error = harness.error("connections.add_runtime", {"name": "bad name!", "url": "http://127.0.0.1:1", "token": "x"})
    assert error["code"] == "invalid_params"
    assert harness.call("connections.remove", {"id": "runtime:second"}) == {"removed": "runtime:second"}
    assert harness.error("connections.remove", {"id": "runtime:second"})["code"] == "not_found"
    assert secret not in harness.output_text()
    profiles = Path(os.environ["STK_PROFILES_FILE"])
    assert json.loads(profiles.read_text(encoding="utf-8"))["cluster"]["token"] == secret
    if os.name == "posix":
        assert profiles.stat().st_mode & 0o077 == 0
    harness.close()
