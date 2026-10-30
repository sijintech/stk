"""Mutually authenticated, bounded bidirectional RPC on an explicit native transport.

Construction is passive. The owner supplies approved public identity pins and a
signing callback; this module neither obtains nor persists private keys, signals
ICE, listens on a socket, or opens a caller-selected project path.
"""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
import json
import math
import re
import threading
import time
from uuid import UUID, uuid4

from suan.project import ProjectError, RevisionConflict
from suan.project.store import UnsupportedProjectFormat
from suan.project.edit_operations import OperationNotFound

from .authority import PeerDenied, PeerOutcomeUncertain, auth_message, peer_id_for
from .projects import PeerProjects
from .protocol import (FORMAT, METHODS, PeerProtocolError, decode_message,
                       encode_message, negotiate_hello, validate_request,
                       validate_response)


AUTH_FORMAT = "stk.peer-auth-channel/1"
MAX_AUTH_BYTES = 4096
MAX_AUTH_DEPTH = 8
MAX_CONNECTION_REQUESTS = 4096
_HEX = re.compile(r"[0-9a-f]{64}")
_SIGNATURE = re.compile(r"[0-9a-f]{128}")
_APPLY = "project.edit_operations.apply_once"
_READ_METHODS = frozenset({"project.catalog", "project.table.read", "project.edit_operations.get"})


def _error(code="unavailable", message="Peer connection is unavailable"):
    return PeerProtocolError(code, message)


class PeerCallUncertain(PeerProtocolError):
    """The write may have committed. Retain the original request and explicitly get its receipt."""

    def __init__(self, operation_id, expected_revision):
        self.operation_id = operation_id
        self.expected_revision = expected_revision
        self.uncertain = True
        super().__init__("unavailable", "Peer write outcome is uncertain; query the original receipt")


class _RemoteFailure(PeerProtocolError):
    pass


def _uuid(value):
    try:
        return type(value) is str and str(UUID(value)) == value
    except (ValueError, AttributeError):
        return False


def _timeout(value):
    if type(value) not in (int, float) or not 0 < value <= 60 or not math.isfinite(value):
        raise _error("invalid_params", "Peer timeout must be greater than zero and at most 60 seconds")
    return float(value)


def _remaining(deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("Peer operation timed out")
    return remaining


def _auth_frame(raw):
    """Strict, small pre-auth decoder, independent from the business envelope."""
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_AUTH_BYTES:
        raise _error("unauthorized", "Peer authentication failed")
    depth = 0
    quoted = escaped = False
    for byte in raw:
        if quoted:
            if escaped:
                escaped = False
            elif byte == 92:
                escaped = True
            elif byte == 34:
                quoted = False
        elif byte == 34:
            quoted = True
        elif byte in (91, 123):
            depth += 1
            if depth > MAX_AUTH_DEPTH:
                raise _error("unauthorized", "Peer authentication failed")
        elif byte in (93, 125):
            depth -= 1
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError
            value[key] = item
        return value
    def constant(_):
        raise ValueError
    try:
        value = json.loads(raw.decode("utf-8", "strict"), object_pairs_hook=pairs, parse_constant=constant)
        if type(value) is not dict or value.get("format") != AUTH_FORMAT:
            raise ValueError
        kind = value.get("type")
        if kind == "challenge" and set(value) == {"format", "type", "challenge"}:
            auth_message(value["challenge"])
        elif kind == "proof" and set(value) == {"format", "type", "challenge_id", "signature"}:
            if (not _uuid(value["challenge_id"]) or type(value["signature"]) is not str
                    or not _SIGNATURE.fullmatch(value["signature"])):
                raise ValueError
        elif kind == "accepted" and set(value) == {"format", "type", "challenge_id"}:
            if not _uuid(value["challenge_id"]):
                raise ValueError
        else:
            raise ValueError
        return value
    except (ValueError, TypeError, UnicodeError, RecursionError, PeerDenied):
        raise _error("unauthorized", "Peer authentication failed") from None


def _auth_encode(kind, **values):
    raw = json.dumps({"format": AUTH_FORMAT, "type": kind, **values}, sort_keys=True,
                     separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")
    _auth_frame(raw)
    return raw


@dataclass
class _Pending:
    method: str
    event: threading.Event = field(default_factory=threading.Event)
    response: object = None
    error: object = None


class PeerEndpoint:
    """One-use connection, with one control reader and bounded requests in both directions.

    ``transport`` is an explicitly connected NativeTransport. Pairing pins and
    ``sign(bytes)->bytes64`` come from trusted local configuration, not the wire.
    Call start on both ends concurrently, then request. No method reconnects or
    retries; a new transport and endpoint are required after any connection loss.
    """

    def __init__(self, transport, authority, *, public_key, sign,
                 remote_peer_id, remote_owner_id, max_inflight=8, max_workers=4):
        own_peer = peer_id_for(public_key)
        if (type(remote_peer_id) is not str or not _HEX.fullmatch(remote_peer_id)
                or remote_peer_id == own_peer or not _uuid(remote_owner_id) or not callable(sign)):
            raise _error("invalid_params", "Peer identity pins are invalid")
        if (type(max_inflight) is not int or not 1 <= max_inflight <= 8
                or type(max_workers) is not int or not 1 <= max_workers <= 4):
            raise _error("invalid_params", "Peer concurrency limit is invalid")
        self._transport, self._authority = transport, authority
        self._sign = sign
        self._own_peer, self._remote_peer = own_peer, remote_peer_id
        self._remote_owner = remote_owner_id
        self._projects = PeerProjects(authority)
        self._max_inflight, self._max_workers = max_inflight, max_workers
        self._lock, self._send_lock = threading.RLock(), threading.Lock()
        self._workers = threading.BoundedSemaphore(max_workers)
        self._ready, self._closed, self._cleaned = threading.Event(), threading.Event(), threading.Event()
        self._pending, self._seen = {}, set()
        self._request_count = 0
        self._started = False
        self._context = self._reader = self._pool = None
        self._remote_capabilities = {}
        self._inbound_capabilities = None
        self._hello_inflight = False

    def __repr__(self):
        return "<PeerEndpoint closed>" if self._closed.is_set() else "<PeerEndpoint>"

    def _send(self, raw, deadline):
        if not self._send_lock.acquire(timeout=_remaining(deadline)):
            raise TimeoutError("Peer send timed out")
        try:
            if self._closed.is_set():
                raise _error()
            self._transport.send_control(raw, timeout=_remaining(deadline))
        finally:
            self._send_lock.release()

    def start(self, *, timeout=30):
        """Verify both channel-bound proofs and negotiate capabilities, without starting a transport."""
        deadline = time.monotonic() + _timeout(timeout)
        with self._lock:
            if self._started or self._closed.is_set():
                raise _error("unavailable", "Peer endpoint cannot be restarted")
            self._started = True
        try:
            self._transport.wait_ready(timeout=_remaining(deadline))
            binding = self._transport.channel_binding
            own_challenge = self._authority.challenge(self._remote_peer, channel_binding=binding)
            self._send(_auth_encode("challenge", challenge=own_challenge), deadline)
            remote = _auth_frame(self._transport.recv_control(timeout=_remaining(deadline)))
            if remote["type"] != "challenge":
                raise PeerDenied
            challenge = remote["challenge"]
            # Validate all structure before invoking the private signing callback.
            message = auth_message(challenge)
            if (challenge["peer_id"] != self._own_peer or challenge["owner_id"] != self._remote_owner
                    or challenge["channel_binding"] != binding):
                raise PeerDenied
            signature = self._sign(message)
            if type(signature) is not bytes or len(signature) != 64:
                raise PeerDenied
            self._send(_auth_encode("proof", challenge_id=challenge["challenge_id"], signature=signature.hex()), deadline)
            proof = _auth_frame(self._transport.recv_control(timeout=_remaining(deadline)))
            if proof["type"] != "proof" or proof["challenge_id"] != own_challenge["challenge_id"]:
                raise PeerDenied
            context = self._authority.authenticate(proof["challenge_id"], bytes.fromhex(proof["signature"]))
            with self._lock:
                if self._closed.is_set():
                    self._authority.disconnect(context)
                    raise PeerDenied
                self._context = context
            # We verified the proof of our own issued challenge. The remote ACK
            # must confirm the different challenge that we signed for it.
            self._send(_auth_encode("accepted", challenge_id=own_challenge["challenge_id"]), deadline)
            accepted = _auth_frame(self._transport.recv_control(timeout=_remaining(deadline)))
            if accepted["type"] != "accepted" or accepted["challenge_id"] != challenge["challenge_id"]:
                raise PeerDenied
            with self._lock:
                if self._closed.is_set():
                    raise PeerDenied
                self._pool = ThreadPoolExecutor(max_workers=self._max_workers, thread_name_prefix="stk-peer-call")
                self._reader = threading.Thread(target=self._read_loop, name="stk-peer-reader", daemon=True)
                self._reader.start()
            result = self._exchange("peer.hello", {"protocols": [1], "capabilities": {name: 1 for name in METHODS}}, deadline)
            with self._lock:
                if self._closed.is_set():
                    raise PeerDenied
                self._remote_capabilities = result["capabilities"]
                self._ready.set()
            return self
        except Exception:
            self._abort()
            raise _error("unauthorized", "Peer authentication or negotiation failed") from None

    def wait_ready(self, *, timeout=30):
        deadline = time.monotonic() + _timeout(timeout)
        try:
            while not self._ready.is_set():
                if self._closed.is_set():
                    raise _error()
                self._ready.wait(min(.05, _remaining(deadline)))
        except TimeoutError:
            self._abort()
            raise _error() from None
        if self._closed.is_set():
            raise _error()
        return self.capabilities

    @property
    def capabilities(self):
        """Detached remote negotiated methods; current grants are still checked per request."""
        with self._lock:
            if not self._ready.is_set() or self._closed.is_set():
                raise _error()
            return dict(self._remote_capabilities)

    def request(self, method, params, *, timeout=30):
        """Make exactly one attempt. Transport failure of apply_once raises PeerCallUncertain."""
        deadline = time.monotonic() + _timeout(timeout)
        request = validate_request({"format": FORMAT, "id": str(uuid4()), "method": method, "params": params})
        with self._lock:
            if not self._ready.is_set() or self._closed.is_set():
                raise _error()
            if method != "peer.hello" and method not in self._remote_capabilities:
                raise _error("unsupported", "Peer capability was not negotiated")
        try:
            result = self._exchange(method, request["params"], deadline, request=request)
        except PeerProtocolError as error:
            if (method == _APPLY and error.code in {"unavailable", "internal_error", "limit_exceeded"}
                    and (self._closed.is_set() or isinstance(error, _RemoteFailure))):
                raise PeerCallUncertain(request["params"]["operation_id"], request["params"]["expected_revision"]) from None
            raise
        if method == "peer.hello":
            with self._lock:
                self._remote_capabilities = result["capabilities"]
        return result

    def _exchange(self, method, params, deadline, *, request=None):
        request = request or {"format": FORMAT, "id": str(uuid4()), "method": method, "params": params}
        raw = encode_message(request)
        pending = _Pending(method)
        with self._lock:
            if self._closed.is_set():
                raise _error()
            if len(self._pending) >= self._max_inflight:
                raise _error("busy", "Peer outgoing request capacity is exhausted")
            if self._request_count >= MAX_CONNECTION_REQUESTS:
                raise _error("limit_exceeded", "Peer connection request budget is exhausted")
            self._request_count += 1
            self._pending[request["id"]] = pending
        try:
            self._send(raw, deadline)
            if not pending.event.wait(_remaining(deadline)):
                raise TimeoutError("Peer request timed out")
        except Exception:
            self._abort()
            raise _error() from None
        finally:
            with self._lock:
                self._pending.pop(request["id"], None)
        if pending.error is not None:
            raise pending.error
        response = pending.response
        if "error" in response:
            # The remote description is untrusted text. Expose a fixed local mapping.
            raise _RemoteFailure(response["error"]["code"], "Peer request was rejected")
        return response["result"]

    def _available(self):
        capabilities = self._authority.capabilities(self._context)
        methods = {"peer.hello": 1}
        if "project.read" in capabilities:
            methods.update({method: 1 for method in _READ_METHODS})
        if "project.edit" in capabilities:
            methods[_APPLY] = 1
        return methods

    def _read_loop(self):
        try:
            while not self._closed.is_set():
                try:
                    raw = self._transport.recv_control(timeout=.2)
                except TimeoutError:
                    continue
                message = decode_message(raw)
                if "method" not in message:
                    with self._lock:
                        pending = self._pending.get(message["id"])
                        if pending is None or pending.event.is_set():
                            raise _error("invalid_request", "Peer response has no pending request")
                        pending.response = validate_response(message, method=pending.method)
                        pending.event.set()
                    continue
                with self._lock:
                    if message["id"] in self._seen or len(self._seen) >= MAX_CONNECTION_REQUESTS:
                        raise _error("invalid_request", "Peer request identity cannot be reused")
                    self._seen.add(message["id"])
                    hello = message["method"] == "peer.hello"
                    hello_busy = hello and self._hello_inflight
                    if hello and not hello_busy:
                        self._hello_inflight = True
                if hello_busy:
                    self._reply_error(message, "busy", "Peer capability negotiation is already in progress")
                    continue
                if not hello and not self._ready.is_set():
                    self._reply_error(message, "busy", "Peer capability negotiation is not complete")
                    continue
                if (message["method"] != "peer.hello" and (self._inbound_capabilities is None
                        or message["method"] not in self._inbound_capabilities)):
                    self._reply_error(message, "unsupported", "Peer capability was not negotiated")
                elif not self._workers.acquire(blocking=False):
                    if hello:
                        with self._lock:
                            self._hello_inflight = False
                    self._reply_error(message, "busy", "Peer incoming request capacity is exhausted")
                else:
                    try:
                        # Hello also consults the authority. Keep that possibly
                        # leased lock off the one reader which routes replies.
                        self._pool.submit(self._worker, message)
                    except Exception:
                        if hello:
                            with self._lock:
                                self._hello_inflight = False
                        self._workers.release()
                        raise
        except Exception:
            self._abort()

    def _worker(self, message):
        try:
            if not self._closed.is_set():
                self._serve(message)
        finally:
            if message["method"] == "peer.hello":
                with self._lock:
                    self._hello_inflight = False
            self._workers.release()

    def _serve(self, message):
        method, params = message["method"], message["params"]
        try:
            if method == "peer.hello":
                result = negotiate_hello(params, capabilities=self._available())
                self._inbound_capabilities = result["capabilities"]
            elif method == "project.catalog":
                result = self._projects.catalog(self._context, **params)
            elif method == "project.table.read":
                result = self._projects.read_table(self._context, **params)
            elif method == _APPLY:
                result = self._projects.apply_once(self._context, **params)
            elif method == "project.edit_operations.get":
                result = {"receipt": self._projects.get(self._context, **params)}
            else:
                raise _error("unsupported", "Peer method is not supported")
            try:
                raw = encode_message({"format": FORMAT, "id": message["id"], "result": result}, method=method)
            except Exception:
                # Requests have already been validated. A broken result DTO is
                # a server failure, and an edit may already have committed.
                raise _error("internal_error", "Peer response could not be encoded") from None
        except Exception as error:
            if isinstance(error, PeerOutcomeUncertain):
                code = "unavailable"
            elif isinstance(error, PeerDenied):
                code = "forbidden"
            elif isinstance(error, (OperationNotFound, FileNotFoundError)):
                code = "not_found"
            elif isinstance(error, RevisionConflict):
                code = "conflict"
            elif isinstance(error, UnsupportedProjectFormat):
                code = "unsupported"
            elif isinstance(error, PeerProtocolError):
                code = error.code
            elif isinstance(error, ProjectError):
                code = "invalid_params"
            else:
                code = "internal_error"
            raw = encode_message({"format": FORMAT, "id": message["id"],
                                  "error": {"code": code, "message": "Peer request was rejected"}}, method=method)
        try:
            self._send(raw, time.monotonic() + 30)
        except Exception:
            self._abort()

    def _reply_error(self, message, code, description):
        self._send(encode_message({"format": FORMAT, "id": message["id"],
                                  "error": {"code": code, "message": description}}, method=message["method"]),
                   time.monotonic() + 30)

    def _abort(self):
        with self._lock:
            if self._closed.is_set():
                return
            self._closed.set()
            context, self._context = self._context, None
            for pending in self._pending.values():
                if not pending.event.is_set():
                    pending.error = _error()
                    pending.event.set()
            if self._pool is not None:
                self._pool.shutdown(wait=False, cancel_futures=True)
        # A store operation already holding its lease may finish after disconnect.
        # Cleanup must not block request timeout delivery on that accepted commit.
        def cleanup():
            try:
                self._transport.close()
            finally:
                try:
                    if context is not None:
                        self._authority.disconnect(context)
                finally:
                    self._cleaned.set()
        threading.Thread(target=cleanup, name="stk-peer-close", daemon=True).start()

    def close(self):
        self._abort()
        self._cleaned.wait(timeout=3)
        if self._reader is not None and self._reader is not threading.current_thread():
            self._reader.join(timeout=.3)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


__all__ = ["PeerEndpoint", "PeerCallUncertain", "AUTH_FORMAT", "MAX_AUTH_BYTES", "MAX_AUTH_DEPTH",
           "MAX_CONNECTION_REQUESTS"]
