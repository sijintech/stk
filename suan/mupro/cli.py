"""`suan mupro`: submit muFerro cases to an STK Runtime and check their results."""

from pathlib import Path
import hashlib
import json
import re
import stat
import tempfile
import uuid
from urllib.parse import urlencode

import click

from suan.runtime.cli import FriendlyGroup, client_options, dump, get_client
from suan.runtime.models import TaskSpec, relative_path
from .spec import LAUNCHERS, muferro_spec


@click.group(cls=FriendlyGroup)
def mupro():
    """MuPRO jobs queued by the STK Runtime."""


@mupro.command("check")
@click.option("--sdk-prefix", help="SDK prefix in this process's environment (default: MUPRO_SDK_PREFIX).")
@click.option("--program", default="muFerro", show_default=True, help="Configured program name or path to locate.")
@click.option("--env-script", "env_scripts", multiple=True, help="Local trusted bash script to source before checking.")
@click.option("--license-dir", help="Local licence directory; its contents are never read.")
@click.option("--json", "as_json", is_flag=True, help="Print the versioned observation without diagnostic paths.")
def check(sdk_prefix, program, env_scripts, license_dir, as_json):
    """Observe this machine's configured prerequisites, without running MuPRO.

    Run on the compute node to inspect that node. This does not connect to a Runtime,
    select a placement, check out a licence or test a solver. Configured environment
    scripts are sourced. Detailed local diagnostics remain in python -m suan.mupro check.
    """
    from types import SimpleNamespace
    from .run import preflight_observation

    report = preflight_observation(SimpleNamespace(sdk_prefix=sdk_prefix, program=program,
        env_scripts=list(env_scripts), license_dir=license_dir))
    if as_json:
        dump(report)
    else:
        click.echo(f"MuPRO preflight: {report['summary']} ({report['scope']}, pid {report['process_id']})")
        click.echo(f"Observed at {report['observed_at']}")
        for item in report["checks"]:
            click.echo(f"[{item['status'].upper()}] {item['id']}")
        click.echo("MuPRO version unobserved; licence checkout not checked; solver not run.")
    if report["summary"] == "checks_failed":
        raise click.exceptions.Exit(1)


def _preflight_task(record, task_id):
    from .spec import preflight_spec

    if not isinstance(record, dict) or record.get("id") != task_id:
        raise ValueError("Preflight task identity does not match the requested task")
    spec = record.get("spec")
    if not isinstance(spec, dict):
        raise ValueError("Preflight task specification is missing")
    try:
        actual = TaskSpec(**spec).to_dict()
        resources = actual["resources"]
        expected = preflight_spec(actual["workspace_id"], backend=actual["backend"], name=actual["name"],
            **{k: resources[k] for k in ("walltime_seconds", "memory_mb", "queue", "account") if k in resources})
        matches = actual == TaskSpec(**expected).to_dict()
    except (TypeError, ValueError, KeyError) as exc:
        raise ValueError("Invalid preflight task specification") from exc
    if not matches:
        raise ValueError("Task is not an unmodified MuPRO preflight task")
    if record.get("state") not in ("succeeded", "failed"):
        raise ValueError("Preflight task must finish successfully or with failed checks before reading its observation")
    return actual


def _preflight_result(client, task_id, profile, *, expected_spec=None):
    from .preflight import MAX_OBSERVATION_BYTES, OBSERVATION_NAME, parse_observation

    if not isinstance(task_id, str) or re.fullmatch(r"[a-f0-9]{32}", task_id) is None:
        raise ValueError("Expected a Runtime task ID")
    identity = client.connection_identity
    if not isinstance(identity, str) or not identity:
        raise ValueError("Preflight result needs a stable Runtime connection identity")
    record = client.task(task_id)
    spec = _preflight_task(record, task_id)
    if expected_spec is not None and spec != TaskSpec(**expected_spec).to_dict():
        raise ValueError("Preflight task no longer matches the submitted specification")
    items = client.artifacts(task_id)
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        raise ValueError("Invalid preflight artifact listing")
    matches = [item for item in items if item.get("path") == OBSERVATION_NAME]
    if len(matches) != 1:
        raise ValueError("Preflight observation artifact is missing or ambiguous; the compute package may need upgrading")
    item = matches[0]
    size, digest = item.get("size"), item.get("sha256")
    if (type(size) is not int or not 1 <= size <= MAX_OBSERVATION_BYTES or
            not isinstance(digest, str) or re.fullmatch(r"[a-f0-9]{64}", digest) is None):
        raise ValueError("Invalid preflight observation artifact size or digest")
    # One bounded ranged read avoids a second artifact listing changing the download budget.
    query = urlencode({"path": OBSERVATION_NAME, "offset": 0, "limit": size})
    data = client.request("GET", f"tasks/{task_id}/file?{query}", binary=True, max_response_bytes=size)
    if (not isinstance(data, bytes) or len(data) != size or hashlib.sha256(data).hexdigest() != digest):
        raise ValueError("Preflight observation does not match the listed artifact")
    observation = parse_observation(data)
    exit_code = record.get("exit_code")
    failed = observation["summary"] == "checks_failed"
    if (type(exit_code) is not int or exit_code != int(failed) or
            record["state"] != ("failed" if failed else "succeeded")):
        raise ValueError("Task completion does not match its preflight observation")
    # A refresh reads this same task; it never submits a replacement or runs a local check.
    latest = client.task(task_id)
    if (client.connection_identity != identity or _preflight_task(latest, task_id) != spec or
            latest.get("state") != record["state"] or type(latest.get("exit_code")) is not int or
            latest["exit_code"] != exit_code):
        raise ValueError("Preflight task or Runtime connection changed while reading the observation")
    return {"schema": "stk.mupro-preflight-result/1", "scope": "runtime_task",
        "target": {"profile": profile, "connection_sha256": hashlib.sha256(identity.encode()).hexdigest()},
        "task": {"id": task_id, "workspace_id": spec["workspace_id"], "backend": spec["backend"],
                 "state": record["state"], "exit_code": exit_code},
        "artifact": {"path": OBSERVATION_NAME, "size": size, "sha256": digest},
        "observation": observation}


@mupro.command("preflight")
@client_options
@click.option("--workspace", "workspace_id", required=True)
@click.option("--backend", type=click.Choice(["local", "pbs", "slurm"]), default="local", show_default=True)
@click.option("--queue")
@click.option("--account")
@click.option("--walltime", "walltime_seconds", type=click.IntRange(1), help="Seconds; required on clusters.")
@click.option("--memory-mb", type=click.IntRange(1))
@click.option("--name", default="")
@click.option("--key", help="Reuse the same key after a lost submission response.")
@click.option("--wait", is_flag=True, help="Wait for and verify the selected task's observation.")
@click.option("--timeout", default=600.0, show_default=True, type=click.FloatRange(0.1))
def preflight(profile, state_dir, workspace_id, backend, queue, account, walltime_seconds, memory_mb,
              name, key, wait, timeout):
    """Submit an explicit prerequisite check in the selected execution environment.

    Uses that worker's configured environment and trusted scripts. Creates a task and
    uses its resources. Does not run MuPRO or MPI, check out a licence, or approve a run.
    The local check command remains independent of Runtime connections.
    """
    from .spec import preflight_spec

    spec = preflight_spec(workspace_id, backend=backend, walltime_seconds=walltime_seconds,
                          memory_mb=memory_mb, queue=queue, account=account, name=name)
    TaskSpec(**spec)
    client = get_client(profile, state_dir)
    key = key or uuid.uuid4().hex
    click.echo(f"Idempotency key: {key}", err=True)
    record = client.submit(spec, key)
    task_id = record.get("id") if isinstance(record, dict) else None
    if not isinstance(task_id, str) or re.fullmatch(r"[a-f0-9]{32}", task_id) is None:
        raise ValueError("Submission returned an invalid Runtime task ID; observe the original idempotency key")
    try:
        matches = TaskSpec(**record["spec"]).to_dict() == TaskSpec(**spec).to_dict()
    except (TypeError, ValueError, KeyError) as exc:
        raise ValueError("Submission returned an invalid preflight specification; observe the original idempotency key") from exc
    if not matches:
        raise ValueError("Submission does not match the requested preflight specification; observe the original idempotency key")
    if not wait:
        dump(record)
        return
    click.echo(f"Waiting for preflight task {task_id}", err=True)
    client.wait(task_id, timeout)
    report = _preflight_result(client, task_id, profile, expected_spec=spec)
    dump(report)
    if report["observation"]["summary"] == "checks_failed":
        raise click.exceptions.Exit(1)


@mupro.command("preflight-result")
@client_options
@click.argument("task_id")
@click.option("--output", type=click.Path(dir_okay=False, path_type=Path), help="Save the verified result to a new file.")
def preflight_result(profile, state_dir, task_id, output):
    """Read one completed preflight task without submitting or running another check."""
    if re.fullmatch(r"[a-f0-9]{32}", task_id) is None:
        raise click.BadParameter("Expected a Runtime task ID", param_hint="TASK_ID")
    report = _preflight_result(get_client(profile, state_dir), task_id, profile)
    if output is not None:
        with output.open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    dump(report)
    if report["observation"]["summary"] == "checks_failed":
        raise click.exceptions.Exit(1)


def _case_uploads(folder, case_dir):
    from .run import case_input_info

    try:
        input_info = case_input_info(folder / "input.toml")
    except OSError as exc:
        raise ValueError(f"Cannot read input.toml: {exc}") from exc
    if not stat.S_ISREG(input_info.st_mode):
        raise ValueError("Cannot read input.toml: expected a regular file")

    prefix = "" if case_dir == "." else case_dir + "/"
    pending, uploads = [folder], []
    while pending:
        for path in pending.pop().iterdir():
            info = case_input_info(path)
            if stat.S_ISDIR(info.st_mode):
                pending.append(path)
            elif stat.S_ISREG(info.st_mode):
                remote = relative_path(prefix + path.relative_to(folder).as_posix())
                uploads.append((path, remote))
            else:
                raise ValueError("Case inputs must be regular files")
    return sorted(uploads)


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
        input_dir = input_dir.resolve()
        case_dir = remote_dir or input_dir.name
    if case_dir:
        case_dir = "." if case_dir == "." else relative_path(case_dir)
    # Validate the layout and the full local manifest before connecting or uploading.
    spec = muferro_spec(workspace_id, case_dir=case_dir or ".", example=example, ranks=ranks,
                        threads_per_rank=threads_per_rank, nodes=nodes, backend=backend, program=program,
                        launcher=launcher, sdk_prefix=sdk_prefix, env_scripts=env_scripts, license_dir=license_dir,
                        walltime_seconds=walltime_seconds, memory_mb=memory_mb, queue=queue, account=account,
                        name=name)
    TaskSpec(**spec)  # The Runtime's own checks, e.g. ranks must be a multiple of nodes.
    if input_dir:
        uploads = _case_uploads(input_dir, case_dir)
        spec["inputs"] = [remote for _, remote in uploads]
        from .run import check_case, read_case

        check_case(read_case(input_dir), input_dir, ranks)
    client = get_client(profile, state_dir)
    if "ranks" not in client.health().get("resources", []):
        raise click.ClickException("This Runtime does not accept MPI rank resources; upgrade the STK server")
    if input_dir:
        for path, remote in uploads:
            client.upload(workspace_id, path, remote)
            click.echo(f"Uploaded {remote}", err=True)
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
    """Print a finished task's stk-mupro.json; exit 0 for a verified, successful Runtime task."""
    client = get_client(profile, state_dir)
    with tempfile.TemporaryDirectory() as folder:
        path = client.download(task_id, "stk-mupro.json", output or Path(folder) / "stk-mupro.json")
        report = json.loads(Path(path).read_text(encoding="utf-8"))
    dump(report)
    if (report.get("verification", {}).get("status") != "passed"
            or client.task(task_id).get("state") != "succeeded"):
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
