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


@pytest.mark.parametrize("returned,completed,expected", [
    (0, 0, None),
    (0xC0000035, 0xC0000035, FileExistsError),
    (0, 0xC0000035, FileExistsError),
    (0xC0000022, 0xC0000022, FileStorageError),
    (0, 0xC0000022, FileStorageError),
    (0x103, 0, FileStorageError),
    (0, 0x103, FileStorageError),
])
def test_windows_publication_native_abi_preserves_parent_no_replace_and_completion(
        monkeypatch, returned, completed, expected):
    # Validate the documented Windows ABI independently on every test host.
    # This does not execute a Windows syscall or replace the actual OS tests.
    import ctypes
    import struct
    from types import SimpleNamespace
    from suan.peer import file_io

    pointer = ctypes.sizeof(ctypes.c_void_p)
    parent = 0x123456789ABC if pointer == 8 else 0x12345678
    source, identity, closed, calls = 67, (123, 456), [], []
    target = "received-数据-🔬"
    encoded = target.encode("utf-16-le")

    def relative(root, name, **options):
        assert (root, name, options) == (parent, ".incoming", {"directory": True, "delete": True})
        return source

    def rename(handle, status, buffer, size, kind):
        assert handle == source and kind == 10  # FileRenameInformation, not Win32 class 3.
        raw = ctypes.string_at(buffer, size)
        root_offset = pointer
        length_offset = root_offset + pointer
        name_offset = length_offset + 4
        structure_size = ((name_offset + 2 + pointer - 1) // pointer) * pointer
        assert len(raw) >= structure_size + len(encoded)
        assert raw[0] == 0  # BOOLEAN ReplaceIfExists is false, including all union flags.
        assert raw[1:root_offset] == bytes(root_offset - 1)
        assert int.from_bytes(raw[root_offset:length_offset], "little") == parent
        assert struct.unpack_from("<I", raw, length_offset)[0] == len(encoded)
        assert raw[name_offset:name_offset + len(encoded)] == encoded
        assert not any(raw[name_offset + len(encoded):])
        assert not any(ctypes.string_at(status, pointer * 2))
        ctypes.cast(status, ctypes.POINTER(ctypes.c_void_p))[0] = completed or None
        calls.append((handle, kind))
        return ctypes.c_int32(returned).value

    class Function:
        def __call__(self, *args):
            return rename(*args)

    function = Function()
    def library(name, **options):
        assert name == "ntdll"  # No Win32/path-based mutation or retry fallback.
        return SimpleNamespace(NtSetInformationFile=function)

    monkeypatch.setattr(file_io, "_windows_relative", relative)
    monkeypatch.setattr(file_io, "_windows_info", lambda handle: (identity, 0x10))
    monkeypatch.setattr(file_io, "_windows_close", closed.append)
    monkeypatch.setattr(file_io.ctypes, "WinDLL", library, raising=False)
    if expected is None:
        file_io._windows_publish(parent, ".incoming", target, identity)
    else:
        with pytest.raises(expected) as caught:
            file_io._windows_publish(parent, ".incoming", target, identity)
        if expected is FileStorageError:
            assert "0x" in str(caught.value) and target not in str(caught.value)
    assert calls == [(source, 10)] and closed == [source]


@pytest.mark.parametrize("directory,delete,expected", [
    (True, False, 0x100000 | 0x80 | 0x20),
    (True, True, 0x100000 | 0x80 | 0x20 | 0x10000),
    (False, False, 0x100000 | 0x80 | 0x1),
])
def test_windows_relative_handles_request_only_needed_access_and_synchronous_io(
        monkeypatch, directory, delete, expected):
    import ctypes
    from types import SimpleNamespace
    from suan.peer import file_io
    calls = []

    class Function:
        def __call__(self, handle, access, attributes, status, allocation, mode,
                     sharing, disposition, options, ea, ea_length):
            assert access == expected
            assert sharing == 7 and disposition == 1
            assert options & 0x20 and access & 0x100000  # SYNCHRONOUS_IO_NONALERT + SYNCHRONIZE.
            ctypes.cast(handle, ctypes.POINTER(ctypes.c_void_p))[0] = 67
            calls.append(access)
            return 0

    monkeypatch.setattr(file_io.ctypes, "WinDLL", lambda *a, **k: SimpleNamespace(NtCreateFile=Function()), raising=False)
    assert file_io._windows_relative(89, "stage", directory=directory, delete=delete) == 67
    assert calls == [expected]


def test_windows_drive_handle_avoids_directory_enumeration_access(monkeypatch):
    from pathlib import PureWindowsPath
    from types import SimpleNamespace
    from suan.peer import file_io

    class Function:
        def __call__(self, name, access, sharing, security, disposition, flags, template):
            assert name == "C:\\" and access == 0x100000 | 0x80 | 0x20
            assert sharing == 7 and disposition == 3
            return 67

    monkeypatch.setattr(file_io.ctypes, "WinDLL", lambda *a, **k: SimpleNamespace(CreateFileW=Function()), raising=False)
    assert file_io._windows_drive(PureWindowsPath("C:/")) == 67
