"""muFerro legacy adapter: native outputs to monitoring events v1 ("adapt" mode).

`python -m suan.mupro run` is the only writer of ``$STK_MONITOR_PATH``: it removes the
variable from the solver's environment and a thread polls the case directory every
POLL_INTERVAL seconds (docs/specs/stk-events-v1.md §6):

- before exec: ``run.started {app: "muFerro", total_steps, ranks}``;
- each new ``mupro_progress.jsonl`` line: ``progress {step, completed_steps, total_steps, fraction}``
  (the latest line of each poll; the emitter coalesces to at most one per second);
- the ``energy_out.dat`` header: ``metric.declare`` for the five energies (labels from the
  header's right-aligned 18-character columns, unit ``normalized``), then each row
  ``kt: N energy: e1..e5`` (``ENERGY_ROW``): ``metrics {step: N, values}``; a non-finite or
  unreadable value is written as ``"NaN"``/``"Inf"``/``"-Inf"`` plus
  ``message {warning, code: "nonfinite_energy"}``;
- ``<Stem>.<step:08d>.dat`` (``FRAME``) whose size and mtime stayed the same over two polls
  while progress has reached its step, or any remaining frame once the solver has exited
  with code 0: ``frame {dataset: Stem, step, path, reader: "mupro.dat@1", components, size}``.
  After a non-zero exit only frames at or before the last progress step are published, since
  later ones may have been cut off mid-write;
- ``mupro_completion.json`` appearing: ``message {info, code: "native_completion"}``;
- after exit and ``verify_run``: ``verification`` and ``run.completed``.

The adapter never fails the run: errors go to stderr, and the launcher's exit codes and
``stk-mupro.json`` are the same with or without monitoring. ``replay`` applies the same
rules to a finished run directory STK did not launch.
"""

from pathlib import Path
import json
import math
import os
import platform

from suan.monitor.emit import Emitter
from suan.monitor.events import VERIFICATION_STATUSES
from suan.monitor.tail import LineTail, PollThread, StableFiles, report, safe_call
from .run import COMPONENTS, ENERGY_ROW, FRAME, VERIFIER, _case_folder, _header, read_case, verify_run

APP = "muFerro"
READER = "mupro.dat@1"
POLL_INTERVAL = 2.0  # seconds between polls of the case directory
STABLE_POLLS = 2  # a frame's size and mtime must match over this many polls
ENERGY_METRICS = ("elastic_energy", "electric_energy", "landau_energy", "gradient_energy", "total_energy")
DEFAULT_LABELS = ("Elastic Energy", "Electric Energy", "Landau Energy", "Gradient P Energy", "Total Energy")
LABEL_WIDTH = 18  # energy header columns are right-aligned, 18 characters wide like the e18.10 values
MAX_WARNINGS = 5  # per warning code; one more note says that further ones are suppressed
FRAME_COMPONENTS = {**COMPONENTS, "Polar": 3}


def parse_progress(line):
    """Progress data from one ``mupro_progress.jsonl`` line, or None when it is unreadable."""
    try:
        record = json.loads(line)
    except (ValueError, RecursionError):
        return None
    if not isinstance(record, dict):
        return None
    data = {key: record[key] for key in ("step", "completed_steps", "total_steps")
            if type(record.get(key)) is int and record[key] >= 0}
    if not data:
        return None
    done, total = data.get("completed_steps"), data.get("total_steps")
    if done is not None and total:
        data["fraction"] = min(1.0, done / total)
    return data


def parse_energy(line):
    """``(step, values)`` for an energy row; ``(step, None)`` without five values; None for other lines.

    Values are floats keyed by ENERGY_METRICS; Fortran ``D`` exponents are accepted and a
    token that is not a number (``NaN``, overflow asterisks) becomes NaN.
    """
    match = ENERGY_ROW.fullmatch(line)
    if not match:
        return None
    tokens = match[2].split()
    if len(tokens) != len(ENERGY_METRICS):
        return int(match[1]), None
    values = {}
    for name, token in zip(ENERGY_METRICS, tokens):
        try:
            values[name] = float(token.replace("D", "E").replace("d", "e"))
        except ValueError:
            values[name] = math.nan
    return int(match[1]), values


def header_labels(line):
    """Series labels from the energy header's last five 18-character columns, else DEFAULT_LABELS."""
    text = line.rstrip()
    width = LABEL_WIDTH * len(ENERGY_METRICS)
    if len(text) <= width:
        return DEFAULT_LABELS
    columns = text[-width:]
    labels = tuple(columns[i * LABEL_WIDTH:(i + 1) * LABEL_WIDTH].strip() for i in range(len(ENERGY_METRICS)))
    return labels if all(labels) and text[:-width].strip().lower() == "step" else DEFAULT_LABELS


class MuferroAdapter:
    """Poll one muFerro case directory and write what is new through ``emitter``."""

    def __init__(self, emitter, folder, case_dir=".", stable_polls=STABLE_POLLS):
        self.emitter = emitter
        self.folder = Path(folder)
        self.prefix = "" if case_dir in ("", ".") else case_dir.rstrip("/") + "/"
        self.progress = LineTail(self.folder / "mupro_progress.jsonl")
        self.energy = LineTail(self.folder / "energy_out.dat")
        self.frames = StableFiles(self.folder, FRAME, stable_polls)
        self.progress_step = None
        self.declared = False
        self.completion_seen = False
        self._warnings = {}

    def poll(self, final=False, exit_code=None):
        """One pass; ``final`` once the solver has exited with ``exit_code``."""
        safe_call(self._poll_progress, final)
        safe_call(self._poll_energy, final)
        safe_call(self._poll_frames, final, exit_code)
        safe_call(self._poll_completion, final)

    def _warn(self, code, text):
        count = self._warnings[code] = self._warnings.get(code, 0) + 1
        if count <= MAX_WARNINGS:
            self.emitter.message("warning", text, code=code)
        elif count == MAX_WARNINGS + 1:
            self.emitter.message("warning", f"Further {code} warnings are suppressed", code=code)

    def _poll_progress(self, final):
        lines = self.progress.drain() if final else self.progress.poll()
        first = self.progress.line_number - len(lines)
        latest = None
        for number, line in enumerate(lines, first + 1):
            if not line.strip():
                continue
            data = parse_progress(line)
            if data is None:
                self._warn("malformed_progress", f"mupro_progress.jsonl line {number} is not a progress record")
                continue
            latest = data
            if "step" in data:
                self.progress_step = max(data["step"], -1 if self.progress_step is None else self.progress_step)
        if latest is not None:
            self.emitter.progress(latest.get("step"), latest.get("total_steps"),
                                  completed_steps=latest.get("completed_steps"), fraction=latest.get("fraction"))

    def _declare(self, labels):
        if not self.declared:
            self.declared = True
            for name, label in zip(ENERGY_METRICS, labels):
                self.emitter.declare(name, "normalized", label=label, group="energy")

    def _poll_energy(self, final):
        lines = self.energy.drain() if final else self.energy.poll()
        first = self.energy.line_number - len(lines)
        for index, line in enumerate(lines, first):
            if not line.strip():
                continue
            parsed = parse_energy(line)
            if parsed is None:
                if index == 0:
                    self._declare(header_labels(line))
                else:
                    self._warn("malformed_energy_row", f"energy_out.dat line {index + 1} is not an energy row")
                continue
            step, values = parsed
            if values is None:
                self._warn("malformed_energy_row", f"energy_out.dat line {index + 1} does not hold five energies")
                continue
            self._declare(DEFAULT_LABELS)  # a trace without a header
            self.emitter.metrics(values, step=step)
            bad = [name for name, value in values.items() if not math.isfinite(value)]
            if bad:
                self._warn("nonfinite_energy", f"Non-finite energy at step {step}: {', '.join(bad)}")

    def _poll_frames(self, final, exit_code):
        clean_exit = final and exit_code == 0
        candidates = sorted(self.frames.candidates(force=final), key=lambda item: (int(item[1][2]), item[1][1]))
        for name, match, size in candidates:
            stem, step = match[1], int(match[2])
            if not clean_exit and (self.progress_step is None or self.progress_step < step):
                continue
            components = FRAME_COMPONENTS.get(stem)
            if components is None:
                header = _header(self.folder / name)
                components = header[1] if header else None
            self.emitter.frame(stem, step, self.prefix + name, reader=READER, components=components, size=size)
            self.frames.publish(name)

    def _poll_completion(self, final):
        path = self.folder / "mupro_completion.json"
        if self.completion_seen or not path.is_file():
            return
        try:
            with open(path, "rb") as stream:
                data = json.loads(stream.read(65536))
            if not isinstance(data, dict):
                raise ValueError("not an object")
            details = ", ".join(f"{key}={data[key]}" for key in ("completed_steps", "final_step") if key in data)
            text = "muFerro wrote mupro_completion.json" + (f": {details}" if details else "")
        except (OSError, ValueError, RecursionError):
            if not final:
                return  # it may still be being written
            text = "muFerro wrote an unreadable mupro_completion.json"
        self.completion_seen = True
        self.emitter.message("info", text, code="native_completion")


class MuferroMonitor:
    """Launcher glue for adapt mode: no-ops without ``$STK_MONITOR_PATH``; no method raises."""

    def __init__(self, emitter=None, interval=None, lifecycle_src="launcher"):
        self.emitter = emitter if emitter is not None else Emitter(src="adapter")
        self.interval = POLL_INTERVAL if interval is None else interval
        self.lifecycle_src = lifecycle_src
        self.adapter = None
        self.launched = False
        self._thread = None

    @property
    def enabled(self):
        return self.emitter.enabled

    def _emit(self, event_type, data):
        self.emitter.emit(event_type, {key: value for key, value in data.items() if value is not None},
                          src=self.lifecycle_src)

    def started(self, folder, case_dir, case, ranks):
        """Before exec: ``run.started`` and the adapter for the case directory."""
        if not self.enabled:
            return

        def start():
            self._emit("run.started", {"app": APP, "total_steps": case["steps"], "ranks": ranks,
                                       "host": platform.node() or None, "pid": os.getpid()})
            self.adapter = MuferroAdapter(self.emitter, folder, case_dir)

        safe_call(start)

    def watch(self):
        """The solver is running: poll its outputs on a daemon thread."""
        self.launched = True
        if self.adapter is not None:
            self._thread = safe_call(lambda: PollThread(self.adapter.poll, self.interval, "stk-muferro-monitor").start())

    def stop(self, exit_code):
        """The solver has exited: stop polling, then read everything it left (the final pass)."""
        if self.adapter is None:
            return
        if self._thread is not None and not safe_call(self._thread.stop):
            report("the muFerro adapter thread did not stop; skipping its final pass")
            return
        safe_call(self.adapter.poll, final=True, exit_code=exit_code)

    def finish(self, record):
        """After ``stk-mupro.json`` is final: ``verification`` (when the solver ran), ``run.completed``, close."""
        if not self.enabled:
            return
        safe_call(self._finish, record)
        safe_call(self.emitter.close)

    def _finish(self, record):
        if self.launched:
            verification = record.get("verification") or {}
            status = verification.get("status")
            self._emit("verification", {
                "verifier": verification.get("verifier") or VERIFIER,
                "status": status if status in VERIFICATION_STATUSES else "skipped",  # "not_run": the solver failed
                "failed_checks": [check.get("id") for check in verification.get("checks") or []
                                  if check.get("status") == "fail"]})
        self._emit("run.completed", {"status": "succeeded" if record.get("state") == "succeeded" else "failed",
                                     "classification": record.get("classification"),
                                     "reason": record.get("reason") or None})


def replay(emitter, work_dir=".", case_dir="."):
    """Write the events of a finished muFerro run directory; returns its ``verify_run`` result.

    For runs STK did not launch: the same rules as a live run, with every frame published and
    every event from the emitter's source (use ``Emitter(path, src="adapter")``). The emitter
    is closed afterwards. Raises MuproError when the case cannot be read.
    """
    work = Path(work_dir).resolve()
    case_dir, folder = _case_folder(work, case_dir)
    case = read_case(folder, work)
    monitor = MuferroMonitor(emitter, lifecycle_src=emitter.src)
    monitor.started(folder, case_dir, case, None)
    monitor.launched = True
    monitor.stop(0)
    result = verify_run(work, case_dir)
    monitor.finish({**result, "state": "succeeded" if result["verification"]["status"] == "passed" else "failed"})
    return result
