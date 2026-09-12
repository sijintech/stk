"""STK postprocessing runs in the server plugin, never in a GUI process."""
from pathlib import Path
from copy import deepcopy
from functools import lru_cache
import json

from synorder_interaction.assets import blob_path
from synorder_interaction.contracts import InteractionError, Query, Unavailable, object_schema, canonical

SOURCE = {
    "resource_id": {"type": "string", "minLength": 1, "maxLength": 128},
    "version": {"type": "integer", "minimum": 1},
    "artifact": {"type": "string", "minLength": 1, "maxLength": 256},
}


def source_file(ctx, values):
    # Resolve authorization before even importing the optional scientific stack.
    obj = ctx.store.resource(ctx.actor, values["resource_id"], version=values["version"])
    if obj["space_id"] != ctx.space_id:
        raise PermissionError("科学结果不属于当前空间")
    item = next((a for a in obj["body"].get("results", []) if a["filename"] == values["artifact"]), None)
    if item is None:
        raise InteractionError("此版本没有所选结果文件")
    suffix = Path(item["filename"]).suffix.lower()
    if suffix not in {".vtk", ".vti"}:
        raise InteractionError("请选择 VTK 或 VTI 规则场数据")
    path = blob_path(ctx.store, item["sha256"])
    if path.stat().st_size > 16 * 1024 * 1024:
        raise InteractionError("当前显示源文件预算为 16 MiB；较大数据请先在执行节点后处理")
    metadata = {"units": "无量纲", "coordinate_units": "无量纲", "timestep": 0} if obj["body"].get("engine") == "stk.analytic-field.v1" else {}
    source = {**{k: values[k] for k in SOURCE}, "sha256": item["sha256"], "probe_query": "stk.probe"}
    return path, suffix, metadata, source


def load(path, suffix, metadata):
    try:
        from suan.visualization.scene import load_grid
        return load_grid(path, file_format=suffix, **metadata)
    except ImportError:
        raise Unavailable("服务端需要安装 STK 的科学可视化依赖") from None


@lru_cache(maxsize=8)
def derived_scene(path, suffix, sha, metadata, options):
    grid = load(path, suffix, json.loads(metadata))
    from suan.visualization.scene import build_scene
    from synorder_gui.scene import validate_scene
    return validate_scene(build_scene(grid, dataset_id=sha, **json.loads(options)))


def scene(ctx, values):
    # Authorize each read before consulting the bounded immutable display cache.
    path, suffix, metadata, source = source_file(ctx, values)
    result = deepcopy(derived_scene(str(path), suffix, source["sha256"], canonical(metadata), canonical({k: v for k, v in values.items() if k not in SOURCE})))
    result["manifest"]["source"] = source
    return result


def probe(ctx, values):
    path, suffix, metadata, source = source_file(ctx, values)
    grid = load(path, suffix, metadata)
    from suan.visualization.scene import probe as sample
    return {**sample(grid, values["position"]), "source_resource": source}


def queries():
    return (
        Query("stk.scene", object_schema({**SOURCE,
            "mode": {"enum": ["slice", "iso", "vectors"]},
            "axis": {"type": "integer", "minimum": 0, "maximum": 2},
            "index": {"type": "integer", "minimum": 0},
            "component": {"type": "integer", "minimum": 0, "maximum": 15},
            "level": {"type": "number"},
            "max_vertices": {"type": "integer", "minimum": 100, "maximum": 40000},
        }, required=list(SOURCE)), scene),
        Query("stk.probe", object_schema({**SOURCE, "position": {
            "type": "array", "minItems": 3, "maxItems": 3, "items": {"type": "number"},
        }}), probe),
    )
