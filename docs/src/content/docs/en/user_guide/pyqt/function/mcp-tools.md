---
title: MCP persistent tasks
description: Use the local and remote STK runtime through MCP
---

In STK 0.1.0a1, the MCP adapter uses **stdio** and calls a separate runtime over
HTTP. Submitted computations outlive the MCP client connection.

## Install and connect

From the repository root:

```bash
python -m pip install '.[server,science,mcp]'
suan server init
suan server start
python -m suan.mcp
```

Configure your MCP client to launch the installed environment's absolute Python
path with arguments `["-m", "suan.mcp"]`. Set `STK_STATE_DIR` to the local runtime
state directory. For a remote runtime, establish an SSH tunnel and set
`STK_RUNTIME_URL` to its local forwarded endpoint and `STK_RUNTIME_TOKEN` to the
server token. Keep the token in private user configuration.

MCP does not serve HTTP on port 8000. The separate runtime defaults to loopback
port 8765 and authenticates every API request with a bearer token.

## Workflow

1. Create a workspace with `create_workspace`; transfer inputs with `upload_input`.
2. Submit `submit_task(spec, idempotency_key)` and retain the returned task ID.
3. Poll `get_task`; use `get_task_logs` with byte offsets to resume log reads.
4. On completion, use `list_artifacts` and `download_artifact` for verified results.
5. Call `cancel_task` to request cancellation, then poll for a terminal state.

A TaskSpec contains `workspace_id`, an `argv` list, `backend` (`local`, `pbs`, or
`slurm`), optional input/output lists, environment overrides, and resources.
`["{python}", "simulate.py"]` uses the runtime's configured Python interpreter.
Submission is not completion: check for `state == "succeeded"`. Reuse the same
idempotency key after a lost response. Desktop Tasks and `suan jobs` see the same
records and results.

## Migration

Synchronous commands and dynamically discovered CLI tools have been replaced by
persistent tasks. `run_stk_command(command, workspace_id, idempotency_key, backend)`
accepts `sjob/smesh/sviz` arguments and returns a task record; it does not evaluate
shell operators. The old `run_sjob/run_smesh/run_sviz` and dynamic tool names are
no longer registered. Replace arbitrary file access with workspace uploads.

See repository `docs/runtime.md` for deployment, SSH connections, lifecycle,
formats, and the real-cluster acceptance procedure.
