"""suan.graph.resolve: bindings to local directories (confined) and to Runtime tasks (verified downloads)."""
import hashlib
import os
from pathlib import Path

import pytest

from suan.connectors.api import FileInfo, FileSource, Resolver
from suan.graph.registry import BudgetExceeded, GraphError
from suan.graph.resolve import (BindingResolver, HashMemo, LocalDirResolver, LocalDirSource, PathNotAllowed,
                                RuntimeResolver, RuntimeTaskSource, check_relative_path)


def sha(data):
    return hashlib.sha256(data).hexdigest()


@pytest.fixture
def tree(tmp_path):
    root = tmp_path / "run"
    (root / "sub" / "deep").mkdir(parents=True)
    (root / "a.txt").write_bytes(b"alpha")
    (root / "sub" / "b.dat").write_bytes(b"beta")
    (root / "sub" / "deep" / "c.npy").write_bytes(b"gamma")
    (tmp_path / "secret.txt").write_bytes(b"outside")
    return root


def symlink(link, target):
    try:
        os.symlink(target, link)
    except (OSError, NotImplementedError):
        pytest.skip("symbolic links are not available")


@pytest.mark.parametrize("path", ["/etc/passwd", "../secret.txt", "sub/../../secret.txt", "C:/x", "c:x", "a\\b",
                                  "a\x00b"])
def test_relative_paths_are_confined(path):
    with pytest.raises(PathNotAllowed) as info:
        check_relative_path(path)
    assert info.value.code == "path_not_allowed" and isinstance(info.value, PermissionError)


def test_relative_path_normalization():
    assert check_relative_path("./sub//b.dat") == "sub/b.dat"
    assert check_relative_path(".", allow_root=True) == "" and check_relative_path("", allow_root=True) == ""
    with pytest.raises(PathNotAllowed):
        check_relative_path(".")
    with pytest.raises(PathNotAllowed):
        check_relative_path(3)


def test_local_dir_source(tree):
    source = LocalDirSource(tree, binding="run")
    assert isinstance(source, FileSource)
    assert source.list() == [FileInfo("a.txt", 5, (tree / "a.txt").stat().st_mtime),
                             FileInfo("sub/b.dat", 4, (tree / "sub" / "b.dat").stat().st_mtime),
                             FileInfo("sub/deep/c.npy", 5, (tree / "sub" / "deep" / "c.npy").stat().st_mtime)]
    assert [f.path for f in source.list("sub")] == ["sub/b.dat", "sub/deep/c.npy"]
    assert source.list("missing") == [] and source.list("a.txt") == []
    with source.open("sub/b.dat") as stream:
        assert stream.read() == b"beta"
    assert source.local_path("sub/b.dat") == (tree / "sub" / "b.dat").resolve()
    assert source.local_path("") == source.local_path(".") == tree.resolve()
    assert source.sha256("a.txt") == sha(b"alpha")
    with pytest.raises(FileNotFoundError, match="'run'"):
        source.open("nope.txt")
    with pytest.raises(FileNotFoundError):
        source.sha256("sub")
    with pytest.raises(FileNotFoundError):
        source.local_path("nope")
    for bad in ("../secret.txt", "/etc/passwd"):
        with pytest.raises(PathNotAllowed):
            source.open(bad)
        with pytest.raises(PathNotAllowed):
            source.list(bad)
    with pytest.raises(FileNotFoundError):
        LocalDirSource(tree / "missing")


def test_symbolic_links_cannot_escape(tree):
    symlink(tree / "leak.txt", tree.parent / "secret.txt")
    symlink(tree / "leakdir", tree.parent)
    symlink(tree / "inside.txt", tree / "a.txt")
    source = LocalDirSource(tree)
    for path in ("leak.txt", "leakdir/secret.txt"):
        with pytest.raises(PathNotAllowed, match="leaves the binding"):
            source.open(path)
        with pytest.raises(PathNotAllowed):
            source.sha256(path)
    with pytest.raises(PathNotAllowed):
        source.list("leakdir")
    listed = [f.path for f in source.list()]
    assert "leak.txt" not in listed and not any(p.startswith("leakdir") for p in listed)
    assert "inside.txt" in listed and source.open("inside.txt").read() == b"alpha"


def test_hash_memo_is_keyed_by_stat_and_persisted(tree, tmp_path):
    memo_path = tmp_path / "memo" / "hashes.sqlite"
    source = LocalDirSource(tree, hash_memo=HashMemo(memo_path))
    target = tree / "a.txt"
    assert source.sha256("a.txt") == sha(b"alpha")
    stat = target.stat()
    target.write_bytes(b"ALPHA")  # same size; restore the mtime: only the memo can answer now
    os.utime(target, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    assert LocalDirSource(tree, hash_memo=HashMemo(memo_path)).sha256("a.txt") == sha(b"alpha")
    assert LocalDirSource(tree).sha256("a.txt") == sha(b"ALPHA")  # no persisted memo: re-hashed
    target.write_bytes(b"alpha2")  # size changed: the memo misses
    assert LocalDirSource(tree, hash_memo=HashMemo(memo_path)).sha256("a.txt") == sha(b"alpha2")


def test_local_dir_resolver(tree):
    resolver = LocalDirResolver({"run": tree, "other": tree / "sub"})
    assert isinstance(resolver, Resolver)
    assert resolver.names() == ["other", "run"]
    assert resolver.resolve("other").open("b.dat").read() == b"beta"
    with pytest.raises(KeyError):
        resolver.resolve("missing")
    with pytest.raises(GraphError) as info:
        LocalDirResolver({"Bad-Name": tree})
    assert info.value.code == "unknown_binding"
    with pytest.raises(FileNotFoundError):
        LocalDirResolver({"run": tree / "missing"})


class FakeRuntime:
    """The two RuntimeClient methods the resolver uses, over an in-memory task."""

    def __init__(self, files):
        self.files = files
        self.downloads = []

    def artifacts(self, task_id):
        assert task_id == "task1"
        return [{"path": path, "size": len(data), "sha256": sha(data), "media_type": "application/octet-stream"}
                for path, data in self.files.items()]

    def download(self, task_id, remote_path, destination):
        self.downloads.append(remote_path)
        data = self.files[remote_path]
        Path(destination).write_bytes(data)
        return Path(destination)


def test_runtime_task_source(tmp_path):
    files = {"Polar.00000100.dat": b"frame", "out/energy_out.dat": b"energy", "../evil": b"x", "big.bin": b"0" * 64}
    client = FakeRuntime(files)
    source = RuntimeTaskSource(client, "task1", tmp_path / "downloads", max_bytes=32, binding="run")
    assert isinstance(source, FileSource)
    assert [f.path for f in source.list()] == ["Polar.00000100.dat", "big.bin", "out/energy_out.dat"]
    assert [f.path for f in source.list("out")] == ["out/energy_out.dat"]
    assert source.sha256("Polar.00000100.dat") == sha(b"frame") and client.downloads == []  # no download to hash
    local = source.local_path("Polar.00000100.dat")
    digest = sha(b"frame")
    assert local == (tmp_path / "downloads" / digest[:2] / (digest + ".dat")).resolve()
    assert source.open("Polar.00000100.dat").read() == b"frame"
    assert client.downloads == ["Polar.00000100.dat"]  # verified once, then reused
    again = RuntimeTaskSource(client, "task1", tmp_path / "downloads")  # e.g. the next request
    assert again.open("Polar.00000100.dat").read() == b"frame" and client.downloads == ["Polar.00000100.dat"]
    before = local.stat()
    local.write_bytes(b"FRAME")  # a modified cached copy is downloaded (and verified) again
    os.utime(local, ns=(before.st_atime_ns, before.st_mtime_ns + 10**9))
    assert again.open("Polar.00000100.dat").read() == b"frame" and len(client.downloads) == 2
    assert source.local_path("") is None
    with pytest.raises(FileNotFoundError, match="finished"):
        source.open("missing.dat")
    with pytest.raises(PathNotAllowed):
        source.open("../evil")
    with pytest.raises(BudgetExceeded, match="1 GiB"):
        source.open("big.bin")
    with pytest.raises(GraphError):
        RuntimeTaskSource(client, "../task", tmp_path)


def test_runtime_resolver_binds_only_task_ids(tmp_path):
    client = FakeRuntime({"a.txt": b"alpha"})
    resolver = RuntimeResolver(client, tmp_path / "downloads")
    assert resolver.names() == []
    bound = resolver.bind({"run": {"task_id": "task1"}})
    assert bound.names() == ["run"] and resolver.names() == []
    assert bound.resolve("run") is bound.resolve("run")
    assert bound.resolve("run").open("a.txt").read() == b"alpha"
    with pytest.raises(KeyError):
        bound.resolve("other")
    for bad in ({"run": {"path": "/data"}}, {"run": {"task_id": "t", "path": "x"}}, {"run": {"task_id": "a/b"}},
                {"Run": {"task_id": "t"}}):
        with pytest.raises(GraphError) as info:
            resolver.bind(bad)
        assert info.value.code == "unknown_binding"
    assert RuntimeResolver(client, tmp_path, {"run": "task1"}).resolve("run").task_id == "task1"


def test_binding_resolver_combines_sources(tree, tmp_path):
    local = LocalDirResolver({"run": tree})
    runtime = RuntimeResolver(FakeRuntime({"a.txt": b"remote"}), tmp_path / "dl", {"run": "task1", "task": "task1"})
    combined = BindingResolver(local, runtime, {"extra": LocalDirSource(tree / "sub")})
    assert combined.names() == ["extra", "run", "task"]
    assert combined.resolve("run").open("a.txt").read() == b"alpha"  # the first resolver wins
    assert combined.resolve("task").open("a.txt").read() == b"remote"
    assert combined.resolve("extra").open("b.dat").read() == b"beta"
    with pytest.raises(KeyError):
        combined.resolve("nope")
    rebound = combined.bind({"late": {"task_id": "task1"}})
    assert rebound.resolve("late").open("a.txt").read() == b"remote"


def test_evaluator_confines_graph_paths(tree):
    pytest.importorskip("numpy")
    from graph_testnodes import make_registry
    from suan.graph.evaluator import EvaluationFailed, evaluate
    from suan.graph.schema import GraphValidationError
    registry = make_registry()
    resolver = LocalDirResolver({"run": tree})

    def run(path):
        document = {"schema": "stk.graph/1", "outputs": {"out": "f.out"},
                    "nodes": [{"id": "f", "type": "test.source.file@1", "params": {"binding": "run", "path": path}}]}
        return evaluate(document, registry=registry, resolver=resolver)
    assert run("sub/b.dat").outputs["out"] == {"size": 4, "sha256": sha(b"beta")}
    for path in ("../secret.txt", "/etc/passwd", "sub\\b.dat"):  # graphs never contain such paths
        with pytest.raises(GraphValidationError) as info:
            run(path)
        assert [issue.code for issue in info.value.issues] == ["invalid_param"]
    with pytest.raises(EvaluationFailed) as info:
        run("nope.txt")
    assert info.value.code == "missing_file" and info.value.node == "f"
    symlink(tree / "leak.txt", tree.parent / "secret.txt")
    with pytest.raises(EvaluationFailed) as info:
        run("leak.txt")
    assert info.value.code == "path_not_allowed" and info.value.node == "f"
    assert registry.runs["f"] == 1  # only the valid file was ever read


def test_runtime_resolver_against_a_real_runtime(runtime, tmp_path):
    from conftest import finish
    from suan.runtime.models import TaskSpec
    client, supervisor, _, _ = runtime
    workspace = client.create_workspace("graph")["id"]
    program = ("from pathlib import Path; Path('out').mkdir(); Path('out/field.dat').write_text('1 2 3'); "
               "Path('log.txt').write_text('done')")
    task = finish(client, supervisor, client.submit(TaskSpec(workspace, ["{python}", "-c", program]))["id"])
    assert task["state"] == "succeeded"
    source = RuntimeResolver(client, tmp_path / "downloads").bind({"run": {"task_id": task["id"]}}).resolve("run")
    assert [f.path for f in source.list()] == ["log.txt", "out/field.dat"]
    assert source.sha256("out/field.dat") == sha(b"1 2 3")
    assert source.open("out/field.dat").read() == b"1 2 3"
    assert source.local_path("out/field.dat").name == sha(b"1 2 3") + ".dat"


# ---------------------------------------------------------------------------
# The built-in muFerro/file sources through both resolvers (one FileSource implementation, one missing-file error)


class DirectoryRuntime:
    """RuntimeClient.artifacts/download over a local directory tree (what a finished task publishes)."""

    def __init__(self, root):
        self.root = Path(root)
        self.downloads = []

    def artifacts(self, task_id):
        return [{"path": p.relative_to(self.root).as_posix(), "size": p.stat().st_size, "sha256": sha(p.read_bytes())}
                for p in sorted(self.root.rglob("*")) if p.is_file()]

    def download(self, task_id, remote_path, destination):
        self.downloads.append(remote_path)
        Path(destination).write_bytes((self.root / remote_path).read_bytes())
        return Path(destination)


def muferro_graph(case_dir=".", frame="Polar.00000002.dat"):
    prefix = "" if case_dir in (".", "./") else case_dir.rstrip("/") + "/"
    return {"schema": "stk.graph/1", "outputs": {"frames": "run.frames", "energy": "run.energy", "polar": "polar.out",
                                                 "file": "file.out"},
            "nodes": [{"id": "run", "type": "stk.source.muferro_run@1", "params": {"binding": "run", "case_dir": case_dir}},
                      {"id": "polar", "type": "stk.source.muferro_frame@1", "inputs": {"frames": {"from": "run.frames"}},
                       "params": {"step": 2}},
                      {"id": "file", "type": "stk.source.file@1", "params": {"binding": "run", "path": prefix + frame}}]}


@pytest.mark.parametrize("kind", ["local", "runtime"])
@pytest.mark.parametrize("case_dir", [".", "./", "case16"])
def test_muferro_sources_through_resolvers_without_a_launcher_record(tmp_path, kind, case_dir):
    pytest.importorskip("numpy")
    from mupro_fake import write_case, write_outputs
    from suan.graph.catalog import build_registry
    from suan.graph.evaluator import evaluate
    root = tmp_path / "work"
    folder = root if case_dir in (".", "./") else root / case_dir
    write_case(folder)
    write_outputs(folder)
    assert not (root / "stk-mupro.json").exists()  # a run STK did not launch
    if kind == "local":
        resolver = LocalDirResolver({"run": root})
    else:
        resolver = RuntimeResolver(DirectoryRuntime(root), tmp_path / "downloads", {"run": "task1"})
    result = evaluate(muferro_graph(case_dir), registry=build_registry(entry_points=False), resolver=resolver)
    frames, energy = result.outputs["frames"], result.outputs["energy"]
    assert frames.n_rows > 0 and energy.n_rows == 3 and "Total Energy" in energy.fields
    for name in ("polar", "file"):  # the field and dataset keep the frame's name, not the download's sha256
        image = result.outputs[name]
        assert image.id == "Polar" and list(image.fields) == ["Polar"] and image.time.step == 2
    assert result.parameters["polar.step"] == {"value": 2, "choices": [0, 2]}


def test_missing_files_raise_one_error_everywhere(tree, tmp_path):
    from suan.connectors.api import ConnectorError
    from suan.connectors.files import LocalFiles, MissingFile, RuntimeFiles
    sources = [LocalFiles(tree), LocalDirSource(tree, binding="run"),
               RuntimeFiles(DirectoryRuntime(tree), "t", tmp_path / "a"),
               RuntimeTaskSource(DirectoryRuntime(tree), "task1", tmp_path / "b")]
    for source in sources:
        for call in (source.open, source.sha256):
            with pytest.raises(MissingFile) as info:
                call("nope.dat")
            assert isinstance(info.value, FileNotFoundError) and isinstance(info.value, ConnectorError)
            assert info.value.code == "missing_file"


def test_symlinked_case_directory_and_link_loops(tmp_path):
    root = tmp_path / "run"
    (root / "real").mkdir(parents=True)
    (root / "real" / "Polar.00000000.dat").write_bytes(b"p")
    (root / "real" / "energy_out.dat").write_bytes(b"e")
    symlink(root / "current", "real")
    symlink(root / "loop", "loop")
    source = LocalDirSource(root)
    assert [f.path for f in source.list("current")] == ["current/Polar.00000000.dat", "current/energy_out.dat"]
    assert [f.path for f in source.list("current/")] == [f.path for f in source.list("current")]
    assert [f.path for f in source.list("current/Polar.")] == ["current/Polar.00000000.dat"]
    assert [f.path for f in source.list("")] == ["real/Polar.00000000.dat", "real/energy_out.dat"]  # loop skipped
    with pytest.raises(FileNotFoundError):
        source.open("loop")
