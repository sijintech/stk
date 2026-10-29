"""Explicit local training on frozen inputs, durable tasks and model admission.

training.sqlite3 records tasks and epochs; jobs/<id>/inputs binds exact bytes.
Reopening and observation never train or recover. registry.json keeps the
existing model layout and explicit rollback interface.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import threading
import time
import uuid

from . import curves, datasets, inputs, jobs as storage, training

GATES = {"pe_loop": 0.25, "capacity_fade": 0.1}
MAX_PREDICT_ROWS = 100


class MaterialsError(ValueError):
    """A request the materials service cannot carry out."""


class MaterialsNotFound(MaterialsError):
    """No such job, kind or version."""


class MaterialsBusy(MaterialsError):
    """A training or registry operation is already running."""


MaterialsUnavailable = storage.StorageError


def _now():
    return datetime.now(timezone.utc).isoformat()


def _id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value):
        raise MaterialsError("job_id must contain 1 to 64 letters, digits, underscores or hyphens")
    return value


def _page(value, low, high, name):
    if type(value) is not int or not low <= value <= high:
        raise MaterialsError(f"{name} must be an integer from {low} to {high}")
    return value


def _bytes(path, maximum):
    storage.private_directory(Path(path).parent, create=False)
    before = storage.ordinary(path)
    if before.st_size > maximum:
        raise MaterialsUnavailable("Model metadata exceeds its byte budget")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    with os.fdopen(os.open(path, flags), "rb") as source:
        opened = os.fstat(source.fileno())
        # Windows lstat/fstat ctime fields need not have the same meaning.
        cross = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns)
        if cross(before) != cross(opened):
            raise MaterialsUnavailable("Model metadata changed before opening")
        data = source.read(maximum + 1)
        finished = os.fstat(source.fileno())
    after = storage.ordinary(path)
    stamp = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    if len(data) > maximum or stamp(before) != stamp(after) or stamp(opened) != stamp(finished):
        raise MaterialsUnavailable("Model metadata changed while it was read")
    return data


def _sha(path, maximum):
    return hashlib.sha256(_bytes(path, maximum)).hexdigest()


class _Cancellation:
    def __init__(self, store, job_id):
        self.store, self.job_id = store, job_id
        self.event = threading.Event()
        self.checked = 0.0

    def set(self):
        self.event.set()

    def is_set(self):
        if self.event.is_set():
            return True
        now = time.monotonic()
        if now - self.checked >= 0.1:
            self.checked = now
            job = self.store.get(self.job_id)
            if job is None or job["cancel_requested"]:
                self.event.set()
        return self.event.is_set()


class MaterialsService:
    def __init__(self, root):
        self.root = Path(root).absolute()
        self._lock = threading.RLock()
        self._store = storage.Store(self.root)
        self._workers = {}
        self._models = {}
        self._closed = False

    @contextmanager
    def _lease(self, name="operations", *, timeout=0):
        try:
            with storage.Lease(self.root / (name + ".lock"), timeout=timeout) as lease:
                yield lease
        except storage.Locked:
            raise MaterialsBusy("Another materials operation is in progress") from None

    def _registry(self):
        path = self.root / "registry.json"
        try:
            if not path.exists() and not path.is_symlink():
                return {"kinds": {}}
            if storage.ordinary(path).st_size > 16 * 1024 * 1024:
                raise ValueError("oversized registry")
            registry = json.loads(_bytes(path, 16 * 1024 * 1024))
        except (OSError, ValueError) as exc:
            raise MaterialsUnavailable(f"The model registry cannot be read: {type(exc).__name__}") from None
        if not isinstance(registry, dict) or not isinstance(registry.get("kinds"), dict):
            raise MaterialsUnavailable("The model registry is damaged")
        for kind, entry in registry["kinds"].items():
            if kind not in curves.KINDS or not isinstance(entry, dict) or not isinstance(entry.get("versions"), list):
                raise MaterialsUnavailable("The model registry is damaged")
            versions = entry["versions"]
            if (len(versions) > 10000 or any(not isinstance(v, dict) or not isinstance(v.get("version"), str)
                    or not re.fullmatch(r"v[1-9][0-9]*", v["version"]) for v in versions)
                    or len({v["version"] for v in versions}) != len(versions)
                    or entry.get("active") not in [None, *(v["version"] for v in versions)]
                    or type(entry.get("generation", 0)) is not int or entry.get("generation", 0) < 0):
                raise MaterialsUnavailable("The model registry is damaged")
        return registry

    def _save(self, registry):
        storage.private_directory(self.root)
        temporary = self.root / ("registry-" + uuid.uuid4().hex + ".tmp")
        try:
            data = json.dumps(registry, ensure_ascii=False, indent=1, allow_nan=False).encode("utf-8") + b"\n"
            with os.fdopen(os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as target:
                target.write(data)
                target.flush()
                os.fsync(target.fileno())
            os.replace(temporary, self.root / "registry.json")
        finally:
            temporary.unlink(missing_ok=True)

    @contextmanager
    def _registry_read(self):
        # All supported registry readers participate in the publication lease.
        # Windows ordinary handles can block replacement even across processes;
        # don't leave one open while another service publishes a model.
        if not (self.root / "registry.json").exists():
            yield self._registry()
        else:
            with self._lease(timeout=0.25):
                yield self._registry()

    def models(self, kind=None):
        if kind is not None and kind not in curves.KINDS:
            raise MaterialsError(f"kind is one of {', '.join(curves.KINDS)}")
        with self._registry_read() as registry:
            registry = registry.copy()
        kinds = {}
        for name in ([kind] if kind else curves.KINDS):
            entry = registry["kinds"].get(name, {"active": None, "versions": []})
            kinds[name] = {"active": entry.get("active"), "versions": entry["versions"]}
        return {"kinds": kinds, "gates": dict(GATES)}

    def activate(self, kind, version):
        with self._lease(), self._lock:
            registry = self._registry()
            entry = registry["kinds"].get(kind)
            if not entry or version not in [item["version"] for item in entry["versions"]]:
                raise MaterialsNotFound("No such model version")
            entry["active"] = version
            entry["generation"] = entry.get("generation", 0) + 1
            self._save(registry)
            return {"active": entry["active"], "versions": entry["versions"]}

    def prepare(self, directory, job_id, *, options=None, base_version=None):
        """Freeze without torch. Identical retries return the original frozen task.

        Use a new ID to capture changed bytes, even at the same source path.
        """
        _id(job_id)
        settings = inputs.normalize_options(options)
        directory = Path(directory).absolute()
        request = {"directory": str(directory), "options": settings, "base_version": base_version}
        with self._lease():
            with self._lock:
                if self._closed:
                    raise MaterialsUnavailable("The materials service is shutting down")
            existing = self._store.get(job_id)
            if existing is not None:
                if existing["request"] != request:
                    raise MaterialsError("This job ID already identifies a different frozen request")
                return self._public(existing)
            # This hint only selects registry roles. The captured kind is checked
            # again; training never depends on these live metadata bytes.
            metadata_path = directory / "dataset.json"
            if storage.ordinary(metadata_path).st_size > 1024 * 1024:
                raise MaterialsError("Dataset metadata exceeds its byte budget")
            raw = _bytes(metadata_path, 1024 * 1024)
            if len(raw) > 1024 * 1024:
                raise MaterialsError("Dataset metadata exceeds its byte budget")
            description = json.loads(raw)
            if not isinstance(description, dict) or not isinstance(description.get("target"), dict):
                raise MaterialsError("Invalid dataset metadata")
            kind = description["target"].get("kind")
            if kind not in curves.KINDS:
                raise MaterialsError("Unsupported training target")
            entry = self._registry()["kinds"].get(kind, {"active": None, "versions": []})
            baseline = entry.get("active")
            if base_version is not None and base_version not in [v["version"] for v in entry["versions"]]:
                raise MaterialsNotFound("No such base model version")
            parent = storage.private_directory(self.root / "jobs")
            folder = parent / job_id
            try:
                folder.mkdir(mode=0o700)
            except FileExistsError:
                raise MaterialsUnavailable("An unclaimed job folder exists; use a new job ID") from None
            owned = True
            try:
                role = lambda version: self.root / "models" / kind / version if version is not None else None
                manifest = inputs.capture(directory, folder / "inputs", options=settings,
                                          base_model=role(base_version), baseline_model=role(baseline))
                if manifest["kind"] != kind:
                    raise MaterialsError("The dataset target changed during preparation")
                gate = GATES[kind]
                if type(gate) not in (int, float) or not math.isfinite(gate) or gate <= 0:
                    raise MaterialsUnavailable("Invalid model admission gate")
                card = manifest["dataset"]["card"]
                record = {"id": job_id, "kind": kind, "state": "prepared", "dataset": str(directory),
                          "synthetic": card["synthetic"], "epoch": 0, "epochs": settings["epochs"],
                          "train_loss": None, "validation_loss": None, "error": None, "version": None,
                          "metrics": None, "gate": gate, "created_at": _now(), "started_at": None,
                          "finished_at": None, "input_sha256": manifest["sha256"], "options": settings,
                          "split_counts": {k: len(v) for k, v in manifest["split"].items()}, "card": card,
                          "base_version": base_version, "baseline_version": baseline,
                          "baseline_generation": entry.get("generation", 0), "comparison": None,
                          "evaluation_preview": None,
                          "reason": None, "cancel_requested": False, "request": request, "admission": None}
                self._store.create({"input_sha256": manifest["sha256"], "request": request}, record)
                owned = False
                return self._public(record)
            finally:
                if owned:
                    shutil.rmtree(folder)

    def train(self, directory, job_id, *, options=None, base_version=None):
        """Compatibility convenience: explicitly prepare and start; never replay an ID."""
        existing = self._store.get(_id(job_id))
        if existing is not None:
            return self._public(existing)
        training.torch_module()
        with self._lease("trainer", timeout=0.25):
            pass
        self.prepare(directory, job_id, options=options, base_version=base_version)
        return self.start(job_id)

    def start(self, job_id):
        job = self._job(job_id)
        if job["state"] != "prepared":
            return self._public(job)
        training.torch_module()
        try:
            lease = storage.Lease(self.root / "trainer.lock", timeout=0.25)
        except storage.Locked:
            raise MaterialsBusy("Another model is being trained; wait for it or cancel it") from None
        transferred = False
        try:
            with self._lease(), self._lock:
                if self._closed:
                    raise MaterialsUnavailable("The materials service is shutting down")
                job = self._job(job_id)
                if job["state"] != "prepared":
                    return self._public(job)
                manifest = inputs.verify(self.root / "jobs" / job_id / "inputs")
                if manifest["sha256"] != job["input_sha256"]:
                    raise MaterialsUnavailable("Frozen training input does not match its task")
                cancel = _Cancellation(self._store, job_id)
                self._store.update(job_id, {"state": "running", "started_at": _now(), "owner": uuid.uuid4().hex})
                self._workers[job_id] = cancel
                worker = threading.Thread(target=self._run, args=(job_id, cancel, lease),
                                          name="stk-materials-train", daemon=True)
                try:
                    worker.start()
                except BaseException:
                    self._workers.pop(job_id, None)
                    self._store.update(job_id, {"state": "failed", "error": "Trainer could not start", "finished_at": _now()})
                    raise
                transferred = True
            return self.job(job_id)
        finally:
            if not transferred:
                lease.close()

    def _job(self, job_id):
        job = self._store.get(_id(job_id))
        if job is None:
            raise MaterialsNotFound("No such training job")
        return job

    @staticmethod
    def _public(job):
        return {k: v for k, v in job.items() if k not in {"request", "admission", "owner", "baseline_generation"}}

    def job(self, job_id):
        return self._public(self._job(job_id))

    def jobs(self, *, offset=0, limit=50):
        result = self._store.list(offset=_page(offset, 0, 1000000, "offset"), limit=_page(limit, 1, 100, "limit"))
        result["jobs"] = [self._public(job) for job in result["jobs"]]
        return result

    def job_curves(self, job_id, *, after=0, limit=200):
        self._job(job_id)
        after, limit = _page(after, 0, 5000, "after"), _page(limit, 1, 1000, "limit")
        recorded, values = self._store.curves(job_id, after=after, limit=limit)
        last = values[-1]["epoch"] if values else after
        return {"id": job_id, "curves": values, "next_after": last if last < recorded else None,
                "recorded_epochs": recorded}

    def cancel(self, job_id):
        self._job(job_id)
        with self._lease(), self._lock:
            job = self._job(job_id)
            if job["state"] not in {"prepared", "running"}:
                return self._public(job)
            changes = {"cancel_requested": True}
            if job["state"] == "prepared":
                changes.update(state="cancelled", finished_at=_now())
            updated = self._store.update(job_id, changes)
            if job_id in self._workers:
                self._workers[job_id].set()
            return self._public(updated)

    def recover(self, job_id):
        """Observe an abandoned trainer; never train, admit or reactivate a model."""
        job = self._job(job_id)
        if job["state"] not in {"running", "uncertain"}:
            return self._public(job)
        with self._lease("trainer"), self._lease():
            job = self._job(job_id)
            if job["state"] not in {"running", "uncertain"}:
                return self._public(job)
            admission = job.get("admission")
            changes = {"state": "cancelled" if job["cancel_requested"] else "interrupted",
                       "finished_at": _now(), "reason": "trainer_stopped"}
            if admission:
                entry = self._registry()["kinds"].get(job["kind"], {"versions": []})
                published = next((v for v in entry["versions"] if v.get("job_id") == job_id), None)
                if published is not None:
                    if published != admission["record"]:
                        changes.update(state="uncertain", reason="admission_receipt_conflict")
                    else:
                        try:
                            folder = self.root / "models" / job["kind"] / published["version"]
                            intact = (_sha(folder / "model.json", 1024 * 1024) == published["model_sha256"] and
                                      _sha(folder / "model.pt", 256 * 1024 * 1024) == published["weights_sha256"])
                            manifest = inputs.verify(self.root / "jobs" / job_id / "inputs")
                            if not intact or manifest["sha256"] != job["input_sha256"]:
                                changes.update(state="uncertain", reason="admitted_model_changed")
                            else:
                                changes.update(state="done", version=published["version"], reason=None)
                        except (OSError, ValueError, MaterialsUnavailable):
                            changes.update(state="uncertain", reason="admitted_evidence_unavailable")
            return self._public(self._store.update(job_id, changes))

    def _register(self, staged, meta, job, cancel):
        kind = job["kind"]
        with self._lease(timeout=60), self._lock:
            current = self._job(job["id"])
            if cancel.is_set() or current["cancel_requested"] or self._closed:
                raise training.Cancelled("Training was cancelled")
            registry = self._registry()
            entry = registry["kinds"].setdefault(kind, {"active": None, "versions": []})
            if (entry.get("active"), entry.get("generation", 0)) != (job["baseline_version"], job["baseline_generation"]):
                return None, "active_model_changed"
            folder = storage.private_directory(self.root / "models" / kind)
            names = [v["version"] for v in entry["versions"]] + [p.name for p in folder.iterdir()]
            numbers = [int(m.group(1)) for name in names if (m := re.fullmatch(r"v(\d+)", name))]
            version = f"v{max(numbers, default=0) + 1}"
            target = folder / version
            record = {"version": version, "created_at": meta["created_at"], "dataset": meta["dataset"],
                      "metrics": meta["metrics"]["test"], "gate": job["gate"], "job_id": job["id"],
                      "input_sha256": job["input_sha256"], "model_sha256": _sha(staged / "model.json", 1024 * 1024),
                      "weights_sha256": meta["weights_sha256"], "comparison": meta["comparison"],
                      "base_version": job["base_version"], "baseline_version": job["baseline_version"]}
            if json.loads(_bytes(staged / "model.json", 1024 * 1024)) != meta:
                raise MaterialsUnavailable("Trained model metadata changed before admission")
            # Intent precedes the move. Recovery can recognize exact publication
            # if the process stops between registry replacement and completion.
            self._store.update(job["id"], {"admission": {"record": record}, "metrics": meta["metrics"],
                                           "comparison": meta["comparison"]})
            if target.exists():
                raise MaterialsUnavailable("A model version appeared during admission")
            if _sha(staged / "model.pt", 256 * 1024 * 1024) != record["weights_sha256"]:
                raise MaterialsUnavailable("Trained model weights changed before admission")
            os.rename(staged, target)
            entry["versions"].append(record)
            entry["active"] = version
            entry["generation"] = entry.get("generation", 0) + 1
            self._save(registry)
            self._store.update(job["id"], {"state": "done", "version": version, "finished_at": _now()})
            return version, None

    def _run(self, job_id, cancel, lease):
        folder = self.root / "jobs" / job_id
        attempt = folder / ("attempt-" + uuid.uuid4().hex)
        staged = attempt / "model"

        def progress(epoch, train_loss, validation_loss):
            if not all(type(v) in (int, float) and math.isfinite(v) for v in (train_loss, validation_loss)):
                raise MaterialsError("Training produced nonfinite losses")
            self._store.update(job_id, {"epoch": epoch, "train_loss": train_loss, "validation_loss": validation_loss},
                               epoch=(epoch, train_loss, validation_loss))

        try:
            storage.private_directory(attempt)
            job = self._job(job_id)
            meta = training.train(folder / "inputs", staged, frozen=True, progress=progress, cancel=cancel)
            if cancel.is_set() or self._job(job_id)["cancel_requested"]:
                raise training.Cancelled("Training was cancelled")
            expected = inputs.verify(folder / "inputs")
            if (expected["sha256"] != job["input_sha256"] or meta["kind"] != job["kind"]
                    or meta["training_input"]["capsule_sha256"] != job["input_sha256"]):
                raise MaterialsError("Training output does not match its frozen task")
            comparison = meta["comparison"]
            digest = lambda v: hashlib.sha256(json.dumps(v, sort_keys=True, separators=(",", ":"),
                                                       ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()
            binding = meta["training_input"]
            if (comparison["test_sha256"] != digest(expected["split"]["test"])
                    or comparison["test_samples"] != len(expected["split"]["test"])
                    or comparison["candidate"] != meta["metrics"]["test"]
                    or binding["split_sha256"] != digest(expected["split"])
                    or binding["split_counts"] != {k: len(v) for k, v in expected["split"].items()}
                    or any(binding[role + "_model"] != expected[role + "_model"] for role in ("base", "baseline"))):
                raise MaterialsError("Evaluation does not match the frozen test set and model roles")
            score = comparison["candidate"]["normalized_rmse"]
            baseline = comparison["baseline"]
            finite = lambda value: type(value) in (int, float) and math.isfinite(value) and value >= 0
            reason = None
            if not finite(score) or score > job["gate"]:
                reason = "absolute_gate"
            elif job["baseline_version"] is not None and (baseline is None or
                    not finite(baseline["normalized_rmse"]) or score > baseline["normalized_rmse"]):
                reason = "baseline_regression"
            self._store.update(job_id, {"metrics": meta["metrics"], "comparison": comparison,
                                       "evaluation_preview": meta.get("evaluation_preview")})
            if reason is None:
                _, reason = self._register(staged, meta, job, cancel)
            if reason is not None:
                self._store.update(job_id, {"state": "rejected", "reason": reason, "finished_at": _now()})
        except training.Cancelled:
            self._store.update(job_id, {"state": "cancelled", "finished_at": _now()})
        except Exception as exc:  # noqa: BLE001 - preserve a terminal or uncertain receipt
            try:
                current = self._job(job_id)
                if current["state"] != "done":
                    self._store.update(job_id, {"state": "uncertain" if current.get("admission") else "failed",
                                               "error": str(exc)[:1000], "finished_at": _now()})
            except Exception:  # unavailable state cannot authorize another start
                pass
        finally:
            # A moved model is outside this uniquely owned attempt directory.
            try:
                if attempt.exists():
                    shutil.rmtree(attempt)
            finally:
                with self._lock:
                    self._workers.pop(job_id, None)
                lease.close()

    def shutdown(self):
        with self._lock:
            self._closed = True
            for cancel in self._workers.values():
                cancel.set()

    def predict(self, kind, rows, *, version=None):
        if kind not in curves.KINDS:
            raise MaterialsError(f"kind is one of {', '.join(curves.KINDS)}")
        if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_PREDICT_ROWS:
            raise MaterialsError(f"inputs are 1 to {MAX_PREDICT_ROWS} rows")
        with self._registry_read() as registry:
            entry = registry["kinds"].get(kind) or {"active": None, "versions": []}
            version = version or entry["active"]
            selected = next((v for v in entry["versions"] if v["version"] == version), None)
            if selected is None:
                raise MaterialsNotFound(f"No registered {kind} model" + (f" {version}" if version else ""))
        with self._lock:
            loaded = self._models.get((kind, version))
        if loaded is None:
            try:
                folder = self.root / "models" / kind / version
                if selected.get("model_sha256") and _sha(folder / "model.json", 1024 * 1024) != selected["model_sha256"]:
                    raise MaterialsUnavailable("Registered model metadata changed")
                loaded = training.load(folder)
            except training.TrainingUnavailable:
                raise
            except Exception as exc:  # noqa: BLE001 - damaged or missing model folder
                raise MaterialsUnavailable(f"The {kind} model {version} cannot be loaded: {type(exc).__name__}") from None
            with self._lock:
                self._models[(kind, version)] = loaded
        meta, predict = loaded
        try:
            predicted = predict(rows)
        except ValueError as exc:
            raise MaterialsError(str(exc)) from None
        return {"model": {"kind": kind, "version": version, "synthetic": meta["dataset"]["synthetic"],
                          "dataset": meta["dataset"]["name"], "metrics": meta["metrics"]["test"]},
                "grid": meta["grid"],
                "results": [{"curve": curve, "readout": curves.readout(kind, curve, row)} for curve, row in zip(predicted, rows)]}


__all__ = ["GATES", "MaterialsBusy", "MaterialsError", "MaterialsNotFound", "MaterialsService", "MaterialsUnavailable"]
