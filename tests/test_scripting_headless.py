"""Headless ``stk``: the desktop console facade in a plain Python process."""
import subprocess
import sys

import pytest

from suan.scripting import ScriptError
from suan.scripting.headless import connect
from test_desktop_bridge import ROOT, bridge_env  # noqa: F401


def test_headless_session_uses_the_console_catalog_and_refuses_desktop_operations(bridge_env, tmp_path):
    with connect(tmp_path / "state") as stk:
        assert "project.sweep.plan" in stk.operations()["operations"]
        project = stk.use(stk.projects.create(tmp_path / "demo", "Demo"))
        assert stk.project.handle == project.handle
        table = "11111111-1111-4111-8111-111111111111"
        field = "22222222-2222-4222-8222-222222222222"
        stk.project.apply([{"op": "create_table", "id": table, "name": "Cases"},
                           {"op": "add_field", "id": field, "table_id": table, "name": "T", "type": "number"}],
                          expected_revision=0)
        result = stk.project.sweep(table, [{"field_id": field, "start": 300, "stop": 400, "count": 3}], expected_revision=1)
        assert result["rows"] == 3 and stk.project.snapshot()["project"]["revision"] == 2
        for desktop_only in (lambda: stk.ui.editors(), lambda: stk.viewer.status(), lambda: stk.project.selection()):
            with pytest.raises(ScriptError) as error:
                desktop_only()
            assert error.value.code == "unavailable"
        with pytest.raises(ScriptError) as busy:
            connect(tmp_path / "state")  # One service per state folder; the message names the way out.
        assert busy.value.code == "busy" and "state_dir" in str(busy.value)
    with pytest.raises(ScriptError) as closed:
        stk.projects.list()
    assert closed.value.code == "shutting_down"
    stk.close()  # Idempotent.
    reopened = connect(tmp_path / "state", project=tmp_path / "demo")
    assert len(reopened.project.snapshot()["tables"][0]["records"]) == 3
    reopened.close()


def test_headless_console_entry_point_runs_without_a_desktop(bridge_env, tmp_path):
    result = subprocess.run([sys.executable, "-m", "suan.scripting.headless", "--state-dir", str(tmp_path / "state")],
                            input="print(sorted(stk.operations()['operations'])[:1])\n", capture_output=True, text=True,
                            cwd=str(ROOT), timeout=120)
    assert result.returncode == 0, result.stderr
    assert "STK headless console" in result.stderr and "['blob.ensure']" in result.stdout
