"""Explicit report requests freeze evidence; controlled completion never creates a report.

These tests use real SQLite contexts, run journals, snapshots and RequestExecutor.
The model adapter has no network or credentials, including gateway admission tests.
"""
import base64
from copy import deepcopy
import hashlib
import json
import sqlite3
from uuid import uuid4
import zipfile

import pytest

from suan.models import ModelGateway
from suan.models.gateway import PolicyDenied
from suan.project import ProjectError, ProjectStore, RevisionConflict
from suan.project import report_inputs, reports
from suan.project.aliyun import _payload
from suan.project.contexts import _digest, _encode
from suan.project.report_generation import INPUT_EXPORT, RESPONSE_EXPORT
from suan.project.report_previews import preview_resources
from suan.project.request_executor import ConfirmedCancellation, DefinitiveFailure, RequestExecutor, TextResponse
from suan.project.requests import REPORT_PROMPT_VERSION, _request_hash
from test_project_contexts import model, capture, cell  # noqa: F401
from test_request_executor import ControlledAdapter, eventually, idle


PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a5WQAAAAASUVORK5CYII=")
REPLY = "# 结果草稿\n\nThese frozen observations do not validate material properties.\n"


@pytest.fixture
def workers():
    active = []

    def make(adapter, gateway=None, adapter_id="controlled"):
        if gateway is None:
            executor = RequestExecutor({adapter_id: adapter})
        else:
            gateway[adapter_id] = adapter
            executor = RequestExecutor(gateway, gate=gateway.admit)
        active.append((executor, adapter))
        return executor

    yield make
    for executor, adapter in active:
        adapter.release.set()
        executor.shutdown()
    for executor, _ in active:
        eventually(lambda: idle(executor))


def selection(store, sources=(), *, snapshot=None, assets=()):
    revision = store.info()["revision"]
    sources = list(sources)
    review = store.reports.review_sources(sources, expected_revision=revision)
    return {"expected_revision": revision, "sources": sources,
            "expected_sources_sha256": review["sources_sha256"],
            "snapshot_id": None if snapshot is None else snapshot["id"], "assets": list(assets)}


def prepare(store, context, selected=None, *, adapter="controlled", request_id=None, message=None):
    if message is None:
        message = store.discussion.add("Write a Markdown report about only the selected frozen evidence.",
                                       message_id=str(uuid4()), context_id=context["id"])
    return store.requests.create(message["id"], request_id=request_id or str(uuid4()),
        configuration={"adapter": adapter, "model": "report-test"}, prompt_version=REPORT_PROMPT_VERSION,
        report_selection=selection(store) if selected is None else selected)


def complete(store, request, workers, *, reply=REPLY, gateway=None):
    adapter = ControlledAdapter(TextResponse(reply, {"model": "report-test", "output_tokens": 25}))
    executor = workers(adapter, gateway, request["configuration"]["adapter"])
    executor.start(store, request["id"])
    assert adapter.started.wait(5)
    assert executor.start(store, request["id"])["status"] == "running"
    adapter.release.set()
    eventually(lambda: idle(executor))
    record = store.requests.get(request["id"])
    assert record["status"] == "completed"
    assert executor.start(store, request["id"]) == record
    assert len(adapter.inputs) == 1
    return record, adapter


def freeze(store, request, body=REPLY, **changes):
    values = {"report_id": str(uuid4()), "expected_revision": store.info()["revision"],
              "expected_input_sha256": request["input_sha256"],
              "expected_response_sha256": (request["result"] or {}).get("text_sha256", "0" * 64)}
    values.update(changes)
    return store.reports.create_generated("生成报告", request["id"], body, **values)


def attachment(store):
    path = store.directory / "plot #100%.png"
    path.write_bytes(PNG)
    indexed = store.files.index([str(path)], expected_revision=store.info()["revision"])
    identity = indexed["record_ids"][0]
    snapshot = store.snapshots.capture([identity], expected_revision=indexed["revision"])["snapshot"]
    return snapshot, {"record_id": identity, "path": "images/plot #100%.png"}, path


def run_sources(store, ids, snapshot, image):
    """Prepare all three real run kinds; no executor, plugin or Runtime is invoked."""
    simulation = store.runs.prepare([{"table_id": ids["table"], "record_id": ids["first"],
        "spec": {"workspace_id": "a" * 32, "argv": ["{python}", "-c", "pass"]}}],
        connection="runtime:Fixture", connection_identity="a" * 16,
        expected_revision=store.info()["revision"])["run_ids"][0]
    analysis_id, analysis_run, workflow_id, workflow_run = (str(uuid4()) for _ in range(4))
    store.analyses.create("Frozen unexecuted graph", {"format": "stk.analysis-document/1", "graph": {
        "schema": "stk.graph/1", "nodes": [{"id": "source", "type": "missing.source.node@1",
                                            "params": {"binding": "data"}}],
        "outputs": {"view": "source.payload"}}, "parameters": {}, "outputs": ["view"]},
        analysis_id=analysis_id, expected_revision=store.info()["revision"])
    name = snapshot["manifest"]["files"][0]["name"]
    store.analysis_runs.prepare(analysis_id, snapshot["id"], {"data": {name: image["record_id"]}},
                               run_id=analysis_run, expected_revision=store.info()["revision"])
    store.workflows.create("Frozen unexecuted workflow", {"format": "stk.workflow/1", "steps": [
        {"id": "cases", "kind": "table", "ref": {"table": ids["table"]}},
        {"id": "simulate", "kind": "simulation", "ref": {"template": "demo-synthetic/1"},
         "inputs": {"rows": {"from": "cases.rows"}}, "parameters": {"temperature": {"$field": ids["temperature"]}}}],
        "ui": {}}, workflow_id=workflow_id, expected_revision=store.info()["revision"])
    store.workflow_runs.prepare(workflow_id, [ids["first"]], run_id=workflow_run,
                                expected_revision=store.info()["revision"])
    return [{"kind": kind, "id": identity} for kind, identity in
            (("simulation_run", simulation), ("analysis_run", analysis_run), ("workflow_run", workflow_run))]


def advance(store, source):
    if source["kind"] == "simulation_run":
        store.runs.observe(source["id"], {"submission": "submitting"})
    elif source["kind"] == "analysis_run":
        store.analysis_runs._claim(source["id"], executor_id=str(uuid4()))
    else:
        store.workflow_runs.start(source["id"], executor_id=str(uuid4()))


def test_generated_inline_body_single_edit_reopen_undo_and_portable_evidence(model, workers, tmp_path):
    store, _ = model
    context = capture(model)
    history = store.history()
    request = prepare(store, context)
    pending = store.reports.generation_request(request["id"])
    assert set(pending) == {"revision", "request", "input", "response"}
    assert pending["response"] is None and pending["input"]["context"] == context
    assert _digest(pending["input"]) == request["input_sha256"]
    assert store.reports.list()["total"] == 0 and store.history() == history
    done, adapter = complete(store, request, workers)
    assert store.reports.list()["total"] == 0 and store.history() == history
    edited = REPLY + "\nExplicitly reviewed by the user.\n"
    result = freeze(store, done, edited)
    assert result["revision"] == pending["revision"] + 1
    assert len(store.history()) == len(history) + 1
    report = store.reports.get(result["record_id"])["report"]
    manifest, generation = report["manifest"], report["manifest"]["generation"]
    assert report["state"] == "readable" and report["format"] == "stk.report/2"
    assert manifest["snapshot_id"] is None and manifest["snapshot_sha256"] is None
    assert generation["body"] == edited and generation["edited"] is True
    assert generation["input_sha256"] == _digest(adapter.inputs[0])
    assert generation["response_sha256"] == hashlib.sha256(REPLY.encode()).hexdigest()
    assert generation["input_revision"] == context["source_revision"]
    assert manifest["sources"][0]["context"] == context
    [entry] = manifest["assets"]
    assert entry["mime"] == "text/markdown; charset=utf-8" and entry["size"] == len(edited.encode())
    with store._connect() as db:
        assert db.execute("SELECT COUNT(*) FROM project_snapshots").fetchone()[0] == 0
        assert db.execute("SELECT 1 FROM records WHERE id=?", (entry["record_id"],)).fetchone() is None
    kwargs = {"expected_revision": result["revision"], "expected_source_sha256": report["source_sha256"]}
    assert base64.b64decode(store.reports.asset(result["record_id"], "report.md", **kwargs)["data"]) == edited.encode()
    output = tmp_path / "generated.zip"
    receipt = store.reports.export_file(result["record_id"], str(output), **kwargs)
    assert receipt["size"] == output.stat().st_size
    assert receipt["sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()
    with zipfile.ZipFile(output) as package:
        assert set(package.namelist()) == {"stk-report.json", "report.md", INPUT_EXPORT, RESPONSE_EXPORT}
        assert package.read("report.md") == edited.encode()
        assert package.read(INPUT_EXPORT) == _encode(pending["input"])
        assert package.read(RESPONSE_EXPORT) == REPLY.encode()
        assert json.loads(package.read("stk-report.json"))["manifest"] == manifest
    reopened = ProjectStore(store.directory)
    assert reopened.reports.get(result["record_id"])["report"] == report
    assert reopened.reports.generation_request(request["id"])["input"] == pending["input"]
    reopened.undo(expected_revision=result["revision"])
    assert reopened.reports.list()["total"] == 0
    assert reopened.requests.get(request["id"])["status"] == "completed"
    reopened.redo(expected_revision=result["revision"] + 1)
    assert reopened.reports.get(result["record_id"])["report"] == report


def test_mixed_sources_and_real_snapshot_survive_run_progress_and_deleted_live_file(model, workers, monkeypatch):
    store, ids = model
    context = capture(model)
    snapshot, image, live = attachment(store)
    sources = run_sources(store, ids, snapshot, image)
    selected = selection(store, [{"kind": "context", "id": context["id"]}] + sources,
                         snapshot=snapshot, assets=[image])
    request = prepare(store, context, selected)
    frozen = store.requests.input(request["id"])
    payload, stream_payload, input_digest = _payload(frozen, adapter="controlled")
    wire = json.loads(payload)
    evidence = json.loads(wire["messages"][1]["content"])
    assert set(evidence) == {"saved_context", "question", "report_input"}
    assert evidence["question"] == frozen["message"]["text"]
    assert evidence["saved_context"] == context and evidence["report_input"] == frozen["report_input"]
    assert input_digest.hex() == request["input_sha256"]
    assert json.loads(stream_payload)["messages"] == wire["messages"]
    message = store.discussion.get(request["message_id"])
    for source in sources:
        advance(store, source)
    live.unlink()
    assert prepare(store, context, selected, request_id=request["id"], message=message) == request
    assert store.reports.generation_request(request["id"])["input"] == frozen
    store.apply([cell(ids, "temperature", 400)], expected_revision=store.info()["revision"])
    done, adapter = complete(store, request, workers)
    assert adapter.inputs == [frozen]
    body = '# Report\n\n![Plot](images/plot%20%23100%25.png)\n\n<script>alert("no")</script>'
    before = store.info()["revision"]
    with monkeypatch.context() as patch:
        patch.setattr(reports, "_capture_sources", lambda *args: pytest.fail("recaptured changed run state"))
        patch.setattr(store, "snapshot", lambda: pytest.fail("loaded the entire project"))
        result = freeze(store, done, body)
        report = store.reports.get(result["record_id"])["report"]
    manifest = report["manifest"]
    assert manifest["source_revision"] == before > frozen["report_input"]["source_revision"] > context["source_revision"]
    assert manifest["generation"]["input_revision"] == frozen["report_input"]["source_revision"]
    assert [s["kind"] for s in manifest["sources"]] == ["context", "simulation_run", "analysis_run", "workflow_run"]
    assert manifest["sources"] == frozen["report_input"]["sources"]
    assert manifest["sources"][1]["captured_status"]["status"] == {"submission": "prepared"}
    kwargs = {"expected_revision": result["revision"], "expected_source_sha256": report["source_sha256"]}
    assert base64.b64decode(store.reports.asset(result["record_id"], image["path"], **kwargs)["data"]) == PNG
    ready = preview_resources(store, result["record_id"], **kwargs)
    display = ready["preview"]
    assert ready["resources"] == manifest["assets"][1:]
    rendered = base64.b64decode(display["data"])
    assert b"<script" not in rendered and b"<img" in rendered
    assert display["source_content_sha256"] == hashlib.sha256(body.encode()).hexdigest()
    assert display["content_sha256"] == hashlib.sha256(rendered).hexdigest()
    assert display["content_sha256"] != display["source_content_sha256"]
    assert ready["total_size"] == len(rendered) + len(PNG)
    reopened = ProjectStore(store.directory)
    assert reopened.reports.get(result["record_id"])["report"] == report
    assert reopened.reports.generation_request(request["id"])["input"] == frozen


@pytest.mark.parametrize("kind", ["simulation_run", "analysis_run", "workflow_run"])
def test_same_revision_source_drift_refuses_request_without_journal_write(model, kind):
    store, ids = model
    context = capture(model)
    snapshot, image, _ = attachment(store)
    sources = run_sources(store, ids, snapshot, image)
    source = next(item for item in sources if item["kind"] == kind)
    selected = selection(store, [source])
    message = store.discussion.add("Report", message_id=str(uuid4()), context_id=context["id"])
    history = store.history()
    advance(store, source)
    assert store.info()["revision"] == selected["expected_revision"]
    with pytest.raises(RevisionConflict, match="sources changed"):
        prepare(store, context, selected, message=message)
    assert store.requests.list()["requests"] == [] and store.history() == history


def rewrite_frozen_input(store, request, mutate):
    """Recompute storage hashes so malformed semantic input cannot fail only its envelope hash."""
    inputs = store.requests.input(request["id"])
    mutate(inputs["report_input"])
    with sqlite3.connect(store.path) as db:
        row = db.execute("SELECT payload,state,request_sha256 FROM project_requests WHERE id=?", (request["id"],)).fetchone()
        payload, state, request_sha = json.loads(row[0]), json.loads(row[1]), row[2]
        payload["report_input"] = inputs["report_input"]
        payload["input_sha256"] = _digest(inputs)
        identity_sha = _digest({"payload": payload, "request_sha256": request_sha})
        state_sha = _digest({"id": request["id"], "sha256": identity_sha, "state": state})
        db.execute("UPDATE project_requests SET payload=?,sha256=?,state_sha256=? WHERE id=?",
                   (_encode(payload).decode(), identity_sha, state_sha, request["id"]))


@pytest.mark.parametrize("corruption", ["missing_shape", "other_primary"])
def test_matching_primary_id_cannot_hide_corrupt_provenance_during_deduplication(model, corruption):
    store, _ = model
    context = capture(model)
    selected = selection(store, [{"kind": "context", "id": context["id"]}])
    request = prepare(store, context, selected)

    def mutate(value):
        source = value["sources"][0]
        if corruption == "missing_shape":
            source.pop("context")
        else:
            source["context"]["title"] = "Different but otherwise valid captured context"
            source["context_sha256"] = _digest(source["context"])

    rewrite_frozen_input(store, request, mutate)
    with pytest.raises(ProjectError):
        store.reports.generation_request(request["id"])
    with pytest.raises(ProjectError):
        store.requests.input(request["id"])
    assert store.reports.list()["total"] == 0


@pytest.mark.parametrize("corruption", ["run_status", "source_order", "asset_path"])
def test_valid_frozen_input_must_still_match_original_reviewed_selection(model, corruption):
    store, ids = model
    context = capture(model)
    snapshot, image, _ = attachment(store)
    sources = run_sources(store, ids, snapshot, image)
    request = prepare(store, context, selection(store, sources, snapshot=snapshot, assets=[image]))

    def mutate(value):
        if corruption == "run_status":
            value["sources"][0]["captured_status"]["status"]["submission"] = "submitting"
        elif corruption == "source_order":
            value["sources"].reverse()
        else:
            value["assets"][0]["path"] = "images/other-valid-name.png"
        # The changed object remains valid provenance and uses original snapshot
        # bytes; only its binding to the user's original reviewed selection differs.
        with store._connect() as db:
            report_inputs.validate(store, db, context, value)

    rewrite_frozen_input(store, request, mutate)
    with pytest.raises(ProjectError):
        store.reports.generation_request(request["id"])
    assert store.reports.list()["total"] == 0


def test_primary_context_occupies_one_of_the_sixteen_total_source_slots(model):
    store, _ = model
    contexts = [capture(model) for _ in range(17)]
    selectors = [{"kind": "context", "id": context["id"]} for context in contexts]
    selected = selection(store, selectors[1:])
    with pytest.raises(ProjectError):
        prepare(store, contexts[0], selected)
    assert store.requests.list()["requests"] == []
    request = prepare(store, contexts[0], selection(store, selectors[:16]))
    value = store.requests.input(request["id"])
    assert len(report_inputs.sources_with_context(value["context"], value["report_input"])) == 16


def test_primary_plus_selected_context_metadata_budget_is_checked_before_request_creation(model):
    store, ids = model
    rows = [str(uuid4()) for _ in range(7)]
    commands = []
    for row in rows:
        commands.extend([{"op": "add_record", "id": row, "table_id": ids["table"]},
            {"op": "set_cell", "table_id": ids["table"], "record_id": row,
             "field_id": ids["note"], "value": "x" * 15000}])
    store.apply(commands, expected_revision=1)
    primary, secondary = [capture(model, record_ids=rows, field_ids=[ids["note"]]) for _ in range(2)]
    assert primary["content"]["state"] == secondary["content"]["state"] == "included"
    assert len(_encode(primary)) < 256 * 1024
    assert len(_encode(primary)) + len(_encode(secondary)) > report_inputs.MAX_SOURCE_BYTES
    selected = selection(store, [{"kind": "context", "id": secondary["id"]}])
    history = store.history()
    with pytest.raises(ProjectError, match="192 KiB"):
        prepare(store, primary, selected)
    assert store.requests.list()["requests"] == [] and store.history() == history


def test_near_limit_sources_leave_room_for_full_64k_json_escaped_body(model, workers):
    store, ids = model
    rows = [str(uuid4()) for _ in range(6)]
    commands = []
    for row in rows:
        commands.extend([{"op": "add_record", "id": row, "table_id": ids["table"]},
            {"op": "set_cell", "table_id": ids["table"], "record_id": row,
             "field_id": ids["note"], "value": "x" * 15000}])
    store.apply(commands, expected_revision=1)
    primary, secondary = [capture(model, record_ids=rows, field_ids=[ids["note"]]) for _ in range(2)]
    request = prepare(store, primary, selection(store, [{"kind": "context", "id": secondary["id"]}]))
    inputs = store.requests.input(request["id"])
    metadata_size = len(_encode({"sources": report_inputs.sources_with_context(primary, inputs["report_input"]),
                                "assets": []}))
    assert 176 * 1024 < metadata_size <= report_inputs.MAX_SOURCE_BYTES
    done, _ = complete(store, request, workers)
    body = "\\" * 65536
    assert len(body.encode()) == 65536 and len(_encode(body)) == 128 * 1024 + 2
    created = freeze(store, done, body)
    report = store.reports.get(created["record_id"])["report"]
    assert report["state"] == "readable"
    assert report["manifest"]["generation"]["body"] == body
    assert len(_encode({"name": report["name"], "format": report["format"], "manifest": report["manifest"]})) <= reports.MAX_MANIFEST_BYTES
    assert ProjectStore(store.directory).reports.get(created["record_id"])["report"] == report


@pytest.mark.parametrize("virtual_path", ["stk-generation-response.txt", "STK-GENERATION-RESPONSE.TXT",
                                         "stk-generation-input.json/attachment.txt"])
def test_export_sidecar_path_conflicts_are_rejected_before_request_creation(model, virtual_path):
    store, _ = model
    context = capture(model)
    source = store.directory / "attachment.txt"
    source.write_text("Explicit selected attachment", encoding="utf-8")
    indexed = store.files.index([str(source)], expected_revision=store.info()["revision"])
    snapshot = store.snapshots.capture(indexed["record_ids"], expected_revision=indexed["revision"])["snapshot"]
    selected = selection(store, snapshot=snapshot, assets=[{"record_id": indexed["record_ids"][0], "path": virtual_path}])
    history = store.history()
    with pytest.raises(ProjectError):
        prepare(store, context, selected)
    assert store.requests.list()["requests"] == [] and store.history() == history


def test_attachment_virtual_extension_cannot_change_frozen_mime(model):
    store, _ = model
    context = capture(model)
    snapshot, image, _ = attachment(store)
    image["path"] = "misleading.html"
    selected = selection(store, snapshot=snapshot, assets=[image])
    history = store.history()
    with pytest.raises(ProjectError, match="frozen original"):
        prepare(store, context, selected)
    assert store.requests.list()["requests"] == [] and store.history() == history


@pytest.mark.parametrize("source_kind", ["file", "primary_context", "context", "simulation_run", "analysis_run", "workflow_run"])
def test_gateway_rechecks_every_report_source_label_before_any_send(model, workers, tmp_path, source_kind):
    store, ids = model
    primary = capture(model)
    snapshot, image, _ = attachment(store)
    sources = run_sources(store, ids, snapshot, image)
    other_table, field, row = (str(uuid4()) for _ in range(3))
    store.apply([{"op": "create_table", "id": other_table, "name": "Other source"},
                 {"op": "add_field", "id": field, "table_id": other_table, "name": "Value", "type": "number"},
                 {"op": "add_record", "id": row, "table_id": other_table}], expected_revision=store.info()["revision"])
    secondary = store.contexts.capture(other_table, [row], [field], context_id=str(uuid4()),
                                      expected_revision=store.info()["revision"], title="Secondary")
    selected_sources = ([next(s for s in sources if s["kind"] == source_kind)] if source_kind.endswith("_run")
                        else [{"kind": "context", "id": secondary["id"]}])
    public = [{"kind": "table", "id": ids["table"]}, {"kind": "table", "id": other_table},
              {"kind": "file", "id": image["record_id"]}]
    store.labels.set(public, label="public")
    gateway = ModelGateway(tmp_path / "model-state")
    endpoint = gateway.endpoints.add("report-cloud", "Controlled cloud", "https://reports.example.invalid/v1", ["report-test"])
    request = prepare(store, primary, selection(store, selected_sources, snapshot=snapshot, assets=[image]),
                      adapter=endpoint["adapter"])
    revision = store.info()["revision"]
    if source_kind == "file":
        store.labels.set([public[2]], label="private")
    elif source_kind == "primary_context":
        store.labels.set([public[0]], label="private")
    elif source_kind == "context":
        store.labels.set([public[1]], label="structure")
    assert store.info()["revision"] == revision
    adapter = ControlledAdapter(REPLY)
    executor = workers(adapter, gateway, endpoint["adapter"])
    with pytest.raises(PolicyDenied, match="report contains private sources"):
        executor.start(store, request["id"])
    assert not adapter.started.is_set() and adapter.inputs == []
    assert store.requests.get(request["id"])["status"] == "pending"
    assert len(store.discussion.list()["messages"]) == 1


@pytest.mark.parametrize("location,url", [("local", "http://127.0.0.1:1/v1"), ("internal", "http://10.1.2.3:1/v1")])
def test_local_and_internal_report_admission_preserve_private_run_evidence(model, workers, tmp_path, location, url):
    store, ids = model
    context = capture(model)
    snapshot, image, _ = attachment(store)
    sources = run_sources(store, ids, snapshot, image)
    gateway = ModelGateway(tmp_path / "model-state")
    endpoint = gateway.endpoints.add("nearby", "Controlled nearby", url, ["report-test"], location)
    request = prepare(store, context, selection(store, sources, snapshot=snapshot, assets=[image]), adapter=endpoint["adapter"])
    done, adapter = complete(store, request, workers, gateway=gateway)
    assert adapter.inputs[0]["report_input"]["sources"][0]["kind"] == "simulation_run"
    assert store.reports.get(freeze(store, done)["record_id"])["report"]["state"] == "readable"


@pytest.mark.parametrize("state", ["pending", "running", "cancelled", "uncertain", "failed"])
def test_only_a_completed_saved_response_can_become_a_report(model, workers, state):
    store, _ = model
    request = prepare(store, capture(model))
    response = OSError("connection lost after send") if state == "uncertain" else DefinitiveFailure("adapter_failed")
    adapter = ControlledAdapter(response)
    executor = workers(adapter)
    if state == "cancelled":
        executor.cancel(store, request["id"])
    elif state != "pending":
        executor.start(store, request["id"])
        assert adapter.started.wait(5)
        if state != "running":
            adapter.release.set()
            eventually(lambda: idle(executor))
    observed = store.requests.get(request["id"])
    assert observed["status"] == state
    assert store.reports.generation_request(request["id"])["response"] is None
    history = store.history()
    with pytest.raises(ProjectError, match="complete saved report response"):
        freeze(store, observed)
    assert store.history() == history and store.reports.list()["total"] == 0
    if state not in ("pending", "running"):
        assert executor.start(store, request["id"])["status"] == state
        assert len(adapter.inputs) == (0 if state == "cancelled" else 1)


def test_confirmed_cancel_after_send_does_not_publish_a_partial_report(model, workers):
    store, _ = model
    request = prepare(store, capture(model))
    adapter = ControlledAdapter(ConfirmedCancellation())
    executor = workers(adapter)
    executor.start(store, request["id"])
    assert adapter.started.wait(5)
    executor.cancel(store, request["id"])
    adapter.release.set()
    eventually(lambda: idle(executor))
    cancelled = store.requests.get(request["id"])
    assert cancelled["status"] == "cancelled"
    with pytest.raises(ProjectError, match="complete saved report response"):
        freeze(store, cancelled)
    assert len(store.discussion.list()["messages"]) == 1 and len(adapter.inputs) == 1


@pytest.mark.parametrize("key", ["expected_input_sha256", "expected_response_sha256", "expected_revision"])
def test_freeze_requires_exact_request_response_and_current_revision(model, workers, key):
    store, _ = model
    done, _ = complete(store, prepare(store, capture(model)), workers)
    history = store.history()
    invalid = 0 if key == "expected_revision" else "0" * 64
    with pytest.raises(RevisionConflict):
        freeze(store, done, **{key: invalid})
    assert store.history() == history and store.reports.list()["total"] == 0


@pytest.mark.parametrize("body,edited", [(REPLY, False), (REPLY.replace("\n", "\r\n"), True), (REPLY + " ", True)])
def test_edited_flag_is_derived_from_exact_completed_response(model, workers, body, edited):
    store, _ = model
    done, _ = complete(store, prepare(store, capture(model)), workers)
    report = store.reports.get(freeze(store, done, body)["record_id"])["report"]
    assert report["manifest"]["generation"]["edited"] is edited
    assert report["manifest"]["assets"][0]["sha256"] == hashlib.sha256(body.encode()).hexdigest()


@pytest.mark.parametrize("body", ["界" * 21846, "x\x00y", "\x85", " ", "\ud800"],
                         ids=["utf8_over_limit", "nul", "c1_control", "blank", "unpaired_surrogate"])
def test_invalid_or_oversized_generated_body_is_rejected_atomically(model, workers, body):
    store, _ = model
    done, _ = complete(store, prepare(store, capture(model)), workers)
    history = store.history()
    with pytest.raises(ProjectError):
        freeze(store, done, body)
    assert store.history() == history and store.reports.list()["total"] == 0


def test_valid_full_64k_utf8_body_is_not_truncated(model, workers):
    store, _ = model
    done, _ = complete(store, prepare(store, capture(model)), workers)
    body = "界" * 21845 + "x"
    assert len(body.encode()) == 65536
    result = freeze(store, done, body)
    report = store.reports.get(result["record_id"])["report"]
    received = store.reports.asset(result["record_id"], "report.md", expected_revision=result["revision"],
                                  expected_source_sha256=report["source_sha256"])
    assert base64.b64decode(received["data"]).decode() == body


def test_asset_io_revision_race_never_leaves_a_partial_generated_report(model, workers, monkeypatch):
    store, ids = model
    context = capture(model)
    snapshot, image, _ = attachment(store)
    done, _ = complete(store, prepare(store, context, selection(store, snapshot=snapshot, assets=[image])), workers)
    history, revision = store.history(), store.info()["revision"]
    original = reports._read_asset

    def racing_read(current, asset):
        data = original(current, asset)
        ProjectStore(store.directory).apply([cell(ids, "temperature", 450)], expected_revision=revision)
        return data

    monkeypatch.setattr(reports, "_read_asset", racing_read)
    with pytest.raises(RevisionConflict):
        freeze(store, done, expected_revision=revision)
    assert store.reports.list()["total"] == 0
    assert len(store.history()) == len(history) + 1  # Only the independent editor committed.


def test_generic_damage_to_generation_provenance_is_local_invalid_metadata(model, workers):
    store, _ = model
    done, _ = complete(store, prepare(store, capture(model)), workers)
    first = freeze(store, done)["record_id"]
    second = freeze(store, done, REPLY + " second edition")["record_id"]
    report = store.reports.get(first)["report"]
    manifest = deepcopy(report["manifest"])
    manifest["generation"]["edited"] = True  # A valid bool, but false provenance.
    store.apply([{"op": "set_cell", "table_id": reports.TABLE_ID, "record_id": first,
                  "field_id": reports.FIELD_IDS["manifest"], "value": manifest}], expected_revision=store.info()["revision"])
    assert store.reports.get(first)["report"]["state"] == "invalid"
    assert store.reports.get(second)["report"]["state"] == "readable"
    assert {value["id"]: value["state"] for value in store.reports.list()["reports"]} == {first: "invalid", second: "readable"}
    with pytest.raises(ProjectError, match="invalid"):
        store.reports.asset(first, "report.md", expected_revision=store.info()["revision"],
                            expected_source_sha256=report["source_sha256"])


def test_ordinary_request_identity_and_input_remain_compatible_and_cannot_impersonate_generation(model, workers):
    store, _ = model
    context = capture(model)
    message = store.discussion.add("Ordinary question", message_id=str(uuid4()), context_id=context["id"])
    request = store.requests.create(message["id"], request_id=str(uuid4()),
                                    configuration={"adapter": "controlled", "model": "report-test"})
    assert store.requests.input(request["id"]) == {"context": context, "message": message,
        "configuration": request["configuration"], "prompt_version": "stk.text/1"}
    assert _request_hash(message["id"], request["configuration"], "stk.text/1") == _digest(
        {"message_id": message["id"], "configuration": request["configuration"]})
    done, _ = complete(store, request, workers)
    with pytest.raises(ProjectError, match="dedicated report request"):
        freeze(store, done)
    with pytest.raises(ProjectError, match="only valid for a report request"):
        store.requests.create(message["id"], request_id=str(uuid4()), configuration=request["configuration"],
                              report_selection=selection(store))
    assert store.reports.list()["total"] == 0
