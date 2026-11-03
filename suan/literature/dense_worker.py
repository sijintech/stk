"""Explicit offline E5 CPU worker; process isolation, not an OS sandbox.

Assets and dependencies must already have been provisioned and reviewed. This
worker never downloads, chooses an interpreter, sends telemetry, or truncates a
passage. It operates on extracted scalar text, not reviewed scientific structure.
"""
import base64
import hashlib
import importlib.metadata as metadata
import json
import math
import os
from pathlib import Path
import platform
import stat
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from suan.literature.encoder_profiles import (CORE, E5_RECIPE, profile_for_manifest,
                                               worker_identity_sha256)

REVISION = "614241f622f53c4eeff9890bdc4f31cfecc418b3"
LFS = {
    "model.safetensors": (470641600, "1a55775f53449dac10a2bcbc312469fac40b96d53198c407081a831f81c98477"),
    "tokenizer.json": (17082730, "0b44a9d7b51c3c62626640cda0e2c2f70fdacdc25bbbd68038369d14ebdf4c39"),
    "sentencepiece.bpe.model": (5069051, "cfc8146abe2a0488e9e2a0c56de7952f7c11ab059eca145a0a727afce0db2865"),
}
FILES = set(LFS) | {"config.json", "tokenizer_config.json", "special_tokens_map.json", "modules.json",
                         "sentence_bert_config.json", "1_Pooling/config.json", "README.md"}
RECIPE = E5_RECIPE  # Retained public legacy metadata; actual recipe follows verified assets.
MAX_WINDOWS, MAX_SCALARS, MAX_OUTPUT = 20000, 4_000_000, 128 * 1024**2


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                      separators=(",", ":")).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def _deny_network(event, args):
    if event.startswith("socket."):
        raise RuntimeError("Offline literature encoder has no network capability")


def _ordinary(path):
    path = Path(path)
    if not path.is_absolute() or ".." in path.parts: raise ValueError
    for parent in (*reversed(path.parents), path.parent):
        s = parent.lstat()
        if not stat.S_ISDIR(s.st_mode) or getattr(s, "st_file_attributes", 0) & 0x400: raise ValueError
    s = path.lstat()
    if not stat.S_ISREG(s.st_mode) or getattr(s, "st_file_attributes", 0) & 0x400: raise ValueError
    return s


def _file_hash(path, size):
    before = _ordinary(path)
    if before.st_size != size: raise ValueError
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)
    with os.fdopen(os.open(path, flags), "rb") as stream:
        initial = os.fstat(stream.fileno())
        cross = lambda s: (s.st_dev, s.st_ino, s.st_mode, s.st_size, s.st_mtime_ns)
        full = lambda s: (*cross(s), s.st_ctime_ns)
        if cross(initial) != cross(before): raise ValueError
        h, count = hashlib.sha256(), 0
        while block := stream.read(1024**2):
            count += len(block)
            if count > size: raise ValueError
            h.update(block)
        after, named = os.fstat(stream.fileno()), _ordinary(path)
        if count != size or full(initial) != full(after) or full(before) != full(named) or cross(after) != cross(named): raise ValueError
    return h.hexdigest()


def assets(root, expected):
    manifest_path = root / "manifest.json"
    if not 1 <= _ordinary(manifest_path).st_size <= 16384: raise ValueError
    before = _ordinary(manifest_path)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)
    with os.fdopen(os.open(manifest_path, flags), "rb") as stream:
        initial = os.fstat(stream.fileno()); encoded = stream.read(16385); after = os.fstat(stream.fileno())
    named = _ordinary(manifest_path)
    stamp = lambda s: (s.st_dev, s.st_ino, s.st_mode, s.st_size, s.st_mtime_ns)
    if (len(encoded) != initial.st_size or len(encoded) > 16384 or stamp(before) != stamp(initial)
            or stamp(initial) != stamp(after) or stamp(after) != stamp(named)
            or initial.st_ctime_ns != after.st_ctime_ns or before.st_ctime_ns != named.st_ctime_ns): raise ValueError
    if hashlib.sha256(encoded).hexdigest() != expected: raise ValueError
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value: raise ValueError
            value[key] = item
        return value
    manifest = json.loads(encoded, object_pairs_hook=pairs)
    profile_for_manifest(manifest)
    for name, identity in manifest["files"].items():
        if _file_hash(root / name, identity["bytes"]) != identity["sha256"]: raise ValueError
    return manifest


def windows(text, tokenizer, recipe=None):
    """Partition every scalar, including whitespace, within the actual token cap.

    Token counts need not be monotone at BPE boundaries. Binary search only
    proposes a candidate; the selected prefix is counted again before use.
    A smaller valid window is acceptable; omitted or truncated tails are not.
    """
    recipe = RECIPE if recipe is None else recipe
    start = 0
    while start < len(text):
        low, high = start, len(text)
        while low < high:
            end = (low + high + 1) // 2
            count = len(tokenizer(recipe["passage_prefix"] + text[start:end], truncation=False)["input_ids"])
            if count <= recipe["tokens"]: low = end
            else: high = end - 1
        if low <= start: raise OverflowError
        count = len(tokenizer(recipe["passage_prefix"] + text[start:low], truncation=False)["input_ids"])
        if not 1 <= count <= recipe["tokens"]: raise OverflowError
        yield start, low, count
        start = low


def runtime():
    packages = {}
    for distribution in metadata.distributions():
        name = distribution.metadata["Name"].lower().replace("_", "-")
        record = distribution.read_text("RECORD")
        packages[name] = {"version": distribution.version,
                          "record_sha256": None if record is None else hashlib.sha256(record.encode()).hexdigest()}
    if any(packages.get(name, {}).get("version") != version for name, version in CORE.items()):
        raise metadata.PackageNotFoundError
    return {"python": sys.version, "platform": platform.platform(), "machine": platform.machine(),
            "packages": packages, "worker_sha256": worker_identity_sha256()}


def encode(request):
    # Reject malformed or over-budget requests before hashing/loading weights.
    entries, query = request["entries"], request.get("query")
    if type(entries) is not list or len(entries) > 10000: raise OverflowError
    seen, total = set(), 0
    for entry in entries:
        if type(entry) is not dict or set(entry) != {"id", "text"}: raise ValueError
        if (type(entry["id"]) is not str or len(entry["id"]) != 64
                or any(c not in "0123456789abcdef" for c in entry["id"]) or entry["id"] in seen): raise ValueError
        if type(entry["text"]) is not str or not entry["text"].strip() or len(entry["text"]) > 2048: raise ValueError
        entry["text"].encode("utf-8")
        seen.add(entry["id"]); total += len(entry["text"])
    if total > MAX_SCALARS: raise OverflowError
    if query is not None:
        if type(query) is not str or not query.strip(): raise ValueError
        query.encode("utf-8")
        if len(query) > 4096: raise OverflowError
    root = Path(request["assets"])
    manifest = assets(root, request["assets_sha256"])
    recipe = profile_for_manifest(manifest)["recipe"]
    identity = {"assets_sha256": request["assets_sha256"], "recipe": recipe, "runtime": runtime()}
    import torch
    import torch.nn.functional as functional
    from transformers import AutoModel, AutoTokenizer
    torch.set_num_threads(recipe["threads"])
    torch.set_num_interop_threads(1)
    tokenizer_options = {"padding_side": "left"} if recipe["pooling"] == "last_nonpadding_token" else {}
    tokenizer = AutoTokenizer.from_pretrained(str(root), local_files_only=True, trust_remote_code=False,
                                             use_fast=True, **tokenizer_options)
    model_options = {"attn_implementation": "eager"} if recipe["pooling"] == "last_nonpadding_token" else {}
    model = AutoModel.from_pretrained(str(root), local_files_only=True, trust_remote_code=False,
                                     use_safetensors=True, torch_dtype=torch.float32, **model_options).to("cpu").eval()
    output, texts = [], []
    for entry in entries:
        for start, end, count in windows(entry["text"], tokenizer, recipe):
            text = entry["text"][start:end]
            output.append({"id": entry["id"], "start": start, "end": end, "tokens": count,
                           "text_sha256": hashlib.sha256(text.encode()).hexdigest()})
            texts.append(recipe["passage_prefix"] + text)
            if len(output) > MAX_WINDOWS: raise OverflowError
    if query is not None:
        count = len(tokenizer(recipe["query_prefix"] + query, truncation=False)["input_ids"])
        if not 1 <= count <= recipe["tokens"]: raise OverflowError
        output.append({"query": True, "text_sha256": hashlib.sha256(query.encode()).hexdigest(), "tokens": count})
        texts.append(recipe["query_prefix"] + query)
    for begin in range(0, len(texts), 8):
        batch = tokenizer(texts[begin:begin + 8], padding=True, truncation=False, return_tensors="pt")
        if batch["input_ids"].shape[1] > recipe["tokens"]: raise OverflowError
        with torch.inference_mode():
            hidden = model(**batch, **({"use_cache": False} if model_options else {})).last_hidden_state
            if recipe["pooling"] == "attention_mask_mean":
                hidden = hidden.masked_fill(~batch["attention_mask"][..., None].bool(), 0.0)
                pooled = hidden.sum(dim=1) / batch["attention_mask"].sum(dim=1)[..., None]
            elif recipe["pooling"] == "last_nonpadding_token":
                if not bool((batch["attention_mask"][:, -1] == 1).all()): raise ValueError
                pooled = hidden[:, -1]
            else: raise ValueError
            vectors = functional.normalize(pooled, p=2, dim=1).to(dtype=torch.float32, device="cpu").tolist()
        for item, vector in zip(output[begin:begin + 8], vectors, strict=True):
            if len(vector) != recipe["dimensions"] or any(not math.isfinite(x) for x in vector): raise ValueError
            if abs(sum(x*x for x in vector) - 1) > 0.0001: raise ValueError
            raw = struct.pack("<" + str(recipe["dimensions"]) + "f", *vector)
            item.update(vector_b64=base64.b64encode(raw).decode(), vector_sha256=hashlib.sha256(raw).hexdigest())
    # Detect ordinary accidental asset replacement during model loading/inference.
    if assets(root, request["assets_sha256"]) != manifest: raise ValueError
    return {"format": "stk.literature-embeddings/1", "identity": identity, "fingerprint": digest(identity),
            "input_sha256": digest({"entries": entries, "query": query}), "windows": output[:len(output) - (query is not None)],
            "query": output[-1] if query is not None else None}


def main():
    os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1",
                      DO_NOT_TRACK="1", HF_HUB_DISABLE_XET="1", TOKENIZERS_PARALLELISM="false")
    sys.addaudithook(_deny_network)
    try:
        source, target = map(Path, sys.argv[1:])
        if source.stat().st_size > 32 * 1024**2: raise OverflowError
        request = json.loads(source.read_bytes())
        result = canonical(encode(request))
        if len(result) > MAX_OUTPUT: raise OverflowError
        with target.open("xb") as stream: stream.write(result)
    except (ImportError, metadata.PackageNotFoundError): return 3
    except OverflowError: return 5
    except Exception: return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
