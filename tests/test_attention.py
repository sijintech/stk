"""One "needs attention" summary: failures first, then reviews, running and finished work, with viewed marks."""
from uuid import uuid4

import pytest

from suan.project import ProjectStore
from suan.project.attention import collect
from test_bridge_workflow_runs import analysis_document, setup  # noqa: F401
from test_project_contexts import capture, model  # noqa: F401
from test_desktop_bridge import bridge_env, inproc  # noqa: F401


def finish(store, run_id, row, outcome, executor):
    for step in ("simulate", "measure"):
        attempt = store.workflow_runs.begin_attempt(run_id, step, row, executor_id=executor)
        status = outcome if step == "simulate" else "succeeded"
        store.workflow_runs.finish_attempt(run_id, step, row, attempt, status, executor_id=executor,
                                           error={"code": "solver_failed", "message": "No field"} if status == "failed" else None)
        if status == "failed":
            return


def test_failures_reviews_running_and_finished_work_in_one_ordered_list(setup):
    h, store, ids, handle, worker = setup
    executor = str(uuid4())
    revision = store.info()["revision"]
    # A finished workflow run, a failed one and one still running (claimed by a phantom executor).
    done = store.workflow_runs.prepare(ids["workflow"], [ids["rows"][0]], run_id=str(uuid4()), expected_revision=revision)
    store.workflow_runs.start(done["id"], executor_id=executor)
    finish(store, done["id"], ids["rows"][0], "succeeded", executor)
    store.workflow_runs.stop(done["id"], executor_id=executor)
    failed = store.workflow_runs.prepare(ids["workflow"], [ids["rows"][1]], run_id=str(uuid4()), expected_revision=revision)
    store.workflow_runs.start(failed["id"], executor_id=executor)
    finish(store, failed["id"], ids["rows"][1], "failed", executor)
    store.workflow_runs.stop(failed["id"], executor_id=executor)
    running = store.workflow_runs.prepare(ids["workflow"], [ids["rows"][2]], run_id=str(uuid4()), expected_revision=revision)
    store.workflow_runs.start(running["id"], executor_id=str(uuid4()))
    # A draft waiting for review.
    draft = str(uuid4())
    store.drafts.save([{"op": "set_cell", "table_id": ids["cases"], "record_id": ids["rows"][0],
                        "field_id": ids["temperature"], "value": 310}],
                      expected_revision=store.info()["revision"], title="Warmer first case", draft_id=draft)
    before, history = store.snapshot(), store.history()
    answer = h.call("project.attention.list", {"handle": handle})
    assert store.snapshot() == before and store.history() == history  # read-only
    order = [(item["kind"], item["group"], item["severity"]) for item in answer["items"]]
    assert order == [("workflow_run", "needs_you", "failure"), ("draft", "needs_you", "review"),
                     ("workflow_run", "running", "progress"), ("workflow_run", "done", "info")]
    first = answer["items"][0]
    assert first["id"] == failed["id"] and first["name"] == "Scan" and first["counts"] == {"failed": 1, "pending": 1}
    assert first["target"] == {"editor": "workflow", "workflow_id": ids["workflow"], "run_id": failed["id"]}
    assert answer["items"][1]["name"] == "Warmer first case" and answer["items"][1]["target"]["page"] == "review"
    assert answer["counts"] == {"needs_you": 2, "running": 1, "unviewed_done": 1}
    # Viewing is personal and outside the project; a new failure of the same run shows again.
    keys = [item["key"] for item in answer["items"]]
    assert h.call("project.attention.viewed", {"handle": handle, "keys": keys}) == {"viewed": 4}
    assert store.snapshot() == before
    seen = h.call("project.attention.list", {"handle": handle})
    assert all(item["viewed"] for item in seen["items"]) and seen["counts"] == {"needs_you": 0, "running": 1, "unviewed_done": 0}
    store.workflow_runs.start(failed["id"], executor_id=executor)
    attempt = store.workflow_runs.begin_attempt(failed["id"], "simulate", ids["rows"][1], executor_id=executor)
    store.workflow_runs.finish_attempt(failed["id"], "simulate", ids["rows"][1], attempt, "interrupted", executor_id=executor)
    store.workflow_runs.stop(failed["id"], executor_id=executor)
    again = h.call("project.attention.list", {"handle": handle})
    assert [item["viewed"] for item in again["items"] if item["id"] == failed["id"]] == [False]
    assert not h.violations


def test_analysis_runs_of_workflow_runs_are_shown_through_their_workflow_run(setup):
    h, store, ids, handle, worker = setup
    run = h.call("project.workflow_runs.prepare", {"handle": handle, "workflow_id": ids["workflow"], "rows": [ids["rows"][0]],
                 "run_id": str(uuid4()), "expected_revision": store.info()["revision"]})["run"]
    h.call("project.workflow_runs.start", {"handle": handle, "run_id": run["id"]})
    from test_bridge_workflow_runs import settled
    settled(h, handle, run["id"])
    items = h.call("project.attention.list", {"handle": handle})["items"]
    assert [(item["kind"], item["group"]) for item in items] == [("workflow_run", "done")]
    assert len(store.analysis_runs.list()["runs"]) == 1  # it exists, but is not listed twice


def test_an_empty_or_older_project_has_nothing_to_attend(inproc, tmp_path):
    store = ProjectStore.create(tmp_path / "empty", "Empty")
    h = inproc()
    handle = h.call("project.open", {"directory": str(store.directory)})["project"]["handle"]
    assert h.call("project.attention.list", {"handle": handle}) == {
        "revision": 0, "items": [], "counts": {"needs_you": 0, "running": 0, "unviewed_done": 0}}
    with pytest.raises(Exception):
        h.call("project.attention.viewed", {"handle": handle, "keys": []})  # at least one key


def test_simulation_runs_and_ai_requests_by_state(model):
    store, ids = model
    spec = {"workspace_id": "a" * 32, "argv": ["{python}", "-c", "pass"]}
    runs = store.runs.prepare([{"table_id": ids["table"], "record_id": ids[row], "spec": spec, "label": label}
                               for row, label in (("first", "failed"), ("second", "running"), ("first", "done"), ("second", "idle"))],
                              connection="runtime:Test", connection_identity="a" * 16, expected_revision=store.info()["revision"])["run_ids"]
    store.runs.observe(runs[0], {"submission": "accepted", "task": {"id": "t0", "state": "failed"}})
    store.runs.observe(runs[1], {"submission": "accepted", "task": {"id": "t1", "state": "queued"}})
    store.runs.observe(runs[2], {"submission": "accepted", "task": {"id": "t2", "state": "succeeded"}})
    context = capture((store, ids))
    requests = []
    for _ in range(3):
        message = store.discussion.add("check", message_id=str(uuid4()), context_id=context["id"])
        requests.append(store.requests.create(message["id"], request_id=str(uuid4()),
                                              configuration={"adapter": "controlled/1", "model": "text-fixture"})["id"])
    owner = str(uuid4())
    store.requests._claim(requests[0], executor_id=owner)
    store.requests._settle(requests[0], executor_id=owner, status="failed", code="adapter_failed")
    store.requests._claim(requests[2], executor_id=owner)
    store.requests._complete(requests[2], executor_id=owner, text="ok")
    items = collect(store)["items"]
    summary = sorted((item["kind"], item["group"], item["status"]) for item in items)
    assert summary == [("request", "done", "completed"), ("request", "needs_you", "failed"), ("request", "running", "pending"),
                       ("simulation_run", "done", "succeeded"), ("simulation_run", "needs_you", "failed"),
                       ("simulation_run", "running", "queued")]
    failed = next(item for item in items if item["kind"] == "request" and item["group"] == "needs_you")
    assert failed["error"] == "adapter_failed" and failed["target"] == {"page": "conversation", "request_id": requests[0]}
    assert [item["group"] for item in items] == ["needs_you"] * 2 + ["running"] * 2 + ["done"] * 2
