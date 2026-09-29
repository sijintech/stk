"""Token Plan wire contract with stdlib HTTP parsing and no external network."""

from copy import deepcopy
import http.client
import io
import json
import ssl
import threading
from uuid import uuid4

import pytest

from suan.project import ProjectError
from suan.project import aliyun
from suan.project.request_executor import ConfirmedCancellation, DefinitiveFailure, InvalidResponse
from test_project_contexts import model, capture  # noqa: F401


KEY = "sk-sp-isolated-test-credential"


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch):
    monkeypatch.setenv(aliyun.API_KEY_ENV, KEY)
    monkeypatch.delenv(aliyun.MODEL_ENV, raising=False)
    # Fail before DNS/TLS if a test accidentally creates a real connection.
    def forbidden(*args, **kwargs):
        raise AssertionError("Tests must not create a network connection")
    monkeypatch.setattr(http.client.HTTPSConnection, "connect", forbidden)


@pytest.fixture
def frozen(model):
    store, _ = model
    context = capture(model)
    message = store.discussion.add("请解释这些参数，不运行模拟", message_id=str(uuid4()), context_id=context["id"])
    saved = store.requests.create(message["id"], request_id=str(uuid4()),
                                 configuration={"adapter": aliyun.ALIYUN_ADAPTER, "model": "qwen-test",
                                                "max_output_tokens": 128, "temperature": 0.25})
    return store.requests.input(saved["id"])


def completion(**changes):
    return {"id": "chatcmpl-test-1", "object": "chat.completion", "model": "qwen-test-version",
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": "已检查保存的参数。"}}],
            "usage": {"prompt_tokens": 80, "completion_tokens": 12, "total_tokens": 92}, **changes}


class WireSocket:
    """An in-memory socket for the real http.client request/response parser."""

    def __init__(self, response):
        self.response, self.sent, self.timeouts, self.streams = response, [], [], []
        self.closed = False

    def makefile(self, mode):
        assert mode == "rb"
        stream = io.BytesIO(self.response)
        self.streams.append(stream)
        return stream

    def sendall(self, data):
        self.sent.append(bytes(data))

    def settimeout(self, value):
        self.timeouts.append(value)

    def close(self):
        self.closed = True


@pytest.fixture
def wire(monkeypatch):
    made = []
    def install(value=None, *, status=200, headers=None, raw=None, on_connect=None, on_request=None):
        if raw is None:
            body = json.dumps(completion() if value is None else value, ensure_ascii=False).encode("utf-8")
            fields = {"Content-Type": "application/json; charset=utf-8", "Content-Length": str(len(body)),
                      **(headers or {})}
            raw = (f"HTTP/1.1 {status} fixture\r\n" + "".join(f"{k}: {v}\r\n" for k, v in fields.items())
                   + "\r\n").encode("ascii") + body
        socket = WireSocket(raw)
        def create():
            connection = http.client.HTTPSConnection("token-plan.cn-beijing.maas.aliyuncs.com", timeout=60)
            def connect():
                connection.sock = socket
                if on_connect:
                    on_connect()
            connection.connect = connect
            if on_request:
                original = connection.request
                def request(*args, **kwargs):
                    result = original(*args, **kwargs)
                    on_request()
                    return result
                connection.request = request
            made.append(connection)
            return connection
        monkeypatch.setattr(aliyun, "_connection", create)
        return socket
    install.connections = made
    return install


def send(frozen):
    return aliyun.AliyunTokenPlanAdapter().send(frozen, threading.Event())


def test_frozen_wire_payload_metadata_and_no_environment_overrides(frozen, wire, monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://credentials@unwanted-proxy:8080")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://unwanted-host/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "unwanted-key")
    monkeypatch.setenv(aliyun.MODEL_ENV, "later-model")
    socket = wire()
    before = deepcopy(frozen)
    result = send(frozen)
    headers, body = b"".join(socket.sent).split(b"\r\n\r\n", 1)
    assert headers.startswith(b"POST /compatible-mode/v1/chat/completions HTTP/1.1\r\n")
    assert b"Host: token-plan.cn-beijing.maas.aliyuncs.com\r\n" in headers
    assert b"Authorization: Bearer " + KEY.encode() + b"\r\n" in headers
    assert b"Accept-Encoding: identity\r\n" in headers
    assert b"unwanted" not in headers and KEY.encode() not in body
    payload = json.loads(body)
    assert set(payload) == {"model", "stream", "enable_thinking", "max_tokens", "temperature", "messages"}
    assert payload["model"] == "qwen-test" and payload["stream"] is False and payload["enable_thinking"] is False
    assert payload["max_tokens"] == 128 and payload["temperature"] == 0.25
    assert [item["role"] for item in payload["messages"]] == ["system", "user"]
    context = json.loads(payload["messages"][1]["content"])
    assert context == {"saved_context": frozen["context"], "question": frozen["message"]["text"]}
    assert "Do not claim" in payload["messages"][0]["content"]
    assert frozen == before and len(wire.connections) == 1 and socket.closed
    assert all(stream.closed for stream in socket.streams)
    assert result.text == "已检查保存的参数。"
    assert result.metadata == {"model": "qwen-test-version", "remote_request_id": "chatcmpl-test-1",
                               "input_tokens": 80, "output_tokens": 12}


def test_factory_uses_fixed_verified_https_endpoint_and_disables_debug(monkeypatch):
    calls = []
    class Connection:
        def __init__(self, *args, **kwargs):
            calls.append((args, kwargs))
        def set_debuglevel(self, value):
            assert value == 0
    monkeypatch.setattr(http.client, "HTTPSConnection", Connection)
    aliyun._connection()
    args, kwargs = calls[0]
    assert args == ("token-plan.cn-beijing.maas.aliyuncs.com",)
    assert kwargs["timeout"] == 60
    assert kwargs["context"].verify_mode == ssl.CERT_REQUIRED and kwargs["context"].check_hostname


def test_provider_info_is_presence_only_with_no_credential_or_model_guess(monkeypatch):
    assert aliyun.provider_info() == {"adapter": aliyun.ALIYUN_ADAPTER, "base_url": aliyun.BASE_URL,
                                     "key_env": aliyun.API_KEY_ENV, "model_env": aliyun.MODEL_ENV,
                                     "configured": True, "model": ""}
    monkeypatch.setenv(aliyun.MODEL_ENV, "provider/model-v1")
    assert aliyun.provider_info()["model"] == "provider/model-v1"
    monkeypatch.setenv(aliyun.MODEL_ENV, "https://bad-model/")
    assert aliyun.provider_info()["model"] == ""
    monkeypatch.delenv(aliyun.API_KEY_ENV)
    assert aliyun.provider_info()["configured"] is False
    assert KEY not in json.dumps(aliyun.provider_info())


@pytest.mark.parametrize("credential", ["", "short", "x" * 4097, "white space credential", "汉" * 20,
                                       "header-injection\r\nX: value"],
                         ids=["empty", "short", "too-long", "spaces", "non-ascii", "newlines"])
def test_invalid_credentials_fail_local_preflight(frozen, monkeypatch, credential):
    monkeypatch.setenv(aliyun.API_KEY_ENV, credential)
    assert aliyun.provider_info()["configured"] is False
    with pytest.raises(ProjectError, match=aliyun.API_KEY_ENV):
        aliyun.AliyunTokenPlanAdapter().prepare(frozen)


def test_prepare_binds_key_and_input_without_printing_them(frozen, wire, monkeypatch):
    prepared = aliyun.AliyunTokenPlanAdapter().prepare(frozen)
    assert KEY not in repr(prepared) and frozen["message"]["text"] not in repr(prepared)
    monkeypatch.setenv(aliyun.API_KEY_ENV, "sk-sp-different-test-credential")
    socket = wire()
    prepared.send(frozen, threading.Event())
    assert b"Authorization: Bearer " + KEY.encode() + b"\r\n" in b"".join(socket.sent)
    frozen["message"]["text"] = "Mutated after preflight"
    with pytest.raises(DefinitiveFailure, match="no longer matches"):
        prepared.send(frozen, threading.Event())
    assert len(wire.connections) == 1


@pytest.mark.parametrize("change", ["adapter", "prompt", "role", "context", "temperature", "secret-field",
                                    "nonfinite", "missing", "size"])
def test_invalid_payload_fails_before_any_connection(frozen, change):
    if change == "adapter":
        frozen["configuration"]["adapter"] = "other"
    elif change == "prompt":
        frozen["prompt_version"] = "future/2"
    elif change == "role":
        frozen["message"]["role"] = "assistant"
    elif change == "context":
        frozen["message"]["context_id"] = str(uuid4())
    elif change == "temperature":
        frozen["configuration"]["temperature"] = 2
    elif change == "secret-field":
        frozen["configuration"]["api_key"] = KEY
    elif change == "nonfinite":
        frozen["configuration"]["temperature"] = float("nan")
    elif change == "missing":
        del frozen["message"]["text"]
    else:
        frozen["context"]["oversized"] = "x" * aliyun.MAX_INPUT_BYTES
    with pytest.raises(ProjectError):
        aliyun.AliyunTokenPlanAdapter().prepare(frozen)


def test_cancel_before_and_after_connect_never_submits(frozen, wire):
    cancel = threading.Event()
    cancel.set()
    socket = wire()
    with pytest.raises(ConfirmedCancellation):
        aliyun.AliyunTokenPlanAdapter().send(frozen, cancel)
    assert not wire.connections and not socket.sent
    cancel.clear()
    socket = wire(on_connect=cancel.set)
    with pytest.raises(ConfirmedCancellation):
        aliyun.AliyunTokenPlanAdapter().send(frozen, cancel)
    assert len(wire.connections) == 1 and not socket.sent and socket.closed


def test_cancel_after_submission_can_still_return_a_complete_reply(frozen, wire):
    cancel = threading.Event()
    wire(on_request=cancel.set)
    reply = aliyun.AliyunTokenPlanAdapter().send(frozen, cancel)
    assert cancel.is_set() and reply.text == "已检查保存的参数。"


@pytest.mark.parametrize("status", [400, 401, 403, 404, 405, 413, 415, 422, 429])
def test_known_rejections_do_not_read_or_leak_error_body_and_never_retry(frozen, wire, status):
    socket = wire({"error": {"message": KEY}}, status=status)
    with pytest.raises(DefinitiveFailure) as error:
        send(frozen)
    assert KEY not in str(error.value) and error.value.__cause__ is None
    assert socket.closed and len(wire.connections) == 1


@pytest.mark.parametrize("status", [202, 301, 302, 307, 308, 408, 500, 502, 503, 504])
def test_unknown_statuses_and_redirects_remain_uncertain_without_following(frozen, wire, status):
    socket = wire({"error": {"message": KEY}}, status=status,
                  headers={"Location": "https://credential:secret@unwanted-host/path"})
    with pytest.raises(RuntimeError, match="outcome is uncertain") as error:
        send(frozen)
    assert KEY not in str(error.value) and error.value.__cause__ is None
    assert socket.closed and len(wire.connections) == 1


def test_post_timeout_redacts_exception_and_does_not_retry(frozen, wire):
    def fail():
        raise TimeoutError(KEY)
    socket = wire(on_request=fail)
    with pytest.raises(RuntimeError, match="outcome is uncertain") as error:
        send(frozen)
    assert KEY not in str(error.value) and error.value.__cause__ is None
    assert socket.closed and len(wire.connections) == 1


@pytest.mark.parametrize("boundary", ["connect", "post"])
def test_elapsed_deadline_does_not_start_or_repeat_another_operation(frozen, wire, monkeypatch, boundary):
    clock = [0]
    monkeypatch.setattr(aliyun.time, "monotonic", lambda: clock[0])
    def expire():
        clock[0] = aliyun.TIMEOUT_SECONDS + 1
    socket = wire(**{"on_connect" if boundary == "connect" else "on_request": expire})
    with pytest.raises(RuntimeError, match="outcome is uncertain"):
        send(frozen)
    assert bool(socket.sent) == (boundary == "post") and socket.closed and len(wire.connections) == 1


@pytest.mark.parametrize("change", ["length", "tool-finish", "function-finish", "missing-finish", "extra-choice",
                                    "tool-call", "function-call", "audio", "user-role", "missing-content",
                                    "reasoning-only", "empty", "oversized", "surrogate", "parts", "bool-index",
                                    "unsafe-model", "unsafe-id", "bool-tokens", "negative-tokens", "large-tokens"])
def test_incomplete_nontext_and_invalid_metadata_outputs_are_not_saved(frozen, wire, change):
    data = completion()
    choice, message = data["choices"][0], data["choices"][0]["message"]
    if change in {"length", "tool-finish", "function-finish", "missing-finish"}:
        choice["finish_reason"] = {"length": "length", "tool-finish": "tool_calls",
                                    "function-finish": "function_call", "missing-finish": None}[change]
    elif change == "extra-choice":
        data["choices"].append(deepcopy(choice))
    elif change == "tool-call":
        message["tool_calls"] = [{"function": {"name": "run_simulation"}}]
    elif change == "function-call":
        message["function_call"] = {"name": "run_simulation"}
    elif change == "audio":
        message["audio"] = {"id": "audio-1"}
    elif change == "user-role":
        message["role"] = "user"
    elif change == "missing-content":
        del message["content"]
    elif change == "reasoning-only":
        message["content"], message["reasoning_content"] = None, "Reasoning without a completed answer"
    elif change in {"empty", "oversized", "surrogate", "parts"}:
        message["content"] = {"empty": "  ", "oversized": "汉" * 21846, "surrogate": "\ud800",
                              "parts": [{"type": "text", "text": "partial"}]}[change]
    elif change == "bool-index":
        choice["index"] = False
    elif change == "unsafe-model":
        data["model"] = "https://secret@model/"
    elif change == "unsafe-id":
        data["id"] = "credential with spaces"
    else:
        data["usage"]["completion_tokens"] = {"bool-tokens": True, "negative-tokens": -1,
                                               "large-tokens": 2**63}[change]
    body = json.dumps(data).encode("ascii")
    socket = wire(raw=b"HTTP/1.1 200 fixture\r\nContent-Type: application/json\r\nContent-Length: "
                       + str(len(body)).encode() + b"\r\n\r\n" + body)
    with pytest.raises(InvalidResponse):
        send(frozen)
    assert socket.closed and len(wire.connections) == 1


@pytest.mark.parametrize("kind", ["invalid-json", "duplicate-key", "nonfinite", "invalid-utf8", "truncated",
                                  "oversized-length", "oversized-chunked", "wrong-content-type", "gzip"])
def test_http_body_framing_encoding_and_size_limits(frozen, wire, kind):
    body = json.dumps(completion()).encode()
    headers = b"Content-Type: application/json\r\n"
    if kind == "invalid-json":
        body = b"not-json " + KEY.encode()
    elif kind == "duplicate-key":
        body = body[:-1] + b', "choices": []}'
    elif kind == "nonfinite":
        body = body[:-1] + b', "extra": NaN}'
    elif kind == "invalid-utf8":
        body = b"\xff"
    elif kind == "wrong-content-type":
        headers = b"Content-Type: text/event-stream\r\n"
    elif kind == "gzip":
        headers += b"Content-Encoding: gzip\r\n"
    if kind == "oversized-chunked":
        headers += b"Transfer-Encoding: chunked\r\n"
        payload = b"x" * (aliyun.MAX_RESPONSE_BYTES + 1)
        body = f"{len(payload):x}\r\n".encode() + payload + b"\r\n0\r\n\r\n"
    else:
        length = len(body)
        if kind == "oversized-length":
            length = aliyun.MAX_RESPONSE_BYTES + 1
        elif kind == "truncated":
            length += 10
        headers += b"Content-Length: " + str(length).encode() + b"\r\n"
    socket = wire(raw=b"HTTP/1.1 200 fixture\r\n" + headers + b"\r\n" + body)
    with pytest.raises(InvalidResponse) as error:
        send(frozen)
    assert KEY not in str(error.value) and socket.closed and len(wire.connections) == 1


def test_chunked_reply_and_optional_metadata(frozen, wire):
    data = completion()
    del data["id"], data["model"], data["usage"]
    data["choices"][0]["message"]["tool_calls"] = []
    body = json.dumps(data).encode()
    chunks = [body[:30], body[30:]]
    raw = (b"HTTP/1.1 200 fixture\r\nContent-Type: application/json\r\nConnection: close\r\nTransfer-Encoding: chunked\r\n\r\n"
           + b"".join(f"{len(chunk):x}\r\n".encode() + chunk + b"\r\n" for chunk in chunks)
           + b"0\r\n\r\n")
    socket = wire(raw=raw)
    result = send(frozen)
    assert result.text == "已检查保存的参数。" and result.metadata == {} and socket.closed
