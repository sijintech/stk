---
title: Adding MCP task tools
description: Extend the shared runtime without coupling computations to MCP
---

MCP tools in `suan/mcp/server.py` are thin asynchronous adapters to
`suan.runtime.client.RuntimeClient`. Keep computations in Qt-free toolkit
functions or standalone programs and execute them as TaskSpecs.

```python
@mcp.tool()
async def submit_analysis(workspace_id: str, idempotency_key: str) -> dict:
    spec = TaskSpec(workspace_id, ["{python}", "analysis.py"],
                    outputs=["summary.json"])
    return await asyncio.to_thread(get_client().submit, spec, idempotency_key)
```

Upload `analysis.py` and its inputs before submission. Return the task record
immediately. Do not start a blocking shell command inside an MCP request. Use
runtime logs, cancellation and artifacts so desktop, CLI and AI share the same
state. Reuse the caller's idempotency key on retries.

The stdio adapter registers explicit tools using `@mcp.tool()`; automatic CLI
reflection is no longer used. Test new adapters with `tests/test_mcp.py` and run
the relevant runtime/scientific tests. Protocol and deployment details are in
repository `docs/runtime.md`.
