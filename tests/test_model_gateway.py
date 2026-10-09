"""Model gateway (docs/design/model-gateway.md): endpoints, keys, the network setting and the data boundary.

Model calls go to an in-process fake OpenAI-compatible server on loopback; nothing reaches a real provider.
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import stat
import threading
from uuid import uuid4

import pytest

from suan.models import EndpointKeys, Endpoints, ModelGateway, ModelPolicy
from suan.project import ProjectError
from suan.project.aliyun import ALIYUN_ADAPTER
from suan.scripting import API, Project
from test_desktop_bridge import bridge_env, inproc  # noqa: F401
from test_project_contexts import model, capture  # noqa: F401
from test_request_executor import ControlledAdapter, eventually


class FakeModel:
    """An OpenAI-compatible chat-completions server; records each request's path, headers and body."""

    def __init__(self, reply="Ferroelectric domains form to lower the depolarization energy.", reasoning="",
                 version="HTTP/1.0", close=False, stall=False):
        self.requests = []
        self.release = threading.Event()  # a stalled server answers once released (a model still thinking)
        owner = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = version

            def log_message(self, *args):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                owner.requests.append({"path": self.path, "authorization": self.headers.get("Authorization"), "body": body})
                if stall:
                    owner.release.wait(30)
                if body.get("stream"):
                    chunks = [{"role": "assistant", "content": None}]
                    if reasoning:
                        chunks.append({"reasoning_content": reasoning})
                    chunks += [{"content": word} for word in reply.split(" ")[:1]] + [{"content": reply[len(reply.split(" ")[0]):]}]
                    events = [{"object": "chat.completion.chunk", "model": body["model"],
                               "choices": [{"index": 0, "delta": delta, "finish_reason": None}]} for delta in chunks]
                    events.append({"object": "chat.completion.chunk", "model": body["model"],
                                   "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]})
                    data = b"".join(b"data: " + json.dumps(event).encode() + b"\n\n" for event in events) + b"data: [DONE]\n\n"
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                else:
                    data = json.dumps({"object": "chat.completion", "model": body["model"], "choices": [
                        {"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": reply}}]}).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                if close:
                    self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(data)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/v1"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def fake():
    server = FakeModel(reasoning="thinking about domains")
    yield server
    server.close()


def test_endpoint_locations_and_urls_follow_the_rules(tmp_path):
    endpoints = Endpoints(tmp_path)
    assert [item["id"] for item in endpoints.list()] == ["aliyun-token-plan"]
    assert endpoints.list()[0]["location"] == "external" and endpoints.list()[0]["adapter"] == ALIYUN_ADAPTER
    local = endpoints.add("laptop", "Laptop llama.cpp", "http://127.0.0.1:8080/v1/", ["qwen2.5-7b-instruct-q4"])
    assert local["location"] == "local" and local["base_url"] == "http://127.0.0.1:8080/v1"
    assert local["adapter"] == "openai-compatible/1:laptop"
    assert endpoints.add("lab", "Lab vLLM", "http://10.1.2.3:8000/v1", ["qwen2.5-72b"], "internal")["location"] == "internal"
    with pytest.raises(ProjectError, match="HTTPS"):
        endpoints.add("cloud", "Cloud", "http://api.example.com/v1", ["m"])  # external by default, needs HTTPS
    assert endpoints.add("cloud", "Cloud", "https://api.example.com/v1", ["m"])["location"] == "external"
    with pytest.raises(ProjectError, match="this computer is local"):
        endpoints.add("loop", "Loop", "http://localhost:1/v1", ["m"], "external")
    for bad in ("ftp://host/v1", "https://user:pw@host/v1", "https://host/v1?x=1", "not a url"):
        with pytest.raises(ProjectError):
            endpoints.add("bad", "Bad", bad, ["m"])
    with pytest.raises(ProjectError, match="ID"):
        endpoints.add("aliyun-token-plan", "Mine", "https://x.example/v1", ["m"])
    # Kept in the service's private state folder, readable only by this user.
    path = tmp_path / "models" / "endpoints.json"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600 or os.name == "nt"
    assert [item["id"] for item in Endpoints(tmp_path).list()] == ["aliyun-token-plan", "laptop", "lab", "cloud"]
    endpoints.remove("cloud")
    with pytest.raises(ProjectError, match="No endpoint"):
        endpoints.remove("cloud")


def test_keys_never_leave_their_store_and_the_environment_wins(tmp_path, monkeypatch):
    keys = EndpointKeys(tmp_path)
    secret = "abcdefghijklmnopqrstu"  # low-entropy placeholder
    assert keys.get("lab") == "" and keys.info("lab")["configured"] is False
    info = keys.set("lab", secret, remember=True)
    assert info == {"configured": True, "source": "saved", "can_remember": True, "key_env": "STK_MODEL_KEY_LAB"}
    assert secret not in repr(keys) and keys.get("lab") == secret
    assert stat.S_IMODE((tmp_path / "models" / "keys" / "lab.json").stat().st_mode) == 0o600 or os.name == "nt"
    monkeypatch.setenv("STK_MODEL_KEY_LAB", "zyxwvutsrqponmlkjihg")
    assert keys.info("lab")["source"] == "environment" and keys.get("lab") == "zyxwvutsrqponmlkjihg"
    monkeypatch.delenv("STK_MODEL_KEY_LAB")
    assert keys.clear("lab")["configured"] is False


def test_network_setting_limits_endpoint_locations(tmp_path):
    policy = ModelPolicy(tmp_path)
    assert policy.get() == {"network": "internet"} and all(policy.allows(place) for place in ("local", "internal", "external"))
    policy.set("organization")
    assert policy.allows("internal") and not policy.allows("external")
    assert ModelPolicy(tmp_path).get() == {"network": "organization"}  # remembered
    policy.set("offline")
    assert policy.allows("local") and not policy.allows("internal")
    with pytest.raises(ProjectError):
        policy.set("everywhere")


def pending(harness, model, configuration):
    store, _ = model
    context = capture(model)
    message = store.discussion.add("What do these values mean?", message_id=str(uuid4()), context_id=context["id"])
    handle = harness.call("project.open", {"directory": str(store.directory)})["project"]["handle"]
    project = Project(lambda method, params: harness.call(method, params), handle)
    saved = project.requests.create(message["id"], request_id=str(uuid4()), configuration=configuration)
    return project, saved, context


def test_private_data_never_goes_to_an_external_endpoint(inproc, model):
    h = inproc()
    store, _ = model
    project, saved, context = pending(h, model, {"adapter": ALIYUN_ADAPTER, "model": "fixture-model"})
    adapter = ControlledAdapter("ok")
    h.bridge.projects._executor._adapters[ALIYUN_ADAPTER] = adapter
    try:
        with pytest.raises(Exception, match="not labelled public"):
            project.requests.start(saved["id"])
        assert store.requests.get(saved["id"])["status"] == "pending" and not adapter.started.is_set()
        # The network setting is checked too: offline refuses external endpoints even for public data.
        store.labels.set([{"kind": "table", "id": context["selection"]["table_id"]}], label="public")
        h.call("models.policy.set", {"network": "offline"})
        with pytest.raises(Exception, match="network setting"):
            project.requests.start(saved["id"])
        h.call("models.policy.set", {"network": "internet"})
        assert project.requests.start(saved["id"])["status"] == "running" and adapter.started.wait(5)
    finally:
        adapter.release.set()
    eventually(lambda: store.requests.get(saved["id"])["status"] == "completed")
    assert not h.violations


def test_a_local_endpoint_receives_private_data_and_the_reply_is_saved(inproc, model, fake):
    h = inproc()
    store, _ = model
    added = h.call("models.endpoints.add", {"id": "laptop", "name": "Laptop", "base_url": fake.url,
                                            "models": ["qwen2.5-7b-instruct"]})["endpoint"]
    assert added["location"] == "local"
    listed = h.call("models.list", {})
    assert [item["id"] for item in listed["endpoints"]] == ["aliyun-token-plan", "laptop"]
    assert listed["endpoints"][1]["allowed"] and listed["endpoints"][1]["key"]["configured"] is False
    h.call("models.policy.set", {"network": "offline"})  # a local endpoint works offline
    project, saved, _ = pending(h, model, {"adapter": "openai-compatible/1:laptop", "model": "qwen2.5-7b-instruct"})
    project.requests.start(saved["id"])
    eventually(lambda: store.requests.get(saved["id"])["status"] == "completed")
    done = store.requests.get(saved["id"])
    reply = store.discussion.get(done["assistant_message_id"])
    assert reply["text"] == "Ferroelectric domains form to lower the depolarization energy."  # reasoning text dropped
    [request] = fake.requests
    assert request["path"] == "/v1/chat/completions" and request["authorization"] is None
    assert request["body"]["model"] == "qwen2.5-7b-instruct" and request["body"]["stream"] is True
    assert "enable_thinking" not in request["body"]  # no provider-specific fields
    assert "saved_context" in request["body"]["messages"][1]["content"]
    assert not h.violations


def test_a_key_is_sent_as_a_bearer_token_and_never_reported(inproc, model, fake):
    h = inproc()
    secret = "abcdefghijklmnopqrstu"
    h.call("models.endpoints.add", {"id": "lab", "name": "Lab", "base_url": fake.url, "models": ["m"]})
    info = h.call("models.keys.set", {"id": "lab", "key": secret})["key"]
    assert info["configured"] and info["source"] == "session"
    assert secret not in json.dumps(h.call("models.list", {}))
    store, _ = model
    project, saved, _ = pending(h, model, {"adapter": "openai-compatible/1:lab", "model": "m"})
    project.requests.start(saved["id"])
    eventually(lambda: store.requests.get(saved["id"])["status"] == "completed")
    assert fake.requests[0]["authorization"] == "Bearer " + secret
    with pytest.raises(Exception, match="does not offer"):
        _, other, _ = pending(h, model, {"adapter": "openai-compatible/1:lab", "model": "unknown"})
        project.requests.start(other["id"])
    with pytest.raises(Exception, match="ai.credentials.set"):
        h.call("models.keys.set", {"id": "aliyun-token-plan", "key": secret})
    assert h.call("models.endpoints.remove", {"id": "lab"}) == {"removed": "lab"}
    assert not h.violations


def test_scripts_can_read_model_settings_but_not_change_them(inproc):
    h = inproc()
    catalog = h.call("script.catalog")["operations"]
    assert "models.list" in catalog
    assert not {"models.endpoints.add", "models.endpoints.remove", "models.keys.set", "models.keys.clear",
                "models.policy.set", "ai.credentials.set"} & set(catalog)
    stk = API(lambda method, params: h.call(method, params))
    assert stk.models.list()["policy"] == {"network": "internet"}


def test_the_gateway_resolves_adapters_and_skips_unknown_ones(tmp_path):
    gateway = ModelGateway(tmp_path)
    assert gateway.get(ALIYUN_ADAPTER) is not None and gateway.get("openai-compatible/1:none") is None
    gateway.endpoints.add("laptop", "Laptop", "http://127.0.0.1:9/v1", ["m"])
    assert gateway.get("openai-compatible/1:laptop") is not None
    marker = object()
    gateway["controlled"] = marker
    assert gateway.get("controlled") is marker
    # Adapters that are not endpoints (test doubles) are not checked against labels or the network setting.
    gateway.admit(None, {"configuration": {"adapter": "controlled"}}, {})


@pytest.mark.parametrize("version,close", [("HTTP/1.0", False), ("HTTP/1.1", True), ("HTTP/1.1", False)])
def test_replies_are_read_when_the_server_closes_the_connection(model, version, close):
    """Local servers answer "Connection: close" by closing; the socket must not be used after the body ends."""
    server = FakeModel(version=version, close=close)
    try:
        store, _ = model
        context = capture(model)
        message = store.discussion.add("Q?", message_id=str(uuid4()), context_id=context["id"])
        saved = store.requests.create(message["id"], request_id=str(uuid4()),
                                      configuration={"adapter": "openai-compatible/1:laptop", "model": "m"})
        gateway = ModelGateway()
        gateway.endpoints.add("laptop", "Laptop", server.url, ["m"])
        frozen = store.requests.input(saved["id"])
        prepared = gateway.get("openai-compatible/1:laptop").prepare(frozen)
        assert prepared.send(frozen, threading.Event()).text == server_reply()
        seen = []
        assert prepared.send_stream(frozen, threading.Event(), seen.append).text == server_reply()
        assert "".join(seen) == server_reply()
    finally:
        server.close()


def server_reply():
    return "Ferroelectric domains form to lower the depolarization energy."


@pytest.mark.parametrize("location", ["local", "internal"])
def test_slow_nearby_models_have_time_and_a_cancellation_closes_the_connection(model, location):
    """A model on this computer (or the group's server) may think for minutes on a CPU: the deadline is long, and a
    cancellation ends the wait at once. On this computer that is a confirmed cancellation; elsewhere it is uncertain."""
    from suan.models.gateway import EXTERNAL_TIMEOUT_SECONDS, NEARBY_TIMEOUT_SECONDS, OpenAICompatibleAdapter
    from suan.project.request_executor import ConfirmedCancellation
    server = FakeModel(stall=True)
    try:
        store, _ = model
        context = capture(model)
        message = store.discussion.add("Q?", message_id=str(uuid4()), context_id=context["id"])
        adapter_id = "openai-compatible/1:near"
        saved = store.requests.create(message["id"], request_id=str(uuid4()), configuration={"adapter": adapter_id, "model": "m"})
        endpoint = {"id": "near", "name": "Near", "base_url": server.url, "location": location, "models": ["m"], "adapter": adapter_id}
        frozen = store.requests.input(saved["id"])
        prepared = OpenAICompatibleAdapter(endpoint, EndpointKeys()).prepare(frozen)
        assert prepared.timeout == NEARBY_TIMEOUT_SECONDS > EXTERNAL_TIMEOUT_SECONDS
        cancel, outcome = threading.Event(), []

        def send():
            try:
                prepared.send_stream(frozen, cancel, lambda text: None)
            except BaseException as exc:  # noqa: BLE001 - the outcome is the point
                outcome.append(exc)
        worker = threading.Thread(target=send)
        worker.start()
        eventually(lambda: server.requests)
        cancel.set()
        worker.join(5)
        assert not worker.is_alive()
        expected = ConfirmedCancellation if location == "local" else RuntimeError
        assert type(outcome[0]) is expected, outcome
    finally:
        server.release.set()
        server.close()
    # External services keep a short deadline and no in-flight cancellation; the built-in Token Plan is unchanged.
    external = OpenAICompatibleAdapter({**endpoint, "base_url": "https://api.example.com/v1", "location": "external"},
                                       EndpointKeys()).prepare(frozen)
    assert external.timeout == EXTERNAL_TIMEOUT_SECONDS and external.cancel_closes == ""
