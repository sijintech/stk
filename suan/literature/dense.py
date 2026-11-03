"""Explicit local E5 inference and immutable, authorization-fenced generations.

No encoder is loaded on import, construction, reopen or info. Model preparation
is an external action. This module does not confer unified-corpus publication
rights, perform remote inference, or attest scientific retrieval quality.
"""
import base64
import hashlib
import json
import math
import os
from pathlib import Path
import re
import struct
import subprocess
import tempfile

from ._io import LiteratureError, fail
from .pdf import canonical, checksum
from .store import Library, _text, _uuid
from .encoder_profiles import profile_for_recipe, worker_identity_sha256

MAX_WINDOWS, MAX_GENERATIONS, MAX_OUTPUT = 20000, 8, 128 * 1024**2
_SHA = re.compile(r"[0-9a-f]{64}\Z")


def _sha(value):
    if type(value) is not str or not _SHA.fullmatch(value): fail()
    return value


def _query(value, maximum):
    try: return _text(value, maximum)
    except UnicodeError: fail()


def _resolve_citations(library, citations):
    """Share exact source checks within bounded read-only calls.

    Character geometry can exceed a batch byte budget even for short text.
    Split that read-only batch; inference and operation identities never retry.
    Callers still enforce their captured corpus/model before publication.
    """
    def batch(items):
        try: return library.resolve_many(items)
        except LiteratureError as error:
            if error.code != "citation_budget" or len(items) <= 1: raise
            middle = len(items) // 2
            return batch(items[:middle]) + batch(items[middle:])
    resolved = []
    for start in range(0, len(citations), 32):
        resolved.extend(batch(citations[start:start + 32]))
    return resolved


def _window_evidence(citation, resolved):
    text = resolved["text"][citation["start"]:citation["end"]]
    if hashlib.sha256(text.encode()).hexdigest() != citation["text_sha256"]:
        fail("citation_mismatch", "Dense cited source text changed")
    start = citation["base"]["start"] + citation["start"]
    end = citation["base"]["start"] + citation["end"]
    return {**resolved, "citation": dict(citation), "text": text,
            "characters": [c for c in resolved["characters"] if start <= c["text_start"] and c["text_end"] <= end]}


def _vector(item, dimensions=384):
    try:
        if type(dimensions) is not int or dimensions not in (384, 1024): fail()
        raw = base64.b64decode(item["vector_b64"], validate=True)
        if len(raw) != dimensions * 4 or hashlib.sha256(raw).hexdigest() != item["vector_sha256"]: fail()
        values = struct.unpack("<" + str(dimensions) + "f", raw)
        if any(not math.isfinite(x) for x in values) or abs(sum(x*x for x in values) - 1) > 0.0001: fail()
        return raw, values
    except (ValueError, KeyError, TypeError, struct.error):
        fail("invalid_embedding", "Encoder vector evidence is inconsistent")


def validate_embeddings(result, entries, query, assets_sha256, worker_sha256):
    try:
        identity = result["identity"]
        recipe = identity["recipe"]
        profile_for_recipe(recipe)
        if (result["format"] != "stk.literature-embeddings/1" or identity["assets_sha256"] != assets_sha256
                or result["fingerprint"] != checksum(identity) or identity["runtime"]["worker_sha256"] != worker_sha256
                or result["input_sha256"] != checksum({"entries": entries, "query": query})): fail()
        windows = result["windows"]
        if type(windows) is not list or len(windows) > MAX_WINDOWS: fail()
        position = 0
        for entry in entries:
            start = 0
            while position < len(windows) and windows[position]["id"] == entry["id"]:
                item = windows[position]
                if (any(type(item[k]) is not int for k in ("start", "end", "tokens"))
                        or item["start"] != start or not start < item["end"] <= len(entry["text"])
                        or not 1 <= item["tokens"] <= recipe["tokens"]
                        or item["text_sha256"] != hashlib.sha256(entry["text"][start:item["end"]].encode()).hexdigest()): fail()
                _vector(item, recipe["dimensions"])
                start, position = item["end"], position + 1
            if start != len(entry["text"]): fail("embedding_coverage", "Encoder omitted part of an evidence paragraph")
        if position != len(windows): fail()
        if query is None:
            if result["query"] is not None: fail()
        else:
            item = result["query"]
            if (item["query"] is not True or item["text_sha256"] != hashlib.sha256(query.encode()).hexdigest()
                    or type(item["tokens"]) is not int or not 1 <= item["tokens"] <= recipe["tokens"]): fail()
            _vector(item, recipe["dimensions"])
        return result
    except LiteratureError:
        raise
    except (KeyError, TypeError, ValueError, UnicodeError, RecursionError):
        fail("invalid_embedding", "Encoder output evidence is inconsistent")


class Encoder:
    """One selected, externally provisioned immutable model/interpreter pair."""
    def __init__(self, assets, *, assets_sha256, python):
        try:
            self.assets, self.python = Path(assets), Path(python)
        except (TypeError, ValueError):
            fail("invalid_path", "An absolute local encoder selection is required")
        if any(not p.is_absolute() or ".." in p.parts or "\0" in str(p) for p in (self.assets, self.python)):
            fail("invalid_path", "An absolute local encoder selection is required")
        self.assets_sha256 = _sha(assets_sha256)

    def selection(self):
        return {"assets_sha256": self.assets_sha256, "assets": str(self.assets), "python": str(self.python)}

    def encode(self, entries, *, query=None, timeout=600):
        if (type(entries) is not list or len(entries) > 10000 or type(timeout) not in (int, float)
                or not math.isfinite(timeout) or not 0 < timeout <= 3600): fail()
        seen = set()
        for entry in entries:
            if type(entry) is not dict or set(entry) != {"id", "text"}: fail()
            _sha(entry["id"])
            if entry["id"] in seen: fail()
            seen.add(entry["id"])
            try: _text(entry["text"], 8192)
            except UnicodeError: fail()
            if len(entry["text"]) > 2048: fail()
        if sum(len(e["text"]) for e in entries) > 4_000_000: fail("embedding_budget", "Encoder input budget exceeded")
        if query is not None:
            _query(query, 16384)
            if len(query) > 4096: fail("embedding_budget", "Query exceeds the supported scalar budget")
        # Freeze the selection for this one dispatch, even if a caller later
        # changes its configurable Encoder instance while the worker runs.
        assets, assets_sha, python = self.assets, self.assets_sha256, self.python
        worker = Path(__file__).with_name("dense_worker.py")
        worker_sha = worker_identity_sha256()
        request = {"assets": str(assets), "assets_sha256": assets_sha, "entries": entries, "query": query}
        safe = {k: v for k, v in os.environ.items() if k in {"SYSTEMROOT", "WINDIR", "TEMP", "TMP", "LANG", "LC_ALL"}}
        safe.update(STK_TOKEN_PLAN_API_KEY="", HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1",
                    HF_HUB_DISABLE_TELEMETRY="1", DO_NOT_TRACK="1", TOKENIZERS_PARALLELISM="false")
        with tempfile.TemporaryDirectory(prefix="stk-literature-dense-") as name:
            root = Path(name); source, target = root / "request.json", root / "embeddings.json"
            source.write_bytes(canonical(request))
            if os.name != "nt": source.chmod(0o600)
            try:
                done = subprocess.run([str(python), "-I", str(worker), str(source), str(target)],
                                      stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                      env=safe, timeout=timeout, check=False)
            except subprocess.TimeoutExpired: fail("embedding_timeout", "Local encoding exceeded its time budget")
            except OSError: fail("encoder_unavailable", "The selected local encoder is unavailable")
            if done.returncode == 3: fail("encoder_unavailable", "Selected interpreter has no pinned local encoder")
            if done.returncode == 5: fail("embedding_budget", "Encoding exceeded the supported token or corpus budget")
            if done.returncode or not target.is_file(): fail("embedding_failed", "Local encoding failed; verify assets and runtime")
            if target.stat().st_size > MAX_OUTPUT: fail("embedding_budget", "Embedding output budget exceeded")
            try:
                with target.open("rb") as stream: encoded = stream.read(MAX_OUTPUT + 1)
                if len(encoded) > MAX_OUTPUT: fail()
                result = json.loads(encoded, parse_constant=lambda _: fail())
            except (ValueError, UnicodeError, RecursionError): fail("invalid_embedding", "Encoder result cannot be decoded")
        if worker_identity_sha256() != worker_sha: fail("encoder_changed", "Encoder changed during inference")
        return validate_embeddings(result, entries, query, assets_sha, worker_sha)


class DenseIndex:
    """Bounded immutable index generations inside one Library's local database.

    Publication and current-version authorization use the same SQLite write
    transaction as Library.revoke. An encoder holds no authorization lease while
    it runs. A changed source corpus requires an explicit new build.
    """
    def __init__(self, library):
        if not isinstance(library, Library): fail()
        self.library = library

    @staticmethod
    def _exists(db):
        return db is not None and db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='dense_meta'").fetchone() is not None

    def info(self):
        with self.library._db() as db:
            row = None if not self._exists(db) else db.execute("SELECT current_generation FROM dense_meta WHERE id=1").fetchone()
            return {"generation": None if row is None else row[0], "corpus_generation": self.library._generation(db)}

    def _snapshot(self, db):
        rows = [] if db is None else db.execute("""SELECT p.*,v.source_sha256,v.source_bytes,v.title
            FROM paragraphs p JOIN versions v ON v.id=p.version_id
            WHERE v.active=1 AND v.current_extraction=p.extraction_id ORDER BY p.key""").fetchall()
        return [{"id": row["key"], "text": row["text"], "citation": self.library._citation(row, row["source_sha256"]),
                 "source_bytes": row["source_bytes"], "title": row["title"]} for row in rows]

    def build(self, operation_id, encoder, *, timeout=600):
        _uuid(operation_id)
        if (not isinstance(encoder, Encoder) or type(timeout) not in (int, float)
                or not math.isfinite(timeout) or not 0 < timeout <= 3600): fail()
        selected = encoder.selection()
        request = {**selected, "timeout": timeout}
        previous = self.library._reserve(operation_id, "dense_build", request)
        if previous is not None: return previous
        try:
            with self.library._db() as db:
                generation, snapshot = self.library._generation(db), self._snapshot(db)
                if self._exists(db) and db.execute("SELECT count(*) FROM dense_generations").fetchone()[0] >= MAX_GENERATIONS:
                    fail("embedding_budget", "Retained dense generation budget is full")
            if not snapshot: fail("index_required", "No active extracted paragraphs are available")
            # Resolve all exact source spans before embedding; no assumed ORM text.
            for start in range(0, len(snapshot), 32):
                items = snapshot[start:start + 32]
                evidence = _resolve_citations(self.library, [item["citation"] for item in items])
                if any(proof["text"] != item["text"] for item, proof in zip(items, evidence, strict=True)): fail()
            entries = [{"id": item["id"], "text": item["text"]} for item in snapshot]
            result = encoder.encode(entries, timeout=timeout)
            if encoder.selection() != selected or result["identity"]["assets_sha256"] != selected["assets_sha256"]:
                fail("encoder_changed", "Selected encoder changed during indexing")
            by_id = {item["id"]: item for item in snapshot}
            frozen = []
            for window in result["windows"]:
                base = by_id[window["id"]]
                evidence = {k: window[k] for k in ("start", "end", "tokens", "text_sha256", "vector_sha256")}
                evidence["citation"] = base["citation"]
                frozen.append({"key": checksum(evidence), **evidence})
            manifest = {"format": "stk.literature-dense-generation/1", "corpus_generation": generation,
                        "encoder": result["identity"], "encoder_fingerprint": result["fingerprint"], "windows": frozen}
            identity = checksum(manifest)
            sources = {(item["citation"]["source_sha256"], item["source_bytes"]) for item in snapshot}
            for sha, size in sources: self.library._verify_object(sha, size)
            with self.library._db(write=True) as db:
                if self.library._generation(db) != generation or self._snapshot(db) != snapshot:
                    fail("corpus_changed", "Literature authorization or extracted corpus changed during encoding")
                db.execute("CREATE TABLE IF NOT EXISTS dense_meta(id INTEGER PRIMARY KEY CHECK(id=1),current_generation TEXT NOT NULL)")
                db.execute("CREATE TABLE IF NOT EXISTS dense_generations(id TEXT PRIMARY KEY,manifest TEXT NOT NULL)")
                db.execute("""CREATE TABLE IF NOT EXISTS dense_windows(generation TEXT NOT NULL REFERENCES dense_generations(id),
                    key TEXT NOT NULL,position INTEGER NOT NULL,vector BLOB NOT NULL,PRIMARY KEY(generation,key))""")
                exists = db.execute("SELECT manifest FROM dense_generations WHERE id=?", (identity,)).fetchone()
                if exists is None:
                    if db.execute("SELECT count(*) FROM dense_generations").fetchone()[0] >= MAX_GENERATIONS:
                        fail("embedding_budget", "Retained dense generation budget is full")
                    db.execute("INSERT INTO dense_generations VALUES(?,?)", (identity, canonical(manifest).decode()))
                    db.executemany("INSERT INTO dense_windows VALUES(?,?,?,?)", [(identity, item["key"], i, _vector(vector, result["identity"]["recipe"]["dimensions"])[0])
                        for i, (item, vector) in enumerate(zip(frozen, result["windows"], strict=True))])
                else:
                    if canonical(json.loads(exists[0])) != canonical(manifest):
                        fail("embedding_changed", "Retained dense generation differs from its original manifest")
                    # Reusing an immutable generation is not permission to
                    # report success over missing or corrupted vector bytes.
                    for _ in self._vectors(db, identity, manifest): pass
                db.execute("INSERT INTO dense_meta VALUES(1,?) ON CONFLICT(id) DO UPDATE SET current_generation=excluded.current_generation", (identity,))
                self.library._finish(db, operation_id, {"generation": identity, "corpus_generation": generation,
                    "encoder_fingerprint": result["fingerprint"], "paragraphs": len(snapshot), "windows": len(frozen)})
        finally: self.library._inactive(operation_id)
        return self.library.operation(operation_id)

    def _current(self, db):
        if not self._exists(db): return None
        row = db.execute("SELECT g.id,g.manifest FROM dense_meta m JOIN dense_generations g ON g.id=m.current_generation WHERE m.id=1").fetchone()
        if row is None: fail()
        manifest = json.loads(row["manifest"])
        if checksum(manifest) != row["id"]: fail("embedding_changed", "Frozen embedding manifest changed")
        if manifest["corpus_generation"] != self.library._generation(db):
            fail("dense_stale", "Source corpus changed; explicitly rebuild the dense index")
        return row["id"], manifest

    @staticmethod
    def _vectors(db, identity, manifest):
        try: dimensions = profile_for_recipe(manifest["encoder"]["recipe"])["recipe"]["dimensions"]
        except (KeyError, TypeError, ValueError): fail("embedding_changed", "Frozen encoder recipe is unavailable")
        rows = db.execute("SELECT key,position,vector FROM dense_windows WHERE generation=? ORDER BY position", (identity,))
        count = 0
        for row in rows:
            if count >= len(manifest["windows"]):
                fail("embedding_changed", "Retained dense window count changed")
            item = manifest["windows"][count]
            raw = row["vector"]
            if (row["position"] != count or row["key"] != item["key"] or type(raw) is not bytes
                    or len(raw) != dimensions * 4 or hashlib.sha256(raw).hexdigest() != item["vector_sha256"]):
                fail("embedding_changed", "Frozen dense vectors changed")
            yield item, struct.unpack("<" + str(dimensions) + "f", raw)
            count += 1
        if count != len(manifest["windows"]):
            fail("embedding_changed", "Retained dense window count changed")

    def search(self, query, encoder, *, limit=10, timeout=120):
        _query(query, 16384)
        if type(limit) is not int or not 1 <= limit <= 20 or not isinstance(encoder, Encoder): fail()
        selection = encoder.selection()
        with self.library._db() as db: selected = self._current(db)
        if selected is None: return {"generation": None, "retriever": "local_e5_exact_cosine", "hits": []}
        identity, manifest = selected
        result = encoder.encode([], query=query, timeout=timeout)
        if encoder.selection() != selection:
            fail("encoder_changed", "Selected encoder changed during query encoding")
        if result["fingerprint"] != manifest["encoder_fingerprint"]:
            fail("encoder_mismatch", "Query encoder differs from the frozen index encoder")
        query_vector = _vector(result["query"], result["identity"]["recipe"]["dimensions"])[1]
        ranking = []
        with self.library._db() as db:
            if self._current(db) != selected: fail("corpus_changed", "Dense generation changed during query encoding")
            for item, vector in self._vectors(db, identity, manifest):
                score = sum(x*y for x, y in zip(query_vector, vector, strict=True))
                if not math.isfinite(score): fail()
                ranking.append((score, item["key"], item))
        ranking.sort(key=lambda item: (-item[0], item[1]))
        selected_hits = ranking[:limit]
        evidence = _resolve_citations(self.library, [item["citation"] for _, _, item in selected_hits])
        hits = []
        for (score, key, item), proof in zip(selected_hits, evidence, strict=True):
            citation = {"format": "stk.literature-dense-citation/1", "generation": identity,
                        "window_key": key, "base": item["citation"], "start": item["start"],
                        "end": item["end"], "text_sha256": item["text_sha256"]}
            resolved = _window_evidence(citation, proof)
            hits.append({"score": score, "text": resolved["text"], "text_status": resolved["text_status"],
                         "structure_status": "unreviewed", "citation": citation})
        with self.library._db() as db:
            if self._current(db) != selected: fail("corpus_changed", "Literature corpus changed during evidence resolution")
        if encoder.selection() != selection:
            fail("encoder_changed", "Selected encoder changed before evidence publication")
        return {"generation": identity, "corpus_generation": manifest["corpus_generation"],
                "encoder_fingerprint": result["fingerprint"], "query_sha256": hashlib.sha256(query.encode()).hexdigest(),
                "retriever": ("local_e5_exact_cosine" if result["identity"]["recipe"]["dimensions"] == 384
                              else "local_qwen3_exact_cosine"), "hits": hits}

    def resolve(self, citation):
        if (type(citation) is not dict or set(citation) != {"format", "generation", "window_key", "base", "start", "end", "text_sha256"}
                or citation["format"] != "stk.literature-dense-citation/1"
                or type(citation["start"]) is not int or type(citation["end"]) is not int): fail()
        for key in ("generation", "window_key", "text_sha256"): _sha(citation[key])
        # Reject caller-controlled containers before canonicalization or any
        # storage read; only the closed, bounded base citation may be encoded.
        base = citation["base"]
        if (type(base) is not dict or set(base) != {"format", "version_id", "source_sha256", "extraction_id", "paragraph_id", "text_sha256", "page_index", "start", "end"}
                or base["format"] != "stk.literature-citation/1"
                or any(type(base[k]) is not int or not 0 <= base[k] <= 250000 for k in ("page_index", "start", "end"))): fail()
        _uuid(base["version_id"])
        for key in ("source_sha256", "extraction_id", "paragraph_id", "text_sha256"): _sha(base[key])
        with self.library._db() as db:
            row = None if not self._exists(db) else db.execute("SELECT manifest FROM dense_generations WHERE id=?", (citation["generation"],)).fetchone()
            if row is None: fail("citation_mismatch", "Dense evidence generation is unavailable")
            manifest = json.loads(row[0])
            if checksum(manifest) != citation["generation"]: fail("embedding_changed", "Frozen dense manifest changed")
            item = next((x for x in manifest["windows"] if x["key"] == citation["window_key"]), None)
            if item is None or any(citation[k] != item[k] for k in ("start", "end", "text_sha256")) or canonical(citation["base"]) != canonical(item["citation"]): fail("citation_mismatch", "Citation differs from the frozen embedding span")
        return _window_evidence(citation, self.library.resolve(citation["base"]))

    def hybrid_search(self, query, encoder, *, limit=10, timeout=120):
        """Deterministic reciprocal-rank fusion of actual lexical/dense results.

        Rank paragraphs using their first dense window; retain that exact window
        citation separately and return the full frozen paragraph as context.
        A query with no literal match still participates in dense retrieval.
        """
        _query(query, 256)
        if type(limit) is not int or not 1 <= limit <= 20 or not isinstance(encoder, Encoder): fail()
        selection = encoder.selection()
        dense = self.search(query, encoder, limit=20, timeout=timeout)
        sparse = self.library.search(query, limit=20)
        if dense["generation"] is None:
            fail("index_required", "Explicitly build a dense generation before fused retrieval")
        if dense["corpus_generation"] != sparse["generation"]:
            fail("corpus_changed", "Corpus changed between retrieval branches")
        candidates, dense_rank = {}, 0
        for hit in dense["hits"]:
            base = hit["citation"]["base"]; key = checksum(base)
            if key in candidates: continue
            dense_rank += 1
            candidates[key] = {"citation": base, "dense_window": hit["citation"],
                               "dense_rank": dense_rank, "lexical_rank": None, "score": 1 / (60 + dense_rank)}
        for rank, hit in enumerate(sparse["hits"], 1):
            base = hit["citation"]; key = checksum(base)
            item = candidates.setdefault(key, {"citation": base, "dense_window": None,
                                               "dense_rank": None, "lexical_rank": None, "score": 0.0})
            item["lexical_rank"] = rank; item["score"] += 1 / (60 + rank)
        ordered = sorted(candidates.items(), key=lambda item: (-item[1]["score"], item[0]))
        selected_hits = ordered[:limit]
        evidence = _resolve_citations(self.library, [item["citation"] for _, item in selected_hits])
        hits = []
        for (_, item), resolved in zip(selected_hits, evidence, strict=True):
            hits.append({**item, "text": resolved["text"], "text_status": resolved["text_status"], "structure_status": "unreviewed"})
        with self.library._db() as db:
            current = self._current(db)
            if current is None or current[0] != dense["generation"] or self.library._generation(db) != sparse["generation"]:
                fail("corpus_changed", "Corpus changed during fused evidence resolution")
        if encoder.selection() != selection:
            fail("encoder_changed", "Selected encoder changed before fused evidence publication")
        return {"generation": dense["generation"], "corpus_generation": sparse["generation"],
                "encoder_fingerprint": dense["encoder_fingerprint"], "query_sha256": dense["query_sha256"],
                "retriever": ("local_fts5_qwen3_rrf" if dense["retriever"] == "local_qwen3_exact_cosine"
                              else "local_fts5_e5_rrf"),
                "fusion": {"constant": 60, "lexical_limit": 20, "dense_window_limit": 20},
                "hits": hits}
