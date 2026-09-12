"""Only declarative ViewSpec data: no host-specific widget or drawing imports."""

def workbench(ctx):
    compact = ctx.surface == "mobile"
    controls = [
        {"kind": "paragraph", "label": "STK · 解析场计算与结果探索"},
        {"kind": "input", "label": "配置名称", "field": "title", "value": "解析场验证"},
        {"kind": "input", "label": "计算连接", "field": "connector", "value": "stk-local"},
        {"kind": "number", "label": "幅度", "field": "amplitude", "value": 1},
        {"kind": "select", "label": "后端", "field": "backend", "value": "local", "options": ["local", "pbs", "slurm"]},
        {"kind": "number", "label": "CPU 数量", "field": "cpus", "value": 1},
        {"kind": "number", "label": "最长运行秒数", "field": "walltime", "value": 120},
        {"kind": "button", "label": "保存计算配置", "action": "stk.configuration.save",
         "bindings": {"title": "title", "connector_id": "connector", "amplitudes": ["amplitude"], "backend": "backend", "cpus": "cpus", "walltime_seconds": "walltime"}},
        {"kind": "input", "label": "已有 Runtime 任务编号", "field": "existing_task", "value": ""},
        {"kind": "button", "label": "收录已有任务", "action": "stk.attach", "bindings": {"connector_id": "connector", "task_id": "existing_task"}},
    ]
    items = [r for r in ctx.resources("configuration,execution") if r["body"].get("engine") in {"stk.analytic-field.v1", "stk.existing-task.v1"}]
    table = {"kind": "table", "label": "项目与任务", "columns": ["名称", "状态", "版本"],
        "rows": [{"resource_id": r["id"], "version": r["version"], "cells": [r["title"], r["body"].get("state", r["body"].get("status", "")), str(r["version"])]} for r in items[:20 if compact else 50]]}
    content = [table]
    selected = ctx.resource
    if selected and selected["body"].get("engine") in {"stk.analytic-field.v1", "stk.existing-task.v1"}:
        body = selected["body"]
        controls.append({"kind": "paragraph", "label": f"{selected['title']} · v{selected['version']}"})
        if selected["type"] == "configuration":
            controls.append({"kind": "button", "label": "提交此配置", "action": "stk.submit", "values": {}, "target_id": selected["id"], "expected_version": selected["version"]})
        if selected["type"] == "execution":
            controls += [
                {"kind": "select", "label": "显示方式", "field": "mode", "value": "slice", "options": ["slice", "iso", "vectors"]},
                {"kind": "number", "label": "切片轴（0/1/2）", "field": "axis", "value": 2},
                {"kind": "number", "label": "切片索引", "field": "index", "value": 1},
                {"kind": "number", "label": "等值面数值", "field": "level", "value": body.get("summary", {}).get("mean", 0)},
                {"kind": "number", "label": "分量索引", "field": "component", "value": 0},
            ]
            for a in body.get("results", []):
                if a["filename"].lower().endswith((".vtk", ".vti")):
                    content.insert(0, {"kind": "scene", "label": a["filename"], "query": "stk.scene",
                        "values": {"resource_id": selected["id"], "version": selected["version"], "artifact": a["filename"], "max_vertices": 5000 if compact else 20000},
                        "bindings": {"mode": "mode", "axis": "axis", "index": "index", "level": "level", "component": "component"}})
            controls.append({"kind": "log", "label": "最近状态：" + body.get("state", "unknown") + " · 更新时间：" + str(body.get("observed_at") or selected["updated_at"])})
    return {"version": 1, "id": "stk.workbench", "title": "STK 科学工作台",
        "layout": [.23, .28, .22, .43], "panels": {"content": content, "inspector": controls}}


def presentations():
    return {"stk.workbench": workbench}
