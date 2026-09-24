"""File sources: LocalFiles (confined to the binding root, sha256 cache) and RuntimeFiles (content-addressed cache)."""
import hashlib
import os
from pathlib import Path

import pytest

from suan.connectors.api import ConnectorError, FileInfo, FileSource
from suan.connectors.files import LocalFiles, RuntimeFiles, check_path, materialize


@pytest.fixture
def tree(tmp_path):
    root = tmp_path / "run"
    (root / "case16").mkdir(parents=True)
    (root / "case16" / "Polar.00000000.dat").write_text("2 1 1\n")
    (root / "case16" / "energy_out.dat").write_text("step\n")
    (root / "stk-mupro.json").write_text("{}")
    (tmp_path / "secret.txt").write_text("outside")
    return root


def test_check_path():
    assert check_path("a/b.dat") == "a/b.dat" and check_path("./a") == "a" and check_path(".") == ""
    for bad in ("/etc/passwd", "../x", "a/../../x", "C:/x", "a\\b", "", None, "a\x00b"):
        with pytest.raises(ConnectorError) as error:
            check_path(bad)
        assert error.value.code == "invalid_path"


def test_local_files(tree, tmp_path):
    source = LocalFiles(tree)
    assert isinstance(source, FileSource)
    assert [f.path for f in source.list()] == ["case16/Polar.00000000.dat", "case16/energy_out.dat", "stk-mupro.json"]
    assert [f.path for f in source.list("case16/Polar.")] == ["case16/Polar.00000000.dat"]
    assert source.list("missing/") == [] and isinstance(source.list()[0], FileInfo)
    info = source.stat("stk-mupro.json")
    assert info.size == 2 and info.mtime > 0
    with source.open("case16/energy_out.dat") as stream:
        assert stream.read() == b"step\n"
    assert source.local_path("stk-mupro.json") == (tree / "stk-mupro.json").resolve()
    assert source.local_path(".") == tree.resolve() and source.local_path("nope") is None
    digest = hashlib.sha256(b"{}").hexdigest()
    assert source.known_sha256("stk-mupro.json") in (None, digest)
    assert source.sha256("stk-mupro.json") == digest and source.known_sha256("stk-mupro.json") == digest
    (tree / "stk-mupro.json").write_text('{"a": 1}')
    os.utime(tree / "stk-mupro.json", ns=(1, 1))  # size and mtime changed -> recomputed
    assert source.sha256("stk-mupro.json") == hashlib.sha256(b'{"a": 1}').hexdigest()
    with pytest.raises(ConnectorError) as error:
        source.open("missing.dat")
    assert error.value.code == "missing_file"
    with pytest.raises(ConnectorError):
        source.open("../secret.txt")
    # A symbolic link that leaves the binding is neither listed nor readable.
    (tree / "link.txt").symlink_to(tmp_path / "secret.txt")
    assert "link.txt" not in [f.path for f in source.list()]
    with pytest.raises(ConnectorError) as error:
        source.open("link.txt")
    assert error.value.code == "invalid_path"
    with pytest.raises(ConnectorError):
        LocalFiles(tmp_path / "missing")
    assert materialize(source, "case16/energy_out.dat") == (tree / "case16" / "energy_out.dat").resolve()


class FakeClient:
    def __init__(self, files):
        self.files = files
        self.downloads = 0

    def artifacts(self, task_id):
        return [{"path": path, "size": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                 "media_type": "text/plain"} for path, data in self.files.items()]

    def download(self, task_id, path, destination):
        self.downloads += 1
        destination.write_bytes(self.files[path])
        return destination


def test_runtime_files(tmp_path):
    client = FakeClient({"Polar.00000000.dat": b"2 1 1\n", "sub/energy_out.dat": b"step\n"})
    source = RuntimeFiles(client, "a" * 32, tmp_path / "cache")
    assert isinstance(source, FileSource)
    assert [(f.path, f.size, f.mtime) for f in source.list()] == [("Polar.00000000.dat", 6, None),
                                                                    ("sub/energy_out.dat", 5, None)]
    assert source.list("sub/") == [FileInfo("sub/energy_out.dat", 5, None)]
    assert source.sha256("Polar.00000000.dat") == hashlib.sha256(b"2 1 1\n").hexdigest()
    assert source.local_path("Polar.00000000.dat") is None and client.downloads == 0
    with source.open("Polar.00000000.dat") as stream:
        assert stream.read() == b"2 1 1\n"
    path = materialize(source, "Polar.00000000.dat")
    assert path.parent.parent.name == "objects" and path.name.endswith(".dat") and client.downloads == 1
    with source.open("Polar.00000000.dat") as stream:  # cached by content
        stream.read()
    assert client.downloads == 1
    with pytest.raises(ConnectorError) as error:
        source.sha256("missing")
    assert error.value.code == "missing_file"
    client.files["new.dat"] = b"x"
    assert not source.exists("new.dat")
    source.refresh()
    assert source.exists("new.dat") and source.stat("new.dat").size == 1


class StreamOnly:
    """A source without local paths or fetch (materialize copies it once)."""

    def __init__(self, data):
        self.data = data

    def local_path(self, path):
        return None

    def sha256(self, path):
        return hashlib.sha256(self.data).hexdigest()

    def open(self, path):
        import io
        return io.BytesIO(self.data)


def test_materialize_copies_stream_sources(tmp_path):
    path = materialize(StreamOnly(b"abc"), "x/field.npy", cache_dir=tmp_path)
    assert path.read_bytes() == b"abc" and path.suffix == ".npy" and tmp_path in path.parents
    assert materialize(StreamOnly(b"abc"), "field.npy", cache_dir=tmp_path) == path


def test_materialize_uses_a_private_directory_and_rehashes_cached_copies(tmp_path):
    import stat
    import tempfile
    path = materialize(StreamOnly(b"abc"), "field.npy")  # no cache_dir: a private per-process directory
    private = path.parents[2]
    assert private.name.startswith("stk-files-") and private.parent == Path(tempfile.gettempdir())
    assert stat.S_IMODE(private.stat().st_mode) == 0o700 and path.read_bytes() == b"abc"
    assert materialize(StreamOnly(b"abc"), "other.npy").parents[2] == private
    # A cached copy that no longer matches its sha256 is copied again, never trusted.
    cached = materialize(StreamOnly(b"abc"), "x/field.npy", cache_dir=tmp_path)
    cached.write_bytes(b"evil")
    again = materialize(StreamOnly(b"abc"), "x/field.npy", cache_dir=tmp_path)
    assert again == cached and again.read_bytes() == b"abc"
    assert not [p for p in cached.parent.iterdir() if p.name.endswith(".part")]

    class Changing(StreamOnly):  # the bytes read differ from the advertised sha256
        def sha256(self, path):
            return hashlib.sha256(b"something else").hexdigest()
    with pytest.raises(ConnectorError) as error:
        materialize(Changing(b"abc"), "y.npy", cache_dir=tmp_path)
    assert error.value.code == "invalid_data"
    assert not [p for p in (tmp_path / "objects").rglob("*.part")]


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFOs are POSIX")
def test_fifos_are_not_regular_files_and_never_block(tree):
    import threading
    os.mkfifo(tree / "case16" / "Stream.00000001.dat")
    source = LocalFiles(tree)
    outcome = {}

    def attempt():
        for name, call in (("open", lambda: source.open("case16/Stream.00000001.dat")),
                           ("sha256", lambda: source.sha256("case16/Stream.00000001.dat"))):
            try:
                call()
                outcome[name] = "returned"
            except ConnectorError as exc:
                outcome[name] = exc.code
    worker = threading.Thread(target=attempt, daemon=True)
    worker.start()
    worker.join(10)
    assert not worker.is_alive(), "reading a FIFO blocked"
    assert outcome == {"open": "missing_file", "sha256": "missing_file"}
    assert source.local_path("case16/Stream.00000001.dat") is None
    assert "case16/Stream.00000001.dat" not in [f.path for f in source.list()]
    with source.open("case16/energy_out.dat") as stream:  # regular files read normally (blocking mode)
        assert stream.read() == b"step\n"


def test_runtime_downloads_check_between_chunks(tmp_path):
    from suan.runtime.client import RuntimeClient
    data = b"x" * 10

    class Chunked(RuntimeClient):
        def __init__(self):
            self.requests = 0

        def artifacts(self, task_id):
            return [{"path": "f.dat", "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}]

        def request(self, method, route, binary=False, **kw):
            self.requests += 1
            return data[self.requests - 1:self.requests]  # one byte per chunk

    class Stop(Exception):
        pass
    calls = []

    def check():
        calls.append(1)
        if len(calls) > 4:
            raise Stop()
    client = Chunked()
    source = RuntimeFiles(client, "t", tmp_path / "cache").with_check(check)
    with pytest.raises(Stop):
        source.open("f.dat")
    assert client.requests == 3  # stopped between chunks (1 check before the download, 1 per chunk)
    assert list((tmp_path / "cache").rglob("*.part"))  # the partial file is kept for a resume
    calls.clear()
    plain = RuntimeFiles(client, "t", tmp_path / "cache")  # no check: resumes and finishes
    with plain.open("f.dat") as stream:
        assert stream.read() == data
    # Clients without a check keyword (older clients, test fakes) still download; check runs around them.
    fake = FakeClient({"g.dat": b"abc"})
    seen = []
    with RuntimeFiles(fake, "t", tmp_path / "c2").with_check(lambda: seen.append(1)).open("g.dat") as stream:
        assert stream.read() == b"abc"
    assert fake.downloads == 1 and len(seen) == 2


def test_vtk_connector_never_downloads_remote_hdf5_to_probe_it(tmp_path):
    pytest.importorskip("numpy")
    pytest.importorskip("h5py")
    from suan.connectors.builtin.vtk import VTKConnector
    client = FakeClient({"run.h5": b"\x89HDF\r\n\x1a\n" + b"0" * 1000, "notes.txt": b"x"})
    source = RuntimeFiles(client, "t", tmp_path / "cache")
    assert VTKConnector()._files(source) == [] and client.downloads == 0


def test_listing_prefixes_links_and_loops(tmp_path):
    root = tmp_path / "run"
    (root / "case" / "deep").mkdir(parents=True)
    (root / "case" / "Polar.00000001.dat").write_text("p")
    (root / "case" / "deep" / "x.dat").write_text("x")
    (root / "case.txt").write_text("sibling")
    (root / "real").mkdir()
    (root / "real" / "a.dat").write_text("a")
    (root / "current").symlink_to("real")
    (root / "loop").symlink_to("loop")
    source = LocalFiles(root)
    assert [f.path for f in source.list("case")] == ["case/Polar.00000001.dat", "case/deep/x.dat"]
    assert [f.path for f in source.list("case/")] == ["case/Polar.00000001.dat", "case/deep/x.dat"]
    assert [f.path for f in source.list("case/P")] == ["case/Polar.00000001.dat"]
    assert source.list("case.txt") == [] and source.list("./") == source.list("")
    assert [f.path for f in source.list("current")] == ["current/a.dat"]  # the path as requested
    assert "loop" not in [f.path for f in source.list()]
    for bad in ("../x", "/etc", "a\\b"):
        with pytest.raises(ConnectorError) as error:
            source.list(bad)
        assert error.value.code == "invalid_path"
    with pytest.raises(FileNotFoundError):
        source.open("loop")
    client = FakeClient({"case/a.dat": b"1", "case/b/c.dat": b"2", "case.txt": b"3", "../evil": b"4"})
    remote = RuntimeFiles(client, "t", tmp_path / "cache")
    assert [f.path for f in remote.list("case")] == ["case/a.dat", "case/b/c.dat"]
    assert [f.path for f in remote.list("case/a")] == ["case/a.dat"] and remote.list("case.txt") == []
    assert [f.path for f in remote.list()] == ["case.txt", "case/a.dat", "case/b/c.dat"]


def test_runtime_download_cap(tmp_path):
    client = FakeClient({"big.dat": b"0" * 64})
    source = RuntimeFiles(client, "t", tmp_path / "cache", max_bytes=32)
    with pytest.raises(ConnectorError) as error:
        source.open("big.dat")
    assert error.value.code == "budget_exceeded" and "1 GiB" in str(error.value) and client.downloads == 0
