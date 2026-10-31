"""Trusted node-owner management, private registration and retained operation IDs.

Only a locally configured Runtime adapter constructs this service. This is not
the Hub's paired-client authority or a sandbox against Runtime-token holders.
Opening, listing and looking up an operation never initialize or recover state.
"""
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
from uuid import uuid4

from suan.materials.jobs import Lease, ordinary, private_directory
from . import inputs
from .protocol import model_layout, training_spec_sha256, validate_training_spec
from .updates import encode_arrays, validate_layout, validate_update

MAX_REQUEST_BYTES = 4 * 1024 * 1024
MAX_OWNER_BYTES = 512 * 1024 * 1024
MAX_OPERATIONS = 4096
MAX_ROWS = 1000
PAGE_BYTES = 1024 * 1024
_APPLICATION_ID = 0x5354464f
READS = frozenset({"info", "operations.get", "datasets.list", "grants.list", "audit.list",
                  "candidates.get", "evaluations.get", "models.list"})
WRITES = frozenset({"datasets.register", "grants.approve", "grants.revoke", "operations.recover",
                   "evaluations.prepare", "evaluations.evaluate", "models.admit", "models.activate"})


class OwnerError(ValueError):
    """A closed, path-free owner failure."""


class OwnerConflict(OwnerError):
    pass


class OwnerRequestRejected(OwnerError):
    """Verified refusal before a new operation identity was reserved.

    This proof says nothing about generic HTTP failures or retained operations.
    A caller must keep the original request and explicitly review fresh owner
    information before choosing another operation identity.
    """
    def __init__(self, rejection):
        self.rejection = deepcopy(rejection)
        super().__init__("Federation owner request was rejected before reservation")


def _fields(value, keys):
    if type(value) is not dict or set(value) != set(keys):
        raise OwnerError("Unexpected federation owner fields")


def _integer(value, low=0, high=2**53-1):
    if type(value) is not int or not low <= value <= high:
        raise OwnerError("Invalid federation owner integer")
    return value


def _sha(value):
    if type(value) is not str or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise OwnerError("Invalid federation owner digest")
    return value


def _text(value, maximum):
    if (type(value) is not str or not value.strip() or len(value.encode("utf-8")) > maximum
            or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        raise OwnerError("Invalid federation owner text")
    return value


def _json(value, maximum=MAX_REQUEST_BYTES):
    raw = inputs.canonical(value)
    if len(raw) > maximum:
        raise OwnerError("Federation owner byte budget exceeded")
    return raw


def validate_owner_rejection(method, original_params, rejection):
    """Validate a closed zero-effect proof against its complete original call."""
    try:
        if type(method) is not str or method not in WRITES:
            raise OwnerError("Rejection is not bound to an owner write")
        _fields(original_params, {"operation_id", "owner_id", "expected_generation", "request"})
        inputs.uuid(original_params["operation_id"])
        if original_params["owner_id"] is not None:
            inputs.uuid(original_params["owner_id"])
        _integer(original_params["expected_generation"])
        if type(original_params["request"]) is not dict:
            raise OwnerError("Invalid original owner request")
        raw = _json(original_params)
        _fields(rejection, {"format", "operation_id", "method", "request_sha256", "owner_id", "generation", "reason"})
        if (rejection["format"] != "stk.federation-owner-rejection/1"
                or rejection["operation_id"] != original_params["operation_id"]
                or rejection["method"] != method
                or rejection["request_sha256"] != hashlib.sha256(raw).hexdigest()
                or rejection["reason"] not in {"stale_owner", "invalid_request"}):
            raise OwnerError("Owner rejection differs from the original request")
        inputs.uuid(rejection["owner_id"])
        _integer(rejection["generation"])
        return deepcopy(rejection)
    except OwnerError:
        raise
    except (ValueError, TypeError, KeyError, UnicodeError, OverflowError, RecursionError):
        raise OwnerError("Invalid federation owner rejection proof") from None


def decode_request(raw, *, object_only=True):
    """Reject duplicates before the ordinary Runtime JSON decoder loses them."""
    if type(raw) is not bytes or len(raw) > MAX_REQUEST_BYTES:
        raise OwnerError("Federation owner request exceeds its byte budget")
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise OwnerError("Duplicate federation owner key")
            result[key] = value
        return result
    def constant(_):
        raise OwnerError("Nonfinite federation owner number")
    def bounded(value, depth=0):
        if depth > 64:
            raise OwnerError("Federation owner nesting limit exceeded")
        if type(value) is float and not math.isfinite(value):
            constant(None)
        if type(value) is dict:
            for k, v in value.items():
                k.encode("utf-8")
                bounded(v, depth+1)
        elif type(value) is list:
            for v in value:
                bounded(v, depth+1)
        elif type(value) is str:
            value.encode("utf-8")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant)
        bounded(value)
        if object_only and type(value) is not dict:
            raise OwnerError("Federation owner request must be an object")
        return value
    except (UnicodeError, RecursionError, OverflowError, json.JSONDecodeError):
        raise OwnerError("Invalid federation owner JSON") from None


def _source(value):
    _fields(value, {"project_id", "revision", "table_id", "features", "targets", "training_rows", "holdout_rows"})
    inputs.uuid(value["project_id"]), inputs.uuid(value["table_id"])
    _integer(value["revision"])
    field_ids = []
    for key, maximum in (("features", 64), ("targets", 16)):
        columns = value[key]
        if type(columns) is not list or not 1 <= len(columns) <= maximum:
            raise OwnerError("Invalid numeric owner column count")
        names = []
        for column in columns:
            _fields(column, {"field_id", "name", "unit"})
            field_ids.append(inputs.uuid(column["field_id"]))
            names.append(_text(column["name"], 128))
            _text(column["unit"], 64)
        if len(set(names)) != len(names):
            raise OwnerError("Numeric owner column names must be distinct")
    if len(set(field_ids)) != len(field_ids):
        raise OwnerError("Numeric owner field identities must be distinct")
    rows = []
    for key in ("training_rows", "holdout_rows"):
        if type(value[key]) is not list or not value[key]:
            raise OwnerError("Training and held-out row identities must be nonempty")
        rows.extend(inputs.uuid(row) for row in value[key])
    if len(rows) > MAX_ROWS or len(set(rows)) != len(rows):
        raise OwnerError("Training and held-out row identities must be distinct and bounded")
    return deepcopy(value)


def _capsule(dataset_id, x, y, source, role):
    dataset_id = inputs.uuid(dataset_id)
    count = len(source[role+"_rows"])
    if (type(x) is not list or type(y) is not list or len(x) != count or len(y) != count
            or any(type(row) is not list for row in x+y)):
        raise OwnerError("Numeric owner matrices must match the bounded selected rows")
    # Project integers retain exact values. The internal capsule is explicitly
    # f64; reject an integer that would silently change during that conversion.
    try:
        if any(type(value) is int and float(value) != value for row in x+y for value in row):
            raise OwnerError("Project integer values must be exactly representable in the numeric capsule")
    except OverflowError:
        raise OwnerError("Numeric owner values exceed the finite capsule range") from None
    arrays = [inputs._matrix(x, 64, "x"), inputs._matrix(y, 16, "y")]
    if (arrays[0]["shape"] != [len(source[role+"_rows"]), len(source["features"])]
            or arrays[1]["shape"] != [len(source[role+"_rows"]), len(source["targets"])]):
        raise OwnerError("Numeric owner matrices differ from the selected rows or columns")
    raw = encode_arrays(arrays, kind="model")
    manifest = {"format": inputs.FORMAT, "dataset_id": dataset_id,
                "data_sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw), "num_examples": len(x),
                "feature_names": [c["name"] for c in source["features"]],
                "target_names": [c["name"] for c in source["targets"]]}
    manifest["dataset_sha256"] = hashlib.sha256(inputs.canonical(manifest)).hexdigest()
    return manifest, raw


def prepare_registration(source, training, holdout):
    """Pure bounded project-row producer. Does not choose a partner file format.

    Each role is exactly ``{dataset_id, x, y}``; the bridge persists the returned
    complete request privately before presenting its metadata for registration.
    """
    source = _source(source)
    roles = {}
    for role, values in (("training", training), ("holdout", holdout)):
        _fields(values, {"dataset_id", "x", "y"})
        manifest, _ = _capsule(values["dataset_id"], values["x"], values["y"], source, role)
        roles[role] = {"manifest": manifest, "x": deepcopy(values["x"]), "y": deepcopy(values["y"])}
    if roles["training"]["manifest"]["dataset_id"] == roles["holdout"]["manifest"]["dataset_id"]:
        raise OwnerError("Training and held-out capsules need distinct identities")
    result = {"format": "stk.federation-registration/1", "source": source,
              "source_sha256": hashlib.sha256(inputs.canonical(source)).hexdigest(), "roles": roles}
    _json(result)
    return result


def _registration(value):
    _fields(value, {"format", "source", "source_sha256", "roles"})
    if value["format"] != "stk.federation-registration/1":
        raise OwnerError("Unsupported federation registration")
    _fields(value["roles"], {"training", "holdout"})
    values = []
    for role in ("training", "holdout"):
        entry = value["roles"][role]
        _fields(entry, {"manifest", "x", "y"})
        if type(entry["manifest"]) is not dict or "dataset_id" not in entry["manifest"]:
            raise OwnerError("Missing federation registration manifest")
        values.append({"dataset_id": entry["manifest"]["dataset_id"], "x": entry["x"], "y": entry["y"]})
    expected = prepare_registration(value["source"], *values)
    if _json(expected) != _json(value):
        raise OwnerError("Federation registration differs from its frozen identities")
    return expected


def _manifest(value):
    _fields(value, {"format", "dataset_id", "data_sha256", "bytes", "num_examples", "feature_names", "target_names", "dataset_sha256"})
    if value["format"] != inputs.FORMAT:
        raise OwnerError("Invalid federation capsule metadata")
    inputs.uuid(value["dataset_id"])
    _sha(value["data_sha256"]), _sha(value["dataset_sha256"])
    _integer(value["bytes"], 1, 64*1024*1024)
    _integer(value["num_examples"], 1, MAX_ROWS)
    for name, maximum in (("feature_names", 64), ("target_names", 16)):
        columns = value[name]
        if type(columns) is not list or not 1 <= len(columns) <= maximum or len(set(columns)) != len(columns):
            raise OwnerError("Invalid federation capsule columns")
        for column in columns:
            _text(column, 128)
    if value["dataset_sha256"] != hashlib.sha256(inputs.canonical({k: v for k, v in value.items() if k != "dataset_sha256"})).hexdigest():
        raise OwnerError("Federation capsule metadata digest differs")


def _dataset_descriptor(value):
    _fields(value, {"role", "manifest", "source", "source_sha256"})
    if value["role"] not in {"training", "holdout"}:
        raise OwnerError("Invalid owner dataset role")
    _source(value["source"])
    _manifest(value["manifest"])
    if (value["source_sha256"] != hashlib.sha256(inputs.canonical(value["source"])).hexdigest()
            or value["manifest"]["num_examples"] != len(value["source"][value["role"]+"_rows"])
            or any(value["manifest"][key+"_names"] != [c["name"] for c in value["source"][other]]
                   for key, other in (("feature", "features"), ("target", "targets")))):
        raise OwnerError("Owner dataset descriptor differs from its source")


def _grant_result(value):
    _fields(value, {"grant_id", "run_id", "coordinator_id", "participant_id", "dataset_id", "dataset_sha256",
                    "spec_sha256", "model_layout", "max_rounds", "active"})
    for key in ("grant_id", "run_id", "dataset_id"):
        inputs.uuid(value[key])
    for key in ("coordinator_id", "participant_id", "dataset_sha256", "spec_sha256"):
        _sha(value[key])
    validate_layout(value["model_layout"])
    _integer(value["max_rounds"], 1, 10000)
    if type(value["active"]) is not bool:
        raise OwnerError("Invalid owner grant state")


def _result(method, request, result, operation_id):
    if method == "datasets.register":
        _fields(result, {"format", "source", "source_sha256", "datasets"})
        if result["format"] != "stk.federation-registration-receipt/1" or type(result["datasets"]) is not list or len(result["datasets"]) != 2:
            raise OwnerError("Invalid owner registration receipt")
        for role, item in zip(("training", "holdout"), result["datasets"]):
            _fields(item, {"role", "manifest"})
            if item["role"] != role:
                raise OwnerError("Owner registration roles changed")
            _dataset_descriptor({**item, "source": result["source"], "source_sha256": result["source_sha256"]})
        if request is not None and (result["source"] != request["source"] or result["source_sha256"] != request["source_sha256"]
                or result["datasets"] != [{"role": role, "manifest": request["roles"][role]["manifest"]} for role in ("training", "holdout")]):
            raise OwnerError("Owner registration receipt differs from the original plan")
    elif method in {"grants.approve", "grants.revoke"}:
        _grant_result(result)
        if method == "grants.approve" and result["grant_id"] != operation_id:
            raise OwnerError("Owner approval receipt belongs to another operation")
        if request is not None:
            if method == "grants.revoke":
                if result["grant_id"] != request["grant_id"] or result["active"] is not False:
                    raise OwnerError("Owner withdrawal receipt differs")
            else:
                expected = {k: request[k] for k in ("run_id", "coordinator_id", "participant_id", "dataset_id", "dataset_sha256", "max_rounds")}
                expected.update(grant_id=operation_id, spec_sha256=training_spec_sha256(request["spec"]), model_layout=model_layout(request["spec"]))
                if any(result[k] != v for k, v in expected.items()):
                    raise OwnerError("Owner approval receipt differs from its original request")
    elif method == "operations.recover":
        _fields(result, {"format", "operation"})
        if result["format"] != "stk.federation-owner-recovery/1":
            raise OwnerError("Invalid owner recovery receipt")
        status = result["operation"]
        _fields(status, {"owner_id", "generation", "operation_id", "method", "request_sha256", "state"})
        inputs.uuid(status["owner_id"]), inputs.uuid(status["operation_id"])
        _integer(status["generation"], 1)
        _sha(status["request_sha256"])
        if status["method"] not in WRITES or status["state"] not in {"completed", "uncertain"}:
            raise OwnerError("Invalid recovered owner operation state")
        if request is not None and result["operation"]["operation_id"] != request["operation_id"]:
            raise OwnerError("Owner recovery returned another operation")
    else:
        from .models import validate_result
        validate_result(method, request, result)
        if method in {"models.admit", "models.activate"} and result["operation_id"] != operation_id:
            raise OwnerError("Linear model result belongs to another owner operation")


def _operation_result(result, method=None, params=None):
    _fields(result, {"format", "owner_id", "generation", "operation_id", "method", "request_sha256", "state", "result"})
    if result["format"] != "stk.federation-owner-operation/1" or result["method"] not in WRITES:
        raise OwnerError("Invalid owner operation receipt")
    inputs.uuid(result["owner_id"]), inputs.uuid(result["operation_id"])
    _integer(result["generation"], 1)
    _sha(result["request_sha256"])
    if result["state"] not in {"completed", "uncertain"} or (result["state"] == "uncertain") != (result["result"] is None):
        raise OwnerError("Invalid owner operation outcome")
    if params is not None and (result["operation_id"] != params["operation_id"] or result["method"] != method
            or result["request_sha256"] != hashlib.sha256(_json(params)).hexdigest()
            or result["generation"] != params["expected_generation"]+1
            or params["owner_id"] is not None and result["owner_id"] != params["owner_id"]):
        raise OwnerError("Owner operation receipt differs from its original request")
    if result["result"] is not None:
        # A recovery/get without the original request can validate the closed
        # result shape; the retained caller journal additionally binds its hash.
        if result["method"].startswith(("evaluations.", "models.")) and params is None:
            from .models import validate_result
            validate_result(result["method"], None, result["result"])
            if result["method"] in {"models.admit", "models.activate"} and result["result"]["operation_id"] != result["operation_id"]:
                raise OwnerError("Linear model result belongs to another owner operation")
        else:
            _result(result["method"], None if params is None else params["request"], result["result"], result["operation_id"])


def _validate_owner_result(method, params, result):
    """Independently validate closed owner responses against the original call."""
    _json(result)
    if method in WRITES:
        _operation_result(result, method, params)
    elif method == "info":
        _fields(result, {"format", "owner_id", "generation", "capabilities"})
        if result["format"] != "stk.federation-owner-info/1":
            raise OwnerError("Invalid owner information")
        if result["owner_id"] is not None:
            inputs.uuid(result["owner_id"])
        elif result["generation"] != 0:
            raise OwnerError("Uninitialized owner has a generation")
        _integer(result["generation"])
        if type(result["capabilities"]) is not list or set(result["capabilities"]) != READS | WRITES or len(result["capabilities"]) != len(READS | WRITES):
            raise OwnerError("Invalid owner capabilities")
    elif method == "operations.get":
        if result is not None:
            _operation_result(result)
            if result["operation_id"] != params["operation_id"]:
                raise OwnerError("Owner lookup returned another operation")
    elif method in {"datasets.list", "grants.list", "audit.list"}:
        _fields(result, {"format", "items", "offset", "total", "next_offset"})
        if (result["format"] != "stk.federation-owner-page/1" or type(result["items"]) is not list
                or result["offset"] != params["offset"] or len(result["items"]) > params["limit"]):
            raise OwnerError("Invalid owner metadata page")
        _integer(result["total"], 0, MAX_OPERATIONS)
        _integer(result["offset"], 0, MAX_OPERATIONS)
        if result["next_offset"] is not None:
            _integer(result["next_offset"], 0, MAX_OPERATIONS)
        expected_next = params["offset"]+len(result["items"])
        if result["next_offset"] != (expected_next if expected_next < result["total"] else None):
            raise OwnerError("Owner pagination identity changed")
        if len(_json(result)) > PAGE_BYTES:
            raise OwnerError("Owner page exceeds its byte budget")
        for item in result["items"]:
            if method == "datasets.list":
                _dataset_descriptor(item)
            elif method == "grants.list":
                _grant_result(item)
            else:
                _fields(item, {"update_id", "grant_id", "round", "model_sha256", "state", "metadata", "layout"})
                inputs.uuid(item["update_id"]), inputs.uuid(item["grant_id"])
                _integer(item["round"], 1, 10000)
                _sha(item["model_sha256"])
                if item["state"] not in {"prepared", "sending", "delivered", "uncertain"}:
                    raise OwnerError("Invalid owner audit state")
                metadata = item["metadata"]
                validate_layout(item["layout"])
                validate_update(metadata, grant_id=item["grant_id"], round=item["round"], model_sha256=item["model_sha256"],
                                **{k: metadata[k] for k in ("run_id", "participant_id", "spec_sha256", "dataset_sha256")})
    else:
        from .models import validate_result
        validate_result(method, params, result)
    return deepcopy(result)


def validate_owner_result(method, params, result):
    """Validate a detached typed result, returning only path-free failures."""
    try:
        return _validate_owner_result(method, params, result)
    except OwnerError:
        raise
    except (ValueError, TypeError, KeyError, UnicodeError, OverflowError, RecursionError):
        raise OwnerError("Invalid federation owner response or original binding") from None


class NodeOwnerService:
    """One trusted Node service, never a caller-selected root or Hub identity."""
    def __init__(self, node, *, coordinator_root=None):
        self.node = node
        self.root = node.root / "owner"
        self.path = self.root / "owner.sqlite3"
        self.coordinator_root = coordinator_root
        self._identity = self._owner_id = self._linear_service = None

    def _directory(self, create=False):
        for parent in (self.root, *self.root.parents):
            marker = parent / "project.sqlite3"
            if marker.exists() or marker.is_symlink():
                raise OwnerError("Federation owner state must be outside shared projects")
        return private_directory(self.root, create=create)

    @contextmanager
    def _connect(self, *, write=False, create=False):
        db = None
        try:
            try:
                self._directory(create)
            except FileNotFoundError:
                yield None
                return
            created = False
            if create:
                try:
                    fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
                    os.close(fd)
                    created = True
                except FileExistsError:
                    pass
            try:
                info = ordinary(self.path)
            except FileNotFoundError:
                yield None
                return
            identity = (info.st_dev, info.st_ino)
            if (self._identity is not None and identity != self._identity
                    or os.name != "nt" and info.st_mode & 0o077):
                raise OwnerError("Federation owner registry identity changed")
            db = sqlite3.connect(self.path.as_uri() + ("?mode=rw" if write else "?mode=ro"), uri=True,
                                 isolation_level=None, timeout=15)
            db.row_factory = sqlite3.Row
            if write:
                db.execute("PRAGMA synchronous=FULL")
            db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            if created:
                db.execute("CREATE TABLE registry (owner_id TEXT NOT NULL,generation INTEGER NOT NULL)")
                db.execute("INSERT INTO registry VALUES (?,0)", (str(uuid4()),))
                db.execute("CREATE TABLE operations (operation_id TEXT PRIMARY KEY,method TEXT NOT NULL,request BLOB NOT NULL,"
                           "request_sha256 TEXT NOT NULL,generation INTEGER NOT NULL,state TEXT NOT NULL,result BLOB)")
                db.execute("CREATE TABLE datasets (dataset_id TEXT PRIMARY KEY,descriptor BLOB NOT NULL,sha256 TEXT NOT NULL)")
                db.execute(f"PRAGMA application_id={_APPLICATION_ID}")
                db.execute("PRAGMA user_version=1")
            if (db.execute("PRAGMA application_id").fetchone()[0] != _APPLICATION_ID
                    or db.execute("PRAGMA user_version").fetchone()[0] != 1):
                raise OwnerError("Unsupported federation owner registry")
            rows = db.execute("SELECT owner_id,generation FROM registry LIMIT 2").fetchall()
            if len(rows) != 1:
                raise OwnerError("Invalid federation owner registry")
            owner_id = inputs.uuid(rows[0]["owner_id"])
            _integer(rows[0]["generation"])
            if self._owner_id is not None and self._owner_id != owner_id:
                raise OwnerError("Federation owner registry was replaced")
            self._identity, self._owner_id = identity, owner_id
            yield db
            if (ordinary(self.path).st_dev, ordinary(self.path).st_ino) != identity:
                raise OwnerError("Federation owner registry changed during operation")
            db.commit()
        except (sqlite3.Error, OSError) as exc:
            raise OwnerError("Federation owner storage is unavailable") from None
        finally:
            if db is not None:
                if db.in_transaction:
                    db.rollback()
                db.close()

    def _linear(self):
        if self._linear_service is None:
            from .models import LinearModelRegistry
            self._linear_service = LinearModelRegistry(self.node.root, self.coordinator_root,
                                                       lookup_dataset=self.dataset)
        return self._linear_service

    def info(self):
        with self._connect() as db:
            row = None if db is None else db.execute("SELECT owner_id,generation FROM registry").fetchone()
        return {"format": "stk.federation-owner-info/1", "owner_id": None if row is None else row[0],
                "generation": 0 if row is None else row[1], "capabilities": sorted(READS | WRITES)}

    @staticmethod
    def _quota(db, extra):
        used = db.execute("SELECT coalesce(sum(length(request)+coalesce(length(result),0)),0) FROM operations").fetchone()[0]
        used += db.execute("SELECT coalesce(sum(length(descriptor)),0) FROM datasets").fetchone()[0]
        if used + extra > MAX_OWNER_BYTES:
            raise OwnerError("Federation owner retention budget is exhausted")

    def _operation(self, db, operation_id):
        if db is None:
            return None
        row = db.execute("SELECT operation_id,method,request_sha256,generation,state,length(request) AS size,"
                         "length(result) AS result_size,CASE WHEN length(request)<=? THEN request END AS request,"
                         "CASE WHEN length(result)<=? THEN result END AS result FROM operations WHERE operation_id=?",
                         (MAX_REQUEST_BYTES, PAGE_BYTES,
                          inputs.uuid(operation_id))).fetchone()
        if row is None:
            return None
        if (row["size"] > MAX_REQUEST_BYTES or (row["result_size"] or 0) > PAGE_BYTES
                or row["method"] not in WRITES or row["state"] not in {"completed", "uncertain"}
                or hashlib.sha256(row["request"]).hexdigest() != row["request_sha256"]):
            raise OwnerError("Retained federation owner operation is damaged")
        request = decode_request(row["request"])
        result = None if row["result"] is None else decode_request(row["result"])
        inputs.uuid(request["operation_id"])
        _integer(row["generation"], 1)
        result = {"format": "stk.federation-owner-operation/1", "owner_id": self._owner_id,
                "generation": row["generation"], "operation_id": row["operation_id"], "method": row["method"],
                "request_sha256": row["request_sha256"], "state": row["state"], "result": result}
        _operation_result(result, row["method"], request)
        return result

    def operation(self, operation_id):
        with self._connect() as db:
            return self._operation(db, inputs.uuid(operation_id))

    def dataset(self, dataset_id):
        with self._connect() as db:
            row = None if db is None else db.execute("SELECT CASE WHEN length(descriptor)<=? THEN descriptor END,sha256 "
                                                    "FROM datasets WHERE dataset_id=?",
                                                    (inputs.MAX_METADATA_BYTES, inputs.uuid(dataset_id))).fetchone()
            if row is None:
                raise OwnerError("No such owner-registered dataset")
            if row[0] is None or hashlib.sha256(row[0]).hexdigest() != row[1]:
                raise OwnerError("Retained dataset descriptor is damaged")
            descriptor = decode_request(row[0])
            _dataset_descriptor(descriptor)
            return descriptor

    def _validate(self, method, request):
        if method == "datasets.register":
            _registration(request)
        elif method == "grants.approve":
            _fields(request, {"dataset_id", "dataset_sha256", "source_sha256", "spec", "run_id",
                              "coordinator_id", "participant_id", "max_rounds"})
            for key in ("dataset_id", "run_id"):
                inputs.uuid(request[key])
            for key in ("dataset_sha256", "source_sha256", "coordinator_id", "participant_id"):
                _sha(request[key])
            _integer(request["max_rounds"], 1, 10000)
            spec = validate_training_spec(request["spec"])
            item = self.dataset(request["dataset_id"])
            if (item["role"] != "training" or item["manifest"]["dataset_sha256"] != request["dataset_sha256"]
                    or item["source_sha256"] != request["source_sha256"] or any(
                        spec[key] != [{"name": c["name"], "unit": c["unit"]} for c in item["source"][key]]
                        for key in ("features", "targets"))):
                raise OwnerError("Owner approval differs from the registered training columns or source")
        elif method in {"grants.revoke", "operations.recover"}:
            key = "grant_id" if method == "grants.revoke" else "operation_id"
            _fields(request, {key})
            inputs.uuid(request[key])
        else:
            self._linear().preflight(method, request)

    def call(self, method, params):
        """Closed local owner RPC. Identical writes return, never rerun, originals."""
        if type(method) is not str or method not in READS | WRITES:
            raise OwnerError("Unsupported federation owner method")
        _json(params)
        if method in READS:
            if method == "info":
                _fields(params, set())
                return self.info()
            if method == "operations.get":
                _fields(params, {"operation_id"})
                return self.operation(params["operation_id"])
            if method.endswith(".list") and method != "models.list":
                _fields(params, {"offset", "limit"})
                _integer(params["offset"], 0, MAX_OPERATIONS)
                _integer(params["limit"], 1, 100)
                return self._page(method, params)
            self._linear().validate(method, params)
            return self._linear().read(method, params)
        _fields(params, {"operation_id", "owner_id", "expected_generation", "request"})
        operation_id = inputs.uuid(params["operation_id"])
        if params["owner_id"] is not None:
            inputs.uuid(params["owner_id"])
        _integer(params["expected_generation"])
        raw = _json(params)
        digest = hashlib.sha256(raw).hexdigest()
        self._directory(True)
        with Lease(self.root / "owner.lock", timeout=15):
            rejection = None
            with self._connect(write=True, create=True) as db:
                old = self._operation(db, operation_id)
                if old is not None:
                    if old["request_sha256"] != digest or old["method"] != method:
                        raise OwnerConflict("Owner operation identity already binds another request")
                    return old
                registry = db.execute("SELECT owner_id,generation FROM registry").fetchone()
                initial = registry[1] == 0 and params["owner_id"] is None
                if (not initial and params["owner_id"] != registry[0]
                        or params["expected_generation"] != registry[1]):
                    reason = "stale_owner"
                else:
                    reason = None
                    try:
                        # Old identity lookup precedes semantic validation. Only
                        # this known read-only validation boundary can certify a
                        # refusal: no INSERT, dataset/grant or model effect ran.
                        self._validate(method, params["request"])
                    except (ValueError, TypeError, KeyError, UnicodeError, OverflowError, RecursionError):
                        reason = "invalid_request"
                if reason is not None:
                    rejection = validate_owner_rejection(method, params, {
                        "format": "stk.federation-owner-rejection/1", "operation_id": operation_id,
                        "method": method, "request_sha256": digest, "owner_id": registry[0],
                        "generation": registry[1], "reason": reason})
                else:
                    if db.execute("SELECT count(*) FROM operations").fetchone()[0] >= MAX_OPERATIONS:
                        raise OwnerError("Retained owner operation capacity is exhausted")
                    self._quota(db, len(raw))
                    generation = registry[1]+1
                    db.execute("INSERT INTO operations VALUES (?,?,?,?,?,'uncertain',NULL)",
                               (operation_id, method, raw, digest, generation))
                    db.execute("UPDATE registry SET generation=?", (generation,))
            # Initial private metadata is committed so a rejection's owner UUID
            # remains observable, but its operation ID was never reserved.
            if rejection is not None:
                raise OwnerRequestRejected(rejection)
            # Intent + original request + CAS are FULL committed before side effects.
            try:
                result = self._execute(method, params["request"], operation_id)
                _result(method, params["request"], result, operation_id)
                self._complete(operation_id, result)
            except Exception:
                # Neither an exception nor a lost reply proves absence of a side effect.
                # Reads never enter recovery; the original identity stays retained.
                pass
            return self.operation(operation_id)

    def _complete(self, operation_id, result):
        raw = _json(result, PAGE_BYTES)
        with self._connect(write=True) as db:
            self._quota(db, len(raw))
            db.execute("UPDATE operations SET state='completed',result=? WHERE operation_id=?", (raw, operation_id))

    def _execute(self, method, request, operation_id):
        if method == "datasets.register":
            return self._register(request)
        if method == "grants.approve":
            return self.node.approve(request["spec"], request["dataset_id"], grant_id=operation_id,
                                     **{k: request[k] for k in ("run_id", "coordinator_id", "participant_id", "max_rounds")}).as_dict()
        if method == "grants.revoke":
            return self.node.consent.revoke(request["grant_id"]).as_dict()
        if method == "operations.recover":
            return self._recover(request["operation_id"])
        return self._linear().execute(method, request, operation_id)

    def _register(self, request):
        request = _registration(request)
        self.node._setup()
        descriptors = []
        # The same node lease as Runtime training and all capsule writers enforces
        # the existing 512MiB raw-bin quota under concurrent owner requests.
        with Lease(self.node.root / "node.lock", timeout=15):
            for role in ("training", "holdout"):
                entry = request["roles"][role]
                manifest, raw = _capsule(entry["manifest"]["dataset_id"], entry["x"], entry["y"], request["source"], role)
                target = self.node.root / "datasets" / manifest["dataset_id"]
                if target.exists() or target.is_symlink():
                    private_directory(target, create=False)
                    names = {p.name for p in target.iterdir()}
                    if not names <= {"manifest.json", "data.bin"}:
                        raise OwnerError("Incomplete numeric capsule contains unexpected files")
                    if "manifest.json" in names:
                        old, old_raw = inputs.load(target)
                        if old != manifest or old_raw != raw:
                            raise OwnerConflict("Dataset identity already binds different frozen values")
                    elif "data.bin" in names and inputs.read_bytes(target / "data.bin") != raw:
                        raise OwnerConflict("Incomplete numeric capsule differs from its original plan")
                else:
                    if len(list(target.parent.iterdir())) >= 1024:
                        raise OwnerError("Numeric capsule capacity is exhausted")
                    private_directory(target)
                if not (target / "data.bin").exists():
                    inputs.check_budget(self.node.root, len(raw))
                    inputs.write_bytes(target / "data.bin", raw)
                if not (target / "manifest.json").exists():
                    inputs.write_json(target / "manifest.json", manifest)
                inputs.load(target)
                descriptors.append({"role": role, "manifest": manifest, "source": request["source"],
                                    "source_sha256": request["source_sha256"]})
        with self._connect(write=True) as db:
            for descriptor in descriptors:
                raw = _json(descriptor, inputs.MAX_METADATA_BYTES)
                dataset_id = descriptor["manifest"]["dataset_id"]
                old = db.execute("SELECT CASE WHEN length(descriptor)<=? THEN descriptor END FROM datasets WHERE dataset_id=?",
                                 (inputs.MAX_METADATA_BYTES, dataset_id)).fetchone()
                if old is not None:
                    if old[0] is None:
                        raise OwnerError("Retained dataset descriptor exceeds its byte budget")
                    if old[0] != raw:
                        raise OwnerConflict("Dataset source identity already binds another registration")
                else:
                    self._quota(db, len(raw))
                    db.execute("INSERT INTO datasets VALUES (?,?,?)", (dataset_id, raw, hashlib.sha256(raw).hexdigest()))
        return {"format": "stk.federation-registration-receipt/1", "source": request["source"],
                "source_sha256": request["source_sha256"],
                "datasets": [{"role": d["role"], "manifest": d["manifest"]} for d in descriptors]}

    def _recover(self, operation_id):
        with self._connect() as db:
            original = self._operation(db, operation_id)
            row = None if original is None else db.execute("SELECT request FROM operations WHERE operation_id=?", (operation_id,)).fetchone()
        if original is None:
            raise OwnerError("No such retained owner operation")
        if original["state"] != "completed":
            method, request = original["method"], decode_request(row[0])["request"]
            if method == "datasets.register":
                result = self._register(request)  # exact plan: verify bytes and fill only missing publications
            elif method in {"grants.approve", "grants.revoke"}:
                grant_id = operation_id if method == "grants.approve" else request["grant_id"]
                grant = self.node.consent.get_grant(grant_id)
                if grant is None or method == "grants.revoke" and grant.active:
                    result = None  # cannot infer an uncommitted approval/revocation occurred
                elif method == "grants.approve":
                    expected = {"grant_id": operation_id, "run_id": request["run_id"],
                                "coordinator_id": request["coordinator_id"], "participant_id": request["participant_id"],
                                "dataset_id": request["dataset_id"], "dataset_sha256": request["dataset_sha256"],
                                "spec_sha256": training_spec_sha256(request["spec"]),
                                "model_layout": model_layout(request["spec"]), "max_rounds": request["max_rounds"]}
                    actual = grant.as_dict()
                    if any(actual[k] != v for k, v in expected.items()):
                        raise OwnerConflict("Retained owner approval differs from its original request")
                    result = actual
                else:
                    result = grant.as_dict()
            elif method == "operations.recover":
                result = None  # recovery intent itself is never recursively replayed
            else:
                result = self._linear().recover(method, request, operation_id)
            if result is not None:
                self._complete(operation_id, result)
                original = self.operation(operation_id)
        return {"format": "stk.federation-owner-recovery/1",
                "operation": {k: original[k] for k in ("owner_id", "generation", "operation_id", "method", "request_sha256", "state")}}

    def _page(self, method, params):
        if method == "datasets.list":
            with self._connect() as db:
                total = 0 if db is None else db.execute("SELECT count(*) FROM datasets").fetchone()[0]
                _integer(total, 0, 1024)
                ids = [] if db is None else [r[0] for r in db.execute("SELECT dataset_id FROM datasets ORDER BY rowid LIMIT ? OFFSET ?",
                                                                     (params["limit"], params["offset"]))]
            items, used = [], 0
            for dataset_id in ids:
                descriptor = self.dataset(dataset_id)
                size = len(_json(descriptor))
                if used+size+1024 > PAGE_BYTES:
                    break
                items.append(descriptor)
                used += size
            offset = params["offset"]+len(items)
        else:
            key = "grants" if method == "grants.list" else "updates"
            page = (self.node.consent.list_grants if key == "grants" else self.node.consent.list_updates)(**params)
            total, items, offset = page["total"], [item.as_dict() for item in page[key]], page["next_offset"]
            offset = total if offset is None else offset
        return {"format": "stk.federation-owner-page/1", "items": items, "offset": params["offset"],
                "total": total, "next_offset": offset if offset < total else None}
