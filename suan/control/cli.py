"""Run the control server and outbound agent as separate long-lived processes."""
import asyncio
import json
import os
from pathlib import Path
import secrets

import click

from suan.runtime.common import atomic_json, load_config
from suan.runtime.client import RuntimeClient
from .agent import NodeAgent, endpoint
from .store import ControlStore


def private_json(path, value):
    path = Path(path)
    if path.is_symlink() or path.exists():
        raise click.ClickException("Credential destination already exists")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(value, stream)


@click.group()
def control():
    """STK cross-device control service (independent of the execution Runtime)."""


@control.command("init")
@click.option("--state-dir", type=click.Path(path_type=Path), required=True)
def init(state_dir):
    private_json(state_dir / "control.json", {"owner_token": secrets.token_urlsafe(32)})
    ControlStore(state_dir)
    click.echo(f"Control initialized: {state_dir}")


@control.command()
@click.option("--state-dir", type=click.Path(path_type=Path), required=True)
@click.option("--host", default="127.0.0.1")
@click.option("--port", default=8790, type=int)
@click.option("--web-dir", type=click.Path(path_type=Path, exists=True))
@click.option("--allow-demo-template", is_flag=True, help="Authorize the fixed manufactured-field demo command.")
def serve(state_dir, host, port, web_dir, allow_demo_template):
    import uvicorn
    from .app import create_app
    from .model import ChatModel
    from .policy import DEMO_TEMPLATE
    config = json.loads((state_dir / "control.json").read_text())
    model = None
    if os.environ.get("STK_MODEL_URL") and os.environ.get("STK_MODEL_NAME"):
        model = ChatModel(os.environ["STK_MODEL_URL"], os.environ.get("STK_MODEL_KEY", ""), os.environ["STK_MODEL_NAME"])
    app = create_app(state_dir, config["owner_token"], {"demo-field": DEMO_TEMPLATE} if allow_demo_template else {}, model, web_dir)
    uvicorn.run(app, host=host, port=port, ws_max_size=16*1024*1024, access_log=False)


@control.command()
@click.option("--state-dir", type=click.Path(path_type=Path, exists=True), required=True)
@click.option("--role", type=click.Choice(["node", "client"]), default="client")
def pair(state_dir, role):
    """Issue a one-time pairing code; expires in five minutes."""
    click.echo(json.dumps(ControlStore(state_dir).pairing(role)))


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
def run_node(state_dir):
    data = json.loads((state_dir / "node.json").read_text())
    runtime = load_config(data["runtime_state_dir"])
    client = RuntimeClient(f"http://127.0.0.1:{runtime['port']}", runtime["token"])
    try:
        asyncio.run(NodeAgent(client, state_dir / "cache").run(data["control_url"], data["token"]))
    except KeyboardInterrupt:
        pass
