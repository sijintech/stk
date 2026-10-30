"""Optional CPU WebRTC helper with bounded private IPC and no default ICE servers.

The explicit CPU helper executable is built separately under its own MIT license;
importing this module neither loads a native library nor starts a process.
A ready encrypted channel is NOT a paired machine identity: its binding must be
used for both peers' signed authority challenges before routing business messages.
Raw control traffic before that decision is solely the endpoint's auth exchange.
Signaling contains ephemeral ICE credentials and must stay out of logs/projects.
No failed send is replayed automatically.
"""
from collections import deque
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import subprocess
import threading
import time


MAX_CONTROL_BYTES = 16 * 1024 * 1024
MAX_BLOB_CHUNK_BYTES = 64 * 1024
_MAX_SIGNAL_BYTES = 256 * 1024
_MAX_QUEUED_BYTES = 32 * 1024 * 1024
_HEX = re.compile(r"[0-9a-f]{64}\Z")


class TransportError(RuntimeError):
    """Safe local transport failure; no rejected payload or signaling attached."""


class TransportClosed(TransportError):
    """The channel has closed or its integrity cannot be established."""


class TransportLimitError(TransportError):
    """The caller exceeded an explicit payload/queue limit."""


@dataclass(frozen=True, repr=False)
class TransportSignal:
    """Ephemeral in-memory signaling; its repr deliberately omits credentials."""
    kind: str
    payload: dict

    def __repr__(self):
        return f"<TransportSignal {self.kind}>"


def _json(value):
    try:
        return json.dumps(value, ensure_ascii=True, allow_nan=False,
                          separators=(",", ":")).encode("ascii")
    except (TypeError, ValueError, UnicodeError):
        raise TransportError("Invalid local transport configuration") from None


def _signal(signal):
    if type(signal) is not TransportSignal or signal.kind not in ("S", "I"):
        raise TransportError("Invalid transport signal")
    expected = {"type", "sdp"} if signal.kind == "S" else {"candidate", "mid"}
    value = signal.payload
    if (type(value) is not dict or set(value) != expected
            or any(type(item) is not str for item in value.values())):
        raise TransportError("Invalid transport signal")
    if signal.kind == "S" and value["type"] not in ("offer", "answer"):
        raise TransportError("Invalid transport signal")
    raw = _json(value)
    if len(raw) > (_MAX_SIGNAL_BYTES if signal.kind == "S" else 8192):
        raise TransportLimitError("Transport signaling exceeds its limit")
    return raw


def _ready(value):
    required = {"channel_binding", "local_fingerprint", "remote_fingerprint", "local_nonce",
                "remote_nonce", "selected_pair", "max_message_size"}
    if type(value) is not dict or set(value) != required:
        raise TransportClosed("Invalid native channel binding")
    for key in required - {"selected_pair", "max_message_size"}:
        if type(value[key]) is not str or not _HEX.fullmatch(value[key]):
            raise TransportClosed("Invalid native channel binding")
    pairs = [bytes.fromhex(value["local_fingerprint"] + value["local_nonce"]),
             bytes.fromhex(value["remote_fingerprint"] + value["remote_nonce"])]
    expected = hashlib.sha256(b"stk.peer.channel/1\0" + b"".join(sorted(pairs))).hexdigest()
    if pairs[0] == pairs[1] or value["channel_binding"] != expected:
        raise TransportClosed("Invalid native channel binding")
    if type(value["max_message_size"]) is not int or not 32793 <= value["max_message_size"] <= 65536:
        raise TransportClosed("Invalid native channel message limit")
    routes = value["selected_pair"]
    if type(routes) is not list or len(routes) != 2:
        raise TransportClosed("Invalid native selected route")
    for route in routes:
        if (type(route) is not dict or set(route) != {"family", "type", "transport", "address", "port"}
                or route["family"] not in ("ipv4", "ipv6")
                or any(type(route[key]) is not str for key in ("type", "transport", "address"))
                or len(route["address"]) > 256 or type(route["port"]) is not int
                or not 0 <= route["port"] <= 65535):
            raise TransportClosed("Invalid native selected route")
    return value


class NativeTransport:
    """One explicitly started helper/connection; it never opens the desktop bridge.

    route='all' permits UDP and ICE-TCP; 'udp'/'tcp'/'ipv6' constrain signaled AND
    actually selected candidates for diagnostics. 'ipv6' is UDP over IPv6.
    ice_servers is an explicit sequence of STUN/TURN URLs; defaults to empty.
    TURN TCP/TLS is a relay connection and does not mean a direct ICE-TCP route.
    An independent native assembly_timeout defaults to 30 seconds from the
    first fragment; .2–30 seconds may be chosen for local diagnostics/tests.
    Only trusted local code may choose helper, ICE servers or timeout policy.
    """
    def __init__(self, helper, *, offerer, route="all", ice_servers=(), relay_only=False,
                 assembly_timeout=30):
        if (type(assembly_timeout) not in (int, float) or not math.isfinite(assembly_timeout)
                or not .2 <= assembly_timeout <= 30):
            raise TransportError("Invalid fragment assembly timeout")
        if (type(offerer) is not bool or type(relay_only) is not bool
                or route not in ("all", "udp", "tcp", "ipv6")
                or not isinstance(ice_servers, (tuple, list)) or len(ice_servers) > 8
                or any(type(server) is not str or len(server.encode("utf-8")) > 4096
                       for server in ice_servers)):
            raise TransportError("Invalid local transport configuration")
        self._helper = Path(helper).expanduser().absolute()
        self._config = {"offerer": offerer, "route": route,
                        "ice_servers": list(ice_servers), "relay_only": relay_only,
                        "assembly_timeout_ms": int(assembly_timeout * 1000)}
        if len(_json(self._config)) > 65536:
            raise TransportLimitError("Native transport configuration exceeds its byte limit")
        self._condition = threading.Condition()
        self._write_lock = threading.Lock()
        self._send_lock = threading.Lock()
        self._process = self._reader = None
        self._failure = None
        self._info = None
        self._signals = deque()
        self._messages = {"D": deque(), "B": deque()}
        self._queued_bytes = self._signal_bytes = 0
        self._ack = None
        self._send_id = 0

    def start(self):
        with self._condition:
            if self._process is not None or self._failure is not None:
                raise TransportClosed("Transport cannot be restarted")
            try:
                self._process = subprocess.Popen([str(self._helper)], stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0)
            except OSError:
                self._failure = TransportClosed("Optional native transport helper is unavailable")
                raise self._failure from None
            self._reader = threading.Thread(target=self._read_loop, daemon=True,
                                             name="stk-peer-transport")
            self._reader.start()
        self._write("C", _json(self._config))
        return self

    @property
    def channel_binding(self):
        with self._condition:
            self._check()
            if self._info is None:
                raise TransportError("The encrypted channel is not ready")
            return self._info["channel_binding"]

    def _check(self):
        if self._failure is not None:
            raise self._failure
        if self._process is None:
            raise TransportClosed("Transport has not been started")

    def _abort(self, error):
        with self._condition:
            if self._failure is None:
                self._failure = error
            self._condition.notify_all()
        if self._process is not None and self._process.poll() is None:
            try:
                self._process.kill()
            except OSError:
                pass

    def _write(self, kind, body):
        with self._write_lock:
            with self._condition:
                self._check()
            try:
                raw = struct.pack("!I", len(body) + 1) + kind.encode("ascii") + body
                view = memoryview(raw)
                while view:
                    count = self._process.stdin.write(view)
                    if not count:
                        raise OSError
                    view = view[count:]
            except (OSError, ValueError):
                self._abort(TransportClosed("Native transport pipe closed"))
                raise self._failure from None

    def _exact(self, count):
        blocks = []
        while count:
            data = self._process.stdout.read(count)
            if not data:
                raise TransportClosed("Native transport pipe closed")
            blocks.append(data)
            count -= len(data)
        return b"".join(blocks)

    def _read_loop(self):
        try:
            while True:
                size, = struct.unpack("!I", self._exact(4))
                if not 1 <= size <= MAX_CONTROL_BYTES + 1:
                    raise TransportClosed("Invalid native transport record")
                kind = self._exact(1).decode("ascii")
                body = self._exact(size - 1)
                if kind in ("D", "B"):
                    if len(body) > (MAX_CONTROL_BYTES if kind == "D" else MAX_BLOB_CHUNK_BYTES):
                        raise TransportClosed("Invalid native payload limit")
                    with self._condition:
                        if self._queued_bytes + len(body) > _MAX_QUEUED_BYTES or sum(
                                len(items) for items in self._messages.values()) >= 1024:
                            raise TransportClosed("Native receive queue is full")
                        self._messages[kind].append(body)
                        self._queued_bytes += len(body)
                        self._condition.notify_all()
                    continue
                if len(body) > _MAX_SIGNAL_BYTES:
                    raise TransportClosed("Invalid native event limit")
                value = json.loads(body)
                with self._condition:
                    if kind in ("S", "I"):
                        signal = TransportSignal(kind, value)
                        _signal(signal)
                        if self._signal_bytes + len(body) > 1024 * 1024 or len(self._signals) >= 256:
                            raise TransportClosed("Native signaling queue is full")
                        self._signals.append((signal, len(body)))
                        self._signal_bytes += len(body)
                    elif kind == "R":
                        if self._info is not None:
                            raise TransportClosed("Native channel binding changed")
                        self._info = _ready(value)
                    elif kind == "A":
                        if self._ack is not None:
                            raise TransportClosed("Unexpected native acknowledgment")
                        self._ack = value
                    elif kind == "E":
                        if value == {"code": "assembly_timeout"}:
                            raise TransportClosed("Native fragment assembly timed out")
                        raise TransportClosed("Native encrypted channel closed")
                    elif kind == "T":
                        if type(value) is not dict or set(value) != {"state"} or type(value["state"]) is not int:
                            raise TransportClosed("Invalid native channel state")
                    else:
                        raise TransportClosed("Invalid native transport event")
                    self._condition.notify_all()
        except TransportClosed as exc:
            self._abort(exc)
        except (OSError, ValueError, UnicodeError, TransportError, struct.error):
            self._abort(TransportClosed("Native encrypted channel closed"))

    def _wait(self, predicate, timeout):
        if type(timeout) not in (int, float) or not 0 < timeout <= 120:
            raise ValueError("Timeout must be between zero and 120 seconds")
        deadline = time.monotonic() + timeout
        with self._condition:
            while True:
                self._check()
                value = predicate()
                if value:
                    return value
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("Native transport operation timed out")
                self._condition.wait(remaining)

    def next_signal(self, *, timeout=30):
        def take():
            if self._signals:
                signal, size = self._signals.popleft()
                self._signal_bytes -= size
                return (signal,)
        return self._wait(take, timeout)[0]

    def accept_signal(self, signal):
        self._write(signal.kind, _signal(signal))

    def wait_ready(self, *, timeout=30):
        self._wait(lambda: self._info, timeout)
        with self._condition:
            # No caller can mutate the binding or route held by this adapter.
            return json.loads(json.dumps(self._info))

    def _send(self, kind, payload, timeout):
        if type(payload) is not bytes:
            raise TypeError("Transport payload must be bytes")
        if len(payload) > (MAX_CONTROL_BYTES if kind == "D" else MAX_BLOB_CHUNK_BYTES):
            raise TransportLimitError("Transport payload exceeds its byte limit")
        with self._send_lock:
            self.wait_ready(timeout=timeout)
            self._send_id += 1
            self._write(kind, payload)
            try:
                ack = self._wait(lambda: self._ack, timeout)
            except TimeoutError:
                self._abort(TransportClosed("Send acknowledgment was not received"))
                raise
            expected = {"message_id": self._send_id, "sha256": hashlib.sha256(payload).hexdigest(),
                        "kind": "control" if kind == "D" else "blob"}
            with self._condition:
                self._ack = None
            if ack != expected:
                self._abort(TransportClosed("Native send acknowledgment does not match"))
                raise self._failure
            return expected

    def send_control(self, payload, *, timeout=40):
        return self._send("D", payload, timeout)

    def send_blob_chunk(self, payload, *, timeout=40):
        return self._send("B", payload, timeout)

    def _receive(self, kind, timeout):
        def take():
            if self._messages[kind]:
                body = self._messages[kind].popleft()
                self._queued_bytes -= len(body)
                return (body,)
        return self._wait(take, timeout)[0]

    def recv_control(self, *, timeout=30):
        return self._receive("D", timeout)

    def recv_blob_chunk(self, *, timeout=30):
        return self._receive("B", timeout)

    def close(self):
        self._abort(TransportClosed("Native transport closed"))
        if self._process is not None:
            try:
                self._process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=3)
            if self._reader is not None and self._reader is not threading.current_thread():
                self._reader.join(timeout=3)
            for stream in (self._process.stdin, self._process.stdout):
                stream.close()

    def __enter__(self):
        return self.start()

    def __exit__(self, *_):
        self.close()
