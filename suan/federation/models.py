"""Private linear-model evaluation, admission and explicit version activation.

The owner facade journals the outer request before calling this service. This
module also retains operation identities at its publication boundary so a lost
reply can be recognized without evaluating, publishing or activating again.
Read methods and constructors never create state or start work.
"""
from __future__ import annotations

from contextlib import nullcontext
from copy import deepcopy
from pathlib import Path
import os
import stat

from suan.materials.jobs import Lease, StorageError, private_directory
from . import inputs
from .evaluation import (EvaluationError, candidate, descriptor, digest, fields, heldout, integer,
                         rmse, sha, validate_request, validate_thresholds, version)
from .protocol import model_layout, training_spec_sha256, validate_training_spec
from .updates import decode_arrays

MAX_STORAGE_BYTES = 256 * 1024 * 1024
MAX_EVALUATIONS = 1024
MAX_OPERATIONS = 4096
MAX_VERSIONS = 128
MAX_REGISTRY_OPERATIONS = 512
READ_METHODS = frozenset({"candidates.get", "evaluations.get", "models.list"})
WRITE_METHODS = frozenset({"evaluations.prepare", "evaluations.evaluate", "models.admit", "models.activate"})


class LinearModelRegistry:
    def __init__(self, node_root, coordinator_root=None, *, lookup_dataset=None):
        self.node_root = Path(node_root)
        self.coordinator_root = Path(coordinator_root) if coordinator_root is not None else None
        for path in (self.node_root, self.coordinator_root):
            if path is not None and (not path.is_absolute() or ".." in path.parts):
                raise EvaluationError("The owner must configure absolute private registry roots")
        self.root = self.node_root / "owner" / "linear"
        self.lookup_dataset = lookup_dataset

    @staticmethod
    def validate(method, request):
        return validate_request(method, request)

    def _private(self, *, create=False):
        for parent in (self.root, *self.root.parents):
            marker = parent / "project.sqlite3"
            if marker.exists() or marker.is_symlink():
                raise EvaluationError("Linear model state must be outside shared projects")
        return private_directory(self.root, create=create)

    def _lock(self):
        self._private(create=True)
        return Lease(self.root / "registry.lock", timeout=15)

    def _budget(self, extra):
        total, seen = extra, 0
        for root, directories, files in os.walk(self.root, followlinks=False):
            for name in directories + files:
                path = Path(root) / name
                info = path.lstat()
                seen += 1
                if (seen > 16384 or stat.S_ISLNK(info.st_mode)
                        or getattr(info, "st_file_attributes", 0) & 0x400
                        or not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode))):
                    raise EvaluationError("Invalid private linear registry storage")
                if stat.S_ISREG(info.st_mode):
                    total += info.st_size
                if total > MAX_STORAGE_BYTES:
                    raise EvaluationError("Retained linear model capacity is exhausted")

    def _write(self, path, value, *, replace=False, binary=False):
        raw = value if binary else inputs.canonical(value)
        if not binary and len(raw) > inputs.MAX_METADATA_BYTES:
            raise EvaluationError("Linear registry metadata exceeds its byte budget")
        self._budget(len(raw))
        inputs.write_bytes(path, raw, replace=replace)

    @staticmethod
    def _exists(path):
        return path.exists() or path.is_symlink()

    def _operation_path(self, operation_id):
        return self.root / "operations" / (inputs.uuid(operation_id) + ".json")

    def _operation(self, operation_id):
        path = self._operation_path(operation_id)
        if not self._exists(path):
            return None
        value = inputs.read_json(path)
        fields(value, {"format", "operation_id", "method", "request", "request_sha256", "state", "result"})
        if (value["format"] != "stk.federation-linear-operation/1" or value["operation_id"] != operation_id
                or value["method"] not in WRITE_METHODS or value["state"] not in {"intent", "completed"}
                or digest(value["request"]) != sha(value["request_sha256"])):
            raise EvaluationError("Retained linear operation binding is damaged")
        validate_request(value["method"], value["request"])
        if (value["state"] == "intent") != (value["result"] is None):
            raise EvaluationError("Retained linear operation outcome is damaged")
        return value

    def _finish(self, operation, result):
        operation = {**operation, "state": "completed", "result": deepcopy(result)}
        self._write(self._operation_path(operation["operation_id"]), operation, replace=True)
        return deepcopy(result)

    def read(self, method, request):
        validate_request(method, request)
        try:
            if method == "candidates.get":
                result = candidate(self.coordinator_root, request["run_id"], request["round"])[0]
            elif method == "evaluations.get":
                result = self._card(*self._evaluation(request["evaluation_id"]))
            elif method == "models.list":
                registry = self._registry(request["spec_sha256"])
                for item in registry["versions"]:
                    self._version_model(registry["spec_sha256"], item)
                result = self._registry_card(registry)
            else:
                raise EvaluationError("This linear registry method requires an explicit owner action")
            return validate_result(method, request, result)
        except EvaluationError:
            raise
        except (OSError, StorageError, ValueError, TypeError, KeyError, OverflowError, RecursionError):
            raise EvaluationError("Private linear registry data could not be verified") from None

    def preflight(self, method, request):
        """Check known refusals before the owner reserves a new outer intent.

        This never creates the linear root, an operation or a publication. An
        existing registry uses the same lease as writers. Execution repeats all
        checks: a change after this observation is still an uncertain outcome,
        never retroactively a pre-reservation rejection.
        """
        validate_request(method, request)
        if method not in WRITE_METHODS:
            raise EvaluationError("Unsupported linear registry preflight")
        try:
            try:
                self._private(create=False)
            except FileNotFoundError:
                guard = nullcontext()
            else:
                guard = Lease(self.root / "registry.lock", timeout=15)
            with guard:
                if method == "evaluations.prepare":
                    path = self._evaluation_path(request["evaluation_id"])
                    if self._exists(path):
                        _, state = self._evaluation(request["evaluation_id"])
                        if state["prepare_request_sha256"] != digest(request):
                            raise EvaluationError("Evaluation identity already binds different originals")
                    else:
                        self._preparation_inputs(request)
                elif method == "evaluations.evaluate":
                    plan, state = self._evaluation(request["evaluation_id"])
                    if state["plan_sha256"] != request["plan_sha256"]:
                        raise EvaluationError("Evaluation plan differs from the reviewed immutable identity")
                    if state["state"] == "prepared":
                        self._frozen_models(plan)
                    elif state["state"] not in {"passed", "failed"}:
                        raise EvaluationError("An interrupted evaluation is not automatically repeated")
                elif method == "models.admit":
                    self._admission_inputs(request)
                else:
                    self._activation_inputs(request)
        except EvaluationError:
            raise
        except (OSError, StorageError, ValueError, TypeError, KeyError, OverflowError, RecursionError):
            raise EvaluationError("Linear request cannot be accepted from the current private evidence") from None

    def execute(self, method, request, operation_id):
        validate_request(method, request)
        inputs.uuid(operation_id)
        if method not in WRITE_METHODS:
            raise EvaluationError("Unsupported linear registry write")
        try:
            with self._lock():
                old = self._operation(operation_id)
                if old is not None:
                    if old["method"] != method or old["request_sha256"] != digest(request):
                        raise EvaluationError("Operation identity already binds a different linear request")
                    if old["state"] == "completed":
                        return validate_result(method, request, old["result"])
                    raise EvaluationError("Linear operation outcome is uncertain; inspect the original identity")
                folder = self.root / "operations"
                private_directory(folder)
                if len(list(folder.iterdir())) >= MAX_OPERATIONS:
                    raise EvaluationError("Retained linear operation quota is exhausted")
                operation = {"format": "stk.federation-linear-operation/1", "operation_id": operation_id,
                             "method": method, "request": deepcopy(request), "request_sha256": digest(request),
                             "state": "intent", "result": None}
                self._write(self._operation_path(operation_id), operation)
                if method == "evaluations.prepare":
                    result = self._prepare(request, operation_id)
                elif method == "evaluations.evaluate":
                    result = self._evaluate(request, operation_id)
                elif method == "models.admit":
                    result = self._admit(request, operation_id)
                else:
                    result = self._activate(request, operation_id)
                return self._finish(operation, validate_result(method, request, result))
        except EvaluationError:
            raise
        except (OSError, StorageError, ValueError, TypeError, KeyError, OverflowError, RecursionError):
            raise EvaluationError("Linear operation outcome requires inspection of its original identity") from None

    def recover(self, method, request, operation_id):
        """Recognize only verified postimages; never repeat an interrupted effect."""
        validate_request(method, request)
        try:
            with self._lock():
                operation = self._operation(operation_id)
                if (operation is None or operation["method"] != method
                        or operation["request_sha256"] != digest(request)):
                    raise EvaluationError("No original linear operation matches this recovery")
                if method in {"models.admit", "models.activate"}:
                    if method == "models.admit":
                        plan, _ = self._evaluation(request["evaluation_id"])
                        spec_sha = plan["candidate"]["spec_sha256"]
                    else:
                        spec_sha = request["spec_sha256"]
                    registry = self._registry(spec_sha)
                    receipt = registry["operations"].get(operation_id)
                    if (receipt is None or receipt["method"] != method
                            or receipt["request_sha256"] != digest(request)):
                        raise EvaluationError("Linear publication has no verified original receipt")
                    item = self._find_version(registry, receipt["result"]["version"])
                    self._version_model(spec_sha, item)
                    result = receipt["result"]
                elif method == "evaluations.prepare":
                    plan, state = self._evaluation(request["evaluation_id"])
                    if (state["prepare_operation_id"] != operation_id
                            or state["prepare_request_sha256"] != digest(request)):
                        raise EvaluationError("Evaluation preparation has no verified original receipt")
                    # Its original accepted outcome was prepared, even if a later
                    # explicit evaluation has since added a terminal receipt.
                    original = {**state, "state": "prepared", "metrics": None, "gate": None,
                                "receipt_sha256": None}
                    result = self._card(plan, original)
                elif method == "evaluations.evaluate":
                    plan, state = self._evaluation(request["evaluation_id"])
                    if (state["evaluation_operation_id"] != operation_id
                            or state["state"] not in {"passed", "failed"}
                            or state["plan_sha256"] != request["plan_sha256"]):
                        raise EvaluationError("Evaluation has no verified terminal receipt; it is not replayed")
                    self._frozen_models(plan)
                    result = self._card(plan, state)
                else:
                    raise EvaluationError("Unsupported linear recovery")
                if operation["state"] == "completed" and operation["result"] != result:
                    raise EvaluationError("Retained linear operation receipt conflicts with its postimage")
                return self._finish(operation, validate_result(method, request, result))
        except EvaluationError:
            raise
        except (OSError, StorageError, ValueError, TypeError, KeyError, OverflowError, RecursionError):
            raise EvaluationError("Original linear operation could not be verified; no effect was replayed") from None

    def _registry_path(self, spec_sha):
        return self.root / "models" / sha(spec_sha) / "registry.json"

    def _registry(self, spec_sha):
        path = self._registry_path(spec_sha)
        if not self._exists(path):
            if self._exists(path.parent):
                private_directory(path.parent, create=False)
                if any(path.parent.iterdir()):
                    raise EvaluationError("Linear registry history is missing; do not reset its generation")
            return {"format": "stk.federation-linear-registry/1", "spec_sha256": spec_sha,
                    "active_version": None, "generation": 0, "versions": [], "operations": {}}
        value = inputs.read_json(path)
        fields(value, {"format", "spec_sha256", "active_version", "generation", "versions", "operations"})
        if value["format"] != "stk.federation-linear-registry/1" or value["spec_sha256"] != spec_sha:
            raise EvaluationError("Invalid independent linear model registry")
        version(value["active_version"], nullable=True), integer(value["generation"], 0, 10**9)
        if (type(value["versions"]) is not list or len(value["versions"]) > MAX_VERSIONS
                or type(value["operations"]) is not dict or len(value["operations"]) > MAX_REGISTRY_OPERATIONS):
            raise EvaluationError("Retained linear registry exceeds its limits")
        seen = set()
        for item in value["versions"]:
            fields(item, {"version", "model", "evaluation_id", "evaluation_receipt_sha256", "admission_operation_id"})
            version(item["version"]), inputs.uuid(item["evaluation_id"]), inputs.uuid(item["admission_operation_id"])
            fields(item["model"], {"sha256", "bytes"})
            sha(item["model"]["sha256"]), integer(item["model"]["bytes"], 1, 64 * 1024 * 1024)
            sha(item["evaluation_receipt_sha256"])
            if item["version"] in seen:
                raise EvaluationError("Linear model version identity is duplicated")
            seen.add(item["version"])
        if value["active_version"] is not None and value["active_version"] not in seen:
            raise EvaluationError("The active linear model is not an admitted version")
        if ((value["active_version"] is None and value["generation"] != 0)
                or (value["active_version"] is not None and value["generation"] == 0)):
            raise EvaluationError("Linear model active generation is inconsistent")
        for operation_id, receipt in value["operations"].items():
            inputs.uuid(operation_id)
            fields(receipt, {"method", "request_sha256", "result"})
            if receipt["method"] not in {"models.admit", "models.activate"}:
                raise EvaluationError("Unsupported retained registry receipt")
            sha(receipt["request_sha256"])
            result = receipt["result"]
            expected = ({"format", "operation_id", "spec_sha256", "version", "model", "evaluation_id",
                         "receipt_sha256", "active_generation"} if receipt["method"] == "models.admit" else
                        {"format", "operation_id", "spec_sha256", "version", "generation", "model"})
            fields(result, expected)
            if result["operation_id"] != operation_id or result["spec_sha256"] != spec_sha or result["version"] not in seen:
                raise EvaluationError("Retained registry receipt has a conflicting identity")
            item = next(item for item in value["versions"] if item["version"] == result["version"])
            if result["model"] != item["model"]:
                raise EvaluationError("Retained registry receipt has a conflicting model")
            integer(result.get("generation", result.get("active_generation")),
                    0 if receipt["method"] == "models.admit" else 1, value["generation"])
            if receipt["method"] == "models.admit" and (result["evaluation_id"] != item["evaluation_id"]
                    or result["receipt_sha256"] != item["evaluation_receipt_sha256"]
                    or operation_id != item["admission_operation_id"]):
                raise EvaluationError("Retained admission receipt has a conflicting evaluation")
        return value

    @staticmethod
    def _registry_card(registry):
        return {"format": "stk.federation-linear-models/1", **{key: deepcopy(registry[key]) for key in
                ("spec_sha256", "active_version", "generation", "versions")}}

    @staticmethod
    def _find_version(registry, selected):
        item = next((x for x in registry["versions"] if x["version"] == selected), None)
        if item is None:
            raise EvaluationError("No such admitted linear model version")
        return item

    def _version_model(self, spec_sha, item, spec=None):
        raw = inputs.read_bytes(self._registry_path(spec_sha).parent / item["version"] / "model.bin")
        bundle = decode_arrays(raw, expected_kind="model", expected_layout=model_layout(spec) if spec else None)
        if descriptor(bundle) != item["model"]:
            raise EvaluationError("Admitted linear model bytes differ from their identity")
        if spec is None:
            plan, _ = self._evaluation(item["evaluation_id"])
            spec = plan["candidate"]["spec"]
            decode_arrays(raw, expected_kind="model", expected_layout=model_layout(spec))
        if training_spec_sha256(spec) != spec_sha:
            raise EvaluationError("Admitted linear model has another frozen specification")
        return raw

    @staticmethod
    def _cas(registry, request):
        if (registry["active_version"] != request["expected_active_version"]
                or registry["generation"] != request["expected_active_generation"]):
            raise EvaluationError("Active linear model or generation changed; review a new operation")

    def _evaluation_path(self, evaluation_id):
        return self.root / "evaluations" / inputs.uuid(evaluation_id)

    def _evaluation(self, evaluation_id):
        path = self._evaluation_path(evaluation_id)
        plan, state = inputs.read_json(path / "plan.json"), inputs.read_json(path / "state.json")
        fields(plan, {"format", "evaluation_id", "candidate", "dataset", "active", "thresholds"})
        fields(state, {"format", "evaluation_id", "plan_sha256", "prepare_operation_id", "prepare_request_sha256",
                       "evaluation_operation_id", "state", "metrics", "gate", "receipt_sha256"})
        if (plan["format"] != "stk.federation-evaluation-plan/1" or plan["evaluation_id"] != evaluation_id
                or state["format"] != "stk.federation-evaluation-state/1" or state["evaluation_id"] != evaluation_id
                or state["plan_sha256"] != digest(plan) or state["state"] not in {"prepared", "running", "passed", "failed"}):
            raise EvaluationError("Frozen evaluation identity is damaged")
        inputs.uuid(state["prepare_operation_id"]), sha(state["prepare_request_sha256"])
        card = plan["candidate"]
        fields(card, {"format", "run_id", "round", "spec_sha256", "spec", "model", "base_model",
                      "receipt_sha256", "participants", "num_examples"})
        spec = validate_training_spec(card["spec"])
        if card["format"] != "stk.federation-candidate/1" or card["spec_sha256"] != training_spec_sha256(spec):
            raise EvaluationError("Frozen candidate specification is damaged")
        inputs.uuid(card["run_id"]), integer(card["round"], 1), sha(card["receipt_sha256"])
        validate_thresholds(plan["thresholds"], spec["targets"])
        fields(plan["active"], {"version", "generation", "model"})
        version(plan["active"]["version"], nullable=True), integer(plan["active"]["generation"], 0, 10**9)
        for value in (card["model"], card["base_model"], plan["active"]["model"]):
            if value is not None:
                fields(value, {"sha256", "bytes"})
                sha(value["sha256"]), integer(value["bytes"], 1, 64 * 1024 * 1024)
        if (plan["active"]["version"] is None) != (plan["active"]["model"] is None):
            raise EvaluationError("Frozen baseline identity is damaged")
        if state["state"] in {"prepared", "running"}:
            if any(state[key] is not None for key in ("metrics", "gate", "receipt_sha256")):
                raise EvaluationError("An unevaluated plan cannot carry metrics")
        else:
            inputs.uuid(state["evaluation_operation_id"])
            expected = self._evaluation_receipt(plan, state)
            if state["receipt_sha256"] != digest(expected):
                raise EvaluationError("Frozen evaluation receipt is damaged")
            self._validate_metrics(plan, state)
        return plan, state

    @staticmethod
    def _evaluation_receipt(plan, state):
        return {"format": "stk.federation-evaluation-receipt/1", "evaluation_id": plan["evaluation_id"],
                "plan_sha256": digest(plan), "state": state["state"], "metrics": state["metrics"], "gate": state["gate"]}

    @staticmethod
    def _validate_metrics(plan, state):
        import math
        metrics, gates = state["metrics"], state["gate"]
        targets = plan["candidate"]["spec"]["targets"]
        if metrics is None:
            if state["state"] != "failed" or gates != []:
                raise EvaluationError("Invalid failed evaluation receipt")
            return
        fields(metrics, {"candidate", "base", "baseline"})
        for values in metrics.values():
            if type(values) is not list or len(values) != len(targets):
                raise EvaluationError("Evaluation metrics do not cover the frozen targets")
            for actual, target in zip(values, targets):
                fields(actual, {"name", "unit", "rmse"})
                if ({k: actual[k] for k in ("name", "unit")} != target
                        or type(actual["rmse"]) not in (int, float) or not math.isfinite(actual["rmse"])
                        or actual["rmse"] < 0):
                    raise EvaluationError("Invalid finite per-target evaluation metric")
        expected = LinearModelRegistry._gate(plan, metrics)
        if type(gates) is not list or len(gates) != len(expected):
            raise EvaluationError("Evaluation gate does not cover the frozen targets")
        for gate in gates:
            fields(gate, {"name", "unit", "max_rmse", "absolute_ok", "baseline_ok", "passed"})
            if any(type(gate[key]) is not bool for key in ("absolute_ok", "baseline_ok", "passed")):
                raise EvaluationError("Evaluation gate decisions must be booleans")
        if gates != expected or state["state"] != ("passed" if all(x["passed"] for x in expected) else "failed"):
            raise EvaluationError("Evaluation gate differs from its frozen metrics or thresholds")

    @staticmethod
    def _gate(plan, metrics):
        result = []
        for threshold, measured, baseline in zip(plan["thresholds"], metrics["candidate"], metrics["baseline"]):
            absolute_ok, baseline_ok = measured["rmse"] <= threshold["max_rmse"], measured["rmse"] <= baseline["rmse"]
            result.append({**threshold, "absolute_ok": absolute_ok, "baseline_ok": baseline_ok,
                           "passed": absolute_ok and baseline_ok})
        return result


    @staticmethod
    def _card(plan, state):
        return {"format": "stk.federation-evaluation/1", "evaluation_id": plan["evaluation_id"],
                "state": "uncertain" if state["state"] == "running" else state["state"],
                "plan_sha256": digest(plan), "plan": deepcopy(plan), "metrics": deepcopy(state["metrics"]),
                "gate": deepcopy(state["gate"]), "receipt_sha256": state["receipt_sha256"]}

    def _prepare(self, request, operation_id):
        path = self._evaluation_path(request["evaluation_id"])
        if self._exists(path):
            plan, state = self._evaluation(request["evaluation_id"])
            if state["prepare_request_sha256"] != digest(request):
                raise EvaluationError("Evaluation identity already binds different originals")
            return self._card(plan, state)
        plan, payloads = self._preparation_inputs(request)
        state = {"format": "stk.federation-evaluation-state/1", "evaluation_id": request["evaluation_id"],
                 "plan_sha256": digest(plan), "prepare_operation_id": operation_id, "prepare_request_sha256": digest(request),
                 "evaluation_operation_id": None, "state": "prepared", "metrics": None, "gate": None, "receipt_sha256": None}
        folder = path.parent
        private_directory(folder)
        if len(list(folder.iterdir())) >= MAX_EVALUATIONS:
            raise EvaluationError("Retained evaluation quota is exhausted")
        # All bindings and byte budgets are checked before creating this identity.
        self._budget(sum(len(raw) for raw in payloads.values()) + len(inputs.canonical(plan)) + 2048)
        private_directory(path)
        for name, payload in payloads.items():
            self._write(path / (name + ".bin"), payload, binary=True)
        self._write(path / "plan.json", plan)
        self._write(path / "state.json", state)  # Complete preparation is published last.
        return self._card(plan, state)

    def _preparation_inputs(self, request):
        """Read and verify the complete preparation before publishing anything."""
        card, base_raw, raw = candidate(self.coordinator_root, request["run_id"], request["round"])
        if (card["spec_sha256"] != request["spec_sha256"] or card["model"]["sha256"] != request["candidate_sha256"]
                or card["base_model"]["sha256"] != request["base_model_sha256"]):
            raise EvaluationError("Candidate differs from the owner's reviewed identities")
        dataset, dataset_raw = heldout(self.node_root, request["dataset_id"], self.lookup_dataset, card["spec"])
        if dataset["manifest"]["dataset_sha256"] != request["dataset_sha256"]:
            raise EvaluationError("Held-out data differs from the owner's reviewed identity")
        manifest = inputs.read_json(self.coordinator_root / request["run_id"] / "run.json")["manifest"]
        if any(p["dataset_sha256"] == request["dataset_sha256"] for p in manifest["participants"]):
            raise EvaluationError("An approved training capsule cannot also be the held-out capsule")
        thresholds = validate_thresholds(request["thresholds"], card["spec"]["targets"])
        registry = self._registry(card["spec_sha256"])
        self._cas(registry, request)
        active = registry["active_version"]
        baseline_raw = self._version_model(registry["spec_sha256"], self._find_version(registry, active), card["spec"]) if active else base_raw
        plan = {"format": "stk.federation-evaluation-plan/1", "evaluation_id": request["evaluation_id"],
                "candidate": card, "dataset": dataset,
                "active": {"version": active, "generation": registry["generation"],
                           "model": descriptor(decode_arrays(baseline_raw)) if active else None}, "thresholds": thresholds}
        if len(inputs.canonical(plan)) > inputs.MAX_METADATA_BYTES:
            raise EvaluationError("Frozen evaluation plan exceeds its byte budget")
        return plan, {"candidate": raw, "base": base_raw, "dataset": dataset_raw, "baseline": baseline_raw}

    def _frozen_models(self, plan):
        path = self._evaluation_path(plan["evaluation_id"])
        spec = plan["candidate"]["spec"]
        result = {}
        for name, expected in (("candidate", plan["candidate"]["model"]), ("base", plan["candidate"]["base_model"]),
                               ("baseline", plan["active"]["model"] or plan["candidate"]["base_model"])):
            raw = inputs.read_bytes(path / (name + ".bin"))
            if descriptor(decode_arrays(raw, expected_kind="model", expected_layout=model_layout(spec))) != expected:
                raise EvaluationError("Frozen evaluation model bytes differ from their identities")
            result[name] = raw
        dataset_raw = inputs.read_bytes(path / "dataset.bin")
        dataset = decode_arrays(dataset_raw, expected_kind="model")
        manifest = plan["dataset"]["manifest"]
        if dataset["sha256"] != manifest["data_sha256"] or dataset["bytes"] != manifest["bytes"]:
            raise EvaluationError("Frozen held-out bytes differ from their identity")
        result["dataset"] = dataset_raw
        return result

    def _evaluate(self, request, operation_id):
        plan, state = self._evaluation(request["evaluation_id"])
        if state["plan_sha256"] != request["plan_sha256"]:
            raise EvaluationError("Evaluation plan differs from the reviewed immutable identity")
        if state["state"] in {"passed", "failed"}:
            return self._card(plan, state)
        if state["state"] != "prepared":
            raise EvaluationError("An interrupted evaluation is not automatically repeated")
        payloads = self._frozen_models(plan)
        state.update(state="running", evaluation_operation_id=operation_id)
        state_path = self._evaluation_path(request["evaluation_id"]) / "state.json"
        self._write(state_path, state, replace=True)  # Single-attempt intent before inference.
        try:
            metrics = {name: rmse(plan["candidate"]["spec"], payloads[name], payloads["dataset"])
                       for name in ("candidate", "base", "baseline")}
            gate = self._gate(plan, metrics)
            state.update(state="passed" if all(item["passed"] for item in gate) else "failed", metrics=metrics, gate=gate)
        except EvaluationError:
            state.update(state="failed", metrics=None, gate=[])
        state["receipt_sha256"] = digest(self._evaluation_receipt(plan, state))
        self._write(state_path, state, replace=True)
        return self._card(plan, state)

    def _registry_receipt(self, registry, method, request, operation_id, result):
        if len(registry["operations"]) >= MAX_REGISTRY_OPERATIONS:
            raise EvaluationError("Retained activation receipt quota is exhausted")
        registry["operations"][operation_id] = {"method": method, "request_sha256": digest(request), "result": result}
        if len(inputs.canonical(registry)) > inputs.MAX_METADATA_BYTES:
            raise EvaluationError("Retained linear registry metadata budget is exhausted")

    def _admission_inputs(self, request):
        """Validate the gate and current baseline without publishing a version."""
        plan, state = self._evaluation(request["evaluation_id"])
        if state["state"] != "passed" or state["receipt_sha256"] != request["receipt_sha256"]:
            raise EvaluationError("Only the exact successful held-out receipt permits admission")
        if (request["expected_active_version"] != plan["active"]["version"]
                or request["expected_active_generation"] != plan["active"]["generation"]):
            raise EvaluationError("Admission must retain the evaluation's original active baseline")
        payloads = self._frozen_models(plan)
        spec_sha = plan["candidate"]["spec_sha256"]
        registry = self._registry(spec_sha)
        self._cas(registry, request)
        if registry["active_version"] is not None:
            current = self._version_model(spec_sha, self._find_version(registry, registry["active_version"]),
                                          plan["candidate"]["spec"])
            if descriptor(decode_arrays(current)) != plan["active"]["model"]:
                raise EvaluationError("Current active baseline bytes differ from the frozen evaluation")
        if len(registry["versions"]) >= MAX_VERSIONS:
            raise EvaluationError("Retained linear model version quota is exhausted")
        if any(item["evaluation_id"] == request["evaluation_id"] for item in registry["versions"]):
            raise EvaluationError("This evaluation already admitted a version; use explicit activation")
        return plan, state, payloads, spec_sha, registry

    def _admit(self, request, operation_id):
        plan, state, payloads, spec_sha, registry = self._admission_inputs(request)
        directory = self._registry_path(spec_sha).parent
        private_directory(directory)
        # Keep the initial generation before a version folder can appear. A
        # later missing registry is evidence loss, never a new empty registry.
        if not self._exists(self._registry_path(spec_sha)):
            self._write(self._registry_path(spec_sha), registry)
        allocated = [int(item["version"][1:]) for item in registry["versions"]]
        # Orphan publication folders reserve their version forever.
        for path in directory.iterdir():
            if path.name.startswith("v"):
                version(path.name)
                private_directory(path, create=False)
                allocated.append(int(path.name[1:]))
        selected = "v" + str(max(allocated, default=0) + 1)
        version(selected)
        item = {"version": selected, "model": plan["candidate"]["model"], "evaluation_id": request["evaluation_id"],
                "evaluation_receipt_sha256": state["receipt_sha256"], "admission_operation_id": operation_id}
        registry["versions"].append(item)
        # Admission publishes a retained version only. The separate explicit
        # models.activate operation owns the active pointer and its generation.
        result = {"format": "stk.federation-model-admission/1", "operation_id": operation_id,
                  "spec_sha256": spec_sha, "version": selected, "model": deepcopy(item["model"]),
                  "evaluation_id": request["evaluation_id"], "receipt_sha256": state["receipt_sha256"],
                  "active_generation": registry["generation"]}
        self._registry_receipt(registry, "models.admit", request, operation_id, result)
        self._budget(len(payloads["candidate"]) + len(inputs.canonical(registry)))
        private_directory(directory / selected)
        self._write(directory / selected / "model.bin", payloads["candidate"], binary=True)
        self._write(self._registry_path(spec_sha), registry, replace=self._exists(self._registry_path(spec_sha)))
        return result

    def _activation_inputs(self, request):
        registry = self._registry(request["spec_sha256"])
        self._cas(registry, request)
        item = self._find_version(registry, request["version"])
        self._version_model(registry["spec_sha256"], item)
        return registry, item

    def _activate(self, request, operation_id):
        registry, item = self._activation_inputs(request)
        registry.update(active_version=item["version"], generation=registry["generation"] + 1)
        result = {"format": "stk.federation-model-activation/1", "operation_id": operation_id,
                  "spec_sha256": registry["spec_sha256"], "version": item["version"],
                  "generation": registry["generation"], "model": deepcopy(item["model"])}
        self._registry_receipt(registry, "models.activate", request, operation_id, result)
        self._write(self._registry_path(registry["spec_sha256"]), registry, replace=True)
        return result


def validate_result(method, request, result):
    """Validate owner RPC metadata independently of the writer, without I/O.

    The caller retains ``request``. An operation wrapper separately binds the
    operation UUID and outer CAS; this function validates its closed inner DTO.
    """
    if type(method) is not str or method not in READ_METHODS | WRITE_METHODS:
        raise EvaluationError("Unsupported linear registry result")
    if request is not None:
        validate_request(method, request)
    try:
        if len(inputs.canonical(result)) > 900 * 1024:
            raise EvaluationError("Linear registry response exceeds its byte budget")

        def bundle(value):
            fields(value, {"sha256", "bytes"})
            sha(value["sha256"]), integer(value["bytes"], 1, 64 * 1024 * 1024)

        def model_card(value):
            fields(value, {"format", "run_id", "round", "spec_sha256", "spec", "model", "base_model",
                           "receipt_sha256", "participants", "num_examples"})
            spec = validate_training_spec(value["spec"])
            if value["format"] != "stk.federation-candidate/1" or value["spec_sha256"] != training_spec_sha256(spec):
                raise EvaluationError("Candidate DTO does not bind its frozen specification")
            inputs.uuid(value["run_id"]), integer(value["round"], 1), sha(value["receipt_sha256"])
            bundle(value["model"]), bundle(value["base_model"])
            peers = value["participants"]
            if type(peers) is not list or not 3 <= len(peers) <= 20:
                raise EvaluationError("Candidate DTO needs an approved quorum")
            for peer in peers:
                sha(peer)
            if len(set(peers)) != len(peers):
                raise EvaluationError("Candidate DTO has duplicate participants")
            integer(value["num_examples"], 1, 20 * 10**9)
            return spec

        def dataset(value, spec):
            fields(value, {"role", "manifest", "source_sha256", "source"})
            if value["role"] != "holdout":
                raise EvaluationError("Evaluation DTO must bind the held-out role")
            source = value["source"]
            fields(source, {"project_id", "revision", "table_id", "features", "targets", "training_rows", "holdout_rows"})
            inputs.uuid(source["project_id"]), inputs.uuid(source["table_id"]), integer(source["revision"], 0, 2**53 - 1)
            if sha(value["source_sha256"]) != digest(source):
                raise EvaluationError("Evaluation DTO source plan identity does not match")
            for key in ("features", "targets"):
                if type(source[key]) is not list or len(source[key]) != len(spec[key]):
                    raise EvaluationError("Evaluation DTO column mapping does not match")
                seen = set()
                for column, target in zip(source[key], spec[key]):
                    fields(column, {"field_id", "name", "unit"})
                    inputs.uuid(column["field_id"])
                    if column["field_id"] in seen or {k: column[k] for k in ("name", "unit")} != target:
                        raise EvaluationError("Evaluation DTO ordered columns or units do not match")
                    seen.add(column["field_id"])
            roles = []
            for key in ("training_rows", "holdout_rows"):
                rows = source[key]
                if type(rows) is not list or not 1 <= len(rows) <= 1000:
                    raise EvaluationError("Evaluation DTO source rows exceed their bound")
                for row in rows:
                    inputs.uuid(row)
                if len(set(rows)) != len(rows):
                    raise EvaluationError("Evaluation DTO source row identity is duplicated")
                roles.append(set(rows))
            if roles[0] & roles[1] or len(roles[0]) + len(roles[1]) > 1000:
                raise EvaluationError("Evaluation DTO training and held-out row identities overlap")
            manifest = value["manifest"]
            fields(manifest, {"format", "dataset_id", "dataset_sha256", "data_sha256", "bytes", "num_examples",
                              "feature_names", "target_names"})
            inputs.uuid(manifest["dataset_id"]), sha(manifest["data_sha256"]), sha(manifest["dataset_sha256"])
            integer(manifest["bytes"], 1, 64 * 1024 * 1024)
            integer(manifest["num_examples"], 1, 1000)
            if (manifest["format"] != inputs.FORMAT or manifest["num_examples"] != len(source["holdout_rows"])
                    or manifest["dataset_sha256"] != digest({k: v for k, v in manifest.items() if k != "dataset_sha256"})
                    or manifest["feature_names"] != [c["name"] for c in spec["features"]]
                    or manifest["target_names"] != [c["name"] for c in spec["targets"]]):
                raise EvaluationError("Evaluation DTO held-out capsule identity does not match")

        if method == "candidates.get":
            model_card(result)
            if request is not None and (result["run_id"] != request["run_id"] or result["round"] != request["round"]):
                raise EvaluationError("Candidate DTO belongs to another original request")
        elif method.startswith("evaluations."):
            fields(result, {"format", "evaluation_id", "state", "plan_sha256", "plan", "metrics", "gate", "receipt_sha256"})
            inputs.uuid(result["evaluation_id"])
            if (result["format"] != "stk.federation-evaluation/1"
                    or (request is not None and result["evaluation_id"] != request["evaluation_id"])
                    or type(result["state"]) is not str or result["state"] not in {"prepared", "passed", "failed", "uncertain"}):
                raise EvaluationError("Evaluation DTO belongs to another request or unsupported state")
            plan = result["plan"]
            fields(plan, {"format", "evaluation_id", "candidate", "dataset", "active", "thresholds"})
            if (plan["format"] != "stk.federation-evaluation-plan/1" or plan["evaluation_id"] != result["evaluation_id"]
                    or sha(result["plan_sha256"]) != digest(plan)):
                raise EvaluationError("Evaluation DTO plan identity does not match")
            spec = model_card(plan["candidate"])
            dataset(plan["dataset"], spec)
            fields(plan["active"], {"version", "generation", "model"})
            version(plan["active"]["version"], nullable=True), integer(plan["active"]["generation"], 0, 10**9)
            if (plan["active"]["version"] is None) != (plan["active"]["model"] is None):
                raise EvaluationError("Evaluation DTO baseline identity does not match")
            if plan["active"]["model"] is not None:
                bundle(plan["active"]["model"])
            validate_thresholds(plan["thresholds"], spec["targets"])
            if method == "evaluations.prepare" and request is not None:
                card, manifest, active = plan["candidate"], plan["dataset"]["manifest"], plan["active"]
                for actual, expected in ((card["run_id"], request["run_id"]), (card["round"], request["round"]),
                        (card["spec_sha256"], request["spec_sha256"]), (card["model"]["sha256"], request["candidate_sha256"]),
                        (card["base_model"]["sha256"], request["base_model_sha256"]), (manifest["dataset_id"], request["dataset_id"]),
                        (manifest["dataset_sha256"], request["dataset_sha256"]), (active["version"], request["expected_active_version"]),
                        (active["generation"], request["expected_active_generation"]), (plan["thresholds"], request["thresholds"])):
                    if inputs.canonical(actual) != inputs.canonical(expected):
                        raise EvaluationError("Evaluation DTO differs from the reviewed request")
            elif method == "evaluations.evaluate" and request is not None and result["plan_sha256"] != request["plan_sha256"]:
                raise EvaluationError("Evaluation DTO belongs to another frozen plan")
            if result["state"] in {"prepared", "uncertain"}:
                if any(result[key] is not None for key in ("metrics", "gate", "receipt_sha256")):
                    raise EvaluationError("An unevaluated DTO cannot carry metrics or a receipt")
            else:
                LinearModelRegistry._validate_metrics(plan, result)
                if sha(result["receipt_sha256"]) != digest(LinearModelRegistry._evaluation_receipt(plan, result)):
                    raise EvaluationError("Evaluation DTO receipt does not match its metrics and plan")
        elif method == "models.list":
            fields(result, {"format", "spec_sha256", "active_version", "generation", "versions"})
            sha(result["spec_sha256"])
            if (result["format"] != "stk.federation-linear-models/1"
                    or (request is not None and result["spec_sha256"] != request["spec_sha256"])):
                raise EvaluationError("Model registry DTO belongs to another specification")
            version(result["active_version"], nullable=True), integer(result["generation"], 0, 10**9)
            values = result["versions"]
            if type(values) is not list or len(values) > MAX_VERSIONS:
                raise EvaluationError("Model registry DTO exceeds its retained version bound")
            seen = set()
            for item in values:
                fields(item, {"version", "model", "evaluation_id", "evaluation_receipt_sha256", "admission_operation_id"})
                version(item["version"]), inputs.uuid(item["evaluation_id"]), inputs.uuid(item["admission_operation_id"])
                sha(item["evaluation_receipt_sha256"]), bundle(item["model"])
                if item["version"] in seen:
                    raise EvaluationError("Model registry DTO has duplicate version identities")
                seen.add(item["version"])
            if result["active_version"] is not None and result["active_version"] not in seen:
                raise EvaluationError("Model registry DTO active version is not admitted")
            if ((result["active_version"] is None and result["generation"] != 0)
                    or (result["active_version"] is not None and result["generation"] == 0)):
                raise EvaluationError("Model registry DTO active generation is inconsistent")
        elif method == "models.admit":
            fields(result, {"format", "operation_id", "spec_sha256", "version", "model", "evaluation_id",
                            "receipt_sha256", "active_generation"})
            integer(result["active_generation"], 0, 10**9)
            if (result["format"] != "stk.federation-model-admission/1"
                    or (request is not None and (result["evaluation_id"] != request["evaluation_id"]
                        or result["receipt_sha256"] != request["receipt_sha256"]
                        or result["active_generation"] != request["expected_active_generation"]))):
                raise EvaluationError("Admission DTO differs from the original reviewed evaluation")
            inputs.uuid(result["operation_id"]), inputs.uuid(result["evaluation_id"]), sha(result["spec_sha256"])
            sha(result["receipt_sha256"]), version(result["version"]), bundle(result["model"])
        elif method == "models.activate":
            fields(result, {"format", "operation_id", "spec_sha256", "version", "generation", "model"})
            inputs.uuid(result["operation_id"]), sha(result["spec_sha256"]), version(result["version"])
            integer(result["generation"], 1, 10**9)
            if (result["format"] != "stk.federation-model-activation/1"
                    or (request is not None and (result["spec_sha256"] != request["spec_sha256"]
                        or result["version"] != request["version"]
                        or result["generation"] != request["expected_active_generation"] + 1))):
                raise EvaluationError("Activation DTO differs from the original reviewed version")
            inputs.uuid(result["operation_id"]), bundle(result["model"])
        else:
            raise EvaluationError("Unsupported linear registry result")
        return deepcopy(result)
    except EvaluationError:
        raise
    except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError):
        raise EvaluationError("Invalid closed linear registry response") from None
