"""Explicit local scopes with globally ranked, database-bound evidence.

Selecting a Library is a local read choice, not publication or external-model
permission. Search requires fresh selected generations; retained citations remain
valid after unrelated changes while their exact source approval remains active.
"""
import hashlib
import heapq
import json
import math
from types import MappingProxyType
import re

from ._io import fail
from .dense import DenseIndex, Encoder, _query, _resolve_citations, _sha, _vector
from .pdf import canonical, checksum
from .store import Library, _uuid

_CORPUS = re.compile(r"[a-z][a-z0-9_-]{0,63}\Z")
RECIPE = {"format": "stk.local-collection-ranking/1", "dense": "global_exact_cosine_top20_windows_then_distinct_paragraphs",
          "lexical": "literal_fts5_top20_each_global_order_local_rank_corpus_database_citation",
          "lexical_global_limit": 20, "dense_global_window_limit": 20,
          "fusion": "reciprocal_rank", "constant": 60, "weights": [1, 1], "maximum_scopes": 8}


def _corpus(value):
    if type(value) is not str or not _CORPUS.fullmatch(value): fail("invalid_scope", "Invalid local literature scope")
    return value


def _inner(value):
    """Check bounded closed citation shapes before canonicalizing caller data."""
    if type(value) is not dict: fail()
    if value.get("format") == "stk.literature-dense-citation/1":
        if set(value) != {"format", "generation", "window_key", "base", "start", "end", "text_sha256"}: fail()
        for key in ("generation", "window_key", "text_sha256"): _sha(value[key])
        if any(type(value[k]) is not int or not 0 <= value[k] <= 2048 for k in ("start", "end")): fail()
        if type(value["base"]) is not dict or value["base"].get("format") != "stk.literature-citation/1": fail()
        _inner(value["base"])
    elif value.get("format") == "stk.literature-citation/1":
        if set(value) != {"format", "version_id", "source_sha256", "extraction_id", "paragraph_id", "text_sha256", "page_index", "start", "end"}: fail()
        _uuid(value["version_id"])
        for key in ("source_sha256", "extraction_id", "paragraph_id", "text_sha256"): _sha(value[key])
        if any(type(value[k]) is not int or not 0 <= value[k] <= 250000 for k in ("page_index", "start", "end")): fail()
    else: fail()
    return value


class Collection:
    """A fixed local scope registry; callers explicitly select each query scope."""
    def __init__(self, corpora):
        if type(corpora) is not dict or not 1 <= len(corpora) <= 8: fail("invalid_scope", "Invalid local literature scope set")
        for identity, library in corpora.items():
            _corpus(identity)
            if not isinstance(library, Library): fail("invalid_scope", "A local Library is required")
        self._corpora = MappingProxyType(dict(corpora))

    def _selected(self, scopes):
        if type(scopes) is not list or not 1 <= len(scopes) <= 8: fail("invalid_scope", "Explicit local scopes are required")
        for identity in scopes:
            _corpus(identity)
            if identity not in self._corpora: fail("scope_not_selected", "Local literature scope is unavailable")
        if len(set(scopes)) != len(scopes): fail("invalid_scope", "Duplicate local scopes are not allowed")
        return sorted(scopes)

    def _capture(self, selected):
        states, seen = [], set()
        for corpus_id in selected:
            library = self._corpora[corpus_id]; info = library.info()
            database_id = info["database_id"]
            if database_id is None: fail("index_required", "Selected local corpus has no frozen index")
            _uuid(database_id)
            if database_id in seen: fail("invalid_scope", "Selected scopes refer to the same database identity")
            seen.add(database_id)
            index = DenseIndex(library)
            with library._db() as db: current = index._current(db)
            if current is None: fail("index_required", "Selected local corpus needs an explicit dense build")
            generation, manifest = current
            if manifest["corpus_generation"] != info["generation"]:
                fail("corpus_changed", "Selected local corpus changed during preparation")
            states.append({"corpus_id": corpus_id, "database_id": database_id,
                           "corpus_generation": info["generation"], "dense_generation": generation,
                           "encoder_fingerprint": manifest["encoder_fingerprint"], "manifest": manifest})
        if len({state["encoder_fingerprint"] for state in states}) != 1:
            fail("encoder_mismatch", "Selected corpora have different frozen encoder proofs")
        return states

    @staticmethod
    def _public(state):
        return {key: state[key] for key in ("corpus_id", "database_id", "corpus_generation", "dense_generation", "encoder_fingerprint")}

    @staticmethod
    def _key(state, inner):
        return state["corpus_id"], state["database_id"], checksum(inner)

    @staticmethod
    def _envelope(state, inner):
        body = {"format": "stk.literature-collection-citation/1", "corpus_id": state["corpus_id"],
                "database_id": state["database_id"], "corpus_generation": state["corpus_generation"],
                "dense_generation": state["dense_generation"], "inner": inner}
        return json.loads(canonical({**body, "evidence_sha256": checksum(body)}))

    def search(self, query, encoder, *, scopes, limit=10, timeout=120):
        _query(query, 256)
        if not isinstance(encoder, Encoder) or type(limit) is not int or not 1 <= limit <= 20: fail()
        selected = self._selected(scopes); states = self._capture(selected)
        selection = encoder.selection()
        if any(state["manifest"]["encoder"]["assets_sha256"] != selection["assets_sha256"] for state in states):
            fail("encoder_mismatch", "Selected query model differs from corpus proofs")
        encoded = encoder.encode([], query=query, timeout=timeout)
        if encoded["fingerprint"] != states[0]["encoder_fingerprint"]:
            fail("encoder_mismatch", "Query encoder differs from the frozen corpus encoder")
        query_vector = _vector(encoded["query"], encoded["identity"]["recipe"]["dimensions"])[1]
        def scored():
            for state in states:
                library = self._corpora[state["corpus_id"]]; index = DenseIndex(library)
                with library._db() as db:
                    current = index._current(db)
                    if current is None or current[0] != state["dense_generation"]:
                        fail("corpus_changed", "Selected corpus changed during query encoding")
                    for item, vector in index._vectors(db, current[0], current[1]):
                        score = sum(x*y for x, y in zip(query_vector, vector, strict=True))
                        if not math.isfinite(score): fail()
                        key = (*self._key(state, item["citation"]), item["key"])
                        yield score, key, state, item
        top = heapq.nsmallest(20, scored(), key=lambda item: (-item[0], item[1]))
        candidates, rank = {}, 0
        for score, _, state, item in top:
            key = self._key(state, item["citation"])
            if key in candidates: continue
            rank += 1
            window = {"format": "stk.literature-dense-citation/1", "generation": state["dense_generation"],
                      "window_key": item["key"], "base": item["citation"], "start": item["start"],
                      "end": item["end"], "text_sha256": item["text_sha256"]}
            candidates[key] = {"state": state, "inner": item["citation"], "dense_window": window,
                               "dense_score": score, "dense_rank": rank, "lexical_rank": None, "score": 1/(60+rank)}
        lexical = []
        for state in states:
            sparse = self._corpora[state["corpus_id"]].search(query, limit=20)
            if sparse["generation"] != state["corpus_generation"]: fail("corpus_changed", "Selected lexical corpus changed")
            for local_rank, hit in enumerate(sparse["hits"], 1):
                lexical.append((local_rank, self._key(state, hit["citation"]), state, hit["citation"]))
        lexical.sort(key=lambda item: (item[0], item[1]))
        for rank, (_, key, state, inner) in enumerate(lexical[:20], 1):
            item = candidates.setdefault(key, {"state": state, "inner": inner, "dense_window": None,
                                               "dense_score": None, "dense_rank": None, "lexical_rank": None, "score": 0.0})
            item["lexical_rank"] = rank; item["score"] += 1/(60+rank)
        # Retain each complete bounded branch for evaluation and frozen query
        # evidence; fused top-K alone cannot reconstruct either branch's top-K.
        verified = {}
        for state in states:
            members = {canonical(window["citation"]) for window in state["manifest"]["windows"]}
            items = [(key, item) for key, item in candidates.items() if item["state"]["corpus_id"] == state["corpus_id"]]
            if any(canonical(item["inner"]) not in members for _, item in items):
                fail("citation_mismatch", "Citation is absent from the selected generation")
            evidence = _resolve_citations(self._corpora[state["corpus_id"]], [item["inner"] for _, item in items])
            for (key, item), resolved in zip(items, evidence, strict=True):
                verified[key] = {**resolved, "citation": self._envelope(state, item["inner"]),
                                 "corpus_id": state["corpus_id"], "database_id": state["database_id"]}
        branches = {"dense": [], "lexical": []}
        for branch, rank_key in (("dense", "dense_rank"), ("lexical", "lexical_rank")):
            ordered = sorted(((item[rank_key], key, item) for key, item in candidates.items() if item[rank_key] is not None),
                             key=lambda item: (item[0], item[1]))
            for rank, key, item in ordered:
                branches[branch].append({**self._public(item["state"]), "rank": rank,
                    "score": item["dense_score"] if branch == "dense" else None,
                    "citation": verified[key]["citation"]})
        hits = []
        for _, item in sorted(candidates.items(), key=lambda item: (-item[1]["score"], item[0]))[:limit]:
            state = item["state"]; envelope = self._envelope(state, item["inner"])
            resolved = verified[self._key(state, item["inner"])]
            hits.append({**self._public(state), "score": item["score"], "dense_score": item["dense_score"],
                         "dense_rank": item["dense_rank"], "lexical_rank": item["lexical_rank"],
                         "text": resolved["text"], "text_status": resolved["text_status"], "structure_status": "unreviewed",
                         "citation": envelope, "dense_window": None if item["dense_window"] is None else self._envelope(state, item["dense_window"])})
        if (encoder.selection() != selection or [self._public(s) for s in self._capture(selected)] != [self._public(s) for s in states]):
            fail("corpus_changed", "Selected corpus or encoder changed before evidence publication")
        retriever = ("local_collection_fts5_e5_rrf" if encoded["identity"]["recipe"]["dimensions"] == 384
                     else "local_collection_fts5_qwen3_rrf")
        return {"retriever": retriever, "recipe": json.loads(canonical(RECIPE)),
                "query_sha256": hashlib.sha256(query.encode()).hexdigest(), "scopes": [self._public(state) for state in states],
                "branches": branches, "hits": hits}

    def resolve(self, citation, *, scopes):
        selected = self._selected(scopes)
        if (type(citation) is not dict or set(citation) != {"format", "corpus_id", "database_id", "corpus_generation", "dense_generation", "inner", "evidence_sha256"}
                or citation["format"] != "stk.literature-collection-citation/1"
                or type(citation["corpus_generation"]) is not int or not 0 <= citation["corpus_generation"] <= 2**63-1): fail()
        corpus_id = _corpus(citation["corpus_id"])
        if corpus_id not in selected: fail("scope_not_selected", "Citation scope is not selected")
        _uuid(citation["database_id"]); _sha(citation["dense_generation"]); _sha(citation["evidence_sha256"])
        inner = _inner(citation["inner"])
        if checksum({k:v for k,v in citation.items() if k != "evidence_sha256"}) != citation["evidence_sha256"]:
            fail("citation_mismatch", "Collection citation identity changed")
        library = self._corpora[corpus_id]
        if library.info()["database_id"] != citation["database_id"]:
            fail("database_mismatch", "Citation belongs to another local database")
        with library._db() as db:
            row = None if not DenseIndex._exists(db) else db.execute("SELECT manifest FROM dense_generations WHERE id=?", (citation["dense_generation"],)).fetchone()
            if row is None: fail("citation_mismatch", "Retained citation generation is unavailable")
            manifest = json.loads(row[0])
            if checksum(manifest) != citation["dense_generation"] or manifest["corpus_generation"] != citation["corpus_generation"]:
                fail("citation_mismatch", "Retained citation generation changed")
            base = inner["base"] if inner["format"] == "stk.literature-dense-citation/1" else inner
            if not any(canonical(w["citation"]) == canonical(base) for w in manifest["windows"]):
                fail("citation_mismatch", "Citation is absent from the retained generation")
        if inner["format"] == "stk.literature-dense-citation/1":
            if inner["generation"] != citation["dense_generation"]: fail("citation_mismatch", "Inner citation generation differs")
            resolved = DenseIndex(library).resolve(inner)
        else: resolved = library.resolve(inner)
        # Current permission and DB identity, not current generation equality,
        # determine retained historical citation validity after source hashing.
        with library._db() as db:
            if db.execute("SELECT identity FROM meta WHERE id=1").fetchone()[0] != citation["database_id"]:
                fail("database_mismatch", "Citation belongs to another local database")
            library._version(db, base["version_id"], active=True)
        return {**resolved, "citation": json.loads(canonical(citation)), "corpus_id": corpus_id, "database_id": citation["database_id"]}
