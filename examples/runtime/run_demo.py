"""Run the identical parameter sweep through local, PBS or Slurm backends."""

import argparse
from importlib.metadata import PackageNotFoundError, version
import json
import math
from pathlib import Path
import platform
import shutil
import sys
import tempfile
import time
import uuid

from suan.runtime.cli import get_client
from suan.runtime.common import atomic_json, now, sha256
from suan.runtime.models import TaskSpec, TERMINAL
from toolkits.sjob.core import schedule_batch, create_batch


def verify_outputs(root, amplitude):
    """Check the manufactured field itself as well as its summary and preview."""
    import numpy as np
    from matplotlib.image import imread
    from toolkits.sviz.field import read_field

    summary = json.loads((root / "summary.json").read_text(encoding="utf-8"))
    expected = {
        "amplitude": amplitude,
        "mean": amplitude * 13,
        "minimum": 0,
        "maximum": amplitude * 26,
    }
    for name, value in expected.items():
        actual = summary.get(name)
        if (
            isinstance(actual, bool)
            or not isinstance(actual, (int, float))
            or not math.isclose(actual, value, rel_tol=0, abs_tol=1e-12)
        ):
            raise ValueError(
                f"Summary mismatch for {name}: expected {value}, got {actual}"
            )
    field = np.fromfunction(lambda x, y, z: amplitude * (x + 2 * y + 3 * z), (8, 6, 4))[
        ..., None
    ]
    errors = {}
    for name in ("field.dat", "field.vtk"):
        actual = read_field(root / name)
        if actual.shape != field.shape or not np.allclose(
            actual, field, rtol=0, atol=1e-12
        ):
            raise ValueError(
                f"{name} does not match the expected (8, 6, 4) acceptance field"
            )
        errors[name] = float(np.max(np.abs(actual - field)))
    preview = imread(root / "preview.png")
    if (
        preview.ndim != 3
        or min(preview.shape[:2]) <= 0
        or preview.shape[2] not in (3, 4)
    ):
        raise ValueError("Preview is not a valid RGB/RGBA PNG")
    return {
        "summary": summary,
        "expected_summary": expected,
        "absolute_tolerance": 1e-12,
        "field_max_absolute_error": errors,
        "preview_shape": list(preview.shape),
    }


def observe_task(client, item, record=None, logs=False):
    record = record if record is not None else client.task(item["id"])
    item.update(
        {
            key: record[key]
            for key in (
                "state",
                "backend_id",
                "exit_code",
                "reason",
                "created_at",
                "started_at",
                "finished_at",
                "input_manifest",
            )
            if key in record
        }
    )
    if logs:
        excerpts = {}
        for stream in ("stdout", "stderr", "wrapper", "scheduler.out", "scheduler.err"):
            chunk = client.logs(item["id"], stream)
            # Keep a bounded diagnostic excerpt; full logs remain in the runtime.
            excerpts[stream] = {
                "text": chunk["bytes"][:65536].decode("utf-8", errors="replace"),
                "next_offset": min(len(chunk["bytes"]), 65536),
                "excerpt_limit_bytes": 65536,
            }
        item["logs"] = excerpts


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-dir")
    parser.add_argument("--profile")
    parser.add_argument("--backend", choices=["local", "pbs", "slurm"], default="local")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=600)
    parser.add_argument("--queue")
    parser.add_argument("--account")
    args = parser.parse_args(argv)
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("--timeout must be positive and finite")
    resources = {k: getattr(args, k) for k in ("queue", "account") if getattr(args, k)}
    if args.backend == "local" and resources:
        parser.error("--queue and --account require a PBS or Slurm backend")
    here = Path(__file__).resolve().parent
    began = time.monotonic()
    run_id = uuid.uuid4().hex
    report_path = args.output.resolve() / f"acceptance-{run_id}.json"
    try:
        stk_version = version("suan_toolkits")
    except PackageNotFoundError:
        stk_version = "source checkout (distribution metadata unavailable)"
    report = {
        "schema_version": 1,
        "case": "deterministic-field-io-v1",
        "run_id": run_id,
        "backend": args.backend,
        "resources": resources,
        "started_at": now(),
        "command": [
            sys.executable,
            str(Path(__file__).resolve()),
            *(sys.argv[1:] if argv is None else argv),
        ],
        "status": "running",
        "verified": False,
        "tasks": [],
        "client_environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "stk_version": stk_version,
        },
        "source_sha256": {
            p.relative_to(here).as_posix(): sha256(p)
            for p in [
                Path(__file__).resolve(),
                here / "batch.json",
                *sorted((here / "inputs").iterdir()),
            ]
        },
    }

    def save():
        report["elapsed_seconds"] = time.monotonic() - began
        atomic_json(report_path, report)

    # Persist before any HTTP request, then before each submission. A response
    # lost after scheduler acceptance still leaves the exact spec and retry key.
    save()
    print(f"Acceptance report: {report_path}", file=sys.stderr)
    client = None
    exit_code = 0
    try:
        client = get_client(args.profile, args.state_dir)
        report["endpoint"] = client.url
        report["health"] = client.health()
        workspace = client.create_workspace("STK acceptance: " + args.backend)["id"]
        report["workspace_id"] = workspace
        save()
        with tempfile.TemporaryDirectory(prefix="stk-demo-") as temp:
            work = Path(temp)
            for path in (here / "inputs").iterdir():
                shutil.copy2(path, work / path.name)
            batch = schedule_batch(here / "batch.json", work)
            folders = create_batch(["@input.json", "simulate.py"], work, batch)
            for folder in folders:
                for path in folder.iterdir():
                    client.upload(workspace, path)
                amplitude = json.loads((folder / "input.json").read_text())["amplitude"]
                spec = TaskSpec(
                    workspace,
                    ["{python}", "simulate.py"],
                    backend=args.backend,
                    name=f"amplitude={amplitude}",
                    resources=resources,
                    inputs=["input.json", "simulate.py"],
                    outputs=[
                        "field.dat",
                        "field.vtk",
                        "preview.png",
                        "summary.json",
                        "environment.json",
                    ],
                )
                item = {
                    "idempotency_key": f"acceptance-{run_id}-{len(report['tasks'])}",
                    "amplitude": amplitude,
                    "spec": spec.to_dict(),
                    "state": "submitting",
                    "verified": False,
                }
                report["tasks"].append(item)
                save()
                task = client.submit(spec, item["idempotency_key"])
                item["id"] = task["id"]
                observe_task(client, item, task)
                save()
        for item in report["tasks"]:
            record = client.wait(item["id"], timeout=args.timeout)
            observe_task(client, item, record, logs=True)
            save()
            if record["state"] != "succeeded":
                raise RuntimeError(
                    f"Task {item['id']} {record['state']}: {record.get('reason', '')}"
                )
            item["artifacts"] = client.artifacts(item["id"])
            root = args.output / item["id"]
            for artifact in item["artifacts"]:
                client.download(item["id"], artifact["path"], root / artifact["path"])
            item["verification"] = verify_outputs(root, item["amplitude"])
            item["compute_environment"] = json.loads(
                (root / "environment.json").read_text(encoding="utf-8")
            )
            item["verified"] = True
            save()
        if not report["tasks"]:
            raise ValueError("Acceptance batch did not generate any tasks")
        report.update(status="succeeded", verified=True)
    except (Exception, KeyboardInterrupt) as exc:
        exit_code = 130 if isinstance(exc, KeyboardInterrupt) else 1
        status = (
            "interrupted"
            if exit_code == 130
            else "timed_out"
            if isinstance(exc, TimeoutError)
            else "failed"
        )
        message = str(exc).replace(client.token, "[redacted]") if client else str(exc)
        report.update(
            status=status, error={"type": type(exc).__name__, "message": message}
        )
        if client:
            for item in report["tasks"]:
                if "id" not in item:
                    continue
                try:
                    record = client.task(item["id"])
                    observe_task(client, item, record, logs=True)
                except Exception:
                    item["observation_error"] = (
                        "Runtime unavailable; last saved observation retained."
                    )
        report["active_task_ids"] = [
            item["id"]
            for item in report["tasks"]
            if "id" in item and item["state"] not in TERMINAL
        ]
        print(
            f"Acceptance {status}; see {report_path}. Submitted tasks remain in the runtime.",
            file=sys.stderr,
        )
    finally:
        report["finished_at"] = now()
        save()
    print(
        json.dumps(
            {
                "backend": args.backend,
                "tasks": [t["id"] for t in report["tasks"] if "id" in t],
                "elapsed_seconds": report["elapsed_seconds"],
                "verified": report["verified"],
                "status": report["status"],
                "report": str(report_path),
            },
            indent=2,
        )
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
