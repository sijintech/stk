"""Attachment reads stay local, bounded, source-bound and independent of project edits."""
import base64
import hashlib
from io import BytesIO

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


@pytest.mark.parametrize("suffix,format", [("jpg", "JPEG"), ("webp", "WEBP"), ("gif", "GIF"),
                                         ("bmp", "BMP"), ("tiff", "TIFF"), ("png", "PNG")])
def test_image_formats_and_thumbnails_keep_distinct_source_and_render_identity(attachment, suffix, format):
    from PIL import Image
    store, _, ref = attachment
    path = store.directory / ("public-image." + suffix)
    Image.new("RGB", (600, 400), (200, 30, 40)).save(path, format=format)
    identity = store.files.index([str(path)], expected_revision=1)["record_ids"][0]
    ref = {**ref, "id": identity}
    before = store.snapshot()
    for thumbnail in (False, True):
        read = store.table.objects_thumbnail if thumbnail else store.table.objects_preview
        result = read(ref, expected_revision=2)
        assert result["kind"] == "png" and not result["truncated"]
        assert result["content_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
        assert result["size"] == path.stat().st_size
        pixels = base64.b64decode(result["data"])
        image = Image.open(BytesIO(pixels)); image.load()
        assert image.format == "PNG"
        if thumbnail or format != "PNG":
            render = result["render"]
            assert render["sha256"] == hashlib.sha256(pixels).hexdigest()
            assert render["size"] == len(pixels) <= module.MAX_BYTES
            assert (render["width"], render["height"]) == (600, 400)
            assert image.size == (render["display_width"], render["display_height"])
            assert max(image.size) <= (256 if thumbnail else 2048)
            assert render["thumbnail"] is thumbnail and render["format"] == format
            assert render["frames"] == 1 and render["frame"] == 0
        assert store.snapshot() == before


def test_image_orientation_is_applied_and_metadata_is_not_copied(attachment):
    from PIL import Image
    store, _, ref = attachment
    path = store.directory / "rotated.jpg"
    exif = Image.Exif(); exif[274] = 6; exif[270] = "public synthetic metadata"
    Image.new("RGB", (30, 20), (40, 90, 200)).save(path, exif=exif)
    identity = store.files.index([str(path)], expected_revision=1)["record_ids"][0]
    result = store.table.objects_thumbnail({**ref, "id": identity}, expected_revision=2)
    image = Image.open(BytesIO(base64.b64decode(result["data"]))); image.load()
    assert image.size == (20, 30) and not image.getexif()
    assert b"public synthetic metadata" not in base64.b64decode(result["data"])


def test_multiframe_preview_identifies_first_frame_and_frozen_bytes(attachment):
    from PIL import Image
    store, _, ref = attachment
    path = store.directory / "public-animation.gif"
    Image.new("RGB", (20, 10), "red").save(path, save_all=True,
        append_images=[Image.new("RGB", (20, 10), "blue")], duration=100, loop=0)
    identity = store.files.index([str(path)], expected_revision=1)["record_ids"][0]
    snap = store.snapshots.capture([identity], expected_revision=2)["snapshot"]
    frozen = store.table.objects_list_candidates("snapshot_file", expected_revision=3)["items"][0]["reference"]
    path.write_bytes(b"changed working copy")
    result = store.table.objects_thumbnail(frozen, expected_revision=3)
    assert result["render"]["frames"] == 2 and result["render"]["frame"] == 0
    image = Image.open(BytesIO(base64.b64decode(result["data"])))
    assert image.convert("RGB").getpixel((0, 0)) == (255, 0, 0)
    resource = store.snapshots._object(snap["manifest"]["files"][0]["sha256"])
    data = resource.read_bytes(); resource.write_bytes(data[:-1] + bytes([data[-1] ^ 1]))
    with pytest.raises(ProjectError, match="checksum"):
        store.table.objects_thumbnail(frozen, expected_revision=3)


def test_thumbnail_is_not_a_text_reader_and_rejects_wrong_format_and_large_dimensions(attachment):
    from PIL import Image
    store, path, ref = attachment
    with pytest.raises(ProjectError, match="Thumbnails require"):
        store.table.objects_thumbnail(ref, expected_revision=1)
    image = store.directory / "public.jpg"
    Image.new("RGB", (2, 2)).save(image, format="PNG")
    identity = store.files.index([str(image)], expected_revision=1)["record_ids"][0]
    with pytest.raises(ProjectError, match="valid supported"):
        store.table.objects_preview({**ref, "id": identity}, expected_revision=2)
    Image.new("RGB", (4097, 1)).save(image, format="JPEG")
    with pytest.raises(ProjectError, match="megapixels"):
        store.table.objects_thumbnail({**ref, "id": identity}, expected_revision=2)
    with pytest.raises(RevisionConflict):
        store.table.objects_thumbnail({**ref, "id": identity}, expected_revision=1)


def test_thumbnail_bridge_and_script_validate_render_receipt(attachment, inproc):
    from PIL import Image
    from suan.scripting import API
    store, _, ref = attachment
    path = store.directory / "public.png"
    Image.new("RGBA", (2, 2), (20, 40, 60, 128)).save(path)
    identity = store.files.index([str(path)], expected_revision=1)["record_ids"][0]
    bridge = inproc()
    opened = API(bridge.call).projects.open(store.directory)
    result = opened.table.objects_thumbnail({**ref, "id": identity}, expected_revision=2)
    assert result["render"]["thumbnail"]
    assert Image.open(BytesIO(base64.b64decode(result["data"]))).getpixel((0, 0)) == (20, 40, 60, 128)


def test_missing_decoder_is_explained_without_breaking_original_png(attachment, monkeypatch):
    import builtins
    from PIL import Image
    store, _, ref = attachment
    path = store.directory / "public.png"
    Image.new("RGB", (2, 2)).save(path)
    identity = store.files.index([str(path)], expected_revision=1)["record_ids"][0]
    original = builtins.__import__
    def no_decoder(name, *args, **kwargs):
        if name == "PIL":
            raise ImportError("synthetic missing optional decoder")
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", no_decoder)
    assert base64.b64decode(store.table.objects_preview({**ref, "id": identity}, expected_revision=2)["data"]) == path.read_bytes()
    with pytest.raises(ProjectError, match="visualization extra"):
        store.table.objects_thumbnail({**ref, "id": identity}, expected_revision=2)
