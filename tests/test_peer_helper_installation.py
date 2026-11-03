"""Explicit installation integrity/compatibility, independent of native startup."""
import copy
import hashlib
import json
import os
from pathlib import Path

import pytest

from suan.peer import helper_installation as hi


def _write(root, value):
    (root / hi.MANIFEST_NAME).write_text(json.dumps(value), encoding="utf-8")


@pytest.fixture
def installation(tmp_path):
    root = tmp_path / "installed"
    root.mkdir()
    system, architecture = hi._host()
    executable = "bin/stk-peer-transport" + (".exe" if system == "windows" else "")
    files = []
    for path, role, data in ((executable, "executable", b"test-only helper bytes"),
                             ("licenses/helper.txt", "notice", b"MIT test notice"),
                             ("sources/helper.tar", "source", b"test source archive")):
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        files.append({"path": path, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                      "role": role, "component": "helper"})
    (root / executable).chmod(0o755)
    value = {"format": hi.INSTALLATION_FORMAT, "abi": hi.HELPER_ABI,
             "protocol": "stk.peer/1", "platform": system, "architecture": architecture,
             "executable": executable, "files": files,
             "components": [{"id": "helper", "version": "test", "license": "MIT",
                             "notices": ["licenses/helper.txt"], "sources": ["sources/helper.tar"]}],
             "host_requirements": ["Test fixture only"]}
    _write(root, value)
    return root, value


def test_explicit_prefix_integrity_is_passive_and_relocatable(installation, tmp_path, monkeypatch):
    root, value = installation
    expected = hashlib.sha256((root / hi.MANIFEST_NAME).read_bytes()).hexdigest()
    monkeypatch.setenv("PATH", "")
    monkeypatch.setenv("STK_PEER_HELPER", "/ignored/source/path")
    elsewhere = tmp_path / "relocated"
    root.rename(elsewhere)
    monkeypatch.chdir(tmp_path)
    result = hi.load_helper_installation(elsewhere, expected_manifest_sha256=expected)
    assert result.executable == elsewhere / value["executable"]
    assert result.manifest_sha256 == expected
    assert result.abi == hi.HELPER_ABI
    with pytest.raises(AttributeError):
        result.executable = Path("other")


@pytest.mark.parametrize("change", [
    lambda v: v.update(extra=True),
    lambda v: v.update(abi="unknown/2"),
    lambda v: v.update(platform="other"),
    lambda v: v.update(architecture="other"),
    lambda v: v.update(executable="other/helper"),
    lambda v: v["files"][0].update(bytes=True),
    lambda v: v["files"][0].update(sha256="f" * 64),
    lambda v: v["files"][0].update(path="../outside"),
    lambda v: v["files"][0].update(path="C:/outside"),
    lambda v: v["files"][0].update(path="bin\\outside"),
    lambda v: v["files"][0].update(path="bin/CON.exe"),
    lambda v: v["files"].append(copy.deepcopy(v["files"][0])),
    lambda v: v["files"].append(dict(v["files"][0], path="BIN/stk-peer-transport")),
    lambda v: v["files"][1].update(role="executable"),
    lambda v: v["files"][0].update(component="absent"),
    lambda v: v["components"][0].update(notices=[]),
    lambda v: v["components"][0].update(sources=[]),
    lambda v: v["components"][0].update(sources=["licenses/helper.txt"]),
    lambda v: v["components"].append(copy.deepcopy(v["components"][0])),
    lambda v: v.update(host_requirements=["bad\nrequirement"]),
])
def test_closed_manifest_rejects_incompatible_or_ambiguous_content(installation, change):
    root, value = installation
    change(value)
    _write(root, value)
    with pytest.raises(hi.HelperInstallationError):
        hi.load_helper_installation(root)


@pytest.mark.parametrize("kind", ["unlisted_file", "unlisted_directory", "missing", "changed", "directory"])
def test_exact_installed_file_set_is_required(installation, kind):
    root, value = installation
    target = root / "sources/helper.tar"
    if kind == "unlisted_file":
        (root / "extra").write_text("extra")
    elif kind == "unlisted_directory":
        (root / "extra").mkdir()
    elif kind == "missing":
        target.unlink()
    elif kind == "changed":
        target.write_bytes(b"different")
    else:
        target.unlink()
        target.mkdir()
    with pytest.raises(hi.HelperInstallationError):
        hi.load_helper_installation(root)


def test_independent_manifest_hash_is_required_when_selected(installation):
    root, _ = installation
    with pytest.raises(hi.HelperInstallationError) as caught:
        hi.load_helper_installation(root, expected_manifest_sha256="0" * 64)
    assert caught.value.code == "manifest_mismatch"


def test_relative_prefix_and_missing_installation_have_safe_errors(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for prefix in ("relative", tmp_path / "private-missing-installation"):
        with pytest.raises(hi.HelperInstallationError) as caught:
            hi.load_helper_installation(prefix)
        assert str(prefix) not in caught.value.message


@pytest.mark.parametrize("kind", ["manifest", "file", "directory", "prefix"])
def test_symlink_installations_are_rejected(installation, tmp_path, kind):
    root, _ = installation
    target = {"manifest": root / hi.MANIFEST_NAME, "file": root / "sources/helper.tar",
              "directory": root / "sources", "prefix": root}[kind]
    moved = tmp_path / (kind + "-original")
    target.rename(moved)
    try:
        target.symlink_to(moved, target_is_directory=moved.is_dir())
    except OSError:
        pytest.skip("Platform does not permit test symlinks")
    with pytest.raises(hi.HelperInstallationError):
        hi.load_helper_installation(root)


def test_duplicate_json_keys_rejected(installation):
    root, _ = installation
    (root / hi.MANIFEST_NAME).write_text('{"format":1,"format":2}')
    with pytest.raises(hi.HelperInstallationError):
        hi.load_helper_installation(root)


def test_changed_previously_hashed_file_is_rechecked(installation, monkeypatch):
    root, _ = installation
    original = hi._digest
    def mutate(path, maximum):
        result = original(path, maximum)
        if path.name == "helper.tar":
            (root / "licenses/helper.txt").write_text("replacement")
        return result
    monkeypatch.setattr(hi, "_digest", mutate)
    with pytest.raises(hi.HelperInstallationError) as caught:
        hi.load_helper_installation(root)
    assert caught.value.code == "changed_installation"


@pytest.mark.skipif(os.name == "nt", reason="POSIX executable permissions")
def test_executable_permission_required(installation):
    root, value = installation
    (root / value["executable"]).chmod(0o644)
    with pytest.raises(hi.HelperInstallationError):
        hi.load_helper_installation(root)


@pytest.mark.parametrize("change", ["stable_cross_api", "fd_changed", "path_changed"])
def test_time_metadata_is_compared_within_its_stat_api(installation, monkeypatch, change):
    # Windows fd/path stat APIs can expose different ctime meanings or precision.
    # Simulate that distinction without claiming execution on Windows.
    from types import SimpleNamespace
    root, _ = installation
    original_fd, original_path = hi.os.fstat, hi._ordinary
    fd_calls, path_calls = 0, 0
    def replacement(info, ctime):
        fields = {k: getattr(info, k) for k in ("st_dev", "st_ino", "st_mode", "st_size", "st_mtime_ns")}
        return SimpleNamespace(**fields, st_ctime_ns=ctime)
    def fd_stat(fd):
        nonlocal fd_calls
        fd_calls += 1
        info = original_fd(fd)
        delta = 100 if change == "stable_cross_api" else int(change == "fd_changed" and fd_calls > 1)
        return replacement(info, info.st_ctime_ns + delta)
    def path_stat(path, directory=False):
        nonlocal path_calls
        info = original_path(path, directory=directory)
        if path == root / hi.MANIFEST_NAME:
            path_calls += 1
            if change == "path_changed" and path_calls > 1:
                return replacement(info, info.st_ctime_ns + 1)
        return info
    monkeypatch.setattr(hi.os, "fstat", fd_stat)
    monkeypatch.setattr(hi, "_ordinary", path_stat)
    if change == "stable_cross_api":
        assert hi.load_helper_installation(root).abi == hi.HELPER_ABI
    else:
        with pytest.raises(hi.HelperInstallationError) as caught:
            hi.load_helper_installation(root)
        assert caught.value.code == "changed_installation"
