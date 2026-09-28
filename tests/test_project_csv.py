"""CSV is a bounded value exchange, with project edits atomic and exports non-destructive."""
import csv
import hashlib
import io
import json
import os
from pathlib import Path

import pytest

from suan.project import ProjectStore, ProjectError, RevisionConflict
from test_desktop_bridge import bridge_env, inproc  # noqa: F401
from test_desktop_scripts import scripts, execute  # noqa: F401


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "参数.csv"
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(["Note", "Count", "Temperature", "Enabled", "Details"])
    writer.writerow(['中文, "quoted"\nnext line', 9223372036854775807, 300.5, "true", '{"tags":["温度"],"x":null}'])
    writer.writerow(["001", "", "", "false", "null"])
    path.write_text(stream.getvalue(), encoding="utf-8-sig", newline="")
    return path


TYPES = {"Count": "integer", "Temperature": "number", "Enabled": "boolean", "Details": "json"}
UNITS = {"Temperature": "K"}


def values(store, index=0):
    table = store.snapshot()["tables"][index]
    return [[record["values"][field["id"]] for field in table["fields"]] for record in table["records"]]


def test_typed_import_round_trip_and_single_undo_preserve_ids(tmp_path, source):
    store = ProjectStore.create(tmp_path / "project", "CSV")
    result = store.csv.import_file(source, name="Cases", types=TYPES, units=UNITS, expected_revision=0)
    assert result["revision"] == 1 and result["rows"] == 2 and result["columns"] == 5
    assert result["source_sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    expected = [['中文, "quoted"\nnext line', 9223372036854775807, 300.5, True, {"tags": ["温度"], "x": None}],
                ["001", None, None, False, None]]
    assert values(store) == expected
    snapshot = store.snapshot()
    assert snapshot["tables"][0]["fields"][2]["unit"] == "K"
    store.undo(expected_revision=1)
    assert store.snapshot()["tables"] == []
    store.redo(expected_revision=2)
    assert store.snapshot()["tables"] == snapshot["tables"]
    exported = store.csv.export_file(result["table_id"], tmp_path / "out.tsv", delimiter="\t", expected_revision=3)
    assert exported["revision"] == store.info()["revision"] == 3
    raw = Path(exported["path"]).read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf") and exported["sha256"] == hashlib.sha256(raw).hexdigest()
    imported = store.csv.import_file(exported["path"], name="Again", delimiter="\t", types=TYPES, units=UNITS, expected_revision=3)
    assert imported["table_id"] != result["table_id"] and values(store, 1) == expected


@pytest.mark.parametrize("text,types", [
    ("A,A\n1,2\n", {}), ("A,\n1,2\n", {}), ("A,B\n1\n", {}), ('A\n"unterminated', {}),
    ("A\ntrue\n", {"A": "number"}), ("A\n1.5\n", {"A": "integer"}),
    ("A\n9223372036854775808\n", {"A": "integer"}), ("A\nNaN\n", {"A": "number"}),
    ("A\n1\n", {"A": "boolean"}), ("A\nno\n", {"A": "json"}),
    ("A\n1\n", {"missing": "text"}), ("A\n1\n", {"A": "unknown"}),
])
def test_invalid_csv_is_atomic(tmp_path, text, types):
    store = ProjectStore.create(tmp_path / "project", "CSV")
    path = tmp_path / "bad.csv"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ProjectError):
        store.csv.import_file(path, name="Bad", types=types, expected_revision=0)
    assert store.info()["revision"] == 0 and store.snapshot()["tables"] == [] and store.history() == []


def test_size_batch_encoding_and_non_regular_sources_fail_without_mutation(tmp_path):
    store = ProjectStore.create(tmp_path / "project", "CSV")
    path = tmp_path / "source.csv"
    for raw in (b"A\n" + b"x" * (8 * 1024 * 1024), b"A\n" + b"x\n" * 500, b"A\n\xff"):
        path.write_bytes(raw)
        with pytest.raises(ProjectError):
            store.csv.import_file(path, name="Bad", expected_revision=0)
    if os.name == "posix":
        fifo = tmp_path / "fifo"
        os.mkfifo(fifo)
        with pytest.raises(ProjectError, match="regular"):
            store.csv.import_file(fifo, name="Bad", expected_revision=0)
    assert store.info()["revision"] == 0 and store.snapshot()["tables"] == []


def test_import_checks_final_revision_and_export_never_replaces_a_racing_destination(tmp_path, source, monkeypatch):
    store = ProjectStore.create(tmp_path / "project", "CSV")
    original = store.apply
    def concurrent(commands, *, expected_revision):
        original([{"op": "create_table", "name": "Other writer"}], expected_revision=0)
        return original(commands, expected_revision=expected_revision)
    monkeypatch.setattr(store, "apply", concurrent)
    with pytest.raises(RevisionConflict):
        store.csv.import_file(source, name="Stale", types=TYPES, expected_revision=0)
    assert [table["name"] for table in store.snapshot()["tables"]] == ["Other writer"]
    monkeypatch.setattr(store, "apply", original)
    result = store.csv.import_file(source, name="Good", types=TYPES, expected_revision=1)
    destination = tmp_path / "out.csv"
    with pytest.raises(RevisionConflict):
        store.csv.export_file(result["table_id"], destination, expected_revision=1)
    assert not destination.exists()
    link = os.link
    def raced(src, dst):
        Path(dst).write_bytes(b"other owner's output")
        return link(src, dst)
    monkeypatch.setattr(os, "link", raced)
    with pytest.raises(FileExistsError):
        store.csv.export_file(result["table_id"], destination, expected_revision=2)
    assert destination.read_bytes() == b"other owner's output"
    assert not list(tmp_path.glob(".stk-csv-*"))


def test_export_materializes_formulas_but_rejects_error_cells(tmp_path):
    store = ProjectStore.create(tmp_path / "project", "CSV")
    path = tmp_path / "source.csv"
    path.write_text("A,B\n3,0\n")
    result = store.csv.import_file(path, name="Derived", types={"A": "number", "B": "number"}, expected_revision=0)
    table, record = result["table_id"], result["record_ids"][0]
    a, b = result["field_ids"]
    command = {"op": "set_expression", "table_id": table, "record_id": record, "field_id": b,
               "expression": "x * 2", "bindings": {"x": {"record_id": record, "field_id": a}}}
    store.apply([command], expected_revision=1)
    dest = tmp_path / "derived.csv"
    store.csv.export_file(table, dest, expected_revision=2)
    assert list(csv.reader(io.StringIO(dest.read_text(encoding="utf-8-sig")))) == [["A", "B"], ["3", "6"]]
    store.apply([{**command, "expression": "x / 0"}], expected_revision=2)
    with pytest.raises(ProjectError, match="formula error"):
        store.csv.export_file(table, tmp_path / "error.csv", expected_revision=3)
    assert not (tmp_path / "error.csv").exists()


def test_csv_bridge_schema_events_and_console_facade(scripts, tmp_path, source):
    project = scripts.call("project.create", {"directory": str(tmp_path / "project"), "name": "CSV"})["project"]
    session = scripts.call("script.open")["session"]
    destination = tmp_path / "out.csv"
    code = f'''
p = stk.project
imported = p.csv.import_file({str(source)!r}, name='Cases', types={TYPES!r}, units={UNITS!r}, expected_revision=0)
assert imported['rows'] == 2
exported = p.csv.export_file(imported['table_id'], {str(destination)!r}, expected_revision=1)
assert exported['revision'] == 1
from suan.scripting import ScriptError
try:
    p.csv.export_file(imported['table_id'], {str(destination)!r}, expected_revision=1)
except ScriptError as error:
    assert error.code == 'conflict'
else:
    raise AssertionError('existing output overwritten')
'''
    result = execute(scripts, session, code, project_handle=project["handle"])
    assert result["run"]["state"] == "succeeded", scripts.call("script.read", {"session": session})["text"]
    assert scripts.wait_event(lambda event: event["event"] == "project.changed")["data"]["revision"] == 1
    assert len(scripts.events_of("project.changed")) == 1
    assert ProjectStore(tmp_path / "project").info()["revision"] == 1
    assert not scripts.violations


def test_csv_cli_and_default_text_do_not_infer_or_execute(tmp_path):
    from click.testing import CliRunner
    from suan.project.cli import project
    directory = tmp_path / "project"
    store = ProjectStore.create(directory, "CSV")
    source = tmp_path / "source.csv"
    source.write_text('Name,Value\ncase,001\nformula,=1+1\nflag,true\n', encoding="utf-8")
    runner = CliRunner()
    imported = runner.invoke(project, ["csv", "import", str(directory), str(source), "--name", "Raw", "--expected-revision", "0"])
    assert imported.exit_code == 0, imported.output
    table = json.loads(imported.output)["table_id"]
    assert values(store) == [["case", "001"], ["formula", "=1+1"], ["flag", "true"]]
    dest = tmp_path / "out.csv"
    exported = runner.invoke(project, ["csv", "export", str(directory), table, str(dest), "--expected-revision", "1"])
    assert exported.exit_code == 0, exported.output
    assert json.loads(exported.output)["rows"] == 3
    bad = runner.invoke(project, ["csv", "import", str(directory), str(source), "--name", "Bad", "--types", "[]", "--expected-revision", "1"])
    assert bad.exit_code != 0 and store.info()["revision"] == 1
