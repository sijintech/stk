"""Automatic model choice (S1d, docs/design/model-gateway.md): which endpoint and model answer a request.

Every (endpoint, model) pair is a candidate unless the data boundary, the network setting or a missing key rules it out;
a local model that is installed but not running stays a candidate that must be started first. Simple tasks (questions on a
saved context) prefer the nearest and smallest model, which is quick and free; complex tasks (parameter edit and sweep
proposals, later planning and tools) prefer the strongest. The first candidate is the choice; the rest are the fallbacks,
used only when a request definitely was not sent.
"""
from .settings import ADAPTER_PREFIX, TIERS

TASKS = {"stk.text/1": "simple", "stk.parameter-edits/1": "complex", "stk.parameter-sweep/1": "complex"}
# An endpoint that does not say its tier: a model someone runs on this computer is usually small, a group server or a
# service on the internet usually large; the built-in Token Plan serves large models.
DEFAULT_TIER = {"local": "small", "internal": "large", "external": "large"}
_NEAR = {"local": 0, "internal": 1, "external": 2}


def task_kind(prompt_version):
    """``simple`` or ``complex`` for a request's prompt version (unknown versions count as complex)."""
    return TASKS.get(prompt_version, "complex")


def candidates(endpoints, local_models, *, task, public):
    """Ranked candidates and the pairs ruled out, each ``{endpoint, name, adapter, model, location, tier, start, reason}``.

    ``endpoints``: ``ModelGateway.describe()["endpoints"]`` (with ``allowed`` from the network setting, ``key``, ``managed``).
    ``local_models``: installed llama.cpp entries ``{id, endpoint, tier, state}`` (state ``running``, ``starting``, ...),
    including ones whose endpoint is not registered yet (never started). ``public``: the request's data is labelled public.
    """
    ranked, excluded = [], []
    by_endpoint = {item["endpoint"]: item for item in local_models}
    seen, failed = set(), set()

    def consider(endpoint, model, *, tier, start):
        item = {"endpoint": endpoint["id"], "name": endpoint["name"], "adapter": endpoint["adapter"], "model": model,
                "location": endpoint["location"], "tier": tier, "start": start}
        if not endpoint.get("allowed", True):
            excluded.append({**item, "reason": "network"})
        elif endpoint["location"] == "external" and not public:
            excluded.append({**item, "reason": "private_data"})
        elif endpoint["location"] == "external" and not (endpoint.get("key") or {}).get("configured", False):
            excluded.append({**item, "reason": "no_key"})
        else:
            ranked.append(item)

    for endpoint in endpoints:
        local = by_endpoint.get(endpoint["id"])
        if local is not None:  # a model STK installed: its tier comes from the catalog, its state from the service
            seen.add(endpoint["id"])
            if local["state"] == "failed":
                failed.add(endpoint["id"])
            consider(endpoint, local["id"], tier=local["tier"], start=local["state"] != "running")
            continue
        # A managed endpoint with no installed entry here: this STK's catalog no longer lists its model; it cannot start.
        if not endpoint.get("models") or endpoint.get("managed"):
            excluded.append({"endpoint": endpoint["id"], "name": endpoint["name"], "adapter": endpoint["adapter"], "model": "",
                             "location": endpoint["location"], "tier": "", "start": False, "reason": "no_model"})
            continue
        tier = endpoint.get("tier") or DEFAULT_TIER.get(endpoint["location"], "medium")
        for model in endpoint["models"]:
            consider(endpoint, model, tier=tier, start=False)
    for local in local_models:  # installed but never started: no endpoint registered yet
        if local["endpoint"] not in seen:
            endpoint = {"id": local["endpoint"], "name": local.get("name") or local["id"],
                        "adapter": ADAPTER_PREFIX + local["endpoint"], "location": "local", "allowed": True}
            if local["state"] == "failed":
                failed.add(endpoint["id"])
            consider(endpoint, local["id"], tier=local["tier"], start=local["state"] != "running")

    def rank(item):
        tier = TIERS.index(item["tier"]) if item["tier"] in TIERS else 1
        near = _NEAR.get(item["location"], 2)
        broken = item["endpoint"] in failed  # its server failed in this session: a last resort, until it runs again
        if task == "simple":  # nearest, ready, smallest: quick and free
            return (broken, near, item["start"], tier, item["name"], item["model"])
        return (broken, -tier, item["start"], near, item["name"], item["model"])  # strongest, then ready, then nearest
    ranked.sort(key=rank)
    return {"task": task, "public": public, "candidates": ranked, "excluded": excluded}
