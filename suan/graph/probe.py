"""Resolve original field sources for rendered picks without opening a field.

The desktop bridge binds evaluated MuFerro picks to a resolved source step and verifies the
file against the local run or the bound Runtime task. The target-only resolver retains the
legacy path lookup for callers without an evaluated scene.
"""
from collections import deque
from collections.abc import Mapping
import re

__all__ = ["FRAME", "frame_dataset", "frames_from_artifacts", "resolve_probe_target"]

# muFerro published frame names, as suan/mupro/run.py FRAME and web/src/graph.ts FRAME.
FRAME = re.compile(r"(?:^|/)([A-Za-z][A-Za-z0-9_]{0,7})\.(\d{8})\.dat$")
_DIGITS = re.compile(r"^\d+$")


def _is_param_ref(value):
    return isinstance(value, Mapping) and len(value) == 1 and isinstance(value.get("$param"), str)


def _own(table, key):
    return table.get(key) if isinstance(table, Mapping) and isinstance(key, str) else None


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _linked_node(link):
    if isinstance(link, Mapping) and isinstance(link.get("from"), str):
        return link["from"].split(".")[0]
    return None


def _linked_nodes(inputs):
    found = []
    for value in (inputs or {}).values() if isinstance(inputs, Mapping) else ():
        for link in value if isinstance(value, list) else [value]:
            node = _linked_node(link)
            if node:
                found.append(node)
    return found


def frame_dataset(graph):
    """The dataset of the first muFerro frame source (default ``Polar``), or ``None``."""
    for node in (graph or {}).get("nodes") or ():
        if isinstance(node, Mapping) and str(node.get("type", "")).startswith("stk.source.muferro_frame@"):
            dataset = (node.get("params") or {}).get("dataset")
            return dataset if isinstance(dataset, str) else "Polar"
    return None


def frames_from_artifacts(artifacts, dataset=None):
    """Sorted steps of the frames (of ``dataset`` when given) among ``artifacts`` (``[{"path"}]``)."""
    steps = set()
    for artifact in artifacts or ():
        match = FRAME.search(str(_own(artifact, "path") or ""))
        if match and (not dataset or match[1] == dataset):
            steps.add(int(match[2]))
    return sorted(steps)


def resolve_probe_target(graph, probe, *, bindings, values=None, result=None, artifacts=None, evaluated=False):
    """``{"binding", "task_id", "path", "node", "metadata"?}`` or ``{"error": message}``.

    ``bindings`` maps binding names to task ids (any non-empty string marks a bound name);
    ``values`` are the parameter values the caller sent; ``result`` a ``stk.graph-result/1``
    (its ``parameters`` give the evaluated step); ``artifacts`` the bound task's ``[{"path"}]``.
    For an evaluated pick, the bridge receives the MuFerro frame name, case and node definition
    to resolve against the actual binding.
    """
    if not isinstance(probe, Mapping) or not probe.get("node"):
        return {"error": "该图层未声明探针数据源（pick.probe）"}
    if not isinstance(graph, Mapping) or not isinstance(graph.get("nodes"), list):
        return {"error": "预设未附带图定义，无法定位探针数据"}
    values = values if isinstance(values, Mapping) else {}
    result_parameters = result.get("parameters") if isinstance(result, Mapping) else None
    nodes = {node.get("id"): node for node in graph["nodes"] if isinstance(node, Mapping)}
    defaults = {p.get("name"): p.get("default") for p in graph.get("parameters") or () if isinstance(p, Mapping)}

    def param(node, name):
        value = (node.get("params") or {}).get(name)
        if _is_param_ref(value):
            given = _own(values, value["$param"])
            return given if given is not None else defaults.get(value["$param"])
        return value

    def bound(binding):
        task = _own(bindings, binding)
        return task if isinstance(task, str) and task else None

    sources = []
    queue, seen = deque([probe["node"]]), set()
    while queue:
        node_id = queue.popleft()
        if node_id in seen:
            continue
        seen.add(node_id)
        node = nodes.get(node_id)
        if node is None:
            continue
        node_type = str(node.get("type", ""))
        if node_type.startswith(("stk.source.file@", "stk.source.muferro_frame@")):
            sources.append(node)
            if not evaluated:
                break
        else:
            if evaluated and node_type.startswith("stk.source."):
                sources.append(node)
            queue.extend(_linked_nodes(node.get("inputs")))
    frames = [node for node in sources if str(node.get("type", "")).startswith("stk.source.muferro_frame@")]
    if evaluated and frames and len(sources) > 1:
        return {"error": "无法确定所选图层对应的唯一 MuFerro 场数据源"}
    node = frames[0] if frames else next((n for n in sources if str(n.get("type", "")).startswith("stk.source.file@")), None)
    if node is None:
        return {"error": f"从节点 {probe['node']} 向上未找到场数据源"}
    node_id = node["id"]
    metadata = {}
    for key in ("origin", "spacing"):
        value = param(node, key)
        if isinstance(value, list) and len(value) == 3:
            metadata[key] = value
    extra = {"metadata": metadata} if metadata else {}
    if not frames:
        binding, path = param(node, "binding"), param(node, "path")
        task = bound(binding)
        if not task:
            return {"error": f"数据源 {_text(binding)} 尚未绑定任务"}
        if not isinstance(path, str) or not path:
            return {"error": f"节点 {node_id} 缺少文件路径"}
        return {"binding": binding, "task_id": task, "path": path, "node": node_id, **extra}

    ref = (node.get("params") or {}).get("step")
    step = _own(_own(result_parameters, f"{node_id}.step"), "value")
    if step is None and _is_param_ref(ref):
        name = ref["$param"]
        shared = evaluated and any(other is not node and (other.get("params") or {}).get("step") == ref
                                   for other in nodes.values())
        if not shared:
            step = _own(_own(result_parameters, name), "value")
        if step is None and not evaluated:
            step = _own(values, name)
    elif step is None and not evaluated and _is_int(ref):
        step = ref
    if not evaluated and isinstance(step, str) and _DIGITS.match(step):
        step = int(step)
    if not _is_int(step) or step < 0:
        return {"error": "无法确定所选图层实际使用的 MuFerro 时间步"}
    run = nodes.get(_linked_node((node.get("inputs") or {}).get("frames")) or "")
    if evaluated and (not run or not str(run.get("type", "")).startswith("stk.source.muferro_run@")):
        return {"error": "无法确定 MuFerro 帧所属的计算数据源"}
    binding = param(run, "binding") if run is not None else None
    task = bound(binding)
    if not task:
        return {"error": f"数据源 {_text(binding if binding is not None else '?')} 尚未绑定任务"}
    dataset = param(node, "dataset")
    if dataset is None:
        dataset = "Polar" if evaluated else probe.get("dataset") or "Polar"
    case_dir = param(run, "case_dir") if run is not None else None
    case_dir = case_dir if case_dir is not None else "auto"
    name = f"{dataset}.{step:08d}.dat"
    target = {"binding": binding, "task_id": task, "node": node_id, **extra}
    if evaluated:
        if not isinstance(dataset, str) or not isinstance(case_dir, str) or "/" in name or FRAME.fullmatch(name) is None:
            return {"error": "无法确定 MuFerro 算例目录或场文件名"}
        return {**target, "frame": name, "case_dir": case_dir, "frame_node": node}
    for artifact in artifacts or ():
        match = FRAME.search(str(_own(artifact, "path") or ""))
        if match and match[1] == dataset and int(match[2]) == step:
            return {**target, "path": artifact["path"]}
    case_dir = str(case_dir)
    return {**target, "path": f"{case_dir.rstrip('/')}/{name}" if case_dir and case_dir not in (".", "auto") else name}


def published_muferro_frame(name, case_dir, artifacts):
    """Exact explicit case path, or the only published path matching the resolved auto-case frame."""
    from suan.connectors.mupro import case_prefix

    paths = {path for item in artifacts if isinstance((path := _own(item, "path")), str)}
    if case_dir != "auto":
        path = case_prefix(case_dir) + name
        if path in paths:
            return path
    else:
        matches = {path for path in paths if path.rsplit("/", 1)[-1] == name}
        if len(matches) == 1:
            return matches.pop()
        if len(matches) > 1:
            raise ValueError("此任务发布了多个同名 MuFerro 帧，无法确定图层使用的文件")
    raise ValueError("此任务未发布与所选图层匹配的 MuFerro 帧")


def _text(value):
    """JavaScript ``String(value)`` for the values a binding parameter can hold."""
    if value is None:
        return "undefined"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)
