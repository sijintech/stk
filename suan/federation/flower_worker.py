"""Private, one-attempt Flower process; imported only when explicitly launched.

The coordinator supplies a fresh private job directory with validated model and
delta bundles. This process starts no Flower service and executes no training.
It uses two version-bound internal Flower identity/message helpers; review the
adapter and its independent numerical checks before upgrading the exact pin.
"""
from __future__ import annotations

import importlib.metadata
import json
import os
from pathlib import Path
import sys
import time
from uuid import UUID


def main(argv=None):
    from .flower import (FLOWER_VERSION, JOB_FORMAT, MAX_JOB_BYTES, MAX_JOB_METADATA_BYTES,
                         MAX_RECEIPT_BYTES, RESULT_FORMAT, _json, _read, _strict_json)
    from .updates import MAX_BUNDLE_BYTES, decode_arrays, encode_arrays, validate_round

    argv = sys.argv[1:] if argv is None else argv
    try:
        if len(argv) != 1 or sys.platform != "linux":
            raise ValueError
        directory = Path(argv[0])
        if not directory.is_absolute() or directory.is_symlink() or not directory.is_dir():
            raise ValueError
        if any(os.environ.get(key) != value for key, value in {
            "FLWR_TELEMETRY_ENABLED": "0", "FLWR_TELEMETRY_LOGGING": "0",
            "FLWR_DISABLE_UPDATE_CHECK": "1", "STK_TOKEN_PLAN_API_KEY": ""}.items()):
            raise ValueError
        if "STK_TOKEN_PLAN_MODEL" in os.environ:
            raise ValueError
        if importlib.metadata.version("flwr") != FLOWER_VERSION:
            raise ValueError

        # Defence in depth for a local mathematical worker, not an OS sandbox.
        # In particular, this path never starts SuperLink/SuperNode or gRPC.
        def audit(event, _):
            if event in {"socket.connect", "socket.bind", "socket.getaddrinfo", "socket.sendto"}:
                raise PermissionError("The local algorithm worker does not use a network")
        sys.addaudithook(audit)

        job = _strict_json(_read(directory / "job.json", MAX_JOB_METADATA_BYTES))
        if (type(job) is not dict or set(job) != {"format", "run_id", "round", "spec_sha256",
                "participants", "model_sha256", "updates"} or job["format"] != JOB_FORMAT):
            raise ValueError
        model_raw = _read(directory / "model.bin", MAX_BUNDLE_BYTES)
        base = decode_arrays(model_raw, expected_kind="model")
        if base["sha256"] != job["model_sha256"]:
            raise ValueError
        admitted = validate_round(job["updates"], participants=job["participants"],
            run_id=job["run_id"], round=job["round"], model_sha256=base["sha256"],
            spec_sha256=job["spec_sha256"])
        metric_keys = set(admitted[0]["metrics"])
        if "num-examples" in metric_keys or any(set(x["metrics"]) != metric_keys for x in admitted):
            raise ValueError
        deltas, total = [], len(model_raw)
        for index, item in enumerate(admitted):
            raw = _read(directory / f"update-{index}.bin", MAX_BUNDLE_BYTES)
            total += len(raw)
            if total > MAX_JOB_BYTES:
                raise ValueError
            delta = decode_arrays(raw, expected_kind="delta", expected_layout=base["layout"])
            if delta["sha256"] != item["update_sha256"] or delta["bytes"] != item["update_bytes"]:
                raise ValueError
            deltas.append(delta)

        import numpy as np
        from flwr.app import ArrayRecord, Metadata, MetricRecord, RecordDict
        from flwr.app.message.message import make_message
        from flwr.serverapp.strategy import FedAvg
        from flwr.supercore.task_identity import TaskIdentity

        internal_run = UUID(job["run_id"]).int & ((1 << 64) - 1) or 1
        TaskIdentity.run_id, TaskIdentity.node_id, TaskIdentity.task_id = internal_run, 0, 1

        def arrays(bundle):
            return [np.frombuffer(x["data"], dtype="<f4" if x["dtype"] == "f32" else "<f8").reshape(x["shape"])
                    for x in bundle["arrays"]]

        original = arrays(base)
        replies = []
        for index, (item, delta) in enumerate(zip(admitted, deltas)):
            with np.errstate(over="raise", invalid="raise"):
                # Only deltas leave the owning nodes. Flower receives complete
                # candidate weights reconstructed against the exact base model.
                trained = [a + b for a, b in zip(original, arrays(delta))]
            metrics = {**item["metrics"], "num-examples": item["num_examples"]}
            content = RecordDict({"arrays": ArrayRecord(trained), "metrics": MetricRecord(metrics)})
            metadata = Metadata(run_id=internal_run, message_id=f"update-{index}",
                src_node_id=index + 1, dst_node_id=0, reply_to_message_id=f"request-{index}",
                group_id=str(job["round"]), created_at=time.time(), ttl=30, message_type="train")
            replies.append(make_message(metadata, content=content))
        strategy = FedAvg(min_train_nodes=3, min_evaluate_nodes=3, min_available_nodes=3)
        aggregated, aggregated_metrics = strategy.aggregate_train(job["round"], replies)
        if aggregated is None or aggregated_metrics is None:
            raise ValueError
        values = aggregated.to_numpy_ndarrays()
        if len(values) != len(base["arrays"]):
            raise ValueError
        result_arrays = []
        for descriptor, value in zip(base["arrays"], values):
            if list(value.shape) != descriptor["shape"]:
                raise ValueError
            with np.errstate(over="raise", invalid="raise"):
                raw = np.asarray(value, dtype="<f4" if descriptor["dtype"] == "f32" else "<f8").tobytes(order="C")
            result_arrays.append({"name": descriptor["name"], "dtype": descriptor["dtype"],
                                  "shape": descriptor["shape"], "data": raw})
        result = encode_arrays(result_arrays, kind="model")
        decoded = decode_arrays(result, expected_kind="model", expected_layout=base["layout"])
        metrics = dict(aggregated_metrics)
        if set(metrics) != metric_keys:
            raise ValueError
        receipt = {"format": RESULT_FORMAT, "run_id": job["run_id"], "round": job["round"],
            "source_model_sha256": base["sha256"], "spec_sha256": job["spec_sha256"],
            "participants": [x["participant_id"] for x in admitted],
            "model_sha256": decoded["sha256"], "model_bytes": len(result),
            "num_examples": sum(x["num_examples"] for x in admitted), "metrics": metrics,
            "framework": {"name": "flwr", "version": FLOWER_VERSION}}
        encoded = _json(receipt, MAX_RECEIPT_BYTES)
        # No stdout protocol and no publication into a model registry.
        with (directory / "result.bin").open("xb") as stream:
            stream.write(result)
            stream.flush()
            os.fsync(stream.fileno())
        with (directory / "result.json").open("xb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        return 0
    except Exception:
        return 2  # Fixed public outcome; never disclose local paths or raw arrays.


if __name__ == "__main__":
    raise SystemExit(main())
