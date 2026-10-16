"""The shipped bridge and scripting facade expose the same bounded table exchange."""
import hashlib
import json
from pathlib import Path

import openpyxl
import pytest

from suan.project import ProjectStore
from suan.scripting import Project
from test_desktop_bridge import bridge_env, inproc  # noqa: F401


@pytest.mark.parametrize("format", ["csv", "xlsx", "json"])
def test_real_bridge_and_facade_roundtrip_have_strict_results_and_one_change(inproc, tmp_path, format):
    bridge = inproc()
    opened = bridge.call("project.create", {"directory": str(tmp_path / "project"), "name": "Exchange"})["project"]
    project = Project(bridge.call, opened["handle"])
    source = tmp_path / "input.csv"; source.write_text("Label,Count\n001,9223372036854775807\n")
    initial = project.csv.import_file(source, name="Original", types={"Count": "integer"}, expected_revision=0)
    assert bridge.wait_event(lambda e: e["event"] == "project.changed" and e["data"]["revision"] == 1)
    before_changes = len(bridge.events_of("project.changed"))
    destination = tmp_path / f"table.{format}"
    exported = project.table_io.export_file(initial["table_id"], destination, format=format, expected_revision=1)
    assert exported["format"] == format and exported["rows"] == 1
    assert exported["sha256"] == hashlib.sha256(destination.read_bytes()).hexdigest()
    preview = project.table_io.preview(destination, format=format, expected_revision=1)
    assert preview["schema_present"] == (format == "json") and preview["total_rows"] == 1
    assert len(bridge.events_of("project.changed")) == before_changes
    result = project.table_io.import_file(destination, format=format, name="Copy", expected_revision=1,
        types=None if format == "json" else {"Count": "integer"}, expected_sha256=preview["source_sha256"])
    bridge.wait_event(lambda e: e["event"] == "project.changed" and e["data"]["revision"] == 2)
    assert len(bridge.events_of("project.changed")) == before_changes + 1
    table = next(t for t in project.snapshot()["tables"] if t["id"] == result["table_id"])
    assert [table["records"][0]["values"][f["id"]] for f in table["fields"]] == ["001", 9223372036854775807]
    project.undo(expected_revision=2)
    assert [t["id"] for t in project.snapshot()["tables"]] == [initial["table_id"]]
    bridge.assert_clean()


@pytest.mark.parametrize("format", ["csv", "xlsx", "json"])
def test_bridge_preview_digest_conflicts_and_create_only_exports_do_not_notify(inproc, tmp_path, format):
    bridge = inproc()
    opened = bridge.call("project.create", {"directory": str(tmp_path / "project"), "name": "Conflict"})["project"]
    project = Project(bridge.call, opened["handle"])
    source = tmp_path / "source.csv"; source.write_text("A\nfirst\n")
    initial = project.csv.import_file(source, name="Original", expected_revision=0)
    path = tmp_path / f"table.{format}"
    project.table_io.export_file(initial["table_id"], path, format=format, expected_revision=1)
    project.table_io.preview(path, format=format, expected_revision=1)
    bridge.wait_event(lambda e: e["event"] == "project.changed" and e["data"]["revision"] == 1)
    events = len(bridge.events_of("project.changed"))
    base = {"handle": opened["handle"], "format": format, "source": str(path), "expected_revision": 1}
    error = bridge.error("project.table.io.import", {**base, "name": "Changed", "expected_sha256": "0" * 64})
    assert error["code"] == "conflict"
    assert bridge.error("project.table.io.preview", {**base, "expected_revision": 0})["code"] == "conflict"
    error = bridge.error("project.table.io.export", {"handle": opened["handle"], "format": format,
        "table_id": initial["table_id"], "destination": str(path), "expected_revision": 1})
    assert error["code"] == "conflict"
    assert len(bridge.events_of("project.changed")) == events
    assert len(project.snapshot()["tables"]) == 1
    bridge.assert_clean()


@pytest.mark.parametrize("method,extra", [
    ("preview", {"format": "xls"}), ("preview", {"limit": True}),
    ("preview", {"unrecognized": "value"}), ("preview", {"sheet": 1}),
    ("import", {"expected_sha256": "not-a-digest"}), ("import", {"types": []}),
    ("import", {"expected_revision": True}), ("export", {"format": "json", "unrecognized": True}),
])
def test_all_new_methods_enforce_strict_parameter_schema(inproc, tmp_path, method, extra):
    bridge = inproc()
    project = bridge.call("project.create", {"directory": str(tmp_path / "project"), "name": "Strict"})["project"]
    source = tmp_path / "a.csv"; source.write_text("A\nx\n")
    base = {"handle": project["handle"], "format": "csv", "expected_revision": 0}
    if method == "export":
        base.update(table_id="11111111-1111-4111-8111-111111111111", destination=str(tmp_path / "out.json"))
    else:
        base["source"] = str(source)
        if method == "import": base["name"] = "New"
    assert bridge.error("project.table.io." + method, {**base, **extra})["code"] == "invalid_params"
    assert ProjectStore(tmp_path / "project").info()["revision"] == 0
    assert not bridge.events_of("project.changed")
    bridge.assert_clean()


def test_xlsx_sheet_selection_flows_through_facade_without_inference(inproc, tmp_path):
    bridge = inproc()
    opened = bridge.call("project.create", {"directory": str(tmp_path / "project"), "name": "Sheet"})["project"]
    project = Project(bridge.call, opened["handle"])
    source = tmp_path / "sheets.xlsx"
    wb = openpyxl.Workbook(); wb.active.title = "Unused"; wb.active.append(["Ignore"])
    selected = wb.create_sheet("实验"); selected.append(["Date", "Count"]); selected.append(["2024-02-29", "001"])
    wb.save(source); wb.close()
    preview = project.table_io.preview(source, format="xlsx", sheet="实验", expected_revision=0)
    assert preview["sheet"] == "实验" and preview["sheets"] == [{"name": "Unused"}, {"name": "实验"}]
    result = project.table_io.import_file(source, format="xlsx", sheet="实验", name="实验", expected_revision=0,
                                         types={"Date": "date"}, expected_sha256=preview["source_sha256"])
    table = project.snapshot()["tables"][0]
    assert [table["records"][0]["values"][f["id"]] for f in table["fields"]] == ["2024-02-29", "001"]
    assert result["sheet"] == "实验"
    bridge.assert_clean()
