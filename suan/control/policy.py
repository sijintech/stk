"""Only registered exact command templates can bypass review."""
import re
from suan.runtime.models import TaskSpec, relative_path

KINDS = {"workspace.create", "task.submit", "task.cancel", "task.logs", "task.artifacts",
         "file.read", "view.build", "view.probe"}
DEMO_TEMPLATE = {"argv": ["@python", "-m", "suan.control.demo_job"],
                 "outputs": ["scalar-0.vti", "scalar-1.vti", "vector.vti"]}


def validate_action(body, templates):
    if set(body) - {"id", "node_id", "kind", "payload"}:
        raise ValueError("Unknown action property")
    for key in ("id", "node_id"):
        if not isinstance(body.get(key), str) or not re.fullmatch(r"[a-f0-9]{32}", body[key]):
            raise ValueError("Action and node IDs must be 32 lowercase hexadecimal characters")
    if body.get("kind") not in KINDS or not isinstance(body.get("payload"), dict):
        raise ValueError("Unknown action kind or invalid payload")
    p = body["payload"]
    kind = body["kind"]
    if kind == "workspace.create":
        if set(p) != {"name"} or not isinstance(p["name"], str) or not 1 <= len(p["name"].strip()) <= 200:
            raise ValueError("Workspace name is required")
    if kind in {"task.cancel", "task.logs", "task.artifacts", "file.read", "view.build", "view.probe"}:
        if not re.fullmatch(r"[a-f0-9]{32}", str(p.get("task_id", ""))):
            raise ValueError("Task ID required")
    if kind in {"file.read", "view.build", "view.probe"}:
        relative_path(p.get("path"))
    if kind != "task.submit":
        return ""
    if set(p) - {"spec", "template"}:
        raise ValueError("Unknown submission property")
    spec = TaskSpec(**p.get("spec", {})).to_dict()
    template = templates.get(p.get("template"))
    r = spec["resources"]
    high = (r.get("cpus", 1) > 8 or r.get("nodes", 1) > 1 or r.get("gpus", 0) > 0
            or r.get("memory_mb", 0) > 16384 or r.get("walltime_seconds", 0) > 3600)
    if high:
        return "资源请求超过自动执行额度，请检查 CPU、内存、时长与 GPU。"
    if not template or spec["argv"] != template["argv"] or spec["outputs"] != template["outputs"] or spec["env"]:
        return "新命令或模板变更：请检查完整参数后批准执行。"
    return ""
