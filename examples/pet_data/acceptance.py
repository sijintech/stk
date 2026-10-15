"""Meaningful local acceptance for the shipped synthetic fixture, outside core discovery."""
import json
from pathlib import Path
import shutil
import socket
import tempfile
import unittest
from unittest.mock import patch

from suan.project import ProjectStore
from suan.project.store import FORMAT_VERSION

from .offline import create_demo, verify_demo


class OfflinePETDataAcceptance(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="stk-pet-data-acceptance-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.project = self.root / "project"

    def receipt(self):
        return json.loads((self.project / "demo.json").read_text(encoding="utf-8"))

    def test_offline_create_and_reopen_preserve_rows_and_sources(self):
        with patch.object(socket, "socket", side_effect=AssertionError("Offline example attempted network access")):
            result = create_demo(self.project)
            before = ProjectStore(self.project).snapshot()
            self.assertEqual(verify_demo(self.project), result)
            self.assertEqual(ProjectStore(self.project).snapshot(), before)
        self.assertEqual((result["tables"], result["records"], result["references"], result["frozen_files"]),
                         (9, 32, 61, 20))
        self.assertEqual(result["format_version"], FORMAT_VERSION)
        self.assertFalse(result["material_validated"])
        table = self.receipt()["tables"]["observations"]
        records = next(t for t in before["tables"] if t["id"] == table["table_id"])["records"]
        fields = table["fields"]
        self.assertEqual({r["values"][fields["represented_source_kind"]] for r in records},
                         {"literature", "calculation", "measurement", "inference"})
        self.assertTrue(all(r["values"][fields["source_kind"]] == "synthetic"
                            and r["values"][fields["synthetic"]] is True for r in records))

    def test_missing_and_failed_values_are_null_and_reasons_remain(self):
        create_demo(self.project)
        receipt = self.receipt()
        snapshot = ProjectStore(self.project).snapshot()
        for label in ("processing", "observations"):
            identity = receipt["tables"][label]
            table = next(t for t in snapshot["tables"] if t["id"] == identity["table_id"])
            fields = identity["fields"]
            for row in table["records"]:
                if row["values"][fields["value_status"]] in {"missing", "failed"}:
                    self.assertIsNone(row["values"][fields["value"]])
                    if label == "processing":
                        self.assertTrue(row["values"][fields["exclusion_reason"]])
        missing_curve = self.project / "fixture/raw/curve-B-desorbed.csv"
        self.assertIn("3,,missing,1,synthetic,true", missing_curve.read_text(encoding="utf-8"))

    def test_display_name_changes_do_not_retarget_references(self):
        create_demo(self.project)
        store = ProjectStore(self.project)
        identity = self.receipt()["tables"]["samples"]
        store.apply([{"op": "rename_table", "id": identity["table_id"], "name": "Renamed samples"},
                     {"op": "rename_field", "id": identity["fields"]["id"], "name": "Renamed identity"}],
                    expected_revision=store.info()["revision"])
        self.assertEqual(verify_demo(self.project)["references"], 61)

    def test_move_preserves_project_identity_references_and_frozen_bytes(self):
        before = create_demo(self.project)
        moved = self.root / "moved project"
        shutil.move(self.project, moved)
        self.assertEqual(verify_demo(moved), before)

    def test_existing_directory_file_and_links_are_never_overwritten(self):
        existing = self.root / "existing"
        existing.mkdir()
        marker = existing / "marker"
        marker.write_text("keep this", encoding="utf-8")
        for path in (existing, marker):
            with self.assertRaises(FileExistsError):
                create_demo(path)
        self.assertEqual(marker.read_text(encoding="utf-8"), "keep this")
        link = self.root / "link"
        try:
            link.symlink_to(existing, target_is_directory=True)
        except OSError:
            self.skipTest("This machine cannot create symlinks")
        with self.assertRaises(FileExistsError):
            create_demo(link)
        dangling = self.root / "dangling"
        dangling.symlink_to(self.root / "absent", target_is_directory=True)
        with self.assertRaises(FileExistsError):
            create_demo(dangling)
        self.assertFalse((self.root / "absent").exists())

    def test_changed_working_curve_does_not_rewrite_frozen_source(self):
        create_demo(self.project)
        curve = self.project / "fixture/raw/curve-A-dry.csv"
        curve.write_text("changed working copy\n", encoding="utf-8")
        self.assertEqual(verify_demo(self.project)["working_copy_changes"], 1)
        store, receipt = ProjectStore(self.project), self.receipt()
        path = store.snapshots.resolve(receipt["snapshot_id"], receipt["files"]["raw/curve-A-dry.csv"])["path"]
        self.assertIn("0,0,synthetic_available,1,synthetic,true", Path(path).read_text(encoding="utf-8"))

    def test_corrupt_frozen_object_is_rejected_without_repair(self):
        create_demo(self.project)
        store, receipt = ProjectStore(self.project), self.receipt()
        resolved = store.snapshots.resolve(receipt["snapshot_id"], receipt["files"]["raw/curve-A-dry.csv"])
        path = Path(resolved["path"])
        path.write_bytes(b"corrupt synthetic object")
        with self.assertRaisesRegex(ValueError, "Frozen fixture bytes are missing or invalid"):
            verify_demo(self.project)
        self.assertEqual(path.read_bytes(), b"corrupt synthetic object")


if __name__ == "__main__":
    unittest.main()
