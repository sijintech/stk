"""Real globally ranked scopes, persistent database identity and retained cites."""
import copy
from pathlib import Path
import sys
import threading
from uuid import uuid4

import pytest

from suan.literature._io import LiteratureError
from suan.literature.collection import Collection, RECIPE
from suan.literature.dense import DenseIndex, Encoder
from suan.literature.store import Library
from test_literature_dense import encoder
from test_literature_pdf import make_pdf, pdf_python
from test_literature_store import _import


@pytest.mark.parametrize("scopes", [None, [], ["unknown"], ["owner", "owner"], [None]])
def test_explicit_valid_scopes_required_before_storage_or_inference(tmp_path, monkeypatch, scopes):
    library = Library(tmp_path / "absent")
    monkeypatch.setattr(library, "info", lambda:pytest.fail("Invalid scopes read storage"))
    selected = Encoder(tmp_path / "absent-assets", assets_sha256="a"*64, python=Path(sys.executable))
    monkeypatch.setattr(selected, "encode", lambda *a, **k:pytest.fail("Invalid scopes loaded model"))
    collection = Collection({"owner": library})
    with pytest.raises(LiteratureError): collection.search("sunlight", selected, scopes=scopes)
    assert not library.root.exists()


@pytest.fixture
def libraries(tmp_path, encoder, pdf_python):
    content = make_pdf([["A solar cell converts sunlight into electrical energy."], ["A lithium battery stores electrochemical energy."]])
    document_id = str(uuid4()); output = {}
    for scope in ("owner", "campus"):
        source = tmp_path / (scope + ".pdf"); source.write_bytes(content)
        library = Library(tmp_path / scope)
        imported = _import(library, source, document=document_id)
        version = imported["receipt"]["version_id"]
        library.index_pdf(str(uuid4()), version, python=pdf_python)
        built = DenseIndex(library).build(str(uuid4()), encoder)
        output[scope] = (library, version, built["receipt"])
    return output


def test_real_global_ranks_bind_both_scopes_even_identical_inner_generations(tmp_path, libraries, encoder, monkeypatch):
    owner, campus = libraries["owner"][0], libraries["campus"][0]
    assert owner.info()["database_id"] != campus.info()["database_id"]
    assert libraries["owner"][2]["generation"] == libraries["campus"][2]["generation"]
    absent = Library(tmp_path / "unselected-empty")
    collection = Collection({"owner": owner, "campus": campus, "unindexed": absent})
    found = collection.search("sunlight", encoder, scopes=["owner", "campus"], limit=2)
    assert not absent.root.exists()
    assert {h["corpus_id"] for h in found["hits"][:2]} == {"owner", "campus"}
    assert found["hits"][0]["corpus_id"] == "campus"
    assert found["hits"][0]["score"] == pytest.approx(2/61)
    assert found["hits"][1]["score"] == pytest.approx(2/62)
    assert found["scopes"][0]["encoder_fingerprint"] == found["scopes"][1]["encoder_fingerprint"]
    assert len(found["branches"]["dense"]) == 4 > len(found["hits"])
    assert len(found["branches"]["lexical"]) == 2
    assert [h["rank"] for h in found["branches"]["dense"]] == [1, 2, 3, 4]
    for branch in found["branches"].values():
        for item in branch:
            assert collection.resolve(item["citation"], scopes=["owner", "campus"])["database_id"] == item["database_id"]
    campus_hit = next(h for h in found["hits"] if h["corpus_id"] == "campus")
    citation = campus_hit["citation"]
    window = collection.resolve(campus_hit["dense_window"], scopes=["owner", "campus"])
    assert window["text"] in campus_hit["text"] and any(c["box"] for c in window["characters"])
    with pytest.raises(LiteratureError) as unselected: collection.resolve(citation, scopes=["owner"])
    assert unselected.value.code == "scope_not_selected"
    # Same content and same dense-generation SHA must not hide a scope remap.
    remapped = Collection({"campus": owner})
    with pytest.raises(LiteratureError) as other: remapped.resolve(citation, scopes=["campus"])
    assert other.value.code == "database_mismatch"
    reopened = Collection({"campus": Library(campus.root)})
    with monkeypatch.context() as guard:
        guard.setattr(encoder, "encode", lambda *a, **k:pytest.fail("Citation reopen invoked inference"))
        assert reopened.resolve(citation, scopes=["campus"])["text"] == campus_hit["text"]
        with pytest.raises(LiteratureError) as duplicate:
            Collection({"owner": owner, "alias": owner}).search("sunlight", encoder, scopes=["owner", "alias"])
        assert duplicate.value.code == "invalid_scope"
    found["recipe"]["weights"][0] = 99
    assert RECIPE["weights"] == [1, 1]
    wrong = copy.deepcopy(citation); wrong["corpus_generation"] = True
    with pytest.raises(LiteratureError): collection.resolve(wrong, scopes=["campus"])


def test_retained_scope_citation_survives_unrelated_import_and_rebuild_then_honors_revoke(tmp_path, libraries, encoder, pdf_python):
    owner, campus = libraries["owner"][0], libraries["campus"][0]
    collection = Collection({"owner": owner, "campus": campus})
    found = collection.search("sunlight", encoder, scopes=["owner", "campus"], limit=4)
    owner_cite = next(h["citation"] for h in found["hits"] if h["corpus_id"] == "owner")
    campus_cite = next(h["citation"] for h in found["hits"] if h["corpus_id"] == "campus")
    original = collection.resolve(owner_cite, scopes=["owner"])
    source = tmp_path / "unrelated.pdf"; source.write_bytes(make_pdf([["Distinct catalyst study for a separate experiment."]]))
    imported = _import(owner, source)
    # Historical evidence is valid even while fresh search needs an explicit build.
    assert collection.resolve(owner_cite, scopes=["owner"])["text"] == original["text"]
    with pytest.raises(LiteratureError) as stale: collection.search("sunlight", encoder, scopes=["owner", "campus"])
    assert stale.value.code == "dense_stale"
    owner.index_pdf(str(uuid4()), imported["receipt"]["version_id"], python=pdf_python)
    DenseIndex(owner).build(str(uuid4()), encoder)
    reopened = Collection({"owner": Library(owner.root), "campus": Library(campus.root)})
    assert reopened.resolve(owner_cite, scopes=["owner"])["text"] == original["text"]
    owner.revoke(str(uuid4()), libraries["owner"][1])
    with pytest.raises(LiteratureError) as revoked: reopened.resolve(owner_cite, scopes=["owner"])
    assert revoked.value.code == "authorization_revoked"
    assert reopened.resolve(campus_cite, scopes=["campus"])["text"] == original["text"]


def test_actual_global_query_revoke_before_publication_fails_closed(libraries, encoder, monkeypatch):
    owner, campus = libraries["owner"][0], libraries["campus"][0]
    collection = Collection({"owner": owner, "campus": campus}); original = encoder.encode; errors = []
    def revoke():
        try: owner.revoke(str(uuid4()), libraries["owner"][1])
        except Exception as error: errors.append(error)
    def encode(*a, **k):
        timer = threading.Timer(0.1, revoke); timer.start()
        try: return original(*a, **k)
        finally: timer.join()
    monkeypatch.setattr(encoder, "encode", encode)
    with pytest.raises(LiteratureError) as caught: collection.search("sunlight", encoder, scopes=["owner", "campus"])
    assert caught.value.code in {"dense_stale", "corpus_changed"} and not errors


def test_actual_global_query_rejects_model_selection_drift(libraries, encoder, monkeypatch):
    owner, campus = libraries["owner"][0], libraries["campus"][0]
    original = encoder.encode
    def encode(*a, **k):
        result = original(*a, **k)
        monkeypatch.setattr(encoder, "assets_sha256", "b"*64)
        return result
    monkeypatch.setattr(encoder, "encode", encode)
    with pytest.raises(LiteratureError) as caught:
        Collection({"owner": owner, "campus": campus}).search("sunlight", encoder, scopes=["owner", "campus"])
    assert caught.value.code == "corpus_changed"


def test_global_query_batches_exact_evidence_and_splits_read_only_budget(libraries, encoder, monkeypatch):
    import suan.literature.store as module
    corpora = {scope: item[0] for scope, item in libraries.items()}
    batches = []
    for library in corpora.values():
        original = library.resolve_many
        def resolve_many(citations, original=original):
            batches.append(len(citations))
            return original(citations)
        monkeypatch.setattr(library, "resolve_many", resolve_many)
        monkeypatch.setattr(library, "resolve", lambda *a, **k:pytest.fail("Per-candidate verification path was used"))
    monkeypatch.setattr(module, "MAX_CITATION_CHARACTERS", 80)
    found = Collection(corpora).search("sunlight", encoder, scopes=["owner", "campus"], limit=2)
    assert len(found["branches"]["dense"]) == 4 and len(found["branches"]["lexical"]) == 2
    assert {hit["corpus_id"] for hit in found["hits"]} == {"owner", "campus"}
    assert batches.count(2) == 2 and batches.count(1) == 4
