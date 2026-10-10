"""Training a curve model (docs/design/materials-models-s3.md): a small multilayer perceptron from standardized inputs to
the standardized curve, on this computer's CPU with PyTorch (an optional dependency: ``pip install torch --index-url
https://download.pytorch.org/whl/cpu``). Missing curve points are masked. Deterministic for a seed.

A model folder holds ``model.pt`` (weights only) and ``model.json`` (kind, inputs, grid, normalization, layers,
dataset digest and whether it is synthetic, metrics). Loading never unpickles objects (``weights_only``).
"""
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import random
import time

import numpy as np

from . import curves, datasets

MODEL_FORMAT = "stk.curve-model/1"
MIN_SAMPLES = 20
DEFAULTS = {"hidden": [128, 128], "epochs": 400, "batch_size": 64, "learning_rate": 1e-3, "patience": 40, "seed": 0,
            "split": [0.7, 0.15, 0.15]}


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


def _split(count, fractions, seed):
    order = list(range(count))
    random.Random(seed).shuffle(order)
    train = max(1, int(round(count * fractions[0])))
    validation = max(1, int(round(count * fractions[1]))) if count >= 3 else 0
    return order[:train], order[train:train + validation], order[train + validation:]


def _arrays(description, samples):
    names = [item["name"] for item in description["inputs"]]
    x = np.array([[sample["inputs"][name] for name in names] for sample in samples], dtype=np.float64)
    y = np.array([[np.nan if value is None else value for value in sample["curve"]] for sample in samples], dtype=np.float64)
    return names, x, y


def _metrics(kind, predicted, y, samples):
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


def train(directory, output, *, options=None, progress=None, cancel=None):
    """Train on the dataset in ``directory`` and write a model folder ``output``; returns its ``model.json``.
    ``progress(epoch, train_loss, validation_loss)`` is called each epoch; ``cancel`` (an Event) stops it."""
    torch = torch_module()
    settings = {**DEFAULTS, **(options or {})}
    description, samples = datasets.load(directory)
    kind = description["target"]["kind"]
    if len(samples) < MIN_SAMPLES:
        raise datasets.DatasetError(f"Training needs at least {MIN_SAMPLES} samples (so the test set has several)")
    names, x, y = _arrays(description, samples)
    train_index, validation_index, test_index = _split(len(samples), settings["split"], settings["seed"])
    x_mean, x_std = x[train_index].mean(axis=0), x[train_index].std(axis=0)
    x_std[x_std == 0] = 1.0
    y_mean, y_std = np.nanmean(y[train_index], axis=0), np.nanstd(y[train_index], axis=0)
    y_mean, y_std = np.nan_to_num(y_mean), np.where(np.nan_to_num(y_std) == 0, 1.0, np.nan_to_num(y_std))
    torch.manual_seed(settings["seed"])
    torch.set_num_threads(max(1, min(8, torch.get_num_threads())))
    model = _network(torch, len(names), y.shape[1], settings["hidden"]).double()
    optimizer = torch.optim.Adam(model.parameters(), lr=settings["learning_rate"])

    def tensors(index):
        xs = torch.from_numpy((x[index] - x_mean) / x_std)
        ys = torch.from_numpy(np.nan_to_num((y[index] - y_mean) / y_std))
        mask = torch.from_numpy(~np.isnan(y[index]))
        return xs, ys, mask

    def loss(xs, ys, mask):
        return (((model(xs) - ys) ** 2) * mask).sum() / mask.sum().clamp(min=1)

    train_x, train_y, train_mask = tensors(train_index)
    check = tensors(validation_index or train_index)
    generator = torch.Generator().manual_seed(settings["seed"])
    best, best_state, best_epoch, waited, started = math.inf, None, 0, 0, time.monotonic()
    for epoch in range(1, settings["epochs"] + 1):
        if cancel is not None and cancel.is_set():
            raise Cancelled("Training was cancelled")
        model.train()
        order = torch.randperm(len(train_index), generator=generator)
        total = 0.0
        for start in range(0, len(train_index), settings["batch_size"]):
            batch = order[start:start + settings["batch_size"]]
            optimizer.zero_grad()
            value = loss(train_x[batch], train_y[batch], train_mask[batch])
            value.backward()
            optimizer.step()
            total += value.item() * len(batch)
        model.eval()
        with torch.no_grad():
            validation = float(loss(*check))
        if progress is not None:
            progress(epoch, total / len(train_index), validation)
        if validation < best - 1e-9:
            best, best_epoch, waited = validation, epoch, 0
            best_state = {key: value.clone() for key, value in model.state_dict().items()}
        else:
            waited += 1
            if waited >= settings["patience"]:
                break
    model.load_state_dict(best_state)
    model.eval()

    def predict(index):
        with torch.no_grad():
            out = model(torch.from_numpy((x[index] - x_mean) / x_std)).numpy()
        return out * y_std + y_mean

    evaluation = test_index or validation_index or train_index
    metrics = {"test": _metrics(kind, predict(evaluation), y[evaluation], [samples[i] for i in evaluation]),
               "train": _metrics(kind, predict(train_index), y[train_index], [samples[i] for i in train_index]),
               "epochs": epoch, "best_epoch": best_epoch, "seconds": round(time.monotonic() - started, 2)}
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    torch.save(model.state_dict(), output / "model.pt")
    meta = {"format": MODEL_FORMAT, "kind": kind, "inputs": description["inputs"], "grid": curves.grid(kind),
            "normalization": {"x_mean": x_mean.tolist(), "x_std": x_std.tolist(), "y_mean": y_mean.tolist(),
                              "y_std": y_std.tolist()},
            "layers": {"hidden": settings["hidden"], "activation": "silu"}, "options": settings,
            "dataset": {"name": str(description.get("name", ""))[:200], "sha256": datasets.digest(description, samples),
                        "samples": len(samples), "synthetic": description["synthetic"],
                        "license": str(description.get("license", ""))[:100], "sensitivity": description.get("sensitivity")},
            "metrics": metrics, "created_at": datetime.now(timezone.utc).isoformat(), "torch": torch.__version__}
    # allow_nan=False: a number that cannot be written as JSON fails here, never later in every read of the registry.
    (output / "model.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1, allow_nan=False) + "\n", encoding="utf-8")
    return meta


def load(folder):
    """``(meta, predict)`` for a model folder: ``predict(list of {name: number})`` returns curves (lists)."""
    torch = torch_module()
    folder = Path(folder)
    meta = json.loads((folder / "model.json").read_text(encoding="utf-8"))
    if meta.get("format") != MODEL_FORMAT:
        raise ValueError("Not an STK curve model")
    names = [item["name"] for item in meta["inputs"]]
    norm = {key: np.array(value) for key, value in meta["normalization"].items()}
    model = _network(torch, len(names), curves.length(meta["kind"]), meta["layers"]["hidden"]).double()
    model.load_state_dict(torch.load(folder / "model.pt", weights_only=True))
    model.eval()

    def predict(rows):
        for row in rows:
            if set(row) != set(names) or not all(type(row[name]) in (int, float) and math.isfinite(row[name]) for name in names):
                raise ValueError(f"Each input row gives a finite number for each of {', '.join(names)}")
        x = np.array([[row[name] for name in names] for row in rows], dtype=np.float64)
        with torch.no_grad():
            out = model(torch.from_numpy((x - norm["x_mean"]) / norm["x_std"])).numpy()
        return (out * norm["y_std"] + norm["y_mean"]).tolist()
    return meta, predict


__all__ = ["Cancelled", "DEFAULTS", "MODEL_FORMAT", "TrainingUnavailable", "load", "torch_module", "train"]
