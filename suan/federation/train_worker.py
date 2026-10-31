"""Private Runtime entrypoint for one owner-approved installed ClientApp attempt.

All dataset/model/delta/job files stay outside Runtime's public work directory.
The only public output is receipt.json, containing an opaque job ID and state.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if sys.platform != "linux" or len(args) not in (1, 2):
        return 2
    if len(args) == 1:
        # Re-exec before importing optional dependencies. No credentials, proxies,
        # arbitrary loader variables or product model settings reach Flower.
        allowed = ("PATH", "LANG", "LC_ALL", "TEMP", "TMP", "STK_TASK_ID")
        env = {key: os.environ[key] for key in allowed if key in os.environ}
        env.update({"STK_TOKEN_PLAN_API_KEY": "", "FLWR_TELEMETRY_ENABLED": "0",
                    "FLWR_TELEMETRY_LOGGING": "0", "FLWR_DISABLE_UPDATE_CHECK": "1",
                    "FLWR_HOME": str(Path(args[0]).absolute() / "flower-state"),
                    "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"})
        os.execve(sys.executable, [sys.executable, "-I", "-m", "suan.federation.train_worker", "--sealed", args[0]], env)
    if args[0] != "--sealed":
        return 2
    try:
        if any(os.environ.get(key) != value for key, value in {
                "STK_TOKEN_PLAN_API_KEY": "", "FLWR_TELEMETRY_ENABLED": "0",
                "FLWR_TELEMETRY_LOGGING": "0", "FLWR_DISABLE_UPDATE_CHECK": "1"}.items()
                ) or "STK_TOKEN_PLAN_MODEL" in os.environ or os.environ.get("FLWR_HOME") != str(Path(args[1]).absolute() / "flower-state"):
            raise ValueError
        def no_network(event, _):
            if event in {"socket.connect", "socket.bind", "socket.getaddrinfo", "socket.sendto"}:
                raise PermissionError("The private fixed trainer has no network operations")
        sys.addaudithook(no_network)
        run(Path(args[1]))
        return 0
    except Exception:
        # Never print a dataset, model value, private path or dependency traceback.
        print("Federation training did not produce an approved result", file=sys.stderr)
        return 2


def run(directory):
    from suan.materials.jobs import Lease, private_directory
    from . import inputs
    from .consent import ConsentRegistry
    from .protocol import model_layout, training_spec_sha256, validate_message, validate_training_spec
    from .training import check_cancel, train
    from .updates import decode_arrays

    directory = private_directory(directory, create=False)
    root = directory.parent.parent
    if directory.parent.name != "jobs" or len(directory.name) != 64 or any(c not in "0123456789abcdef" for c in directory.name):
        raise ValueError("Invalid private training identity")
    with Lease(directory / "worker.lock"):
        job = inputs.read_json(directory / "job.json")
        if type(job) is not dict or set(job) != {"format", "request", "spec", "dataset_id"} or job["format"] != "stk.federation-train-job/1":
            raise ValueError("Invalid private training job")
        message = validate_message(job["request"])
        spec = validate_training_spec(job["spec"])
        if message["operation"] != "train" or training_spec_sha256(spec) != message["spec_sha256"]:
            raise ValueError("Private training specification differs")
        consent = ConsentRegistry(root / "consent")
        expected = {key: message[key] for key in ("coordinator_id", "run_id", "round", "participant_id", "dataset_sha256", "spec_sha256")}
        with consent.authorized(message["grant_id"], **expected) as grant:
            if grant.dataset_id != job["dataset_id"] or grant.as_dict()["model_layout"] != model_layout(spec):
                raise ValueError("Private training grant differs")
        def cancelled():
            return (directory / "cancel").exists()
        check_cancel(cancelled)
        if (directory / "attempt.json").exists():
            raise ValueError("A private trainer attempt is never replayed")
        inputs.write_json(directory / "attempt.json", {"started": True})
        manifest, dataset = inputs.load(root / "datasets" / inputs.uuid(job["dataset_id"]))
        if manifest["dataset_sha256"] != message["dataset_sha256"]:
            raise ValueError("Private training dataset differs")
        if (manifest["feature_names"] != [x["name"] for x in spec["features"]]
                or manifest["target_names"] != [x["name"] for x in spec["targets"]]):
            raise ValueError("Private training column order differs")
        model = inputs.read_bytes(directory / "model.bin")
        decoded = decode_arrays(model, expected_kind="model", expected_layout=model_layout(spec))
        if decoded["sha256"] != message["model"]["sha256"] or len(model) != message["model"]["bytes"]:
            raise ValueError("Private training base differs")
        delta, metrics, count = train(spec, model, dataset, run_id=message["run_id"], round=message["round"],
                                      participant_id=message["participant_id"], cancel=cancelled)
        decoded = decode_arrays(delta, expected_kind="delta", expected_layout=model_layout(spec))
        result = {"format": "stk.federation-train-result/1",
                  "request_sha256": __import__("hashlib").sha256(inputs.canonical(message)).hexdigest(),
                  "delta_sha256": decoded["sha256"], "delta_bytes": len(delta),
                  "num_examples": count, "metrics": metrics}
        with Lease(root / "node.lock", timeout=10):
            with consent.authorized(message["grant_id"], **expected):
                check_cancel(cancelled)
                inputs.check_budget(root, len(delta))
                inputs.write_bytes(directory / "delta.bin", delta)
                inputs.write_json(directory / "result.json", result)
        inputs.write_json(Path.cwd() / "receipt.json", {"format": "stk.federation-task-receipt/1",
                                                        "job_id": directory.name, "state": "succeeded"})


if __name__ == "__main__":
    sys.exit(main())
