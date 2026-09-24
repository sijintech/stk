"""MCP adapter for the persistent runtime. Transport remains stdio.

Set STK_RUNTIME_URL/STK_RUNTIME_TOKEN or STK_STATE_DIR. Long operations
return task IDs and never inherit MCP transport lifetimes or timeouts.
"""

import asyncio
import json
import os
import shlex
from typing import Optional

from mcp.server.fastmcp import FastMCP
try:
    from mcp.server.fastmcp import Image
except ImportError:  # older 1.x releases export it only from the utilities module
    from mcp.server.fastmcp.utilities.types import Image
from suan.mcp import graph_tools
from suan.runtime.cli import get_client
from suan.runtime.models import TaskSpec

mcp = FastMCP("stk-toolkit", instructions="Use workspaces and persistent tasks. Submission returns a task ID; query it for completion. Do not infer success from submission.")


@mcp.tool()
async def stk_info() -> dict:
    """Runtime health and API version."""
    return await asyncio.to_thread(get_client().health)


@mcp.tool()
async def create_workspace(name: str) -> dict:
    """Create an isolated input workspace and return its ID."""
    return await asyncio.to_thread(get_client().create_workspace, name)


@mcp.tool()
async def list_workspaces() -> list:
    """List the connected user's workspaces."""
    return await asyncio.to_thread(get_client().workspaces)


@mcp.tool()
async def upload_input(workspace_id: str, local_file: str, remote_path: Optional[str] = None) -> dict:
    """Upload a local MCP-host file with resume and SHA-256 verification."""
    return await asyncio.to_thread(get_client().upload, workspace_id, local_file, remote_path)


@mcp.tool()
async def list_directory(workspace_id: str) -> list:
    """List uploaded workspace inputs and checksums, relative to the workspace."""
    return await asyncio.to_thread(get_client().files, workspace_id)


@mcp.tool()
async def submit_task(spec: dict, idempotency_key: str) -> dict:
    """Submit TaskSpec (workspace_id, argv, backend, inputs, outputs, env, resources).

    Reuse idempotency_key when retrying an uncertain submission. Use {python}
    as the executable to select the runtime's configured Python interpreter.
    """
    return await asyncio.to_thread(get_client().submit, TaskSpec(**spec), idempotency_key)


@mcp.tool()
async def list_tasks(workspace_id: Optional[str] = None) -> list:
    """List durable task records, optionally filtered by workspace."""
    return await asyncio.to_thread(get_client().tasks, workspace_id)


@mcp.tool()
async def get_task(task_id: str) -> dict:
    """Get task state, backend job ID, exit code, reason and input manifest."""
    return await asyncio.to_thread(get_client().task, task_id)


@mcp.tool()
async def cancel_task(task_id: str) -> dict:
    """Request cancellation. Query until a terminal state is observed."""
    return await asyncio.to_thread(get_client().cancel, task_id)


@mcp.tool()
async def get_task_logs(task_id: str, stream: str = "stdout", offset: int = 0) -> dict:
    """Read a bounded log chunk; next_offset is a byte offset for reconnection."""
    chunk = await asyncio.to_thread(get_client().logs, task_id, stream, offset)
    chunk["text"] = chunk.pop("bytes").decode("utf-8", errors="replace")
    return chunk


@mcp.tool()
async def list_artifacts(task_id: str) -> list:
    """List completed task outputs with size, MIME type and SHA-256."""
    return await asyncio.to_thread(get_client().artifacts, task_id)


@mcp.tool()
async def download_artifact(task_id: str, remote_path: str, destination: str) -> str:
    """Download to the MCP host; verify checksum and resume partial downloads."""
    return str(await asyncio.to_thread(get_client().download, task_id, remote_path, destination))


@mcp.tool()
async def run_stk_command(command: str, workspace_id: str, idempotency_key: str, backend: str = "local") -> dict:
    """Submit a legacy sjob/smesh/sviz CLI command as a persistent task.

    This parses arguments only; shell operators are not evaluated. Upload
    required inputs first. Return value is a task record, not stdout.
    """
    argv = shlex.split(command)
    if not argv or argv[0] not in {"sjob", "smesh", "sviz"}:
        raise ValueError("Expected sjob, smesh or sviz")
    spec = TaskSpec(workspace_id, ["{python}", "-m", "suan.cli.main"] + argv, backend=backend)
    return await asyncio.to_thread(get_client().submit, spec, idempotency_key)


@mcp.tool()
async def get_task_events(task_id: str, offset: int = 0, limit: Optional[int] = None) -> dict:
    """Monitoring events of a task (stk-events-v1: progress, metrics, frame, message, run.completed).

    Pass next_offset back as offset to continue; terminal is true once the task
    has ended and every event was read. Progress is not success: check the task
    state and the program's own result record.
    """
    return await asyncio.to_thread(graph_tools.get_task_events, task_id, offset, limit)


@mcp.tool()
async def graph_catalog(family: Optional[str] = None, node_type: Optional[str] = None) -> dict:
    """STK graph node types (compact) and graph presets; node_type returns one full declaration.

    family filters by source, filter, analysis, render, view, output or plot.
    """
    return await asyncio.to_thread(graph_tools.graph_catalog, family, node_type)


@mcp.tool()
async def graph_validate(graph: Optional[dict] = None, preset: Optional[str] = None,
                         parameters: Optional[dict] = None) -> dict:
    """Validate an stk.graph/1 document (or a preset with parameter overrides) without running it.

    Each error has a code, a JSON pointer path, the node and a hint for fixing it.
    """
    return await asyncio.to_thread(graph_tools.graph_validate, graph, preset, parameters)


@mcp.tool()
async def graph_evaluate(graph: Optional[dict] = None, preset: Optional[str] = None, bindings: Optional[dict] = None,
                         parameters: Optional[dict] = None, outputs: Optional[list] = None, profile: str = "web",
                         plot_format: str = "svg", output_dir: Optional[str] = None) -> dict:
    """Evaluate a graph or preset on this host; returns a JSON summary plus local file paths.

    bindings map source binding names to {"task_id": id} (a finished Runtime task)
    or {"dir": path} (a run directory on this host). Tables with few rows are
    inlined; payloads are written as manifest.json + <sha256>.bin.
    """
    return await asyncio.to_thread(graph_tools.graph_evaluate, graph, preset, bindings, parameters, outputs, profile,
                                   plot_format, None, output_dir)


@mcp.tool()
async def graph_render(graph: Optional[dict] = None, preset: Optional[str] = None, bindings: Optional[dict] = None,
                       parameters: Optional[dict] = None, output: Optional[str] = None, width: Optional[int] = None,
                       height: Optional[int] = None, output_dir: Optional[str] = None):
    """Render a graph's image output (or its first scene) offscreen and return the PNG plus a summary.

    Fails with a clear message when this host has no offscreen OpenGL.
    """
    rendered = await asyncio.to_thread(graph_tools.graph_render, graph, preset, bindings, parameters, output, width,
                                       height, output_dir)
    return [Image(data=rendered["png"], format="png"), json.dumps(rendered["summary"], ensure_ascii=False)]


@mcp.tool()
async def plot_table(columns: Optional[dict] = None, y: Optional[list] = None, x: Optional[str] = None,
                     kind: str = "line", units: Optional[dict] = None, title: Optional[str] = None,
                     x_label: Optional[str] = None, y_label: Optional[str] = None, spec: Optional[dict] = None,
                     output_dir: Optional[str] = None):
    """Plot table columns ({name: [values]}) as line, scatter, bar or hist (or render a full stk.plot/1 spec).

    Returns the PNG plus the file paths of the image and of the plotted data.
    Units default to "unspecified"; never guess them.
    """
    rendered = await asyncio.to_thread(graph_tools.plot_table, columns, y, x, kind, units, title, x_label, y_label,
                                       spec, "png", output_dir)
    return [Image(data=rendered["bytes"], format="png"), json.dumps(rendered["summary"], ensure_ascii=False)]


def run_server():
    mcp.run(transport="stdio")
    return 0


if __name__ == "__main__":
    run_server()
