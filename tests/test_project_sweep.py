"""Parameter sweeps: value generation, row planning, base-row copies and every entry point."""
import json

from click.testing import CliRunner
import pytest

from suan.project import ProjectError, ProjectStore
from suan.project.sweep import MAX_ROWS, axis_values, plan_sweep
from test_desktop_bridge import bridge_env, inproc  # noqa: F401
from test_desktop_scripts import execute, scripts  # noqa: F401

T = "11111111-1111-4111-8111-111111111111"
TEMP, DERIVED, LABEL, STEPS, FLAG, OTHER = (f"{i}{i}{i}{i}{i}{i}{i}{i}-2222-4222-8222-222222222222" for i in range(2, 8))
BASE, ELSEWHERE = "55555555-5555-4555-8555-555555555555", "66666666-6666-4666-8666-666666666666"
NUMBER = {"id": TEMP, "name": "T", "type": "number"}
INTEGER = {"id": STEPS, "name": "steps", "type": "integer"}


def project(tmp_path):
    store = ProjectStore.create(tmp_path / "p", "Sweep")
    store.apply([
        {"op": "create_table", "id": T, "name": "Cases"},
        {"op": "add_field", "id": TEMP, "table_id": T, "name": "Temperature", "type": "number", "unit": "K"},
        {"op": "add_field", "id": DERIVED, "table_id": T, "name": "Derived", "type": "number", "unit": "K"},
        {"op": "add_field", "id": LABEL, "table_id": T, "name": "Label", "type": "text"},
        {"op": "add_field", "id": STEPS, "table_id": T, "name": "Steps", "type": "integer"},
        {"op": "add_field", "id": FLAG, "table_id": T, "name": "Flag", "type": "boolean"},
        {"op": "add_field", "id": OTHER, "table_id": T, "name": "Other row T", "type": "number", "unit": "K"},
        {"op": "add_record", "id": ELSEWHERE, "table_id": T},
        {"op": "set_cell", "table_id": T, "record_id": ELSEWHERE, "field_id": TEMP, "value": 250},
        {"op": "add_record", "id": BASE, "table_id": T},
        {"op": "set_cell", "table_id": T, "record_id": BASE, "field_id": TEMP, "value": 300},
        {"op": "set_expression", "table_id": T, "record_id": BASE, "field_id": DERIVED,
         "expression": "base + quantity(10, \"K\")", "bindings": {"base": {"record_id": BASE, "field_id": TEMP}}},
        {"op": "set_cell", "table_id": T, "record_id": BASE, "field_id": LABEL, "value": "case"},
        {"op": "set_cell", "table_id": T, "record_id": BASE, "field_id": STEPS, "value": 1000},
        {"op": "set_reference", "table_id": T, "record_id": BASE, "field_id": OTHER,
         "source": {"record_id": ELSEWHERE, "field_id": TEMP}},
    ], expected_revision=0)
    return store


def table(store):
    return next(t for t in store.snapshot()["tables"] if t["id"] == T)


def test_axis_values_are_typed_ranges_and_lists():
    assert axis_values({"field_id": TEMP, "start": 300, "stop": 400, "count": 5}, NUMBER) == [300, 325.0, 350.0, 375.0, 400]
    tenths = axis_values({"field_id": TEMP, "start": 0, "stop": 1, "count": 11}, NUMBER)
    assert tenths[3] == 0.3 and tenths[-1] == 1 and len(tenths) == 11  # never 0.30000000000000004
    assert axis_values({"field_id": TEMP, "start": 0.0, "stop": 0.3, "step": 0.1}, NUMBER) == [0.0, 0.1, 0.2, 0.3]
    assert axis_values({"field_id": TEMP, "start": 5, "stop": -5, "step": -5}, NUMBER) == [5, 0, -5]
    assert axis_values({"field_id": STEPS, "start": 100, "stop": 400, "count": 4}, INTEGER) == [100, 200, 300, 400]
    assert all(type(v) is int for v in axis_values({"field_id": STEPS, "start": 1, "stop": 9, "step": 4}, INTEGER))
    assert axis_values({"field_id": TEMP, "values": [1, 2.5]}, NUMBER) == [1, 2.5]
    assert axis_values({"field_id": TEMP, "start": 7, "stop": 9, "count": 1}, NUMBER) == [7]
    for axis, field in (
            ({"field_id": STEPS, "start": 0, "stop": 10, "count": 4}, INTEGER),       # 10/3 is not an integer step
            ({"field_id": STEPS, "start": 0.5, "stop": 10, "count": 2}, INTEGER),
            ({"field_id": STEPS, "values": [1.0]}, INTEGER),                        # 1.0 is not an integer
            ({"field_id": TEMP, "values": [True]}, NUMBER),                         # booleans are not numbers
            ({"field_id": TEMP, "values": ["300"]}, NUMBER),
            ({"field_id": TEMP, "values": [float("nan")]}, NUMBER),
            ({"field_id": TEMP, "start": 0, "stop": 1, "step": 0}, NUMBER),
            ({"field_id": TEMP, "start": 0, "stop": 1, "step": -1}, NUMBER),
            ({"field_id": TEMP, "start": 0, "stop": 1}, NUMBER),
            ({"field_id": TEMP, "values": []}, NUMBER),
            ({"field_id": TEMP, "start": 0, "stop": 1, "count": 1001}, NUMBER),
            ({"field_id": LABEL, "start": 0, "stop": 1, "count": 2}, {"id": LABEL, "name": "Label", "type": "text"}),
            ({"field_id": TEMP, "values": [2 ** 63]}, {"id": STEPS, "name": "s", "type": "integer"})):
        with pytest.raises(ProjectError):
            axis_values(axis, field)


def test_product_and_zip_rows_with_the_first_axis_varying_slowest(tmp_path):
    store = project(tmp_path)
    snapshot = store.snapshot()
    plan = plan_sweep(snapshot, T, [{"field_id": TEMP, "values": [300, 310]},
                                    {"field_id": LABEL, "values": ["a", "b", "c"]}])
    assert plan["rows"] == 6 and len(set(plan["record_ids"])) == 6
    cells = [(c["field_id"], c["value"]) for c in plan["commands"] if c["op"] == "set_cell"]
    assert cells[:6] == [(TEMP, 300), (LABEL, "a"), (TEMP, 300), (LABEL, "b"), (TEMP, 300), (LABEL, "c")]
    zipped = plan_sweep(snapshot, T, [{"field_id": TEMP, "values": [300, 310]}, {"field_id": LABEL, "values": ["a", "b"]}],
                        mode="zip")
    assert zipped["rows"] == 2
    with pytest.raises(ProjectError, match="same number"):
        plan_sweep(snapshot, T, [{"field_id": TEMP, "values": [1, 2]}, {"field_id": LABEL, "values": ["a"]}], mode="zip")
    with pytest.raises(ProjectError, match="at most"):
        plan_sweep(snapshot, T, [{"field_id": TEMP, "start": 0, "stop": 1, "count": 101},
                                 {"field_id": STEPS, "start": 0, "stop": 100, "count": 11}])
    for axes, message in (([{"field_id": "nope", "values": [1]}], "names a field"),
                          ([{"field_id": TEMP, "values": [1]}, {"field_id": TEMP, "values": [2]}], "one axis"),
                          ([], "1 to 8")):
        with pytest.raises(ProjectError, match=message):
            plan_sweep(snapshot, T, axes)
    with pytest.raises(ProjectError, match="Unknown table"):
        plan_sweep(snapshot, "nope", [{"field_id": TEMP, "values": [1]}])
    with pytest.raises(ProjectError, match="base row"):
        plan_sweep(snapshot, T, [{"field_id": TEMP, "values": [1]}], "77777777-7777-4777-8777-777777777777")
    assert MAX_ROWS == 1000
    # Every plan fits one ProjectStore.apply edit: 333 rows x 3 commands fit, 334 do not.
    two = [{"field_id": TEMP, "start": 0, "stop": 332, "count": 333}, {"field_id": LABEL, "values": ["a"]}]
    assert len(plan_sweep(snapshot, T, two)["commands"]) == 999
    two[0].update(stop=333, count=334)
    with pytest.raises(ProjectError, match="at most 333 rows"):
        plan_sweep(snapshot, T, two)
    with pytest.raises(ProjectError, match=r"\(6 per row\)"):
        plan_sweep(snapshot, T, [{"field_id": TEMP, "start": 0, "stop": 199, "count": 200}], BASE)
    from suan.project import analyses, files
    for managed in (analyses.TABLE_ID, files.TABLE_ID):
        fake = {"tables": [{"id": managed, "fields": [{"id": TEMP, "name": "x", "type": "number"}], "records": []}]}
        with pytest.raises(ProjectError, match="manages this table"):
            plan_sweep(fake, managed, [{"field_id": TEMP, "values": [1]}])


def test_base_row_copies_literals_references_and_row_relative_formulas(tmp_path):
    store = project(tmp_path)
    before = store.snapshot()["project"]["revision"]
    plan = plan_sweep(store.snapshot(), T, [{"field_id": TEMP, "start": 320, "stop": 340, "count": 2}], BASE)
    result = store.apply(plan["commands"], expected_revision=before)
    assert result["revision"] == before + 1
    rows = {r["id"]: r for r in table(store)["records"]}
    for record, temperature in zip(plan["record_ids"], [320, 340]):
        row = rows[record]
        assert row["values"][TEMP] == temperature and row["values"][LABEL] == "case" and row["values"][STEPS] == 1000
        # "base + 10 K" now reads this row's temperature, not the base row's.
        assert row["definitions"][DERIVED]["bindings"]["base"] == {"record_id": record, "field_id": TEMP}
        assert row["evaluations"][DERIVED]["value"] == temperature + 10
        # A reference to another row keeps pointing at that row.
        assert row["definitions"][OTHER] == {"kind": "reference", "source": {"record_id": ELSEWHERE, "field_id": TEMP}}
        assert FLAG not in row["values"]  # cells the base row lacks stay empty
    assert rows[BASE]["values"][TEMP] == 300  # the base row is unchanged
    store.undo(expected_revision=before + 1)
    assert set(r["id"] for r in table(store)["records"]) == {BASE, ELSEWHERE}


def test_bridge_plan_is_read_only_and_applies_through_project_apply(inproc, tmp_path):
    store = project(tmp_path)
    harness = inproc()
    opened = harness.call("project.open", {"directory": str(store.directory)})["project"]
    handle, revision = opened["handle"], opened["revision"]
    planned = harness.call("project.sweep.plan", {"handle": handle, "table_id": T, "base_record_id": BASE,
                                                  "axes": [{"field_id": TEMP, "start": 300, "stop": 320, "count": 3}]})
    assert planned["revision"] == revision and planned["plan"]["rows"] == 3
    assert harness.call("project.snapshot", {"handle": handle})["snapshot"]["project"]["revision"] == revision
    applied = harness.call("project.apply", {"handle": handle, "commands": planned["plan"]["commands"],
                                             "expected_revision": revision})
    assert applied["revision"] == revision + 1
    error = harness.error("project.sweep.plan", {"handle": handle, "table_id": T,
                                                 "axes": [{"field_id": TEMP, "values": ["hot"]}]})
    assert error["code"] == "invalid_params" and "does not fit" in error["message"]
    assert harness.error("project.sweep.plan", {"handle": handle, "table_id": T, "axes": []})["code"] == "invalid_params"
    assert not harness.violations
    harness.close()


def test_console_sweep_checks_the_revision_and_supports_a_dry_run(scripts, tmp_path):
    session = scripts.call("script.open")["session"]
    result = execute(scripts, session, f'''
from suan.scripting import ScriptError
p = stk.projects.create({str(tmp_path / "console")!r}, "Console sweep")
p.apply([{{"op": "create_table", "id": "{T}", "name": "Cases"}},
         {{"op": "add_field", "id": "{TEMP}", "table_id": "{T}", "name": "T", "type": "number", "unit": "K"}}],
        expected_revision=0)
axes = [{{"field_id": "{TEMP}", "start": 300, "stop": 400, "count": 5}}]
plan = p.sweep("{T}", axes, expected_revision=1, dry_run=True)
assert plan["rows"] == 5 and p.snapshot()["project"]["revision"] == 1
done = p.sweep("{T}", axes, expected_revision=1)
assert done["revision"] == 2 and done["rows"] == 5
try:
    p.sweep("{T}", axes, expected_revision=1)
except ScriptError as error:
    assert error.code == "conflict"
else:
    raise AssertionError("stale revision accepted")
print(sorted(r["values"]["{TEMP}"] for r in p.snapshot()["tables"][0]["records"]))
''')
    assert result["run"]["state"] == "succeeded", scripts.call("script.read", {"session": session})["text"]
    assert "[300, 325.0, 350.0, 375.0, 400]" in scripts.call("script.read", {"session": session})["text"]
    assert not scripts.violations


def test_cli_sweep_by_names_with_dry_run_and_revision(tmp_path):
    from suan.cli.main import cli
    store = project(tmp_path)
    runner = CliRunner()
    base = ["project", "sweep", str(store.directory), "--table", "Cases", "--range", "Temperature", "300", "320", "3",
            "--values", "Label", '["x", "y"]']
    dry = runner.invoke(cli, base + ["--dry-run"])
    assert dry.exit_code == 0, dry.output
    assert json.loads(dry.output)["rows"] == 6
    refused = runner.invoke(cli, base)
    assert refused.exit_code != 0 and "--expected-revision" in refused.output
    revision = store.snapshot()["project"]["revision"]
    done = runner.invoke(cli, base + ["--base", BASE, "--expected-revision", str(revision)])
    assert done.exit_code == 0, done.output
    assert json.loads(done.output)["rows"] == 6 and len(table(store)["records"]) == 8
    unknown = runner.invoke(cli, ["project", "sweep", str(store.directory), "--table", "Nope", "--values", "x", "[1]",
                                  "--dry-run"])
    assert unknown.exit_code != 0 and "No single table" in unknown.output
