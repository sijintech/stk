"""MCP adapter for the persistent runtime. Transport remains stdio.

Set STK_RUNTIME_URL/STK_RUNTIME_TOKEN or STK_STATE_DIR. Long operations
return task IDs and never inherit MCP transport lifetimes or timeouts.
"""

import asyncio
import os
import shlex
from typing import Optional

from mcp.server.fastmcp import FastMCP
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


def run_server():
    mcp.run(transport="stdio")
    return 0


if __name__ == "__main__":
    run_server()
