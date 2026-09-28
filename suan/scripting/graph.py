"""Explicit analysis graph operations over the desktop's shared graph service."""
from pathlib import Path


def _directories(bindings):
    return {name: str(Path(path).expanduser().resolve()) for name, path in bindings.items()}


class Graph:
    def __init__(self, call):
        self._call = call

    def catalog(self):
        return self._call("graph.catalog", {})["catalog"]

    def presets(self):
        return self._call("graph.presets", {})["presets"]

    def validate(self, graph, *, parameters=None):
        params = {"graph": graph}
        if parameters is not None:
            params["parameters"] = parameters
        return self._call("graph.validate", params)

    def evaluate(self, request, *, eval_id, local_bindings=None, connection=None, node=None,
                 mode="local", wait=None):
        """Execute explicitly and return the full result/Hub-action envelope.

        eval_id belongs to the caller. Local IDs identify active work, not durable idempotency;
        Hub IDs recover the same action. This helper never retries or approves an action.
        """
        params = {"request": request, "eval_id": eval_id, "mode": mode}
        if local_bindings is not None:
            params["local_bindings"] = _directories(local_bindings)
        for key, value in (("connection", connection), ("node", node), ("wait", wait)):
            if value is not None:
                params[key] = value
        return self._call("graph.evaluate", params)

    def cancel(self, eval_id, *, connection=None, node=None):
        """Explicitly cancel local graph work or the matching Hub evaluation, not simulation tasks."""
        params = {"eval_id": eval_id}
        if connection is not None:
            params["connection"] = connection
        if node is not None:
            params["node"] = node
        return self._call("graph.cancel", params)

    def ensure_blobs(self, digests, *, connection=None):
        """Locate graph blobs in the bridge cache; optionally download missing Hub blobs."""
        params = {"sha256": list(digests)}
        if connection is not None:
            params["connection"] = connection
        return self._call("blob.ensure", params)

    def probe(self, pick, *, graph=None, preset=None, context=None, position=None,
              local_bindings=None, connection=None, node=None):
        """Resolve a payload pick and optionally sample its original grid at a world position."""
        params = {"pick": pick}
        if local_bindings is not None:
            params["local_bindings"] = _directories(local_bindings)
        for key, value in (("graph", graph), ("preset", preset), ("context", context), ("position", position),
                           ("connection", connection), ("node", node)):
            if value is not None:
                params[key] = value
        return self._call("probe", params)

    def colormaps(self):
        return self._call("colormaps.list", {})
