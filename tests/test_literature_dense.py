"""Real provisioned E5 inference, complete windows, and authorization fences.

These tests never download a model or install a runtime. Actual-encoder cases
require the explicit external asset path, manifest SHA and interpreter. A CI
claim must check the JUnit cases and zero skips, not merely a green collection.
"""
import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import struct
import sys
import threading
from uuid import uuid4

import pytest

from suan.literature._io import LiteratureError
from suan.literature.dense import DenseIndex, Encoder, validate_embeddings
from suan.literature.store import Library
from test_literature_pdf import pdf_python
from test_literature_store import _ready


@pytest.fixture(scope="module")
def encoder():
    root = os.environ.get("STK_LITERATURE_E5_ASSETS")
    sha = os.environ.get("STK_LITERATURE_E5_MANIFEST_SHA256")
    python = os.environ.get("STK_LITERATURE_E5_PYTHON", sys.executable)
    if not root or not sha: pytest.skip("Requires explicitly provisioned real pinned E5 assets")
    return Encoder(root, assets_sha256=sha, python=python)


def test_dense_construction_info_reopen_and_empty_search_do_not_load_or_create(tmp_path, monkeypatch):
    monkeypatch.setattr(Encoder, "encode", lambda *a, **k: pytest.fail("Passive read invoked inference"))
    root = tmp_path / "absent"
    selection = Encoder(tmp_path / "absent-assets", assets_sha256="a"*64, python=Path(sys.executable))
    for index in (DenseIndex(Library(root)), DenseIndex(Library(root))):
        assert index.info() == {"generation": None, "corpus_generation": 0}
        assert index.search("query", selection)["hits"] == []
    assert not root.exists()


@pytest.mark.parametrize("entries", [[None], [{}], [{"id": [], "text": "owned"}],
    [{"id": "a"*64, "text": None}], [{"id": "a"*64, "text": "\ud800"}],
    [{"id": "a"*64, "text": "owned"}, {"id": "a"*64, "text": "owned"}]])
def test_malformed_entries_fail_with_bounded_error_before_worker(entries, tmp_path, monkeypatch):
    import suan.literature.dense as module
    monkeypatch.setattr(module.subprocess, "run", lambda *a, **k:pytest.fail("Invalid input launched inference"))
    selected = Encoder(tmp_path / "absent-assets", assets_sha256="a"*64, python=Path(sys.executable))
    with pytest.raises(LiteratureError) as caught: selected.encode(entries)
    assert caught.value.code == "invalid_data"


@pytest.mark.parametrize("assets,python", [(None, sys.executable), ([], sys.executable),
    ("relative", sys.executable), ("/tmp/owned", None), ("/tmp/owned", "/tmp/owned\0python")])
def test_bad_explicit_paths_have_path_free_errors(assets, python):
    with pytest.raises(LiteratureError) as caught: Encoder(assets, assets_sha256="a"*64, python=python)
    assert caught.value.code == "invalid_path"
    assert "owned" not in str(caught.value)


@pytest.mark.parametrize("query,code", [("\ud800", "invalid_data"), ("x"*4097, "embedding_budget")])
def test_invalid_query_rejected_before_any_weight_load(query, code, tmp_path, monkeypatch):
    import suan.literature.dense as module
    monkeypatch.setattr(module.subprocess, "run", lambda *a, **k:pytest.fail("Invalid query launched inference"))
    selected = Encoder(tmp_path / "absent-assets", assets_sha256="a"*64, python=Path(sys.executable))
    with pytest.raises(LiteratureError) as caught: selected.encode([], query=query)
    assert caught.value.code == code


@pytest.mark.parametrize("method", ["search", "hybrid_search"])
def test_surrogate_query_has_bounded_error_before_any_index_read(method, tmp_path, monkeypatch):
    library = Library(tmp_path / "absent")
    monkeypatch.setattr(library, "_db", lambda *a, **k:pytest.fail("Invalid query opened storage"))
    selected = Encoder(tmp_path / "absent-assets", assets_sha256="a"*64, python=Path(sys.executable))
    with pytest.raises(LiteratureError) as caught: getattr(DenseIndex(library), method)("\ud800", selected)
    assert caught.value.code == "invalid_data"


def test_actual_e5_preserves_every_chinese_scalar_and_finite_normalized_vectors(encoder):
    text = ("锂离子电池循环寿命取决于电极材料及界面反应。" * 100)[:2048]
    entries = [{"id": hashlib.sha256(text.encode()).hexdigest(), "text": text}]
    result = encoder.encode(entries, query="电池为什么会衰减？")
    assert len(result["windows"]) > 1
    position = 0
    for window in result["windows"]:
        assert window["start"] == position
        position = window["end"]
        vector = struct.unpack("<384f", base64.b64decode(window["vector_b64"]))
        assert sum(x*x for x in vector) == pytest.approx(1, abs=0.0001)
        assert 0 < window["tokens"] <= 512
    assert position == len(text)
    assert result["query"]["text_sha256"] == hashlib.sha256("电池为什么会衰减？".encode()).hexdigest()
    assert result["identity"]["runtime"]["packages"]["torch"]["version"] == "2.14.1+cpu"
    truncated = copy.deepcopy(result); truncated["windows"].pop()
    with pytest.raises(LiteratureError) as caught:
        validate_embeddings(truncated, entries, "电池为什么会衰减？", encoder.assets_sha256,
                            result["identity"]["runtime"]["worker_sha256"])
    assert caught.value.code == "embedding_coverage"


def test_actual_query_over_token_limit_fails_without_truncation(encoder):
    with pytest.raises(LiteratureError) as caught:
        encoder.encode([], query="电池" * 1500)
    assert caught.value.code == "embedding_budget"


def test_real_dense_build_replay_search_exact_geometry_and_reopen(tmp_path, encoder, pdf_python, monkeypatch):
    library, version, source = _ready(tmp_path, pdf_python, [["The electrolyte carries lithium ions between battery electrodes."],
        ["The cat is a small domestic animal and sleeps on the sofa."], ["A solar cell converts sunlight into electrical energy."]])
    index = DenseIndex(library); op = str(uuid4())
    built = index.build(op, encoder)
    assert built["state"] == "completed" and built["receipt"]["windows"] >= 3
    query = index.search("How does a photovoltaic device generate electricity?", encoder, limit=3)
    assert query["hits"][0]["citation"]["base"]["page_index"] == 2
    citation = query["hits"][0]["citation"]
    resolved = DenseIndex(Library(library.root)).resolve(citation)
    assert resolved["text"] == query["hits"][0]["text"]
    assert any(c["box"] for c in resolved["characters"])
    monkeypatch.setattr(encoder, "encode", lambda *a, **k:pytest.fail("Replay or resolve re-encoded"))
    assert index.build(op, encoder) == built
    assert index.resolve(citation) == resolved
    wrong = copy.deepcopy(citation); wrong["start"] = False
    with pytest.raises(LiteratureError): index.resolve(wrong)
    source.unlink()
    assert index.resolve(citation) == resolved
    library.revoke(str(uuid4()), version)
    with pytest.raises(LiteratureError) as revoked: index.resolve(citation)
    assert revoked.value.code == "authorization_revoked"
    with pytest.raises(LiteratureError) as stale: index.search("sunlight", encoder)
    assert stale.value.code == "dense_stale"


def test_revoke_while_actual_e5_runs_prevents_any_dense_publication(tmp_path, encoder, pdf_python, monkeypatch):
    library, version, _ = _ready(tmp_path, pdf_python)
    index = DenseIndex(library); original = encoder.encode; errors = []
    def revoke():
        try: library.revoke(str(uuid4()), version)
        except Exception as exc: errors.append(exc)
    def encode(*a, **k):
        timer = threading.Timer(0.1, revoke); timer.start()
        try: return original(*a, **k)
        finally: timer.join()
    monkeypatch.setattr(encoder, "encode", encode)
    op = str(uuid4())
    with pytest.raises(LiteratureError) as caught: index.build(op, encoder)
    assert caught.value.code == "corpus_changed" and not errors
    assert index.info()["generation"] is None
    assert library.operation(op)["state"] == "uncertain"
    with library._db() as db:
        assert db.execute("SELECT count(*) FROM sqlite_master WHERE name='dense_generations'").fetchone()[0] == 0


def test_actual_index_capacity_failure_rolls_back_full_generation(tmp_path, encoder, pdf_python, monkeypatch):
    library, _, _ = _ready(tmp_path, pdf_python)
    import suan.literature.dense as module
    # Force the post-inference publication gate, not a fake vector/parser path.
    original = encoder.encode
    def encode(*a, **k):
        result = original(*a, **k)
        monkeypatch.setattr(module, "MAX_GENERATIONS", 0)
        return result
    monkeypatch.setattr(encoder, "encode", encode)
    index = DenseIndex(library)
    with pytest.raises(LiteratureError) as caught: index.build(str(uuid4()), encoder)
    assert caught.value.code == "embedding_budget"
    assert index.info()["generation"] is None
    with library._db() as db:
        assert db.execute("SELECT count(*) FROM sqlite_master WHERE name='dense_windows'").fetchone()[0] == 0


def test_actual_model_manifest_mismatch_is_rejected_without_fallback(encoder):
    wrong = Encoder(encoder.assets, assets_sha256="0"*64, python=encoder.python)
    with pytest.raises(LiteratureError) as caught: wrong.encode([], query="battery")
    assert caught.value.code == "embedding_failed"


@pytest.mark.parametrize("method", ["search", "hybrid_search"])
def test_actual_query_model_selection_change_cannot_publish_old_model_evidence(tmp_path, encoder, pdf_python, monkeypatch, method):
    library, _, _ = _ready(tmp_path, pdf_python)
    index = DenseIndex(library); index.build(str(uuid4()), encoder)
    original = encoder.encode
    def encode(*args, **kwargs):
        result = original(*args, **kwargs)
        monkeypatch.setattr(encoder, "assets_sha256", "b" * 64)
        return result
    monkeypatch.setattr(encoder, "encode", encode)
    with pytest.raises(LiteratureError) as caught:
        getattr(index, method)("sunlight", encoder)
    assert caught.value.code == "encoder_changed"


def test_retained_dense_citation_rejects_deep_invalid_base_with_bounded_error(tmp_path, encoder, pdf_python):
    library, _, _ = _ready(tmp_path, pdf_python)
    index = DenseIndex(library); index.build(str(uuid4()), encoder)
    with library._db() as db:
        identity, manifest = index._current(db)
    item = manifest["windows"][0]
    citation = {"format": "stk.literature-dense-citation/1", "generation": identity,
                "window_key": item["key"], "base": item["citation"], "start": item["start"],
                "end": item["end"], "text_sha256": item["text_sha256"]}
    assert index.resolve(citation)["text"]
    nested = []
    for _ in range(20000): nested = [nested]
    citation["base"] = {"unexpected": nested}
    with pytest.raises(LiteratureError) as caught: index.resolve(citation)
    assert caught.value.code == "invalid_data"


def test_actual_fusion_model_change_during_lexical_branch_cannot_publish(tmp_path, encoder, pdf_python, monkeypatch):
    library, _, _ = _ready(tmp_path, pdf_python)
    index = DenseIndex(library); index.build(str(uuid4()), encoder)
    original = library.search
    def search(*args, **kwargs):
        result = original(*args, **kwargs)
        monkeypatch.setattr(encoder, "assets_sha256", "b" * 64)
        return result
    monkeypatch.setattr(library, "search", search)
    with pytest.raises(LiteratureError) as caught: index.hybrid_search("sunlight", encoder)
    assert caught.value.code == "encoder_changed"


def test_frozen_vector_tampering_is_detected(tmp_path, encoder, pdf_python):
    library, _, _ = _ready(tmp_path, pdf_python)
    index = DenseIndex(library); index.build(str(uuid4()), encoder)
    with sqlite3.connect(library.path) as db:
        db.execute("UPDATE dense_windows SET vector=zeroblob(1536)")
    with pytest.raises(LiteratureError) as caught: index.search("zircon", encoder)
    assert caught.value.code == "embedding_changed"


@pytest.mark.parametrize("damage", ["corrupt", "delete"])
def test_new_actual_build_cannot_adopt_damaged_existing_generation(tmp_path, encoder, pdf_python, damage):
    library, _, _ = _ready(tmp_path, pdf_python)
    index = DenseIndex(library); previous = index.build(str(uuid4()), encoder)
    with sqlite3.connect(library.path) as db:
        if damage == "corrupt": db.execute("UPDATE dense_windows SET vector=zeroblob(1536)")
        else: db.execute("DELETE FROM dense_windows")
    op = str(uuid4())
    with pytest.raises(LiteratureError) as caught: index.build(op, encoder)
    assert caught.value.code == "embedding_changed"
    assert library.operation(op)["state"] == "uncertain"
    assert index.info()["generation"] == previous["receipt"]["generation"]


def test_actual_literal_dense_fusion_retains_branch_ranks_and_exact_citations(tmp_path, encoder, pdf_python):
    library, version, _ = _ready(tmp_path, pdf_python, [["A solar cell converts sunlight into electrical energy."],
        ["The cat sleeps on the sofa."], ["Lithium electrolyte carries ions."]])
    index = DenseIndex(library); index.build(str(uuid4()), encoder)
    found = index.hybrid_search("sunlight", encoder, limit=3)
    hit = found["hits"][0]
    assert hit["lexical_rank"] == hit["dense_rank"] == 1
    assert hit["score"] == pytest.approx(2/61)
    assert library.resolve(hit["citation"])["text"] == hit["text"]
    assert index.resolve(hit["dense_window"])["text"] in hit["text"]
    assert DenseIndex(Library(library.root)).hybrid_search("sunlight", encoder, limit=3) == found
    library.revoke(str(uuid4()), version)
    with pytest.raises(LiteratureError) as caught: index.hybrid_search("sunlight", encoder)
    assert caught.value.code == "dense_stale"


def test_revoke_between_real_fusion_branches_returns_no_evidence(tmp_path, encoder, pdf_python, monkeypatch):
    library, version, _ = _ready(tmp_path, pdf_python)
    index = DenseIndex(library); index.build(str(uuid4()), encoder)
    search = library.search
    def revoked(*a, **k):
        result = search(*a, **k)
        library.revoke(str(uuid4()), version)
        return result
    monkeypatch.setattr(library, "search", revoked)
    with pytest.raises(LiteratureError) as caught: index.hybrid_search("zircon", encoder)
    assert caught.value.code == "authorization_revoked"


def test_actual_build_rejects_encoder_selection_changed_in_callback(tmp_path, encoder, pdf_python, monkeypatch):
    library, _, _ = _ready(tmp_path, pdf_python)
    original = encoder.encode
    def changed(*a, **k):
        result = original(*a, **k)
        monkeypatch.setattr(encoder, "assets_sha256", "b"*64)
        return result
    monkeypatch.setattr(encoder, "encode", changed)
    index = DenseIndex(library)
    with pytest.raises(LiteratureError) as caught: index.build(str(uuid4()), encoder)
    assert caught.value.code == "encoder_changed"
    assert index.info()["generation"] is None


def test_real_build_search_and_fusion_share_bounded_source_verification(tmp_path, encoder, pdf_python, monkeypatch):
    library, _, _ = _ready(tmp_path, pdf_python, [["A solar cell converts sunlight into electrical energy."],
        ["The cat sleeps on the sofa."], ["Lithium electrolyte carries ions."]])
    batches = []; original = library.resolve_many
    def resolve_many(citations):
        batches.append(len(citations))
        return original(citations)
    monkeypatch.setattr(library, "resolve_many", resolve_many)
    monkeypatch.setattr(library, "resolve", lambda *a, **k:pytest.fail("Per-paragraph verification path was used"))
    index = DenseIndex(library); built = index.build(str(uuid4()), encoder)
    assert built["receipt"]["paragraphs"] == 3
    found = index.search("sunlight", encoder, limit=3)
    fused = index.hybrid_search("sunlight", encoder, limit=3)
    assert found["hits"][0]["citation"]["base"]["page_index"] == 0
    assert fused["hits"][0]["dense_rank"] == fused["hits"][0]["lexical_rank"] == 1
    assert batches and all(size == 3 for size in batches)
