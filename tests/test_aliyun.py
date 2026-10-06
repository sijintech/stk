"""Token Plan wire contract with stdlib HTTP parsing and no external network."""

from copy import deepcopy
import hashlib
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
from suan.project.requests import PARAMETER_EDITS_PROMPT_VERSION, PROMPT_VERSION
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
                                     "configured": True, "model": "", "key_source": "environment",
                                     "can_remember": False}
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


def stream_chunk(content=None, *, role=None, finish=None, usage=None, **changes):
    return {"id": "chatcmpl-stream-1", "object": "chat.completion.chunk", "model": "qwen-test-version",
            "choices": ([{"index": 0, "finish_reason": finish, "delta": {"role": role, "content": content}}]
                        if usage is None else []), "usage": usage, **changes}


def stream_records():
    return [stream_chunk("", role="assistant"), stream_chunk("温度"), stream_chunk(" 300 K。"),
            stream_chunk("", finish="stop"),
            stream_chunk(usage={"prompt_tokens": 80, "completion_tokens": 12, "total_tokens": 92}), "[DONE]"]


def sse_body(records=None, newline=b"\n"):
    return b"".join(b"data: " + (value.encode() if isinstance(value, str)
                                    else json.dumps(value, ensure_ascii=False).encode("utf-8"))
                    + newline * 2 for value in (stream_records() if records is None else records))


def stream_wire(wire, records=None, *, body=None, pieces=None, headers=b"", length=None, **kwargs):
    body = sse_body(records) if body is None else body
    if pieces is None:
        framing = b"Content-Length: " + str(len(body) if length is None else length).encode() + b"\r\n"
    else:
        framing = b"Transfer-Encoding: chunked\r\n"
        body = b"".join(f"{len(piece):x}\r\n".encode() + piece + b"\r\n" for piece in pieces) + b"0\r\n\r\n"
    return wire(raw=b"HTTP/1.1 200 fixture\r\nContent-Type: text/event-stream; charset=utf-8\r\n"
                    + framing + headers + b"\r\n" + body, **kwargs)


def send_stream(frozen, deltas, cancel=None):
    return aliyun.AliyunTokenPlanAdapter().send_stream(frozen, cancel or threading.Event(), deltas.append)


def test_stream_payload_is_frozen_and_only_validated_deltas_reach_observer(frozen, wire, monkeypatch):
    prepared = aliyun.AliyunTokenPlanAdapter().prepare(frozen)
    monkeypatch.setenv(aliyun.API_KEY_ENV, "sk-sp-later-test-credential")
    monkeypatch.setenv(aliyun.MODEL_ENV, "later-model")
    monkeypatch.setenv("HTTPS_PROXY", "http://unwanted-proxy:8080")
    socket = stream_wire(wire)
    deltas = []
    reply = prepared.send_stream(frozen, threading.Event(), deltas.append)
    headers, body = b"".join(socket.sent).split(b"\r\n\r\n", 1)
    assert b"Authorization: Bearer " + KEY.encode() + b"\r\n" in headers
    assert b"Accept: text/event-stream\r\n" in headers
    assert b"Host: token-plan.cn-beijing.maas.aliyuncs.com\r\n" in headers
    payload = json.loads(body)
    assert payload["stream"] is True and payload["stream_options"] == {"include_usage": True}
    assert payload["enable_thinking"] is False and payload["model"] == "qwen-test"
    assert payload["max_tokens"] == 128 and payload["temperature"] == 0.25
    assert json.loads(payload["messages"][1]["content"]) == {
        "saved_context": frozen["context"], "question": frozen["message"]["text"]}
    assert KEY.encode() not in body and "later-model" not in body.decode()
    assert deltas == ["温度", " 300 K。"] and reply.text == "".join(deltas)
    assert reply.metadata == {"remote_request_id": "chatcmpl-stream-1", "model": "qwen-test-version",
                              "input_tokens": 80, "output_tokens": 12}
    assert socket.closed and all(stream.closed for stream in socket.streams) and len(wire.connections) == 1
    frozen["message"]["text"] = "Changed after preflight"
    with pytest.raises(DefinitiveFailure, match="no longer matches"):
        prepared.send_stream(frozen, threading.Event(), deltas.append)
    assert len(wire.connections) == 1


@pytest.mark.parametrize("newline", [b"\n", b"\r\n", b"\r"], ids=["lf", "crlf", "cr"])
def test_stream_fragmentation_handles_utf8_lines_comments_and_multiline_data(frozen, wire, newline):
    records = stream_records()
    body = b"\xef\xbb\xbf: keepalive" + newline + b"id: ignored" + newline + b"retry: 1" + newline * 2
    # Multiline JSON data is one SSE event, including UTF-8 split inside every character.
    first = json.dumps(records[0]).encode().replace(b'"object":', b'\n"object":')
    body += newline.join(b"data: " + line for line in first.split(b"\n")) + newline * 2
    body += sse_body(records[1:], newline)
    socket = stream_wire(wire, pieces=[body[i:i + 1] for i in range(len(body))])
    observed = []
    def progress(text):
        assert socket.streams[0].tell() < len(socket.response)
        observed.append(text)
    reply = aliyun.AliyunTokenPlanAdapter().send_stream(frozen, threading.Event(), progress)
    assert observed == ["温度", " 300 K。"] and reply.text == "".join(observed)
    assert socket.closed and len(wire.connections) == 1


def test_stream_accepts_optional_metadata_and_whitespace_deltas(frozen, wire):
    records = [stream_chunk(" ", role="assistant"), stream_chunk("answer", finish="stop"), "[DONE]"]
    for record in records[:-1]:
        del record["id"], record["model"]
        record["choices"][0]["delta"].update(tool_calls=[], refusal=None, reasoning_content="")
    stream_wire(wire, records)
    observed = []
    reply = send_stream(frozen, observed)
    assert observed == [" ", "answer"] and reply.text == " answer" and reply.metadata == {}


@pytest.mark.parametrize("kind", ["length", "tools-finish", "tool", "function", "refusal", "audio", "reasoning",
                                  "content-list", "surrogate", "no-role", "user-role", "extra-choice", "bool-index",
                                  "changed-model", "unsafe-id", "missing-delta", "wrong-object", "provider-error",
                                  "bool-tokens", "negative-tokens", "large-tokens", "bad-total", "missing-token",
                                  "early-usage", "duplicate-usage", "early-done", "after-stop", "after-done",
                                  "empty", "oversized"])
def test_invalid_streams_never_become_complete_replies(frozen, wire, kind):
    records = stream_records()
    choice, delta = records[1]["choices"][0], records[1]["choices"][0]["delta"]
    if kind in {"length", "tools-finish"}:
        choice["finish_reason"] = "length" if kind == "length" else "tool_calls"
    elif kind in {"tool", "function", "refusal", "audio", "reasoning"}:
        key, value = {"tool": ("tool_calls", [{"function": {"name": "run"}}]),
                      "function": ("function_call", {"name": "run"}), "refusal": ("refusal", "declined"),
                      "audio": ("audio", {}), "reasoning": ("reasoning_content", "private reasoning")}[kind]
        delta[key] = value
    elif kind in {"content-list", "surrogate"}:
        delta["content"] = [{"text": "wrong shape"}] if kind == "content-list" else "\ud800"
    elif kind == "no-role":
        records[0]["choices"][0]["delta"]["role"] = None
    elif kind == "user-role":
        delta["role"] = "user"
    elif kind == "extra-choice":
        records[1]["choices"].append(deepcopy(choice))
    elif kind == "bool-index":
        choice["index"] = False
    elif kind == "changed-model":
        records[1]["model"] = "different-model"
    elif kind == "unsafe-id":
        records[1]["id"] = "https://credential@example/"
    elif kind == "missing-delta":
        del choice["delta"]
    elif kind == "wrong-object":
        records[1]["object"] = "chat.completion"
    elif kind == "provider-error":
        records[1]["error"] = {"message": KEY}
    elif kind in {"bool-tokens", "negative-tokens", "large-tokens", "bad-total", "missing-token"}:
        usage = records[-2]["usage"]
        if kind == "missing-token":
            del usage["completion_tokens"]
        else:
            usage["total_tokens" if kind == "bad-total" else "completion_tokens"] = {
                "bool-tokens": True, "negative-tokens": -1, "large-tokens": 2**63, "bad-total": "92"}[kind]
    elif kind == "early-usage":
        records.insert(1, records.pop(-2))
    elif kind == "duplicate-usage":
        records.insert(-1, deepcopy(records[-2]))
    elif kind == "early-done":
        records.insert(1, "[DONE]")
    elif kind == "after-stop":
        records.insert(-2, stream_chunk("late text"))
    elif kind == "after-done":
        records.append(stream_chunk("late text"))
    elif kind == "empty":
        records[1]["choices"][0]["delta"]["content"] = " "
        records[2]["choices"][0]["delta"]["content"] = "\n"
    else:
        delta["content"] = "x" * (64 * 1024 + 1)
    # ASCII encoding deliberately preserves malformed Unicode as JSON escapes.
    body = b"".join(b"data: " + (record.encode() if isinstance(record, str)
                                    else json.dumps(record).encode()) + b"\n\n" for record in records)
    socket = stream_wire(wire, body=body)
    observed = []
    with pytest.raises(InvalidResponse) as error:
        send_stream(frozen, observed)
    assert KEY not in str(error.value) and error.value.__cause__ is None
    assert socket.closed and len(wire.connections) == 1
    if kind in {"tool", "function", "refusal", "audio", "reasoning", "length", "tools-finish", "oversized"}:
        assert observed == []  # Reject the whole event before publishing its text.


@pytest.mark.parametrize("kind", ["no-done", "no-stop-or-done", "unterminated-event", "short-http-body",
                                  "incomplete-http-chunk"])
def test_incomplete_streams_are_uncertain_not_success_or_confirmed_cancel(frozen, wire, kind):
    records = stream_records()
    body, length = sse_body(records), None
    if kind == "no-done":
        body = sse_body(records[:-1])
    elif kind == "no-stop-or-done":
        body = sse_body(records[:3])
    elif kind == "unterminated-event":
        body = body[:-1]
    elif kind == "short-http-body":
        length = len(body) + 100
    if kind == "incomplete-http-chunk":
        raw = (b"HTTP/1.1 200 fixture\r\nContent-Type: text/event-stream\r\nTransfer-Encoding: chunked\r\n\r\n"
               + f"{len(body) + 100:x}\r\n".encode() + body)
        socket = wire(raw=raw)
    else:
        socket = stream_wire(wire, body=body, length=length)
    deltas, cancel = [], threading.Event()
    def progress(text):
        deltas.append(text)
        cancel.set()
    with pytest.raises(RuntimeError, match="outcome is uncertain"):
        aliyun.AliyunTokenPlanAdapter().send_stream(frozen, cancel, progress)
    assert "".join(deltas) == "温度 300 K。" and socket.closed and len(wire.connections) == 1


@pytest.mark.parametrize("kind", ["invalid-json", "duplicate-key", "nonfinite", "invalid-utf8", "invalid-tail", "gzip",
                                  "oversized-length", "oversized-body", "wrong-content-type"])
def test_stream_framing_encoding_and_wire_bounds(frozen, wire, kind):
    body, headers, length = sse_body(), b"", None
    if kind == "invalid-json":
        body = b"data: not-json " + KEY.encode() + b"\n\n"
    elif kind == "duplicate-key":
        body = b'data: {"choices":[],"choices":[]}\n\n'
    elif kind == "nonfinite":
        body = b'data: {"invalid":NaN}\n\n'
    elif kind == "invalid-utf8":
        body = b": invalid comment \xff\n\n"
    elif kind == "invalid-tail":
        body = b": invalid comment \xff"
    elif kind == "gzip":
        headers = b"Content-Encoding: gzip\r\n"
    elif kind == "oversized-length":
        length = aliyun.MAX_RESPONSE_BYTES + 1
    elif kind == "oversized-body":
        body = b":" + b"x" * aliyun.MAX_RESPONSE_BYTES
    if kind == "wrong-content-type":
        socket = wire()
    elif kind == "oversized-body":
        socket = stream_wire(wire, pieces=[body])
    else:
        socket = stream_wire(wire, body=body, headers=headers, length=length)
    with pytest.raises(InvalidResponse) as error:
        send_stream(frozen, [])
    assert KEY not in str(error.value) and socket.closed and len(wire.connections) == 1


@pytest.mark.parametrize("status", [401, 429, 302, 503])
def test_stream_http_failures_never_leak_or_retry(frozen, wire, status):
    socket = wire({"error": {"message": KEY}}, status=status,
                  headers={"Location": "https://secret@unwanted-host/path"})
    with pytest.raises(DefinitiveFailure if status in {401, 429} else RuntimeError) as error:
        send_stream(frozen, [])
    assert KEY not in str(error.value) and socket.closed and len(wire.connections) == 1


def test_stream_cancellation_only_confirms_when_unsent(frozen, wire):
    cancel, deltas = threading.Event(), []
    cancel.set()
    socket = stream_wire(wire)
    with pytest.raises(ConfirmedCancellation):
        send_stream(frozen, deltas, cancel)
    assert not socket.sent and not wire.connections
    cancel.clear()
    socket = stream_wire(wire, on_connect=cancel.set)
    with pytest.raises(ConfirmedCancellation):
        send_stream(frozen, deltas, cancel)
    assert not socket.sent and socket.closed
    cancel.clear()
    socket = stream_wire(wire, on_request=cancel.set)
    reply = send_stream(frozen, deltas, cancel)
    assert cancel.is_set() and reply.text == "".join(deltas) and socket.closed


def test_stream_callback_failures_are_redacted_and_validator_failure_is_preserved(frozen, wire):
    socket = stream_wire(wire)
    def broken(text):
        raise ValueError(KEY)
    with pytest.raises(RuntimeError, match="outcome is uncertain") as error:
        aliyun.AliyunTokenPlanAdapter().send_stream(frozen, threading.Event(), broken)
    assert KEY not in str(error.value) and socket.closed
    socket = stream_wire(wire)
    def invalid(text):
        raise InvalidResponse("Invalid text delta")
    with pytest.raises(InvalidResponse, match="Invalid text delta"):
        aliyun.AliyunTokenPlanAdapter().send_stream(frozen, threading.Event(), invalid)
    assert socket.closed


def test_stream_deadline_bounds_total_read_time(frozen, wire, monkeypatch):
    clock, deltas = [0], []
    monkeypatch.setattr(aliyun.time, "monotonic", lambda: clock[0])
    records = stream_records()
    socket = stream_wire(wire, pieces=[sse_body(records[:2]), sse_body(records[2:])])
    def progress(text):
        deltas.append(text)
        clock[0] = aliyun.TIMEOUT_SECONDS + 1
    with pytest.raises(RuntimeError, match="outcome is uncertain"):
        aliyun.AliyunTokenPlanAdapter().send_stream(frozen, threading.Event(), progress)
    assert deltas == ["温度"] and socket.closed and len(wire.connections) == 1


def test_stream_size_limit_counts_aggregate_utf8_not_individual_chunks(frozen, wire):
    records = [stream_chunk("汉" * 10000, role="assistant"), stream_chunk("汉" * 10000),
               stream_chunk("汉" * 1845 + "x", finish="stop"), "[DONE]"]
    stream_wire(wire, records)
    deltas = []
    reply = send_stream(frozen, deltas)
    assert len(reply.text.encode("utf-8")) == 64 * 1024 and reply.text == "".join(deltas)
    records[-2]["choices"][0]["delta"]["content"] += "x"
    stream_wire(wire, records)
    deltas = []
    with pytest.raises(InvalidResponse):
        send_stream(frozen, deltas)
    assert len("".join(deltas).encode("utf-8")) == 60000


def test_stream_bad_observer_fails_before_connection(frozen, wire):
    socket = stream_wire(wire)
    with pytest.raises(DefinitiveFailure, match="observer"):
        aliyun.AliyunTokenPlanAdapter().send_stream(frozen, threading.Event(), None)
    assert not socket.sent and not wire.connections


@pytest.fixture
def edits_frozen(model, frozen):
    store, _ = model
    record = store.requests.create(frozen["message"]["id"], request_id=str(uuid4()),
                                   configuration=frozen["configuration"], prompt_version=PARAMETER_EDITS_PROMPT_VERSION)
    return store.requests.input(record["id"])


@pytest.mark.parametrize("streaming", [False, True], ids=["complete", "stream"])
def test_parameter_edit_mode_uses_fixed_policy_and_preserves_saved_scope(edits_frozen, model, wire, streaming):
    _, ids = model
    context = edits_frozen["context"]
    # This selected scalar has neither a literal nor a definition in the saved capture.
    row = next(item for item in context["content"]["value"]["records"] if item["id"] == ids["second"])
    assert ids["temperature"] not in row["literals"] and ids["temperature"] not in row["definitions"]
    answer = json.dumps({"format": PARAMETER_EDITS_PROMPT_VERSION, "context_id": context["id"],
                         "base_revision": context["source_revision"], "summary": "Fill the captured blank temperature",
                         "edits": [{"record_id": ids["second"], "field_id": ids["temperature"], "value": 325}]})
    if streaming:
        socket = stream_wire(wire, [stream_chunk(answer[:40], role="assistant"),
                                   stream_chunk(answer[40:], finish="stop"), "[DONE]"])
        deltas = []
        reply = send_stream(edits_frozen, deltas)
        assert "".join(deltas) == answer
    else:
        data = completion()
        data["choices"][0]["message"]["content"] = answer
        socket = wire(data)
        reply = send(edits_frozen)
    _, body = b"".join(socket.sent).split(b"\r\n\r\n", 1)
    payload = json.loads(body)
    assert set(payload) == {"model", "stream", "enable_thinking", "max_tokens", "temperature", "messages"} | (
        {"stream_options"} if streaming else set())
    assert payload["stream"] is streaming and payload["enable_thinking"] is False
    assert [message["role"] for message in payload["messages"]] == ["system", "user"]
    user = json.loads(payload["messages"][1]["content"])
    assert user == {"saved_context": context, "question": edits_frozen["message"]["text"]}
    policy = payload["messages"][0]["content"]
    for requirement in (
            "exactly one strict JSON document", "without Markdown", "format, context_id, base_revision, summary, edits",
            'format to "stk.parameter-edits/1"', "context_id to saved_context.id",
            "saved_context.source_revision", "4096 characters", "1 to 1000", "exactly record_id, field_id, value",
            "pair must be unique", "never invent IDs", "selected in saved_context.selection",
            "omitted literal is not editable", "JSON fields are forbidden", "formulas and references",
            "captured blank cell", "included null", "without type coercion", "unchanged units",
            "16 KiB UTF-8", "64 KiB UTF-8", "no tools", "human action to apply"):
        assert requirement in policy
    assert reply.text == answer and len(wire.connections) == 1 and socket.closed


@pytest.mark.parametrize("streaming", [False, True], ids=["complete", "stream"])
def test_original_text_mode_policy_and_wire_shape_are_unchanged(frozen, wire, streaming):
    socket = stream_wire(wire) if streaming else wire()
    send_stream(frozen, []) if streaming else send(frozen)
    payload = json.loads(b"".join(socket.sent).split(b"\r\n\r\n", 1)[1])
    # Pin the released stk.text/1 prompt from 6123300; adding another mode must
    # not silently change the meaning of an existing saved request identity.
    assert hashlib.sha256(payload["messages"][0]["content"].encode()).hexdigest() == (
        "ddee9c489b3bfe4468489542ee680b10252564435dd03e3aa63cc18ca148e371")
    assert frozen["prompt_version"] == PROMPT_VERSION
    expected = {"model": "qwen-test", "stream": streaming, "enable_thinking": False, "max_tokens": 128,
                "temperature": 0.25, "messages": [payload["messages"][0], {"role": "user", "content":
                    aliyun._encode({"saved_context": frozen["context"], "question": frozen["message"]["text"]}).decode()}]}
    if streaming:
        expected["stream_options"] = {"include_usage": True}
    assert payload == expected


@pytest.mark.parametrize("initial_mode", [PROMPT_VERSION, PARAMETER_EDITS_PROMPT_VERSION], ids=["text", "edits"])
@pytest.mark.parametrize("streaming", [False, True], ids=["complete", "stream"])
def test_prepared_credentials_and_payload_cannot_be_rebound_to_another_prompt_mode(
        frozen, edits_frozen, wire, initial_mode, streaming):
    selected = deepcopy(frozen if initial_mode == PROMPT_VERSION else edits_frozen)
    prepared = aliyun.AliyunTokenPlanAdapter().prepare(selected)
    selected["prompt_version"] = PARAMETER_EDITS_PROMPT_VERSION if initial_mode == PROMPT_VERSION else PROMPT_VERSION
    socket = stream_wire(wire) if streaming else wire()
    with pytest.raises(DefinitiveFailure, match="no longer matches"):
        if streaming:
            prepared.send_stream(selected, threading.Event(), lambda delta: None)
        else:
            prepared.send(selected, threading.Event())
    assert not wire.connections and not socket.sent


@pytest.mark.parametrize("version", [None, True, 1, [], {}, "stk.parameter-edits/2", "stk.text/2"],
                         ids=["null", "boolean", "integer", "array", "object", "future-edits", "future-text"])
def test_unknown_prompt_versions_fail_local_preflight_without_sending(frozen, wire, version):
    frozen["prompt_version"] = version
    socket = wire()
    with pytest.raises(ProjectError, match="Invalid frozen input"):
        aliyun.AliyunTokenPlanAdapter().prepare(frozen)
    assert not wire.connections and not socket.sent
