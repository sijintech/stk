"""Closed offline profiles, actual Qwen inference and retained mixed dimensions."""
import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
from uuid import uuid4

import pytest

from suan.literature._io import LiteratureError
from suan.literature.collection import Collection
from suan.literature.dense import DenseIndex, Encoder, validate_embeddings
from suan.literature.encoder_profiles import (E5_RECIPE, QWEN_RECIPE, profiles,
    profile_for_manifest, profile_for_recipe, worker_identity_sha256)
from suan.literature.store import Library
from test_literature_pdf import make_pdf, pdf_python
from test_literature_store import _import
from test_literature_dense import encoder


def manifest(profile):
    return {"format": profile["asset_format"], "model": profile["recipe"]["encoder"],
            "revision": profile["recipe"]["revision"], "declared_license": profile["license"],
            "files": profile["files"]}


def test_inspection_is_detached_and_legacy_recipe_is_unchanged():
    assert E5_RECIPE == {"encoder": "intfloat/multilingual-e5-small",
        "revision": "614241f622f53c4eeff9890bdc4f31cfecc418b3", "dimensions": 384,
        "tokens": 512, "query_prefix": "query: ", "passage_prefix": "passage: ",
        "pooling": "attention_mask_mean", "normalization": "l2", "device": "cpu",
        "dtype": "float32", "windows": "complete_contiguous_scalar_partition/1", "threads": 2}
    observed = profiles()
    observed[0]["recipe"]["dimensions"] = 1
    observed[0]["files"]["config.json"]["bytes"] = 0
    assert profile_for_recipe(E5_RECIPE)["recipe"]["dimensions"] == 384
    assert profile_for_recipe(QWEN_RECIPE)["recipe"]["dimensions"] == 1024
    assert profiles()[0]["files"]["config.json"]["bytes"] > 0


@pytest.mark.parametrize("field,value", [("dimensions", 1024.0), ("tokens", True),
    ("pooling", "attention_mask_mean"), ("query_prefix", "query: "),
    ("revision", "unreviewed"), ("device", "cuda"), ("threads", 4)])
def test_unknown_or_type_changed_qwen_recipe_is_not_a_supported_profile(field, value):
    recipe = copy.deepcopy(QWEN_RECIPE)
    recipe[field] = value
    with pytest.raises(ValueError):
        profile_for_recipe(recipe)


@pytest.mark.parametrize("damage", ["extra", "missing", "license", "revision", "config", "weight", "integer"])
def test_asset_manifest_requires_every_reviewed_publisher_file_and_exact_types(damage):
    value = manifest(profile_for_recipe(QWEN_RECIPE))
    if damage == "extra": value["files"]["remote.py"] = {"bytes": 1, "sha256": "a"*64}
    elif damage == "missing": value["files"].pop("config.json")
    elif damage == "license": value["declared_license"] = "MIT"
    elif damage == "revision": value["revision"] = "unreviewed"
    elif damage == "config": value["files"]["config.json"]["sha256"] = "b"*64
    elif damage == "weight": value["files"]["model.safetensors"]["sha256"] = "c"*64
    else: value["files"]["config.json"]["bytes"] = float(value["files"]["config.json"]["bytes"])
    with pytest.raises(ValueError):
        profile_for_manifest(value)


def test_legacy_license_evidence_note_is_metadata_without_an_arbitrary_model_escape():
    value = manifest(profile_for_recipe(E5_RECIPE))
    value["license_evidence"] = "Publisher README; no invented separate license file"
    assert profile_for_manifest(value)["recipe"] == E5_RECIPE
    value["model"] = "another/model"
    with pytest.raises(ValueError):
        profile_for_manifest(value)


@pytest.mark.parametrize("note", ["", "x" * 1025, "\ud800", False, {}])
def test_license_evidence_note_is_bounded_utf8_metadata(note):
    value = manifest(profile_for_recipe(E5_RECIPE))
    value["license_evidence"] = note
    with pytest.raises(ValueError):
        profile_for_manifest(value)


def test_worker_identity_changes_with_either_inference_source(tmp_path, monkeypatch):
    import suan.literature.encoder_profiles as module
    profile = tmp_path / "encoder_profiles.py"
    worker = tmp_path / "dense_worker.py"
    profile.write_text("reviewed profile implementation\n")
    worker.write_text("reviewed inference implementation\n")
    monkeypatch.setattr(module, "__file__", str(profile))
    original = module.worker_identity_sha256()
    profile.write_text("changed profile implementation\n")
    changed_profile = module.worker_identity_sha256()
    worker.write_text("changed inference implementation\n")
    assert len({original, changed_profile, module.worker_identity_sha256()}) == 3


@pytest.mark.parametrize("dense_id,fused_id", [
    ("local_e5_exact_cosine", "local_fts5_e5_rrf"),
    ("local_qwen3_exact_cosine", "local_fts5_qwen3_rrf"),
])
def test_hybrid_retriever_identity_follows_the_selected_dense_profile(tmp_path, monkeypatch, dense_id, fused_id):
    library = Library(tmp_path / "absent")
    index = DenseIndex(library)
    selected = Encoder(tmp_path / "absent-assets", assets_sha256="a" * 64, python=Path(sys.executable))
    generation = "b" * 64
    monkeypatch.setattr(selected, "encode", lambda *a, **k: pytest.fail("Metadata regression loaded a model"))
    monkeypatch.setattr(index, "search", lambda *a, **k: {
        "generation": generation, "corpus_generation": 0, "retriever": dense_id,
        "encoder_fingerprint": "c" * 64, "query_sha256": "d" * 64, "hits": [],
    })
    monkeypatch.setattr(library, "search", lambda *a, **k: {"generation": 0, "hits": []})
    monkeypatch.setattr(index, "_current", lambda db: (generation, {}))
    assert index.hybrid_search("sunlight", selected)["retriever"] == fused_id
    assert not library.root.exists()


@pytest.fixture(scope="module")
def qwen():
    root = os.environ.get("STK_LITERATURE_QWEN_ASSETS")
    digest = os.environ.get("STK_LITERATURE_QWEN_MANIFEST_SHA256")
    python = os.environ.get("STK_LITERATURE_QWEN_PYTHON")
    if not root or not digest or not python:
        pytest.skip("Requires explicitly provisioned, pinned local Qwen assets/runtime")
    return Encoder(root, assets_sha256=digest, python=python)


def test_actual_qwen_uses_reviewed_instruction_last_token_and_1024_finite_components(qwen):
    texts = ["A solar cell converts sunlight into electrical energy.",
             "A battery stores electrochemical energy for later use."]
    entries = [{"id": hashlib.sha256(text.encode()).hexdigest(), "text": text} for text in texts]
    result = qwen.encode(entries, query="哪种装置把阳光转换为电能？")
    assert result["identity"]["recipe"] == QWEN_RECIPE
    assert result["identity"]["runtime"]["worker_sha256"] == worker_identity_sha256()
    assert [w["id"] for w in result["windows"]] == [e["id"] for e in entries]
    vectors = []
    for item in [*result["windows"], result["query"]]:
        raw = base64.b64decode(item["vector_b64"], validate=True)
        assert len(raw) == 4096 and hashlib.sha256(raw).hexdigest() == item["vector_sha256"]
        vector = struct.unpack("<1024f", raw)
        assert sum(x*x for x in vector) == pytest.approx(1, abs=0.0001)
        assert 1 <= item["tokens"] <= 512
        vectors.append(vector)
    score = lambda left, right: sum(x*y for x, y in zip(left, right, strict=True))
    assert score(vectors[0], vectors[2]) > score(vectors[1], vectors[2])
    for field, value in [("dimensions", 384), ("pooling", "attention_mask_mean")]:
        corrupted = copy.deepcopy(result)
        corrupted["identity"]["recipe"][field] = value
        with pytest.raises(LiteratureError):
            validate_embeddings(corrupted, entries, "哪种装置把阳光转换为电能？",
                                qwen.assets_sha256, result["identity"]["runtime"]["worker_sha256"])


def test_real_qwen_collection_and_retained_1024_citation_survive_explicit_384_rebuild(tmp_path, qwen, encoder, pdf_python, monkeypatch):
    content = make_pdf([["A solar cell converts sunlight into electrical energy."],
                        ["A battery stores electrochemical energy for later use."]])
    source = tmp_path / "owned.pdf"
    source.write_bytes(content)
    document = str(uuid4())
    libraries = {}
    for scope in ("owner", "campus"):
        library = Library(tmp_path / scope)
        imported = _import(library, source, document=document)
        library.index_pdf(str(uuid4()), imported["receipt"]["version_id"], python=pdf_python)
        DenseIndex(library).build(str(uuid4()), qwen)
        libraries[scope] = library
    collection = Collection(libraries)
    found = collection.search("哪种装置把阳光转换为电能？", qwen, scopes=["owner", "campus"], limit=2)
    assert found["retriever"] == "local_collection_fts5_qwen3_rrf"
    assert {hit["corpus_id"] for hit in found["hits"]} == {"owner", "campus"}
    assert all("solar cell" in hit["text"] for hit in found["hits"])
    saved = next(hit["dense_window"] for hit in found["hits"] if hit["corpus_id"] == "owner")
    original = collection.resolve(saved, scopes=["owner"])
    # SQL schema and historical generation bytes are retained when an explicit
    # supported model switch builds a different-dimensional current generation.
    DenseIndex(libraries["owner"]).build(str(uuid4()), encoder)
    with monkeypatch.context() as guard:
        guard.setattr(qwen, "encode", lambda *a, **k: pytest.fail("Mixed profiles reached query encoding"))
        with pytest.raises(LiteratureError) as mismatch:
            collection.search("sunlight", qwen, scopes=["owner", "campus"])
        assert mismatch.value.code == "encoder_mismatch"
        assert collection.resolve(saved, scopes=["owner"]) == original
    library = libraries["campus"]
    index = DenseIndex(library)
    with library._db(write=True) as db:
        generation, frozen = index._current(db)
        db.execute("UPDATE dense_windows SET vector=substr(vector,1,1536) WHERE generation=?", (generation,))
    with library._db() as db:
        with pytest.raises(LiteratureError) as damaged:
            list(index._vectors(db, generation, frozen))
    assert damaged.value.code == "embedding_changed"
