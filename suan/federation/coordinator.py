"""Explicit persistent rounds; opening, observing and recovering never train or send.

Each operation has a durable original action before a single HTTP submission.
Lost replies are queried by that identity, never replayed with another identity.
Only explicit train/collect/aggregate/prepare_round methods advance a run. The
candidate is private and unadmitted; no model registry or project is modified.
"""
from pathlib import Path
from uuid import uuid4

from suan.materials.jobs import Lease, private_directory
from . import inputs
from .client import _identity
from .protocol import (MESSAGE_FORMAT, canonical_json, model_layout, training_spec_sha256,
                       validate_node_result, validate_run_manifest, validate_training_spec)
from .updates import decode_arrays, validate_round

MAX_ACTIONS_PER_ROUND = 128
MAX_COORDINATOR_BYTES = 512*1024*1024


class CoordinatorError(RuntimeError):
    pass


class FederationCoordinator:
    def __init__(self, root, client, aggregator):
        self.root = Path(root).absolute()
        self.client, self.aggregator = client, aggregator

    def _run(self, run_id):
        path = self.root / _identity(run_id,uuid=True)
        return path, inputs.read_json(path / "run.json")

    def _round(self, run_id, number):
        path, run = self._run(run_id)
        if type(number) is not int or not 1 <= number <= run["manifest"]["max_rounds"]:
            raise CoordinatorError("Round is outside the approved run")
        path = path / str(number)
        return path, run, inputs.read_json(path / "round.json")

    def _lock(self):
        private_directory(self.root)
        return Lease(self.root / "coordinator.lock")

    def _save(self, path, value):
        encoded = canonical_json(value)
        # Retained originals/receipts are never GC'd to make a new identity reusable.
        total = sum(p.stat().st_size for p in self.root.rglob("*") if p.is_file())
        if total + len(encoded) > MAX_COORDINATOR_BYTES:
            raise CoordinatorError("Coordinator retention budget is exhausted")
        inputs.write_bytes(path,encoded,replace=True)

    def create(self, manifest, spec, model):
        manifest, spec = validate_run_manifest(manifest), validate_training_spec(spec)
        if manifest["spec_sha256"] != training_spec_sha256(spec):
            raise CoordinatorError("Run specification does not match its frozen identity")
        decoded = decode_arrays(model,expected_kind="model",expected_layout=model_layout(spec))
        document = {"format":"stk.federation-coordinator/1","manifest":manifest,"spec":spec,
                    "initial_model_sha256":decoded["sha256"],"rounds":0}
        with self._lock():
            path = self.root / manifest["run_id"]
            if path.exists():
                old = inputs.read_json(path / "run.json")
                if any(canonical_json(old[key]) != canonical_json(document[key]) for key in
                       ("manifest","spec","initial_model_sha256")):
                    raise CoordinatorError("Run identity already binds different originals")
                return old
            private_directory(path)
            inputs.write_bytes(path / "initial.bin",model)
            self._save(path / "run.json",document)
            return document

    def _approved(self, manifest):
        remote = self.client.run(manifest["run_id"])
        if (type(remote) is not dict or set(remote) != {"manifest","active"}
                or remote["active"] is not True
                or canonical_json(validate_run_manifest(remote["manifest"])) != canonical_json(manifest)):
            raise CoordinatorError("Hub run is inactive or differs from the owner's frozen mapping")

    def prepare_round(self, run_id):
        """Freeze the next model explicitly; never publish, dispatch or aggregate."""
        with self._lock():
            path, run = self._run(run_id)
            number = run["rounds"]
            if number:
                previous = inputs.read_json(path / str(number) / "round.json")
                if previous["state"] != "aggregated":
                    return previous
                model = inputs.read_bytes(path / str(number) / "candidate.bin")
                expected_sha256 = previous["candidate_sha256"]
            else:
                model = inputs.read_bytes(path / "initial.bin")
                expected_sha256 = run["initial_model_sha256"]
            number += 1
            if number > run["manifest"]["max_rounds"]:
                raise CoordinatorError("The owner's approved round limit is reached")
            decoded = decode_arrays(model,expected_kind="model",expected_layout=model_layout(run["spec"]))
            if decoded["sha256"] != expected_sha256:
                raise CoordinatorError("Next round base differs from the retained model identity")
            directory = path / str(number)
            document = {"format":"stk.federation-round/1","run_id":run_id,"round":number,
                        "model":{"sha256":decoded["sha256"],"bytes":len(model)},
                        "state":"prepared","model_phase":"prepared","actions":[],"receipt":None}
            # An interrupted prepare is retained and blocks adoption, never overwritten.
            private_directory(directory)
            inputs.write_bytes(directory / "model.bin",model)
            self._save(directory / "round.json",document)
            run["rounds"] = number
            self._save(path / "run.json",run)
            return document

    @staticmethod
    def _message(manifest, current, participant, operation):
        return {"format":MESSAGE_FORMAT,"operation":operation,"run_id":manifest["run_id"],
                "round":current["round"],"coordinator_id":manifest["coordinator_id"],
                "spec_sha256":manifest["spec_sha256"],"model":dict(current["model"]),
                **{key:participant[key] for key in ("participant_id","grant_id","dataset_sha256")}}

    def _poll(self, item):
        try:
            remote = self.client.action(item["action_id"],node_id=item["node_id"],message=item["message"])
            if remote["state"] == "succeeded":
                item["result"] = validate_node_result(remote["result"],message=item["message"])
                item["phase"] = "done"
            elif remote["state"] == "failed":
                item["phase"] = "failed"
            else:
                item["phase"] = "queued"
        except Exception:
            # A failed query is not proof the action was not accepted or finished.
            item["phase"] = "uncertain"

    def recover(self, run_id, number):
        """Only query retained actions. Never submit/train/send/aggregate on reopen."""
        with self._lock():
            path, run, current = self._round(run_id,number)
            self._approved(run["manifest"])
            for item in current["actions"]:
                if item["phase"] in {"sending","queued","uncertain"}:
                    self._poll(item)
            self._save(path / "round.json",current)
            return current

    def _operate(self, run_id, number, operation):
        with self._lock():
            path, run, current = self._round(run_id,number)
            manifest = run["manifest"]
            self._approved(manifest)
            if current["state"] in {"aggregating","aggregate_uncertain"}:
                raise CoordinatorError("An interrupted aggregation requires evidence review")
            if current["state"] == "aggregated":
                raise CoordinatorError("This round already has an immutable candidate")
            if operation == "train" and current["model_phase"] != "published":
                raw = inputs.read_bytes(path / "model.bin")
                decoded = decode_arrays(raw,expected_kind="model",expected_layout=model_layout(run["spec"]))
                if {"sha256":decoded["sha256"],"bytes":len(raw)} != current["model"]:
                    raise CoordinatorError("Private round model differs from its frozen identity")
                if current["model_phase"] in {"sending","uncertain"}:
                    # Resolve an interrupted upload only by GET; never automatically PUT again.
                    probe = self._message(manifest,current,manifest["participants"][0],"status")
                    if self.client.fetch_model(probe) != raw:
                        raise CoordinatorError("Original model publication is uncertain")
                else:
                    current["model_phase"] = "sending"
                    self._save(path / "round.json",current)
                    try:
                        self.client.upload_model(run_id,number,raw)
                    except Exception:
                        current["model_phase"] = "uncertain"
                        self._save(path / "round.json",current)
                        raise CoordinatorError("Model publication outcome is uncertain") from None
                current["model_phase"] = "published"
                self._save(path / "round.json",current)
            if current["model_phase"] != "published":
                raise CoordinatorError("Explicitly publish and start this round first")
            for participant in manifest["participants"]:
                previous = next((x for x in reversed(current["actions"]) if x["node_id"] == participant["node_id"]
                                 and x["message"]["operation"] == operation),None)
                if previous is not None:
                    if previous["phase"] in {"sending","queued","uncertain"}:
                        self._poll(previous)
                        self._save(path / "round.json",current)
                        continue
                    if operation == "train" or (operation == "cancel" and previous["phase"] != "failed"):
                        continue
                    if operation == "collect" and previous["result"] and previous["result"]["state"] in {"delivered","uncertain"}:
                        continue
                if len(current["actions"]) >= MAX_ACTIONS_PER_ROUND:
                    raise CoordinatorError("This round's retained action budget is exhausted")
                item = {"action_id":uuid4().hex,"node_id":participant["node_id"],
                        "message":self._message(manifest,current,participant,operation),"phase":"sending","result":None}
                current["actions"].append(item)
                self._save(path / "round.json",current)  # intent precedes network
                try:
                    self.client.submit(item["node_id"],item["message"],item["action_id"])
                    item["phase"] = "queued"
                except Exception:
                    item["phase"] = "uncertain"
                self._save(path / "round.json",current)
            current["state"] = "active"
            self._save(path / "round.json",current)
            return current

    def train(self, run_id, number):
        return self._operate(run_id,number,"train")

    def observe(self, run_id, number):
        return self._operate(run_id,number,"status")

    def collect(self, run_id, number):
        return self._operate(run_id,number,"collect")

    def cancel(self, run_id, number):
        return self._operate(run_id,number,"cancel")

    def aggregate(self, run_id, number):
        with self._lock():
            path, run, current = self._round(run_id,number)
            self._approved(run["manifest"])
            if current["state"] == "aggregated":
                return current
            if current["state"] in {"aggregating","aggregate_uncertain"}:
                raise CoordinatorError("Aggregation was interrupted; automatic replay is prohibited")
            participants = {p["participant_id"]:{k:p[k] for k in ("dataset_sha256","grant_id")}
                            for p in run["manifest"]["participants"]}
            rows = {}
            for item in current["actions"]:
                if (item["message"]["operation"] == "collect" and item["phase"] == "done"
                        and item["result"]["state"] == "delivered"):
                    result = validate_node_result(item["result"],message=item["message"])
                    rows[result["participant_id"]] = (item,result)
            validate_round([r["update"] for _,r in rows.values()],participants=participants,run_id=run_id,
                           round=number,model_sha256=current["model"]["sha256"],spec_sha256=run["manifest"]["spec_sha256"])
            updates = [(r["update"],self.client.fetch_update(i["message"],r)) for i,r in rows.values()]
            model = inputs.read_bytes(path / "model.bin")
            decoded = decode_arrays(model,expected_kind="model",expected_layout=model_layout(run["spec"]))
            if {"sha256":decoded["sha256"],"bytes":len(model)} != current["model"]:
                raise CoordinatorError("Private round model differs from its frozen identity")
            current["state"] = "aggregating"
            self._save(path / "round.json",current)
            try:
                result = self.aggregator.aggregate(model,updates,participants=participants,run_id=run_id,
                    round=number,spec_sha256=run["manifest"]["spec_sha256"])
                decoded = decode_arrays(result["model"],expected_kind="model",expected_layout=model_layout(run["spec"]))
                inputs.write_bytes(path / "candidate.bin",result["model"])
                current.update(state="aggregated",receipt=result["receipt"],candidate_sha256=decoded["sha256"])
                self._save(path / "round.json",current)
            except Exception:
                current["state"] = "aggregate_uncertain"
                self._save(path / "round.json",current)
                raise CoordinatorError("Aggregation outcome requires explicit evidence review") from None
            return current

    def get(self, run_id, number):
        """Read only; no network call, recovery, task start, or model admission."""
        return self._round(run_id,number)[2]
