"""Explicit owner actions over an existing direct/SSH Runtime connection.

Numeric project rows are frozen in bridge-private storage, never in a project
workspace, Hub blob or public DTO. Durable original intents precede HTTP; a
lost reply is observed by its original operation ID instead of being resent.
"""
from contextlib import contextmanager
import hashlib
import json
import math
from pathlib import Path

from suan.federation import inputs
from suan.materials.jobs import Lease, StorageError, ordinary, private_directory
from suan.project.catalog import _project
from suan.project.store import _version
from suan.project.table_reader import TableReader, batches, placeholders

from .protocol import BridgeError


MAX_REQUEST_BYTES = 4 * 1024 * 1024
MAX_STATE_BYTES = 64 * 1024 * 1024
PLAN_LIMIT = 128
OPERATION_LIMIT = 4096
WRITE_METHODS = frozenset({
    "datasets.register", "grants.approve", "grants.revoke", "evaluations.prepare",
    "evaluations.evaluate", "models.admit", "models.activate", "operations.recover",
})
READ_METHODS = frozenset({
    "info", "operations.get", "datasets.list", "grants.list", "audit.list",
    "candidates.get", "evaluations.get", "models.list",
})


def _keys(value, names):
    if type(value) is not dict or set(value) != set(names):
        raise ValueError("Unexpected federation owner fields")


def _digest(value):
    return hashlib.sha256(inputs.canonical(value)).hexdigest()


def _page(params, maximum=50):
    offset, limit = params["offset"], params["limit"]
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= maximum:
        raise ValueError("Invalid federation owner page")
    return offset, limit


def _ids(value, maximum):
    if type(value) is not list or not 1 <= len(value) <= maximum:
        raise ValueError("Explicit bounded field and row selections are required")
    for identity in value:
        inputs.uuid(identity)
    if len(set(value)) != len(value):
        raise ValueError("Federation selections must not repeat identities")
    return value


def _decode(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate private owner metadata key")
            result[key] = value
        return result

    def constant(_):
        raise ValueError("Nonfinite private owner metadata")

    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant)
    except (UnicodeError, RecursionError, OverflowError):
        raise ValueError("Invalid private owner metadata") from None


class FederationOwner:
    def __init__(self, state_dir, projects, connections):
        # Construction and read-only refresh do not create this directory.
        self.root = Path(state_dir).absolute() / "federation-owner"
        self.projects, self.connections = projects, connections

    @contextmanager
    def _errors(self):
        try:
            yield
        except BridgeError:
            raise
        except FileNotFoundError:
            raise BridgeError("not_found", "Federation owner record not found") from None
        except FileExistsError:
            raise BridgeError("conflict", "Federation owner identity already exists") from None
        except (ValueError, KeyError, TypeError, RecursionError, OverflowError):
            raise BridgeError("invalid_params", "Invalid federation owner request or frozen record") from None
        except (StorageError, OSError):
            raise BridgeError("unavailable", "Private federation owner state is unavailable", retryable=False) from None

    def _path(self, kind, identity):
        return self.root / kind / (inputs.uuid(identity) + ".json")

    def _read(self, kind, identity):
        path = self._path(kind, identity)
        raw = inputs.read_bytes(path, MAX_REQUEST_BYTES + 256 * 1024)
        value = _decode(raw)
        if inputs.canonical(value) != raw:
            raise ValueError("Private owner record is not canonical")
        if kind == "operations":
            self._validate_intent(value, identity)
        elif kind == "plans":
            _keys(value, {"selection", "registration", "card"})
            if value["card"]["plan_id"] != identity or value["selection"]["plan_id"] != identity:
                raise ValueError("Frozen owner plan filename binding changed")
        return value

    @staticmethod
    def _selection(value):
        _keys(value, {"expected_revision", "plan_id", "training_dataset_id", "holdout_dataset_id", "table_id",
                      "feature_ids", "target_ids", "training_rows", "holdout_rows"})
        if type(value["expected_revision"]) is not int or not 0 <= value["expected_revision"] <= 2**53-1:
            raise ValueError("Invalid source revision")
        for key in ("plan_id", "training_dataset_id", "holdout_dataset_id", "table_id"):
            inputs.uuid(value[key])
        fields = _ids(value["feature_ids"], 64) + _ids(value["target_ids"], 16)
        rows = _ids(value["training_rows"], 999) + _ids(value["holdout_rows"], 999)
        if (len(set(fields)) != len(fields) or len(rows) > 1000 or len(set(rows)) != len(rows)
                or value["training_dataset_id"] == value["holdout_dataset_id"]):
            raise ValueError("Training and held-out identities must be distinct")

    @staticmethod
    def _validate_intent(value, identity):
        _keys(value, {"format", "operation_id", "connection", "server_key", "method", "params", "plan_id"})
        if (value["format"] != "stk.federation-owner-intent/1" or value["operation_id"] != identity
                or value["method"] not in WRITE_METHODS or type(value["server_key"]) is not str
                or len(value["server_key"]) != 16 or any(c not in "0123456789abcdef" for c in value["server_key"])
                or type(value["connection"]) is not str
                or not (value["connection"] == "local" or value["connection"].startswith("runtime:"))):
            raise ValueError("Original owner intent binding changed")
        inputs.uuid(identity)
        params = value["params"]
        _keys(params, {"operation_id", "owner_id", "expected_generation", "request"})
        if params["operation_id"] != identity or type(params["request"]) is not dict:
            raise ValueError("Original owner intent identity changed")
        if params["owner_id"] is not None:
            inputs.uuid(params["owner_id"])
        if (type(params["expected_generation"]) is not int or not 0 <= params["expected_generation"] <= 2**53-1
                or len(inputs.canonical(params)) > MAX_REQUEST_BYTES):
            raise ValueError("Original owner intent exceeds its bounds")
        if value["plan_id"] is not None:
            inputs.uuid(value["plan_id"])
        if value["method"] == "datasets.register":
            from suan.federation.owner import _registration
            _registration(params["request"])
        else:
            from .schema import validate_params
            if validate_params("federation.owner." + value["method"], {"connection": value["connection"], **params}):
                raise ValueError("Original owner intent fields changed")

    def _exists(self, kind, identity):
        path = self._path(kind, identity)
        try:
            private_directory(path.parent, create=False)
            ordinary(path)
            return True
        except FileNotFoundError:
            return False

    def _publish(self, kind, identity, value, *, replace=False):
        raw = inputs.canonical(value)
        if len(raw) > MAX_REQUEST_BYTES + 256 * 1024:
            raise ValueError("Private owner record exceeds its byte limit")
        folder = self.root / kind
        private_directory(folder)
        path = self._path(kind, identity)
        existing = self._exists(kind, identity)
        entries = list(folder.glob("*.json"))
        maximum = PLAN_LIMIT if kind == "plans" else OPERATION_LIMIT
        if not existing and len(entries) >= maximum:
            raise BridgeError("busy", "Private owner record quota reached", retryable=False)
        total = len(raw)
        for candidate in self.root.rglob("*.json"):
            private_directory(candidate.parent, create=False)
            size = ordinary(candidate).st_size
            if candidate != path:
                total += size
            if total > MAX_STATE_BYTES:
                raise BridgeError("busy", "Private owner storage quota reached", retryable=False)
        inputs.write_bytes(path, raw, replace=replace)

    def _entries(self, kind):
        folder = self.root / kind
        try:
            private_directory(folder, create=False)
        except FileNotFoundError:
            return
        paths = list(folder.glob("*.json"))
        maximum = PLAN_LIMIT if kind == "plans" else OPERATION_LIMIT
        if len(paths) > maximum:
            raise ValueError("Private owner record count exceeds its bound")
        total = 0
        for path in paths:
            total += ordinary(path).st_size
            if total > MAX_STATE_BYTES:
                raise ValueError("Private owner read exceeds its byte budget")
            inputs.uuid(path.stem)
        # UUID order is deterministic; no private filesystem times leave the bridge.
        for path in sorted(paths):
            yield self._read(kind, path.stem)

    def _plan(self, identity):
        from suan.federation.owner import prepare_registration
        record = self._read("plans", identity)
        _keys(record, {"selection", "registration", "card"})
        registration = record["registration"]
        roles = registration["roles"]
        rebuilt = prepare_registration(registration["source"], *[
            {"dataset_id": roles[role]["manifest"]["dataset_id"],
             "x": roles[role]["x"], "y": roles[role]["y"]}
            for role in ("training", "holdout")
        ])
        if inputs.canonical(rebuilt) != inputs.canonical(registration):
            raise ValueError("Frozen owner registration changed")
        card = self._card(identity, registration)
        if inputs.canonical(card) != inputs.canonical(record["card"]):
            raise ValueError("Frozen owner card changed")
        selection, source = record["selection"], registration["source"]
        self._selection(selection)
        if (selection["plan_id"] != identity or selection["expected_revision"] != source["revision"]
                or selection["table_id"] != source["table_id"]
                or selection["feature_ids"] != [column["field_id"] for column in source["features"]]
                or selection["target_ids"] != [column["field_id"] for column in source["targets"]]
                or any(selection[role+"_rows"] != source[role+"_rows"]
                       or selection[role+"_dataset_id"] != roles[role]["manifest"]["dataset_id"]
                       for role in ("training", "holdout"))):
            raise ValueError("Frozen owner selection changed")
        return record

    @staticmethod
    def _card(identity, registration):
        return {"format": "stk.federation-owner-plan/1", "plan_id": identity,
                "source": registration["source"], "source_sha256": registration["source_sha256"],
                "datasets": [{"role": role, "manifest": registration["roles"][role]["manifest"]}
                             for role in ("training", "holdout")],
                "registration_sha256": _digest(registration),
                "bytes": len(inputs.canonical(registration))}

    def _project(self, handle, expected_revision=None):
        store = self.projects._get(handle)
        info = store.info()
        if expected_revision is not None and (type(expected_revision) is not int or info["revision"] != expected_revision):
            raise BridgeError("conflict", "The project revision changed; prepare a new federation plan")
        return store, info

    def prepare(self, params):
        _keys(params, {"handle", "expected_revision", "plan_id", "training_dataset_id", "holdout_dataset_id",
                       "table_id", "feature_ids", "target_ids", "training_rows", "holdout_rows"})
        identity = inputs.uuid(params["plan_id"])
        _ids(params["feature_ids"], 64)
        _ids(params["target_ids"], 16)
        _ids(params["training_rows"], 999)
        _ids(params["holdout_rows"], 999)
        rows = params["training_rows"] + params["holdout_rows"]
        fields = params["feature_ids"] + params["target_ids"]
        if len(rows) > 1000 or len(set(rows)) != len(rows) or len(set(fields)) != len(fields):
            raise ValueError("Training and held-out identities must be disjoint")
        inputs.uuid(params["table_id"])
        inputs.uuid(params["training_dataset_id"])
        inputs.uuid(params["holdout_dataset_id"])
        if params["training_dataset_id"] == params["holdout_dataset_id"]:
            raise ValueError("Training and held-out datasets need distinct identities")
        selection = {key: value for key, value in params.items() if key != "handle"}
        with self.projects._operation():
            store, info = self._project(params["handle"], params["expected_revision"])
            with Lease(self.root / ".lock"):
                if self._exists("plans", identity):
                    old = self._plan(identity)
                    if (inputs.canonical(old["selection"]) != inputs.canonical(selection)
                            or old["card"]["source"]["project_id"] != info["id"]):
                        raise BridgeError("conflict", "Plan identity is already bound to another selection")
                    return {"plan": old["card"]}
                with store._connect() as db:
                    project = _project(db, params["expected_revision"])
                    if project["id"] != info["id"]:
                        raise BridgeError("conflict", "Project identity changed")
                    reader = TableReader(db, params["table_id"], project["revision"], _version(db))
                    available = {field["id"]: field for field in reader.fields}
                    descriptors = []
                    for field_id in fields:
                        field = available.get(field_id)
                        if field is None or field["type"] not in {"number", "integer"}:
                            raise ValueError("Federation columns must be numeric fields of this table")
                        descriptors.append({"field_id": field_id, "name": field["name"],
                                            "unit": field.get("unit") or "unspecified"})
                    found = set()
                    for group in batches(rows):
                        found.update(row[0] for row in db.execute(
                            "SELECT id FROM records WHERE table_id=? AND id IN (" + placeholders(group) + ")",
                            [params["table_id"], *group]))
                    if found != set(rows):
                        raise ValueError("Federation rows must belong to this table")
                    records = reader.records(rows, set(fields))
                    values = {record["id"]: record["values"] for record in records}
                    for record in records:
                        for field_id in fields:
                            value = record["values"].get(field_id)
                            if type(value) not in (int, float) or not math.isfinite(value):
                                raise ValueError("Federation training requires finite values in every selected cell")
                    source = {"project_id": project["id"], "revision": project["revision"],
                              "table_id": params["table_id"], "features": descriptors[:len(params["feature_ids"])],
                              "targets": descriptors[len(params["feature_ids"]):],
                              "training_rows": params["training_rows"], "holdout_rows": params["holdout_rows"]}
                    from suan.federation.owner import prepare_registration
                    registration = prepare_registration(source, *[
                        {"dataset_id": params[role + "_dataset_id"],
                         "x": [[values[row][field] for field in params["feature_ids"]] for row in params[role + "_rows"]],
                         "y": [[values[row][field] for field in params["target_ids"]] for row in params[role + "_rows"]]}
                        for role in ("training", "holdout")
                    ])
                card = self._card(identity, registration)
                self._publish("plans", identity, {"selection": selection, "registration": registration, "card": card})
                return {"plan": card}

    def get(self, params):
        _keys(params, {"handle", "plan_id"})
        with self.projects._operation():
            _, project = self._project(params["handle"])
            card = self._plan(params["plan_id"])["card"]
            if card["source"]["project_id"] != project["id"]:
                raise BridgeError("not_found", "Federation plan belongs to another project")
            return {"plan": card}

    def plans(self, params):
        _keys(params, {"handle", "offset", "limit"})
        offset, limit = _page(params, 20)
        with self.projects._operation():
            _, project = self._project(params["handle"])
            cards = [self._plan(record["card"]["plan_id"])["card"] for record in self._entries("plans")
                     if record["card"]["source"]["project_id"] == project["id"]]
            selected = cards[offset:offset + limit]
            return {"plans": selected, "offset": offset, "total": len(cards),
                    "next_offset": offset + len(selected) if offset + len(selected) < len(cards) else None}

    def register(self, params):
        _keys(params, {"handle", "expected_revision", "plan_id", "connection", "operation_id",
                       "owner_id", "expected_generation"})
        with self.projects._operation():
            _, project = self._project(params["handle"], params["expected_revision"])
            record = self._plan(params["plan_id"])
            if (record["card"]["source"]["project_id"] != project["id"]
                    or record["card"]["source"]["revision"] != project["revision"]):
                raise BridgeError("conflict", "Project changed after this federation plan was prepared")
            remote = {key: params[key] for key in ("operation_id", "owner_id", "expected_generation")}
            remote["request"] = record["registration"]
            # Keep the accepted source pinned until the original request is journaled/sent.
            return self.owner("datasets.register", {"connection": params["connection"], **remote},
                              plan_id=params["plan_id"])

    def _backend(self, connection):
        if type(connection) is not str or not (connection == "local" or connection.startswith("runtime:")):
            raise BridgeError("invalid_params", "Owner actions require a direct or SSH Runtime connection")
        backend = self.connections.backend(connection)
        if backend.kind != "runtime":
            raise BridgeError("invalid_params", "A Hub pairing does not grant node owner access")
        return backend

    def _observe(self, intent, receipt):
        from suan.federation.owner import validate_owner_result
        validate_owner_result(intent["method"], intent["params"], receipt)
        with Lease(self.root / ".lock"):
            if self._exists("rejections", intent["operation_id"]):
                raise BridgeError("conflict", "Owner outcome conflicts with a retained rejection")
            if self._exists("receipts", intent["operation_id"]):
                retained = self._read("receipts", intent["operation_id"])
                validate_owner_result(intent["method"], intent["params"], retained)
                if any(retained[key] != receipt[key] for key in
                       ("format", "owner_id", "generation", "operation_id", "method", "request_sha256")):
                    raise BridgeError("conflict", "Owner receipt identity changed")
                if retained["state"] == "completed":
                    if receipt["state"] == "completed" and inputs.canonical(receipt) != inputs.canonical(retained):
                        raise BridgeError("conflict", "Completed owner receipt changed")
                    return retained  # A delayed uncertain observation cannot undo completion.
            self._publish("receipts", intent["operation_id"], receipt,
                          replace=self._exists("receipts", intent["operation_id"]))
            return receipt

    def _rejection(self, intent):
        if not self._exists("rejections", intent["operation_id"]):
            return None
        from suan.federation.owner import validate_owner_rejection
        return validate_owner_rejection(intent["method"], intent["params"],
                                        self._read("rejections", intent["operation_id"]))

    def _reject(self, intent, proof):
        from suan.federation.owner import validate_owner_rejection
        proof = validate_owner_rejection(intent["method"], intent["params"], proof)
        with Lease(self.root / ".lock"):
            if self._exists("receipts", intent["operation_id"]):
                raise BridgeError("conflict", "Owner rejection conflicts with an observed reservation")
            retained = self._rejection(intent)
            if retained is not None:
                if inputs.canonical(retained) != inputs.canonical(proof):
                    raise BridgeError("conflict", "Retained owner rejection changed")
            else:
                self._publish("rejections", intent["operation_id"], proof)
        return proof

    @staticmethod
    def _rejected_error(identity, proof):
        return BridgeError("conflict", "The owner rejected this request before reservation; refresh owner state",
                           data={"operation_id": identity, "rejection": proof}, retryable=False)

    def owner(self, method, params, *, plan_id=None):
        if method not in WRITE_METHODS | READ_METHODS:
            raise ValueError("Unsupported federation owner method")
        connection = params["connection"]
        remote = {key: value for key, value in params.items() if key != "connection"}
        backend = self._backend(connection)
        if method == "operations.get":
            inputs.uuid(remote["operation_id"])
            if self._exists("operations", remote["operation_id"]):
                intent = self._read("operations", remote["operation_id"])
                if intent["connection"] != connection or intent["server_key"] != backend.server_key:
                    raise BridgeError("conflict", "The original owner connection changed")
            else:
                intent = None
            receipt = backend.call(backend.client.federation_owner, method, remote)
            if intent is not None and receipt is not None:
                receipt = self._observe(intent, receipt)
            return receipt
        if method not in WRITE_METHODS:
            return backend.call(backend.client.federation_owner, method, remote)
        _keys(remote, {"operation_id", "owner_id", "expected_generation", "request"})
        identity = inputs.uuid(remote["operation_id"])
        if method == "operations.recover":
            target_id = remote["request"]["operation_id"]
            if self._exists("operations", target_id):
                target = self._read("operations", target_id)
                if target["connection"] != connection or target["server_key"] != backend.server_key:
                    raise BridgeError("conflict", "The original owner connection changed")
        if len(inputs.canonical(remote)) > MAX_REQUEST_BYTES:
            raise ValueError("Owner request exceeds its byte limit")
        intent = {"format": "stk.federation-owner-intent/1", "operation_id": identity,
                  "connection": connection, "server_key": backend.server_key, "method": method,
                  "params": remote, "plan_id": plan_id}
        self._validate_intent(intent, identity)
        with Lease(self.root / ".lock"):
            if self._exists("operations", identity):
                original = self._read("operations", identity)
                if inputs.canonical(original) != inputs.canonical(intent):
                    raise BridgeError("conflict", "Owner operation is already bound to another request")
                if self._exists("receipts", identity):
                    from suan.federation.owner import validate_owner_result
                    retained = self._read("receipts", identity)
                    validate_owner_result(method, remote, retained)
                    return retained
                proof = self._rejection(original)
                if proof is not None:
                    raise self._rejected_error(identity, proof)
                raise BridgeError("conflict", "Owner outcome is uncertain; query the original operation ID",
                                  retryable=False)
            self._publish("operations", identity, intent)
        from suan.federation.owner import OwnerRequestRejected
        try:
            receipt = backend.call(backend.client.federation_owner, method, remote)
        except OwnerRequestRejected as exc:
            raise self._rejected_error(identity, self._reject(intent, exc.rejection)) from None
        except BridgeError as exc:
            raise BridgeError(exc.code, "Owner outcome was not confirmed; query the original operation ID",
                              data={"operation_id": identity}, retryable=False) from None
        return self._observe(intent, receipt)

    def operations(self, params):
        _keys(params, {"connection", "offset", "limit"})
        offset, limit = _page(params)
        # No Runtime call: pending local identities remain visible while disconnected.
        connection = params["connection"]
        if type(connection) is not str or not (connection == "local" or connection.startswith("runtime:")):
            raise ValueError("Expected a Runtime connection identity")
        selected, total = [], 0
        for intent in self._entries("operations"):
            if intent["connection"] != connection:
                continue
            position, total = total, total + 1
            if position < offset or len(selected) == limit:
                continue
            identity = intent["operation_id"]
            receipt = self._read("receipts", identity) if self._exists("receipts", identity) else None
            proof = self._rejection(intent)
            if receipt is not None and proof is not None:
                raise BridgeError("conflict", "Retained owner outcomes conflict")
            if receipt is not None:
                from suan.federation.owner import validate_owner_result
                validate_owner_result(intent["method"], intent["params"], receipt)
            selected.append({key: intent[key] for key in ("operation_id", "connection", "server_key", "method", "plan_id")}
                            | {"state": receipt["state"] if receipt else "rejected" if proof else "uncertain",
                               "receipt": receipt, "rejection": proof})
        return {"operations": selected, "offset": offset, "total": total,
                "next_offset": offset + len(selected) if offset + len(selected) < total else None}

    def call(self, action, params):
        with self._errors():
            if action == "prepare":
                return self.prepare(params)
            if action == "get":
                return self.get(params)
            if action == "list":
                return self.plans(params)
            if action == "register":
                return self.register(params)
            if action == "operations.local":
                return self.operations(params)
            if action == "operations.get":
                operation = self.owner(action, params)
                identity = params["operation_id"]
                proof = (self._rejection(self._read("operations", identity))
                         if self._exists("operations", identity) else None)
                return {"operation": operation, "rejection": proof}
            return self.owner(action, params)
