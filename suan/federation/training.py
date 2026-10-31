"""Fixed installed linear ClientApp; no remote code, rescaling, services or sends."""
from __future__ import annotations

import importlib.metadata
import math
import time
from uuid import UUID

from .flower import FLOWER_VERSION
from .protocol import model_layout, validate_training_spec
from .updates import decode_arrays, encode_arrays


class TrainingCancelled(RuntimeError):
    pass


def check_cancel(cancel):
    if cancel is not None and cancel():
        raise TrainingCancelled("Federation training cancelled")


def fit(spec, weights, bias, x, y, *, cancel=None):
    """Full-batch mean squared error plus mu/2 times squared base distance.

    Accumulate each example's gradient in float64, then round each updated
    parameter to the owner's exact dtype. This defines the same arithmetic for
    single/multiple targets and avoids participant-specific normalization.
    """
    import numpy as np
    spec = validate_training_spec(spec)
    dtype = "<f4" if spec["dtype"] == "f32" else "<f8"
    weights, bias = np.asarray(weights, dtype=dtype).copy(), np.asarray(bias, dtype=dtype).copy()
    x, y = np.asarray(x, dtype=np.float64), np.asarray(y, dtype=np.float64)
    if (weights.shape != (len(spec["features"]), len(spec["targets"]))
            or bias.shape != (len(spec["targets"]),) or x.ndim != 2 or y.ndim != 2
            or not 1 <= len(x) <= 100000 or len(y) != len(x)
            or x.shape[1] != weights.shape[0] or y.shape[1] != weights.shape[1]
            or any(not np.isfinite(a).all() for a in (weights, bias, x, y))):
        raise ValueError("Invalid fixed trainer inputs")
    base_w, base_b = weights.astype(np.float64), bias.astype(np.float64)
    with np.errstate(over="raise", invalid="raise", divide="raise"):
        for _ in range(spec["steps"]):
            check_cancel(cancel)
            gw, gb = np.zeros_like(base_w), np.zeros_like(base_b)
            for index, (row, truth) in enumerate(zip(x, y)):
                if index % 256 == 0:
                    check_cancel(cancel)
                error = row @ weights.astype(np.float64) + bias.astype(np.float64) - truth
                gw += np.outer(row, error)
                gb += error
            scale = 2.0 / (len(x) * y.shape[1])
            gw = gw * scale + spec["proximal_mu"] * (weights.astype(np.float64) - base_w)
            gb = gb * scale + spec["proximal_mu"] * (bias.astype(np.float64) - base_b)
            weights = np.asarray(weights - spec["learning_rate"] * gw, dtype=dtype)
            bias = np.asarray(bias - spec["learning_rate"] * gb, dtype=dtype)
            if not np.isfinite(weights).all() or not np.isfinite(bias).all():
                raise ValueError("Fixed trainer produced nonfinite parameters")
        check_cancel(cancel)
        error = x @ weights.astype(np.float64) + bias.astype(np.float64) - y
        loss = float(np.mean(error * error))
    if not math.isfinite(loss):
        raise ValueError("Fixed trainer produced a nonfinite loss")
    return weights, bias, loss


def train(spec, model, dataset, *, run_id, round, participant_id, cancel=None):
    """Execute a real Flower ClientApp once, returning only private delta bytes.

    The process launcher must sanitize its environment before calling this.
    Dataset is the verified owner-only x/y numeric capsule wire.
    """
    spec = validate_training_spec(spec)
    base = decode_arrays(model, expected_kind="model", expected_layout=model_layout(spec))
    samples = decode_arrays(dataset, expected_kind="model")
    check_cancel(cancel)
    if (importlib.metadata.version("flwr") != FLOWER_VERSION
            or importlib.metadata.version("numpy") != "2.5.4"):
        raise ValueError("The fixed trainer requires the pinned Flower and NumPy versions")
    import numpy as np
    from flwr.app import ArrayRecord, Context, Metadata, MetricRecord, RecordDict, Message
    from flwr.app.message.message import make_message
    from flwr.clientapp import ClientApp
    from flwr.supercore.task_identity import TaskIdentity

    def arrays(bundle):
        return [np.frombuffer(a["data"], dtype="<f4" if a["dtype"] == "f32" else "<f8").reshape(a["shape"])
                for a in bundle["arrays"]]
    source = arrays(base)
    if (len(samples["arrays"]) != 2 or [a["name"] for a in samples["arrays"]] != ["x", "y"]
            or any(a["dtype"] != "f64" or len(a["shape"]) != 2 for a in samples["arrays"])):
        raise ValueError("The fixed trainer needs a verified local numeric capsule")
    x, y = arrays(samples)
    app = ClientApp()

    @app.train()
    def train_message(message, context):
        values = message.content["arrays"].to_numpy_ndarrays()
        if len(values) != 2:
            raise ValueError("Invalid fixed trainer model")
        w, b, loss = fit(spec, *values, x, y, cancel=cancel)
        return Message(RecordDict({"arrays": ArrayRecord([w, b]),
            "metrics": MetricRecord({"loss": loss, "num-examples": len(x)})}), reply_to=message)

    internal_run = UUID(run_id).int & ((1 << 64) - 1) or 1
    internal_node = int(participant_id[-16:], 16) or 1
    TaskIdentity.run_id, TaskIdentity.node_id, TaskIdentity.task_id = internal_run, internal_node, round
    context = Context(run_id=internal_run, node_id=internal_node, node_config={}, state=RecordDict(), run_config={})
    metadata = Metadata(run_id=internal_run, message_id=f"train-{round}", src_node_id=0,
        dst_node_id=internal_node, reply_to_message_id="", group_id=str(round), created_at=time.time(),
        ttl=300, message_type="train")
    request = make_message(metadata, content=RecordDict({"arrays": ArrayRecord(source)}))
    reply = app(request, context)
    check_cancel(cancel)
    values, metrics = reply.content["arrays"].to_numpy_ndarrays(), dict(reply.content["metrics"])
    if (len(values) != 2 or set(metrics) != {"loss", "num-examples"}
            or type(metrics["num-examples"]) is not int or metrics["num-examples"] != len(x)
            or type(metrics["loss"]) not in (int, float) or not math.isfinite(metrics["loss"])):
        raise ValueError("Invalid fixed ClientApp result")
    delta = []
    for desc, before, after in zip(base["layout"], source, values):
        if list(after.shape) != desc["shape"]:
            raise ValueError("Fixed ClientApp changed the approved layout")
        dtype = "<f4" if desc["dtype"] == "f32" else "<f8"
        with np.errstate(over="raise", invalid="raise"):
            raw = np.asarray(after - before, dtype=dtype).tobytes(order="C")
        delta.append({**desc, "data": raw})
    result = encode_arrays(delta, kind="delta")
    decode_arrays(result, expected_kind="delta", expected_layout=base["layout"])
    return result, {"loss": float(metrics["loss"])}, len(x)
