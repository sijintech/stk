"""Desktop auto-run policy (WP11): the expected-transfer cap, writes, other profiles, import paths.

Pure policy (no FastAPI, no NumPy): ``validate_action(..., desktop_bytes=cap)`` is what the hub calls
for a client device paired with ``profile: "desktop"``; every other requester passes ``None``.
"""
import copy
import uuid

import pytest

from suan.control.policy import (DESKTOP_AUTO_BYTES, GRAPH_REVIEW, IMPORT_MAX_FILES, IMPORT_REVIEW, import_path,
                                 validate_action, validate_workspace_import)
from test_control_graph import muferro_graph

TASK = "d" * 32
NODE = "c" * 32
WORKSPACE = "b" * 32
MIB = 1024 * 1024
DIGEST = "a" * 64


def action(kind, payload):
    return {"id": uuid.uuid4().hex, "node_id": NODE, "kind": kind, "payload": payload}


def evaluate(payload, desktop_bytes=None):
    return validate_action(action("graph.evaluate", payload), {}, desktop_bytes=desktop_bytes)


def request(**change):
    return {"graph": muferro_graph(), "bindings": {"run": {"task_id": TASK}}, "outputs": ["payload", "energy"],
            **change}


def test_default_cap_is_256_mib():
    assert DESKTOP_AUTO_BYTES == 256 * MIB


# ---------------------------------------------------------------------------
# Under and over the cap


@pytest.mark.parametrize("change", [
    {"profile": "desktop", "budget": {"max_output_bytes": 64 * MIB}},
    {"profile": "desktop", "budget": {"max_output_bytes": DESKTOP_AUTO_BYTES}},  # the cap itself is allowed
    {"profile": "web"},  # 128 MiB default delivery limit
    {"profile": "phone", "budget": {"max_output_bytes": 200 * MIB}},  # over the ordinary 128 MiB, under the cap
])
def test_desktop_under_the_cap_runs_without_review(change):
    assert evaluate(request(**change), DESKTOP_AUTO_BYTES) == ""


def test_desktop_payload_profile_and_counts_under_the_cap_run_without_review():
    graph = muferro_graph()
    graph["nodes"][8]["params"] = {"profile": "desktop", "budget": {"voxels": 512 ** 3, "triangles": 10_000_000,
                                                                    "bytes": 200 * MIB}}
    payload = request(graph=graph, profile="desktop", budget={"max_output_bytes": 200 * MIB})
    assert evaluate(payload, DESKTOP_AUTO_BYTES) == ""
    # The same request from any other client is reviewed as before.
    reason = evaluate(payload)
    assert reason.startswith(GRAPH_REVIEW)
    assert all(why in reason for why in ("输出大小", "桌面级结果配置", "桌面级渲染数据包", "渲染数据包预算"))


@pytest.mark.parametrize("change", [
    {"profile": "desktop"},  # no max_output_bytes: the desktop profile delivers up to 2 GiB
    {"profile": "desktop", "budget": {"max_output_bytes": DESKTOP_AUTO_BYTES + 1}},
    {"profile": "desktop", "budget": {"max_output_bytes": None}},  # unlimited
    {"profile": "web", "budget": {"max_output_bytes": 1024 * MIB}},
])
def test_desktop_over_the_cap_goes_to_review(change):
    reason = evaluate(request(**change), DESKTOP_AUTO_BYTES)
    assert reason.startswith(GRAPH_REVIEW) and "预计传输超过桌面自动执行上限 256 MiB" in reason


def test_desktop_payload_budget_over_the_cap_goes_to_review():
    graph = muferro_graph()
    graph["nodes"][8]["params"] = {"profile": "desktop", "budget": {"bytes": 300 * MIB}}
    reason = evaluate(request(graph=graph, profile="desktop", budget={"max_output_bytes": 64 * MIB}),
                      DESKTOP_AUTO_BYTES)
    assert "渲染数据包预算" in reason
    graph["nodes"][8]["params"] = {"profile": "desktop", "budget": {"voxels": 2048 ** 3}}  # over the desktop counts
    assert "渲染数据包预算" in evaluate(request(graph=graph, profile="desktop",
                                               budget={"max_output_bytes": 64 * MIB}), DESKTOP_AUTO_BYTES)


def test_the_cap_is_configurable():
    payload = request(profile="desktop", budget={"max_output_bytes": 400 * MIB})
    assert "预计传输" in evaluate(payload, DESKTOP_AUTO_BYTES)
    assert evaluate(payload, 512 * MIB) == ""
    small = evaluate(request(profile="web"), 64 * MIB)  # the web default (128 MiB) exceeds a 64 MiB cap
    assert "预计传输超过桌面自动执行上限 64 MiB" in small
    # 0 (and nonsense) turns desktop auto-run off: the ordinary rules apply.
    for off in (0, None, True, "256"):
        assert "桌面级结果配置" in evaluate(request(profile="desktop", budget={"max_output_bytes": MIB}), off)


def test_desktop_keeps_the_time_image_and_unknown_node_limits():
    cheap = {"max_output_bytes": 64 * MIB}
    assert "计算时长" in evaluate(request(profile="desktop", budget={**cheap, "max_seconds": 3600}),
                                  DESKTOP_AUTO_BYTES)
    graph = muferro_graph()
    graph["nodes"][10]["params"] = {"width": 8000, "height": 8000, "magnification": 2}
    assert "图像像素" in evaluate(request(graph=graph, profile="desktop", budget=cheap), DESKTOP_AUTO_BYTES)
    graph = muferro_graph()
    graph["nodes"].append({"id": "private", "type": "lab.private.filter@1", "inputs": {"in": {"from": "polar.out"}}})
    assert "未安装的节点类型" in evaluate(request(graph=graph, profile="desktop", budget=cheap), DESKTOP_AUTO_BYTES)


# ---------------------------------------------------------------------------
# Writes and other kinds


def test_writes_and_new_commands_are_reviewed_for_desktop_devices():
    files = [{"path": "inputs/a.dat", "sha256": DIGEST, "size": 3}]
    for desktop in (None, DESKTOP_AUTO_BYTES):
        assert validate_action(action("workspace.import", {"workspace_id": WORKSPACE, "files": files}), {},
                               desktop_bytes=desktop) == IMPORT_REVIEW
        spec = {"workspace_id": WORKSPACE, "argv": ["@python", "-c", "print(1)"]}
        assert validate_action(action("task.submit", {"spec": spec}), {}, desktop_bytes=desktop).startswith("新命令")
        template = {"argv": ["@python", "-c", "print(1)"], "outputs": ["out.txt"]}
        templated = {"spec": {**template, "workspace_id": WORKSPACE, "name": "echo"}, "template": "echo"}
        assert validate_action(action("task.submit", templated), {"echo": template}, desktop_bytes=desktop) == ""


@pytest.mark.parametrize("kind, payload", [
    ("task.logs", {"task_id": TASK, "stream": "stdout", "offset": 0}),
    ("task.events", {"task_id": TASK, "offset": 0}),
    ("task.artifacts", {"task_id": TASK}),
    ("file.read", {"task_id": TASK, "path": "out/a.vti", "offset": 0}),
    ("file.read", {"workspace_id": WORKSPACE, "path": "inputs/a.dat"}),
    ("workspace.files", {"workspace_id": WORKSPACE}),
    ("view.probe", {"task_id": TASK, "path": "a.vti", "position": [0, 0, 0]}),
    ("graph.meta", {"include": ["catalog"]}),
    ("graph.cancel", {"action_id": "e" * 32}),
])
def test_reads_run_without_review_for_everyone(kind, payload):
    for desktop in (None, DESKTOP_AUTO_BYTES):
        assert validate_action(action(kind, copy.deepcopy(payload)), {}, desktop_bytes=desktop) == ""


@pytest.mark.parametrize("kind, payload", [
    ("file.read", {"path": "a"}),
    ("file.read", {"task_id": TASK, "workspace_id": WORKSPACE, "path": "a"}),
    ("file.read", {"task_id": TASK, "path": "../a"}),
    ("file.read", {"task_id": TASK, "path": "a", "offset": -1}),
    ("workspace.files", {"workspace_id": "x"}),
    ("workspace.files", {"workspace_id": WORKSPACE, "extra": 1}),
    ("graph.cancel", {"action_id": "E" * 32}),
    ("graph.cancel", {}),
])
def test_invalid_read_payloads_are_refused(kind, payload):
    with pytest.raises(ValueError):
        validate_action(action(kind, payload), {})


def test_non_desktop_profiles_are_unchanged():
    """Every graph request is judged exactly as before when the requester is not a desktop device."""
    cases = [request(), request(profile="phone"), request(profile="desktop"),
             request(budget={"max_output_bytes": 512 * MIB}), request(budget={"max_seconds": 3600}),
             request(profile="desktop", budget={"max_output_bytes": MIB})]
    for payload in cases:
        before = evaluate(copy.deepcopy(payload))
        assert evaluate(copy.deepcopy(payload), None) == before
        assert evaluate(copy.deepcopy(payload), 0) == before
    assert evaluate(request()) == ""
    assert "桌面级结果配置" in evaluate(request(profile="desktop", budget={"max_output_bytes": MIB}))


# ---------------------------------------------------------------------------
# Import paths (path traversal) and limits


@pytest.mark.parametrize("path", [
    "../escape", "a/../../b", "a/..", "/etc/passwd", "~/x", "C:/x", "c:x", "a\\b", "a//b", "./a", "a/./b", "a/",
    ".", "", "a\x00b", "a\nb", "a\x7fb", "x" * 256, "/".join(["d"] * 600),
])
def test_import_paths_are_confined(path):
    if path == "~/x":
        assert import_path(path) == path  # a literal file name, still inside the workspace
        return
    with pytest.raises(ValueError):
        import_path(path)


def test_import_accepts_normal_nested_and_unicode_paths():
    for path in ("a.dat", "inputs/中文 数据.bin", "deep/er/file.txt", ".hidden"):
        assert import_path(path) == path


@pytest.mark.parametrize("files", [
    [],
    [{"path": "a", "sha256": DIGEST, "size": 1}, {"path": "a", "sha256": DIGEST, "size": 1}],  # duplicate
    [{"path": "a", "sha256": DIGEST, "size": 1}, {"path": "a/b", "sha256": DIGEST, "size": 1}],  # file vs folder
    [{"path": "a", "sha256": "A" * 64, "size": 1}],
    [{"path": "a", "sha256": DIGEST, "size": -1}],
    [{"path": "a", "sha256": DIGEST, "size": True}],
    [{"path": "a", "sha256": DIGEST}],
    [{"path": "a", "sha256": DIGEST, "size": 1, "mode": "0777"}],
    [{"path": "../a", "sha256": DIGEST, "size": 1}],
    [{"path": "a", "sha256": DIGEST, "size": 1}] * 2,
])
def test_invalid_imports_are_refused(files):
    with pytest.raises(ValueError):
        validate_workspace_import({"workspace_id": WORKSPACE, "files": files})


def test_import_file_count_is_limited():
    files = [{"path": f"f{i}", "sha256": DIGEST, "size": 0} for i in range(IMPORT_MAX_FILES + 1)]
    with pytest.raises(ValueError, match=f"1 to {IMPORT_MAX_FILES} files"):
        validate_workspace_import({"workspace_id": WORKSPACE, "files": files})
    assert validate_workspace_import({"workspace_id": WORKSPACE, "files": files[:IMPORT_MAX_FILES]}) == IMPORT_REVIEW
    with pytest.raises(ValueError):
        validate_workspace_import({"workspace_id": WORKSPACE, "files": files[:1], "overwrite": True})
