"""Where a probe (a pick on a rendered layer) reads its original data values (standard library only).

A payload layer that supports probing declares ``pick.probe = {"node", "dataset"?}``: the graph node
whose *input data* holds the values under the picked point. :func:`resolve_probe_target` walks the
graph upstream from that node, breadth first, to the first field source:

* ``stk.source.file@1``: its ``binding`` and ``path`` parameters;
* ``stk.source.muferro_frame@1``: the frame file of the resolved step, named
  ``<Dataset>.<step:08d>.dat`` (muFerro's published frame names), found in the bound task's
  ``artifacts`` when given, else under the run's ``case_dir`` (``auto``: the binding root).

The step of a muFerro frame is the graph parameter it references (the evaluated value from
``result["parameters"]`` wins over ``values``), an integer literal, or the node's reported
``<node>.step`` choice. ``origin``/``spacing`` parameters of the source become ``metadata``.

This is the Python port of ``web/src/graph.ts::resolveProbeTarget`` (the web keeps its TypeScript
copy; both follow the same rules and messages). The only addition is the ``binding`` key of a
target, so a caller whose bindings are local directories (the desktop bridge) can resolve the path
itself. Errors are returned, not raised: ``{"error": "<message>"}``.
"""
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


def resolve_probe_target(graph, probe, *, bindings, values=None, result=None, artifacts=None):
    """``{"binding", "task_id", "path", "node", "metadata"?}`` or ``{"error": message}``.

    ``bindings`` maps binding names to task ids (any non-empty string marks a bound name);
    ``values`` are the parameter values the caller sent; ``result`` a ``stk.graph-result/1``
    (its ``parameters`` give the evaluated step); ``artifacts`` the bound task's ``[{"path"}]``.
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

    queue, seen = [probe["node"]], set()
    while queue:
        node_id = queue.pop(0)
        if node_id in seen:
            continue
        seen.add(node_id)
        node = nodes.get(node_id)
        if node is None:
            continue
        node_type = str(node.get("type", ""))
        metadata = {}
        for key in ("origin", "spacing"):
            value = param(node, key)
            if isinstance(value, list) and len(value) == 3:
                metadata[key] = value
        extra = {"metadata": metadata} if metadata else {}
        if node_type.startswith("stk.source.file@"):
            binding, path = param(node, "binding"), param(node, "path")
            task = bound(binding)
            if not task:
                return {"error": f"数据源 {_text(binding)} 尚未绑定任务"}
            if not isinstance(path, str) or not path:
                return {"error": f"节点 {node_id} 缺少文件路径"}
            return {"binding": binding, "task_id": task, "path": path, "node": node_id, **extra}
        if node_type.startswith("stk.source.muferro_frame@"):
            dataset = param(node, "dataset")
            if dataset is None:
                dataset = probe.get("dataset") if probe.get("dataset") is not None else "Polar"
            dataset = _text(dataset)
            ref = (node.get("params") or {}).get("step")
            if _is_param_ref(ref):
                evaluated = _own(_own(result_parameters, ref["$param"]), "value")
                resolved = evaluated if evaluated is not None else _own(values, ref["$param"])
            elif _is_int(ref):
                resolved = ref
            else:
                resolved = _own(_own(result_parameters, f"{node_id}.step"), "value")
            step = int(resolved) if isinstance(resolved, str) and _DIGITS.match(resolved) else resolved
            if not _is_int(step) or step < 0:
                return {"error": "请先完成一次图谱计算以确定探针所在的时间步"}
            run = nodes.get(_linked_node((node.get("inputs") or {}).get("frames")) or "")
            binding = param(run, "binding") if run is not None else None
            task = bound(binding)
            if not task:
                return {"error": f"数据源 {_text(binding if binding is not None else '?')} 尚未绑定任务"}
            # 'auto' (the default): the case directory recorded by the launcher; the published frame names it.
            case_dir = str(param(run, "case_dir") if param(run, "case_dir") is not None else "auto")
            name = f"{dataset}.{step:08d}.dat"
            published = None
            for artifact in artifacts or ():
                match = FRAME.search(str(_own(artifact, "path") or ""))
                if match and match[1] == dataset and int(match[2]) == step:
                    published = artifact["path"]
                    break
            if published is None:
                published = f"{case_dir.rstrip('/')}/{name}" if case_dir and case_dir not in (".", "auto") else name
            return {"binding": binding, "task_id": task, "path": published, "node": node_id, **extra}
        queue.extend(_linked_nodes(node.get("inputs")))
    return {"error": f"从节点 {probe['node']} 向上未找到场数据源"}


def _text(value):
    """JavaScript ``String(value)`` for the values a binding parameter can hold."""
    if value is None:
        return "undefined"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)
