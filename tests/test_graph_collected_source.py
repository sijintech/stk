"""Collected graph sources bind reads to registered bytes, including cache hits."""
from copy import deepcopy
import hashlib
import os
from pathlib import Path
import subprocess
import sys

import pytest

from suan.connectors.api import FileSource
from suan.graph import collected
from suan.graph.collected import CollectedFiles, local_resolver
from suan.graph.registry import GraphError
from suan.graph.resolve import LocalDirResolver


@pytest.fixture
def case(tmp_path):
    project = tmp_path / "project"
    root = project / "runs" / "case"
    (root / "sub").mkdir(parents=True)
    contents = {"a.dat": b"alpha", "sub/b.dat": b"beta", "empty.dat": b""}
    for path, data in contents.items():
        (root / path).write_bytes(data)
    (root / "foreign.dat").write_bytes(b"not registered")
    proof = {"project_root": str(project), "case_path": "runs/case", "files": [
        {"path": "runs/case/" + path, "sha256": hashlib.sha256(data).hexdigest()}
        for path, data in contents.items()]}
    return root, proof


def invalid(call, code="invalid_data"):
    with pytest.raises(GraphError) as caught:
        call()
    assert caught.value.code == code


def rewrite(path, data):
    before = path.stat()
    with path.open("r+b") as stream:
        stream.write(data)
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
    assert path.stat().st_ino == before.st_ino
    assert path.stat().st_size == before.st_size
    assert path.stat().st_mtime_ns == before.st_mtime_ns


def test_manifest_listing_and_verified_private_stream(case):
    root, proof = case
    source = local_resolver({"run": root}, {"run": proof}).resolve("run")
    assert isinstance(source, FileSource)
    assert [f.path for f in source.list()] == ["a.dat", "empty.dat", "sub/b.dat"]
    assert [f.path for f in source.list("sub")] == ["sub/b.dat"]
    assert source.list("sub/") == source.list("sub")
    assert [f.path for f in source.list("a.")] == ["a.dat"]
    assert source.list("a.dat") == []
    assert source.list(".") == source.list("./") == source.list()
    assert source.list("foreign") == []
    assert source.stat("a.dat").size == 5
    assert source.stat("a.dat").mtime == (root / "a.dat").stat().st_mtime
    assert source.exists("a.dat") and not source.exists("foreign.dat")
    for path in (".", "a.dat", "foreign.dat", "../foreign.dat"):
        assert source.local_path(path) is None
    for entry in proof["files"]:
        relative = entry["path"].removeprefix("runs/case/")
        assert source.sha256(relative) == entry["sha256"]
    with source.open("a.dat") as snapshot:
        assert snapshot.seekable()
        rewrite(root / "a.dat", b"omega")
        assert snapshot.read() == b"alpha"
        invalid(lambda: source.open("a.dat"))
    rewrite(root / "a.dat", b"alpha")
    with source.open("a.dat") as snapshot:
        assert snapshot.read() == b"alpha"


def test_proof_is_detached_and_guarded_root_is_never_resolved(case, monkeypatch):
    root, proof = case

    def unexpected_resolution(*args, **kw):
        raise AssertionError("A guarded binding must retain its lexical path")

    monkeypatch.setattr(Path, "resolve", unexpected_resolution)
    source = local_resolver({"run": str(root)}, {"run": proof}).resolve("run")
    proof["files"][0]["sha256"] = "0" * 64
    proof["files"].clear()
    proof["project_root"] = "/somewhere/else"
    assert source.sha256("a.dat") == hashlib.sha256(b"alpha").hexdigest()


def test_ordinary_bindings_keep_existing_behavior(case, tmp_path):
    root, proof = case
    ordinary = tmp_path / "ordinary"
    ordinary.mkdir()
    (ordinary / "readme.txt").write_bytes(b"old")
    assert isinstance(local_resolver({"plain": ordinary}), LocalDirResolver)
    assert isinstance(local_resolver({"plain": ordinary}, {}), LocalDirResolver)
    resolver = local_resolver({"run": root, "plain": ordinary}, {"run": proof})
    assert resolver.names() == ["plain", "run"]
    source = resolver.resolve("plain")
    assert source.local_path(".") == ordinary
    (ordinary / "readme.txt").write_bytes(b"new")
    with source.open("readme.txt") as stream:
        assert stream.read() == b"new"
    assert resolver.resolve("run").local_path(".") is None
    with pytest.raises(KeyError):
        resolver.resolve("unknown")


@pytest.mark.parametrize("change", [
    lambda p: p.pop("files"),
    lambda p: p.update(extra=True),
    lambda p: p.update(project_root="relative"),
    lambda p: p.update(project_root=1),
    lambda p: p.update(project_root="/root\0bad"),
    lambda p: p.update(case_path="."),
    lambda p: p.update(case_path="/case"),
    lambda p: p.update(case_path="runs/../case"),
    lambda p: p.update(case_path="runs//case"),
    lambda p: p.update(case_path=1),
    lambda p: p.update(files=[]),
    lambda p: p.update(files={}),
    lambda p: p.update(files=p["files"] * 3334),
    lambda p: p["files"][0].update(extra=True),
    lambda p: p["files"][0].pop("sha256"),
    lambda p: p["files"][0].update(sha256="short"),
    lambda p: p["files"][0].update(sha256="G" * 64),
    lambda p: p["files"][0].update(sha256=1),
    lambda p: p["files"][0].update(path="runs/case"),
    lambda p: p["files"][0].update(path="runs/case-other/a.dat"),
    lambda p: p["files"][0].update(path="runs/other/a.dat"),
    lambda p: p["files"][0].update(path="runs/case/sub/../a.dat"),
    lambda p: p["files"][0].update(path="runs/case/./a.dat"),
    lambda p: p["files"][0].update(path="runs/case\\a.dat"),
    lambda p: p["files"].append(deepcopy(p["files"][0])),
])
def test_invalid_proofs_are_bad_requests(case, change):
    root, original = case
    proof = deepcopy(original)
    change(proof)
    invalid(lambda: CollectedFiles(root, proof), "bad_request")


def test_invalid_binding_or_proof_mapping(case):
    root, proof = case
    invalid(lambda: CollectedFiles(root.parent, proof), "bad_request")
    invalid(lambda: CollectedFiles(root, None), "bad_request")
    invalid(lambda: local_resolver({"run": root}, []), "bad_request")
    invalid(lambda: local_resolver({"run": root}, {"other": proof}), "bad_request")
    invalid(lambda: local_resolver({"Bad": root}, {"Bad": proof}), "bad_request")
    invalid(lambda: local_resolver(None, {"run": proof}), "bad_request")


@pytest.mark.parametrize("path", ["missing.dat", "foreign.dat", "../a.dat", "/a.dat", "sub\\b.dat", ".", ""])
def test_missing_foreign_and_unsafe_files_are_refused(case, path):
    root, proof = case
    source = CollectedFiles(root, proof)
    invalid(lambda: source.open(path))
    invalid(lambda: source.sha256(path))
    assert not source.exists(path)


def test_missing_manifest_file_fails_listing_and_reads_then_recovers(case):
    root, proof = case
    source = CollectedFiles(root, proof)
    path = root / "a.dat"
    path.unlink()
    invalid(source.list)
    invalid(lambda: source.open("a.dat"))
    assert not source.exists("a.dat")
    path.write_bytes(b"alpha")
    assert source.sha256("a.dat") == proof["files"][0]["sha256"]


def link(source, target, *, directory=False):
    try:
        target.symlink_to(source, target_is_directory=directory)
    except (OSError, NotImplementedError):
        pytest.skip("Creating local links is unavailable")


@pytest.mark.parametrize("replacement", ["file", "parent", "case", "project"])
def test_byte_identical_links_are_refused_and_real_paths_recover(case, replacement):
    root, proof = case
    source = CollectedFiles(root, proof)
    target = {"file": root / "a.dat", "parent": root / "sub", "case": root,
              "project": Path(proof["project_root"])}[replacement]
    backup = target.with_name(target.name + "-real")
    target.rename(backup)
    link(backup, target, directory=replacement != "file")
    relative = "sub/b.dat" if replacement == "parent" else "a.dat"
    try:
        invalid(source.list)
        invalid(lambda: source.open(relative))
        invalid(lambda: source.sha256(relative))
        assert source.local_path(".") is None
    finally:
        target.unlink()
        backup.rename(target)
    with source.open(relative) as stream:
        assert stream.read() == (b"beta" if replacement == "parent" else b"alpha")


def test_file_size_budget_checked_before_snapshot(case, monkeypatch):
    root, proof = case
    source = CollectedFiles(root, proof)
    monkeypatch.setattr(collected, "MAX_FILE_BYTES", 4)
    monkeypatch.setattr(collected, "TemporaryFile", lambda **kw: pytest.fail("oversize snapshot"))
    invalid(lambda: source.stat("a.dat"))
    invalid(lambda: source.open("a.dat"))
    invalid(lambda: source.sha256("a.dat"))


def test_failed_verification_closes_partial_snapshot(case, monkeypatch):
    root, proof = case
    source = CollectedFiles(root, proof)
    snapshots = []
    temporary_file = collected.TemporaryFile

    def capture(**kw):
        stream = temporary_file(**kw)
        snapshots.append(stream)
        return stream

    monkeypatch.setattr(collected, "TemporaryFile", capture)
    rewrite(root / "a.dat", b"omega")
    invalid(lambda: source.open("a.dat"))
    assert len(snapshots) == 1 and snapshots[0].closed


def test_replacement_during_copy_refuses_and_closes_the_snapshot(case, monkeypatch):
    root, proof = case
    source = CollectedFiles(root, proof)
    temporary_file = collected.TemporaryFile
    snapshots = []
    replacement = root / "replacement.dat"
    replacement.write_bytes(b"omega")

    class ReplaceAfterWrite:
        def __init__(self, **kw):
            self.stream = temporary_file(**kw)
            snapshots.append(self.stream)

        def write(self, block):
            self.stream.write(block)
            os.replace(replacement, root / "a.dat")

        def close(self):
            self.stream.close()

    monkeypatch.setattr(collected, "TemporaryFile", ReplaceAfterWrite)
    invalid(lambda: source.open("a.dat"))
    assert len(snapshots) == 1 and snapshots[0].closed
    monkeypatch.setattr(collected, "TemporaryFile", temporary_file)
    (root / "a.dat").write_bytes(b"alpha")
    with source.open("a.dat") as stream:
        assert stream.read() == b"alpha"


def test_source_hash_refuses_changed_bytes_before_memory_or_disk_cache_hits(case, tmp_path):
    from suan.graph.cache import GraphCache
    from suan.graph.evaluator import EvaluationFailed, evaluate
    from suan.graph.registry import Port, Registry, binding, rel_path

    root, proof = case
    resolver = local_resolver({"run": root}, {"run": proof})
    registry = Registry(namespaces={"collected": 1})
    reads = []

    def fingerprint(ctx, inputs, params):
        return {"path": params["path"], "sha256": ctx.resolve(params["binding"]).sha256(params["path"])}

    @registry.node("collected.source.text", outputs=[Port("out", "value", value_type="string")],
                   params={"binding": binding(), "path": rel_path()}, fingerprint=fingerprint, cache="disk")
    def text(ctx, inputs, params):
        reads.append(params["path"])
        with ctx.resolve(params["binding"]).open(params["path"]) as stream:
            return stream.read().decode("utf-8")

    graph = {"schema": "stk.graph/1", "catalog": {"collected": 1}, "nodes": [
        {"id": "read", "type": "collected.source.text@1", "params": {"binding": "run", "path": "a.dat"}}],
        "outputs": {"text": "read.out"}}
    cache = GraphCache(tmp_path / "cache")
    first = evaluate(graph, registry=registry, resolver=resolver, cache=cache)
    assert first.outputs == {"text": "alpha"} and reads == ["a.dat"]
    assert evaluate(graph, registry=registry, resolver=resolver, cache=cache).cache == {"hits": 1, "misses": 0}
    disk = GraphCache(tmp_path / "cache")
    assert evaluate(graph, registry=registry, resolver=resolver, cache=disk).cache == {"hits": 1, "misses": 0}
    rewrite(root / "a.dat", b"omega")
    for candidate in (cache, disk, GraphCache()):
        with pytest.raises(EvaluationFailed) as caught:
            evaluate(graph, registry=registry, resolver=resolver, cache=candidate)
        assert caught.value.code == "invalid_data"
        assert caught.value.partial.outputs == {}
    assert reads == ["a.dat"]
    rewrite(root / "a.dat", b"alpha")
    assert evaluate(graph, registry=registry, resolver=resolver, cache=cache).outputs == {"text": "alpha"}
    assert reads == ["a.dat"]


def test_import_and_read_need_no_optional_scientific_dependencies(case):
    root, proof = case
    import json

    script = """
import importlib.abc
import json
import sys
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path=None, target=None):
        if name.split('.')[0] in {'numpy', 'h5py', 'vtk', 'vtkmodules'}:
            raise AssertionError('Optional dependency imported: ' + name)
sys.meta_path.insert(0, Block())
from suan.graph.collected import local_resolver
source = local_resolver({'run': sys.argv[1]}, {'run': json.loads(sys.argv[2])}).resolve('run')
with source.open('a.dat') as stream:
    assert stream.read() == b'alpha'
assert source.local_path('.') is None
"""
    environment = {name: value for name, value in os.environ.items() if name != "STK_TOKEN_PLAN_MODEL"}
    environment["STK_TOKEN_PLAN_API_KEY"] = ""
    completed = subprocess.run([sys.executable, "-c", script, str(root), json.dumps(proof)],
                               env=environment, text=True, capture_output=True, timeout=20)
    assert completed.returncode == 0, completed.stderr
