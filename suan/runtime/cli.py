"""CLI adapters over the Runtime client and the paired Hub backend."""

from pathlib import Path
import codecs
import json
import os
import re
import tempfile
import time
import uuid

import click

from .client import RuntimeClient
from .common import atomic_json, init_config, load_config, read_json
from .models import TaskSpec
from suan.desktop_bridge.protocol import BridgeError


def default_state():
    return os.environ.get("STK_STATE_DIR", str(Path.home() / ".stk" / "runtime"))


def profiles_path():
    return Path(
        os.environ.get(
            "STK_PROFILES_FILE", str(Path.home() / ".stk" / "connections.json")
        )
    )


def default_hub_state():
    """Separate from the running desktop bridge's writable connection state."""
    return str(Path.home() / ".stk" / "client")


class HubCLIClient:
    """A thin CLI adapter over the existing paired Hub backend, with no desktop server."""

    def __init__(self, name, node, state_dir):
        from suan.desktop_bridge.connections import ConnectionStore
        self.store = ConnectionStore(state_dir)
        try:
            self.backend = self.store.backend("hub:" + name, node)
        except Exception:
            self.store.close()
            raise
        self.backend.wait = 0  # Submission acknowledges the action, never waits for execution/review.

    @staticmethod
    def _public_task(task):
        if "spec" not in task:
            return task
        return {k: v for k, v in task.items() if k != "spec"} | {
            "name": task["spec"]["name"], "workspace_id": task["spec"]["workspace_id"]}

    def _operation(self, kind, key, operation):
        from suan.desktop_bridge.backends import action_id
        identity = action_id(kind, self.backend.node_id, key)
        click.echo(f"Hub action: {identity}", err=True)
        try:
            result = operation()
        except BridgeError as exc:
            if exc.data and exc.data.get("action") and (
                    exc.code == "timeout" or exc.data["action"]["state"] in {"failed", "rejected"}):
                result = {"action": exc.data["action"]}
            elif exc.code == "unavailable":
                # The hub may have accepted the request before its reply was lost.
                # Only the original key/action can resolve that uncertainty.
                dump({"outcome": "unknown", "key": key,
                      "action": {"id": identity, "node_id": self.backend.node_id, "kind": kind},
                      "error": exc.to_json()})
                raise click.exceptions.Exit(1) from None
            else:
                raise
        if "task" in result:
            result["task"] = self._public_task(result["task"])
        result["key"] = key
        state = result["action"]["state"]
        result["outcome"] = {"review": "pending_review", "succeeded": "accepted"}.get(state, state)
        if state in {"failed", "rejected"}:
            dump(result)
            raise click.exceptions.Exit(1)
        return result

    def submit(self, spec, key, *, template=None, workspace_id=None):
        return self._operation("task.submit", key, lambda: self.backend.submit(
            spec.to_dict() if isinstance(spec, TaskSpec) else spec, key,
            template=template, workspace_id=workspace_id))

    def cancel(self, task_id, key):
        return self._operation("task.cancel", key, lambda: self.backend.cancel(task_id, key))

    def tasks(self, workspace_id=None):
        device = self.backend.device()
        tasks = (device.get("snapshot") or {}).get("tasks") or []
        return {"tasks": [t for t in tasks if workspace_id is None or t.get("workspace_id") == workspace_id],
                "observation": "heartbeat_snapshot", "online": bool(device.get("online")),
                "limit": 200}

    def task(self, task_id):
        return self.backend.task(task_id, require_live=True)["task"]

    def action(self, identity):
        from suan.desktop_bridge.backends import summary
        if not re.fullmatch(r"[a-f0-9]{32}", identity):
            raise click.UsageError("An action ID is 32 lowercase hexadecimal characters")
        record = self.backend.call(self.backend.hub.action, identity)
        if record["node_id"] != self.backend.node_id or record["request"]["kind"] not in {"task.submit", "task.cancel"}:
            raise click.ClickException("This is not a task action for the selected node")
        out = {"action": summary(record)}
        if record["state"] == "succeeded":
            out["task"] = self._public_task(record["result"])
        return out

    def logs(self, task_id, stream, offset):
        chunk = self.backend.logs(task_id, stream, offset, 1024 * 1024)
        return {**chunk, "bytes": chunk["data"]}

    def events(self, task_id, offset):
        return self.backend.events(task_id, offset)

    def artifacts(self, task_id):
        return self.backend.artifacts(task_id)["artifacts"]

    def download(self, task_id, remote_path, destination):
        from suan.desktop_bridge.transfers import TransferManager
        # Per-command journals cannot interrupt another CLI process's transfer.
        # The existing .part + sha256 metadata beside the destination permit retries.
        with tempfile.TemporaryDirectory(prefix="stk-cli-transfer-") as journal:
            manager = TransferManager(journal, lambda *args: None, lambda *args: self.backend)
            try:
                transfer = manager.start_download(self.backend.connection_id, "task", task_id, remote_path,
                                                  Path(destination).absolute(), node=self.backend.node_id)
                while True:
                    record = manager.load(transfer["id"])
                    if record["state"] == "completed":
                        return Path(record["local"])
                    if record["state"] in {"failed", "cancelled", "interrupted"}:
                        error = record.get("error") or {}
                        raise BridgeError(error.get("code", "remote_error"), error.get("message", "Download interrupted"))
                    time.sleep(0.05)
            finally:
                manager.stop(timeout=35)


def get_client(profile=None, state_dir=None):
    if profile:
        profiles = read_json(profiles_path(), {})
        if profile not in profiles:
            raise click.ClickException("Connection profile not found")
        config = profiles[profile]
        from .ssh import profile_client
        return profile_client(str(profiles_path().absolute()) + ":" + profile, config)
    url = os.environ.get("STK_RUNTIME_URL")
    if url:
        return RuntimeClient(url, os.environ.get("STK_RUNTIME_TOKEN", ""))
    from .daemon import status

    config = load_config(state_dir or default_state())
    url = status(state_dir or default_state())["url"]
    if url is None:
        raise click.ClickException("The Runtime API is not running and has no fixed port; run suan server start")
    return RuntimeClient(url, config["token"])


class LazyClient:
    """Connects on first use, so a subcommand's --help needs no Runtime."""

    def __init__(self, profile, state_dir):
        self._options, self._client = (profile, state_dir), None

    def __getattr__(self, name):
        if self._client is None:
            self._client = get_client(*self._options)
        return getattr(self._client, name)


def dump(value):
    click.echo(json.dumps(value, ensure_ascii=False, indent=2))


class FriendlyGroup(click.Group):
    def invoke(self, ctx):
        try:
            return super().invoke(ctx)
        except (click.exceptions.Exit, click.Abort):
            raise  # Click's control-flow exceptions also inherit RuntimeError.
        except (ValueError, RuntimeError, OSError, KeyError, BridgeError) as exc:
            raise click.ClickException(str(exc)) from exc


@click.group(cls=FriendlyGroup)
@click.option("--state-dir", default=default_state, type=click.Path(path_type=Path))
@click.pass_context
def server(ctx, state_dir):
    """Initialize and run independent API/supervisor processes."""
    ctx.obj = state_dir


@server.command("init")
@click.option("--workspace-root", type=click.Path(path_type=Path))
@click.option("--port", default=8765, type=click.IntRange(0, 65535))
@click.option("--concurrency", default=1, type=click.IntRange(1))
@click.option("--federation-node-root", type=click.Path(path_type=Path), default=None,
              help="Trusted private registry root, exactly the root used by the outbound NodeAgent.")
@click.option("--federation-coordinator-root", type=click.Path(path_type=Path), default=None,
              help="Trusted private coordinator root for explicit candidate evaluation.")
@click.pass_obj
def init_server(state_dir, workspace_root, port, concurrency, federation_node_root, federation_coordinator_root):
    config = init_config(state_dir, workspace_root, port, concurrency,
                         federation_node_root=federation_node_root,
                         federation_coordinator_root=federation_coordinator_root)
    dump({k: v for k, v in config.items() if k != "token"})
    click.echo(f"Private token: {state_dir / 'config.json'} (not printed)")


@server.command("start")
@click.pass_obj
def start_server(state_dir):
    from .daemon import start

    dump(start(state_dir))


@server.command("status")
@click.pass_obj
def status_server(state_dir):
    from .daemon import status

    dump(status(state_dir))


def show_diagnostics(report, json_output):
    if json_output:
        dump(report)
    else:
        for item in report["checks"]:
            click.echo(f"[{item['status'].upper()}] {item['id']}: {item['message']}")
    if not report["ok"]:
        raise click.exceptions.Exit(1)


def scheduler_name(ctx, param, value):
    if value is not None and not re.fullmatch(r"[A-Za-z0-9_.@/-]+", value):
        raise click.BadParameter("use only letters, digits and _ . @ / -")
    return value


@server.command("doctor")
@click.option(
    "--backend",
    type=click.Choice(["local", "pbs", "slurm"]),
    default="local",
    show_default=True,
)
@click.option(
    "--science",
    is_flag=True,
    help="Also check the worker's STK, NumPy and Matplotlib imports.",
)
@click.option(
    "--timeout", default=5.0, type=click.FloatRange(0.1, 120), show_default=True
)
@click.option(
    "--partition",
    callback=scheduler_name,
    help="Partition or queue to check; overrides scheduler.queue.",
)
@click.option(
    "--account",
    callback=scheduler_name,
    help="Account to check; overrides scheduler.account.",
)
@click.option(
    "--qos",
    callback=scheduler_name,
    help="Slurm QOS to check; overrides scheduler.qos.",
)
@click.option(
    "--probe-preamble",
    is_flag=True,
    help="Run scheduler.preamble with the job shell on this host (nothing is submitted).",
)
@click.option(
    "--json", "json_output", is_flag=True, help="Print a token-free JSON report."
)
@click.pass_obj
def doctor_server(
    state_dir,
    backend,
    science,
    timeout,
    partition,
    account,
    qos,
    probe_preamble,
    json_output,
):
    """Check deployment on this host; temporary filesystem probes are removed.

    Slurm probes run sbatch only with --version or --test-only; no job is submitted.
    """
    from .diagnostics import diagnose_server

    report = diagnose_server(
        state_dir,
        backend,
        science,
        timeout,
        partition=partition,
        account=account,
        qos=qos,
        probe_preamble=probe_preamble,
    )
    show_diagnostics(report, json_output)


@server.command("stop")
@click.option(
    "--supervisor",
    is_flag=True,
    help="Also stop dispatch/reconciliation; existing workers keep running.",
)
@click.pass_obj
def stop_server(state_dir, supervisor):
    """Stop the API. Task workers are not cancelled."""
    from .daemon import stop

    dump(stop(state_dir, supervisor))


@click.group(cls=FriendlyGroup)
def connect():
    """Save Runtime endpoints or pair a client with a control hub."""


@connect.command("hub-pair")
@click.argument("name")
@click.option("--url", required=True)
@click.option("--device-name", required=True)
@click.option("--hub-state-dir", default=default_hub_state, type=click.Path(path_type=Path), show_default=True)
def pair_hub(name, url, device_name, hub_state_dir):
    """Claim an owner-issued client pairing code (entered without echo)."""
    from suan.desktop_bridge.connections import ConnectionStore
    code = click.prompt("Client pairing code", hide_input=True)
    store = ConnectionStore(hub_state_dir)
    try:
        dump(store.pair_hub(name, url, code, device_name))
    finally:
        store.close()


@connect.command("hub-nodes")
@click.argument("name")
@click.option("--hub-state-dir", default=default_hub_state, type=click.Path(path_type=Path), show_default=True)
def hub_nodes(name, hub_state_dir):
    """List the paired hub's node identities, availability and advertised capabilities."""
    from suan.desktop_bridge.connections import ConnectionStore
    from suan.desktop_bridge.backends import HubBackend
    store = ConnectionStore(hub_state_dir)
    try:
        hub = store.hub_client("hub:" + name)
        devices = HubBackend("hub:" + name, hub, "").call(hub.devices)
        dump([{"id": device["id"], "name": device["name"], "online": bool(device.get("online")),
               "features": (device.get("snapshot") or {}).get("features") or [],
               "health": (device.get("snapshot") or {}).get("health") or {}}
              for device in devices if device["role"] == "node"])
    finally:
        store.close()


@connect.command("add")
@click.argument("name")
@click.option("--url", required=True)
@click.option("--ssh-host", help="OpenSSH Host alias; --url is the remote loopback Runtime endpoint")
@click.option(
    "--token-file", type=click.Path(exists=True, dir_okay=False, path_type=Path)
)
def add_connection(name, url, token_file, ssh_host):
    token = (
        token_file.read_text().strip()
        if token_file
        else click.prompt("Runtime token", hide_input=True)
    )
    from .ssh import TunnelManager
    config = {"url": url, "token": token}
    if ssh_host:
        config["ssh"] = {"host": ssh_host}
    manager = TunnelManager()
    try:
        manager.client(name, config).health()
    finally:
        manager.close()
    profiles = read_json(profiles_path(), {})
    profiles[name] = config
    atomic_json(profiles_path(), profiles)
    click.echo(f"Saved connection {name}")


@connect.command("list")
def list_connections():
    dump(
        {
            name: {"url": config["url"], **({"ssh": config["ssh"]} if "ssh" in config else {})}
            for name, config in read_json(profiles_path(), {}).items()
        }
    )


@connect.command("check")
@click.argument("name")
@click.option(
    "--timeout", default=5.0, type=click.FloatRange(0.1, 120), show_default=True
)
@click.option("--json", "json_output", is_flag=True)
def check_connection(name, timeout, json_output):
    """Check a saved endpoint's API and supervisor through an existing SSH tunnel."""
    from .common import now
    from .diagnostics import check, connection_checks

    try:
        client = get_client(name)
        client.timeout = timeout
        checks = connection_checks(client)
    except (
        ValueError,
        RuntimeError,
        OSError,
        KeyError,
        TypeError,
        click.ClickException,
    ):
        checks = [
            check(
                "profile",
                "fail",
                "Cannot load the connection profile; check its name, endpoint and token.",
            )
        ]
    show_diagnostics(
        {
            "schema_version": 1,
            "checked_at": now(),
            "scope": "connection",
            "profile": name,
            "ok": not any(item["status"] == "fail" for item in checks),
            "checks": checks,
        },
        json_output,
    )


def client_options(function):
    function = click.option(
        "--profile", help="Saved SSH-forwarded/local connection name"
    )(function)
    return click.option("--state-dir", type=click.Path(path_type=Path), default=None)(
        function
    )


def hub_job_options(function):
    function = client_options(function)
    function = click.option("--hub", help="Paired hub name; select its execution node with --node")(function)
    function = click.option("--node", help="Exact execution node device ID (see connect hub-nodes)")(function)
    return click.option("--hub-state-dir", default=default_hub_state,
                        type=click.Path(path_type=Path), show_default=True)(function)


@click.group(cls=FriendlyGroup)
@client_options
@click.pass_context
def workspaces(ctx, profile, state_dir):
    """Create workspaces and transfer immutable task inputs."""
    ctx.obj = LazyClient(profile, state_dir)


@workspaces.command("create")
@click.argument("name")
@click.pass_obj
def create_workspace(client, name):
    dump(client.create_workspace(name))


@workspaces.command("list")
@click.pass_obj
def list_workspaces(client):
    dump(client.workspaces())


@workspaces.command("files")
@click.argument("workspace_id")
@click.pass_obj
def list_files(client, workspace_id):
    dump(client.files(workspace_id))


@workspaces.command("upload")
@click.argument("workspace_id")
@click.argument("source", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--path", "remote_path", help="Remote relative filename (single-file upload only)"
)
@click.pass_obj
def upload(client, workspace_id, source, remote_path):
    if source.is_dir():
        if remote_path:
            raise click.UsageError("--path is only supported for a single file")
        for path in sorted(source.rglob("*")):
            if path.is_file():
                dump(
                    client.upload(
                        workspace_id, path, path.relative_to(source).as_posix()
                    )
                )
    else:
        dump(client.upload(workspace_id, source, remote_path))


@click.group(cls=FriendlyGroup)
@hub_job_options
@click.pass_context
def jobs(ctx, profile, state_dir, hub, node, hub_state_dir):
    """Submit, reconnect to, inspect and cancel persistent tasks."""
    if hub:
        if profile or state_dir:
            raise click.UsageError("--hub cannot be combined with --profile or --state-dir")
        if not node:
            raise click.UsageError("--hub requires --node; use connect hub-nodes NAME to select one")
        ctx.obj = HubCLIClient(hub, node, hub_state_dir)
        ctx.call_on_close(ctx.obj.store.close)
    else:
        if node:
            raise click.UsageError("--node requires --hub")
        ctx.obj = LazyClient(profile, state_dir)


@jobs.command("submit", context_settings={"ignore_unknown_options": True})
@click.option("--spec", "spec_file", type=click.Path(exists=True, path_type=Path))
@click.option("--workspace", "workspace_id")
@click.option("--template", help="Registered Hub template name (requires --hub and --workspace)")
@click.option(
    "--backend", type=click.Choice(["local", "pbs", "slurm"]), default="local"
)
@click.option("--name", default="")
@click.option("--key", help="Reuse when retrying after a lost submission response")
@click.argument("argv", nargs=-1, type=click.UNPROCESSED)
@click.pass_obj
def submit(client, spec_file, workspace_id, template, backend, name, key, argv):
    if template:
        if not isinstance(client, HubCLIClient) or not workspace_id or spec_file or argv:
            raise click.UsageError("--template requires --hub and --workspace, without --spec or an argv command")
        if name or backend != "local":
            raise click.UsageError("--template uses the registered name/backend; omit --name and --backend")
        spec = None
    elif spec_file:
        if argv:
            raise click.UsageError("Use either --spec or an argv command")
        spec = TaskSpec(**json.loads(spec_file.read_text(encoding="utf-8")))
    else:
        if not workspace_id or not argv:
            raise click.UsageError(
                "Provide --spec, or --workspace ID -- PROGRAM ARG..."
            )
        spec = TaskSpec(workspace_id, list(argv), backend=backend, name=name)
    key = key or uuid.uuid4().hex
    click.echo(f"Idempotency key: {key}", err=True)
    if template:
        dump(client.submit(None, key, template=template, workspace_id=workspace_id))
    else:
        dump(client.submit(spec, key))


@jobs.command("list")
@click.option("--workspace", "workspace_id")
@click.pass_obj
def list_jobs(client, workspace_id):
    dump(client.tasks(workspace_id))


@jobs.command("show")
@click.argument("task_id")
@click.pass_obj
def show_job(client, task_id):
    dump(client.task(task_id))


@jobs.command("cancel")
@click.argument("task_id")
@click.option("--key", help="Hub cancellation key; reuse it after a lost response")
@click.pass_obj
def cancel_job(client, task_id, key):
    if isinstance(client, HubCLIClient):
        key = key or uuid.uuid4().hex
        click.echo(f"Idempotency key: {key}", err=True)
        dump(client.cancel(task_id, key))
    else:
        if key:
            raise click.UsageError("--key on cancel is only used with --hub")
        dump(client.cancel(task_id))


@jobs.command("action")
@click.argument("action_id")
@click.pass_obj
def show_action(client, action_id):
    """Resolve a pending/unknown Hub submission by its original action ID."""
    if not isinstance(client, HubCLIClient):
        raise click.UsageError("jobs action requires --hub and --node")
    result = client.action(action_id)
    dump(result)
    if result["action"]["state"] in {"failed", "rejected"}:
        raise click.exceptions.Exit(1)


@jobs.command("watch")
@click.argument("task_id")
@click.option("--interval", default=1.0, type=click.FloatRange(0.1), show_default=True)
@click.option("--timeout", default=0.0, type=click.FloatRange(0), help="Stop after this many seconds; 0 waits indefinitely")
@click.pass_obj
def watch_job(client, task_id, interval, timeout):
    """Print JSON observations until terminal; disconnection never changes task state."""
    from .models import TERMINAL
    deadline = time.monotonic() + timeout if timeout else None
    previous, last_state = None, None
    while True:
        try:
            task = client.task(task_id)
            observation = {"task_id": task_id, "observation": "current", "task": task}
            last_state = task["state"]
        except BridgeError as exc:
            if not exc.retryable:
                raise
            observation = {"task_id": task_id, "observation": "unavailable", "last_state": last_state,
                           "error": exc.to_json()}
        encoded = json.dumps(observation, ensure_ascii=False, sort_keys=True)
        if encoded != previous:
            click.echo(encoded)
            previous = encoded
        if observation["observation"] == "current" and last_state in TERMINAL | {"unknown"}:
            if last_state != "succeeded":
                raise click.exceptions.Exit(1)
            return
        if deadline is not None and time.monotonic() >= deadline:
            click.echo(json.dumps({"task_id": task_id, "observation": "timeout", "last_state": last_state}))
            raise click.exceptions.Exit(1)
        time.sleep(interval if deadline is None else min(interval, max(0, deadline - time.monotonic())))


@jobs.command("logs")
@click.argument("task_id")
@click.option(
    "--stream",
    default="stdout",
    type=click.Choice(
        ["stdout", "stderr", "scheduler.out", "scheduler.err", "wrapper"]
    ),
)
@click.option("--offset", default=0, type=click.IntRange(0))
@click.option("--follow", is_flag=True)
@click.option("--show-offset", is_flag=True, help="Print the next byte offset on stderr, including on interruption")
@click.pass_obj
def logs(client, task_id, stream, offset, follow, show_offset):
    decoder = codecs.getincrementaldecoder("utf-8")("replace")
    try:
        while True:
            chunk = client.logs(task_id, stream, offset)
            click.echo(decoder.decode(chunk["bytes"]), nl=False)
            offset = chunk["next_offset"]
            if not follow or (chunk["terminal"] and not chunk["bytes"]):
                click.echo(decoder.decode(b"", final=True), nl=False)
                break
            if not chunk["bytes"]:
                time.sleep(0.5)
    finally:
        if show_offset:
            click.echo(f"Next offset: {offset}", err=True)


@jobs.command("events")
@click.argument("task_id")
@click.option("--offset", default=0, type=click.IntRange(0))
@click.pass_obj
def events(client, task_id, offset):
    """Read persistent monitoring events, returning the server's next cursor."""
    dump(client.events(task_id, offset))


@jobs.command("artifacts")
@click.argument("task_id")
@click.pass_obj
def artifacts(client, task_id):
    dump(client.artifacts(task_id))


@jobs.command("download")
@click.argument("task_id")
@click.argument("remote_path")
@click.argument("destination", type=click.Path(path_type=Path))
@click.pass_obj
def download(client, task_id, remote_path, destination):
    click.echo(client.download(task_id, remote_path, destination))
