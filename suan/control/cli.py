"""Run the control server and outbound agent as separate long-lived processes."""
import asyncio
import json
import os
from pathlib import Path
import secrets

import click

from suan.runtime.common import UnsupportedServerPlatform, atomic_json, load_config, require_linux_server
from suan.runtime.client import RuntimeClient
from .agent import NodeAgent, endpoint
from .limits import FRAME_LIMIT
from .policy import DESKTOP_AUTO_BYTES, REVIEW_POLICIES
from .store import ControlStore
from .templates import BUILTIN_TEMPLATES, load_templates


def private_json(path, value):
    path = Path(path)
    if path.is_symlink() or path.exists():
        raise click.ClickException("Credential destination already exists")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(value, stream)


def linux_server():
    """Control, node agent and Runtime are Linux services; other hosts are clients."""
    try:
        require_linux_server()
    except UnsupportedServerPlatform as exc:
        # The Runtime's hint (suan connect --profile) configures the suan CLI, not the workbench.
        raise click.ClickException(
            "The STK control service and node agent run on Linux only, on the server next to the Runtime. "
            "Connect this computer's workbench through an SSH tunnel: ssh -N -L 8790:127.0.0.1:8790 HOST, "
            "then suan-workbench --url http://127.0.0.1:8790.") from exc


@click.group()
def control():
    """STK cross-device control service (independent of the execution Runtime)."""


@control.command("init")
@click.option("--state-dir", type=click.Path(path_type=Path), required=True)
def init(state_dir):
    linux_server()
    private_json(state_dir / "control.json", {"owner_token": secrets.token_urlsafe(32)})
    ControlStore(state_dir)
    click.echo(f"Control initialized: {state_dir}")


@control.command()
@click.option("--state-dir", type=click.Path(path_type=Path), required=True)
@click.option("--host", default="127.0.0.1")
@click.option("--port", default=8790, type=int)
@click.option("--web-dir", type=click.Path(path_type=Path, exists=True))
@click.option("--allow-demo-template", is_flag=True,
              help="Authorize the fixed manufactured-field demo command (same as --template demo-field).")
@click.option("--template", "names", multiple=True, type=click.Choice(sorted(BUILTIN_TEMPLATES)),
              help="Authorize a built-in exact command template (repeatable).")
@click.option("--template-file", "files", multiple=True, type=click.Path(exists=True, dir_okay=False, path_type=Path),
              help="JSON object mapping template IDs to exact commands (repeatable).")
@click.option("--blob-max-mib", default=512, show_default=True, type=click.IntRange(1, 65536),
              help="Largest blob a node or client may upload (graph payload buffers, images, plots, client "
                   "files for workspace.import). A reverse proxy in front of the hub needs a request body limit "
                   "at least this large for /api/v1/blobs/ and at least 8 MiB for /api/v1/uploads/.")
@click.option("--desktop-auto-mib", type=click.IntRange(0, 65536), default=None,
              help="Expected-transfer cap under which desktop-profile clients run graph evaluations without "
                   "review (default: \"desktop_auto_mib\" in control.json, else 256; 0 turns it off).")
@click.option("--upload-quota-mib", type=click.IntRange(0, 1048576), default=None,
              help="Per desktop device: bytes of unfinished uploads plus uploaded files not imported yet "
                   "(default: \"upload_quota_mib\" in control.json, else 4096).")
@click.option("--upload-gc-hours", type=click.FloatRange(0, 8760), default=None,
              help="Delete uploaded files no workspace.import references this long after upload (default: "
                   "\"upload_gc_hours\" in control.json, else 24).")
@click.option("--upload-min-free-mib", type=click.IntRange(0, 1048576), default=None,
              help="Refuse uploads (HTTP 507) while the blob store has less free disk space (default: "
                   "\"upload_min_free_mib\" in control.json, else 5120).")
@click.option("--review-policy", type=click.Choice(REVIEW_POLICIES), default=None,
              help="Who may approve reviewed actions: any client (default; review is a confirmation step), "
                   "not-self (not the submitting device; recommended for internet-reachable hubs) or owner "
                   "(default: \"review_policy\" in control.json, else any).")
def serve(state_dir, host, port, web_dir, allow_demo_template, names, files, blob_max_mib, desktop_auto_mib,
          upload_quota_mib, upload_gc_hours, upload_min_free_mib, review_policy):
    linux_server()
    import uvicorn
    from .app import create_app
    from .model import ChatModel
    try:
        templates = load_templates((("demo-field",) if allow_demo_template else ()) + names, files)
    except (OSError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    config = json.loads((state_dir / "control.json").read_text(encoding="utf-8"))
    desktop_auto_mib = setting(config, "desktop_auto_mib", desktop_auto_mib, DESKTOP_AUTO_BYTES // (1024 * 1024),
                               65536)
    upload_quota_mib = setting(config, "upload_quota_mib", upload_quota_mib, 4096, 1048576)
    upload_gc_hours = setting(config, "upload_gc_hours", upload_gc_hours, 24, 8760, number=True)
    upload_min_free_mib = setting(config, "upload_min_free_mib", upload_min_free_mib, 5120, 1048576)
    if review_policy is None:
        review_policy = config.get("review_policy", "any")
        if review_policy not in REVIEW_POLICIES:
            raise click.ClickException("control.json review_policy must be one of " + ", ".join(REVIEW_POLICIES))
    model = None
    if os.environ.get("STK_MODEL_URL") and os.environ.get("STK_MODEL_NAME"):
        model = ChatModel(os.environ["STK_MODEL_URL"], os.environ.get("STK_MODEL_KEY", ""), os.environ["STK_MODEL_NAME"])
    mib = 1024 * 1024
    app = create_app(state_dir, config["owner_token"], templates, model, web_dir,
                     blob_max_bytes=blob_max_mib * mib, desktop_auto_bytes=desktop_auto_mib * mib,
                     upload_quota_bytes=upload_quota_mib * mib, upload_ttl_seconds=upload_gc_hours * 3600,
                     upload_min_free_bytes=upload_min_free_mib * mib, review_policy=review_policy)
    uvicorn.run(app, host=host, port=port, ws_max_size=FRAME_LIMIT, access_log=False)


def setting(config, key, value, default, maximum, number=False):
    """A command-line value, else ``control.json[key]``, else ``default`` (checked like the option)."""
    if value is not None:
        return value
    value = config.get(key, default)
    kinds = (int, float) if number else (int,)
    if isinstance(value, bool) or not isinstance(value, kinds) or not 0 <= value <= maximum:
        raise click.ClickException(f"control.json {key} must be a number from 0 to {maximum}")
    return value


@control.command()
@click.option("--state-dir", type=click.Path(path_type=Path, exists=True), required=True)
@click.option("--role", type=click.Choice(["node", "client"]), default="client")
@click.option("--profile", type=click.Choice(["desktop"]), default=None,
              help="Grant the client the desktop profile: graph evaluations within the desktop cap run "
                   "without review (writes and new commands are still reviewed).")
def pair(state_dir, role, profile):
    """Issue a one-time pairing code; expires in five minutes."""
    linux_server()
    if profile and role != "client":
        raise click.ClickException("--profile desktop is for client pairings")
    click.echo(json.dumps(ControlStore(state_dir).pairing(role, profile or "")))


@click.group()
def node():
    """Outbound execution-node agent; stopping it does not stop Runtime jobs."""


@node.command("pair")
@click.option("--control-url", required=True)
@click.option("--code", prompt="One-time node pairing code", hide_input=True)
@click.option("--name", required=True)
@click.option("--runtime-state-dir", type=click.Path(path_type=Path, exists=True), required=True)
@click.option("--state-dir", type=click.Path(path_type=Path), required=True)
def pair_node(control_url, code, name, runtime_state_dir, state_dir):
    linux_server()
    import httpx
    url = endpoint(control_url)
    with httpx.Client(timeout=30, follow_redirects=False) as client:
        response = client.post(url + "/api/v1/pairings/claim", json={"code": code, "name": name})
        response.raise_for_status()
    data = response.json()
    if data["role"] != "node":
        raise click.ClickException("Pairing code must have the node role")
    private_json(state_dir / "node.json", {**data, "control_url": url, "runtime_state_dir": str(runtime_state_dir.resolve())})
    click.echo(f"Paired node {data['device_id']}")


@node.command("run")
@click.option("--state-dir", type=click.Path(path_type=Path, exists=True), required=True)
@click.option("--graph-workers", default=1, show_default=True, type=click.IntRange(1, 2),
              help="Graph evaluations run at the same time (other actions never wait for them).")
def run_node(state_dir, graph_workers):
    linux_server()
    data = json.loads((state_dir / "node.json").read_text(encoding="utf-8"))
    runtime = load_config(data["runtime_state_dir"])
    client = RuntimeClient(f"http://127.0.0.1:{runtime['port']}", runtime["token"])
    try:
        agent = NodeAgent(client, state_dir / "cache", graph_workers=graph_workers)
        asyncio.run(agent.run(data["control_url"], data["token"]))
    except KeyboardInterrupt:
        pass
