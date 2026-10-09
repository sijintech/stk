"""Model endpoints, their keys and the network setting, kept in the service's private state folder.

Nothing here is project data: endpoints belong to this computer (or this on-prem installation). Keys follow
the Token Plan rules (``suan.project.aliyun.TokenPlanCredentials``): an environment variable always wins,
then a key set for this service session, then one the user asked this computer to remember (mode 0600);
reports, reprs, errors and logs never contain a key.
"""
import ipaddress
import json
import os
from pathlib import Path
import re
import threading
from urllib.parse import urlsplit
import uuid

from suan.project.aliyun import ALIYUN_ADAPTER, BASE_URL, MODEL_ENV, _KEY
from suan.project.requests import _identifier
from suan.project.store import ProjectError

BUILTIN_ID = "aliyun-token-plan"
ADAPTER_PREFIX = "openai-compatible/1:"
LOCATIONS = ("local", "internal", "external")
TIERS = ("tiny", "small", "medium", "large")  # how capable an endpoint's models are (automatic model choice)
NETWORK_MODES = ("offline", "organization", "internet")
MAX_ENDPOINTS = 32
MAX_MODELS = 32
_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,31}\Z")
_ALLOWED = {"offline": {"local"}, "organization": {"local", "internal"}, "internet": set(LOCATIONS)}


def _write_private(path, data):
    """Atomically replace ``path`` with JSON readable only by this user."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        descriptor = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def _read(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def loopback(host):
    """``localhost`` and loopback addresses: the endpoint runs on this computer."""
    if host.lower() in ("localhost", "localhost.localdomain"):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def parse_base_url(value):
    """(scheme, host, port, path) of an OpenAI-compatible base URL such as ``http://127.0.0.1:8080/v1``."""
    if not isinstance(value, str) or not 1 <= len(value) <= 2048 or any(c.isspace() for c in value):
        raise ProjectError("A base URL is 1 to 2048 characters without spaces")
    parts = urlsplit(value)
    if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password \
            or parts.query or parts.fragment:
        raise ProjectError("A base URL is http(s)://host[:port][/path] without credentials, query or fragment")
    try:
        port = parts.port or (443 if parts.scheme == "https" else 80)
    except ValueError:
        raise ProjectError("The base URL port is invalid") from None
    return parts.scheme, parts.hostname, port, parts.path.rstrip("/")


class Endpoints:
    """The built-in Alibaba Token Plan endpoint and the OpenAI-compatible endpoints added on this computer."""

    FILE = "endpoints.json"

    def __init__(self, state_dir=None):
        self._path = Path(state_dir) / "models" / self.FILE if state_dir else None
        self._memory = []  # without a state folder (tests, scripts) endpoints last for this process
        self._lock = threading.Lock()

    def _custom(self):
        if self._path is None:
            return list(self._memory)
        data = _read(self._path) or {}
        items = data.get("endpoints") if data.get("format") == "stk.model-endpoints/1" else None
        return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []

    def _save(self, items):
        if self._path is None:
            self._memory = list(items)
        else:
            _write_private(self._path, {"format": "stk.model-endpoints/1", "endpoints": items})

    @staticmethod
    def builtin():
        try:
            model = _identifier(os.environ.get(MODEL_ENV, ""), "model")
        except ProjectError:
            model = ""
        return {"id": BUILTIN_ID, "name": "Alibaba Token Plan", "adapter": ALIYUN_ADAPTER, "base_url": BASE_URL,
                "location": "external", "models": [model] if model else [], "builtin": True}

    def list(self):
        return [self.builtin(), *({**item, "adapter": ADAPTER_PREFIX + item["id"], "builtin": False} for item in self._custom())]

    def get(self, endpoint_id):
        return next((item for item in self.list() if item["id"] == endpoint_id), None)

    def by_adapter(self, adapter):
        return next((item for item in self.list() if item["adapter"] == adapter), None)

    def add(self, endpoint_id, name, base_url, models, location=None, tier=None):
        """Add (or replace) an endpoint. A loopback host is always ``local``; any other host is ``external``
        unless declared ``internal`` (inside the organization's network). External endpoints need HTTPS.
        ``tier`` (tiny, small, medium, large) tells the automatic model choice how capable its models are."""
        if not isinstance(endpoint_id, str) or not _ID.fullmatch(endpoint_id) or endpoint_id == BUILTIN_ID:
            raise ProjectError("An endpoint ID is 1 to 32 lowercase letters, digits or hyphens (not the built-in one)")
        if not isinstance(name, str) or not name.strip() or len(name) > 64 or "\0" in name:
            raise ProjectError("An endpoint name is 1 to 64 characters")
        scheme, host, _, _ = parse_base_url(base_url)
        if loopback(host):
            if location not in (None, "local"):
                raise ProjectError("An endpoint on this computer is local")
            location = "local"
        else:
            location = location or "external"
            if location not in ("internal", "external"):
                raise ProjectError("An endpoint on another computer is internal (inside the organization) or external")
        if location == "external" and scheme != "https":
            raise ProjectError("External endpoints must use HTTPS")
        if not isinstance(models, list) or not 1 <= len(models) <= MAX_MODELS:
            raise ProjectError(f"List 1 to {MAX_MODELS} model names")
        models = list(dict.fromkeys(_identifier(model, "model") for model in models))
        if tier not in (None, *TIERS):
            raise ProjectError("An endpoint's tier is tiny, small, medium or large")
        item = {"id": endpoint_id, "name": name.strip(), "base_url": base_url.rstrip("/"), "location": location, "models": models}
        if tier:
            item["tier"] = tier
        with self._lock:
            items = [existing for existing in self._custom() if existing.get("id") != endpoint_id]
            if len(items) >= MAX_ENDPOINTS:
                raise ProjectError(f"At most {MAX_ENDPOINTS} endpoints")
            self._save([*items, item])
        return self.get(endpoint_id)

    def remove(self, endpoint_id):
        with self._lock:
            items = self._custom()
            kept = [item for item in items if item.get("id") != endpoint_id]
            if len(kept) == len(items):
                raise ProjectError(f"No endpoint {endpoint_id}")
            self._save(kept)


class EndpointKeys:
    """Keys of added endpoints: ``STK_MODEL_KEY_<ID>`` (ID upper case, ``-`` as ``_``) wins, then a key set for
    this session, then a remembered one (``models/keys/<id>.json``, mode 0600)."""

    def __init__(self, state_dir=None):
        self._folder = Path(state_dir) / "models" / "keys" if state_dir else None
        self._session = {}
        self._managed = {}  # keys STK gave the local model servers it started; these win over everything else
        self._lock = threading.Lock()

    def __repr__(self):
        return "EndpointKeys(<redacted>)"

    @staticmethod
    def environment_name(endpoint_id):
        return "STK_MODEL_KEY_" + endpoint_id.upper().replace("-", "_")

    def _saved(self, endpoint_id):
        if self._folder is None:
            return ""
        data = _read(self._folder / f"{endpoint_id}.json") or {}
        value = data.get("key")
        return value if isinstance(value, str) and _KEY.fullmatch(value) else ""

    def _resolve(self, endpoint_id):
        with self._lock:
            if endpoint_id in self._managed:
                return "managed", self._managed[endpoint_id]
        environment = os.environ.get(self.environment_name(endpoint_id), "")
        if environment:
            return "environment", environment
        with self._lock:
            if self._session.get(endpoint_id):
                return "session", self._session[endpoint_id]
        saved = self._saved(endpoint_id)
        return ("saved", saved) if saved else ("", "")

    def get(self, endpoint_id):
        """The key, or "" when none is set (local endpoints usually need none)."""
        _, value = self._resolve(endpoint_id)
        return value if _KEY.fullmatch(value) else ""

    def info(self, endpoint_id):
        source, value = self._resolve(endpoint_id)
        return {"configured": bool(_KEY.fullmatch(value)), "source": source, "can_remember": self._folder is not None,
                "key_env": self.environment_name(endpoint_id)}

    def set(self, endpoint_id, key, remember=False):
        if not isinstance(key, str) or not _KEY.fullmatch(key):
            raise ProjectError("The key must be 16 to 4096 letters, digits or the characters . _ ~ -")
        if remember and self._folder is None:
            raise ProjectError("This service has no private state folder in which to remember the key")
        with self._lock:
            self._session[endpoint_id] = "" if remember else key
            if remember:
                _write_private(self._folder / f"{endpoint_id}.json", {"format": 1, "key": key})
            elif self._folder is not None:
                (self._folder / f"{endpoint_id}.json").unlink(missing_ok=True)
        return self.info(endpoint_id)

    def set_managed(self, endpoint_id, key):
        """The key of a model server STK started (``LocalModels``): in memory only, until the server stops."""
        if not isinstance(key, str) or not _KEY.fullmatch(key):
            raise ProjectError("A managed key must be 16 to 4096 letters, digits or the characters . _ ~ -")
        with self._lock:
            self._managed[endpoint_id] = key

    def clear(self, endpoint_id):
        with self._lock:
            self._managed.pop(endpoint_id, None)
            self._session.pop(endpoint_id, None)
            if self._folder is not None:
                (self._folder / f"{endpoint_id}.json").unlink(missing_ok=True)
        return self.info(endpoint_id)


class ModelPolicy:
    """Which endpoint locations model requests may use: ``offline`` (this computer only), ``organization``
    (this computer and the organization's network) or ``internet`` (all; the default, as before). Independent
    of it, private data never goes to external endpoints (``ModelGateway.admit``)."""

    FILE = "policy.json"

    def __init__(self, state_dir=None):
        self._path = Path(state_dir) / "models" / self.FILE if state_dir else None
        self._memory = "internet"

    def get(self):
        if self._path is None:
            return {"network": self._memory}
        data = _read(self._path) or {}
        network = data.get("network")
        return {"network": network if network in NETWORK_MODES else "internet"}

    def set(self, network):
        if network not in NETWORK_MODES:
            raise ProjectError("The network setting is offline, organization or internet")
        if self._path is None:
            self._memory = network
        else:
            _write_private(self._path, {"format": "stk.model-policy/1", "network": network})
        return self.get()

    def allows(self, location):
        return location in _ALLOWED[self.get()["network"]]
