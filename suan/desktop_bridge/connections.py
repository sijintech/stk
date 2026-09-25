"""Connection profiles owned by the bridge: Runtime profiles, paired hubs and the local Runtime.

Connection ids are opaque to the app:

* ``local``: the Runtime initialized on this computer (``$STK_STATE_DIR``, default ``~/.stk/runtime``);
* ``runtime:<name>``: a saved loopback endpoint (directly or through an SSH tunnel), stored in the
  profiles file the ``suan connect`` CLI uses (``$STK_PROFILES_FILE``, default ``~/.stk/connections.json``);
* ``hub:<name>``: a control hub this bridge paired with as a client device, stored in
  ``<state_dir>/hubs.json``.

Credentials (Runtime tokens, hub device tokens) live only in those private files (mode 0600,
written atomically) and inside this process; nothing returned to the app contains them.
"""
import os
from pathlib import Path
import re
import threading

from suan.runtime.common import atomic_json, read_json

from .backends import HubBackend, RuntimeBackend, make_hub_client, make_runtime_client
from .protocol import BridgeError

__all__ = ["ConnectionStore", "NAME_RE"]

NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def profiles_path():
    return Path(os.environ.get("STK_PROFILES_FILE", str(Path.home() / ".stk" / "connections.json")))


def local_state_dir():
    return os.environ.get("STK_STATE_DIR", str(Path.home() / ".stk" / "runtime"))


def _name(value, what="name"):
    if not isinstance(value, str) or not NAME_RE.match(value):
        raise BridgeError("invalid_params", f"The {what} must be 1-64 of A-Z, a-z, 0-9, '.', '_' or '-'")
    return value


class ConnectionStore:
    def __init__(self, state_dir):
        self.state_dir = Path(state_dir)
        self.hubs_path = self.state_dir / "hubs.json"
        self.lock = threading.RLock()

    # -- listing --------------------------------------------------------------------------------

    def _profiles(self):
        data = read_json(profiles_path(), {})
        return data if isinstance(data, dict) else {}

    def _hubs(self):
        data = read_json(self.hubs_path, {})
        return data if isinstance(data, dict) else {}

    def list(self):
        connections = []
        local = self.local_status(check=False)
        if local["initialized"]:
            connections.append({"id": "local", "kind": "local", "name": "local", "url": local["url"]})
        for name, config in sorted(self._profiles().items()):
            if isinstance(config, dict) and isinstance(config.get("url"), str):
                connections.append({"id": "runtime:" + name, "kind": "runtime", "name": name, "url": config["url"]})
        for name, config in sorted(self._hubs().items()):
            if isinstance(config, dict) and isinstance(config.get("url"), str):
                connections.append({"id": "hub:" + name, "kind": "hub", "name": name, "url": config["url"],
                                    "device_id": config.get("device_id")})
        return connections

    def describe(self, connection_id):
        found = next((c for c in self.list() if c["id"] == connection_id), None)
        if found is None:
            raise BridgeError("not_found", f"Unknown connection {connection_id!r}")
        return found

    # -- local Runtime --------------------------------------------------------------------------

    def local_status(self, check=True):
        state = Path(local_state_dir()).expanduser()
        config = read_json(state / "config.json") if (state / "config.json").is_file() else None
        result = {"initialized": bool(config), "api_running": False, "supervisor_running": False, "url": None,
                  "state_dir": str(state)}
        if not config:
            return result
        if not check:
            api = read_json(state / "api.pid") or {}
            port = api.get("port") or config.get("port")
            result["url"] = f"http://127.0.0.1:{port}" if port else None
            return result
        try:
            from suan.runtime.daemon import status
            result.update(status(state))
        except Exception as exc:  # psutil missing, unreadable pid files, non-Linux server platform
            result["error"] = f"{type(exc).__name__}: {exc}"[:500]
        return result

    def local_start(self):
        from suan.runtime.common import UnsupportedServerPlatform
        from suan.runtime.daemon import start
        try:
            start(local_state_dir())
        except UnsupportedServerPlatform as exc:
            raise BridgeError("unsupported", str(exc)) from None
        except ValueError as exc:
            raise BridgeError("not_found", str(exc)) from None
        except RuntimeError as exc:
            raise BridgeError("remote_error", str(exc)) from None
        return self.local_status()

    # -- changes --------------------------------------------------------------------------------

    def add_runtime(self, name, url, token, check=True):
        _name(name)
        client = make_runtime_client(url, token)
        if check:
            RuntimeBackend("runtime:" + name, client).health()
        with self.lock:
            profiles = self._profiles()
            profiles[name] = {"url": client.url, "token": token}
            atomic_json(profiles_path(), profiles)
        return self.describe("runtime:" + name)

    def pair_hub(self, name, url, code, device_name):
        _name(name)
        hub = make_hub_client(url)
        claimed = HubBackend("hub:" + name, hub, "").call(hub.claim, code, device_name)
        if claimed.get("role") != "client":
            raise BridgeError("invalid_params", "Use a client pairing code (the hub owner creates it with role "
                              "'client')")
        with self.lock:
            hubs = self._hubs()
            hubs[name] = {"url": hub.url, "token": claimed["token"], "device_id": claimed["device_id"]}
            atomic_json(self.hubs_path, hubs)
        return self.describe("hub:" + name)

    def remove(self, connection_id):
        with self.lock:
            kind, _, name = connection_id.partition(":")
            if kind == "runtime":
                profiles = self._profiles()
                if name not in profiles:
                    raise BridgeError("not_found", f"Unknown connection {connection_id!r}")
                del profiles[name]
                atomic_json(profiles_path(), profiles)
            elif kind == "hub":
                hubs = self._hubs()
                if name not in hubs:
                    raise BridgeError("not_found", f"Unknown connection {connection_id!r}")
                del hubs[name]
                atomic_json(self.hubs_path, hubs)
            else:
                raise BridgeError("invalid_params", "Only saved Runtime profiles and paired hubs can be removed")

    # -- clients --------------------------------------------------------------------------------

    def runtime_client(self, connection_id):
        if connection_id == "local":
            from suan.runtime.common import load_config
            status = self.local_status()
            if not status["initialized"]:
                raise BridgeError("not_found", "No local Runtime is initialized on this computer")
            if not status.get("url") or not status.get("api_running"):
                raise BridgeError("unavailable", "The local Runtime API is not running; start it "
                                  "(connections.local_start or 'suan server start')")
            try:
                token = load_config(status["state_dir"])["token"]
            except Exception as exc:
                raise BridgeError("unavailable", f"The local Runtime configuration cannot be read "
                                  f"({type(exc).__name__})") from None
            return make_runtime_client(status["url"], token)
        kind, _, name = connection_id.partition(":")
        if kind != "runtime":
            raise BridgeError("invalid_params", f"{connection_id!r} is not a Runtime connection")
        config = self._profiles().get(name)
        if not isinstance(config, dict):
            raise BridgeError("not_found", f"Unknown connection {connection_id!r}")
        return make_runtime_client(config["url"], config.get("token", ""))

    def hub_client(self, connection_id):
        kind, _, name = connection_id.partition(":")
        config = self._hubs().get(name) if kind == "hub" else None
        if not isinstance(config, dict):
            raise BridgeError("not_found", f"Unknown hub connection {connection_id!r}")
        return make_hub_client(config["url"], config["token"])

    def backend(self, connection_id, node=None):
        """A :class:`RuntimeBackend` or (with ``node``) :class:`HubBackend` for a connection id."""
        if not isinstance(connection_id, str):
            raise BridgeError("invalid_params", "A 'connection' id is required")
        if connection_id.startswith("hub:"):
            if not node:
                raise BridgeError("invalid_params", "Hub connections need 'node': the execution node's device id")
            return HubBackend(connection_id, self.hub_client(connection_id), node)
        return RuntimeBackend(connection_id, self.runtime_client(connection_id))
