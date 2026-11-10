"""Client-side TaskSpec builder for muFerro runs; safe on any client OS."""

from suan.runtime.launch import LAUNCHERS  # noqa: F401 - re-exported for the MuPRO CLI and launcher
from suan.runtime.models import BACKENDS, TaskSpec, relative_path


def muferro_spec(workspace_id, *, case_dir=".", inputs=None, example=False, ranks=1, threads_per_rank=1,
                 nodes=1, backend="local", program="muFerro", launcher="auto", sdk_prefix=None, env_scripts=(),
                 license_dir=None, walltime_seconds=None, memory_mb=None, queue=None, account=None, name=""):
    """Return TaskSpec keyword arguments; the Runtime validates them on submission."""
    for key, value in (("ranks", ranks), ("threads_per_rank", threads_per_rank), ("nodes", nodes)):
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError(f"{key} must be a positive integer")
    case_dir = "." if case_dir == "." else relative_path(case_dir)
    if example and inputs:
        raise ValueError("An example run stages the SDK example case; inputs must be empty")
    if backend not in BACKENDS:
        raise ValueError("backend must be local, pbs or slurm")
    if backend == "local" and nodes > 1:
        raise ValueError("Local MuPRO jobs run on one node")
    # Cluster time is billed in core-hours (e.g. Paratera), so every job needs a limit.
    if backend != "local" and walltime_seconds is None:
        raise ValueError("Cluster MuPRO jobs require walltime_seconds")
    if launcher not in LAUNCHERS:
        raise ValueError("launcher must be auto, none, mpiexec or srun")
    argv = ["{python}", "-m", "suan.mupro", "run", "--ranks", "{ranks}", "--threads-per-rank", "{threads_per_rank}"]
    if case_dir != ".":
        argv += ["--case-dir", case_dir]
    if example:
        argv.append("--example")
    if program != "muFerro":
        argv += ["--program", program]
    if launcher != "auto":
        argv += ["--launcher", launcher]
    if sdk_prefix:
        argv += ["--sdk-prefix", sdk_prefix]
    for script in env_scripts:
        argv += ["--env-script", script]
    if license_dir:
        argv += ["--license-dir", license_dir]
    resources = {"ranks": ranks, "threads_per_rank": threads_per_rank}
    if nodes > 1:
        resources["nodes"] = nodes
    for key, value in (("walltime_seconds", walltime_seconds), ("memory_mb", memory_mb),
                       ("queue", queue), ("account", account)):
        if value is not None:
            resources[key] = value
    return {"workspace_id": workspace_id, "argv": argv, "backend": backend, "name": name,
            "inputs": [] if example else (None if inputs is None else list(inputs)),
            "outputs": ["stk-mupro.json"], "env": {}, "resources": resources}


def preflight_spec(workspace_id, *, backend="local", walltime_seconds=None, memory_mb=None, queue=None,
                   account=None, name=""):
    """Return validated TaskSpec keyword arguments for an explicit compute-side preflight task.

    The task runs ``python -m suan.mupro.preflight`` in the selected environment and observes
    that worker's configured MuPRO settings. The client stages no case and passes no SDK,
    program, script, licence or environment values; only scheduler resources are accepted.
    """
    if backend not in BACKENDS:
        raise ValueError("backend must be local, pbs or slurm")
    if backend != "local" and walltime_seconds is None:
        raise ValueError("Cluster MuPRO jobs require walltime_seconds")
    resources = {"cpus": 1}
    for key, value in (("walltime_seconds", walltime_seconds), ("memory_mb", memory_mb),
                       ("queue", queue), ("account", account)):
        if value is not None:
            resources[key] = value
    spec = {"workspace_id": workspace_id, "argv": ["{python}", "-m", "suan.mupro.preflight"],
            "backend": backend, "name": name, "inputs": [], "outputs": ["stk-mupro-preflight.json"],
            "env": {}, "resources": resources}
    # Full Runtime validation (numbers, local queue/account, IDs) before any submission effect.
    TaskSpec(**spec)
    return spec
