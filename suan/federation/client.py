"""Bounded, explicit federation requests to one already paired Hub origin.

No redirects, environment proxies, credential persistence or automatic retry.
The transport may be injected for local HTTP acceptance; it returns status and
bounded bytes, never arbitrary URLs. Authentication is Hub bearer authentication,
not a new public-key proof protocol.
"""
import hashlib
import json
import math
import re
from urllib.error import HTTPError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
from uuid import UUID

from .protocol import canonical_json, validate_message, validate_node_result
from .updates import MAX_BUNDLE_BYTES, decode_arrays, validate_update


class FederationTransportError(RuntimeError):
    pass


def _identity(value, *, uuid=False):
    if type(value) is not str:
        raise ValueError("Invalid federation route identity")
    if uuid:
        try:
            valid = str(UUID(value)) == value
        except ValueError:
            valid = False
    else:
        valid = bool(re.fullmatch(r"[a-f0-9]{32}", value))
    if not valid:
        raise ValueError("Invalid federation route identity")
    return value


def _round_path(run_id, round):
    if type(round) is not int or not 1 <= round <= 10000:
        raise ValueError("Invalid federation round")
    return f"/api/v1/federation/runs/{_identity(run_id, uuid=True)}/rounds/{round}"


def _json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError
            result[key] = value
        return result
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, UnicodeError, RecursionError):
        raise FederationTransportError("Invalid federation response") from None


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise FederationTransportError("Federation redirects are not allowed")


class FederationClient:
    def __init__(self, origin, token, *, timeout=30, transport=None):
        p = urlsplit(origin)
        if (p.username or p.password or p.query or p.fragment or p.path not in ("", "/")
                or p.scheme not in ("http", "https") or not p.hostname
                or (p.scheme == "http" and p.hostname not in ("127.0.0.1", "localhost", "::1"))):
            raise ValueError("Use a paired HTTPS Hub origin, or loopback HTTP")
        if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 300:
            raise ValueError("Invalid federation transport timeout")
        self.origin = urlunsplit((p.scheme, p.netloc, "", "", ""))
        self._token, self.timeout, self._transport = token, timeout, transport

    def _request(self, method, path, body=None, *, maximum=128*1024):
        headers = {"Authorization": "Bearer " + self._token, "Cache-Control": "no-store"}
        if body is not None:
            headers.update({"Content-Type": "application/octet-stream" if method == "PUT" else "application/json",
                            "Content-Length": str(len(body))})
        try:
            if self._transport is not None:
                status, raw = self._transport(method, path, body, headers, maximum)
            else:
                opener = build_opener(ProxyHandler({}), _NoRedirect())
                request = Request(self.origin + path, data=body, headers=headers, method=method)
                try:
                    response = opener.open(request, timeout=self.timeout)
                except HTTPError as exc:
                    response = exc
                with response:
                    status, raw = response.code, response.read(maximum+1)
            if type(raw) is not bytes or len(raw) > maximum:
                raise FederationTransportError("Federation response exceeds its byte limit")
            if status != 200:
                raise FederationTransportError(f"Federation Hub answered HTTP {status}")
            return raw
        except FederationTransportError:
            raise
        except Exception:
            # Network errors may contain headers, bearer values and private URLs.
            raise FederationTransportError("Federation request outcome is unknown") from None

    def run(self, run_id):
        return _json(self._request("GET", "/api/v1/federation/runs/" + _identity(run_id, uuid=True)))

    def upload_model(self, run_id, round, raw):
        data = decode_arrays(raw, expected_kind="model")
        return self._upload(_round_path(run_id, round) + "/model/" + data["sha256"], raw,
                            {"run_id":run_id,"round":round,"kind":"model","participant_id":"","update_id":"",
                             "sha256":data["sha256"],"bytes":len(raw)})

    def _upload(self, path, raw, expected):
        actual = _json(self._request("PUT", path, raw))
        # Canonical JSON distinguishes bool/int in acknowledgements.
        if canonical_json(actual) != canonical_json(expected):
            raise FederationTransportError("Federation upload receipt does not match its original bytes")
        return actual

    def fetch_model(self, message):
        request = validate_message(message)
        data = self._request("GET", _round_path(request["run_id"], request["round"]) +
                             "/model/" + request["model"]["sha256"], maximum=request["model"]["bytes"])
        self._bytes(data, request["model"]["sha256"], request["model"]["bytes"])
        decode_arrays(data, expected_kind="model")
        return data

    @staticmethod
    def _bytes(raw, sha256, size):
        if type(raw) is not bytes or len(raw) != size or hashlib.sha256(raw).hexdigest() != sha256:
            raise FederationTransportError("Federation bytes do not match the trusted descriptor")

    def publish_update(self, message, update_id, metadata, raw):
        request = validate_message(message)
        metadata = validate_update(metadata, **{k:request[k] for k in
            ("run_id","round","participant_id","spec_sha256","dataset_sha256","grant_id")},
            model_sha256=request["model"]["sha256"])
        self._bytes(raw, metadata["update_sha256"], metadata["update_bytes"])
        decode_arrays(raw, expected_kind="delta")
        expected = {"run_id":request["run_id"],"round":request["round"],"kind":"update",
                    "participant_id":request["participant_id"],"update_id":_identity(update_id,uuid=True),
                    "sha256":metadata["update_sha256"],"bytes":metadata["update_bytes"]}
        path = (_round_path(request["run_id"],request["round"]) + "/updates/" + request["participant_id"] +
                "/" + update_id + "/" + metadata["update_sha256"])
        return self._upload(path,raw,expected)

    def fetch_update(self, message, result):
        result = validate_node_result(result,message=message)
        metadata = result["update"]
        if metadata is None:
            raise FederationTransportError("Only a delivered collect receipt identifies an update")
        path = (_round_path(metadata["run_id"],metadata["round"]) + "/updates/" + metadata["participant_id"] +
                "/" + result["update_id"] + "/" + metadata["update_sha256"])
        raw = self._request("GET",path,maximum=metadata["update_bytes"])
        self._bytes(raw,metadata["update_sha256"],metadata["update_bytes"])
        decode_arrays(raw,expected_kind="delta")
        return raw

    def submit(self, node_id, message, action_id):
        request = {"id":_identity(action_id),"node_id":_identity(node_id),"kind":"fl.message",
                   "payload":validate_message(message)}
        result = _json(self._request("POST","/api/v1/actions",canonical_json(request)))
        if type(result) is not dict or result.get("id") != action_id or result.get("request") != request:
            raise FederationTransportError("Federation action receipt has a different original request")
        return result

    def action(self, action_id, *, node_id, message):
        result = _json(self._request("GET","/api/v1/actions/"+_identity(action_id)))
        expected = {"id":action_id,"node_id":_identity(node_id),"kind":"fl.message","payload":validate_message(message)}
        if type(result) is not dict or result.get("id") != action_id or result.get("request") != expected:
            raise FederationTransportError("Federation action does not match its retained request")
        if result.get("state") == "succeeded":
            result["result"] = validate_node_result(result.get("result"),message=message)
        return result
