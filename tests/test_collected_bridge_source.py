"""Collected-source proofs through the strict child-process bridge and its graph worker.

A collected MuPRO result is opened in the Viewer with a *source proof*: the optional outer
``local_proofs`` mapping of ``graph.evaluate`` and ``probe`` names, per local binding, the project
root, the canonical case folder and the registered ``{path, sha256}`` files (project-relative, under
the case folder). ``local_bindings`` still names the case directory, and the ``graph.evaluate``
request itself is unchanged.

Everything here runs ``python -m suan.desktop_bridge --stdio --strict`` as a child process
(:class:`test_desktop_bridge.ProcessBridge`, every message checked against the bridge schema), whose
graph evaluation runs in the separate graph worker subprocess. The fields are tiny synthetic MuPRO
DAT files read by an ordinary ``stk.source.file@1`` graph; no VTK, no native window.

* An unguarded local binding keeps working and follows the current bytes (control).
* A guarded evaluation and probe accept the registered bytes, reject an in-place rewrite that keeps
  the inode, size and mtime -- also when the graph cache already holds a value for the rewritten
  bytes and after a clean sample primed the bridge's grid cache -- and accept again once the original
  bytes are back.
* A guarded binding exposes only the manifest files.
* Hub mode refuses ``local_proofs``; neither the proof nor the project root reaches the hub.
"""
import json
import os
from pathlib import Path
import sys

import pytest

from test_desktop_bridge import ProcessBridge, bridge_env  # noqa: F401 (fixture)

np = pytest.importorskip("numpy")

GRID = (4, 3, 2)
CASE = "runs/case-1"
POINT = (1, 2, 1)  # grid index of the probed (and mutated) sample
SLOW = 180


def _field(bump=0.0):
    values = np.zeros((*GRID, 3))
    values[..., 0] = np.arange(np.prod(GRID)).reshape(GRID) / 8
    values[..., 1] = 0.25
    values[..., 2] = -0.5
    values[POINT + (0,)] += bump
    return values


def _dat_bytes(values, scratch):
    from suan.data.dat import write_dat
    write_dat(scratch, values, component_shape=(3,))
    data = Path(scratch).read_bytes()
    Path(scratch).unlink()
    return data


def _sha256(data):
    import hashlib
    return hashlib.sha256(data).hexdigest()


def _graph(path="field.dat"):
    return {"schema": "stk.graph/1", "catalog": {"stk": 1}, "nodes": [
        {"id": "src", "type": "stk.source.file@1", "params": {"binding": "run", "path": path}},
        {"id": "stats", "type": "stk.analysis.statistics@1", "inputs": {"in": {"from": "src.out"}}}],
        "outputs": {"stats": "stats.out"}}


class Collected:
    """A project folder with one collected case: ``field.dat`` registered, ``other.dat`` not."""

    def __init__(self, tmp_path):
        self.project_root = tmp_path / "project"
        self.case_dir = self.project_root / CASE
        self.case_dir.mkdir(parents=True)
        self.clean = _dat_bytes(_field(), tmp_path / "clean.dat")
        self.changed = _dat_bytes(_field(bump=0.5), tmp_path / "changed.dat")
        # A same-size rewrite: the DAT columns have a fixed width.
        assert len(self.clean) == len(self.changed) and self.clean != self.changed
        self.field = self.case_dir / "field.dat"
        self.field.write_bytes(self.clean)
        (self.case_dir / "other.dat").write_bytes(self.clean)
        self.bindings = {"run": str(self.case_dir)}
        self.proofs = {"run": {"project_root": str(self.project_root), "case_path": CASE,
                               "files": [{"path": f"{CASE}/field.dat", "sha256": _sha256(self.clean)}]}}

    def rewrite(self, data):
        """Rewrite ``field.dat`` in place, keeping its inode, size and mtime."""
        before = os.stat(self.field)
        with open(self.field, "r+b") as stream:
            stream.write(data)
            stream.truncate()
        os.utime(self.field, ns=(before.st_atime_ns, before.st_mtime_ns))
        after = os.stat(self.field)
        assert (after.st_ino, after.st_size, after.st_mtime_ns) == (before.st_ino, before.st_size, before.st_mtime_ns)
        assert self.field.read_bytes() == data


@pytest.fixture
def collected(tmp_path):
    return Collected(tmp_path)


@pytest.fixture
def bridge(bridge_env):  # noqa: F811
    harness = ProcessBridge(bridge_env / "bridge")
    yield harness
    try:
        code = harness.close()  # EOF: graceful exit; also asserts zero schema violations
    except BaseException:
        if harness.process.poll() is None:
            harness.kill()
        raise
    assert code == 0, harness.stderr_text()[-2000:]


def _evaluate(eval_id, *, path="field.dat", bindings, proofs=None):
    params = {"eval_id": eval_id, "mode": "local", "request": {"graph": _graph(path), "outputs": ["stats"]},
              "local_bindings": bindings}
    if proofs is not None:
        params["local_proofs"] = proofs
    return params


def _stats(evaluated):
    output = evaluated["result"]["outputs"]["stats"]
    assert output["type"] == "table" and "columns" in output, output
    # The "field" column is the file stem; the remaining columns are the statistics of the bytes.
    return {name: column for name, column in output["columns"].items() if name != "field"}


def _probe(*, path="field.dat", bindings, proofs=None, position=POINT):
    params = {"graph": _graph(path), "pick": {"node": "stats"}, "local_bindings": bindings,
              "position": [float(x) for x in position]}
    if proofs is not None:
        params["local_proofs"] = proofs
    return params


def _graph_workers(pid):
    """PIDs of the bridge's graph worker children (Linux ``/proc``); ``None`` elsewhere."""
    if not sys.platform.startswith("linux"):
        return None
    found, readable = [], False
    for task in Path(f"/proc/{pid}/task").iterdir():
        try:  # a bridge thread may exit meanwhile; some kernels do not expose children
            children = (task / "children").read_text().split()
        except OSError:
            continue
        readable = True
        for child in children:
            try:
                command = Path(f"/proc/{child}/cmdline").read_bytes().split(b"\0")
            except OSError:
                continue
            if b"suan.desktop_bridge.graph_worker_main" in command:
                found.append(int(child))
    return found if readable else None


def _rejected(harness, method, params, codes):
    """The error of a refused call (an error reply carries no result, hence no sample)."""
    error = harness.error(method, params, timeout=SLOW)
    assert error["code"] in codes, error
    return error


# ---------------------------------------------------------------------------
# Ordinary local bindings (no proof): unchanged behavior


def test_unguarded_local_evaluate_and_probe_follow_the_current_bytes(bridge, collected):
    clean = bridge.call("graph.evaluate", _evaluate("plain-1", bindings=collected.bindings), timeout=SLOW)
    assert clean["result"]["schema"] == "stk.graph-result/1"
    workers = _graph_workers(bridge.process.pid)
    assert workers is None or len(workers) == 1  # the evaluation ran in the graph worker subprocess
    repeat = bridge.call("graph.evaluate", _evaluate("plain-2", bindings=collected.bindings), timeout=SLOW)
    assert _stats(repeat) == _stats(clean) and not {"src", "stats"} & set(repeat["result"]["evaluated"])
    probe = bridge.call("probe", _probe(bindings=collected.bindings), timeout=SLOW)
    assert probe["target"] == {"binding": "run", "path": "field.dat", "node": "src"}
    assert np.allclose(probe["sample"]["values"], _field()[POINT])
    extra = {**collected.bindings, "unused": str(collected.project_root / "missing")}
    assert bridge.call("probe", _probe(bindings=extra), timeout=SLOW)["sample"] == probe["sample"]
    # Without a proof a same-stat rewrite is simply the current data.
    collected.rewrite(collected.changed)
    changed = bridge.call("graph.evaluate", _evaluate("plain-3", bindings=collected.bindings), timeout=SLOW)
    assert _stats(changed) != _stats(clean) and "src" in changed["result"]["evaluated"]
    other = bridge.call("graph.evaluate", _evaluate("plain-4", path="other.dat", bindings=collected.bindings),
                        timeout=SLOW)
    assert _stats(other) == _stats(clean)


# ---------------------------------------------------------------------------
# Guarded (proof-carrying) local bindings


def test_guarded_evaluate_and_probe_reject_warm_same_stat_rewrites(bridge, collected):
    bindings, proofs = collected.bindings, collected.proofs
    first = bridge.call("graph.evaluate", _evaluate("g-1", bindings=bindings, proofs=proofs), timeout=SLOW)
    assert first["result"]["schema"] == "stk.graph-result/1"
    expected = _stats(first)
    workers = _graph_workers(bridge.process.pid)
    assert workers is None or len(workers) == 1
    # An unguarded evaluation of the same bytes gives the same table: the proof only guards the source.
    plain = bridge.call("graph.evaluate", _evaluate("g-plain", bindings=bindings), timeout=SLOW)
    assert _stats(plain) == expected
    warm = bridge.call("graph.evaluate", _evaluate("g-2", bindings=bindings, proofs=proofs), timeout=SLOW)
    assert _stats(warm) == expected and not {"src", "stats"} & set(warm["result"]["evaluated"])

    # Clean samples prime both the guarded path and the bridge's grid cache for field.dat.
    guarded_probe = _probe(bindings=bindings, proofs=proofs)
    sample = bridge.call("probe", guarded_probe, timeout=SLOW)
    assert sample["target"]["binding"] == "run" and sample["target"]["path"] == "field.dat"
    assert "task_id" not in sample["target"]
    assert np.allclose(sample["sample"]["values"], _field()[POINT])
    primed = bridge.call("probe", _probe(bindings=bindings), timeout=SLOW)
    assert np.allclose(primed["sample"]["values"], _field()[POINT])

    collected.rewrite(collected.changed)
    # An unguarded evaluation caches a value for the rewritten bytes (still supported) ...
    plain = bridge.call("graph.evaluate", _evaluate("g-plain-changed", bindings=bindings), timeout=SLOW)
    assert _stats(plain) != expected
    # ... yet the guarded evaluation reads the bytes against the proof and refuses, cache hit or not.
    _rejected(bridge, "graph.evaluate", _evaluate("g-3", bindings=bindings, proofs=proofs), {"graph_error"})
    _rejected(bridge, "graph.evaluate", _evaluate("g-4", bindings=bindings, proofs=proofs), {"graph_error"})
    # The guarded probe refuses after the clean sample primed the grid cache.
    _rejected(bridge, "probe", guarded_probe, {"graph_error", "invalid_params", "not_found"})
    _rejected(bridge, "probe", guarded_probe, {"graph_error", "invalid_params", "not_found"})

    # Restoring the registered bytes makes the same requests valid again.
    collected.rewrite(collected.clean)
    restored = bridge.call("graph.evaluate", _evaluate("g-5", bindings=bindings, proofs=proofs), timeout=SLOW)
    assert _stats(restored) == expected
    sample = bridge.call("probe", guarded_probe, timeout=SLOW)
    assert np.allclose(sample["sample"]["values"], _field()[POINT])
    assert _graph_workers(bridge.process.pid) in (None, workers)  # the same worker served every evaluation


def test_guarded_binding_exposes_only_the_manifest_files(bridge, collected):
    bindings, proofs = collected.bindings, collected.proofs
    # other.dat holds the same bytes as the registered field.dat, but it is not in the manifest.
    _rejected(bridge, "graph.evaluate", _evaluate("s-1", path="other.dat", bindings=bindings, proofs=proofs),
              {"graph_error"})
    _rejected(bridge, "probe", _probe(path="other.dat", bindings=bindings, proofs=proofs),
              {"graph_error", "invalid_params", "not_found"})
    # The same file stays readable through an ordinary binding, and the registered file through the proof.
    plain = bridge.call("graph.evaluate", _evaluate("s-2", path="other.dat", bindings=bindings), timeout=SLOW)
    guarded = bridge.call("graph.evaluate", _evaluate("s-3", bindings=bindings, proofs=proofs), timeout=SLOW)
    assert _stats(plain) == _stats(guarded)
    sample = bridge.call("probe", _probe(path="other.dat", bindings=bindings), timeout=SLOW)
    assert np.allclose(sample["sample"]["values"], _field()[POINT])


# ---------------------------------------------------------------------------
# Hub mode


def test_hub_mode_never_forwards_local_proofs(bridge, collected, runtime, tmp_path):
    pytest.importorskip("fastapi")
    pytest.importorskip("uvicorn")
    pytest.importorskip("httpx")
    from test_desktop_bridge_hub import Hub, pair
    hub = Hub(runtime, tmp_path)
    try:
        hub_id = pair(bridge, hub)

        def requests(kind=None):
            found = [action["request"] for action in hub.store.actions(hub.node_id)]
            return [r for r in found if kind is None or r.get("kind") == kind]

        # Control: an ordinary hub evaluation does create a graph.evaluate action on the hub.
        control = {"eval_id": "hub-control", "mode": "hub", "connection": hub_id, "node": hub.node_id,
                   "request": {"graph": _graph(), "outputs": ["stats"], "bindings": {"run": {"task_id": "a" * 32}}},
                   "wait": 30}
        bridge.response(bridge.request("graph.evaluate", control), timeout=SLOW)  # fails on the node: no such task
        evaluations = len(requests("graph.evaluate"))
        assert evaluations >= 1

        hub_eval = {"eval_id": "hub-proof", "mode": "hub", "connection": hub_id, "node": hub.node_id,
                    "request": {"graph": _graph(), "outputs": ["stats"]}, "local_proofs": collected.proofs,
                    "wait": 30}
        error = bridge.error("graph.evaluate", hub_eval)
        assert error["code"] == "invalid_params", error
        assert len(requests("graph.evaluate")) == evaluations

        # A probe through the hub connection with a proof: whatever it answers, nothing goes to the hub.
        probe = {"graph": _graph(), "pick": {"node": "stats"}, "context": {"bindings": {"run": "a" * 32}},
                 "connection": hub_id, "node": hub.node_id, "local_proofs": collected.proofs,
                 "position": [float(x) for x in POINT]}
        answer = bridge.response(bridge.request("probe", probe, check=False), timeout=SLOW)
        assert "error" not in answer or answer["error"]["code"] != "internal_error", answer
        assert requests("view.probe") == []

        stored = json.dumps(requests(), ensure_ascii=False)
        assert str(collected.project_root) not in stored and "local_proofs" not in stored
        assert collected.proofs["run"]["files"][0]["sha256"] not in stored
    finally:
        hub.close()
