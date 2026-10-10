"""The materials models of this computer (docs/design/materials-models-s3.md): datasets, background training jobs, a model
registry with an evaluation gate and rollback, and prediction. Everything stays on this computer.

Registry (``<root>/registry.json``)::

    {"kinds": {"pe_loop": {"active": "v2", "versions": [{"version", "created_at", "dataset", "metrics", "gate"}]}}}

Models live in ``<root>/models/<kind>/<version>/``. A training job writes its model to ``<root>/staging/<job>/``; it is
registered (and becomes active) only when its test metrics pass the gate, otherwise it is discarded. Jobs are kept in
memory: a job of a service that stopped is gone, but the models it registered stay.
"""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import threading

from . import curves, datasets, training

# The test set's curve error relative to the curves' spread (normalized RMSE) a model must reach to be registered.
GATES = {"pe_loop": 0.25, "capacity_fade": 0.1}
MAX_PREDICT_ROWS = 100


class MaterialsError(ValueError):
    """A request the materials service cannot carry out."""


class MaterialsNotFound(MaterialsError):
    """No such job, model kind or version."""


class MaterialsBusy(MaterialsError):
    """A training job is already running (one at a time)."""


class MaterialsUnavailable(RuntimeError):
    """The registry cannot be read (for example a damaged registry.json)."""


def _now():
    return datetime.now(timezone.utc).isoformat()


class MaterialsService:
    def __init__(self, root):
        self.root = Path(root)
        self._lock = threading.Lock()
        self._jobs = {}
        self._models = {}  # (kind, version) -> (meta, predict)

    # ---- registry ----

    def _registry(self):
        try:
            registry = json.loads((self.root / "registry.json").read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {"kinds": {}}
        except (OSError, ValueError) as exc:
            raise MaterialsUnavailable(f"The model registry ({self.root / 'registry.json'}) cannot be read: "
                                       f"{type(exc).__name__}") from None
        if (not isinstance(registry, dict) or not isinstance(registry.get("kinds"), dict)
                or not all(isinstance(entry, dict) and isinstance(entry.get("versions"), list)
                           for entry in registry["kinds"].values())):
            raise MaterialsUnavailable(f"The model registry ({self.root / 'registry.json'}) is damaged")
        return registry

    def _save(self, registry):
        self.root.mkdir(parents=True, exist_ok=True)
        temporary = self.root / "registry.json.tmp"
        temporary.write_text(json.dumps(registry, ensure_ascii=False, indent=1, allow_nan=False) + "\n", encoding="utf-8")
        temporary.replace(self.root / "registry.json")

    def models(self, kind=None):
        """Registered versions per kind, newest last, with the active one."""
        if kind is not None and kind not in curves.KINDS:
            raise MaterialsError(f"kind is one of {', '.join(curves.KINDS)}")
        with self._lock:
            registry = self._registry()
        kinds = {name: registry["kinds"].get(name, {"active": None, "versions": []})
                 for name in ([kind] if kind else curves.KINDS)}
        return {"kinds": kinds, "gates": GATES}

    def activate(self, kind, version):
        """Use another registered version (for example to roll back)."""
        with self._lock:
            registry = self._registry()
            entry = registry["kinds"].get(kind)
            if not entry or version not in [item["version"] for item in entry["versions"]]:
                raise MaterialsNotFound("No such model version")
            entry["active"] = version
            self._save(registry)
            return entry

    def _register(self, staged, meta, gate, cancel):
        kind = meta["kind"]
        with self._lock:
            if cancel.is_set():
                raise training.Cancelled("Training was cancelled")
            registry = self._registry()
            entry = registry["kinds"].setdefault(kind, {"active": None, "versions": []})
            # The next number after every version the registry or the models folder knows (a folder left by a lost
            # registry is never reused, so a version always names the weights it was registered with).
            folder = self.root / "models" / kind
            numbers = [int(match.group(1)) for name in [item["version"] for item in entry["versions"]] +
                       ([path.name for path in folder.iterdir()] if folder.exists() else [])
                       if (match := re.fullmatch(r"v(\d+)", str(name)))]
            version = f"v{max(numbers, default=0) + 1}"
            target = folder / version
            folder.mkdir(parents=True, exist_ok=True)
            os.rename(staged, target)  # fails rather than moving into an existing folder
            self._models.pop((kind, version), None)
            entry["versions"].append({"version": version, "created_at": meta["created_at"], "dataset": meta["dataset"],
                                      "metrics": meta["metrics"]["test"], "gate": gate})
            entry["active"] = version
            self._save(registry)
            return version

    # ---- training ----

    def train(self, directory, job_id, *, options=None):
        """Start training on the dataset in ``directory`` in the background; the same job ID again returns the job."""
        with self._lock:
            if job_id in self._jobs:
                return self._public(self._jobs[job_id])
            if any(job["state"] == "running" for job in self._jobs.values()):
                raise MaterialsBusy("Another model is being trained; wait for it or cancel it")
        training.torch_module()
        card = datasets.validate(directory)  # outside the lock: reading a large dataset takes seconds
        if not card["ok"]:
            raise MaterialsError("The dataset is not valid: " + "; ".join(card["problems"][:3]))
        with self._lock:
            if job_id in self._jobs:
                return self._public(self._jobs[job_id])
            if any(job["state"] == "running" for job in self._jobs.values()):
                raise MaterialsBusy("Another model is being trained; wait for it or cancel it")
            job = {"id": job_id, "kind": card["kind"], "state": "running", "dataset": str(directory),
                   "synthetic": card["synthetic"], "epoch": 0, "epochs": (options or {}).get("epochs", training.DEFAULTS["epochs"]),
                   "train_loss": None, "validation_loss": None, "error": None, "version": None, "metrics": None,
                   "gate": GATES[card["kind"]], "started_at": _now(), "finished_at": None}
            self._jobs[job_id] = job
            cancel = threading.Event()
            self._jobs[job_id]["_cancel"] = cancel
        thread = threading.Thread(target=self._run, args=(job_id, directory, options or {}, cancel), name="stk-materials-train",
                                  daemon=True)
        thread.start()
        return self.job(job_id)

    def _run(self, job_id, directory, options, cancel):
        staged = self.root / "staging" / job_id

        def progress(epoch, train_loss, validation_loss):
            with self._lock:
                self._jobs[job_id].update(epoch=epoch, train_loss=train_loss, validation_loss=validation_loss)
        try:
            if staged.exists():
                shutil.rmtree(staged)
            staged.parent.mkdir(parents=True, exist_ok=True)
            meta = training.train(directory, staged, options=options, progress=progress, cancel=cancel)
            if cancel.is_set():
                raise training.Cancelled("Training was cancelled")
            test = meta["metrics"]["test"]
            gate = GATES[meta["kind"]]
            passed = test["normalized_rmse"] is not None and test["normalized_rmse"] <= gate
            version = self._register(staged, meta, gate, cancel) if passed else None
            if not passed:
                shutil.rmtree(staged, ignore_errors=True)
            with self._lock:
                self._jobs[job_id].update(state="done" if passed else "rejected", version=version, metrics=meta["metrics"])
        except training.Cancelled:
            shutil.rmtree(staged, ignore_errors=True)
            with self._lock:
                self._jobs[job_id].update(state="cancelled")
        except Exception as exc:  # noqa: BLE001 - a job ends recorded
            shutil.rmtree(staged, ignore_errors=True)
            with self._lock:
                self._jobs[job_id].update(state="failed", error=str(exc)[:1000])
        finally:
            with self._lock:
                self._jobs[job_id]["finished_at"] = _now()

    @staticmethod
    def _public(job):
        return {key: value for key, value in job.items() if not key.startswith("_")}

    def job(self, job_id):
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise MaterialsNotFound("No such training job in this service")
            return self._public(job)

    def cancel(self, job_id):
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise MaterialsNotFound("No such training job in this service")
            job["_cancel"].set()
        return self.job(job_id)

    def shutdown(self):
        with self._lock:
            for job in self._jobs.values():
                job["_cancel"].set()

    # ---- prediction ----

    def predict(self, kind, rows, *, version=None):
        """Curves and their readouts for input rows, with which model made them and whether it learned from synthetic data."""
        if kind not in curves.KINDS:
            raise MaterialsError(f"kind is one of {', '.join(curves.KINDS)}")
        if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_PREDICT_ROWS:
            raise MaterialsError(f"inputs are 1 to {MAX_PREDICT_ROWS} rows")
        with self._lock:
            entry = self._registry()["kinds"].get(kind) or {"active": None, "versions": []}
            version = version or entry["active"]
            if version is None or version not in [item["version"] for item in entry["versions"]]:
                raise MaterialsNotFound(f"No registered {kind} model" + (f" {version}" if version else ""))
            loaded = self._models.get((kind, version))
        if loaded is None:
            try:
                loaded = training.load(self.root / "models" / kind / version)
            except training.TrainingUnavailable:
                raise
            except Exception as exc:  # noqa: BLE001 - a damaged or missing model folder
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
