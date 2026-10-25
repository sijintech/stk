"""The explicit report facade preserves selection guards in both Python and real workers."""
from pathlib import Path
from uuid import uuid4
import zipfile

import pytest

from suan.scripting import API
from test_bridge_reports import METHODS, assert_no_runs, prepared
from test_desktop_bridge import bridge_env  # noqa: F401
from test_desktop_scripts import scripts, execute  # noqa: F401


def test_report_facade_preserves_kwargs_destinations_and_original_project_handle():
    calls = []

    def call(method, params):
        calls.append((method, params))
        return {"method": method}

    api = API(call)
    api._project_handle = "a" * 32
    reports = api.project.reports
    identity, snapshot, record, context = (str(uuid4()) for _ in range(4))
    assets = [{"record_id": record, "path": "report.md"}]
    sources = [{"kind": "context", "id": context}]
    selection = {"expected_revision": 8, "expected_source_sha256": "b" * 64}
    assert reports.create("Report", snapshot, record, assets, report_id=identity,
                          expected_revision=7, sources=sources) == {"method": "project.reports.create"}
    reports.get(identity)
    reports.list(offset=4, limit=9)
    reports.asset(identity, "report.md", **selection)
    reports.preview(identity, **selection)
    destination = Path("export/report.zip")
    reports.export_file(identity, destination, **selection)
    base = {"handle": "a" * 32, "report_id": identity}
    assert calls == [
        ("project.reports.create", {**base, "name": "Report", "snapshot_id": snapshot,
            "entry_record_id": record, "assets": assets, "expected_revision": 7, "sources": sources}),
        ("project.reports.get", base),
        ("project.reports.list", {"handle": "a" * 32, "offset": 4, "limit": 9}),
        ("project.reports.asset", {**base, "path": "report.md", **selection}),
        ("project.reports.preview", {**base, **selection}),
        ("project.reports.export_file", {**base, "destination": str(destination), **selection}),
    ]
    api._project_handle = "c" * 32
    reports.get(identity)
    assert calls[-1] == ("project.reports.get", base)
    api.project.reports.get(identity)
    assert calls[-1][1]["handle"] == "c" * 32
    reports.create("Implicit empty provenance", snapshot, record, assets,
                   report_id=identity, expected_revision=8)
    assert "sources" not in calls[-1][1]
    reports.create("Explicit empty provenance", snapshot, record, assets,
                   report_id=identity, expected_revision=8, sources=[])
    assert calls[-1][1]["sources"] == []
    reports.list()
    assert calls[-1][1] == {"handle": "a" * 32, "offset": 0, "limit": 50}
    count = len(calls)
    with pytest.raises(TypeError):
        reports.preview(identity, 8, "b" * 64)
    with pytest.raises(TypeError):
        reports.asset(identity, "report.md", expected_revision=8)
    with pytest.raises(TypeError):
        reports.export_file(identity, destination, expected_source_sha256="b" * 64)
    assert len(calls) == count


def test_real_worker_report_facade_reads_frozen_bytes_reopens_and_never_starts_sources(scripts, tmp_path):
    project, store, snapshot, assets, originals = prepared(scripts, tmp_path)
    assert METHODS <= scripts.call("script.catalog")["operations"].keys()
    session = scripts.call("script.open")["session"]
    identity = str(uuid4())
    destination = tmp_path / "worker-report.zip"
    before_events = scripts.events_of("project.changed")
    source = f'''
import base64
import hashlib
from pathlib import Path
from suan.scripting import ScriptError
p = stk.project
reports = p.reports
assert reports.list()['reports'] == []
report_id = {identity!r}
created = reports.create('Worker report', {snapshot['id']!r}, {assets[0]['record_id']!r},
                         {assets!r}, report_id=report_id, expected_revision=2, sources=[])
assert created['revision'] == 3 and created['record_id'] == report_id
saved = reports.get(report_id)['report']
selection = {{'expected_revision': 3, 'expected_source_sha256': saved['source_sha256']}}
assert reports.list(limit=1)['reports'][0]['id'] == report_id
assert 'manifest' not in reports.list()['reports'][0]
for name in {list(originals)!r}:
    (Path({str(store.directory)!r}) / name).unlink()
asset = reports.asset(report_id, {assets[0]['path']!r}, **selection)
assert base64.b64decode(asset['data']) == {originals['report.md']!r}
preview = reports.preview(report_id, **selection)
assert preview['renderer'] == 'stk.report-renderer/1'
assert preview['source_content_sha256'] == asset['content_sha256']
assert preview['source_sha256'] == saved['source_sha256']
assert preview['content_sha256'] == hashlib.sha256(base64.b64decode(preview['data'])).hexdigest()
assert preview['content_sha256'] != preview['source_content_sha256']
exported = reports.export_file(report_id, Path({str(destination)!r}), **selection)
assert exported['sha256'] == hashlib.sha256(Path({str(destination)!r}).read_bytes()).hexdigest()
for selection_change in ({{'expected_revision': 2}}, {{'expected_source_sha256': '0' * 64}}):
    try:
        reports.preview(report_id, **{{**selection, **selection_change}})
    except ScriptError as error:
        assert error.code == 'conflict'
    else:
        raise AssertionError('stale report selection accepted')
try:
    reports.asset(report_id, 'unlisted.png', **selection)
except ScriptError as error:
    assert error.code == 'not_found'
else:
    raise AssertionError('unlisted report asset accepted')
assert p.close()
reopened = stk.projects.open({str(store.directory)!r})
assert reopened.reports.get(report_id)['report'] == saved
assert reopened.reports.asset(report_id, {assets[0]['path']!r}, **selection) == asset
assert reopened.reports.preview(report_id, **selection)['session_id'] != preview['session_id']
try:
    reports.get(report_id)
except ScriptError as error:
    assert error.code == 'not_found'
else:
    raise AssertionError('old report facade silently retargeted')
'''
    result = execute(scripts, session, source, project_handle=project.handle)
    assert result["run"]["state"] == "succeeded", scripts.call("script.read", {"session": session})["text"]
    assert store.info()["revision"] == 3 and len(store.history()) == 3
    assert_no_runs(store)
    assert scripts.events_of("project.changed") == before_events + [{"handle": project.handle, "revision": 3}]
    assert scripts.events_of("ui.request") == []
    with zipfile.ZipFile(destination) as archive:
        assert archive.read(assets[0]["path"]) == originals["report.md"]
    scripts.assert_clean()
