"""File sharing freezes explicit snapshot bytes without disclosing local paths."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from uuid import UUID

import pytest

from suan.peer.manifests import (FORMAT, MAX_FILE_BYTES, FileManifestError,
                                 encode_manifest, manifest_sha256, portable_name,
                                 prepare_manifest, validate_manifest)
from suan.project import ProjectError, ProjectStore


def uid(value):
    return str(UUID(int=value))


def manifest(*names):
    return {"format": FORMAT, "project_id": uid(1), "source_revision": 7,
            "snapshot_id": uid(2), "snapshot_sha256": "a" * 64,
            "files": [{"file_id": uid(10 + i), "name": name, "bytes": 0,
                       "sha256": hashlib.sha256(b"").hexdigest(),
                       "media_type": "application/octet-stream"} for i, name in enumerate(names or ("数据.csv",))]}


def test_content_digest_is_detached_and_independent_of_json_key_order():
    original = manifest("数据/first.csv", "empty.txt")
    result = validate_manifest(original)
    expected = json.dumps(original, ensure_ascii=False, allow_nan=False,
                          sort_keys=True, separators=(",", ":")).encode("utf-8")
    assert encode_manifest(original) == expected
    assert manifest_sha256(original) == hashlib.sha256(expected).hexdigest()
    reversed_keys = dict(reversed(list(original.items())))
    assert manifest_sha256(reversed_keys) == manifest_sha256(original)
    original["files"][0]["name"] = "changed.csv"
    assert result["files"][0]["name"] == "数据/first.csv"
    assert manifest_sha256(original) != manifest_sha256(result)
    reordered = deepcopy(result)
    reordered["files"].reverse()
    assert manifest_sha256(reordered) != manifest_sha256(result)


@pytest.mark.parametrize("name", ["/absolute", "C:/drive", "//host/share", "../outside", "a/../b",
    "a//b", "a/./b", "a/", "a\\b", "file:stream", "AUX", "con.txt", "CoN .txt",
    "COM1.bin", "LPT².txt", "trailing.", "trailing ", "x?y", "x*y", 'a"b', "a|b",
    "a%2fb", "a%5Cb", "a%00b", "a\x00b", "a\nb", "a\u202eb", "e\u0301.txt",
    ".stk-peer-receipt.json", ".STK-PEER-RECEIPT.JSON/child", "\ud800", "x" * 256,
    "文" * 86, "/".join(["a"] * 17)])
def test_unsafe_or_ambiguous_portable_names_are_rejected_without_echo(name):
    with pytest.raises(FileManifestError) as caught:
        portable_name(name)
    assert name not in str(caught.value)


@pytest.mark.parametrize("name", ["file.txt", "数据/参数.csv", "é.txt", "a b/c+d.csv", ".hidden",
                                    "x%20y.csv", "com10.txt", "dir/a_b-c.01"])
def test_safe_names_are_preserved_without_renaming(name):
    assert portable_name(name) == name


@pytest.mark.parametrize("names", [("a", "a/b"), ("a/b", "a"), ("a", "A"),
    ("A/x", "a/y"), ("straße/x", "STRASSE/y"), ("dup", "dup")])
def test_cross_platform_collisions_and_file_parent_conflicts_fail(names):
    with pytest.raises(FileManifestError):
        validate_manifest(manifest(*names))


def test_exact_shared_directory_is_allowed_and_limits_are_not_block_limits():
    value = manifest("same/a", "same/b", "other/c", "other/d")
    for file in value["files"]:
        file["bytes"] = MAX_FILE_BYTES
    assert sum(f["bytes"] for f in validate_manifest(value)["files"]) == 4 * MAX_FILE_BYTES
    oversized = deepcopy(value)
    oversized["files"][0]["bytes"] += 1
    with pytest.raises(FileManifestError, match="size limit"):
        validate_manifest(oversized)
    oversized = deepcopy(value)
    oversized["files"].append({**value["files"][0], "file_id": uid(50), "name": "fifth"})
    with pytest.raises(FileManifestError, match="transfer size"):
        validate_manifest(oversized)


@pytest.mark.parametrize("change", [
    lambda v: v.update(session_id=uid(3)), lambda v: v.update(recipient="b" * 64),
    lambda v: v.update(source_revision=True), lambda v: v.update(source_revision=-1),
    lambda v: v.update(source_revision=2 ** 63), lambda v: v.update(snapshot_sha256="A" * 64),
    lambda v: v.update(files=[]), lambda v: v["files"][0].update(bytes=True),
    lambda v: v["files"][0].update(bytes=-1), lambda v: v["files"][0].update(bytes=1.0),
    lambda v: v["files"][0].update(path="/private/source"),
    lambda v: v["files"][0].update(media_type="text/plain; charset=utf-8"),
    lambda v: v["files"][0].update(sha256="invalid"),
    lambda v: v["files"].append(deepcopy(v["files"][0])),
])
def test_closed_content_schema_rejects_wrong_types_and_authority_metadata(change):
    value = manifest()
    change(value)
    with pytest.raises(FileManifestError):
        validate_manifest(value)


@pytest.fixture
def frozen(tmp_path):
    store = ProjectStore.create(tmp_path / "project", "Explicit sharing")
    a, b = store.directory / "数据.csv", tmp_path / "empty.txt"
    a.write_bytes(b"x,y\n1,2\n")
    b.write_bytes(b"")
    ids = store.files.index([str(a), str(b)], expected_revision=0)["record_ids"]
    snapshot = store.snapshots.capture(ids, expected_revision=1)["snapshot"]
    return store, ids, snapshot, a, b


def test_prepare_reads_frozen_selected_objects_and_never_discloses_source_paths(frozen):
    store, ids, snapshot, a, b = frozen
    a.write_bytes(b"changed working copy")
    b.unlink()
    before = store.info()
    result = prepare_manifest(store, snapshot["id"], list(reversed(ids)),
                              names={ids[0]: "results/数据.csv"}, media_types={ids[0]: "text/csv"})
    assert result["source_revision"] == 1
    assert result["snapshot_sha256"] == snapshot["sha256"]
    assert [f["file_id"] for f in result["files"]] == list(reversed(ids))
    assert result["files"][0]["bytes"] == 0
    assert result["files"][1]["sha256"] == hashlib.sha256(b"x,y\n1,2\n").hexdigest()
    encoded = encode_manifest(result)
    assert str(a).encode() not in encoded and str(b).encode() not in encoded
    assert set(result) == {"format", "project_id", "source_revision", "snapshot_id", "snapshot_sha256", "files"}
    assert store.info() == before
    assert a.read_bytes() == b"changed working copy" and not b.exists()


def test_prepare_rejects_corrupt_selected_bytes_without_repair_or_writes(frozen):
    store, ids, snapshot, *_ = frozen
    path = Path(store.snapshots.resolve(snapshot["id"], ids[0])["path"])
    path.write_bytes(b"bad")
    # An unselected broken object does not cause an implicit full-project read.
    assert prepare_manifest(store, snapshot["id"], [ids[1]])["files"][0]["bytes"] == 0
    with pytest.raises(ProjectError):
        prepare_manifest(store, snapshot["id"], [ids[0]])
    assert path.read_bytes() == b"bad"
    assert store.info()["revision"] == 2


def test_unknown_file_identity_is_rejected_against_the_actual_snapshot(frozen):
    store, _, snapshot, *_ = frozen
    before = store.info()
    with pytest.raises(FileManifestError, match="not in the frozen snapshot"):
        prepare_manifest(store, snapshot["id"], [uid(99)])
    assert store.info() == before


@pytest.mark.parametrize("selection,names", [([], None),
    (["not-a-uuid"], None), (None, None), ([], {}), ([uid(10)], {uid(99): "other"})])
def test_invalid_explicit_selection_does_not_reach_project_io(selection, names):
    class Unread:
        @property
        def snapshots(self):
            raise AssertionError("Invalid local selection reached project I/O")
    with pytest.raises(FileManifestError):
        prepare_manifest(Unread(), uid(2), selection, names=names)
