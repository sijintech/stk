"""Anchored file operations and atomic absent-target directory publication."""
import os
import stat

import pytest

from suan.peer.file_io import Directory, FileStorageError


def test_private_staging_publishes_complete_directory_without_overwrite(tmp_path):
    root = tmp_path.resolve()
    with Directory.open(root) as parent:
        with parent.child(".incoming", create=True, exclusive=True) as stage:
            identity = stage.identity
            with stage.child("数据", create=True) as nested:
                with nested.file("result.csv", create=True, write=True) as stream:
                    stream.write(b"x,y\n1,2\n")
                    os.fsync(stream.fileno())
                nested.sync()
            with stage.file("empty", create=True, write=True) as stream:
                os.fsync(stream.fileno())
            stage.sync()
        parent.publish(".incoming", "received", expected_identity=identity)
        with parent.child("received") as published:
            assert published.identity == identity
            with published.child("数据") as nested, nested.file("result.csv") as stream:
                assert stream.read() == b"x,y\n1,2\n"
            with published.file("empty") as stream:
                assert stream.read() == b""
    assert not (root / ".incoming").exists()
    assert (root / "received/数据/result.csv").read_bytes() == b"x,y\n1,2\n"


def test_existing_empty_or_nonempty_target_is_never_replaced(tmp_path):
    with Directory.open(tmp_path.resolve()) as parent:
        for name in ("empty", "nonempty"):
            with parent.child(name, create=True, exclusive=True) as target:
                if name == "nonempty":
                    with target.file("keep", create=True, write=True) as stream:
                        stream.write(b"existing owner bytes")
            with parent.child("stage", create=True, exclusive=True) as stage:
                identity = stage.identity
                with stage.file("new", create=True, write=True) as stream:
                    stream.write(b"new bytes")
            with pytest.raises(FileExistsError):
                parent.publish("stage", name, expected_identity=identity)
            assert (tmp_path / "stage/new").read_bytes() == b"new bytes"
            if name == "nonempty":
                assert (tmp_path / name / "keep").read_bytes() == b"existing owner bytes"
            else:
                assert list((tmp_path / name).iterdir()) == []
            (tmp_path / "stage/new").unlink()
            (tmp_path / "stage").rmdir()


def test_create_file_is_exclusive_and_open_does_not_truncate(tmp_path):
    with Directory.open(tmp_path.resolve()) as directory:
        with directory.file("keep", create=True, write=True) as stream:
            stream.write(b"keep original")
            os.fsync(stream.fileno())
        with pytest.raises(FileExistsError):
            directory.file("keep", create=True, write=True)
        with directory.file("keep", write=True) as stream:
            assert stream.read() == b"keep original"
        if os.name != "nt":
            assert stat.S_IMODE((tmp_path / "keep").stat().st_mode) == 0o600


def test_staged_directory_replacement_or_wrong_identity_blocks_publication(tmp_path):
    with Directory.open(tmp_path.resolve()) as directory:
        with directory.child("stage", create=True, exclusive=True) as stage:
            identity = stage.identity
        with pytest.raises(FileStorageError, match="identity"):
            directory.publish("stage", "received", expected_identity=(identity[0], identity[1] + 1))
        (tmp_path / "stage").rename(tmp_path / "old-stage")
        (tmp_path / "stage").mkdir()
        with pytest.raises(FileStorageError, match="identity"):
            directory.publish("stage", "received", expected_identity=identity)
        assert not (tmp_path / "received").exists()


def test_moved_parent_is_rejected_before_creating_a_file(tmp_path):
    original = tmp_path / "original"
    original.mkdir()
    with Directory.open(original.resolve()) as directory:
        original.rename(tmp_path / "moved")
        original.mkdir()
        with pytest.raises(FileStorageError, match="identity"):
            directory.file("must-not-exist", create=True, write=True)
    assert list(original.iterdir()) == []
    assert list((tmp_path / "moved").iterdir()) == []


@pytest.mark.skipif(os.name == "nt", reason="POSIX link/FIFO boundary; native Windows reparse case below")
def test_linked_parent_final_file_and_fifo_never_escape_or_block(tmp_path):
    root, outside = tmp_path / "root", tmp_path / "outside"
    root.mkdir(); outside.mkdir()
    (outside / "keep").write_bytes(b"untouched")
    (root / "link").symlink_to(outside, target_is_directory=True)
    with pytest.raises(OSError):
        Directory.open(root / "link")
    with Directory.open(root) as directory:
        with pytest.raises(OSError):
            directory.child("link")
        (root / "file").symlink_to(outside / "keep")
        with pytest.raises(OSError):
            directory.file("file", write=True)
        os.mkfifo(root / "pipe")
        with pytest.raises(FileStorageError, match="ordinary"):
            directory.file("pipe")
    assert (outside / "keep").read_bytes() == b"untouched"
    assert list(outside.iterdir()) == [outside / "keep"]


@pytest.mark.skipif(os.name != "nt", reason="Actual Windows junction/reparse handling")
def test_windows_junction_descendant_is_not_followed(tmp_path):
    import subprocess
    root, outside = tmp_path / "root", tmp_path / "outside"
    root.mkdir(); outside.mkdir()
    result = subprocess.run(["cmd", "/c", "mklink", "/J", str(root / "junction"), str(outside)],
                            capture_output=True, check=False, timeout=10)
    assert result.returncode == 0
    try:
        with Directory.open(root) as directory:
            with pytest.raises(FileStorageError):
                directory.child("junction")
        assert list(outside.iterdir()) == []
    finally:
        os.rmdir(root / "junction")


def test_closed_handles_and_component_traversal_are_rejected(tmp_path):
    directory = Directory.open(tmp_path.resolve())
    for name in ("../escape", "a/b", "file:stream", "NUL", ""):
        with pytest.raises((OSError, ValueError)):
            directory.file(name, create=True, write=True)
    directory.close()
    directory.close()
    with pytest.raises(FileStorageError, match="closed"):
        directory.sync()
    assert list(tmp_path.iterdir()) == []
