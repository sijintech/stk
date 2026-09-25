"""`suan mupro`: submit muFerro cases to an STK Runtime and check their results."""

from pathlib import Path
import json
import tempfile
import uuid

import click

from suan.runtime.cli import FriendlyGroup, client_options, dump, get_client
from suan.runtime.models import TaskSpec, relative_path
from .spec import LAUNCHERS, muferro_spec


@click.group(cls=FriendlyGroup)
def mupro():
    """MuPRO jobs queued by the STK Runtime."""


@mupro.command("submit")
@client_options
@click.option("--workspace", "workspace_id", required=True)
@click.option("--input", "input_dir", type=click.Path(exists=True, file_okay=False, path_type=Path),
              help="Upload this local case directory, then run it.")
@click.option("--case-dir", help="Run a case already uploaded under this workspace path ('.' for the root).")
@click.option("--example", is_flag=True, help="Run the SDK example case installed on the compute node.")
@click.option("--remote-dir", help="Workspace path for --input (default: the directory name).")
@click.option("--ranks", default=1, show_default=True, type=click.IntRange(1), help="Total MPI ranks.")
@click.option("--threads-per-rank", default=1, show_default=True, type=click.IntRange(1))
@click.option("--nodes", default=1, show_default=True, type=click.IntRange(1))
@click.option("--backend", type=click.Choice(["local", "pbs", "slurm"]), default="local", show_default=True)
@click.option("--queue")
@click.option("--account")
@click.option("--walltime", "walltime_seconds", type=click.IntRange(1), help="Seconds; required on clusters.")
@click.option("--memory-mb", type=click.IntRange(1))
@click.option("--program", default="muFerro", show_default=True)
@click.option("--launcher", type=click.Choice(LAUNCHERS), default="auto", show_default=True)
@click.option("--sdk-prefix", help="SDK prefix on the compute node (default: its MUPRO_SDK_PREFIX).")
@click.option("--env-script", "env_scripts", multiple=True, help="Compute-node bash script to source first.")
@click.option("--license-dir", help="Compute-node licence directory, exported as MUPROROOT.")
@click.option("--name", default="")
@click.option("--key", help="Reuse when retrying after a lost submission response")
@click.option("--wait", is_flag=True, help="Wait for the task and exit 1 unless it succeeds.")
@click.option("--timeout", default=600.0, show_default=True, type=click.FloatRange(0.1))
def submit(profile, state_dir, workspace_id, input_dir, case_dir, example, remote_dir, ranks, threads_per_rank,
           nodes, backend, queue, account, walltime_seconds, memory_mb, program, launcher, sdk_prefix, env_scripts,
           license_dir, name, key, wait, timeout):
    """Upload or select a muFerro case and queue it."""
    if sum(map(bool, (input_dir, case_dir, example))) != 1:
        raise click.UsageError("Use exactly one of --input DIR, --case-dir REL or --example")
    if remote_dir and not input_dir:
        raise click.UsageError("--remote-dir only applies to --input")
    if input_dir:
        case_dir = remote_dir or input_dir.resolve().name
    if case_dir:
        case_dir = "." if case_dir == "." else relative_path(case_dir)
    # Validate the layout before connecting or uploading anything; the inputs are filled in below.
    spec = muferro_spec(workspace_id, case_dir=case_dir or ".", example=example, ranks=ranks,
                        threads_per_rank=threads_per_rank, nodes=nodes, backend=backend, program=program,
                        launcher=launcher, sdk_prefix=sdk_prefix, env_scripts=env_scripts, license_dir=license_dir,
                        walltime_seconds=walltime_seconds, memory_mb=memory_mb, queue=queue, account=account,
                        name=name)
    TaskSpec(**spec)  # The Runtime's own checks, e.g. ranks must be a multiple of nodes.
    if input_dir:
        from .run import check_case, read_case

        check_case(read_case(input_dir), input_dir, ranks)
    client = get_client(profile, state_dir)
    if "ranks" not in client.health().get("resources", []):
        raise click.ClickException("This Runtime does not accept MPI rank resources; upgrade the STK server")
    if input_dir:
        inputs = []
        for path in sorted(input_dir.rglob("*")):
            if path.is_file():
                remote = path.relative_to(input_dir).as_posix()
                remote = remote if case_dir == "." else f"{case_dir}/{remote}"
                client.upload(workspace_id, path, remote)
                click.echo(f"Uploaded {remote}", err=True)
                inputs.append(remote)
        if not inputs:
            raise click.ClickException(f"No files in {input_dir}")
        spec["inputs"] = inputs
    elif case_dir:
        inputs = [item["path"] for item in client.files(workspace_id)
                  if case_dir == "." or item["path"].startswith(case_dir + "/")]
        if not inputs:
            raise click.ClickException(f"No workspace files under {case_dir}")
        spec["inputs"] = inputs
    key = key or uuid.uuid4().hex
    click.echo(f"Idempotency key: {key}", err=True)
    record = client.submit(spec, key)
    if wait:
        click.echo(f"Waiting for task {record['id']}", err=True)
        record = client.wait(record["id"], timeout)
    dump(record)
    if wait and record["state"] != "succeeded":
        raise click.exceptions.Exit(1)


@mupro.command("result")
@client_options
@click.argument("task_id")
@click.option("--output", type=click.Path(dir_okay=False, path_type=Path), help="Keep stk-mupro.json here.")
def result(profile, state_dir, task_id, output):
    """Print a finished task's stk-mupro.json; exit 0 only if verification passed."""
    client = get_client(profile, state_dir)
    with tempfile.TemporaryDirectory() as folder:
        path = client.download(task_id, "stk-mupro.json", output or Path(folder) / "stk-mupro.json")
        report = json.loads(Path(path).read_text(encoding="utf-8"))
    dump(report)
    if report.get("verification", {}).get("status") != "passed":
        raise click.exceptions.Exit(3)


@mupro.command("verify")
@click.argument("run_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--case-dir", default=".", show_default=True, help="Case directory relative to RUN_DIR.")
def verify(run_dir, case_dir):
    """Check a local run directory against MuPRO's output contract."""
    from .run import verify_run

    report = verify_run(run_dir, case_dir)
    dump(report)
    if report["verification"]["status"] != "passed":
        raise click.exceptions.Exit(3)
