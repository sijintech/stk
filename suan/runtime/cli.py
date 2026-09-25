"""CLI adapters. Task operations always go through RuntimeClient."""

from pathlib import Path
import codecs
import json
import os
import re
import time
import uuid

import click

from .client import RuntimeClient
from .common import atomic_json, init_config, load_config, read_json
from .models import TaskSpec


def default_state():
    return os.environ.get("STK_STATE_DIR", str(Path.home() / ".stk" / "runtime"))


def profiles_path():
    return Path(
        os.environ.get(
            "STK_PROFILES_FILE", str(Path.home() / ".stk" / "connections.json")
        )
    )


def get_client(profile=None, state_dir=None):
    if profile:
        profiles = read_json(profiles_path(), {})
        if profile not in profiles:
            raise click.ClickException("Connection profile not found")
        config = profiles[profile]
        return RuntimeClient(config["url"], config["token"])
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
        except (ValueError, RuntimeError, OSError, KeyError) as exc:
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
@click.pass_obj
def init_server(state_dir, workspace_root, port, concurrency):
    config = init_config(state_dir, workspace_root, port, concurrency)
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
    """Save loopback endpoints (including SSH-forwarded server endpoints)."""


@connect.command("add")
@click.argument("name")
@click.option("--url", required=True)
@click.option(
    "--token-file", type=click.Path(exists=True, dir_okay=False, path_type=Path)
)
def add_connection(name, url, token_file):
    token = (
        token_file.read_text().strip()
        if token_file
        else click.prompt("Runtime token", hide_input=True)
    )
    RuntimeClient(url, token).health()
    profiles = read_json(profiles_path(), {})
    profiles[name] = {"url": url, "token": token}
    atomic_json(profiles_path(), profiles)
    click.echo(f"Saved connection {name}")


@connect.command("list")
def list_connections():
    dump(
        {
            name: {"url": config["url"]}
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
@client_options
@click.pass_context
def jobs(ctx, profile, state_dir):
    """Submit, reconnect to, inspect and cancel persistent tasks."""
    ctx.obj = LazyClient(profile, state_dir)


@jobs.command("submit", context_settings={"ignore_unknown_options": True})
@click.option("--spec", "spec_file", type=click.Path(exists=True, path_type=Path))
@click.option("--workspace", "workspace_id")
@click.option(
    "--backend", type=click.Choice(["local", "pbs", "slurm"]), default="local"
)
@click.option("--name", default="")
@click.option("--key", help="Reuse when retrying after a lost submission response")
@click.argument("argv", nargs=-1, type=click.UNPROCESSED)
@click.pass_obj
def submit(client, spec_file, workspace_id, backend, name, key, argv):
    if spec_file:
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
@click.pass_obj
def cancel_job(client, task_id):
    dump(client.cancel(task_id))


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
@click.pass_obj
def logs(client, task_id, stream, offset, follow):
    decoder = codecs.getincrementaldecoder("utf-8")("replace")
    while True:
        chunk = client.logs(task_id, stream, offset)
        click.echo(decoder.decode(chunk["bytes"]), nl=False)
        offset = chunk["next_offset"]
        if not follow or (chunk["terminal"] and not chunk["bytes"]):
            click.echo(decoder.decode(b"", final=True), nl=False)
            break
        if not chunk["bytes"]:
            time.sleep(0.5)


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
