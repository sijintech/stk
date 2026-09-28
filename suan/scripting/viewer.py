"""Control the shared local Viewer through the desktop's main-thread operation executor."""
import math
from pathlib import Path
import time


class Viewer:
    def __init__(self, call):
        self._call = call

    def _operation(self, name, params=None, *, expected_source=None):
        params = dict(params or {})
        if expected_source is not None:
            params["expected_source"] = expected_source
        return self._call("ui.viewer." + name, params)

    def status(self):
        return self._operation("status")

    def presets(self):
        return self._operation("presets")

    def open(self, path, *, preset=None, parameters=None, focus=True):
        """Open a payload, result/run directory or scientific field file. Evaluation is asynchronous; use status/wait."""
        params = {"path": str(Path(path).expanduser().resolve()), "focus": focus}
        if preset is not None:
            params["preset"] = preset
        if parameters is not None:
            params["parameters"] = parameters
        return self._operation("open", params)

    def close(self, *, expected_source=None):
        return self._operation("close", expected_source=expected_source)

    def configure(self, *, parameters=None, auto_evaluate=None, overlays=None, prefetch=None,
                  fps=None, loop=None, expected_source=None):
        """Validate all supplied fields before applying; parameter edits follow auto_evaluate."""
        values = {"parameters": parameters, "auto_evaluate": auto_evaluate, "overlays": overlays,
                  "prefetch": prefetch, "fps": fps, "loop": loop}
        return self._operation("configure", {key: value for key, value in values.items() if value is not None},
                               expected_source=expected_source)

    def preset(self, identity, *, expected_source=None):
        return self._operation("preset", {"id": identity}, expected_source=expected_source)

    def evaluate(self, *, expected_source=None):
        return self._operation("evaluate", expected_source=expected_source)

    def cancel(self, *, expected_source=None):
        """Cancel Viewer graph work; this does not cancel Runtime simulation tasks."""
        return self._operation("cancel", expected_source=expected_source)

    def layer(self, identity, *, visible=None, opacity=None, expected_source=None):
        params = {"id": identity}
        if visible is not None:
            params["visible"] = visible
        if opacity is not None:
            params["opacity"] = opacity
        return self._operation("layer", params, expected_source=expected_source)

    def step(self, index, *, expected_source=None):
        return self._operation("step", {"index": index}, expected_source=expected_source)

    def play(self, playing=True, *, expected_source=None):
        return self._operation("play", {"playing": playing}, expected_source=expected_source)

    def reset_camera(self, *, expected_source=None):
        return self._operation("reset_camera", expected_source=expected_source)

    def wait(self, *, timeout=120, interval=0.1):
        """Wait for current Viewer work; timeouts never cancel it, source changes abort waiting."""
        if (type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout < 0
                or type(interval) not in (int, float) or not math.isfinite(interval) or interval <= 0):
            raise ValueError("timeout must be finite and non-negative; interval must be finite and positive")
        deadline, source = time.monotonic() + timeout, None
        while True:
            status = self.status()
            current = status["source"]["key"]
            if source is not None and current != source:
                raise RuntimeError("The Viewer source changed while waiting; inspect its current state")
            source = current
            if (not status["evaluating"] and not status["pending_edit"]
                    and (status["has_payload"] or status["error"] or status["metadata_error"] or status["source"]["kind"] == "none")):
                return status
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Viewer evaluation is still pending; waiting timed out without cancelling it")
            time.sleep(min(interval, remaining))
