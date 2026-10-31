"""Node-owned fixed training dispatch; all numeric files stay in private state.

Only trusted local owner code calls register_dataset/approve. Authenticated STK
transport calls execute; asserted message identities alone are not authentication.
Runtime remains the execution authority and is not a multi-user sandbox.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path
import re

from suan.materials.jobs import Lease, private_directory
from suan.runtime.models import TaskSpec
from . import inputs
from .consent import ConsentRegistry, ConsentOutcomeUncertain
from .protocol import model_layout, training_spec_sha256, validate_message, validate_node_result, validate_training_spec
from .updates import decode_arrays, validate_update

STATES = frozenset({"prepared", "queued", "running", "ready", "delivered", "failed", "cancelled", "unknown", "uncertain"})
_TASK = re.compile(r"[0-9a-f]{32}\Z")


class NodeFederationError(ValueError):
    """A safe, path-free node failure; callers retain their original identity."""


class NodeFederationService:
    def __init__(self, runtime, root, python, *, workspace_root=None):
        self.runtime = runtime
        self.root = Path(root).absolute()
        self.python = str(python) if python else None
        if (self.python is not None and (not Path(self.python).is_absolute() or "\0" in self.python)) or ".." in self.root.parts:
            raise ValueError("The owner must select absolute private state and interpreter paths")
        self.consent = ConsentRegistry(self.root / "consent")
        self.registry = self.consent
        # RuntimeService can disclose its managed root locally; never nest raw
        # data under a workspace where the generic file routes could reach it.
        config = getattr(runtime, "config", None)
        if workspace_root is None and isinstance(config, dict):
            workspace_root = config.get("workspace_root")
        if workspace_root is not None:
            public = Path(workspace_root).absolute()
            if self.root.is_relative_to(public) or public.is_relative_to(self.root):
                raise ValueError("Federation state and Runtime workspace roots must be disjoint")

    def _setup(self):
        private_directory(self.root)
        for name in ("datasets", "specs", "jobs"):
            private_directory(self.root / name)

    def register_dataset(self, dataset_id, x, y, *, feature_names=None, target_names=None):
        self._setup()
        return inputs.capture(self.root / "datasets" / inputs.uuid(dataset_id), dataset_id, x, y,
                              feature_names=feature_names, target_names=target_names)

    def approve(self, spec, dataset_id, *, run_id, coordinator_id, participant_id, max_rounds):
        self._setup()
        spec, dataset_id = validate_training_spec(spec), inputs.uuid(dataset_id)
        with Lease(self.root / "node.lock", timeout=10):
            manifest, _ = inputs.load(self.root / "datasets" / dataset_id)
            self._columns(spec, manifest)
            digest = training_spec_sha256(spec)
            path = self.root / "specs" / (digest + ".json")
            if path.exists():
                if inputs.read_json(path) != spec:
                    raise NodeFederationError("Frozen trainer specification conflicts")
            else:
                if len(list(path.parent.iterdir())) >= 1024:
                    raise NodeFederationError("Frozen trainer specification quota exceeded")
                inputs.write_json(path, spec)
            return self.consent.grant(run_id, coordinator_id=coordinator_id, participant_id=participant_id,
                dataset_id=dataset_id, dataset_sha256=manifest["dataset_sha256"], spec_sha256=digest,
                model_layout=model_layout(spec), max_rounds=max_rounds)

    @staticmethod
    def _columns(spec, manifest):
        if (manifest["feature_names"] != [c["name"] for c in spec["features"]]
                or manifest["target_names"] != [c["name"] for c in spec["targets"]]):
            raise NodeFederationError("Owner dataset columns do not match the frozen trainer")

    @staticmethod
    def _original(message):
        return {**deepcopy(message), "operation": "train"}

    def _directory(self, message):
        key = inputs.canonical([message["grant_id"], message["round"]])
        return self.root / "jobs" / hashlib.sha256(key).hexdigest()

    def _grant(self, message):
        grant = self.consent.get_grant(message["grant_id"])
        if (grant is None or message["round"] > grant.max_rounds or any(
                getattr(grant, key) != message[key] for key in (
                    "run_id", "coordinator_id", "participant_id", "spec_sha256", "dataset_sha256"))):
            raise NodeFederationError("No owner grant matches this original request")
        return grant

    @staticmethod
    def _expected(message):
        return {key: message[key] for key in ("coordinator_id", "run_id", "round", "participant_id", "dataset_sha256", "spec_sha256")}

    def _dto(self, message, state, status=None, update=None, *, disclose=False):
        status = status or {}
        result = {"format": "stk.federation-node-result/1", "run_id": message["run_id"],
                "round": message["round"], "participant_id": message["participant_id"],
                "grant_id": message["grant_id"], "state": state,
                "task_id": status.get("task_id"), "update_id": update.update_id if update else status.get("update_id"),
                "update": update.as_dict()["metadata"] if disclose and update and update.state == "delivered" else None}
        return validate_node_result(result, message=message)

    def execute(self, message, *, fetch_model, publish_update):
        """Short explicit dispatch/observe/send/cancel; never train in the agent lane."""
        message = validate_message(message)
        try:
            return self._execute(message, fetch_model, publish_update)
        except NodeFederationError:
            raise
        except Exception:
            # Runtime/file/optional-dependency errors can contain private paths.
            raise NodeFederationError("Node federation operation failed; retain the original request") from None

    def _execute(self, message, fetch_model, publish_update):
        grant = self._grant(message)
        directory = self._directory(message)
        if message["operation"] == "train":
            return self._dispatch(message, grant, directory, fetch_model)
        if not directory.exists():
            raise NodeFederationError("No retained original training request")
        with Lease(self.root / "node.lock", timeout=10):
            job = inputs.read_json(directory / "job.json")
            if job["request"] != self._original(message):
                raise NodeFederationError("This grant and round already have another original request")
            status = inputs.read_json(directory / "state.json") if (directory / "state.json").exists() else {}
            if not status.get("task_id") and status.get("workspace_id"):
                # Reconcile a lost submit response by observation only. Never
                # submit a task merely to process a status/cancellation request.
                candidates = [item for item in self.runtime.tasks(status["workspace_id"])
                              if item.get("spec") == status.get("spec")]
                if len(candidates) > 1:
                    raise NodeFederationError("Conflicting private Runtime task identities")
                if candidates:
                    identity = candidates[0].get("id")
                    if type(identity) is not str or not _TASK.fullmatch(identity):
                        raise NodeFederationError("Invalid Runtime training identity")
                    status["task_id"] = identity
                    inputs.write_json(directory / "state.json", status, replace=True)
            if message["operation"] == "cancel":
                if status:
                    status["cancel_requested"] = True
                    inputs.write_json(directory / "state.json", status, replace=True)
                if status.get("task_id"):
                    record = self.runtime.cancel(status["task_id"])
                    # An active program must be stopped by Runtime's authority.
                    # A private cooperative exit can beat its wrapper's cancel
                    # poll and be misclassified as a normal program failure.
                    mark_private = record["state"] in {"succeeded", "failed", "cancelled"}
                else:
                    mark_private = True  # no known active Runtime process
                if mark_private and not (directory / "cancel").exists():
                    inputs.write_bytes(directory / "cancel", b"cancel\n")
                return self._observe(message, grant, directory, status)
            result = self._observe(message, grant, directory, status)
            if message["operation"] != "collect" or not status.get("update_id"):
                return result
            if status.get("cancel_requested") or (directory / "cancel").exists():
                raise NodeFederationError("A cancelled federation job cannot publish an update")
            try:
                update = self.consent.send_update(status["update_id"], coordinator_id=message["coordinator_id"],
                    deliver=lambda metadata, payload: publish_update(status["update_id"], metadata, payload))
            except ConsentOutcomeUncertain:
                return self._dto(message, "uncertain", status)
            return self._dto(message, "delivered", status, update, disclose=True)

    def _dispatch(self, message, grant, directory, fetch_model):
        self._setup()
        with Lease(self.root / "node.lock", timeout=10):
            with self.consent.authorized(message["grant_id"], **self._expected(message)):
                pass
            spec = validate_training_spec(inputs.read_json(self.root / "specs" / (message["spec_sha256"] + ".json")))
            if training_spec_sha256(spec) != message["spec_sha256"] or grant.as_dict()["model_layout"] != model_layout(spec):
                raise NodeFederationError("Frozen trainer specification differs from owner consent")
            manifest, _ = inputs.load(self.root / "datasets" / grant.dataset_id)
            if manifest["dataset_sha256"] != grant.dataset_sha256:
                raise NodeFederationError("Owner dataset identity changed")
            self._columns(spec, manifest)
            job = {"format": "stk.federation-train-job/1", "request": self._original(message),
                   "spec": spec, "dataset_id": grant.dataset_id}
            if directory.exists():
                if inputs.read_json(directory / "job.json") != job:
                    raise NodeFederationError("This grant and round already have another original request")
            else:
                if len(list(directory.parent.iterdir())) >= 4096:
                    raise NodeFederationError("Retained training job quota exceeded")
                directory.mkdir(mode=0o700)
                inputs.write_json(directory / "job.json", job)
            state_path = directory / "state.json"
            status = inputs.read_json(state_path) if state_path.exists() else {}
            if status.get("task_id"):
                return self._observe(message, grant, directory, status)
            if self.python is None:
                raise NodeFederationError("The owner-selected federation interpreter is unavailable")
            if (directory / "cancel").exists() and not status:
                return self._dto(message, "cancelled")
            model_path = directory / "model.bin"
            if model_path.exists():
                raw = inputs.read_bytes(model_path)
            else:
                raw = fetch_model(deepcopy(message["model"]))
                if type(raw) is not bytes:
                    raise NodeFederationError("Model fetch did not return immutable bytes")
                decoded = decode_arrays(raw, expected_kind="model", expected_layout=model_layout(spec))
                if decoded["sha256"] != message["model"]["sha256"] or len(raw) != message["model"]["bytes"]:
                    raise NodeFederationError("Fetched model differs from the original request")
                inputs.check_budget(self.root, len(raw))
                inputs.write_bytes(model_path, raw)
            decoded = decode_arrays(raw, expected_kind="model", expected_layout=model_layout(spec))
            if decoded["sha256"] != message["model"]["sha256"] or len(raw) != message["model"]["bytes"]:
                raise NodeFederationError("Private model differs from the original request")
            if not status:
                key = "federation:" + directory.name
                workspace_id = hashlib.sha256(("workspace:" + key).encode()).hexdigest()[:32]
                task_spec = TaskSpec(workspace_id=workspace_id,
                    argv=[self.python, "-I", "-m", "suan.federation.train_worker", str(directory)],
                    name="Owner-approved federation training", inputs=[], input_hashes={}, outputs=["receipt.json"],
                    resources={"cpus": 1, "memory_mb": 1024, "walltime_seconds": 300}).to_dict()
                status = {"workspace_id": workspace_id, "key": key, "spec": task_spec,
                          "task_id": None, "update_id": None, "cancel_requested": False}
                # Reserve public namespace identity before Runtime can expose it.
                inputs.write_json(state_path, status)
            workspace = self.runtime.create_workspace("Owner-approved federation training", status["key"])
            if workspace["id"] != status["workspace_id"]:
                raise NodeFederationError("Runtime workspace identity differs")
            with self.consent.authorized(message["grant_id"], **self._expected(message)):
                # Reusing this exact key/spec resolves a lost response. Runtime
                # unknown/terminal tasks retain their ID and are never retrained.
                record = self.runtime.submit(status["spec"], status["key"])
                if type(record.get("id")) is not str or not _TASK.fullmatch(record["id"]):
                    raise NodeFederationError("Invalid Runtime training identity")
                status["task_id"] = record["id"]
                inputs.write_json(state_path, status, replace=True)
            if status["cancel_requested"] or (directory / "cancel").exists():
                self.runtime.cancel(status["task_id"])
            return self._observe(message, grant, directory, status)

    def _observe(self, message, grant, directory, status):
        if not status.get("task_id"):
            return self._dto(message, "uncertain" if status else "prepared", status)
        record = self.runtime.task(status["task_id"])
        if record.get("id") != status["task_id"] or record.get("spec") != status.get("spec"):
            raise NodeFederationError("Observed Runtime task differs from the frozen request")
        state = {"preparing": "prepared", "queued": "queued", "submitting": "queued", "pending": "queued",
                 "running": "running", "succeeded": "ready", "failed": "failed", "cancelled": "cancelled"}.get(record["state"], "unknown")
        if status.get("update_id"):
            update = self.consent.get_update(status["update_id"])
            if update is None:
                raise NodeFederationError("Retained update is missing")
            validate_update(update.as_dict()["metadata"], run_id=message["run_id"], round=message["round"],
                participant_id=message["participant_id"], model_sha256=message["model"]["sha256"],
                spec_sha256=message["spec_sha256"], dataset_sha256=message["dataset_sha256"], grant_id=message["grant_id"])
            mapped = {"prepared": "ready", "delivered": "delivered", "sending": "uncertain", "uncertain": "uncertain"}
            return self._dto(message, mapped.get(update.state, "unknown"), status, update,
                             disclose=message["operation"] == "collect")
        if state == "ready" and grant.active and not status.get("cancel_requested") and not (directory / "cancel").exists():
            job = inputs.read_json(directory / "job.json")
            result = inputs.read_json(directory / "result.json")
            if (type(result) is not dict or set(result) != {"format", "request_sha256", "delta_sha256", "delta_bytes", "num_examples", "metrics"}
                    or result["format"] != "stk.federation-train-result/1"
                    or result["request_sha256"] != hashlib.sha256(inputs.canonical(job["request"])).hexdigest()):
                raise NodeFederationError("Private training result binding differs")
            raw = inputs.read_bytes(directory / "delta.bin")
            decoded = decode_arrays(raw, expected_kind="delta", expected_layout=model_layout(job["spec"]))
            manifest, _ = inputs.load(self.root / "datasets" / grant.dataset_id)
            if (decoded["sha256"] != result["delta_sha256"] or type(result["delta_bytes"]) is not int
                    or len(raw) != result["delta_bytes"] or type(result["num_examples"]) is not int
                    or manifest["num_examples"] != result["num_examples"] or manifest["dataset_sha256"] != grant.dataset_sha256):
                raise NodeFederationError("Private training result bytes differ")
            metadata = {"format": "stk.federation-update/1", **{k: message[k] for k in (
                "run_id", "round", "participant_id", "spec_sha256", "dataset_sha256", "grant_id")},
                "model_sha256": message["model"]["sha256"], "update_sha256": decoded["sha256"],
                "update_bytes": len(raw), "num_examples": result["num_examples"], "metrics": result["metrics"], "masked": False}
            validate_update(metadata, **{key: metadata[key] for key in (
                "run_id", "round", "participant_id", "model_sha256", "spec_sha256", "dataset_sha256", "grant_id")})
            update = self.consent.prepare_update(message["grant_id"], metadata, raw, model_sha256=message["model"]["sha256"])
            status["update_id"] = update.update_id
            inputs.write_json(directory / "state.json", status, replace=True)
            return self._dto(message, "ready", status, update)
        return self._dto(message, "unknown" if state == "ready" else state, status)

    def is_private_workspace(self, workspace_id):
        """Read retained reservations, including those made before Runtime creation."""
        if type(workspace_id) is not str or not _TASK.fullmatch(workspace_id):
            return False
        return workspace_id in self.private_identities()["workspaces"]

    def private_identities(self):
        """One bounded, no-follow read of retained public identity reservations.

        A snapshot/action should reuse this returned set for all of its task and
        workspace checks. No Runtime call or state creation happens here.
        """
        result = {"tasks": set(), "workspaces": set()}
        jobs = self.root / "jobs"
        if not jobs.exists() and not jobs.is_symlink():
            return result
        private_directory(jobs, create=False)
        count = 0
        for directory in jobs.iterdir():
            count += 1
            if count > 4096 or not re.fullmatch(r"[0-9a-f]{64}", directory.name):
                raise NodeFederationError("Invalid retained private training identities")
            private_directory(directory, create=False)
            path = directory / "state.json"
            if not path.exists() and not path.is_symlink():
                continue  # reserved private job, no public namespace allocated yet
            status = inputs.read_json(path)
            if type(status) is not dict or type(status.get("workspace_id")) is not str or not _TASK.fullmatch(status["workspace_id"]):
                raise NodeFederationError("Invalid retained private workspace reservation")
            for field, group in (("task_id", "tasks"), ("workspace_id", "workspaces")):
                identity = status.get(field)
                if identity is not None:
                    if type(identity) is not str or not _TASK.fullmatch(identity):
                        raise NodeFederationError("Invalid retained private training identity")
                    result[group].add(identity)
        return result

    def is_private_task(self, task_id):
        if type(task_id) is not str or not _TASK.fullmatch(task_id):
            return False
        identities = self.private_identities()
        if task_id in identities["tasks"]:
            return True
        if not identities["workspaces"]:
            return False
        # A lost submit reply can precede the task-ID write. Its already-reserved
        # workspace still proves private ownership, without creating any state.
        try:
            record = self.runtime.task(task_id)
        except KeyError:
            return False
        return record["spec"]["workspace_id"] in identities["workspaces"]
