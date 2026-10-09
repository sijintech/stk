"""Automatic model choice (S1d, docs/design/model-gateway.md): candidates by task, data boundary, network and availability."""
import pytest

from suan.models.routing import candidates, task_kind
from test_desktop_bridge import bridge_env, inproc  # noqa: F401
from test_project_contexts import capture, model  # noqa: F401


def endpoint(id, location, models, *, allowed=True, key=True, managed=False, tier=None, builtin=False):
    item = {"id": id, "name": id.title(), "adapter": "aliyun-token-plan/1" if builtin else f"openai-compatible/1:{id}",
            "location": location, "models": models, "allowed": allowed, "key": {"configured": key}, "builtin": builtin}
    if managed:
        item["managed"] = True
    if tier:
        item["tier"] = tier
    return item


TOKEN_PLAN = endpoint("aliyun-token-plan", "external", ["qwen-max"], builtin=True)
LAB = endpoint("lab", "internal", ["qwen3.8-27b"])
SMALL = {"id": "qwen3.5-4b-q4_k_m", "endpoint": "local-qwen3-5-4b-q4-k-m", "tier": "tiny", "state": "running"}
MEDIUM = {"id": "qwen3.8-27b-q4_k_m", "endpoint": "local-qwen3-8-27b-q4-k-m", "tier": "medium", "state": "stopped"}


def choice(result):
    return (result["candidates"][0]["endpoint"], result["candidates"][0]["model"]) if result["candidates"] else None


def test_simple_tasks_take_the_nearest_smallest_model_and_complex_ones_the_strongest():
    registered = endpoint(SMALL["endpoint"], "local", [SMALL["id"]], managed=True)
    endpoints = [TOKEN_PLAN, LAB, registered]
    simple = candidates(endpoints, [SMALL, MEDIUM], task="simple", public=True)
    assert choice(simple) == (SMALL["endpoint"], SMALL["id"])  # on this computer, running, smallest
    # The medium model was never started: it has no endpoint yet, but it is a candidate that STK starts first.
    medium = next(item for item in simple["candidates"] if item["model"] == MEDIUM["id"])
    assert medium["start"] is True and medium["adapter"] == "openai-compatible/1:" + MEDIUM["endpoint"]
    complex_ = candidates(endpoints, [SMALL, MEDIUM], task="complex", public=True)
    # Large first (the group server before the internet: nearer), then medium, then tiny.
    assert [item["endpoint"] for item in complex_["candidates"]] == ["lab", "aliyun-token-plan", MEDIUM["endpoint"], SMALL["endpoint"]]


def test_private_data_network_setting_and_keys_rule_endpoints_out():
    endpoints = [TOKEN_PLAN, LAB, endpoint("cloud", "external", ["deepseek"], key=False)]
    private = candidates(endpoints, [SMALL], task="complex", public=False)
    assert choice(private) == ("lab", "qwen3.8-27b")
    assert {(item["endpoint"], item["reason"]) for item in private["excluded"]} == {("aliyun-token-plan", "private_data"),
                                                                                     ("cloud", "private_data")}
    public = candidates(endpoints, [SMALL], task="complex", public=True)
    assert ("cloud", "no_key") in {(item["endpoint"], item["reason"]) for item in public["excluded"]}
    offline = candidates([{**TOKEN_PLAN, "allowed": False}, {**LAB, "allowed": False}], [SMALL], task="complex", public=True)
    assert choice(offline) == (SMALL["endpoint"], SMALL["id"]) and {item["reason"] for item in offline["excluded"]} == {"network"}
    assert candidates([TOKEN_PLAN], [], task="simple", public=False)["candidates"] == []


def test_tiers_come_from_the_catalog_the_endpoint_or_its_location():
    endpoints = [endpoint("laptop", "local", ["llama"]), endpoint("lab", "internal", ["big"], tier="medium"),
                 endpoint("empty", "local", [])]
    result = candidates(endpoints, [], task="complex", public=False)
    assert [(item["endpoint"], item["tier"]) for item in result["candidates"]] == [("lab", "medium"), ("laptop", "small")]
    assert result["excluded"][0]["reason"] == "no_model"
    assert task_kind("stk.text/1") == "simple" and task_kind("stk.parameter-sweep/1") == "complex"
    assert task_kind("unknown/1") == "complex"


def test_the_service_routes_questions_by_their_data_and_task(inproc, model, monkeypatch):
    monkeypatch.setenv("STK_TOKEN_PLAN_MODEL", "qwen-max")  # the built-in endpoint offers a model
    h = inproc()
    store, _ = model
    context = capture(model)
    handle = h.call("project.open", {"directory": str(store.directory)})["project"]["handle"]
    h.call("models.endpoints.add", {"id": "laptop", "name": "Laptop", "base_url": "http://127.0.0.1:9/v1", "models": ["small"]})
    h.call("models.endpoints.add", {"id": "lab", "name": "Lab", "base_url": "http://10.1.2.3:8000/v1", "models": ["big"],
                                    "location": "internal"})
    simple = h.call("models.route", {"handle": handle, "context_id": context["id"]})
    assert simple["task"] == "simple" and simple["public"] is False
    assert simple["choice"]["endpoint"] == "laptop" and simple["choice"]["model"] == "small"
    assert ("aliyun-token-plan", "private_data") in {(item["endpoint"], item["reason"]) for item in simple["excluded"]}
    proposal = h.call("models.route", {"handle": handle, "context_id": context["id"], "prompt_version": "stk.parameter-edits/1"})
    assert proposal["task"] == "complex" and proposal["choice"]["endpoint"] == "lab"
    h.call("models.policy.set", {"network": "offline"})
    offline = h.call("models.route", {"handle": handle, "context_id": context["id"], "prompt_version": "stk.parameter-edits/1"})
    assert offline["choice"]["endpoint"] == "laptop"
    from suan.scripting import Project
    project = Project(lambda method, params: h.call(method, params), handle)
    assert project.route_model(context["id"], "stk.parameter-edits/1")["choice"]["endpoint"] == "laptop"  # still offline
    monkeypatch.delenv("STK_TOKEN_PLAN_MODEL")
    unset = h.call("models.route", {"handle": handle, "context_id": context["id"]})
    assert ("aliyun-token-plan", "no_model") in {(item["endpoint"], item["reason"]) for item in unset["excluded"]}
    assert not h.violations


def test_an_added_endpoint_can_declare_its_tier(inproc, model):
    h = inproc()
    store, _ = model
    context = capture(model)
    handle = h.call("project.open", {"directory": str(store.directory)})["project"]["handle"]
    added = h.call("models.endpoints.add", {"id": "lab", "name": "Lab", "base_url": "http://10.1.2.3:8000/v1", "models": ["mid"],
                                            "location": "internal", "tier": "medium"})["endpoint"]
    assert added["tier"] == "medium"
    h.call("models.endpoints.add", {"id": "big", "name": "Big", "base_url": "http://10.1.2.4:8000/v1", "models": ["huge"],
                                    "location": "internal"})  # no tier: judged by location (large)
    proposal = h.call("models.route", {"handle": handle, "context_id": context["id"], "prompt_version": "stk.parameter-sweep/1"})
    assert [(item["endpoint"], item["tier"]) for item in proposal["candidates"]][:2] == [("big", "large"), ("lab", "medium")]
    with pytest.raises(Exception, match="tier"):
        h.call("models.endpoints.add", {"id": "odd", "name": "Odd", "base_url": "http://127.0.0.1:9/v1", "models": ["m"],
                                        "tier": "huge"})
    assert not h.violations


def test_failed_and_orphaned_local_models_are_not_the_choice():
    failed = {**SMALL, "state": "failed"}
    endpoints = [endpoint(SMALL["endpoint"], "local", [SMALL["id"]], managed=True), LAB,
                 endpoint("local-gone", "local", ["gone"], managed=True)]  # managed, but no longer in the catalog
    result = candidates(endpoints, [failed], task="simple", public=False)
    assert choice(result) == ("lab", "qwen3.8-27b")  # the failed local model comes last, the orphaned one not at all
    assert [item["endpoint"] for item in result["candidates"]] == ["lab", SMALL["endpoint"]]
    assert ("local-gone", "no_model") in {(item["endpoint"], item["reason"]) for item in result["excluded"]}
