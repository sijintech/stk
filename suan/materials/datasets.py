"""Dataset contract ``stk.dataset/1`` (docs/design/materials-models-s3.md): a folder with ``dataset.json`` (what the
samples are) and ``samples.jsonl`` (one sample per line: ``{"id", "inputs": {name: number}, "curve": [number | null]}``).

``dataset.json``::

    {"format": "stk.dataset/1", "name": ..., "target": {"kind": "pe_loop" | "capacity_fade", "grid": {...}},
     "inputs": [{"name", "unit"}], "source": ..., "license": ..., "sensitivity": "private" | "public",
     "synthetic": bool, "generator": {...} | null}

The validator runs here only; its data card (counts, ranges, missing values, readouts) stays on this computer.
"""
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from . import curves, synthetic

FORMAT = "stk.dataset/1"
MAX_SAMPLES = 100000
MAX_INPUTS = 64
SENSITIVITY = ("private", "public")


class DatasetError(ValueError):
    """The folder is not a valid ``stk.dataset/1`` dataset."""


def write_synthetic(directory, kind, count, *, seed=0, name=None):
    """Make a labelled synthetic dataset of ``count`` samples in a new (or empty) folder; returns its data card."""
    directory = Path(directory)
    if directory.exists() and any(directory.iterdir()):
        raise DatasetError("The dataset folder is not empty")
    inputs, samples = synthetic.generate(kind, count, seed=seed)
    description = {"format": FORMAT, "name": name or f"Synthetic {kind} ({count})",
                   "target": {"kind": kind, "grid": curves.grid(kind)}, "inputs": inputs,
                   "source": "STK synthetic generator (for testing the chain only; not a material's data)",
                   "license": "CC0-1.0", "sensitivity": "public", "synthetic": True,
                   "generator": {"name": f"stk.synthetic.{kind}", "version": synthetic.GENERATOR_VERSION, "seed": seed}}
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "dataset.json").write_text(json.dumps(description, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    with open(directory / "samples.jsonl", "w", encoding="utf-8") as handle:
        for sample in samples:
            handle.write(json.dumps(sample, separators=(",", ":")) + "\n")
    return validate(directory)


def load(directory):
    """``(description, samples)`` after validation (raises ``DatasetError`` listing the first problems)."""
    description, samples, problems = _read(Path(directory))
    if problems:
        raise DatasetError("; ".join(problems[:5]))
    return description, samples


MAX_PROBLEMS = 200
MAX_PROBLEM_CHARS = 500
VALUE_LIMIT = 1e12  # inputs and curve points beyond this are refused (they would only overflow the statistics)
SOH_RANGE = (0.0, 1.5)


def _number(value):
    try:
        return type(value) in (int, float) and math.isfinite(value) and abs(value) <= VALUE_LIMIT
    except OverflowError:  # an integer too large for a float
        return False


def _read(directory):
    problems = []

    def problem(text):
        if len(problems) < MAX_PROBLEMS:
            problems.append(text if len(text) <= MAX_PROBLEM_CHARS else text[:MAX_PROBLEM_CHARS - 1] + "…")
    try:
        description = json.loads((directory / "dataset.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:  # a decoding error is a ValueError too
        problem(f"dataset.json cannot be read: {type(exc).__name__}")
        return None, [], problems
    if not isinstance(description, dict) or description.get("format") != FORMAT:
        return description, [], [f"dataset.json is not {FORMAT}"]
    target = description.get("target")
    kind = target.get("kind") if isinstance(target, dict) else None
    if kind not in curves.KINDS:
        problem(f"target is an object whose kind is one of {', '.join(curves.KINDS)}")
        return description, [], problems
    if target.get("grid") != curves.grid(kind):
        problem(f"target.grid must be the {kind} grid of {FORMAT}")
    inputs = description.get("inputs")
    if (not isinstance(inputs, list) or not 1 <= len(inputs) <= MAX_INPUTS
            or not all(isinstance(item, dict) and isinstance(item.get("name"), str) and 1 <= len(item["name"]) <= 64
                       for item in inputs)
            or len({item["name"] for item in inputs}) != len(inputs)):
        problem(f"inputs are 1 to {MAX_INPUTS} fields with distinct names of 1 to 64 characters")
        return description, [], problems
    names = [item["name"] for item in inputs]
    if kind == "pe_loop" and "e_max" not in names:
        problem("a pe_loop dataset has the input e_max (kV/cm): the loop's field grid is E / E_max")
        return description, [], problems
    if description.get("sensitivity") not in SENSITIVITY:
        problem("sensitivity is private or public")
    if type(description.get("synthetic")) is not bool:
        problem("synthetic is true or false")
    for key in ("name", "source", "license"):
        if key in description and not isinstance(description[key], str):
            problem(f"{key} is text")
    length, samples, ids = curves.length(kind), [], set()
    try:
        handle = open(directory / "samples.jsonl", encoding="utf-8")
    except OSError as exc:
        problem(f"samples.jsonl cannot be read: {exc.strerror or type(exc).__name__}")
        return description, [], problems
    with handle:
        try:
            for number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                if len(samples) >= MAX_SAMPLES:
                    problem(f"at most {MAX_SAMPLES} samples")
                    break
                if len(problems) >= MAX_PROBLEMS:
                    break
                try:
                    sample = json.loads(line)
                except (ValueError, RecursionError):
                    problem(f"line {number}: not JSON")
                    continue
                if not isinstance(sample, dict):
                    problem(f"line {number}: a sample is a JSON object")
                    continue
                values, curve = sample.get("inputs"), sample.get("curve")
                if not isinstance(values, dict) or set(values) != set(names) or not all(_number(values[name]) for name in names):
                    problem(f"line {number}: inputs give a number (at most 1e12 in size) for each input of dataset.json")
                    continue
                if kind == "pe_loop" and values["e_max"] <= 0:
                    problem(f"line {number}: e_max is positive")
                    continue
                if (not isinstance(curve, list) or len(curve) != length
                        or not all(value is None or _number(value) for value in curve)):
                    problem(f"line {number}: curve is {length} numbers (null where not measured)")
                    continue
                if kind == "capacity_fade" and not all(value is None or SOH_RANGE[0] <= value <= SOH_RANGE[1] for value in curve):
                    problem(f"line {number}: SOH values are between 0 and 1.5")
                    continue
                if sum(value is not None for value in curve) < 2:
                    problem(f"line {number}: curve has fewer than 2 measured points")
                    continue
                identity = str(sample.get("id", number))[:128]
                if identity in ids:
                    problem(f"line {number}: id {identity} is used twice")
                    continue
                ids.add(identity)
                samples.append({"id": identity, "inputs": values, "curve": curve})
        except UnicodeDecodeError:
            problem("samples.jsonl is not UTF-8 text")
    if not samples and not problems:
        problem("samples.jsonl has no samples")
    return description, samples, problems


def digest(description, samples):
    """SHA-256 of the dataset's canonical content (what a trained model records)."""
    hasher = hashlib.sha256(json.dumps(description, sort_keys=True, separators=(",", ":")).encode())
    for sample in samples:
        hasher.update(json.dumps(sample, sort_keys=True, separators=(",", ":")).encode())
    return hasher.hexdigest()


def _summary(values):
    present = np.array([value for value in values if value is not None and math.isfinite(value)], dtype=np.float64)
    if present.size == 0:
        return {"count": 0, "missing": len(values)}
    return {"count": int(present.size), "missing": len(values) - int(present.size), "min": float(present.min()),
            "max": float(present.max()), "mean": float(present.mean()), "std": float(present.std())}


def validate(directory):
    """The data card of a dataset folder: {ok, problems, name, kind, synthetic, sensitivity, samples, inputs (summaries),
    curve (summary of all points), readouts (summaries), sha256}. Never raises for content problems."""
    description, samples, problems = _read(Path(directory))
    card = {"ok": not problems, "problems": problems[:50], "samples": len(samples)}
    target = description.get("target") if isinstance(description, dict) else None
    if not isinstance(target, dict) or target.get("kind") not in curves.KINDS:
        return card
    kind = target["kind"]
    synthetic_flag, sensitivity = description.get("synthetic"), description.get("sensitivity")
    card.update(name=str(description.get("name", ""))[:200], kind=kind,
                synthetic=synthetic_flag if type(synthetic_flag) is bool else None,
                sensitivity=sensitivity if sensitivity in SENSITIVITY else None,
                source=str(description.get("source", ""))[:500], license=str(description.get("license", ""))[:100])
    if isinstance(description.get("generator"), dict):
        card["generator"] = {key: str(value)[:100] for key, value in list(description["generator"].items())[:8]}
    if not samples:
        return card
    names = [item["name"] for item in description["inputs"]]
    card["inputs"] = {name: _summary([sample["inputs"][name] for sample in samples]) for name in names}
    card["curve"] = _summary([value for sample in samples for value in sample["curve"]])
    readouts = [curves.readout(kind, sample["curve"], sample["inputs"]) for sample in samples]
    card["readouts"] = {key: _summary([item[key] for item in readouts]) for key in readouts[0]}
    card["sha256"] = digest(description, samples)
    return card


__all__ = ["DatasetError", "FORMAT", "digest", "load", "validate", "write_synthetic"]
