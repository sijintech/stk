"""Training a curve model (docs/design/materials-models-s3.md): a small multilayer perceptron from standardized inputs to
the standardized curve, on this computer's CPU with PyTorch (an optional dependency: ``pip install torch --index-url
https://download.pytorch.org/whl/cpu``). Missing curve points are masked. Deterministic for a seed.

A model folder holds ``model.pt`` (weights only) and ``model.json`` (kind, inputs, grid, normalization, layers,
dataset digest and whether it is synthetic, metrics). Loading never unpickles objects (``weights_only``).
"""
from datetime import datetime, timezone
from copy import deepcopy
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import stat
import time

import numpy as np

from . import curves, datasets, inputs as training_inputs

MODEL_FORMAT = "stk.curve-model/1"
MIN_SAMPLES = 20
DEFAULTS = deepcopy(training_inputs.DEFAULTS)
_MAX_METADATA_BYTES = 1024 * 1024
_MAX_WEIGHTS_BYTES = 256 * 1024 * 1024


class TrainingUnavailable(RuntimeError):
    """PyTorch is not installed."""


class Cancelled(RuntimeError):
    """Training was cancelled."""


def torch_module():
    try:
        import torch
    except ImportError:
        raise TrainingUnavailable("Training needs PyTorch (CPU): pip install torch --index-url "
                                  "https://download.pytorch.org/whl/cpu") from None
    return torch


def _network(torch, inputs, outputs, hidden):
    layers, width = [], inputs
    for size in hidden:
        layers += [torch.nn.Linear(width, size), torch.nn.SiLU()]
        width = size
    layers.append(torch.nn.Linear(width, outputs))
    return torch.nn.Sequential(*layers)


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                                     allow_nan=False).encode("utf-8")).hexdigest()


def _cancel(cancel):
    if cancel is not None and cancel.is_set():
        raise Cancelled("Training was cancelled")


def _indices(samples, split, settings):
    ids = [sample["id"] for sample in samples]
    expected = training_inputs.partition(ids, settings["split"], settings["seed"])
    if split != expected:
        raise datasets.DatasetError("Training partitions differ from the complete, disjoint frozen sample split")
    by_id = {identity: index for index, identity in enumerate(ids)}
    return {name: [by_id[identity] for identity in selected] for name, selected in split.items()}


def _arrays(description, samples):
    names = [item["name"] for item in description["inputs"]]
    x = np.array([[sample["inputs"][name] for name in names] for sample in samples], dtype=np.float64)
    y = np.array([[np.nan if value is None else value for value in sample["curve"]] for sample in samples], dtype=np.float64)
    return names, x, y


def _metrics(kind, predicted, y, samples):
    if not np.isfinite(predicted).all():
        raise datasets.DatasetError("Model predictions are not finite")
    mask = ~np.isnan(y)
    errors = (predicted - np.nan_to_num(y))[mask]
    rmse = float(math.sqrt(np.mean(errors ** 2))) if errors.size else None
    spread = float(np.std(y[mask])) if mask.any() else None
    result = {"samples": len(samples), "rmse": rmse,
              "normalized_rmse": rmse / spread if rmse is not None and spread else None}
    truth = [curves.readout(kind, sample["curve"], sample["inputs"]) for sample in samples]
    guess = [curves.readout(kind, list(row), sample["inputs"]) for row, sample in zip(predicted, samples)]
    for key in truth[0] if truth else ():
        pairs = [(a[key], b[key]) for a, b in zip(truth, guess)
                 if a[key] is not None and b[key] is not None and math.isfinite(a[key]) and math.isfinite(b[key])]
        result[f"{key}_mae"] = float(np.mean([abs(a - b) for a, b in pairs])) if pairs else None
        result[f"{key}_pairs"] = len(pairs)
    return result


def _read_model_file(path, maximum):
    before = path.lstat()
    def linked(info):
        return stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400
    def identity(info):
        return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns
    if linked(before) or not stat.S_ISREG(before.st_mode) or before.st_size > maximum:
        raise ValueError("Model files must be bounded regular files, without links or reparse points")
    with path.open("rb") as stream:
        opened = os.fstat(stream.fileno())
        if linked(opened) or identity(opened) != identity(before):
            raise ValueError("Model file changed before reading")
        raw = stream.read(maximum + 1)
        after = os.fstat(stream.fileno())
    current = path.lstat()
    if (len(raw) != before.st_size or len(raw) > maximum or identity(opened) != identity(after)
            or opened.st_ctime_ns != after.st_ctime_ns or linked(current) or identity(after) != identity(current)):
        raise ValueError("Model file changed while reading")
    return raw


def _model_metadata(meta):
    if type(meta) is not dict or meta.get("format") != MODEL_FORMAT or meta.get("kind") not in curves.KINDS:
        raise ValueError("Not an STK curve model")
    kind = meta["kind"]
    fields = meta.get("inputs")
    if (type(fields) is not list or not 1 <= len(fields) <= datasets.MAX_INPUTS or
            any(type(field) is not dict or type(field.get("name")) is not str or not field["name"] for field in fields) or
            len({field["name"] for field in fields}) != len(fields) or meta.get("grid") != curves.grid(kind)):
        raise ValueError("Model kind, ordered inputs or curve grid is invalid")
    layers = meta.get("layers")
    if type(layers) is not dict or layers.get("activation") != "silu":
        raise ValueError("Model network activation is unsupported; it cannot be reinterpreted")
    # Use the same published architecture limits as new frozen training options.
    hidden = training_inputs.normalize_options({"hidden": layers.get("hidden")})["hidden"]
    normal = meta.get("normalization")
    lengths = {"x_mean": len(fields), "x_std": len(fields), "y_mean": curves.length(kind), "y_std": curves.length(kind)}
    if type(normal) is not dict or set(normal) != set(lengths):
        raise ValueError("Model normalization is invalid")
    norm = {}
    for name, count in lengths.items():
        values = normal[name]
        if (type(values) is not list or len(values) != count or
                any(type(value) not in (int, float) or not math.isfinite(value) for value in values)):
            raise ValueError("Model normalization must have finite vectors of the declared dimensions")
        norm[name] = np.asarray(values, dtype=np.float64)
        if name.endswith("_std") and (norm[name] <= 0).any():
            raise ValueError("Model normalization scales must be positive")
    return hidden, norm


def _load_components(folder, *, torch=None, binding=None):
    folder = Path(folder)
    metadata = _read_model_file(folder / "model.json", _MAX_METADATA_BYTES)
    weights = _read_model_file(folder / "model.pt", _MAX_WEIGHTS_BYTES)
    if binding is not None and (hashlib.sha256(metadata).hexdigest() != binding["model_sha256"] or
            hashlib.sha256(weights).hexdigest() != binding["weights_sha256"] or
            len(metadata) != binding["model_size"] or len(weights) != binding["weights_size"]):
        raise ValueError("Model files differ from their frozen training-input binding")
    def pairs(items):
        result = {}
        for name, value in items:
            if name in result:
                raise ValueError("Duplicate model metadata member")
            result[name] = value
        return result
    def constant(value):
        raise ValueError("Model metadata must contain finite JSON numbers")
    meta = json.loads(metadata.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant)
    hidden, norm = _model_metadata(meta)
    expected = meta.get("weights_sha256")
    verified = "weights_sha256" in meta
    if verified and (type(expected) is not str or not re.fullmatch("[a-f0-9]{64}", expected) or
                     hashlib.sha256(weights).hexdigest() != expected):
        raise ValueError("Model weights checksum does not match its metadata")
    # Verify the bytes above before any deserialization; load those same bytes.
    torch = torch_module() if torch is None else torch
    model = _network(torch, len(meta["inputs"]), curves.length(meta["kind"]), hidden).double()
    model.load_state_dict(torch.load(io.BytesIO(weights), weights_only=True, map_location="cpu"), strict=True)
    if any(not bool(torch.isfinite(parameter).all()) for parameter in model.parameters()):
        raise ValueError("Model weights are not finite")
    model.eval()
    meta = {**meta, "weights_verified": verified,
            "weights_integrity": "sha256" if verified else "legacy_unverified"}
    return meta, model, norm


def _compatible(meta, description, *, hidden=None):
    fields = lambda values: [(value["name"], value.get("unit")) for value in values]
    if (meta["kind"] != description["target"]["kind"] or meta["grid"] != description["target"]["grid"] or
            fields(meta["inputs"]) != fields(description["inputs"])):
        raise ValueError("Frozen model kind, grid or ordered input fields/units are incompatible with the dataset")
    if hidden is not None and meta["layers"]["hidden"] != hidden:
        raise ValueError("Frozen base model network architecture differs from the training options")


def _predict(torch, model, norm, x, *, cancel=None):
    rows = []
    with torch.no_grad():
        for start in range(0, len(x), 1024):
            _cancel(cancel)
            values = model(torch.from_numpy((x[start:start + 1024] - norm["x_mean"]) / norm["x_std"])).numpy()
            rows.append(values * norm["y_std"] + norm["y_mean"])
    return np.concatenate(rows) if rows else np.empty((0, len(norm["y_mean"])), dtype=np.float64)


def train(directory, output, *, options=None, progress=None, cancel=None, frozen=False):
    """Train on the dataset in ``directory`` and write a model folder ``output``; returns its ``model.json``.
    ``progress(epoch, train_loss, validation_loss)`` is called each epoch; ``cancel`` (an Event) stops it.
    With ``frozen=True``, only verified capsule bytes and its exact options/split are used;
    its base initializes the candidate and its independent baseline is evaluated only.
    """
    _cancel(cancel)
    if type(frozen) is not bool:
        raise ValueError("frozen must be a boolean")
    manifest = None
    if frozen:
        if Path(output).resolve().is_relative_to(Path(directory).resolve()):
            raise ValueError("Training output must not modify its frozen input capsule")
        manifest, description, samples = training_inputs.load(directory)
        settings = training_inputs.normalize_options(manifest["options"])
        if settings != manifest["options"]:
            raise ValueError("Frozen training options are not normalized")
        if options is not None:
            if type(options) is not dict or training_inputs.normalize_options({**settings, **options}) != settings:
                raise ValueError("Training options differ from the frozen input capsule")
        split = manifest["split"]
    else:
        settings = training_inputs.normalize_options(options)
        description, samples = datasets.load(directory)
        split = training_inputs.partition([sample["id"] for sample in samples], settings["split"], settings["seed"])
    kind = description["target"]["kind"]
    if len(samples) < MIN_SAMPLES:
        raise datasets.DatasetError(f"Training needs at least {MIN_SAMPLES} samples (so the test set has several)")
    names, x, y = _arrays(description, samples)
    indices = _indices(samples, split, settings)
    train_index, validation_index, test_index = (indices[name] for name in ("train", "validation", "test"))
    observed = (~np.isnan(y[train_index])).sum(axis=0)
    if (observed == 0).any():
        missing = np.flatnonzero(observed == 0)
        raise datasets.DatasetError("Training partition has no observations for output positions " +
                                    ", ".join(map(str, missing[:16])) + (" ..." if len(missing) > 16 else ""))
    _cancel(cancel)
    torch = torch_module()
    torch.set_num_threads(max(1, min(8, torch.get_num_threads())))
    roles, role_bindings = {}, {name: manifest[name + "_model"] if manifest else None for name in ("base", "baseline")}
    for role, binding in role_bindings.items():
        if binding is not None:
            loaded = _load_components(Path(directory) / role, torch=torch, binding=binding)
            _compatible(loaded[0], description, hidden=settings["hidden"] if role == "base" else None)
            roles[role] = loaded
    if "base" in roles:
        _, base, norm = roles["base"]
        norm = {name: value.copy() for name, value in norm.items()}
        model = deepcopy(base)
    else:
        x_mean, x_std = x[train_index].mean(axis=0), x[train_index].std(axis=0)
        x_std[x_std == 0] = 1.0
        y_mean, y_std = np.nanmean(y[train_index], axis=0), np.nanstd(y[train_index], axis=0)
        y_std[y_std == 0] = 1.0
        norm = {"x_mean": x_mean, "x_std": x_std, "y_mean": y_mean, "y_std": y_std}
        torch.manual_seed(settings["seed"])
        model = _network(torch, len(names), y.shape[1], settings["hidden"]).double()
    # Loading comparison models must not affect initialization or batch ordering.
    torch.manual_seed(settings["seed"])
    x_mean, x_std, y_mean, y_std = (norm[name] for name in ("x_mean", "x_std", "y_mean", "y_std"))
    optimizer = torch.optim.Adam(model.parameters(), lr=settings["learning_rate"])

    def tensors(index):
        xs = torch.from_numpy((x[index] - x_mean) / x_std)
        ys = torch.from_numpy(np.nan_to_num((y[index] - y_mean) / y_std))
        mask = torch.from_numpy(~np.isnan(y[index]))
        return xs, ys, mask

    def loss(xs, ys, mask):
        return (((model(xs) - ys) ** 2) * mask).sum() / mask.sum().clamp(min=1)

    train_x, train_y, train_mask = tensors(train_index)
    check = tensors(validation_index)
    generator = torch.Generator().manual_seed(settings["seed"])
    best, best_state, best_epoch, waited, started = math.inf, None, 0, 0, time.monotonic()
    for epoch in range(1, settings["epochs"] + 1):
        _cancel(cancel)
        model.train()
        order = torch.randperm(len(train_index), generator=generator)
        total, total_observed = 0.0, 0
        for start in range(0, len(train_index), settings["batch_size"]):
            _cancel(cancel)
            batch = order[start:start + settings["batch_size"]]
            optimizer.zero_grad()
            value = loss(train_x[batch], train_y[batch], train_mask[batch])
            if not bool(torch.isfinite(value)):
                raise datasets.DatasetError("Training loss is not finite")
            value.backward()
            optimizer.step()
            count = int(train_mask[batch].sum())
            total += value.item() * count
            total_observed += count
        model.eval()
        with torch.no_grad():
            validation = float(loss(*check))
        if not math.isfinite(validation):
            raise datasets.DatasetError("Validation loss is not finite")
        if progress is not None:
            progress(epoch, total / total_observed, validation)
        _cancel(cancel)
        if validation < best - 1e-9:
            best, best_epoch, waited = validation, epoch, 0
            best_state = {key: value.clone() for key, value in model.state_dict().items()}
        else:
            waited += 1
            if waited >= settings["patience"]:
                break
    _cancel(cancel)
    model.load_state_dict(best_state)
    model.eval()

    def evaluate(net, normal, index):
        return _metrics(kind, _predict(torch, net, normal, x[index], cancel=cancel),
                        y[index], [samples[i] for i in index])

    metrics = {"test": evaluate(model, norm, test_index),
               "train": evaluate(model, norm, train_index),
               "epochs": epoch, "best_epoch": best_epoch, "seconds": round(time.monotonic() - started, 2)}
    comparison = {"format": "stk.materials-training-comparison/1", "test_sha256": _digest(split["test"]),
                  "test_samples": len(test_index), "candidate": metrics["test"],
                  "base": None, "baseline": None}
    for role, (_, net, normal) in roles.items():
        comparison[role] = evaluate(net, normal, test_index)
    preview_index = test_index[:3]
    preview_predictions = {"candidate": _predict(torch, model, norm, x[preview_index], cancel=cancel).tolist()}
    for role, (_, net, normal) in roles.items():
        preview_predictions[role] = _predict(torch, net, normal, x[preview_index], cancel=cancel).tolist()
    evaluation_preview = {"grid": curves.grid(kind), "samples": [
        {"id": samples[index]["id"], "inputs": deepcopy(samples[index]["inputs"]),
         "observed": list(samples[index]["curve"]),
         **{role: preview_predictions[role][position] if role in preview_predictions else None
            for role in ("candidate", "base", "baseline")}}
        for position, index in enumerate(preview_index)]}
    buffer = io.BytesIO()
    torch.save(model.state_dict(), buffer)
    weights = buffer.getvalue()
    meta = {"format": MODEL_FORMAT, "kind": kind, "inputs": description["inputs"], "grid": curves.grid(kind),
            "normalization": {"x_mean": x_mean.tolist(), "x_std": x_std.tolist(), "y_mean": y_mean.tolist(),
                              "y_std": y_std.tolist()},
            "layers": {"hidden": settings["hidden"], "activation": "silu"}, "options": settings,
            "dataset": {"name": str(description.get("name", ""))[:200], "sha256": datasets.digest(description, samples),
                        "samples": len(samples), "synthetic": description["synthetic"],
                        "license": str(description.get("license", ""))[:100], "sensitivity": description.get("sensitivity")},
            "metrics": metrics, "comparison": comparison, "evaluation_preview": evaluation_preview,
            "weights_sha256": hashlib.sha256(weights).hexdigest(),
            "training_input": {"capsule_sha256": manifest["sha256"] if manifest else None,
                               "split_sha256": _digest(split),
                               "split_counts": {name: len(ids) for name, ids in split.items()},
                               "base_model": role_bindings["base"], "baseline_model": role_bindings["baseline"]},
            "created_at": datetime.now(timezone.utc).isoformat(), "torch": torch.__version__}
    # allow_nan=False: a number that cannot be written as JSON fails here, never later in every read of the registry.
    metadata = json.dumps(meta, ensure_ascii=False, indent=1, allow_nan=False) + "\n"
    if len(metadata.encode("utf-8")) > _MAX_METADATA_BYTES or len(weights) > _MAX_WEIGHTS_BYTES:
        raise ValueError("Trained model exceeds its metadata or weights byte budget")
    _cancel(cancel)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    (output / "model.pt").write_bytes(weights)
    (output / "model.json").write_text(metadata, encoding="utf-8")
    return meta


def load(folder):
    """``(meta, predict)`` for a model folder: ``predict(list of {name: number})`` returns curves (lists)."""
    torch = torch_module()
    meta, model, norm = _load_components(folder, torch=torch)
    names = [item["name"] for item in meta["inputs"]]

    def predict(rows):
        for row in rows:
            if set(row) != set(names) or not all(type(row[name]) in (int, float) and math.isfinite(row[name]) for name in names):
                raise ValueError(f"Each input row gives a finite number for each of {', '.join(names)}")
        x = np.array([[row[name] for name in names] for row in rows], dtype=np.float64).reshape((-1, len(names)))
        result = _predict(torch, model, norm, x)
        if not np.isfinite(result).all():
            raise ValueError("Model predictions are not finite")
        return result.tolist()
    return meta, predict


__all__ = ["Cancelled", "DEFAULTS", "MODEL_FORMAT", "TrainingUnavailable", "load", "torch_module", "train"]
