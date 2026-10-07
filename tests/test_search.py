"""One project search over names and text, read-only, grouped by kind with navigation targets."""
from uuid import uuid4

import pytest

from suan.project import ProjectError
from suan.project.search import search
from test_bridge_workflow_runs import analysis_document, setup  # noqa: F401
from test_desktop_bridge import bridge_env, inproc  # noqa: F401
from test_project_contexts import capture, model  # noqa: F401


def test_names_cells_and_messages_are_found_case_insensitively_without_changing_anything(model):
    store, ids = model
    store.apply([{"op": "set_cell", "table_id": ids["table"], "record_id": ids["second"], "field_id": ids["note"],
                  "value": "Thin FILM on a substrate; annealed at 600 K before the run"}], expected_revision=store.info()["revision"])
    context = capture(model)
    store.discussion.add("Why is the film thinner?", message_id=str(uuid4()), context_id=context["id"])
    store.drafts.save([{"op": "set_cell", "table_id": ids["table"], "record_id": ids["first"], "field_id": ids["temperature"],
                        "value": 320}], expected_revision=store.info()["revision"], title="Film temperature", draft_id=str(uuid4()))
    before, history = store.snapshot(), store.history()
    found = search(store, "  film ")
    assert store.snapshot() == before and store.history() == history
    assert found["query"] == "film" and not found["truncated"]
    assert [item["kind"] for item in found["results"]] == ["cell", "draft", "message"]
    cell, draft, message = found["results"]
    assert cell["table"] == "Cases" and cell["name"] == "note" and cell["row"] == 2
    assert cell["text"] == "Thin FILM on a substrate; annealed at 600 K before the run"
    assert cell["target"] == {"page": "data", "table_id": ids["table"], "record_id": ids["second"]}
    assert draft["name"] == "Film temperature" and draft["status"] == "pending" and draft["target"]["page"] == "review"
    assert message["role"] == "user" and message["text"] == "Why is the film thinner?"
    assert [item["kind"] for item in search(store, "TEMPERATURE")["results"]] == ["field", "draft"]
    assert search(store, "cases")["results"][0] == {"kind": "table", "id": ids["table"], "name": "Cases",
                                                    "target": {"page": "data", "table_id": ids["table"]}}
    assert search(store, "nothing like this")["results"] == []
    for bad in ("", "   ", "x" * 201, None):
        with pytest.raises(ProjectError):
            search(store, bad)
    with pytest.raises(ProjectError):
        search(store, "film", limit=0)


def test_long_text_is_cut_around_the_match_and_results_are_bounded(model):
    store, ids = model
    long_text = "a" * 300 + " needle " + "b" * 300
    commands = [{"op": "set_cell", "table_id": ids["table"], "record_id": ids["first"], "field_id": ids["note"], "value": long_text}]
    store.apply(commands, expected_revision=store.info()["revision"])
    (item,) = search(store, "NEEDLE")["results"]
    assert "needle" in item["text"] and item["text"].startswith("…") and item["text"].endswith("…")
    assert len(item["text"]) <= 82
    rows = [{"op": "add_record", "id": str(uuid4()), "table_id": ids["table"]} for _ in range(60)]
    store.apply(rows, expected_revision=store.info()["revision"])
    store.apply([{"op": "set_cell", "table_id": ids["table"], "record_id": row["id"], "field_id": ids["note"], "value": "same"}
                 for row in rows], expected_revision=store.info()["revision"])
    found = search(store, "same", limit=20)
    assert len(found["results"]) == 20 and found["counts"]["cell"] == 60 and found["truncated"]
    assert len(search(store, "same", limit=200)["results"]) == 50  # at most 50 of one kind


def test_workflows_analyses_and_files_are_found_through_the_bridge(setup, tmp_path):
    h, store, ids, handle, worker = setup
    field = store.directory / "case-1" / "field.vtk"
    field.parent.mkdir()
    field.write_text("not read\n")
    store.files.index([str(field)], expected_revision=store.info()["revision"])
    (workflow,) = h.call("project.search", {"handle": handle, "query": "SCAN"})["results"]
    assert workflow == {"kind": "workflow", "id": ids["workflow"], "name": "Scan",
                        "target": {"editor": "workflow", "workflow_id": ids["workflow"]}}
    (analysis,) = h.call("project.search", {"handle": handle, "query": "measure"})["results"]
    assert analysis["target"] == {"editor": "analysis_graph", "analysis_id": ids["analysis"]}
    (indexed,) = h.call("project.search", {"handle": handle, "query": "case-1"})["results"]
    assert indexed["kind"] == "file" and indexed["name"] == "field.vtk" and indexed["text"].endswith("field.vtk")
    assert indexed["target"]["page"] == "files"
    found = h.call("project.search", {"handle": handle, "query": "t", "limit": 5})
    assert found["revision"] == store.info()["revision"] and len(found["results"]) <= 5
    assert not h.violations
