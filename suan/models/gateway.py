"""The model gateway: which adapter sends a request, and whether it may be sent (docs/design/model-gateway.md).

``ModelGateway.get`` resolves a request's adapter identity: the built-in Alibaba Token Plan adapter, or an
OpenAI-compatible endpoint added on this computer (``openai-compatible/1:<id>``). ``ModelGateway.admit`` runs
in the request executor before a request is claimed: the network setting must allow the endpoint's location,
and an external endpoint only receives data labelled public (owner decision 8: data is not sent out unless a
person labelled it public). A refused request stays pending.
"""
import http.client
import ssl

from suan.project import aliyun as _wire
from suan.project.aliyun import ALIYUN_ADAPTER, AliyunTokenPlanAdapter
from suan.project.requests import _configuration
from suan.project.store import ProjectError

from .settings import EndpointKeys, Endpoints, ModelPolicy, parse_base_url


NEARBY_TIMEOUT_SECONDS = 1800  # a 27B model on CPU writes a few tokens a second
EXTERNAL_TIMEOUT_SECONDS = 300


class PolicyDenied(ProjectError):
    """The network setting or the data boundary does not allow sending this request."""


class OpenAICompatibleAdapter:
    """One endpoint speaking the OpenAI chat-completions protocol (llama.cpp, vLLM, Ollama, other APIs).
    It uses the Token Plan adapter's payload checks, single attempt and response parsing, without
    provider-specific body fields; a reasoning model's separate reasoning text is dropped, not shown."""

    def __init__(self, endpoint, keys):
        self._endpoint = endpoint
        self._keys = keys
        scheme, host, port, path = parse_base_url(endpoint["base_url"])
        self._path = path + "/chat/completions"
        # A model on this computer or the organization's network may answer slowly (CPU, reasoning first); there a
        # cancellation closes the connection. External services keep the short, single-attempt deadline.
        nearby = endpoint.get("location") in ("local", "internal")
        self._timeout = NEARBY_TIMEOUT_SECONDS if nearby else EXTERNAL_TIMEOUT_SECONDS
        self._cancel_closes = {"local": "this_computer", "internal": "organization"}.get(endpoint.get("location"), "")
        # Connecting (and the TLS handshake) keeps the short limit, where a cancellation cannot interrupt; the request
        # deadline applies from then on.
        if scheme == "https":
            self._connect = lambda: http.client.HTTPSConnection(host, port, timeout=_wire.TIMEOUT_SECONDS,
                                                                context=ssl.create_default_context())
        else:  # only local or internal endpoints may use plain HTTP (Endpoints.add)
            self._connect = lambda: http.client.HTTPConnection(host, port, timeout=_wire.TIMEOUT_SECONDS)

    def prepare(self, frozen_input):
        model = _configuration(frozen_input.get("configuration") if isinstance(frozen_input, dict) else None)["model"]
        if model not in self._endpoint["models"]:
            raise ProjectError(f"The endpoint {self._endpoint['name']} does not offer the model {model}")
        payload, stream_payload, digest = _wire._payload(frozen_input, adapter=self._endpoint["adapter"], options={},
                                                         provider=self._endpoint["name"])
        return _wire._Prepared(self._keys.get(self._endpoint["id"]), payload, stream_payload, digest,
                               connect=self._connect, path=self._path, provider=self._endpoint["name"], reasoning=True,
                               timeout=self._timeout, cancel_closes=self._cancel_closes)

    def prepare_turn(self, value):
        """An agent planner turn (suan/agent/wire.py): the same single-attempt transport, deadline and cancellation,
        with tools in the request and a parser that accepts one tool call. Send it with ``send(value, cancel)``."""
        import hashlib
        from suan.agent import wire
        from suan.project.contexts import _encode
        model = value["configuration"]["model"]
        if model not in self._endpoint["models"]:
            raise ProjectError(f"The endpoint {self._endpoint['name']} does not offer the model {model}")
        return _wire._Prepared(self._keys.get(self._endpoint["id"]), wire.turn_payload(value), b"",
                               hashlib.sha256(_encode(value)).digest(), connect=self._connect, path=self._path,
                               provider=self._endpoint["name"], reasoning=True, timeout=self._timeout,
                               cancel_closes=self._cancel_closes, parse=wire.turn_response)

    def send(self, frozen_input, cancel_event):
        return self.prepare(frozen_input).send(frozen_input, cancel_event)

    def send_stream(self, frozen_input, cancel_event, on_text):
        return self.prepare(frozen_input).send_stream(frozen_input, cancel_event, on_text)


class ModelGateway:
    def __init__(self, state_dir=None, credentials=None):
        self.endpoints = Endpoints(state_dir)
        self.keys = EndpointKeys(state_dir)
        self.policy = ModelPolicy(state_dir)
        self._aliyun = AliyunTokenPlanAdapter(credentials)
        self._overrides = {}  # adapters installed by tests or embedding code, by adapter identity
        self.local = None  # LocalModels, when this service manages local model servers

    def __setitem__(self, adapter, value):
        self._overrides[adapter] = value

    def get(self, adapter, default=None):
        """The adapter for a request's adapter identity (the request executor's lookup)."""
        if adapter in self._overrides:
            return self._overrides[adapter]
        if adapter == ALIYUN_ADAPTER:
            return self._aliyun
        endpoint = self.endpoints.by_adapter(adapter)
        return OpenAICompatibleAdapter(endpoint, self.keys) if endpoint else default

    def admit(self, store, record, frozen_input):
        """Refuse (``PolicyDenied``) unless the network setting allows the endpoint and, for an external
        endpoint, the request's data is labelled public. Adapters that are not endpoints are not checked."""
        endpoint = self.endpoints.by_adapter(record["configuration"]["adapter"])
        if endpoint is None:
            return
        if self.local is not None and self.local.manages(endpoint["id"]) and not self.local.is_running(endpoint["id"]):
            raise PolicyDenied(f"The local model {endpoint['name']} is not running; start it in Models and network")
        if not self.policy.allows(endpoint["location"]):
            raise PolicyDenied(f"The network setting ({self.policy.get()['network']}) does not allow the "
                               f"{endpoint['location']} endpoint {endpoint['name']}")
        if endpoint["location"] == "external":
            table = frozen_input["context"]["selection"]["table_id"]
            if not store.labels.is_public("table", table):
                raise PolicyDenied("This question's data is not labelled public: its parameter table stays private and is "
                                   "not sent to external model endpoints. Label the table public, or ask a local or "
                                   "internal model")

    def admit_planner(self, configuration, *, all_public):
        """Refuse (``PolicyDenied``) an agent planner turn the network setting or the data boundary does not allow. In v1
        the planner only runs on this computer or the organization's network (owner decision, docs/design/agent-harness.md);
        an external planner would also need every source the session has seen to be public. Adapters that are not
        endpoints (installed by tests or embedding code) are not checked, as in ``admit``."""
        endpoint = self.endpoints.by_adapter(configuration["adapter"])
        if endpoint is None:
            if configuration["adapter"] in self._overrides:
                return
            raise PolicyDenied("The agent's model endpoint is no longer configured")
        if self.local is not None and self.local.manages(endpoint["id"]) and not self.local.is_running(endpoint["id"]):
            raise PolicyDenied(f"The local model {endpoint['name']} is not running; start it in Models and network")
        if not self.policy.allows(endpoint["location"]):
            raise PolicyDenied(f"The network setting ({self.policy.get()['network']}) does not allow the "
                               f"{endpoint['location']} endpoint {endpoint['name']}")
        if endpoint["location"] == "external":
            if not all_public:
                raise PolicyDenied("The agent has read private data: it plans only with models on this computer or the "
                                   "organization's network")
            raise PolicyDenied("The agent plans only with models on this computer or the organization's network")

    def admit_sources(self, configuration, *, all_public):
        """A request the agent makes for itself goes to an external endpoint only when every data source the session
        has seen is public (its own context table is checked again by ``admit``)."""
        endpoint = self.endpoints.by_adapter(configuration["adapter"])
        if endpoint is not None and endpoint["location"] == "external" and not all_public:
            raise PolicyDenied("The agent has read private data: this request may only go to a model on this computer "
                               "or the organization's network")

    def describe(self):
        """Endpoints with their key presence and whether the network setting allows them; never keys."""
        from suan.project.aliyun import provider_info
        endpoints = []
        for item in self.endpoints.list():
            if item["builtin"]:
                info = provider_info(self._aliyun._credentials)
                key = {"configured": info["configured"], "source": info["key_source"], "can_remember": info["can_remember"],
                       "key_env": info["key_env"]}
            else:
                key = self.keys.info(item["id"])
            managed = {"managed": True} if self.local is not None and self.local.manages(item["id"]) else {}
            endpoints.append({**item, **managed, "key": key, "allowed": self.policy.allows(item["location"])})
        return {"endpoints": endpoints, "policy": self.policy.get()}
