"""Private, immutable inputs for local material training; no model is executed here.

The existing ``stk.dataset/1`` directory stays unchanged. A separate internal
``stk.materials-training-input/1`` capsule binds exact source bytes, the local
data card, options, held-out sample identities and optional model roles.
"""
from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import random
import shutil
import stat
import tempfile

from . import datasets

FORMAT = "stk.materials-training-input/1"
# Shared with training without importing it (and without importing torch).
DEFAULTS = {"hidden": [128, 128], "epochs": 400, "batch_size": 64,
            "learning_rate": 1e-3, "patience": 40, "seed": 0, "split": [0.7, 0.15, 0.15]}
MAX_MANIFEST_BYTES = 16 * 1024 * 1024
_LIMITS = {"dataset.json": 1024 * 1024, "samples.jsonl": 256 * 1024 * 1024,
           "model.json": 1024 * 1024, "model.pt": 256 * 1024 * 1024}
_FIELDS = {"format", "sha256", "kind", "dataset", "options", "split", "base_model", "baseline_model", "files"}
_MODEL_FIELDS = {"model_sha256", "weights_sha256", "model_size", "weights_size"}


class InputsError(ValueError):
    """A training input could not be captured or verified without ambiguity."""


def _canonical(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                          allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, UnicodeError, RecursionError) as error:
        raise InputsError("Training input metadata must be finite, bounded UTF-8 JSON") from error


def _integer(value, low, high, name):
    if type(value) is not int or not low <= value <= high:
        raise InputsError(f"{name} must be an integer from {low} to {high}")
    return value


def _fractions(value):
    if type(value) not in (list, tuple) or len(value) != 3:
        raise InputsError("split must contain three positive fractions")
    try:
        if any(type(item) not in (int, float) or not math.isfinite(item) or item <= 0 for item in value):
            raise InputsError("split must contain three positive finite fractions")
        total = math.fsum(value)
        if not math.isclose(total, 1.0, rel_tol=0, abs_tol=1e-9):
            raise InputsError("split fractions must sum to one")
        # Preserve accepted finite fractions. Renormalizing an approximately-one
        # float sum can round again on every verification and change the identity.
        return [float(item) for item in value]
    except (OverflowError, TypeError, ValueError) as error:
        if isinstance(error, InputsError):
            raise
        raise InputsError("split must contain three positive finite fractions") from error


def normalize_options(options=None):
    """Validate the published training budgets and return an independent full setting."""
    if options is not None and type(options) is not dict:
        raise InputsError("options must be an object")
    if options is not None and set(options) - set(DEFAULTS):
        raise InputsError("Unknown training option")
    settings = deepcopy(DEFAULTS)
    if options is not None:
        settings.update(deepcopy(options))
    for key in ("epochs", "patience"):
        _integer(settings[key], 1, 5000, key)
    _integer(settings["batch_size"], 1, 4096, "batch_size")
    _integer(settings["seed"], 0, 2**31 - 1, "seed")
    hidden = settings["hidden"]
    if type(hidden) is not list or not 1 <= len(hidden) <= 4:
        raise InputsError("hidden must contain one to four layer widths")
    for width in hidden:
        _integer(width, 4, 1024, "hidden layer width")
    rate = settings["learning_rate"]
    try:
        valid_rate = type(rate) in (int, float) and math.isfinite(rate) and 0 < rate <= 1
    except OverflowError:
        valid_rate = False
    if not valid_rate:
        raise InputsError("learning_rate must be finite, positive and at most one")
    settings["learning_rate"] = float(rate)
    settings["split"] = _fractions(settings["split"])
    return settings


def partition(sample_ids, fractions, seed):
    """Split exact IDs reproducibly, independent of input order; empty sets are errors."""
    _integer(seed, 0, 2**31 - 1, "seed")
    ratios = _fractions(fractions)
    if type(sample_ids) not in (list, tuple) or not 3 <= len(sample_ids) <= datasets.MAX_SAMPLES:
        raise InputsError("A split needs between three and 100000 sample IDs")
    try:
        valid = all(type(item) is str and 1 <= len(item) <= 128 and item.encode("utf-8") for item in sample_ids)
    except UnicodeError:
        valid = False
    if not valid or len(set(sample_ids)) != len(sample_ids):
        raise InputsError("Sample IDs must be distinct nonempty UTF-8 strings of at most 128 characters")
    order = sorted(sample_ids)
    random.Random(seed).shuffle(order)
    train, validation = round(len(order) * ratios[0]), round(len(order) * ratios[1])
    test = len(order) - train - validation
    if min(train, validation, test) <= 0:
        raise InputsError("Training, validation and test partitions must all be nonempty")
    return {"train": order[:train], "validation": order[train:train + validation],
            "test": order[train + validation:]}


def _path(value):
    try:
        path = Path(value)
        if ".." in path.parts or "\0" in os.fspath(path):
            raise InputsError("Training input paths must not contain traversal or NUL")
        if os.name == "nt" and os.fspath(path).startswith(("\\\\", "//")):
            raise InputsError("Training input paths must refer to local files")
        return path.absolute()
    except (TypeError, OSError, ValueError) as error:
        if isinstance(error, InputsError):
            raise
        raise InputsError("Invalid training input path") from error


def _linked(info):
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) &
                                           getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def _identity(info):
    return info.st_dev, info.st_ino, info.st_mode, getattr(info, "st_file_attributes", 0)


def _stamp(info):
    return _identity(info) + (info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _remember(guards, path, info, *, directory=False):
    signature = _identity(info) if directory else _stamp(info)
    previous = guards.setdefault(path, (signature, directory))
    if previous != (signature, directory):
        raise InputsError("Training input changed while it was read")


def _directory(path, guards):
    for part in (*reversed(path.parents), path):
        info = part.lstat()
        if _linked(info) or not stat.S_ISDIR(info.st_mode):
            raise InputsError("Training input directories must not be links or reparse points")
        _remember(guards, part, info, directory=True)


def _unchanged(guards):
    for path, (signature, directory) in guards.items():
        info = path.lstat()
        if _linked(info) or not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)):
            raise InputsError("Training input changed while it was read")
        if (_identity(info) if directory else _stamp(info)) != signature:
            raise InputsError("Training input changed while it was read")


def _copy_regular(source, destination, limit, guards):
    _directory(source.parent, guards)
    before = source.lstat()
    if _linked(before) or not stat.S_ISREG(before.st_mode) or before.st_size > limit:
        raise InputsError("Training input files must be bounded ordinary files without links or reparse points")
    _remember(guards, source, before)
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    descriptor = os.open(source, flags)
    try:
        opened = os.fstat(descriptor)
        # ctime is intentionally compared only within lstat or within fstat.
        # Windows can expose different ctime meanings through those two APIs.
        if (_linked(opened) or not stat.S_ISREG(opened.st_mode) or
                (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) !=
                (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns)):
            raise InputsError("Training input changed before it was opened")
        hasher, size = hashlib.sha256(), 0
        out_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        with os.fdopen(os.open(destination, out_flags, 0o600), "wb") as output:
            while chunk := os.read(descriptor, 1024 * 1024):
                size += len(chunk)
                if size > limit:
                    raise InputsError("Training input file exceeds its byte budget")
                hasher.update(chunk)
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
        if size != opened.st_size or _stamp(os.fstat(descriptor)) != _stamp(opened):
            raise InputsError("Training input changed while it was copied")
        _unchanged(guards)
        return {"size": size, "sha256": hasher.hexdigest()}
    finally:
        os.close(descriptor)


def _json_file(path):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise InputsError("Training input JSON contains duplicate keys")
            result[key] = value
        return result
    def constant(_):
        raise InputsError("Training input JSON must contain only finite numbers")
    try:
        raw = path.read_bytes()
        if raw.startswith(b"\xef\xbb\xbf"):
            raise InputsError("Training input JSON must not contain a BOM")
        return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant)
    except (OSError, ValueError, UnicodeError, RecursionError) as error:
        if isinstance(error, InputsError):
            raise
        raise InputsError("Training input metadata is not valid UTF-8 JSON") from error


def _model(folder, description):
    meta = _json_file(folder / "model.json")
    _canonical(meta)
    if (type(meta) is not dict or meta.get("format") != "stk.curve-model/1" or
            meta.get("kind") != description["target"]["kind"] or
            _canonical(meta.get("inputs")) != _canonical(description["inputs"]) or
            _canonical(meta.get("grid")) != _canonical(description["target"]["grid"])):
        raise InputsError("Frozen model kind, ordered inputs and grid must match the training dataset")


def _loaded(folder):
    try:
        description, samples = datasets.load(folder)
        card = datasets.validate(folder)
        if not card.get("ok"):
            raise InputsError("Frozen dataset validation failed")
        _canonical(card)
        return description, samples, card
    except (ValueError, OSError, RecursionError, OverflowError) as error:
        if isinstance(error, InputsError):
            raise
        raise InputsError("Frozen training dataset is invalid") from error


def _model_descriptor(files, role):
    meta, weights = files[f"{role}/model.json"], files[f"{role}/model.pt"]
    if not weights["size"]:
        raise InputsError("Frozen model weights must not be empty")
    return {"model_sha256": meta["sha256"], "weights_sha256": weights["sha256"],
            "model_size": meta["size"], "weights_size": weights["size"]}


def _seal(manifest):
    manifest["sha256"] = hashlib.sha256(_canonical({k: v for k, v in manifest.items() if k != "sha256"})).hexdigest()
    encoded = _canonical(manifest) + b"\n"
    if len(encoded) > MAX_MANIFEST_BYTES:
        raise InputsError("Training input manifest exceeds the 16 MiB budget")
    return encoded


def _remove_owned(path, identity):
    try:
        info = path.lstat()
        if not _linked(info) and stat.S_ISDIR(info.st_mode) and _identity(info) == identity:
            shutil.rmtree(path)
    except FileNotFoundError:
        pass


def capture(directory, target, *, options=None, base_model=None, baseline_model=None):
    """Freeze bounded stable bytes into a new capsule; existing targets are never reused.

    Private staging precedes exclusive target reservation. Complete files are linked
    without replacement, and the complete manifest is published last as the commit
    marker. A concurrent reader accepts the capsule only after that atomic marker.
    """
    target = _path(target)
    parent_guards, guards = {}, {}
    staging = None
    staging_identity = None
    owned_target = None
    try:
        settings = normalize_options(options)
        _directory(target.parent, parent_guards)
        if os.path.lexists(target):
            raise InputsError("Training input target already exists")
        staging = Path(tempfile.mkdtemp(prefix=".stk-training-input-", dir=target.parent))
        staging_identity = _identity(staging.lstat())
        source = _path(directory)
        files = {name: _copy_regular(source / name, staging / name, _LIMITS[name], guards)
                 for name in ("dataset.json", "samples.jsonl")}
        description, samples, card = _loaded(staging)
        split = partition([sample["id"] for sample in samples], settings["split"], settings["seed"])
        models = {}
        for role, model_path in (("base", base_model), ("baseline", baseline_model)):
            models[role] = None
            if model_path is not None:
                folder = _path(model_path)
                (staging / role).mkdir(mode=0o700)
                for name in ("model.json", "model.pt"):
                    files[f"{role}/{name}"] = _copy_regular(folder / name, staging / role / name,
                                                           _LIMITS[name], guards)
                _model(staging / role, description)
                models[role] = _model_descriptor(files, role)
        manifest = {"format": FORMAT, "kind": description["target"]["kind"],
                    "dataset": {"sha256": datasets.digest(description, samples), "card": card},
                    "options": settings, "split": split, "base_model": models["base"],
                    "baseline_model": models["baseline"], "files": files}
        encoded = _seal(manifest)
        manifest_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
        with os.fdopen(os.open(staging / "manifest.json", manifest_flags, 0o600), "wb") as output:
            output.write(encoded)
            output.flush()
            os.fsync(output.fileno())
        _unchanged(guards)
        _unchanged(parent_guards)
        target.mkdir(mode=0o700)  # Exclusive: never rename over an existing empty directory.
        owned_target = _identity(target.lstat())
        publication_guards = dict(parent_guards)
        _directory(target, publication_guards)
        for role in ("base", "baseline"):
            if models[role] is not None:
                (target / role).mkdir(mode=0o700)
                _directory(target / role, publication_guards)
        for name in (*files, "manifest.json"):
            _unchanged(publication_guards)
            if _identity(target.lstat()) != owned_target or _linked(target.lstat()):
                raise InputsError("Training input destination changed during publication")
            os.link(staging / name, target / name, follow_symlinks=False)
            _unchanged(publication_guards)
        return deepcopy(manifest)
    except (OSError, ValueError, TypeError, RecursionError) as error:
        if owned_target is not None:
            _remove_owned(target, owned_target)
        if isinstance(error, InputsError):
            raise
        raise InputsError("Training input capture failed without replacing an existing target") from error
    finally:
        if staging is not None and staging_identity is not None:
            _remove_owned(staging, staging_identity)


def _exact_tree(folder, roles):
    expected = {"manifest.json", "dataset.json", "samples.jsonl", *roles}
    if {item.name for item in folder.iterdir()} != expected:
        raise InputsError("Training input contains missing or unlisted files")
    for role in roles:
        if {item.name for item in (folder / role).iterdir()} != {"model.json", "model.pt"}:
            raise InputsError("Frozen model contains missing or unlisted files")


def _inspect(target):
    source, guards = _path(target), {}
    try:
        _directory(source, guards)
        with tempfile.TemporaryDirectory(prefix="stk-training-input-check-") as temporary:
            snapshot = Path(temporary)
            _copy_regular(source / "manifest.json", snapshot / "manifest.json", MAX_MANIFEST_BYTES, guards)
            manifest = _json_file(snapshot / "manifest.json")
            if type(manifest) is not dict or set(manifest) != _FIELDS or manifest["format"] != FORMAT:
                raise InputsError("Not an exact training input manifest")
            actual_identity = hashlib.sha256(_canonical({k: v for k, v in manifest.items() if k != "sha256"})).hexdigest()
            if manifest["sha256"] != actual_identity:
                raise InputsError("Training input manifest SHA-256 differs")
            roles = []
            expected = {"dataset.json", "samples.jsonl"}
            for role in ("base", "baseline"):
                model = manifest[f"{role}_model"]
                if model is not None:
                    if type(model) is not dict or set(model) != _MODEL_FIELDS:
                        raise InputsError("Frozen model role descriptor differs")
                    for field in ("model_size", "weights_size"):
                        if type(model[field]) is not int or model[field] < 0:
                            raise InputsError("Frozen model role sizes must be nonnegative integers")
                    roles.append(role)
                    expected.update((f"{role}/model.json", f"{role}/model.pt"))
                    _directory(source / role, guards)
                    (snapshot / role).mkdir(mode=0o700)
            if type(manifest["files"]) is not dict or set(manifest["files"]) != expected:
                raise InputsError("Training input file manifest differs")
            _exact_tree(source, roles)
            files = {}
            for name in sorted(expected):
                descriptor = manifest["files"][name]
                if (type(descriptor) is not dict or set(descriptor) != {"size", "sha256"} or
                        type(descriptor["size"]) is not int or descriptor["size"] < 0 or
                        type(descriptor["sha256"]) is not str or len(descriptor["sha256"]) != 64 or
                        any(ch not in "0123456789abcdef" for ch in descriptor["sha256"])):
                    raise InputsError("Training input file descriptor is invalid")
                actual = _copy_regular(source / name, snapshot / name, _LIMITS[Path(name).name], guards)
                if actual != descriptor:
                    raise InputsError("Frozen training input file size or SHA-256 differs")
                files[name] = actual
            description, samples, card = _loaded(snapshot)
            if (manifest["kind"] != description["target"]["kind"] or
                    _canonical(manifest["dataset"]) != _canonical({"sha256": datasets.digest(description, samples), "card": card})):
                raise InputsError("Frozen dataset digest or data card differs")
            settings = normalize_options(manifest["options"])
            if _canonical(manifest["options"]) != _canonical(settings) or manifest["split"] != partition(
                    [sample["id"] for sample in samples], settings["split"], settings["seed"]):
                raise InputsError("Frozen training options or sample partition differs")
            for role in roles:
                if manifest[f"{role}_model"] != _model_descriptor(files, role):
                    raise InputsError("Frozen model role does not match its files")
                _model(snapshot / role, description)
            _exact_tree(source, roles)
            _unchanged(guards)
            return manifest, description, samples
    except (OSError, ValueError, TypeError, KeyError, RecursionError) as error:
        if isinstance(error, InputsError):
            raise
        raise InputsError("Training input verification failed") from error


def verify(target):
    """Verify the complete capsule, including actual bytes and every frozen binding."""
    return _inspect(target)[0]


def load(target):
    """Return (manifest, description, samples), read solely from a verified frozen copy."""
    return _inspect(target)


__all__ = ["DEFAULTS", "FORMAT", "InputsError", "capture", "load", "normalize_options", "partition", "verify"]
