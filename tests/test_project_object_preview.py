"""Attachment reads stay local, bounded, source-bound and independent of project edits."""
import base64
import hashlib

import pytest

from suan.project import ProjectStore, ProjectError, RevisionConflict
from suan.project import object_preview as module
from test_desktop_bridge import bridge_env, inproc  # noqa: F401


@pytest.fixture(params=["\n", "\r\n"], ids=["lf", "crlf"])
def attachment(tmp_path, request):
    store = ProjectStore.create(tmp_path / "project", "Synthetic attachments")
    path = store.directory / "note.md"
    path.write_bytes(("# 合成记录" + request.param + "<script>never executed</script>" + request.param).encode("utf-8"))
    identity = store.files.index([str(path)], expected_revision=0)["record_ids"][0]
    ref = {"version": 1, "project_id": store.info()["id"], "kind": "file", "id": identity}
    return store, path, ref


def test_text_is_literal_and_read_does_not_edit_or_refresh_index(attachment):
    store, path, ref = attachment
    before, history = store.snapshot(), store.history()
    result = store.table.objects_preview(ref, expected_revision=1)
    assert result["kind"] == "text" and result["data"] == path.read_bytes().decode("utf-8")
    assert result["content_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert result["size"] == len(path.read_bytes()) and not result["truncated"]
    assert store.snapshot() == before and store.history() == history
    path.write_text("new current bytes", encoding="utf-8")
    assert store.table.objects_preview(ref, expected_revision=1)["data"] == "new current bytes"
    assert store.snapshot() == before
    with pytest.raises(RevisionConflict):
        store.table.objects_preview(ref, expected_revision=0)


def test_frozen_preview_verifies_bytes_after_source_change_and_relocation(attachment, tmp_path):
    store, path, ref = attachment
    original = path.read_bytes()
    snap = store.snapshots.capture([ref["id"]], expected_revision=1)["snapshot"]
    frozen = store.table.objects_list_candidates("snapshot_file", expected_revision=2)["items"][0]["reference"]
    path.write_text("changed", encoding="utf-8")
    root = tmp_path / "moved"
    store.directory.rename(root)
    store = ProjectStore(root)
    assert store.table.objects_preview(frozen, expected_revision=2)["data"] == original.decode()
    resource = store.snapshots._object(snap["manifest"]["files"][0]["sha256"])
    resource.write_bytes(b"x" * len(original))
    # Metadata checks alone cannot detect same-size corruption.
    assert store.table.objects_resolve(frozen, expected_revision=2)["state"] == "available"
    with pytest.raises(ProjectError, match="checksum"):
        store.table.objects_preview(frozen, expected_revision=2)


def test_utf8_truncation_preserves_character_boundary_and_full_checksum(attachment):
    store, path, ref = attachment
    data = ("样" * 30000).encode()
    path.write_bytes(data)
    result = store.table.objects_preview(ref, expected_revision=1)
    assert result["truncated"] and len(result["data"].encode()) <= module.TEXT_BYTES
    assert data.startswith(result["data"].encode()) and "�" not in result["data"]
    assert result["content_sha256"] == hashlib.sha256(data).hexdigest()


@pytest.mark.parametrize("data,reason", [(b"\xff", "UTF-8"), (b"a\0b", "binary"),
                                         (b"x" * (module.MAX_BYTES + 1), "1 MiB")],
                         ids=["invalid-utf8", "binary", "oversized"])
def test_invalid_or_oversized_text_is_not_silently_shown(attachment, data, reason):
    store, path, ref = attachment
    path.write_bytes(data)
    with pytest.raises(ProjectError, match=reason):
        store.table.objects_preview(ref, expected_revision=1)


def test_png_response_keeps_exact_bytes_without_decoder_dependency(attachment):
    store, path, ref = attachment
    png = store.directory / "synthetic.png"
    # Public 1x1 PNG fixture, never a credential.
    data = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/5S8AAAAASUVORK5CYII=")
    png.write_bytes(data)
    identity = store.files.index([str(png)], expected_revision=1)["record_ids"][0]
    result = store.table.objects_preview({**ref, "id": identity}, expected_revision=2)
    assert result["kind"] == "png" and base64.b64decode(result["data"]) == data
    assert result["content_sha256"] == hashlib.sha256(data).hexdigest()
    png.write_bytes(data[:16] + (9999).to_bytes(4, "big") + data[20:])
    with pytest.raises(ProjectError, match="megapixels"):
        store.table.objects_preview({**ref, "id": identity}, expected_revision=2)


def test_nonregular_file_cannot_be_previewed(attachment):
    store, path, ref = attachment
    path.unlink()
    path.mkdir()
    with pytest.raises(ProjectError, match="regular"):
        store.table.objects_preview(ref, expected_revision=1)


def test_file_change_during_read_is_rejected(attachment, monkeypatch):
    store, path, ref = attachment
    fstat = module.os.fstat
    calls = 0
    def changing(fd):
        nonlocal calls
        calls += 1
        if calls == 2:
            path.write_bytes(b"changed during preview")
        return fstat(fd)
    monkeypatch.setattr(module.os, "fstat", changing)
    with pytest.raises(ProjectError, match="changed"):
        store.table.objects_preview(ref, expected_revision=1)


def test_bridge_discovers_and_validates_explicit_preview(attachment, inproc):
    store, path, ref = attachment
    bridge = inproc()
    info = bridge.call("project.open", {"directory": str(store.directory)})["project"]
    result = bridge.call("project.table.objects.preview", {"handle": info["handle"], "expected_revision": 1, "reference": ref})
    assert result["data"] == path.read_bytes().decode("utf-8")
    assert bridge.call("project.snapshot", {"handle": info["handle"]})["snapshot"] == store.snapshot()
    from suan.scripting import API
    api = API(bridge.call)
    opened = api.projects.open(store.directory)
    assert opened.table.objects_preview(ref, expected_revision=1) == result


def test_wrong_project_missing_object_and_unsupported_format_fail(attachment, tmp_path):
    store, path, ref = attachment
    other = ProjectStore.create(tmp_path / "other", "Other synthetic project")
    with pytest.raises(ProjectError):
        other.table.objects_preview(ref, expected_revision=0)
    with pytest.raises(ProjectError):
        store.table.objects_preview({**ref, "id": "11111111-1111-4111-8111-111111111111"}, expected_revision=1)
    unsupported = store.directory / "unsupported.pdf"
    unsupported.write_bytes(b"public synthetic unsupported format")
    identity = store.files.index([str(unsupported)], expected_revision=1)["record_ids"][0]
    with pytest.raises(ProjectError, match="PNG and UTF-8"):
        store.table.objects_preview({**ref, "id": identity}, expected_revision=2)


def test_frozen_object_parent_link_is_not_followed(attachment, tmp_path):
    store, path, ref = attachment
    snap = store.snapshots.capture([ref["id"]], expected_revision=1)["snapshot"]
    frozen = store.table.objects_list_candidates("snapshot_file", expected_revision=2)["items"][0]["reference"]
    resource = store.snapshots._object(snap["manifest"]["files"][0]["sha256"])
    original_parent = resource.parent
    moved = tmp_path / "moved-objects"
    original_parent.rename(moved)
    try:
        original_parent.symlink_to(moved, target_is_directory=True)
    except OSError:
        pytest.skip("Creating directory symlinks requires platform permission")
    with pytest.raises(ProjectError, match="links|reparse"):
        store.table.objects_preview(frozen, expected_revision=2)
