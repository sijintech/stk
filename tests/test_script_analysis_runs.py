"""Saved analyses travel through the real Python kernel, bridge and graph worker."""
from textwrap import dedent

from suan.project import ProjectStore
from test_desktop_bridge import bridge_env  # noqa: F401
from test_desktop_scripts import execute, scripts  # noqa: F401


def test_kernel_analysis_runs_are_explicit_and_survive_project_reopen(scripts, tmp_path):  # noqa: F811
    directory = tmp_path / "kernel-analysis"
    project = scripts.call("project.create", {
        "directory": str(directory), "name": "Kernel analysis",
    })["project"]
    source = directory / "input.dat"
    source.write_bytes(b"1 1 1\n1 1 1 -3\n")
    session = scripts.call("script.open", {"directory": str(directory)})["session"]

    def run(code, **params):
        result = execute(scripts, session, dedent(code), **params)
        assert result["run"]["state"] == "succeeded", scripts.call(
            "script.read", {"session": session})["text"]
        return result

    first = run("""
        from pathlib import Path
        from uuid import uuid4
        import hashlib
        import json
        import time
        from suan.scripting import ScriptError

        p = stk.project
        methods = {'project.analysis_runs.' + name for name in
                   ('prepare', 'get', 'list', 'start', 'cancel', 'recover', 'result')}
        assert methods <= set(stk.operations()['operations'])
        indexed = p.files.index(['input.dat'], expected_revision=0)
        record_id = indexed['record_ids'][0]
        captured = p.snapshots.capture([record_id], expected_revision=indexed['revision'])
        snapshot_id = captured['snapshot']['id']
        analysis_id, run_id, cancelled_id = (str(uuid4()) for _ in range(3))
        document = {
            'format': 'stk.analysis-document/1',
            'graph': {'schema': 'stk.graph/1', 'nodes': [
                {'id': 'source', 'type': 'stk.source.file@1',
                 'params': {'binding': 'data', 'path': 'nested/input.dat', 'format': 'dat'}}],
                      'outputs': {'field': 'source.out'}},
            'parameters': {}, 'outputs': [],
        }
        saved = p.analyses.create('Frozen field definition', document,
                                 analysis_id=analysis_id, expected_revision=captured['revision'])
        before_snapshot, before_history = p.snapshot(), p.history()
        assert saved['revision'] == before_snapshot['project']['revision'] == 3
        assert len(before_history) == 3
        bindings = {'data': {'nested/input.dat': record_id}}
        runs = p.analysis_runs
        prepared = runs.prepare(analysis_id, snapshot_id, bindings,
                                run_id=run_id, expected_revision=3)
        assert prepared['status'] == 'prepared'
        assert prepared['document'] == document
        assert prepared['bindings']['data']['nested/input.dat']['sha256'] == hashlib.sha256(
            b'1 1 1\\n1 1 1 -3\\n').hexdigest()
        assert runs.get(run_id) == prepared
        assert runs.recover(run_id) == prepared
        assert runs.list(offset=0, limit=1)['runs'][0]['id'] == run_id
        try:
            runs.result(run_id)
        except ScriptError as error:
            assert error.code == 'conflict'
        else:
            raise AssertionError('A prepared run has no result')
        assert runs.get(run_id) == prepared
        assert not (Path.cwd() / '.stk' / 'analysis-runs' / run_id).exists()

        runs.prepare(analysis_id, snapshot_id, bindings,
                     run_id=cancelled_id, expected_revision=3)
        cancelled = runs.cancel(cancelled_id)
        assert cancelled['status'] == 'cancelled'
        assert cancelled['started_at'] is None and cancelled['result'] is None
        assert runs.start(cancelled_id) == cancelled
        assert runs.get(run_id) == prepared
        assert p.snapshot() == before_snapshot and p.history() == before_history
    """, project_handle=project["handle"])

    store = ProjectStore(directory)
    before_snapshot, before_history = store.snapshot(), store.history()
    assert store.info()["revision"] == 3
    assert sorted(item["status"] for item in store.analysis_runs.list()["runs"]) == [
        "cancelled", "prepared"]
    scripts.wait_event(lambda event: event["event"] == "project.changed"
                      and event["data"]["revision"] == 3)
    changed_before = scripts.events_of("project.changed")
    source.unlink()  # The real executor must stage the saved copy, never the original file.

    second = run("""
        frozen_path = Path(p.snapshots.resolve(snapshot_id, record_id)['path'])
        assert frozen_path.read_bytes() == b'1 1 1\\n1 1 1 -3\\n'
        assert runs.start(run_id)['status'] == 'running'
        deadline = time.monotonic() + 10
        while True:
            completed = runs.get(run_id)
            if completed['status'] not in ('running', 'cancel_requested'):
                break
            assert time.monotonic() < deadline, completed
            time.sleep(0.02)
        assert completed['status'] == 'succeeded', completed
        assert completed['result']['output_count'] == 0
        assert not completed['result']['has_payload']
        archived = runs.result(run_id)
        assert archived['run'] == completed
        assert archived['result']['schema'] == 'stk.graph-result/1'
        assert archived['result']['outputs'] == {}
        assert not archived['result'].get('errors')
        blob_dir = Path(archived['blob_dir'])
        assert blob_dir.is_dir()
        manifest = blob_dir.parent / 'graph-result.json'
        assert json.loads(manifest.read_text(encoding='utf-8')) == archived['result']
        assert hashlib.sha256(manifest.read_bytes()).hexdigest() == completed['result']['manifest_sha256']
        assert runs.start(run_id) == completed
        assert p.snapshot() == before_snapshot and p.history() == before_history

        old_handle = p.handle
        assert p.close()
        reopened = stk.projects.open(Path.cwd(), expected_id=before_snapshot['project']['id'])
        assert reopened.handle != old_handle
        try:
            runs.get(run_id)
        except ScriptError as error:
            assert error.code == 'not_found'
        else:
            raise AssertionError('The saved facade must retain its closed project handle')
        assert reopened.analysis_runs.get(run_id) == completed
        assert reopened.analysis_runs.get(cancelled_id) == cancelled
        assert {item['id'] for item in reopened.analysis_runs.list()['runs']} == {run_id, cancelled_id}
        assert reopened.analysis_runs.result(run_id) == archived
        assert reopened.analysis_runs.start(run_id) == completed
        assert reopened.snapshot() == before_snapshot and reopened.history() == before_history
    """)
    assert second["kernel"] == first["kernel"]
    assert store.snapshot() == before_snapshot and store.history() == before_history
    assert scripts.events_of("project.changed") == changed_before
    assert scripts.events_of("graph.progress") == []
    assert not scripts.violations
